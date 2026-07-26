#!/usr/bin/env python3
"""Run isolated episode releases concurrently from a JSON batch manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--tts-jobs", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8:
        parser.error("--jobs must stay within 1..8")
    if not 1 <= args.tts_jobs <= 16:
        parser.error("--tts-jobs must stay within 1..16")

    project = Path(__file__).resolve().parents[1]
    manifest_path = args.manifest.expanduser().resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    episodes = payload.get("episodes", [])
    if not episodes:
        raise SystemExit("batch manifest must contain a non-empty episodes array")

    names = [str(item["episode"]) for item in episodes]
    if len(names) != len(set(names)):
        raise SystemExit("batch episode names must be unique")

    def release(item: dict) -> str:
        command = [
            "python3",
            "scripts/release_story.py",
            "--episode",
            str(item["episode"]),
            "--storyboard",
            str((manifest_path.parent / item["storyboard"]).resolve()),
            "--config",
            str((manifest_path.parent / item["config"]).resolve()),
            "--jobs",
            str(args.tts_jobs),
        ]
        if args.force:
            command.append("--force")
        subprocess.run(command, cwd=project, check=True)
        return str(item["episode"])

    worker_count = min(args.jobs, len(episodes))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(release, item): item for item in episodes}
        for future in as_completed(futures):
            episode = future.result()
            print(f"Completed episode: {episode}")

    print(f"Completed {len(episodes)} episode(s) with {worker_count} worker(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
