#!/usr/bin/env python3
"""Split visual scenes into short verbatim subtitle machine scenes.

Every fragment keeps the source illustration, motion and focus. The generated
``visual_interval_*`` fields make the camera path continue across subtitle
changes instead of restarting at every cue.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path


PUNCTUATION = re.compile(r"[\s，。；：！？、,.!?;:“”‘’\"'（）()《》〈〉—…·]")
ALLOWED_GRADES = {"monochrome", "warm_bronze", "snow_cinnabar"}


def lexical_text(value: str) -> str:
    return PUNCTUATION.sub("", value)


def fragment_id(source_id: str, index: int) -> str:
    if index >= 26:
        raise ValueError(f"{source_id}: at most 26 subtitle fragments are supported")
    return f"{source_id}{chr(ord('a') + index)}"


def allocate_frames(total_frames: int, weights: list[int]) -> list[int]:
    if total_frames < len(weights):
        raise ValueError("visual interval has fewer frames than subtitle fragments")
    total_weight = sum(weights)
    raw = [total_frames * weight / total_weight for weight in weights]
    frames = [max(1, int(value)) for value in raw]
    difference = total_frames - sum(frames)
    order = sorted(
        range(len(raw)),
        key=lambda index: raw[index] - int(raw[index]),
        reverse=difference > 0,
    )
    cursor = 0
    while difference != 0:
        index = order[cursor % len(order)]
        if difference > 0:
            frames[index] += 1
            difference -= 1
        elif frames[index] > 1:
            frames[index] -= 1
            difference += 1
        cursor += 1
    return frames


def load_fragments(plan: dict, source_id: str) -> list[str]:
    raw = plan.get("scenes", {}).get(source_id)
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{source_id}: cue plan requires a non-empty fragment array")
    fragments = [str(value).strip() for value in raw if str(value).strip()]
    if len(fragments) != len(raw):
        raise ValueError(f"{source_id}: subtitle fragments must be non-empty strings")
    return fragments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--cue-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--color-grade", choices=sorted(ALLOWED_GRADES))
    args = parser.parse_args()

    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))
    plan = json.loads(args.cue_plan.read_text(encoding="utf-8"))
    if plan.get("version") != 1 or not isinstance(plan.get("scenes"), dict):
        raise ValueError("cue plan must use version=1 and a scenes object")

    source_scenes = storyboard.get("scenes", [])
    source_ids = [str(scene.get("id")) for scene in source_scenes]
    planned_ids = [str(value) for value in plan["scenes"]]
    if set(source_ids) != set(planned_ids):
        missing = sorted(set(source_ids) - set(planned_ids))
        unknown = sorted(set(planned_ids) - set(source_ids))
        raise ValueError(
            f"cue plan scene mismatch; missing={missing or 'none'} "
            f"unknown={unknown or 'none'}"
        )

    fps = int(storyboard["project"]["fps"])
    output_scenes: list[dict] = []
    for source in source_scenes:
        source_id = str(source["id"])
        fragments = load_fragments(plan, source_id)
        if lexical_text("".join(fragments)) != lexical_text(
            str(source.get("narration", ""))
        ):
            raise ValueError(
                f"{source_id}: fragments must preserve every spoken character; "
                "only whitespace and punctuation may change"
            )

        total_frames = max(1, round(float(source["duration_sec"]) * fps))
        weights = [max(1, len(lexical_text(fragment))) for fragment in fragments]
        fragment_frames = allocate_frames(total_frames, weights)
        interval_id = str(source.get("visual_interval_id") or source_id)
        elapsed_frames = 0

        for index, (fragment, frames) in enumerate(
            zip(fragments, fragment_frames)
        ):
            scene = copy.deepcopy(source)
            start_progress = elapsed_frames / total_frames
            elapsed_frames += frames
            end_progress = elapsed_frames / total_frames
            scene["id"] = fragment_id(source_id, index)
            scene["duration_sec"] = round(frames / fps, 6)
            if index == 0 and source.get("text"):
                scene["summary_text"] = str(source["text"])
            else:
                scene.pop("summary_text", None)
            scene["text"] = fragment
            scene["narration"] = fragment
            scene["visual_interval_id"] = interval_id
            scene["visual_interval_start"] = index == 0
            scene["visual_interval_progress_start"] = round(start_progress, 6)
            scene["visual_interval_progress_end"] = round(end_progress, 6)
            if args.color_grade:
                scene["color_grade"] = args.color_grade
            if index < len(fragments) - 1:
                scene["transition_to_next"] = "cut"
            output_scenes.append(scene)

    storyboard["scenes"] = output_scenes
    storyboard.setdefault("project", {})["subtitle_contract"] = "verbatim_tts"
    if args.color_grade:
        storyboard["project"]["color_grade"] = args.color_grade

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "source_scenes": len(source_scenes),
                "subtitle_scenes": len(output_scenes),
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
