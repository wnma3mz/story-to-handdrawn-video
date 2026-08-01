#!/usr/bin/env python3
"""Submit, inspect, and resume detached story release jobs."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("STORY_VIDEO_WORKSPACE", PROJECT)).expanduser().resolve()
JOB_ROOT = WORKSPACE / ".work" / "jobs"
JOB_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def configure_workspace(value: Path | None) -> None:
    global WORKSPACE, JOB_ROOT
    WORKSPACE = (value or WORKSPACE).expanduser().resolve()
    JOB_ROOT = WORKSPACE / ".work" / "jobs"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_path(job_id: str) -> Path:
    if not JOB_ID.fullmatch(job_id):
        raise SystemExit("job id may contain only ASCII letters, numbers, dots, underscores, and hyphens")
    return JOB_ROOT / job_id / "state.json"


def read_state(job_id: str) -> dict:
    path = state_path(job_id)
    if not path.exists():
        raise SystemExit(f"unknown job: {job_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(job_id: str, state: dict) -> None:
    path = state_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def patch_state(job_id: str, **updates: object) -> dict:
    state = read_state(job_id)
    state.update(updates)
    state["updated_at"] = now()
    write_state(job_id, state)
    return state


def launch(job_id: str) -> dict:
    path = state_path(job_id)
    log_path = path.parent / "job.log"
    patch_state(job_id, status="queued", stage="queued")
    with log_path.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "run",
                job_id,
                "--workspace",
                str(WORKSPACE),
            ],
            cwd=PROJECT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return patch_state(job_id, pid=process.pid, log=str(log_path))


def submit(args: argparse.Namespace) -> int:
    episode = args.episode
    if not re.fullmatch(r"[\w.-]+", episode) or episode in {".", ".."}:
        raise SystemExit(
            "--episode may contain only letters, numbers, dots, underscores, and hyphens"
        )
    if JOB_ROOT.exists():
        for existing_path in JOB_ROOT.glob("*/state.json"):
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
            if (
                existing.get("status") in {"queued", "running"}
                and existing.get("spec", {}).get("episode") == episode
            ):
                raise SystemExit(
                    f"episode already has an active job: {existing.get('job_id')}"
                )
    base_id = re.sub(r"[^A-Za-z0-9._-]+", "-", episode).strip("-") or "story"
    job_id = args.job_id or f"{base_id}-{uuid.uuid4().hex[:8]}"
    path = state_path(job_id)
    if path.exists():
        raise SystemExit(f"job already exists: {job_id}")
    if not 1 <= args.jobs <= 16:
        raise SystemExit("--jobs must stay within 1..16")
    storyboard = args.storyboard.expanduser()
    storyboard = storyboard.resolve() if storyboard.is_absolute() else (WORKSPACE / storyboard).resolve()
    config = args.config.expanduser()
    config = config.resolve() if config.is_absolute() else (WORKSPACE / config).resolve()
    if not storyboard.is_file():
        raise SystemExit(f"missing storyboard: {storyboard}")
    if not config.is_file():
        raise SystemExit(f"missing config: {config}")
    state = {
        "job_id": job_id,
        "status": "created",
        "stage": "queued",
        "created_at": now(),
        "updated_at": now(),
        "attempts": 0,
        "spec": {
            "episode": episode,
            "workspace": str(WORKSPACE),
            "storyboard": str(storyboard),
            "config": str(config),
            "jobs": args.jobs,
            "force": args.force,
        },
    }
    write_state(job_id, state)
    launched = launch(job_id)
    print(json.dumps(launched, ensure_ascii=False, indent=2))
    return 0


def run_job(job_id: str) -> int:
    state = read_state(job_id)
    spec = state["spec"]
    attempts = int(state.get("attempts", 0)) + 1
    patch_state(
        job_id,
        status="running",
        stage="starting",
        attempts=attempts,
        started_at=now(),
        error=None,
    )
    command = [
        sys.executable,
        "scripts/release_story.py",
        "--episode",
        spec["episode"],
        "--workspace",
        spec.get("workspace", str(WORKSPACE)),
        "--storyboard",
        spec["storyboard"],
        "--config",
        spec["config"],
        "--jobs",
        str(spec["jobs"]),
        "--progress-file",
        str(state_path(job_id)),
    ]
    if spec.get("force"):
        command.append("--force")
    try:
        result = subprocess.run(command, cwd=PROJECT, check=False)
        if result.returncode != 0:
            patch_state(
                job_id,
                status="failed",
                return_code=result.returncode,
                finished_at=now(),
                error=f"release command exited with {result.returncode}",
            )
            return result.returncode
        patch_state(
            job_id,
            status="completed",
            stage="complete",
            return_code=0,
            finished_at=now(),
        )
        return 0
    except Exception as error:
        patch_state(
            job_id,
            status="failed",
            finished_at=now(),
            error=f"{type(error).__name__}: {error}",
        )
        raise


def resume(job_id: str) -> int:
    state = read_state(job_id)
    if state["status"] in {"queued", "running"}:
        raise SystemExit(f"job is already active: {job_id}")
    launched = launch(job_id)
    print(json.dumps(launched, ensure_ascii=False, indent=2))
    return 0


def show_status(job_id: str) -> int:
    print(json.dumps(read_state(job_id), ensure_ascii=False, indent=2))
    return 0


def show_log(job_id: str, lines: int) -> int:
    log_path = state_path(job_id).parent / "job.log"
    if not log_path.exists():
        raise SystemExit(f"job has no log yet: {job_id}")
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(content[-lines:]))
    return 0


def list_jobs() -> int:
    rows = []
    if JOB_ROOT.exists():
        for path in sorted(JOB_ROOT.glob("*/state.json")):
            state = json.loads(path.read_text(encoding="utf-8"))
            rows.append({
                "job_id": state["job_id"],
                "status": state["status"],
                "stage": state.get("stage"),
                "updated_at": state.get("updated_at"),
            })
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    submit_parser = commands.add_parser("submit")
    submit_parser.add_argument("--episode", required=True)
    submit_parser.add_argument("--workspace", type=Path)
    submit_parser.add_argument("--storyboard", type=Path, required=True)
    submit_parser.add_argument("--config", type=Path, required=True)
    submit_parser.add_argument("--jobs", type=int, default=4)
    submit_parser.add_argument("--job-id")
    submit_parser.add_argument("--force", action="store_true")

    run_parser = commands.add_parser("run")
    run_parser.add_argument("job_id")
    run_parser.add_argument("--workspace", type=Path)
    status_parser = commands.add_parser("status")
    status_parser.add_argument("job_id")
    status_parser.add_argument("--workspace", type=Path)
    resume_parser = commands.add_parser("resume")
    resume_parser.add_argument("job_id")
    resume_parser.add_argument("--workspace", type=Path)
    log_parser = commands.add_parser("log")
    log_parser.add_argument("job_id")
    log_parser.add_argument("--lines", type=int, default=80)
    log_parser.add_argument("--workspace", type=Path)
    list_parser = commands.add_parser("list")
    list_parser.add_argument("--workspace", type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    configure_workspace(getattr(args, "workspace", None))
    if args.command == "submit":
        return submit(args)
    if args.command == "run":
        return run_job(args.job_id)
    if args.command == "status":
        return show_status(args.job_id)
    if args.command == "resume":
        return resume(args.job_id)
    if args.command == "log":
        return show_log(args.job_id, args.lines)
    if args.command == "list":
        return list_jobs()
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
