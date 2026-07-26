#!/usr/bin/env python3
"""Build and audit one episode from an isolated storyboard."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def run(command: list[str], project: Path) -> None:
    subprocess.run(command, cwd=project, check=True)


def update_progress(path: Path | None, stage: str) -> None:
    if path is None:
        return
    current = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {}
    )
    current["stage"] = stage
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", default=os.environ.get("EPISODE", "default"))
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--progress-file", type=Path)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error("--jobs must stay within 1..16")

    project = Path(__file__).resolve().parents[1]
    storyboard_path = args.storyboard.expanduser().resolve()
    config_path = args.config.expanduser().resolve()
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    visual_mode = storyboard["project"].get("visual_mode", "diary")

    if visual_mode == "ink-comic":
        update_progress(args.progress_file, "subtitles")
        run([
            "python3",
            "scripts/apply_verbatim_subtitles.py",
            "--storyboard",
            str(storyboard_path),
            "--config",
            str(config_path),
        ], project)

    update_progress(args.progress_file, "validation")
    run([
        "node",
        "scripts/validate-storyboard.mjs",
        str(storyboard_path),
    ], project)
    run([
        "node",
        "scripts/audit-motion-storyboard.mjs",
        str(storyboard_path),
    ], project)

    picture = project / "out" / args.episode / "silent.mp4"
    cover = project / "out" / args.episode / "cover.png"
    storyboard_mtime = storyboard_path.stat().st_mtime
    if not args.skip_render:
        render_args = [
            "--episode",
            args.episode,
            "--storyboard",
            str(storyboard_path),
        ]
        if (
            args.force
            or not picture.exists()
            or picture.stat().st_mtime < storyboard_mtime
        ):
            update_progress(args.progress_file, "picture_render")
            run(["npm", "run", "render", "--", *render_args], project)
        if (
            args.force
            or not cover.exists()
            or cover.stat().st_mtime < storyboard_mtime
        ):
            update_progress(args.progress_file, "cover_render")
            run(["npm", "run", "render:cover", "--", *render_args], project)

    update_progress(args.progress_file, "audio_build")
    audio_command = [
        "python3",
        "scripts/build_story_audio.py",
        "--episode",
        args.episode,
        "--storyboard",
        str(storyboard_path),
        "--config",
        str(config_path),
        "--picture",
        str(picture),
        "--cover",
        str(cover),
        "--tts-concurrency",
        str(args.jobs),
    ]
    if args.force:
        audio_command.append("--force")
    run(audio_command, project)

    voiced_dir = project / "out" / args.episode / "voiced"
    release = voiced_dir / "release.mp4"
    cover_config = config.get("cover") or config.get("release", {})
    cover_duration = float(
        cover_config.get(
            "duration_sec",
            cover_config.get("cover_duration_sec", 2.7),
        )
    )
    continuity = config.get("continuity", {})
    audit_command = [
        "python3",
        "scripts/audit_story_delivery.py",
        str(release),
        "--master",
        str(voiced_dir / "narration-master.wav"),
        "--build",
        str(voiced_dir / "build.json"),
        "--sync-map",
        str(voiced_dir / "sync-map.json"),
        "--cover-duration",
        str(cover_duration),
        "--expect-width",
        str(storyboard["project"]["width"]),
        "--expect-height",
        str(storyboard["project"]["height"]),
        "--expect-fps",
        str(storyboard["project"]["fps"]),
        "--ordinary-pause-limit",
        str(continuity.get("ordinary_pause_limit_sec", 1.25)),
        "--max-group-gap",
        str(continuity.get("maximum_group_gap_sec", 0.8)),
        "--max-global-silence",
        str(continuity.get("maximum_global_silence_sec", 2.0)),
        "--max-sync-error",
        str(continuity.get("maximum_sync_error_sec", 0.6)),
        "--report",
        str(voiced_dir / "audit.json"),
    ]
    update_progress(args.progress_file, "delivery_audit")
    run(audit_command, project)
    update_progress(args.progress_file, "complete")
    print(f"Release ready: {release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
