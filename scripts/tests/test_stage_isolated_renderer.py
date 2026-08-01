#!/usr/bin/env python3
"""Regression tests for safe, reproducible isolated-renderer staging."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "stage-isolated-renderer.py"
PROVENANCE = "STAGING_PROVENANCE.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StageIsolatedRendererTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.renderer = self.base / "renderer"
        self.renderer.mkdir()
        (self.renderer / ".git").mkdir()
        (self.renderer / ".git" / "config").write_text("private\n", encoding="utf-8")
        (self.renderer / "node_modules" / "a-package").mkdir(parents=True)
        (self.renderer / "node_modules" / "a-package" / "index.js").write_text(
            "module.exports = 1;\n",
            encoding="utf-8",
        )
        (self.renderer / "out").mkdir()
        (self.renderer / "out" / "existing.mp4").write_bytes(b"existing render")
        (self.renderer / "build").mkdir()
        (self.renderer / "build" / "stale.bundle.js").write_text(
            "stale compiled output\n",
            encoding="utf-8",
        )
        (self.renderer / "src").mkdir()
        (self.renderer / "src" / "Root.tsx").write_text(
            "export const Root = () => null;\n",
            encoding="utf-8",
        )
        (self.renderer / "package.json").write_text(
            '{"scripts":{"render":"remotion render"}}\n',
            encoding="utf-8",
        )
        (self.renderer / "public" / "assets" / "episode").mkdir(parents=True)
        (self.renderer / "public" / "assets" / "episode" / "used.png").write_bytes(
            b"used image"
        )
        (self.renderer / "public" / "assets" / "episode" / "unused.png").write_bytes(
            b"unused image"
        )
        (self.renderer / "public" / "fonts").mkdir()
        (self.renderer / "public" / "fonts" / "story.ttf").write_bytes(b"font")
        (self.renderer / "public" / "not-render-input.txt").write_text(
            "do not copy\n",
            encoding="utf-8",
        )
        self.protected_storyboards: dict[Path, bytes] = {}
        for name, marker in (
            ("storyboard.json", "shared"),
            ("storyboard.generated.json", "generated"),
            ("storyboard.uploaded.json", "uploaded"),
        ):
            path = self.renderer / name
            path.write_text(
                json.dumps({"marker": marker}) + "\n",
                encoding="utf-8",
            )
            self.protected_storyboards[path] = path.read_bytes()

        self.storyboard = self.base / "episode-storyboard.json"
        self.storyboard.write_text(
            json.dumps(
                {
                    "title": "Episode",
                    "scenes": [
                        {
                            "id": "01",
                            "assets": {
                                "bw": "assets/episode/used.png",
                                "color": "assets/episode/used.png",
                                "detail": None,
                            },
                        },
                        {"id": "02", "assets": {}},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.out_before = (self.renderer / "out" / "existing.mp4").read_bytes()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_stage(
        self,
        destination: Path,
        *,
        storyboard: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--renderer-root",
                str(self.renderer),
                "--storyboard",
                str(storyboard or self.storyboard),
                "--destination",
                str(destination),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def assert_source_protected(self) -> None:
        for path, expected in self.protected_storyboards.items():
            self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(
            (self.renderer / "out" / "existing.mp4").read_bytes(),
            self.out_before,
        )

    def test_stages_only_current_code_referenced_assets_and_fonts(self) -> None:
        destination = self.base / "isolated"
        result = self.run_stage(destination)
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertEqual(
            (destination / "src" / "Root.tsx").read_text(encoding="utf-8"),
            "export const Root = () => null;\n",
        )
        self.assertFalse((destination / ".git").exists())
        self.assertFalse((destination / "build").exists())
        self.assertFalse((destination / "out").exists())
        self.assertFalse((destination / "public" / "not-render-input.txt").exists())
        self.assertTrue(
            (destination / "public" / "assets" / "episode" / "used.png").is_file()
        )
        self.assertFalse(
            (destination / "public" / "assets" / "episode" / "unused.png").exists()
        )
        self.assertEqual(
            (destination / "public" / "fonts" / "story.ttf").read_bytes(),
            b"font",
        )

        installed_storyboard = self.storyboard.read_bytes()
        self.assertEqual((destination / "storyboard.json").read_bytes(), installed_storyboard)
        self.assertEqual(
            (destination / "storyboard.generated.json").read_bytes(),
            installed_storyboard,
        )
        self.assertEqual(
            (destination / "storyboard.uploaded.json").read_bytes(),
            self.protected_storyboards[self.renderer / "storyboard.uploaded.json"],
        )

        linked_modules = destination / "node_modules"
        self.assertTrue(linked_modules.is_symlink())
        self.assertEqual(linked_modules.resolve(), (self.renderer / "node_modules").resolve())

        provenance = json.loads((destination / PROVENANCE).read_text(encoding="utf-8"))
        self.assertEqual(provenance["schema"], "isolated-renderer-stage/v1")
        self.assertTrue(provenance["invariants"]["source_protected_state_unchanged"])
        self.assertEqual(
            provenance["source"]["storyboard_sha256"],
            digest(self.storyboard),
        )
        self.assertEqual(
            [entry["storyboard_path"] for entry in provenance["staged"]["referenced_assets"]],
            ["assets/episode/used.png"],
        )
        self.assertEqual(
            provenance["staged"]["referenced_assets"][0]["referenced_by"],
            ["scene '01'.assets.bw", "scene '01'.assets.color"],
        )
        self.assert_source_protected()

    def test_hashes_are_reproducible_across_destinations(self) -> None:
        first = self.base / "isolated-a"
        second = self.base / "isolated-b"
        first_result = self.run_stage(first)
        second_result = self.run_stage(second)
        self.assertEqual(first_result.returncode, 0, first_result.stderr)
        self.assertEqual(second_result.returncode, 0, second_result.stderr)
        first_provenance = json.loads((first / PROVENANCE).read_text(encoding="utf-8"))
        second_provenance = json.loads((second / PROVENANCE).read_text(encoding="utf-8"))
        for key in (
            "storyboard_sha256",
            "renderer_snapshot_sha256",
            "protected_state_sha256",
        ):
            self.assertEqual(first_provenance["source"][key], second_provenance["source"][key])
        self.assertEqual(
            first_provenance["staged"]["tree_sha256"],
            second_provenance["staged"]["tree_sha256"],
        )

    def test_existing_destination_fails_without_overwriting(self) -> None:
        destination = self.base / "occupied"
        destination.mkdir()
        marker = destination / "keep.txt"
        marker.write_text("keep\n", encoding="utf-8")
        result = self.run_stage(destination)
        self.assertEqual(result.returncode, 2)
        self.assertIn("destination already exists", result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")
        self.assert_source_protected()

    def test_missing_asset_fails_before_destination_is_created(self) -> None:
        missing_storyboard = self.base / "missing.json"
        missing_storyboard.write_text(
            json.dumps(
                {
                    "scenes": [
                        {
                            "id": "missing",
                            "assets": {"color": "assets/episode/missing.png"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        destination = self.base / "missing-stage"
        result = self.run_stage(destination, storyboard=missing_storyboard)
        self.assertEqual(result.returncode, 2)
        self.assertIn("does not exist", result.stderr)
        self.assertFalse(destination.exists())
        self.assert_source_protected()

    def test_unsafe_asset_path_is_rejected(self) -> None:
        unsafe_storyboard = self.base / "unsafe.json"
        unsafe_storyboard.write_text(
            json.dumps(
                {
                    "scenes": [
                        {
                            "id": "unsafe",
                            "assets": {"color": "assets/../package.json"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        destination = self.base / "unsafe-stage"
        result = self.run_stage(destination, storyboard=unsafe_storyboard)
        self.assertEqual(result.returncode, 2)
        self.assertIn("normalized path below public/assets", result.stderr)
        self.assertFalse(destination.exists())
        self.assert_source_protected()

    def test_destination_below_renderer_is_rejected(self) -> None:
        destination = self.renderer / "episode-stage"
        result = self.run_stage(destination)
        self.assertEqual(result.returncode, 2)
        self.assertIn("outside the source renderer", result.stderr)
        self.assertFalse(destination.exists())
        self.assert_source_protected()

    def test_symlinked_asset_is_rejected(self) -> None:
        external = self.base / "external.png"
        external.write_bytes(b"external")
        linked = self.renderer / "public" / "assets" / "episode" / "linked.png"
        os.symlink(external, linked)
        linked_storyboard = self.base / "linked.json"
        linked_storyboard.write_text(
            json.dumps(
                {
                    "scenes": [
                        {
                            "id": "linked",
                            "assets": {"color": "assets/episode/linked.png"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        destination = self.base / "linked-stage"
        result = self.run_stage(destination, storyboard=linked_storyboard)
        self.assertEqual(result.returncode, 2)
        self.assertIn("traverses a symlink", result.stderr)
        self.assertFalse(destination.exists())
        self.assert_source_protected()


if __name__ == "__main__":
    unittest.main()
