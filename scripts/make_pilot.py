#!/usr/bin/env python3
"""Create an isolated prefix pilot from a storyboard, manifest, and voiceover."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path

from story_timeline import compute_scene_timeline


SENTENCE = re.compile(r"[^。！？!?]+(?:[。！？!?]+|$)")


def sentence_cues(text: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in SENTENCE.finditer(text)
        if match.group(0).strip()
    ]


def selected_prefix(storyboard: dict, scene_count: int | None, target_sec: float) -> list[dict]:
    scenes = storyboard["scenes"]
    if scene_count is not None:
        if not 1 <= scene_count <= len(scenes):
            raise ValueError("scene_count is outside the storyboard scene range")
        return scenes[:scene_count]
    if target_sec <= 0:
        raise ValueError("target_sec must be positive")
    timeline, _ = compute_scene_timeline(storyboard)
    selected: list[dict] = []
    for scene in scenes:
        selected.append(scene)
        if float(timeline[str(scene["id"])]["end_sec"]) >= target_sec:
            break
    return selected


def truncate_voiceover(voiceover: dict, selected_ids: set[str]) -> dict:
    result = copy.deepcopy(voiceover)
    groups: list[dict] = []
    for group in result.get("continuity", {}).get("groups", []):
        source_ids = [str(value) for value in group.get("scene_ids", [])]
        cue_texts = [str(value) for value in group.get("cue_texts", [])]
        if not cue_texts:
            cue_texts = sentence_cues(str(group.get("speech_text", "")))
        if len(source_ids) != len(cue_texts):
            raise ValueError(
                f"{group.get('id', '(unnamed group)')}: "
                f"{len(cue_texts)} cues for {len(source_ids)} scene ids"
            )
        selected = [
            (scene_id, cue)
            for scene_id, cue in zip(source_ids, cue_texts)
            if scene_id in selected_ids
        ]
        if not selected:
            continue
        group["scene_ids"] = [scene_id for scene_id, _ in selected]
        group["cue_texts"] = [cue for _, cue in selected]
        group["speech_text"] = "".join(group["cue_texts"])
        if len(selected) < len(source_ids):
            group["pilot_truncated_source_group"] = True
        groups.append(group)
    result.setdefault("continuity", {})["groups"] = groups
    return result


def pilot_manifest(manifest: dict, selected_ids: set[str], storyboard_path: Path) -> dict:
    result = copy.deepcopy(manifest)
    jobs = {str(job["id"]): job for job in result.get("jobs", [])}
    included = {job_id for job_id in selected_ids if job_id in jobs}
    pending = list(included)
    while pending:
        job_id = pending.pop()
        for dependency in jobs[job_id].get("depends_on", []):
            dependency_id = str(dependency)
            if dependency_id not in jobs:
                raise ValueError(f"{job_id}: missing dependency job {dependency_id}")
            if dependency_id not in included:
                included.add(dependency_id)
                pending.append(dependency_id)
    result["jobs"] = [
        job for job in result.get("jobs", []) if str(job["id"]) in included
    ]
    result["storyboard"] = str(storyboard_path.resolve())
    return result


def build_pilot(
    storyboard_path: Path,
    manifest_path: Path,
    output_dir: Path,
    *,
    voiceover_path: Path | None = None,
    scene_count: int | None = None,
    target_sec: float = 60.0,
    title_suffix: str = "｜代表性样片",
    force: bool = False,
) -> dict:
    outputs = [output_dir / "storyboard.json", output_dir / "codex-image-jobs.json"]
    if voiceover_path is not None:
        outputs.append(output_dir / "voiceover.json")
    existing = [path for path in outputs if path.exists()]
    if existing and not force:
        raise FileExistsError(
            "refusing to overwrite pilot files: " + ", ".join(map(str, existing))
        )

    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = selected_prefix(storyboard, scene_count, target_sec)
    selected_ids = {str(scene["id"]) for scene in selected}
    pilot_storyboard = copy.deepcopy(storyboard)
    pilot_storyboard["scenes"] = copy.deepcopy(selected)
    if title_suffix and not str(pilot_storyboard["project"]["title"]).endswith(title_suffix):
        pilot_storyboard["project"]["title"] += title_suffix
    _, duration = compute_scene_timeline(pilot_storyboard)
    pilot_storyboard["project"]["pilot"] = {
        "source_storyboard": str(storyboard_path.resolve()),
        "scene_count": len(selected),
        "duration_sec": round(duration, 3),
        "purpose": "composition, continuity, subtitle-safe framing, motion, and listening approval",
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    pilot_storyboard_path = output_dir / "storyboard.json"
    values: list[tuple[Path, dict]] = [
        (pilot_storyboard_path, pilot_storyboard),
        (
            output_dir / "codex-image-jobs.json",
            pilot_manifest(manifest, selected_ids, pilot_storyboard_path),
        ),
    ]
    if voiceover_path is not None:
        voiceover = json.loads(voiceover_path.read_text(encoding="utf-8"))
        values.append(
            (output_dir / "voiceover.json", truncate_voiceover(voiceover, selected_ids))
        )
    for output, value in values:
        output.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return {
        "status": "PASS",
        "output_dir": str(output_dir.resolve()),
        "scene_count": len(selected),
        "duration_sec": round(duration, 3),
        "voiceover_included": voiceover_path is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--voiceover", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--scene-count", type=int)
    selection.add_argument("--target-sec", type=float, default=60.0)
    parser.add_argument("--title-suffix", default="｜代表性样片")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report = build_pilot(
        args.storyboard.expanduser().resolve(),
        args.manifest.expanduser().resolve(),
        args.output_dir.expanduser().resolve(),
        voiceover_path=args.voiceover.expanduser().resolve() if args.voiceover else None,
        scene_count=args.scene_count,
        target_sec=args.target_sec,
        title_suffix=args.title_suffix,
        force=args.force,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
