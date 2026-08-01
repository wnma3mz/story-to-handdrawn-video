#!/usr/bin/env python3
"""Guard the single-worker visual rendering contract."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RENDER_SCRIPT = ROOT / "scripts" / "render-picture.mjs"


class RendererConcurrencyContractTest(unittest.TestCase):
    def test_preview_and_formal_render_are_single_worker(self) -> None:
        source = RENDER_SCRIPT.read_text(encoding="utf-8")
        self.assertGreaterEqual(
            source.count("'--concurrency=1'"),
            2,
            "uploaded and storyboard renders must both remain single-worker",
        )
        self.assertNotIn("--concurrency=2", source)


if __name__ == "__main__":
    unittest.main()
