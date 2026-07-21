# Contributing

Thanks for your interest in improving `story-to-handdrawn-video`.

## Ground rules

- The **core** of this project is the renderer logic in `src/` and `scripts/`, plus the skill contract in `skill-package/story-to-handdrawn-video/` (`SKILL.md` and its wrapper). Changes to them require a clear rationale in the pull request — drive-by refactors of the core will not be merged.
- Keep the skill wrapper portable: it must never depend on an author-specific absolute path. Project discovery goes through `STORY_VIDEO_PROJECT` or an upward walk from the current working directory.
- Documentation (README, examples, translations) and non-core improvements are always welcome.

## How to contribute

1. Fork the repository and create a branch from `main`.
2. Make your change. Keep diffs small and focused.
3. If you change user-facing behavior, update `README.md` (both the 中文 and English sections) and `CHANGELOG.md` under `Unreleased`.
4. Open a pull request describing the problem and the change. Link any related issue.

## Reporting issues

Open a GitHub issue with:

- What you ran (exact command, input type: story text or images).
- What you expected vs. what happened.
- Your environment: agent runtime, OS, Python and Node versions, and the renderer project you pointed `STORY_VIDEO_PROJECT` at.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
