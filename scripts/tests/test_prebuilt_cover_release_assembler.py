#!/usr/bin/env python3
"""Deterministic tests for the prebuilt audible-cover release assembler."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "assemble-prebuilt-cover-release.py"
AUDITOR = ROOT / "scripts" / "audit_story_delivery.py"


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(path: Path, entries: str) -> dict:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            entries,
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(result.stdout)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class PrebuiltCoverReleaseAssemblerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.picture = self.base / "picture.mp4"
        self.narration = self.base / "narration.wav"
        self.cover = self.base / "cover.mp4"
        self.sync = self.base / "planned-sync.json"
        self.config = self.base / "timeline.json"
        self.no_cover = self.base / "no-cover.mp4"
        self.release = self.base / "release.mp4"
        self.build = self.base / "release-build.json"
        self.release_sync = self.base / "release-sync.json"
        self._make_picture(self.picture, 0.4)
        self._make_narration(self.narration, 0.4)
        self._make_cover(self.cover, 0.2)
        self._write_config(cover_duration=0.2, cover_frames=2)
        self.sync.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "mode": "pre_picture_audio_only",
                    "story_timeline": {
                        "duration_sec": 0.4,
                        "first_story_sentence_start_sec": 0.0,
                        "picture_timeline_status": "planned-storyboard-only",
                    },
                    "release_timeline": {
                        "main_video_start_sec": None,
                        "story_audio_start_sec": None,
                    },
                    "summary": {
                        "group_count": 1,
                        "group_internal_cut_count": 0,
                        "sentence_level_tempo_variants": 0,
                    },
                    "groups": [
                        {
                            "id": "G01",
                            "group_internal_cut_count": 0,
                            "sentence_level_tempo_variants": 0,
                            "whole_group_tempo": 1.0,
                        }
                    ],
                    "sentences": [
                        {
                            "index": 1,
                            "scene_id": "01",
                            "is_bridge": False,
                            "scene_start_sec": 0.0,
                            "scene_end_sec": 0.4,
                            "actual_start_sec": 0.0,
                            "actual_end_sec": 0.4,
                            "target_start_sec": 0.0,
                            "semantic_start_error_sec": 0.0,
                            "actual_offset_from_scene_start_sec": 0.0,
                            "scene_overlap_ratio": 1.0,
                            "gap_to_next_sec": None,
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _make_picture(path: Path, duration: float) -> None:
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x284878:s=64x96:r=10:d={duration}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "10",
                str(path),
            ]
        )

    @staticmethod
    def _make_narration(path: Path, duration: float) -> None:
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:sample_rate=48000:duration={duration}",
                "-c:a",
                "pcm_s24le",
                "-ar",
                "48000",
                "-ac",
                "1",
                str(path),
            ]
        )

    @staticmethod
    def _make_cover(path: Path, duration: float) -> None:
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x9b6542:s=64x96:r=10:d={duration}",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=660:sample_rate=48000:duration={duration}",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "10",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(path),
            ]
        )

    def _write_config(self, *, cover_duration: float, cover_frames: int) -> None:
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "cover": {
                        "duration_sec": cover_duration,
                        "frame_count": cover_frames,
                        "video_codec": "h264",
                        "audio_codec": "aac",
                        "audio_sample_rate_hz": 48000,
                        "audio_channels": 2,
                    },
                    "picture": {"video_codec": "h264"},
                    "narration": {
                        "audio_codec": "pcm_s24le",
                        "sample_rate_hz": 48000,
                        "channels": 1,
                    },
                    "timeline": {
                        "cover_video_start_sec": 0.0,
                        "cover_video_end_sec": cover_duration,
                        "main_video_start_sec": cover_duration,
                        "story_audio_start_sec": cover_duration,
                        "transition_overlap_sec": 0.0,
                    },
                    "delivery": {
                        "width": 64,
                        "height": 96,
                        "fps": "10/1",
                        "audio_sample_rate_hz": 48000,
                        "audio_channels": 2,
                        "audio_bitrate": "96k",
                        "video_encoder": "libx264",
                        "video_preset": "ultrafast",
                        "video_crf": 23,
                    },
                    "tolerances": {
                        "duration_sec": 0.05,
                        "timeline_sec": 0.001,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _command(self, *, narration: Path | None = None, approve: bool = True) -> list[str]:
        narration = narration or self.narration
        command = [
            sys.executable,
            str(SCRIPT),
            "--timeline-config",
            str(self.config),
            "--cover-clip",
            str(self.cover),
            "--picture",
            str(self.picture),
            "--narration",
            str(narration),
            "--planned-sync-map",
            str(self.sync),
            "--no-cover-output",
            str(self.no_cover),
            "--release-output",
            str(self.release),
            "--release-build-output",
            str(self.build),
            "--release-sync-map-output",
            str(self.release_sync),
            "--cover-sha256",
            digest(self.cover),
            "--picture-sha256",
            digest(self.picture),
            "--narration-sha256",
            digest(narration),
        ]
        if approve:
            command.append("--confirm-cover-approved")
        return command

    def test_builds_strict_release_and_preserves_picture_stream(self) -> None:
        result = run(self._command())
        self.assertIn("PASS:", result.stdout)
        build = json.loads(self.build.read_text(encoding="utf-8"))
        sync = json.loads(self.release_sync.read_text(encoding="utf-8"))
        self.assertEqual(build["status"], "PASS_TECHNICAL_ASSEMBLY_HUMAN_RELEASE_LISTEN_REQUIRED")
        self.assertFalse(build["commands"]["no_cover_uses_shortest"])
        self.assertEqual(build["commands"]["no_cover_video_codec_policy"], "copy")
        self.assertEqual(
            build["output_evidence"]["picture_video_stream_sha256"],
            build["output_evidence"]["no_cover_video_stream_sha256"],
        )
        self.assertEqual(sync["release_timeline"]["main_video_start_sec"], 0.2)
        self.assertEqual(sync["release_timeline"]["story_audio_start_sec"], 0.2)
        self.assertEqual(sync["release_timeline"]["main_video_story_audio_delta_sec"], 0.0)
        self.assertEqual(
            sync["summary"]["maximum_non_bridge_scene_start_offset_sec"],
            0.0,
        )
        self.assertEqual(sync["sentences"][0]["release_actual_start_sec"], 0.2)
        release_probe = probe(
            self.release,
            "stream=codec_type,nb_read_frames,width,height,r_frame_rate,sample_rate,channels",
        )
        release_video = next(
            stream for stream in release_probe["streams"] if stream["codec_type"] == "video"
        )
        self.assertEqual(int(release_video["nb_read_frames"]), 6)
        audit = run(
            [
                sys.executable,
                str(AUDITOR),
                str(self.release),
                "--sync-map",
                str(self.release_sync),
                "--cover-duration",
                "0.2",
                "--expected-duration",
                "0.6",
                "--expect-width",
                "64",
                "--expect-height",
                "96",
                "--expect-fps",
                "10/1",
            ]
        )
        self.assertEqual(json.loads(audit.stdout)["status"], "PASS")

    def test_rejects_stale_cover_duration_before_writing_outputs(self) -> None:
        self._write_config(cover_duration=0.3, cover_frames=2)
        result = run(self._command(), check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("stale duration assumption", result.stderr)
        self.assertFalse(self.no_cover.exists())
        self.assertFalse(self.release.exists())
        self.assertFalse(self.build.exists())

    def test_rejects_cover_frame_count_mismatch(self) -> None:
        replacement = self.base / "three-frame-cover.mp4"
        self._make_cover(replacement, 0.3)
        self.cover = replacement
        result = run(self._command(), check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("cover_frame_count", result.stderr)
        self.assertFalse(self.no_cover.exists())
        self.assertFalse(self.release.exists())

    def test_rejects_picture_narration_delta_over_50ms(self) -> None:
        long_narration = self.base / "long-narration.wav"
        self._make_narration(long_narration, 0.6)
        result = run(self._command(narration=long_narration), check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("narration/picture duration difference", result.stderr)
        self.assertFalse(self.no_cover.exists())
        self.assertFalse(self.release.exists())

    def test_requires_explicit_human_cover_approval(self) -> None:
        result = run(self._command(approve=False), check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--confirm-cover-approved is required", result.stderr)
        self.assertFalse(self.no_cover.exists())
        self.assertFalse(self.release.exists())

    def test_rejects_main_audio_timeline_mismatch(self) -> None:
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["timeline"]["story_audio_start_sec"] = 0.3
        self.config.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        result = run(self._command(), check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("story_audio_start_sec must equal", result.stderr)
        self.assertFalse(self.no_cover.exists())
        self.assertFalse(self.release.exists())


if __name__ == "__main__":
    unittest.main()
