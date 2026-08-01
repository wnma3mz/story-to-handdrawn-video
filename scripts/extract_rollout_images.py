#!/usr/bin/env python3
"""Recover Codex Image PNG results from a rollout into a Codex manifest.

Use this only when the normal generated-image directory is unavailable. The
latest matching image-generation result wins, so a later correction replaces
an earlier rejected attempt when ``--force`` is supplied.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path


NARRATIVE_SENTENCE = re.compile(
    r'Narrative sentence to illustrate:\s*["“](?P<sentence>.+?)["”]\s*(?:\n|$)',
    re.IGNORECASE,
)
EXPLICIT_JOB = re.compile(
    r"(?:Episode\s+\d+.*?\bscene|\bscene|\bjob(?:\s+id)?)\s*[:#-]?\s*"
    r"(?P<id>[A-Za-z0-9][A-Za-z0-9._-]*)",
    re.IGNORECASE | re.DOTALL,
)


def normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).translate(
        str.maketrans("", "", '"“”‘’')
    )


def rollout_image_calls(rollout: Path) -> list[dict]:
    calls: list[dict] = []
    with rollout.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            payload = row.get("payload", row)
            if payload.get("type") != "image_generation_call":
                continue
            result = payload.get("result", "")
            if isinstance(result, str) and result.startswith("data:image/png;base64,"):
                result = result.split(",", 1)[1]
            calls.append(
                {
                    "line_number": line_number,
                    "prompt": str(
                        payload.get("revised_prompt")
                        or payload.get("prompt")
                        or ""
                    ),
                    "result": result,
                }
            )
    return calls


def match_job(prompt: str, jobs: dict[str, dict]) -> str | None:
    explicit = EXPLICIT_JOB.search(prompt)
    if explicit:
        candidate = explicit.group("id")
        if candidate in jobs:
            return candidate

    compact_prompt = normalized(prompt)
    sentence_matches: list[str] = []
    for job_id, job in jobs.items():
        match = NARRATIVE_SENTENCE.search(str(job.get("prompt", "")))
        if match and normalized(match.group("sentence")) in compact_prompt:
            sentence_matches.append(job_id)
    return sentence_matches[0] if len(sentence_matches) == 1 else None


def extract_images(
    rollout: Path,
    manifest_path: Path,
    requested_jobs: list[str] | None = None,
    *,
    force: bool = False,
) -> list[dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("generator") != "codex-image2":
        raise ValueError("manifest.generator must be codex-image2")
    all_jobs = {str(job["id"]): job for job in manifest.get("jobs", [])}
    if requested_jobs:
        unknown = sorted(set(requested_jobs) - all_jobs.keys())
        if unknown:
            raise ValueError(f"unknown manifest jobs: {', '.join(unknown)}")
        jobs = {job_id: all_jobs[job_id] for job_id in requested_jobs}
    else:
        jobs = {
            job_id: job
            for job_id, job in all_jobs.items()
            if str(job.get("role", "scene")) == "scene"
        }
    if not jobs:
        raise ValueError("no selected scene jobs in manifest")

    latest: dict[str, dict] = {}
    for call in rollout_image_calls(rollout):
        job_id = match_job(call["prompt"], jobs)
        if job_id is not None:
            latest[job_id] = call
    missing = sorted(set(jobs) - latest.keys())
    if missing:
        raise RuntimeError(f"rollout has no image result for: {', '.join(missing)}")

    extracted: list[dict] = []
    for job_id, job in jobs.items():
        output = Path(str(job["output_master"])).expanduser()
        if not output.is_absolute():
            output = (manifest_path.parent / output).resolve()
        if output.exists() and not force:
            raise FileExistsError(f"refusing to overwrite {output}; use --force")
        encoded = latest[job_id]["result"]
        if not isinstance(encoded, str):
            raise ValueError(f"{job_id}: rollout result is not base64 text")
        png = base64.b64decode(encoded, validate=True)
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"{job_id}: decoded result is not a PNG")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(png)
        prompt_output = output.with_suffix(".imagegen-prompt.txt")
        prompt_output.write_text(
            latest[job_id]["prompt"].rstrip() + "\n",
            encoding="utf-8",
        )
        extracted.append(
            {
                "id": job_id,
                "rollout_line": latest[job_id]["line_number"],
                "output": str(output),
                "bytes": len(png),
            }
        )
    return extracted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--jobs",
        nargs="+",
        help="Manifest job IDs; defaults to every role=scene job",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    rows = extract_images(
        args.rollout.expanduser().resolve(),
        args.manifest.expanduser().resolve(),
        args.jobs,
        force=args.force,
    )
    print(json.dumps({"status": "PASS", "images": rows}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
