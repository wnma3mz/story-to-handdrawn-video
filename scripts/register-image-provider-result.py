#!/usr/bin/env python3
"""Register one already-downloaded external image result without networking.

This is deliberately a narrow, fail-closed boundary.  It verifies a canonical
atomic-reference request, its canonical index, the provider capability profile,
a secret-free execution receipt, and a real PNG.  It may write only the
request-declared provider-original attempt directory.  Review candidates and
formal targets are never written or promoted here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


REQUEST_SCHEMA = "image-job-request/v1"
INDEX_SCHEMA = "canonical-image-job-index/v1"
PROFILE_SCHEMA = "image-provider-capability/v1"
EXECUTION_SCHEMA = "provider-execution/v1"
RESULT_SCHEMA = "image-result-provenance/v1"
AUTHORIZED_PHASE = "atomic_reference"
FORMAL_MASTER_EDGE_PX = 1254
ATTEMPT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
UTC_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T"
    r"(?P<time>\d{2}:\d{2}:\d{2})(?P<fraction>\.\d{1,6})?Z$"
)
RECEIPT_FIELDS = {
    "schema",
    "provider_id",
    "provider_profile_sha256",
    "model_id",
    "attempt_id",
    "submitted_at_utc",
    "completed_at_utc",
    "provider_request_id",
    "status",
    "canonical_request_sha256",
    "canonical_index_sha256",
    "input_fingerprint_sha256",
    "idempotency_key",
    "ordered_reference_sha256",
}
SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "access_token",
    "bearer_token",
    "client_secret",
    "credential",
    "secret",
    "token",
    "password",
    "cookie",
    "header",
)


class ContractError(ValueError):
    """A fail-closed registration contract violation."""


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read valid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"JSON document must be an object: {path}")
    return value


def workspace_path(
    value: str | Path, workspace: Path, *, must_be_file: bool = False
) -> tuple[Path, str]:
    path = Path(value)
    absolute = (path if path.is_absolute() else workspace / path).resolve()
    try:
        relative = absolute.relative_to(workspace)
    except ValueError as exc:
        raise ContractError(f"path escapes workspace: {value}") from exc
    if must_be_file and not absolute.is_file():
        raise ContractError(f"required file is missing: {relative.as_posix()}")
    return absolute, relative.as_posix()


def reject_secret_fields(value: object, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            declared_secret_prohibition = (
                location == "$.provider_execution_schema"
                and normalized == "secret_material"
                and child == "forbidden_in_files"
            )
            if not declared_secret_prohibition and any(
                fragment in normalized for fragment in SECRET_KEY_FRAGMENTS
            ):
                raise ContractError(
                    f"secret-bearing field is forbidden: {location}.{key}"
                )
            reject_secret_fields(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_secret_fields(child, f"{location}[{index}]")


def nonempty_text(value: object, field: str, *, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ContractError(f"{field} must be non-empty, trimmed printable text")
    return value


def parse_utc(value: object, field: str) -> datetime:
    text = nonempty_text(value, field, maximum=32)
    if not UTC_RE.fullmatch(text):
        raise ContractError(f"{field} must be strict RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{field} is not a real UTC timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ContractError(f"{field} must use UTC")
    return parsed


def validate_profile(profile: dict[str, Any]) -> None:
    if profile.get("schema") != PROFILE_SCHEMA:
        raise ContractError(f"provider profile schema must be {PROFILE_SCHEMA}")
    nonempty_text(profile.get("provider_id"), "provider_id")
    for field in (
        "max_reference_images",
        "minimum_input_edge_px",
        "maximum_output_edge_px",
    ):
        if not isinstance(profile.get(field), int) or profile[field] < 1:
            raise ContractError(f"provider profile {field} must be a positive integer")
    for field in ("reference_order_preserved", "labeled_references", "square_output"):
        if not isinstance(profile.get(field), bool):
            raise ContractError(f"provider profile {field} must be boolean")
    for field in ("accepted_input_formats", "supported_output_formats"):
        values = profile.get(field)
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(item, str) or not item for item in values)
        ):
            raise ContractError(f"provider profile {field} must be a string list")
    reject_secret_fields(profile)


def validate_request_fingerprint(request: dict[str, Any]) -> None:
    final_fields = {
        "input_fingerprint_sha256",
        "idempotency_key",
        "provider_execution_schema",
        "result_provenance_schema",
    }
    if not final_fields.issubset(request):
        raise ContractError("canonical request is missing fingerprint contract fields")
    core = {key: value for key, value in request.items() if key not in final_fields}
    expected = sha256_bytes(canonical_bytes(core))
    if request["input_fingerprint_sha256"] != expected:
        raise ContractError("canonical request input fingerprint does not verify")
    expected_key = (
        f"{REQUEST_SCHEMA}:{request.get('episode')}:{request.get('job_id')}:{expected}"
    )
    if request["idempotency_key"] != expected_key:
        raise ContractError("canonical request idempotency key does not verify")


def validate_request(request: dict[str, Any]) -> list[dict[str, Any]]:
    if (
        request.get("schema") != REQUEST_SCHEMA
        or request.get("phase") != AUTHORIZED_PHASE
        or request.get("role") != "reference"
    ):
        raise ContractError("only canonical atomic-reference requests may be registered")
    job_id = nonempty_text(request.get("job_id"), "request job_id", maximum=128)
    if "/" in job_id or "\\" in job_id or job_id in {".", ".."}:
        raise ContractError("request job_id is not path-safe")
    authorization = request.get("authorization")
    if (
        not isinstance(authorization, dict)
        or authorization.get("authorized") is not True
        or authorization.get("authorized_phase") != AUTHORIZED_PHASE
        or authorization.get("authorized_role") != "reference"
        or authorization.get("scene_generation_authorized") is not False
    ):
        raise ContractError("request authorization is not fail-closed atomic_reference")
    output = request.get("output_contract")
    if (
        not isinstance(output, dict)
        or output.get("format") != "image/png"
        or output.get("direct_formal_write_authorized") is not False
    ):
        raise ContractError("request output contract permits an unsafe output")
    canvas = output.get("canvas")
    if (
        not isinstance(canvas, dict)
        or canvas.get("shape") != "square"
        or not isinstance(canvas.get("minimum_edge_px"), int)
        or canvas["minimum_edge_px"] < FORMAL_MASTER_EDGE_PX
    ):
        raise ContractError("request must require a square PNG of at least 1254px")
    result_schema = request.get("result_provenance_schema")
    if (
        not isinstance(result_schema, dict)
        or result_schema.get("schema") != RESULT_SCHEMA
        or result_schema.get("direct_promotion_authorized") is not False
        or result_schema.get("review_state_on_arrival")
        != "unapproved_provider_original"
    ):
        raise ContractError("request result provenance contract is unsafe")
    execution_schema = request.get("provider_execution_schema")
    if (
        not isinstance(execution_schema, dict)
        or execution_schema.get("schema") != EXECUTION_SCHEMA
        or execution_schema.get("secret_material") != "forbidden_in_files"
    ):
        raise ContractError("request provider execution schema is invalid")
    references = request.get("ordered_references")
    if not isinstance(references, list) or not references:
        raise ContractError("request has no ordered references")
    for expected_ordinal, reference in enumerate(references, start=1):
        if (
            not isinstance(reference, dict)
            or reference.get("ordinal") != expected_ordinal
            or not isinstance(reference.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", reference["sha256"])
        ):
            raise ContractError("ordered reference contract is malformed or reordered")
        nonempty_text(reference.get("label"), "reference label")
        nonempty_text(reference.get("path"), "reference path", maximum=1024)
    validate_request_fingerprint(request)
    reject_secret_fields(request)
    return references


def validate_index(
    index: dict[str, Any],
    request: dict[str, Any],
    request_relative: str,
    request_sha: str,
    profile: dict[str, Any],
    profile_sha: str,
) -> None:
    if (
        index.get("schema") != INDEX_SCHEMA
        or index.get("phase") != AUTHORIZED_PHASE
        or index.get("episode") != request.get("episode")
        or index.get("scene_generation_authorized") is not False
        or index.get("execution_available") is not False
        or index.get("network_calls_performed") != 0
    ):
        raise ContractError("canonical index safety contract does not verify")
    compatibility = index.get("provider_compatibility_validation")
    if (
        not isinstance(compatibility, dict)
        or compatibility.get("provider_id") != profile["provider_id"]
        or compatibility.get("profile_sha256") != profile_sha
        or compatibility.get("status") != "SUPPORTED_EXACT_NO_FALLBACK"
        or compatibility.get("reference_reduction_used") is not False
        or compatibility.get("reference_montage_used") is not False
    ):
        raise ContractError("provider profile hash/capability binding does not verify")
    entries = index.get("requests")
    if not isinstance(entries, list):
        raise ContractError("canonical index requests must be a list")
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("job_id") == request["job_id"]
    ]
    if len(matches) != 1:
        raise ContractError("canonical index must contain exactly one request entry")
    entry = matches[0]
    expected = {
        "job_id": request["job_id"],
        "path": request_relative,
        "request_sha256": request_sha,
        "input_fingerprint_sha256": request["input_fingerprint_sha256"],
        "idempotency_key": request["idempotency_key"],
    }
    if entry != expected:
        raise ContractError("canonical request/index hash binding does not verify")
    reject_secret_fields(index)


def validate_reference_files(
    references: list[dict[str, Any]], workspace: Path
) -> None:
    for reference in references:
        path, relative = workspace_path(reference["path"], workspace, must_be_file=True)
        if relative != reference["path"]:
            raise ContractError("ordered reference path is not canonical")
        if sha256_file(path) != reference["sha256"]:
            raise ContractError(
                f"ordered reference hash no longer matches: {reference['path']}"
            )


def validate_receipt(
    receipt: dict[str, Any],
    *,
    request: dict[str, Any],
    request_sha: str,
    index_sha: str,
    profile: dict[str, Any],
    profile_sha: str,
    references: list[dict[str, Any]],
) -> str:
    reject_secret_fields(receipt)
    if set(receipt) != RECEIPT_FIELDS:
        missing = sorted(RECEIPT_FIELDS - set(receipt))
        extra = sorted(set(receipt) - RECEIPT_FIELDS)
        raise ContractError(
            f"execution receipt fields differ; missing={missing}, extra={extra}"
        )
    if receipt["schema"] != EXECUTION_SCHEMA:
        raise ContractError(f"execution receipt schema must be {EXECUTION_SCHEMA}")
    if receipt["status"] != "succeeded":
        raise ContractError("only status=succeeded results may be registered")
    for field in ("provider_id", "model_id", "provider_request_id"):
        nonempty_text(receipt[field], f"receipt {field}")
    attempt_id = nonempty_text(receipt["attempt_id"], "receipt attempt_id", maximum=64)
    if not ATTEMPT_RE.fullmatch(attempt_id):
        raise ContractError(
            "attempt_id must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}"
        )
    submitted = parse_utc(receipt["submitted_at_utc"], "submitted_at_utc")
    completed = parse_utc(receipt["completed_at_utc"], "completed_at_utc")
    if completed < submitted:
        raise ContractError("completed_at_utc precedes submitted_at_utc")
    expected_scalars = {
        "provider_id": profile["provider_id"],
        "provider_profile_sha256": profile_sha,
        "canonical_request_sha256": request_sha,
        "canonical_index_sha256": index_sha,
        "input_fingerprint_sha256": request["input_fingerprint_sha256"],
        "idempotency_key": request["idempotency_key"],
    }
    for field, expected in expected_scalars.items():
        if receipt[field] != expected:
            raise ContractError(f"execution receipt {field} binding does not verify")
    expected_hashes = [reference["sha256"] for reference in references]
    if receipt["ordered_reference_sha256"] != expected_hashes:
        raise ContractError("execution receipt ordered reference hashes do not verify")
    return attempt_id


def validate_png(
    path: Path, minimum_edge: int, maximum_edge: int
) -> tuple[int, int, str, int, str]:
    if not path.is_file():
        raise ContractError(f"downloaded provider PNG is missing: {path}")
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise ContractError("provider result must be a real PNG")
            image.verify()
        with Image.open(path) as image:
            if image.format != "PNG":
                raise ContractError("provider result changed during validation")
            if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) != 1:
                raise ContractError("animated/multi-frame PNG results are forbidden")
            image.load()
            width, height = image.size
            mode = image.mode
    except ContractError:
        raise
    except (OSError, UnidentifiedImageError, SyntaxError, ValueError) as exc:
        raise ContractError(f"provider result is not a decodable PNG: {exc}") from exc
    if width != height:
        raise ContractError(f"provider PNG must be square, got {width}x{height}")
    if width < minimum_edge or width < FORMAL_MASTER_EDGE_PX:
        raise ContractError(
            f"provider PNG edge {width}px is below required {minimum_edge}px"
        )
    if width > maximum_edge:
        raise ContractError(
            f"provider PNG edge {width}px exceeds provider maximum {maximum_edge}px"
        )
    return width, height, mode, path.stat().st_size, sha256_file(path)


def destination_for(
    request: dict[str, Any], workspace: Path, attempt_id: str
) -> tuple[Path, str]:
    template = request["output_contract"].get("provider_original_path_template")
    if not isinstance(template, str) or template.count("{attempt_id}") != 1:
        raise ContractError("provider original path template is invalid")
    if "{" in template.replace("{attempt_id}", "") or "}" in template.replace(
        "{attempt_id}", ""
    ):
        raise ContractError("provider original path template has unknown placeholders")
    destination, relative = workspace_path(
        template.replace("{attempt_id}", attempt_id), workspace
    )
    expected_tail = (
        Path("image-jobs")
        / "provider-execution"
        / request["job_id"]
        / attempt_id
        / "original.png"
    )
    relative_path = Path(relative)
    if (
        destination.name != "original.png"
        or len(relative_path.parts) < len(expected_tail.parts)
        or relative_path.parts[-len(expected_tail.parts) :] != expected_tail.parts
    ):
        raise ContractError("provider original path template targets an unsafe location")
    if any(part in {"candidates", "candidate", "formal"} for part in relative_path.parts):
        raise ContractError("provider original path may not target candidates or formal files")
    return destination, relative


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def existing_is_identical(
    attempt_dir: Path, source_sha: str, provenance_bytes: bytes
) -> bool:
    original = attempt_dir / "original.png"
    provenance = attempt_dir / "result-provenance.json"
    try:
        entries = {path.name for path in attempt_dir.iterdir()}
    except OSError:
        return False
    return (
        entries == {"original.png", "result-provenance.json"}
        and original.is_file()
        and provenance.is_file()
        and sha256_file(original) == source_sha
        and provenance.read_bytes() == provenance_bytes
    )


def store_attempt_atomically(
    source: Path,
    destination: Path,
    provenance_bytes: bytes,
    source_sha: str,
) -> str:
    attempt_dir = destination.parent
    attempts_parent = attempt_dir.parent
    attempts_parent.mkdir(parents=True, exist_ok=True)
    if attempt_dir.exists():
        if attempt_dir.is_dir() and existing_is_identical(
            attempt_dir, source_sha, provenance_bytes
        ):
            return "IDEMPOTENT"
        raise ContractError(f"conflicting immutable attempt already exists: {attempt_dir}")
    temporary = Path(tempfile.mkdtemp(prefix=".register-", dir=attempts_parent))
    try:
        staged_original = temporary / "original.png"
        staged_provenance = temporary / "result-provenance.json"
        shutil.copyfile(source, staged_original)
        if sha256_file(staged_original) != source_sha:
            raise ContractError("provider PNG changed while it was being copied")
        with staged_original.open("rb") as handle:
            os.fsync(handle.fileno())
        with staged_provenance.open("xb") as handle:
            handle.write(provenance_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            temporary.rename(attempt_dir)
        except FileExistsError:
            if attempt_dir.is_dir() and existing_is_identical(
                attempt_dir, source_sha, provenance_bytes
            ):
                return "IDEMPOTENT"
            raise ContractError(
                f"conflicting immutable attempt appeared concurrently: {attempt_dir}"
            )
        fsync_directory(attempts_parent)
        return "REGISTERED"
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def register(args: argparse.Namespace) -> tuple[str, str]:
    workspace = Path(args.workspace).resolve()
    request_path, request_relative = workspace_path(
        args.request, workspace, must_be_file=True
    )
    index_path, index_relative = workspace_path(
        args.index, workspace, must_be_file=True
    )
    profile_path, profile_relative = workspace_path(
        args.provider_profile, workspace, must_be_file=True
    )
    receipt_path, receipt_relative = workspace_path(
        args.execution_receipt, workspace, must_be_file=True
    )
    source = Path(args.provider_png).resolve()

    request = load_json(request_path)
    index = load_json(index_path)
    profile = load_json(profile_path)
    receipt = load_json(receipt_path)
    references = validate_request(request)
    validate_profile(profile)

    if request_path.read_bytes() != canonical_bytes(request):
        raise ContractError("request file is not canonical deterministic JSON")
    if index_path.read_bytes() != canonical_bytes(index):
        raise ContractError("index file is not canonical deterministic JSON")
    request_sha = sha256_bytes(canonical_bytes(request))
    index_sha = sha256_bytes(canonical_bytes(index))
    profile_sha = sha256_bytes(canonical_bytes(profile))
    validate_index(
        index,
        request,
        request_relative,
        request_sha,
        profile,
        profile_sha,
    )
    validate_reference_files(references, workspace)
    attempt_id = validate_receipt(
        receipt,
        request=request,
        request_sha=request_sha,
        index_sha=index_sha,
        profile=profile,
        profile_sha=profile_sha,
        references=references,
    )

    minimum_edge = max(
        request["output_contract"]["canvas"]["minimum_edge_px"],
        request.get("provider_requirements", {}).get(
            "minimum_output_edge_px", FORMAL_MASTER_EDGE_PX
        ),
    )
    width, height, mode, size_bytes, source_sha = validate_png(
        source, minimum_edge, profile["maximum_output_edge_px"]
    )
    destination, destination_relative = destination_for(
        request, workspace, attempt_id
    )
    provenance = {
        "schema": RESULT_SCHEMA,
        "review_state": "unapproved_provider_original",
        "direct_promotion_authorized": False,
        "direct_formal_write_authorized": False,
        "scene_generation_authorized": False,
        "network_calls_performed": 0,
        "canonical_request": {
            "path": request_relative,
            "sha256": request_sha,
            "job_id": request["job_id"],
            "episode": request["episode"],
            "input_fingerprint_sha256": request["input_fingerprint_sha256"],
            "idempotency_key": request["idempotency_key"],
        },
        "canonical_index": {"path": index_relative, "sha256": index_sha},
        "provider_profile": {
            "path": profile_relative,
            "sha256": profile_sha,
            "provider_id": profile["provider_id"],
        },
        "provider_execution_receipt": {
            "path": receipt_relative,
            "sha256": sha256_bytes(canonical_bytes(receipt)),
            "record": receipt,
        },
        "ordered_references": [
            {
                "ordinal": reference["ordinal"],
                "label": reference["label"],
                "path": reference["path"],
                "sha256": reference["sha256"],
            }
            for reference in references
        ],
        "result": {
            "original_path": destination_relative,
            "original_sha256": source_sha,
            "media_type": "image/png",
            "width": width,
            "height": height,
            "mode": mode,
            "bytes": size_bytes,
        },
        "writes": {
            "provider_original_written": True,
            "candidate_written": False,
            "formal_target_written": False,
        },
    }
    reject_secret_fields(provenance)
    status = store_attempt_atomically(
        source, destination, canonical_bytes(provenance), source_sha
    )
    return status, destination_relative


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify and register one downloaded provider PNG. "
            "No network calls, review candidates, or formal promotions are performed."
        )
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--provider-profile", required=True)
    parser.add_argument("--execution-receipt", required=True)
    parser.add_argument("--provider-png", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        status, path = register(args)
        print(
            f"{status} immutable provider original: {path}; "
            "direct promotion=false, network calls=0"
        )
        return 0
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
