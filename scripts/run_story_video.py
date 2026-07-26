#!/usr/bin/env python3
"""Convenience entry point for the story-to-handdrawn-video Remotion project."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def default_project() -> Path:
    """Find the project without relying on the original author's machine path."""
    configured = os.environ.get("STORY_VIDEO_PROJECT")
    if configured:
        return Path(configured).expanduser().resolve()

    candidates = [Path.cwd(), *Path(__file__).resolve().parents]
    for candidate in candidates:
        if (candidate / "package.json").exists() and (
            candidate / "scripts/story-to-video.mjs"
        ).exists():
            return candidate
    return Path.cwd()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan, generate, import, or render a hand-drawn story animation."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="UTF-8 story text file")
    source.add_argument("--text", help="Inline story copy")
    source.add_argument(
        "--images",
        type=Path,
        nargs="+",
        help="Uploaded comic pages or full-frame images, in playback order",
    )
    parser.add_argument("--title", default="手绘故事")
    parser.add_argument("--episode", default=os.environ.get("EPISODE", "default"))
    parser.add_argument("--series-title", default="手绘故事 · 动画")
    parser.add_argument("--episode-label")
    parser.add_argument("--episode-number")
    parser.add_argument("--cover-title")
    parser.add_argument("--cover-background", help="Non-white CSS color, for example #5E7468")
    parser.add_argument("--character-lock")
    parser.add_argument(
        "--character-reference-prompt",
        type=Path,
        help=(
            "Episode-specific brief for a newly generated character reference. "
            "This limits the local reference job without weakening the full scene continuity lock."
        ),
    )
    parser.add_argument("--visual-plan", type=Path)
    parser.add_argument(
        "--scene-contract",
        action="store_true",
        help="Preserve one non-empty source line per complete visual-plan scene",
    )
    parser.add_argument(
        "--mode",
        choices=("plan", "generate", "full", "import", "render", "preview"),
        default="plan",
    )
    parser.add_argument("--generator", choices=("codex", "api"), default="codex")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--storyboard",
        type=Path,
        help="Storyboard to render in render/preview modes",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Episode-specific generated storyboard path",
    )
    parser.add_argument("--asset-set")
    parser.add_argument("--character-reference", type=Path)
    parser.add_argument("--text-mode", choices=("image2", "font"), default="font")
    parser.add_argument(
        "--visual-mode",
        choices=("diary", "essay", "ink-comic"),
        default="diary",
        help="Diary, literary essay, or full-screen 16:9 monochrome motion comic",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=max(1, min(4, os.cpu_count() or 1)),
        help="Parallel jobs for independent asset and TTS work",
    )
    parser.add_argument("--transition", choices=("cut", "page-flip"), default="cut")
    parser.add_argument("--transition-sec", type=float, default=0.7)
    parser.add_argument("--page-duration", type=float, default=4.4)
    parser.add_argument("--layout", choices=("auto", "composite", "full"), default="auto")
    parser.add_argument(
        "--split-y",
        action="append",
        default=[],
        metavar="SCENE:PIXELS",
        help="Override the caption/art split for an uploaded scene (repeatable)",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=default_project(),
    )
    return parser.parse_args()


def require_project(project: Path) -> None:
    required = (project / "package.json", project / "scripts/story-to-video.mjs")
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"Story video project is incomplete; missing: {', '.join(missing)}")


def run(command: list[str], project: Path) -> None:
    subprocess.run(command, cwd=project, check=True)


def main() -> None:
    args = parse_args()
    project = args.project_dir.expanduser().resolve()
    require_project(project)
    if args.jobs < 1 or args.jobs > 16:
        raise SystemExit("--jobs must be within 1..16")
    os.environ["EPISODE"] = args.episode
    isolated_dir = project / "episodes" / args.episode
    default_storyboard = project / "storyboard.json"
    requested_storyboard = (
        args.storyboard.expanduser().resolve()
        if args.storyboard
        else (
            default_storyboard
            if args.episode == "default"
            else isolated_dir / "storyboard.json"
        )
    )

    if args.images:
        if args.mode == "import":
            raise SystemExit("--mode import is reserved for Codex Image2 manifests")
        command = ["npm", "run", "import:uploaded", "--"]
        for image in args.images:
            command += ["--image", str(image.expanduser().resolve())]
        command += [
            "--title",
            args.title,
            "--transition",
            args.transition,
            "--transition-sec",
            str(args.transition_sec),
            "--page-duration",
            str(args.page_duration),
            "--layout",
            args.layout,
        ]
        uploaded_storyboard = (
            args.output.expanduser().resolve()
            if args.output
            else (
                project / "storyboard.uploaded.json"
                if args.episode == "default"
                else isolated_dir / "storyboard.uploaded.json"
            )
        )
        uploaded_manifest = (
            project / "uploaded-pages.json"
            if args.episode == "default"
            else isolated_dir / "uploaded-pages.json"
        )
        command += [
            "--output",
            str(uploaded_storyboard),
            "--manifest",
            str(uploaded_manifest),
        ]
        for split_y in args.split_y:
            command += ["--split-y", split_y]
        run(command, project)
        if args.mode in {"full", "render"}:
            run([
                "npm", "run", "render:uploaded", "--",
                "--episode", args.episode,
                "--storyboard", str(uploaded_storyboard),
            ], project)
            print(
                f"Rendered uploaded-image video: "
                f"{project / 'out' / args.episode / 'uploaded.mp4'}"
            )
        elif args.mode == "preview":
            run([
                "npm", "run", "render:uploaded:preview", "--",
                "--episode", args.episode,
                "--storyboard", str(uploaded_storyboard),
            ], project)
            print(
                f"Rendered uploaded-image preview: "
                f"{project / 'out' / args.episode / 'uploaded-preview.mp4'}"
            )
        else:
            print(f"Prepared uploaded-image storyboard: {uploaded_storyboard}")
        return

    if args.mode in {"render", "preview"}:
        run([
            "npm", "run", "render" if args.mode == "render" else "render:preview",
            "--", "--episode", args.episode, "--storyboard", str(requested_storyboard),
        ], project)
        output = project / "out" / args.episode / (
            "silent.mp4" if args.mode == "render" else "silent-preview.mp4"
        )
        print(f"Rendered silent video: {output}")
        return

    if args.mode == "import":
        command = [
            "npm", "run", "import:codex", "--",
            "--jobs", str(args.jobs),
        ]
        if args.manifest:
            command += ["--manifest", str(args.manifest.expanduser().resolve())]
        elif args.episode != "default":
            command += ["--manifest", str(isolated_dir / "codex-image-jobs.json")]
        if args.episode == "default" and not args.output:
            command.append("--apply")
        run(command, project)
        print(
            "Imported Codex Image2 assets"
            + (
                f" and activated: {project / 'storyboard.json'}"
                if "--apply" in command
                else " without changing the global storyboard"
            )
        )
        return

    if not args.input and not args.text:
        raise SystemExit(
            "--input, --text, or --images is required for plan, generate, and full modes"
        )
    if (
        args.generator == "api"
        and args.mode in {"generate", "full"}
        and not os.environ.get("OPENAI_API_KEY")
    ):
        raise SystemExit("OPENAI_API_KEY is required only for --generator api")

    command = ["npm", "run", "story", "--"]
    if args.input:
        command += ["--input", str(args.input.expanduser().resolve())]
    else:
        command += ["--text", args.text]
    command += [
        "--title",
        args.title,
        "--series-title",
        args.series_title,
        "--text-mode",
        args.text_mode,
        "--generator",
        args.generator,
        "--visual-mode",
        args.visual_mode,
        "--transition",
        args.transition,
        "--transition-sec",
        str(args.transition_sec),
        "--jobs",
        str(args.jobs),
    ]
    for option, value in (
        ("--episode-label", args.episode_label),
        ("--episode-number", args.episode_number),
        ("--cover-title", args.cover_title),
        ("--cover-background", args.cover_background),
    ):
        if value:
            command += [option, value]
    if args.character_lock:
        command += ["--character-lock", args.character_lock]
    if args.character_reference_prompt:
        command += [
            "--character-reference-prompt",
            str(args.character_reference_prompt.expanduser().resolve()),
        ]
    if args.visual_plan:
        command += ["--visual-plan", str(args.visual_plan.expanduser().resolve())]
    if args.scene_contract:
        command.append("--scene-contract")
    if args.manifest:
        command += ["--manifest", str(args.manifest.expanduser().resolve())]
    elif args.episode != "default":
        command += ["--manifest", str(isolated_dir / "codex-image-jobs.json")]
    if args.output:
        command += ["--output", str(args.output.expanduser().resolve())]
    elif args.episode != "default":
        command += ["--output", str(isolated_dir / "storyboard.json")]
    if args.asset_set:
        command += ["--asset-set", args.asset_set]
    if args.character_reference:
        command += [
            "--character-reference",
            str(args.character_reference.expanduser().resolve()),
        ]

    if args.mode in {"generate", "full"}:
        command.append("--generate")
        if args.generator == "api":
            command.append("--apply")
    if args.mode == "full" and args.generator == "api":
        command.append("--render")
    if args.force:
        command.append("--force")

    run(command, project)
    generated_storyboard = (
        args.output.expanduser().resolve()
        if args.output
        else (
            isolated_dir / "storyboard.json"
            if args.episode != "default"
            else (
                project / "storyboard.json"
                if args.generator == "api" and args.mode in {"generate", "full"}
                else project / "storyboard.generated.json"
            )
        )
    )
    if args.mode == "plan":
        print(f"Prepared dynamic storyboard plan: {generated_storyboard}")
    elif args.generator == "codex":
        generated_manifest = (
            args.manifest.expanduser().resolve()
            if args.manifest
            else (
                isolated_dir / "codex-image-jobs.json"
                if args.episode != "default"
                else project / "codex-image-jobs.json"
            )
        )
        print(
            "Prepared Codex Image2 jobs without an API key. "
            f"Generate the dependency stages in {generated_manifest}, copy each master to its "
            "output_master path, then run --mode import and render the episode storyboard."
        )
    elif args.mode == "generate":
        print(f"Generated storyboard: {generated_storyboard}")
    else:
        print(f"Rendered silent video: {project / 'out' / args.episode / 'silent.mp4'}")


if __name__ == "__main__":
    main()
