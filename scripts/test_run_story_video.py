#!/usr/bin/env python3
"""Tests for the Python convenience wrapper's style-profile forwarding."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("run_story_video.py")
SPEC = importlib.util.spec_from_file_location("run_story_video", MODULE_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class StyleProfileWrapperTest(unittest.TestCase):
    def test_episode_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "scripts").mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            (project / "scripts/story-to-video.mjs").write_text("", encoding="utf-8")
            argv = [
                str(MODULE_PATH),
                "--text",
                "一句话。",
                "--episode",
                "..",
                "--project-dir",
                str(project),
                "--workspace",
                str(project / "task"),
            ]
            with patch.object(sys, "argv", argv), self.assertRaises(SystemExit):
                RUNNER.main()

    def test_profile_selects_mode_when_visual_mode_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "scripts").mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            (project / "scripts/story-to-video.mjs").write_text("", encoding="utf-8")
            argv = [
                str(MODULE_PATH),
                "--text",
                "一句话。",
                "--style-profile",
                "celadon-kiln-scroll",
                "--project-dir",
                str(project),
                "--workspace",
                str(project / "task"),
            ]
            with patch.object(sys, "argv", argv), patch.object(
                RUNNER.subprocess, "run"
            ) as mocked_run:
                RUNNER.main()

            command = mocked_run.call_args.args[0]
            self.assertIn("--style-profile", command)
            self.assertEqual(
                command[command.index("--style-profile") + 1],
                "celadon-kiln-scroll",
            )
            self.assertNotIn("--visual-mode", command)
            self.assertEqual(
                command[command.index("--workspace") + 1],
                str((project / "task").resolve()),
            )

    def test_real_plan_keeps_generated_files_in_external_workspace(self) -> None:
        project = MODULE_PATH.parent.parent
        renderer_roots = [
            project / "prompts/generated",
            project / "public/assets/generated",
            project / "episodes",
            project / "out",
            project / ".work",
        ]
        before = [path.exists() for path in renderer_roots]
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--project-dir",
                    str(project),
                    "--workspace",
                    str(workspace),
                    "--text",
                    "风吹过旧院子。",
                    "--title",
                    "外部工作区测试",
                    "--mode",
                    "plan",
                ],
                cwd=workspace,
                check=True,
                text=True,
                capture_output=True,
            )
            storyboard_path = workspace / "storyboard.generated.json"
            self.assertTrue(storyboard_path.is_file(), result.stdout)
            storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
            self.assertGreater(len(storyboard["scenes"]), 0)
            self.assertTrue((workspace / "prompts/generated").is_dir())
            self.assertTrue((workspace / "public/assets/generated").is_dir())
        self.assertEqual([path.exists() for path in renderer_roots], before)

    def test_render_staging_uses_external_workdir_and_bundled_assets(self) -> None:
        project = MODULE_PATH.parent.parent
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            storyboard = workspace / "storyboard.json"
            storyboard.write_text(
                (project / "storyboard.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "node",
                    str(project / "scripts/prepare-render-assets.mjs"),
                    "--episode",
                    "workspace-test",
                    "--storyboard",
                    str(storyboard),
                    "--asset-root",
                    str(workspace / "public"),
                    "--work-root",
                    str(workspace / ".work"),
                ],
                cwd=project,
                check=True,
                text=True,
                capture_output=True,
            )
            staged_public = Path(result.stdout.strip())
            self.assertTrue(staged_public.is_relative_to(workspace / ".work"))
            self.assertTrue((staged_public / "assets/02_bw.png").is_file())
            self.assertTrue((staged_public / "fonts").is_dir())


if __name__ == "__main__":
    unittest.main()
