#!/usr/bin/env python3
"""Replace ink-comic summary captions with the exact final TTS sentences.

The voiceover config is the source of truth. Each narration group must contain
exactly one terminally-punctuated sentence per scene id.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SENTENCE = re.compile(r"[^。！？!?]+(?:[。！？!?]+|$)")


def sentences(text: str) -> list[str]:
    return [match.group(0).strip() for match in SENTENCE.finditer(text) if match.group(0).strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", type=Path, default=Path("storyboard.json"))
    parser.add_argument("--config", type=Path, required=True, help="Final voiceover JSON")
    parser.add_argument("--output", type=Path, help="Output storyboard; defaults to --storyboard")
    args = parser.parse_args()

    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    groups = config.get("continuity", {}).get("groups", [])
    if not groups:
        raise SystemExit("voiceover config has no continuity.groups")

    spoken_by_scene: dict[str, str] = {}
    for group in groups:
        scene_ids = [str(value) for value in group.get("scene_ids", [])]
        spoken = sentences(str(group.get("speech_text", "")))
        if len(spoken) != len(scene_ids):
            raise SystemExit(
                f"{group.get('id', '(unnamed group)')}: {len(spoken)} spoken sentences "
                f"for {len(scene_ids)} scene ids"
            )
        for scene_id, sentence in zip(scene_ids, spoken):
            if scene_id in spoken_by_scene:
                raise SystemExit(f"scene {scene_id} appears in more than one narration group")
            spoken_by_scene[scene_id] = sentence

    scenes = storyboard.get("scenes", [])
    known = {str(scene.get("id")) for scene in scenes}
    unknown = sorted(set(spoken_by_scene) - known)
    if unknown:
        raise SystemExit(f"voiceover config references unknown scenes: {', '.join(unknown)}")
    if storyboard.get("project", {}).get("visual_mode") == "ink-comic":
        missing = sorted(known - set(spoken_by_scene))
        if missing:
            raise SystemExit(f"ink-comic final subtitles missing scenes: {', '.join(missing)}")

    changed = 0
    for scene in scenes:
        scene_id = str(scene.get("id"))
        if scene_id not in spoken_by_scene:
            continue
        spoken = spoken_by_scene[scene_id]
        old_text = str(scene.get("text", ""))
        if old_text and old_text != spoken and "summary_text" not in scene:
            scene["summary_text"] = old_text
        scene["text"] = spoken
        scene["narration"] = spoken
        changed += 1

    storyboard.setdefault("project", {})["subtitle_contract"] = "verbatim_tts"
    target = args.output or args.storyboard
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(f"Applied verbatim TTS subtitles to {changed} scenes → {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
