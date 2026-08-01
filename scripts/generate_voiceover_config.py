#!/usr/bin/env python3
"""Generate a draft voiceover config from a storyboard.

Reads storyboard.json and produces a voiceover JSON that groups
consecutive scenes into narration groups.  Each group's speech_text
joins the narration of its scenes so the entire group is synthesized
as one connected audio clip.

The generated config is a starting point — review and adjust:
  - Group boundaries (where the narrator pauses)
  - whole_group_tempo per group
  - profile.voice / rate / pitch / volume
  - cover.title_audio_text and duration_sec
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from story_timeline import compute_scene_timeline


def compute_timeline(storyboard: dict) -> tuple[dict[str, dict], float]:
    return compute_scene_timeline(storyboard)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--storyboard", type=Path, default=Path("storyboard.json")
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Task-owned root; defaults to STORY_VIDEO_WORKSPACE or the current directory",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("voiceover.generated.json")
    )
    parser.add_argument(
        "--group-size", type=int, default=3,
        help="Scenes per narration group (default: 3)",
    )
    parser.add_argument(
        "--single-group", action="store_true",
        help="Put all scenes in one narration group",
    )
    parser.add_argument(
        "--initial-head-sec", type=float, default=0.15,
        help="Offset before the first group starts (default: 0.15)",
    )
    parser.add_argument(
        "--group-gap-sec", type=float, default=0.5,
        help="Gap between narration groups (default: 0.5)",
    )
    parser.add_argument(
        "--chars-per-sec", type=float, default=4.0,
        help="Estimated TTS speed for timeline placement (default: 4.0)",
    )
    parser.add_argument("--voice", type=str, default="zh-CN-XiaoxiaoNeural")
    parser.add_argument("--rate", type=str, default="-8%")
    parser.add_argument("--pitch", type=str, default="-1Hz")
    parser.add_argument("--volume", type=str, default="+0%")
    parser.add_argument("--cover-duration-sec", type=float, default=2.7)
    parser.add_argument("--minimum-final-tail-sec", type=float, default=0.5)
    args = parser.parse_args()

    workspace = (
        args.workspace
        or (Path(os.environ["STORY_VIDEO_WORKSPACE"]) if os.environ.get("STORY_VIDEO_WORKSPACE") else None)
        or Path.cwd()
    ).expanduser().resolve()

    def workspace_path(path: Path) -> Path:
        expanded = path.expanduser()
        return expanded.resolve() if expanded.is_absolute() else (workspace / expanded).resolve()

    args.storyboard = workspace_path(args.storyboard)
    args.output = workspace_path(args.output)

    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))
    scenes = storyboard["scenes"]
    if not scenes:
        raise SystemExit("storyboard has no scenes")

    timeline, total_sec = compute_timeline(storyboard)
    available = total_sec - args.minimum_final_tail_sec

    group_size = len(scenes) if args.single_group else args.group_size
    group_size = max(1, min(group_size, len(scenes)))

    groups: list[dict] = []
    for i in range(0, len(scenes), group_size):
        chunk = scenes[i : i + group_size]
        group_scene_ids = [s["id"] for s in chunk]
        speech_parts = [s.get("narration", s.get("text", "")) for s in chunk]
        speech_text = "".join(speech_parts)
        groups.append({
            "scene_ids": group_scene_ids,
            "speech_text": speech_text,
            "cue_texts": speech_parts,
        })

    cursor = args.initial_head_sec
    group_rows: list[dict] = []
    for idx, group in enumerate(groups):
        estimated_duration = len(group["speech_text"]) / args.chars_per_sec
        group_id = f"G{idx + 1:02d}"
        group_rows.append({
            "id": group_id,
            "scene_ids": group["scene_ids"],
            "start_sec": round(cursor, 3),
            "whole_group_tempo": 1.0,
            "speech_text": group["speech_text"],
            "cue_texts": group["cue_texts"],
        })
        cursor += estimated_duration + args.group_gap_sec

    last_end = cursor - args.group_gap_sec
    if last_end > available:
        print(
            f"WARNING: estimated narration ends at {last_end:.1f}s, "
            f"but only {available:.1f}s is available "
            f"(total={total_sec:.1f}s - tail={args.minimum_final_tail_sec}s). "
            f"Consider smaller --group-size, faster --rate, or higher --chars-per-sec.",
            file=sys.stderr,
        )

    voiceover = {
        "profile": {
            "backend": "edge-tts",
            "voice": args.voice,
            "rate": args.rate,
            "pitch": args.pitch,
            "volume": args.volume,
        },
        "continuity": {
            "minimum_group_gap_sec": 0.35,
            "maximum_group_gap_sec": 0.8,
            "ordinary_pause_limit_sec": 1.25,
            "maximum_global_silence_sec": 2.0,
            "minimum_final_tail_sec": args.minimum_final_tail_sec,
            "maximum_sync_error_sec": 0.6,
            "groups": group_rows,
        },
        "cover": {
            "duration_sec": args.cover_duration_sec,
            "title_audio_text": storyboard["project"]["title"],
        },
        "background_music": {
            "enabled": False,
            "path": "",
            "target_lufs": -28.0,
            "fade_in_sec": 1.2,
            "fade_out_sec": 2.0,
            "ducking": {
                "threshold_db": -32.0,
                "ratio": 8.0,
                "attack_ms": 25.0,
                "release_ms": 450.0,
            },
        },
        "mastering": {
            "integrated_lufs": -16.0,
            "true_peak_dbtp": -1.5,
            "lra": 7.0,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(voiceover, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"Generated {len(group_rows)} narration groups ({len(scenes)} scenes) "
        f"→ {args.output}"
    )
    print(f"  Total storyboard duration: {total_sec:.1f}s")
    print(f"  Estimated narration length: {last_end:.1f}s")
    print()
    print("Review and adjust before running build:audio:")
    print("  - Group boundaries and speech_text")
    print("  - whole_group_tempo per group")
    print("  - profile.voice, rate, pitch, volume")
    print("  - cover.title_audio_text and duration_sec")
    print("  - background_music (leave enabled=false unless the story benefits)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
