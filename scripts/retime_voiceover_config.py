#!/usr/bin/env python3
"""Fit continuous TTS groups to storyboard scene starts without sentence cuts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from dataclasses import dataclass
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


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


@dataclass
class GroupShape:
    group_id: str
    targets: list[float]
    relative_cues: list[float]
    natural_duration: float


@dataclass
class Node:
    rows: list[dict]
    end: float
    max_error: float
    sum_squared_error: float
    tempo_cost: float

    @property
    def score(self) -> tuple[float, float, float]:
        return (
            round(self.max_error, 9),
            round(self.sum_squared_error, 9),
            round(self.tempo_cost, 9),
        )


def storyboard_timeline(storyboard: dict) -> tuple[dict[str, float], float]:
    starts: dict[str, float] = {}
    cursor = 0.0
    for scene in storyboard["scenes"]:
        starts[str(scene["id"])] = cursor
        cursor += float(scene["duration_sec"])
    return starts, cursor


def group_shapes(
    episode: str,
    workspace: Path,
    config: dict,
    scene_starts: dict[str, float],
    audio,
) -> list[GroupShape]:
    raw_dir = workspace / ".work" / episode / "raw-groups"
    shapes = []
    for group in config["continuity"]["groups"]:
        group_id = str(group["id"])
        media = raw_dir / f"{group_id}.mp3"
        vtt = raw_dir / f"{group_id}.vtt"
        if not media.is_file() or not vtt.is_file():
            raise FileNotFoundError(
                f"Missing prepared group {group_id}; run prepare_voice_groups.py first"
            )
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
        shapes.append(
            GroupShape(
                group_id=group_id,
                targets=[scene_starts[scene_id] for scene_id in scene_ids],
                relative_cues=[
                    float(cue["start_sec"]) - origin for cue in cues
                ],
                natural_duration=outer_end - origin,
            )
        )
    return shapes


def candidate_row(shape: GroupShape, tempo: float, start: float) -> tuple[dict, list[float]]:
    actual = [
        start + relative / tempo for relative in shape.relative_cues
    ]
    errors = [
        value - target for value, target in zip(actual, shape.targets)
    ]
    return (
        {
            "id": shape.group_id,
            "start_sec": start,
            "whole_group_tempo": tempo,
            "speech_sec": shape.natural_duration / tempo,
            "end_sec": start + shape.natural_duration / tempo,
            "errors": errors,
        },
        errors,
    )


def optimal_start(shape: GroupShape, tempo: float) -> float:
    offsets = [
        target - relative / tempo
        for target, relative in zip(shape.targets, shape.relative_cues)
    ]
    return (min(offsets) + max(offsets)) / 2


def fit(
    shapes: list[GroupShape],
    continuity: dict,
    total: float,
    beam_width: int,
) -> Node:
    tempos = [0.95 + index * 0.0005 for index in range(201)]
    minimum_gap = float(continuity.get("minimum_group_gap_sec", 0.35))
    maximum_gap = float(continuity.get("maximum_group_gap_sec", 0.8))
    final_tail = float(continuity.get("minimum_final_tail_sec", 0.5))
    beam: list[Node] = []

    first = shapes[0]
    for tempo in tempos:
        start = clamp(optimal_start(first, tempo), 0.0, 0.8)
        row, errors = candidate_row(first, tempo, start)
        beam.append(
            Node(
                rows=[row],
                end=row["end_sec"],
                max_error=max(abs(value) for value in errors),
                sum_squared_error=sum(value * value for value in errors),
                tempo_cost=(tempo - 1.0) ** 2,
            )
        )

    for shape in shapes[1:]:
        next_nodes: dict[tuple[int, int], Node] = {}
        for previous in beam:
            low = previous.end + minimum_gap
            high = previous.end + maximum_gap
            for tempo_index, tempo in enumerate(tempos):
                start = clamp(optimal_start(shape, tempo), low, high)
                row, errors = candidate_row(shape, tempo, start)
                node = Node(
                    rows=[*previous.rows, row],
                    end=row["end_sec"],
                    max_error=max(
                        previous.max_error,
                        max(abs(value) for value in errors),
                    ),
                    sum_squared_error=(
                        previous.sum_squared_error
                        + sum(value * value for value in errors)
                    ),
                    tempo_cost=previous.tempo_cost + (tempo - 1.0) ** 2,
                )
                key = (tempo_index, round(node.end * 20))
                incumbent = next_nodes.get(key)
                if incumbent is None or node.score < incumbent.score:
                    next_nodes[key] = node
        beam = sorted(next_nodes.values(), key=lambda item: item.score)[:beam_width]

    eligible = [node for node in beam if node.end <= total - final_tail]
    if not eligible:
        raise RuntimeError(
            f"No fit leaves the required {final_tail:.3f}s final tail"
        )
    return min(eligible, key=lambda item: item.score)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--beam-width", type=int, default=2000)
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
    scene_starts, total = storyboard_timeline(storyboard)
    shapes = group_shapes(
        args.episode, workspace, config, scene_starts, audio
    )
    result = fit(
        shapes,
        config["continuity"],
        total,
        args.beam_width,
    )

    output_rows = []
    for group, row in zip(config["continuity"]["groups"], result.rows):
        output_rows.append(
            {
                "id": row["id"],
                "start_sec": round(row["start_sec"], 3),
                "whole_group_tempo": round(row["whole_group_tempo"], 6),
                "end_sec": round(row["end_sec"], 3),
                "max_scene_start_error_sec": round(
                    max(abs(value) for value in row["errors"]), 3
                ),
                "scene_start_errors_sec": [
                    round(value, 3) for value in row["errors"]
                ],
            }
        )
        if args.apply:
            group["start_sec"] = round(row["start_sec"], 3)
            group["whole_group_tempo"] = round(
                row["whole_group_tempo"], 6
            )

    if args.apply:
        args.config.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "episode": args.episode,
                "applied": args.apply,
                "maximum_scene_start_error_sec": round(result.max_error, 3),
                "rms_scene_start_error_sec": round(
                    math.sqrt(
                        result.sum_squared_error
                        / sum(len(shape.targets) for shape in shapes)
                    ),
                    3,
                ),
                "final_tail_sec": round(total - result.end, 3),
                "groups": output_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
