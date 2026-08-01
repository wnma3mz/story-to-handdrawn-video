#!/usr/bin/env python3
"""Compile and validate provider-neutral image generation requests.

This module deliberately has no provider execution command.  ``plan`` writes
only deterministic request JSON under an episode's ``image-jobs/canonical``
directory; ``validate`` is read-only.  Provider originals, reviewed
candidates, and promoted reference/scene masters are outside this compiler's
authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUEST_SCHEMA = "image-job-request/v1"
INDEX_SCHEMA = "canonical-image-job-index/v1"
PROFILE_SCHEMA = "image-provider-capability/v1"
EXECUTION_SCHEMA = "provider-execution/v1"
RESULT_SCHEMA = "image-result-provenance/v1"
AUTHORIZED_PHASE = "atomic_reference"
FORMAL_MASTER_EDGE_PX = 1254
FORBIDDEN_SECRET_NAMES = {
    "api_key",
    "apikey",
    "access_token",
    "bearer_token",
    "client_secret",
    "credential",
    "credentials",
    "secret",
    "token",
}


class ContractError(ValueError):
    """A fail-closed contract violation."""


@dataclass(frozen=True)
class ImageInfo:
    media_type: str
    width: int
    height: int


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


def workspace_relative(path_value: str, workspace: Path) -> tuple[Path, str]:
    path = Path(path_value)
    absolute = path if path.is_absolute() else workspace / path
    absolute = absolute.resolve()
    try:
        relative = absolute.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ContractError(f"path escapes workspace: {path_value}") from exc
    return absolute, relative.as_posix()


def require_file(path_value: str, workspace: Path, label: str) -> tuple[Path, str]:
    absolute, relative = workspace_relative(path_value, workspace)
    if not absolute.is_file():
        raise ContractError(f"{label} is missing: {relative}")
    return absolute, relative


def image_info(path: Path) -> ImageInfo:
    header = path.read_bytes()[:32]
    if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", header[16:24])
        if width < 1 or height < 1:
            raise ContractError(f"invalid PNG dimensions: {path}")
        return ImageInfo("image/png", width, height)
    if header[:3] == b"\xff\xd8\xff":
        data = path.read_bytes()
        cursor = 2
        while cursor + 9 <= len(data):
            if data[cursor] != 0xFF:
                cursor += 1
                continue
            marker = data[cursor + 1]
            cursor += 2
            if marker in {0xD8, 0xD9}:
                continue
            if cursor + 2 > len(data):
                break
            length = struct.unpack(">H", data[cursor : cursor + 2])[0]
            if length < 2 or cursor + length > len(data):
                break
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                height, width = struct.unpack(">HH", data[cursor + 3 : cursor + 7])
                return ImageInfo("image/jpeg", width, height)
            cursor += length
    raise ContractError(f"unsupported or invalid input image: {path}")


def ensure_no_secret_fields(value: object, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in FORBIDDEN_SECRET_NAMES:
                raise ContractError(
                    f"secret-bearing field {location}.{key} is forbidden in provenance"
                )
            ensure_no_secret_fields(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            ensure_no_secret_fields(child, f"{location}[{index}]")


def validate_profile(profile: dict[str, Any]) -> None:
    if profile.get("schema") != PROFILE_SCHEMA:
        raise ContractError(f"provider profile schema must be {PROFILE_SCHEMA}")
    provider_id = profile.get("provider_id")
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ContractError("provider profile requires a non-empty provider_id")
    integer_fields = (
        "max_reference_images",
        "minimum_input_edge_px",
        "maximum_output_edge_px",
    )
    for field in integer_fields:
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
            raise ContractError(f"provider profile {field} must be a non-empty string list")
    ensure_no_secret_fields(profile)


def authorization(plan: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    phase = plan.get("phase_authorization")
    if not isinstance(phase, dict):
        raise ContractError("atomic plan has no phase_authorization object")
    allowed = phase.get("authorized_job_ids")
    if (
        phase.get("schema") != "image-generation-phase-authorization/v1"
        or phase.get("authorized_phase") != AUTHORIZED_PHASE
        or phase.get("authorized_role") != "reference"
        or phase.get("scene_generation_authorized") is not False
        or not isinstance(allowed, list)
        or not allowed
        or any(not isinstance(item, str) or not item for item in allowed)
        or len(allowed) != len(set(allowed))
    ):
        raise ContractError("invalid fail-closed atomic-reference phase authorization")
    if plan.get("execution_authorized") is not False:
        raise ContractError("legacy execution_authorized must remain false")
    if plan.get("scene_generation_authorized") is not False:
        raise ContractError("scene_generation_authorized must be false")
    return allowed, phase


def reference_label(path: str, ordinal: int) -> str:
    name = Path(path).stem.lower().replace("_", "-")
    return f"reference-{ordinal:02d}-{name}"


def output_contract(
    episode_relative: str,
    job_id: str,
    formal_target: str,
) -> dict[str, Any]:
    return {
        "provider_original_path_template": (
            f"{episode_relative}/image-jobs/provider-execution/"
            f"{job_id}/{{attempt_id}}/original.png"
        ),
        "format": "image/png",
        "canvas": {
            "shape": "square",
            "minimum_edge_px": FORMAL_MASTER_EDGE_PX,
        },
        "formal_target_path": formal_target,
        "direct_formal_write_authorized": False,
        "promotion_gate": [
            "full_resolution_semantic_review",
            "single_panel_and_text_free_review",
            "exact_white_border_audit",
            "approved_hash_freeze",
        ],
    }


def compile_requests(
    workspace: Path,
    episode: Path,
    profile: dict[str, Any],
    requested_job_ids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compile all authorized requests in memory, without writing anything."""

    workspace = workspace.resolve()
    episode = episode.resolve()
    try:
        episode_relative = episode.relative_to(workspace).as_posix()
    except ValueError as exc:
        raise ContractError("episode directory is outside the workspace") from exc
    validate_profile(profile)

    manifest_path = episode / "codex-image-jobs.json"
    map_path = episode / "reference-map.json"
    plan_path = episode / "ATOMIC_REFERENCE_PLAN.json"
    manifest = load_json(manifest_path)
    reference_map = load_json(map_path)
    plan = load_json(plan_path)
    allowed_ids, phase = authorization(plan)
    if manifest.get("execution_authorized") is not False:
        raise ContractError("manifest execution_authorized must remain false")
    if manifest.get("scene_generation_authorized") is not False:
        raise ContractError("manifest scene_generation_authorized must be false")
    if manifest.get("phase_authorization") != phase:
        raise ContractError("manifest and atomic-plan phase authorization disagree")

    if requested_job_ids:
        unauthorized = sorted(set(requested_job_ids) - set(allowed_ids))
        if unauthorized:
            raise ContractError(
                "requested jobs are not authorized for atomic_reference: "
                + ", ".join(unauthorized)
            )
        if set(requested_job_ids) != set(allowed_ids):
            raise ContractError(
                "partial canonical plans are forbidden; request the exact authorized job set"
            )

    plan_jobs = plan.get("jobs")
    manifest_jobs = manifest.get("jobs")
    references = reference_map.get("references")
    style_references = reference_map.get("style_references")
    if not isinstance(plan_jobs, list) or not isinstance(manifest_jobs, list):
        raise ContractError("manifest and atomic plan must contain job lists")
    if not isinstance(references, dict):
        raise ContractError("reference-map references must be an object")
    if (
        not isinstance(style_references, list)
        or not style_references
        or any(not isinstance(item, str) for item in style_references)
    ):
        raise ContractError("reference-map style_references must be a non-empty list")
    style_reference_relatives = [
        workspace_relative(item, workspace)[1] for item in style_references
    ]

    plan_by_id = {
        item.get("id"): item
        for item in plan_jobs
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    manifest_by_id = {
        item.get("id"): item
        for item in manifest_jobs
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if set(plan_by_id) != set(allowed_ids):
        raise ContractError("authorization must exactly match all atomic-plan job ids")
    if any(
        manifest_by_id.get(job_id, {}).get("role") != "reference"
        for job_id in allowed_ids
    ):
        raise ContractError("every authorized job must have role=reference in the manifest")

    compiled: list[dict[str, Any]] = []
    for job_id in allowed_ids:
        plan_job = plan_by_id[job_id]
        manifest_job = manifest_by_id[job_id]
        key = plan_job.get("key")
        if manifest_job.get("reference_key") != key:
            raise ContractError(f"reference key mismatch for {job_id}")
        definition = references.get(key)
        if (
            not isinstance(definition, dict)
            or definition.get("generated_by_job") != job_id
            or definition.get("status")
            != "contract_ready_atomic_image_pending_provider"
        ):
            raise ContractError(f"reference-map does not declare pending producer {job_id}")

        prompt_path, prompt_relative = require_file(
            str(manifest_job.get("prompt_file", "")), workspace, f"{job_id} prompt"
        )
        plan_prompt_path = plan_job.get("prompt_file")
        if plan_prompt_path != prompt_relative:
            raise ContractError(f"prompt path mismatch for {job_id}")
        prompt_text = manifest_job.get("prompt")
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            raise ContractError(f"empty manifest prompt for {job_id}")
        disk_prompt = prompt_path.read_text(encoding="utf-8").rstrip("\r\n")
        if disk_prompt != prompt_text or plan_job.get("prompt") != prompt_text:
            raise ContractError(f"prompt sources disagree for {job_id}")

        formal_path, formal_relative = workspace_relative(
            str(manifest_job.get("output_master", "")), workspace
        )
        expected_formal, expected_formal_relative = workspace_relative(
            str(definition.get("path", "")), workspace
        )
        if formal_path != expected_formal:
            raise ContractError(f"formal output target mismatch for {job_id}")
        if formal_path.exists():
            raise ContractError(
                f"formal target already exists without promotion evidence: {formal_relative}"
            )
        expected_filename = plan_job.get("output")
        if (
            not isinstance(expected_filename, str)
            or Path(expected_filename).name != Path(formal_relative).name
            or formal_relative != expected_formal_relative
        ):
            raise ContractError(f"atomic-plan output mismatch for {job_id}")

        manifest_refs = manifest_job.get("references")
        if not isinstance(manifest_refs, list) or not manifest_refs:
            raise ContractError(f"{job_id} has no ordered references")
        if len(manifest_refs) > profile["max_reference_images"]:
            raise ContractError(
                f"UNSUPPORTED provider {profile['provider_id']}: {job_id} needs "
                f"{len(manifest_refs)} ordered references, max is "
                f"{profile['max_reference_images']}; reducing or compositing references "
                "is forbidden"
            )
        if not profile["reference_order_preserved"]:
            raise ContractError(
                f"UNSUPPORTED provider {profile['provider_id']}: ordered references required"
            )
        if not profile["labeled_references"]:
            raise ContractError(
                f"UNSUPPORTED provider {profile['provider_id']}: labeled references required"
            )

        ordered_references: list[dict[str, Any]] = []
        for ordinal, path_value in enumerate(manifest_refs, start=1):
            if not isinstance(path_value, str):
                raise ContractError(f"non-string reference in {job_id}")
            ref_path, ref_relative = require_file(
                path_value, workspace, f"{job_id} reference {ordinal}"
            )
            info = image_info(ref_path)
            if info.media_type not in profile["accepted_input_formats"]:
                raise ContractError(
                    f"UNSUPPORTED provider {profile['provider_id']}: "
                    f"{info.media_type} input is not accepted"
                )
            if min(info.width, info.height) < profile["minimum_input_edge_px"]:
                raise ContractError(
                    f"UNSUPPORTED provider {profile['provider_id']}: {ref_relative} "
                    f"edge {min(info.width, info.height)} is below required "
                    f"{profile['minimum_input_edge_px']}"
                )
            ordered_references.append(
                {
                    "ordinal": ordinal,
                    "label": reference_label(ref_relative, ordinal),
                    "path": ref_relative,
                    "sha256": sha256_file(ref_path),
                    "media_type": info.media_type,
                    "width": info.width,
                    "height": info.height,
                }
            )
        if [
            item["path"] for item in ordered_references[: len(style_reference_relatives)]
        ] != style_reference_relatives:
            raise ContractError(
                f"style reference order differs from reference-map for {job_id}"
            )

        if "image/png" not in profile["supported_output_formats"]:
            raise ContractError(
                f"UNSUPPORTED provider {profile['provider_id']}: PNG output required"
            )
        if not profile["square_output"]:
            raise ContractError(
                f"UNSUPPORTED provider {profile['provider_id']}: square output required"
            )
        if profile["maximum_output_edge_px"] < FORMAL_MASTER_EDGE_PX:
            raise ContractError(
                f"UNSUPPORTED provider {profile['provider_id']}: "
                f"{FORMAL_MASTER_EDGE_PX}px output required"
            )

        source_refs = plan_job.get("source_references")
        if not isinstance(source_refs, list):
            raise ContractError(f"source_references must be a list for {job_id}")
        source_ref_relatives = [
            workspace_relative(str(value), workspace)[1] for value in source_refs
        ]
        actual_non_style = [
            item["path"]
            for item in ordered_references
            if item["path"] not in set(style_reference_relatives)
        ]
        if actual_non_style != source_ref_relatives:
            raise ContractError(
                f"manifest reference order/source donors disagree for {job_id}"
            )
        expected_source_hashes = plan_job.get("source_reference_sha256")
        if not isinstance(expected_source_hashes, dict):
            raise ContractError(f"missing source hash contract for {job_id}")
        for relative in source_ref_relatives:
            actual = next(
                item["sha256"]
                for item in ordered_references
                if item["path"] == relative
            )
            if expected_source_hashes.get(relative) != actual:
                raise ContractError(f"frozen donor hash mismatch for {job_id}: {relative}")

        request_core: dict[str, Any] = {
            "schema": REQUEST_SCHEMA,
            "episode": str(plan.get("episode")),
            "job_id": job_id,
            "phase": AUTHORIZED_PHASE,
            "role": "reference",
            "reference_key": key,
            "authorization": {
                "schema": phase["schema"],
                "authorized": True,
                "authorized_phase": phase["authorized_phase"],
                "authorized_role": phase["authorized_role"],
                "scene_generation_authorized": False,
                "source": f"{episode_relative}/ATOMIC_REFERENCE_PLAN.json",
            },
            "prompt": {
                "path": prompt_relative,
                "file_sha256": sha256_file(prompt_path),
                "text_sha256": sha256_bytes(prompt_text.encode("utf-8")),
                "text": prompt_text,
            },
            "ordered_references": ordered_references,
            "provider_requirements": {
                "minimum_max_reference_images": len(ordered_references),
                "reference_order_preserved": True,
                "labeled_references": True,
                "accepted_input_formats": sorted(
                    {item["media_type"] for item in ordered_references}
                ),
                "minimum_input_edge_px": min(
                    min(item["width"], item["height"])
                    for item in ordered_references
                ),
                "required_output_format": "image/png",
                "required_square_output": True,
                "minimum_output_edge_px": FORMAL_MASTER_EDGE_PX,
                "fallback_reference_reduction_authorized": False,
                "fallback_reference_montage_authorized": False,
            },
            "output_contract": output_contract(
                episode_relative, job_id, formal_relative
            ),
            "content_contract": {
                "atomic_kind": plan_job.get("kind"),
                "single_panel": True,
                "contains_text": False,
                "pure_white_background": True,
                "minimum_exact_white_safe_border_fraction": 0.10,
                "semantic_review_required": True,
            },
        }
        fingerprint = sha256_bytes(canonical_bytes(request_core))
        request = {
            **request_core,
            "input_fingerprint_sha256": fingerprint,
            "idempotency_key": (
                f"{REQUEST_SCHEMA}:{plan.get('episode')}:{job_id}:{fingerprint}"
            ),
            "provider_execution_schema": {
                "schema": EXECUTION_SCHEMA,
                "required_fields_at_execution": [
                    "provider_id",
                    "provider_profile_sha256",
                    "model_id",
                    "attempt_id",
                    "submitted_at_utc",
                    "completed_at_utc",
                    "provider_request_id",
                    "status",
                ],
                "secret_material": "forbidden_in_files",
            },
            "result_provenance_schema": {
                "schema": RESULT_SCHEMA,
                "bind_to": [
                    "input_fingerprint_sha256",
                    "idempotency_key",
                    "ordered_reference_sha256",
                    "provider_execution",
                ],
                "required_result_fields": [
                    "original_path",
                    "original_sha256",
                    "media_type",
                    "width",
                    "height",
                ],
                "review_state_on_arrival": "unapproved_provider_original",
                "direct_promotion_authorized": False,
            },
        }
        ensure_no_secret_fields(request)
        compiled.append(request)

    sources = {
        f"{episode_relative}/ATOMIC_REFERENCE_PLAN.json": sha256_file(plan_path),
        f"{episode_relative}/codex-image-jobs.json": sha256_file(manifest_path),
        f"{episode_relative}/reference-map.json": sha256_file(map_path),
    }
    profile_sha = sha256_bytes(canonical_bytes(profile))
    index = {
        "schema": INDEX_SCHEMA,
        "episode": str(plan.get("episode")),
        "phase": AUTHORIZED_PHASE,
        "scene_generation_authorized": False,
        "execution_available": False,
        "network_calls_performed": 0,
        "source_contract_sha256": sources,
        "provider_compatibility_validation": {
            "provider_id": profile["provider_id"],
            "profile_sha256": profile_sha,
            "status": "SUPPORTED_EXACT_NO_FALLBACK",
            "reference_reduction_used": False,
            "reference_montage_used": False,
        },
        "requests": [
            {
                "job_id": request["job_id"],
                "path": (
                    f"{episode_relative}/image-jobs/canonical/"
                    f"{request['job_id']}.json"
                ),
                "request_sha256": sha256_bytes(canonical_bytes(request)),
                "input_fingerprint_sha256": request["input_fingerprint_sha256"],
                "idempotency_key": request["idempotency_key"],
            }
            for request in compiled
        ],
    }
    ensure_no_secret_fields(index)
    return compiled, index


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_plan(
    episode: Path,
    requests: list[dict[str, Any]],
    index: dict[str, Any],
) -> None:
    output = episode / "image-jobs" / "canonical"
    expected = {f"{request['job_id']}.json" for request in requests} | {"index.json"}
    if output.exists():
        unexpected = sorted(
            path.name for path in output.iterdir() if path.name not in expected
        )
        if unexpected:
            raise ContractError(
                "canonical output contains unexpected files; refusing destructive cleanup: "
                + ", ".join(unexpected)
            )
    for request in requests:
        atomic_write(output / f"{request['job_id']}.json", canonical_bytes(request))
    atomic_write(output / "index.json", canonical_bytes(index))


def validate_disk(
    episode: Path,
    requests: list[dict[str, Any]],
    index: dict[str, Any],
) -> None:
    output = episode / "image-jobs" / "canonical"
    expected_files = {f"{request['job_id']}.json" for request in requests} | {
        "index.json"
    }
    actual_files = (
        {path.name for path in output.iterdir()} if output.is_dir() else set()
    )
    if actual_files != expected_files:
        raise ContractError(
            f"canonical file set mismatch: expected {sorted(expected_files)}, "
            f"got {sorted(actual_files)}"
        )
    for request in requests:
        path = output / f"{request['job_id']}.json"
        if path.read_bytes() != canonical_bytes(request):
            raise ContractError(f"canonical request differs from source contracts: {path}")
    if (output / "index.json").read_bytes() != canonical_bytes(index):
        raise ContractError("canonical index differs from source contracts")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or validate provider-neutral image generation requests."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "validate"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument(
            "--episode", required=True, help="Episode directory inside the workspace."
        )
        subparser.add_argument(
            "--provider-profile",
            required=True,
            help="Read-only provider capability profile JSON.",
        )
        subparser.add_argument(
            "--workspace",
            default=str(Path(__file__).resolve().parents[1]),
            help="Workspace root used to canonicalize every path.",
        )
        subparser.add_argument(
            "--job-id",
            action="append",
            default=[],
            help="Optional explicit job id; if used, the full authorized set is required.",
        )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        workspace = Path(args.workspace).resolve()
        episode, _ = workspace_relative(args.episode, workspace)
        profile_path, _ = require_file(
            args.provider_profile, workspace, "provider profile"
        )
        requests, index = compile_requests(
            workspace,
            episode,
            load_json(profile_path),
            requested_job_ids=args.job_id or None,
        )
        if args.command == "plan":
            write_plan(episode, requests, index)
            print(
                f"PLANNED {len(requests)} canonical {AUTHORIZED_PHASE} requests; "
                "execution unavailable, network calls=0"
            )
        else:
            validate_disk(episode, requests, index)
            print(
                f"VALID {len(requests)} canonical {AUTHORIZED_PHASE} requests; "
                "scene generation unauthorized"
            )
        return 0
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
