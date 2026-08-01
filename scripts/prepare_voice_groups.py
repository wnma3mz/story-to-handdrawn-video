#!/usr/bin/env python3
"""Pre-synthesize continuous Edge TTS groups into build_story_audio's cache."""

from __future__ import annotations

import argparse
import importlib.util
import json
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    workspace = (
        args.workspace
        or (Path(os.environ["STORY_VIDEO_WORKSPACE"]) if os.environ.get("STORY_VIDEO_WORKSPACE") else None)
        or Path.cwd()
    ).expanduser().resolve()
    config_path = args.config.expanduser()
    config_path = config_path.resolve() if config_path.is_absolute() else (workspace / config_path).resolve()

    audio = load_audio_module()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    profile = config["profile"]
    groups = config["continuity"]["groups"]
    raw_dir = workspace / ".work" / args.episode / "raw-groups"
    raw_dir.mkdir(parents=True, exist_ok=True)

    prepared = []
    for group in groups:
        group_id = str(group["id"])
        media = raw_dir / f"{group_id}.mp3"
        subtitles = raw_dir / f"{group_id}.vtt"
        cache_key_path = raw_dir / f"{group_id}.sha256"
        cue_texts = group.get("cue_texts")
        expected_key = audio.tts_cache_key(
            group["speech_text"], profile, cue_texts
        )
        cached_key = (
            cache_key_path.read_text(encoding="utf-8").strip()
            if cache_key_path.exists()
            else ""
        )
        if (
            args.force
            or not media.exists()
            or not subtitles.exists()
            or cached_key != expected_key
        ):
            audio.synthesize_cached(
                group["speech_text"],
                media,
                subtitles,
                profile,
                cache_key_path,
                expected_key,
                cue_texts,
            )
        cues = audio.parse_vtt(subtitles)
        prepared.append(
            {
                "id": group_id,
                "media": str(media),
                "vtt": str(subtitles),
                "duration_sec": round(audio.media_duration(media), 3),
                "cue_count": len(cues),
                "expected_cue_count": len(group["scene_ids"]),
            }
        )

    print(json.dumps({"episode": args.episode, "groups": prepared}, ensure_ascii=False, indent=2))
    if any(row["cue_count"] != row["expected_cue_count"] for row in prepared):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
