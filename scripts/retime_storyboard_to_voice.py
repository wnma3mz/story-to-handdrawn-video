#!/usr/bin/env python3
"""Make scene durations follow prepared continuous-group Edge TTS cues."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_story_audio.py"


def load_audio_module():
    spec = importlib.util.spec_from_file_location("build_story_audio", BUILD_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {BUILD_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def recompute_visual_intervals(storyboard: dict) -> None:
    scenes = storyboard["scenes"]
    cursor = 0
    while cursor < len(scenes):
        interval = str(
            scenes[cursor].get("visual_interval_id") or scenes[cursor]["id"]
        )
        end = cursor + 1
        while end < len(scenes):
            candidate = str(
                scenes[end].get("visual_interval_id") or scenes[end]["id"]
            )
            if candidate != interval:
                break
            end += 1
        group = scenes[cursor:end]
        total = sum(float(scene["duration_sec"]) for scene in group)
        elapsed = 0.0
        for index, scene in enumerate(group):
            start_progress = elapsed / total
            elapsed += float(scene["duration_sec"])
            end_progress = elapsed / total
            scene["visual_interval_start"] = index == 0
            scene["visual_interval_progress_start"] = round(
                start_progress, 6
            )
            scene["visual_interval_progress_end"] = round(end_progress, 6)
        cursor = end


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--initial-head-sec", type=float, default=0.15)
    parser.add_argument("--group-gap-sec", type=float, default=0.5)
    parser.add_argument("--final-tail-sec", type=float, default=0.8)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    workspace = (
        args.workspace
        or (Path(os.environ["STORY_VIDEO_WORKSPACE"]) if os.environ.get("STORY_VIDEO_WORKSPACE") else None)
        or Path.cwd()
    ).expanduser().resolve()
    for name in ("config", "storyboard"):
        path = getattr(args, name).expanduser()
        setattr(
            args,
            name,
            path.resolve() if path.is_absolute() else (workspace / path).resolve(),
        )

    audio = load_audio_module()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))
    fps = int(storyboard["project"]["fps"])
    scenes = storyboard["scenes"]
    scenes_by_id = {str(scene["id"]): scene for scene in scenes}
    raw_dir = workspace / ".work" / args.episode / "raw-groups"

    first_start_frame = max(0, round(args.initial_head_sec * fps))
    next_group_start_frame = first_start_frame
    scene_start_frames: dict[str, int] = {str(scenes[0]["id"]): 0}
    group_rows = []

    for group_index, group in enumerate(config["continuity"]["groups"]):
        group_id = str(group["id"])
        media = raw_dir / f"{group_id}.mp3"
        vtt = raw_dir / f"{group_id}.vtt"
        cues = audio.parse_vtt(vtt)
        scene_ids = [str(value) for value in group["scene_ids"]]
        if len(cues) != len(scene_ids):
            raise RuntimeError(
                f"{group_id}: {len(cues)} cues for {len(scene_ids)} scenes"
            )
        origin = float(cues[0]["start_sec"])
        outer_end = min(
            audio.media_duration(media),
            float(cues[-1]["end_sec"]) + 0.03,
        )
        speech_duration = outer_end - origin
        group_start_frame = next_group_start_frame
        group_start_sec = group_start_frame / fps

        for cue_index, (scene_id, cue) in enumerate(zip(scene_ids, cues)):
            if group_index == 0 and cue_index == 0:
                scene_start_frames[scene_id] = 0
            else:
                cue_relative = float(cue["start_sec"]) - origin
                scene_start_frames[scene_id] = round(
                    (group_start_sec + cue_relative) * fps
                )

        group_audio_end = group_start_sec + speech_duration
        if group_index < len(config["continuity"]["groups"]) - 1:
            next_group_start_frame = math.ceil(
                (group_audio_end + args.group_gap_sec) * fps
            )
            group_visual_end_frame = next_group_start_frame
        else:
            group_visual_end_frame = math.ceil(
                (group_audio_end + args.final_tail_sec) * fps
            )

        group["start_sec"] = round(group_start_sec, 6)
        group["whole_group_tempo"] = 1.0
        group_rows.append(
            {
                "id": group_id,
                "start_sec": round(group_start_sec, 3),
                "speech_end_sec": round(group_audio_end, 3),
                "visual_end_sec": round(group_visual_end_frame / fps, 3),
                "gap_or_tail_sec": round(
                    group_visual_end_frame / fps - group_audio_end, 3
                ),
            }
        )

    total_frames = group_visual_end_frame
    for index, scene in enumerate(scenes):
        scene_id = str(scene["id"])
        start_frame = scene_start_frames[scene_id]
        if index + 1 < len(scenes):
            end_frame = scene_start_frames[str(scenes[index + 1]["id"])]
        else:
            end_frame = total_frames
        if end_frame <= start_frame:
            raise RuntimeError(
                f"{scene_id}: non-positive retimed duration "
                f"({start_frame}..{end_frame})"
            )
        scene["duration_sec"] = round((end_frame - start_frame) / fps, 6)

    recompute_visual_intervals(storyboard)

    duration_rows = [
        {
            "id": str(scene["id"]),
            "duration_sec": round(float(scene["duration_sec"]), 3),
        }
        for scene in scenes
    ]
    if args.apply:
        args.storyboard.write_text(
            json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        args.config.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "episode": args.episode,
                "applied": args.apply,
                "fps": fps,
                "total_frames": total_frames,
                "total_sec": round(total_frames / fps, 3),
                "groups": group_rows,
                "scenes": duration_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
