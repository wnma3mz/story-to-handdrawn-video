# Contributing

Thanks for your interest in improving `story-to-handdrawn-video`.

## Ground rules

- `SKILL.md` and `scripts/run_story_video.py` define the **core behavior contract** of the skill. Changes to them require a clear rationale in the pull request — drive-by refactors of the core will not be merged.
- Keep the wrapper portable: it must never depend on an author-specific absolute path. Project discovery goes through `STORY_VIDEO_PROJECT` or an upward walk from the current working directory.
- Documentation (README, examples, translations) and non-core improvements are always welcome.

## How to contribute

1. Fork the repository and create a branch from `main`.
2. Make your change. Keep diffs small and focused.
3. If you change user-facing behavior, update `README.md` (both the English and 中文 sections) and `CHANGELOG.md` under `Unreleased`.
4. Open a pull request describing the problem and the change. Link any related issue.

## Reporting issues

Open a GitHub issue with:

- What you ran (exact command, input type: story text or images).
- What you expected vs. what happened.
- Your environment: agent runtime, OS, Python and Node versions, and the renderer project you pointed `STORY_VIDEO_PROJECT` at.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
