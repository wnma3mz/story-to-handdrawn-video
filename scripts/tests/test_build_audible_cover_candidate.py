#!/usr/bin/env python3
"""Minimal deterministic tests for the audible-cover candidate builder."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "build-audible-cover-candidate.py"
SPEC = importlib.util.spec_from_file_location("audible_cover_candidate", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class DurationFitTests(unittest.TestCase):
    def test_keeps_configured_duration_when_title_fits(self) -> None:
        result = MODULE.choose_effective_duration(2.7, 2.1, 0.15, 0.2, 30, 1.5)
        self.assertEqual(result["effective_duration_sec"], 2.7)
        self.assertFalse(result["override_applied"])
        self.assertFalse(result["atempo_filter_used"])
        self.assertFalse(result["last_syllable_trimmed"])

    def test_extends_to_next_frame_without_speeding_or_trimming(self) -> None:
        result = MODULE.choose_effective_duration(2.7, 2.64, 0.15, 0.2, 30, 1.5)
        self.assertEqual(result["effective_frame_count"], 90)
        self.assertEqual(result["effective_duration_sec"], 3.0)
        self.assertTrue(result["override_applied"])
        self.assertEqual(
            result["override_reason"],
            "natural_title_plus_head_and_tail_did_not_fit",
        )
        self.assertEqual(result["whole_title_tempo"], 1.0)
        self.assertFalse(result["last_syllable_trimmed"])

    def test_rejects_non_small_extension(self) -> None:
        with self.assertRaises(MODULE.BuildError):
            MODULE.choose_effective_duration(2.7, 4.0, 0.15, 0.2, 30, 1.0)


class LoudnormTests(unittest.TestCase):
    def test_preserves_all_two_pass_measurement_fields(self) -> None:
        payload = """
        {
          "input_i" : "-18.25",
          "input_tp" : "-3.10",
          "input_lra" : "0.00",
          "input_thresh" : "-28.25",
          "target_offset" : "0.02"
        }
        """
        result = MODULE.parse_loudnorm_raw(payload)
        self.assertEqual(result["input_thresh"], "-28.25")
        self.assertEqual(result["target_offset"], "0.02")


if __name__ == "__main__":
    unittest.main()
