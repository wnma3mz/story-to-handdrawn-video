#!/usr/bin/env python3
"""Unit tests for the rendered transition evidence contract."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "audit-rendered-transitions.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "audit_rendered_transitions",
        MODULE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class JavaScriptFramePlanningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_math_round_matches_javascript_for_positive_halves(self) -> None:
        self.assertEqual(self.module.js_math_round(0.49), 0)
        self.assertEqual(self.module.js_math_round(0.5), 1)
        self.assertEqual(self.module.js_math_round(10.49), 10)
        self.assertEqual(self.module.js_math_round(10.5), 11)

    def test_internal_fade_samples_and_terminal_transition_are_exact(self) -> None:
        storyboard = {
            "project": {
                "fps": 30,
                "transition": "cut",
                "transition_sec": 0.7,
            },
            "scenes": [
                {
                    "id": "01",
                    "duration_sec": 1.015,
                    "transition_to_next": "fade",
                },
                {
                    "id": "02",
                    "duration_sec": 2.0,
                    "transition_to_next": "cut",
                },
                {
                    "id": "03",
                    "duration_sec": 1.0,
                    "transition_to_next": "fade",
                },
            ],
        }
        plan = self.module.build_transition_plan(storyboard)
        self.assertEqual(plan["expected_frame_count"], 120)
        self.assertEqual(plan["fade_frames"], 21)
        self.assertEqual(plan["route_counts"], {"fade": 1, "cut": 1, "terminal_ignored": 1})
        fade = plan["transitions"][0]
        self.assertEqual(fade["boundary_frame"], 30)
        self.assertEqual(
            [(row["role"], row["frame"]) for row in fade["samples"]],
            [
                ("out_end", 29),
                ("fade_00", 30),
                ("fade_05", 35),
                ("fade_10", 40),
                ("fade_15", 45),
                ("fade_20", 50),
                ("in_live", 51),
            ],
        )
        self.assertEqual(
            plan["terminal_transition_ignored"],
            {"scene": "03", "declared": "fade"},
        )


class FadeEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def evaluation(self, boundary_metrics, boundary_similarity):
        common = {
            "metrics": {"yavg": 235.0, "nonwhite_ratio": 0.12},
            "similarity_to_out_end": {
                "global_luma_ssim": 1.0,
                "normalized_rgb_similarity": 1.0,
            },
        }
        rows = [
            {"role": "out_end", "offset": -1, **common},
            {
                "role": "fade_00",
                "offset": 0,
                "metrics": boundary_metrics,
                "similarity_to_out_end": boundary_similarity,
            },
            {
                "role": "fade_20",
                "offset": 20,
                "metrics": {"yavg": 250.0, "nonwhite_ratio": 0.03},
                "similarity_to_out_end": {
                    "global_luma_ssim": 0.80,
                    "normalized_rgb_similarity": 0.90,
                },
            },
            {
                "role": "in_live",
                "offset": 21,
                "metrics": {"yavg": 249.0, "nonwhite_ratio": 0.04},
                "similarity_to_out_end": {
                    "global_luma_ssim": 0.79,
                    "normalized_rgb_similarity": 0.89,
                },
            },
        ]
        return self.module.evaluate_fade(
            rows,
            minimum_boundary_ssim=0.995,
            minimum_boundary_similarity=0.995,
            minimum_nonwhite_retention=0.85,
            maximum_boundary_yavg_delta=2.0,
            minimum_outgoing_nonwhite_ratio=0.002,
            white_frame_yavg=253.5,
            white_frame_nonwhite_ratio=0.001,
            minimum_tail_similarity_drop=0.001,
        )

    def test_completed_outgoing_frame_at_fade_zero_passes(self) -> None:
        result = self.evaluation(
            {"yavg": 235.1, "nonwhite_ratio": 0.119},
            {
                "global_luma_ssim": 0.9998,
                "normalized_rgb_similarity": 0.9997,
            },
        )
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["measurements"]["hard_cut_to_white_detected"])

    def test_hard_cut_to_white_fails_closed_even_when_decode_would_pass(self) -> None:
        result = self.evaluation(
            {"yavg": 255.0, "nonwhite_ratio": 0.0},
            {
                "global_luma_ssim": 0.70,
                "normalized_rgb_similarity": 0.92,
            },
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["measurements"]["hard_cut_to_white_detected"])
        self.assertFalse(
            result["checks"]["fade_frame_zero_is_not_hard_cut_to_white"]
        )


if __name__ == "__main__":
    unittest.main()
