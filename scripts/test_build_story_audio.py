#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from build_story_audio import build_program_master, resolve_background_music


def create_tone(path: Path, frequency: int, duration: float, channels: int) -> None:
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration}",
        "-ar", "48000", "-ac", str(channels), "-c:a", "pcm_s24le", str(path),
    ], check=True)


class BackgroundMusicTests(unittest.TestCase):
    def test_disabled_music_needs_no_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "voiceover.json"
            self.assertIsNone(
                resolve_background_music(
                    {"background_music": {"enabled": False}},
                    config_path,
                )
            )

    def test_relative_music_path_resolves_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            music_path = root / "music.wav"
            music_path.touch()
            resolved = resolve_background_music(
                {
                    "background_music": {
                        "enabled": True,
                        "path": "music.wav",
                    }
                },
                root / "voiceover.json",
            )
            self.assertEqual(resolved["path"], music_path.resolve())

    def test_enabled_music_builds_stereo_program_master(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            narration = root / "narration.wav"
            music_path = root / "music.wav"
            output = root / "program.wav"
            create_tone(narration, 440, 1.0, 1)
            create_tone(music_path, 220, 0.3, 2)
            music = resolve_background_music(
                {
                    "background_music": {
                        "enabled": True,
                        "path": str(music_path),
                        "fade_in_sec": 0.1,
                        "fade_out_sec": 0.1,
                    }
                },
                root / "voiceover.json",
            )
            build_program_master(narration, output, 1.0, music)
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries",
                "stream=sample_rate,channels:format=duration", "-of", "json",
                str(output),
            ], check=True, text=True, stdout=subprocess.PIPE)
            media = json.loads(probe.stdout)
            self.assertEqual(media["streams"][0]["sample_rate"], "48000")
            self.assertEqual(media["streams"][0]["channels"], 2)
            self.assertAlmostEqual(float(media["format"]["duration"]), 1.0, places=2)


if __name__ == "__main__":
    unittest.main()
