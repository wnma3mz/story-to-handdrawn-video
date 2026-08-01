#!/usr/bin/env python3
"""Rebuild an episode motion TSV from its visual plan and image-job manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write an exact four-column motion timeline using the visual plan as "
            "the timing/motion authority and the manifest as the image authority."
        )
    )
    parser.add_argument("episode_dir", type=Path)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Workspace root used to resolve relative episode and image paths.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output TSV; defaults to <episode_dir>/motion-timeline.tsv.",
    )
    return parser.parse_args()


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    workspace_root = args.workspace.expanduser().resolve()
    episode_input = args.episode_dir.expanduser()
    episode_dir = (
        episode_input if episode_input.is_absolute() else workspace_root / episode_input
    ).resolve()
    visual_plan_path = episode_dir / "visual-plan.json"
    manifest_path = episode_dir / "codex-image-jobs.json"
    if args.output is None:
        output_path = episode_dir / "motion-timeline.tsv"
    else:
        output_input = args.output.expanduser()
        output_path = (
            output_input if output_input.is_absolute() else workspace_root / output_input
        ).resolve()

    visual_plan = load_json(visual_plan_path)
    manifest = load_json(manifest_path)
    if not isinstance(visual_plan, dict):
        raise SystemExit(f"Visual plan must be an object: {visual_plan_path}")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("jobs"), list):
        raise SystemExit(f"Manifest must contain jobs: {manifest_path}")

    scene_jobs = {
        str(job.get("id", "")).zfill(2): job
        for job in manifest["jobs"]
        if isinstance(job, dict) and job.get("role") == "scene"
    }
    scene_ids = list(visual_plan)
    if list(scene_jobs) != scene_ids:
        raise SystemExit(
            "Visual-plan and scene-job IDs/order differ: "
            f"{scene_ids!r} != {list(scene_jobs)!r}"
        )

    rows = ["# scene\tduration\timage\tmotion"]
    for scene_id in scene_ids:
        scene = visual_plan[scene_id]
        job = scene_jobs[scene_id]
        if not isinstance(scene, dict):
            raise SystemExit(f"{scene_id}: visual-plan entry must be an object")
        duration = scene.get("duration_sec")
        motion = scene.get("motion")
        output_master = job.get("output_master")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise SystemExit(f"{scene_id}: invalid duration_sec {duration!r}")
        if not isinstance(motion, str) or not motion:
            raise SystemExit(f"{scene_id}: missing motion")
        if not isinstance(output_master, str) or not output_master:
            raise SystemExit(f"{scene_id}: missing output_master")

        image_input = Path(output_master).expanduser()
        image_path = (
            image_input if image_input.is_absolute() else workspace_root / image_input
        ).resolve()
        try:
            image = image_path.relative_to(workspace_root).as_posix()
        except ValueError:
            image = image_path.as_posix()
        rows.append(f"{scene_id}\t{duration}\t{image}\t{motion}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"WROTE {output_path} scenes={len(scene_ids)}")


if __name__ == "__main__":
    main()
