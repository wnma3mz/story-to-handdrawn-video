#!/usr/bin/env python3

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from extract_rollout_images import extract_images
from make_pilot import build_pilot
from story_timeline import compute_scene_timeline


class FrameLockedTimelineTests(unittest.TestCase):
    def test_cut_timeline_rounds_each_scene_to_renderer_frames(self) -> None:
        storyboard = {
            "project": {"fps": 30, "transition": "cut"},
            "scenes": [
                {"id": "01", "duration_sec": 1.01},
                {"id": "02", "duration_sec": 1.01},
            ],
        }
        timeline, total = compute_scene_timeline(storyboard)
        self.assertEqual(timeline["02"]["start_frame"], 30)
        self.assertEqual(timeline["02"]["end_frame"], 60)
        self.assertEqual(total, 2.0)

    def test_page_flip_timeline_uses_renderer_overlap(self) -> None:
        storyboard = {
            "project": {"fps": 30, "transition": "page-flip", "transition_sec": 0.7},
            "scenes": [
                {"id": "01", "duration_sec": 2.0},
                {"id": "02", "duration_sec": 2.0},
            ],
        }
        timeline, total = compute_scene_timeline(storyboard)
        self.assertEqual(timeline["02"]["start_frame"], 39)
        self.assertEqual(total, 3.3)


class RolloutExtractionTests(unittest.TestCase):
    def test_latest_matching_rollout_png_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            output = root / "assets" / "01_master.png"
            manifest.write_text(
                json.dumps(
                    {
                        "generator": "codex-image2",
                        "jobs": [
                            {
                                "id": "01",
                                "role": "scene",
                                "prompt": 'Narrative sentence to illustrate: "风起了。"\n',
                                "output_master": str(output),
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            png_one = b"\x89PNG\r\n\x1a\nfirst"
            png_two = b"\x89PNG\r\n\x1a\nsecond"
            rollout = root / "rollout.jsonl"
            rows = [
                {
                    "payload": {
                        "type": "image_generation_call",
                        "revised_prompt": "Scene 01. 风起了。",
                        "result": base64.b64encode(png_one).decode(),
                    }
                },
                {
                    "payload": {
                        "type": "image_generation_call",
                        "revised_prompt": "Scene 01 correction. 风起了。",
                        "result": base64.b64encode(png_two).decode(),
                    }
                },
            ]
            rollout.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )
            report = extract_images(rollout, manifest)
            self.assertEqual(output.read_bytes(), png_two)
            self.assertEqual(report[0]["rollout_line"], 2)


class PilotBuilderTests(unittest.TestCase):
    def test_pilot_keeps_prefix_jobs_and_transitive_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            storyboard_path = root / "storyboard.json"
            manifest_path = root / "manifest.json"
            voiceover_path = root / "voiceover.json"
            output_dir = root / "pilot"
            storyboard_path.write_text(
                json.dumps(
                    {
                        "project": {"title": "测试", "fps": 30, "transition": "cut"},
                        "scenes": [
                            {"id": "01", "duration_sec": 2.0},
                            {"id": "02", "duration_sec": 2.0},
                            {"id": "03", "duration_sec": 2.0},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "generator": "codex-image2",
                        "jobs": [
                            {"id": "character_reference", "depends_on": []},
                            {"id": "01", "depends_on": ["character_reference"]},
                            {"id": "02", "depends_on": ["character_reference"]},
                            {"id": "03", "depends_on": ["character_reference"]},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            voiceover_path.write_text(
                json.dumps(
                    {
                        "continuity": {
                            "groups": [
                                {
                                    "id": "G01",
                                    "scene_ids": ["01", "02", "03"],
                                    "cue_texts": ["第一句。", "第二句。", "第三句。"],
                                    "speech_text": "第一句。第二句。第三句。",
                                }
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            report = build_pilot(
                storyboard_path,
                manifest_path,
                output_dir,
                voiceover_path=voiceover_path,
                target_sec=3.5,
            )
            pilot_storyboard = json.loads(
                (output_dir / "storyboard.json").read_text(encoding="utf-8")
            )
            pilot_manifest = json.loads(
                (output_dir / "codex-image-jobs.json").read_text(encoding="utf-8")
            )
            pilot_voiceover = json.loads(
                (output_dir / "voiceover.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["scene_count"], 2)
            self.assertEqual([scene["id"] for scene in pilot_storyboard["scenes"]], ["01", "02"])
            self.assertEqual(
                [job["id"] for job in pilot_manifest["jobs"]],
                ["character_reference", "01", "02"],
            )
            group = pilot_voiceover["continuity"]["groups"][0]
            self.assertEqual(group["scene_ids"], ["01", "02"])
            self.assertEqual(group["speech_text"], "第一句。第二句。")
            self.assertTrue(group["pilot_truncated_source_group"])


if __name__ == "__main__":
    unittest.main()
