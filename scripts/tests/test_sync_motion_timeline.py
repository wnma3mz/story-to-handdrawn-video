#!/usr/bin/env python3
"""Tests for portable visual-plan to motion-timeline synchronization."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sync-motion-timeline.py"


class SyncMotionTimelineTest(unittest.TestCase):
    def test_resolves_relative_paths_against_explicit_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            episode = workspace / "episodes" / "e01"
            episode.mkdir(parents=True)
            (episode / "visual-plan.json").write_text(
                json.dumps(
                    {
                        "01": {"duration_sec": 4.5, "motion": "push_soft"},
                        "02": {"duration_sec": 3, "motion": "hold"},
                    }
                ),
                encoding="utf-8",
            )
            (episode / "codex-image-jobs.json").write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": "01",
                                "role": "scene",
                                "output_master": "assets/e01/01.png",
                            },
                            {
                                "id": "02",
                                "role": "scene",
                                "output_master": "assets/e01/02.png",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "episodes/e01",
                    "--workspace",
                    str(workspace),
                    "--output",
                    "evidence/e01-motion.tsv",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            output = workspace / "evidence" / "e01-motion.tsv"
            self.assertIn("WROTE", result.stdout)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "# scene\tduration\timage\tmotion\n"
                "01\t4.5\tassets/e01/01.png\tpush_soft\n"
                "02\t3\tassets/e01/02.png\thold\n",
            )


if __name__ == "__main__":
    unittest.main()
