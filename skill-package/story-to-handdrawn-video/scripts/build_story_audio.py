#!/usr/bin/env python3
"""Portable Skill wrapper for continuous narration and release assembly."""

from __future__ import annotations

import os
import runpy
from pathlib import Path


def find_project() -> Path:
    configured = os.environ.get("STORY_VIDEO_PROJECT")
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = [Path.cwd(), *Path(__file__).resolve().parents]
    for candidate in candidates:
        script = candidate / "scripts/build_story_audio.py"
        if (candidate / "package.json").exists() and script.exists():
            return candidate
    raise SystemExit("Story video project not found; run inside it or set STORY_VIDEO_PROJECT.")


if __name__ == "__main__":
    project = find_project()
    os.chdir(project)
    runpy.run_path(str(project / "scripts/build_story_audio.py"), run_name="__main__")
