#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "split_verbatim_subtitle_scenes.py"


class SplitVerbatimSubtitleScenesTests(unittest.TestCase):
    def test_split_preserves_picture_and_continuous_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "storyboard.json"
            plan = root / "cues.json"
            output = root / "output.json"
            source.write_text(
                json.dumps(
                    {
                        "project": {
                            "fps": 30,
                            "subtitle_contract": "draft_summary",
                        },
                        "scenes": [
                            {
                                "id": "01",
                                "duration_sec": 6,
                                "text": "摘要",
                                "narration": "风起了；少年回头。",
                                "motion": "push_soft",
                                "focus": "left",
                                "assets": {"color": "same.png"},
                                "transition_to_next": "fade",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            plan.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "scenes": {"01": ["风起了。", "少年回头。"]},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--storyboard",
                    str(source),
                    "--cue-plan",
                    str(plan),
                    "--output",
                    str(output),
                    "--color-grade",
                    "warm_bronze",
                ],
                check=True,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                text=True,
            )
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["project"]["subtitle_contract"], "verbatim_tts")
            self.assertEqual(result["project"]["color_grade"], "warm_bronze")
            self.assertEqual([row["id"] for row in result["scenes"]], ["01a", "01b"])
            self.assertEqual(
                [row["text"] for row in result["scenes"]],
                ["风起了。", "少年回头。"],
            )
            self.assertTrue(result["scenes"][0]["visual_interval_start"])
            self.assertFalse(result["scenes"][1]["visual_interval_start"])
            self.assertEqual(
                result["scenes"][0]["visual_interval_progress_start"], 0
            )
            self.assertEqual(
                result["scenes"][-1]["visual_interval_progress_end"], 1
            )
            self.assertEqual(
                result["scenes"][0]["assets"], result["scenes"][1]["assets"]
            )
            self.assertEqual(
                result["scenes"][0]["motion"], result["scenes"][1]["motion"]
            )
            self.assertEqual(result["scenes"][0]["transition_to_next"], "cut")
            self.assertEqual(result["scenes"][1]["transition_to_next"], "fade")


if __name__ == "__main__":
    unittest.main()
