# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Add a reusable continuous-narration and audible-cover release workflow:
  connected TTS groups, VTT-based semantic sync, configurable narrator profiles,
  a 2.7-second non-white code-typeset cover with title audio, separate picture /
  narration / voiced / release artifacts, and repeatable delivery QC.
- Add acoustic-silence, zero-internal-cut, whole-group-tempo, cover audibility,
  first-frame, same-offset, loudness, and full-decode gates, plus the documented
  failure record that makes the accepted workflow portable across stories.
- Accept an episode-specific `--character-reference-prompt` so a new reference
  sheet can stay narrowly scoped while the full continuity lock remains active.
- Add a planning-only `--allow-missing-assets` storyboard validation mode; strict
  asset existence and dimension checks remain the default.

### Fixed

- Preserve every copied picture packet in the no-cover voiced master when the
  narration and frame-grid durations differ by less than one frame.

## [1.0.0] - 2026-07-21

### Added

- Initial open-source release of `story-to-handdrawn-video`.
- Remotion renderer (`src/`): story-text beats, uploaded-page cropping,
  left-to-right `text → bw → color` reveals, page-flip transition,
  safe contained framing, silent MP4 output (final 1080×1440, preview 720×960).
- Unified CLI entry `scripts/run_story_video.py` with plan / generate /
  import / render / preview / full modes and Codex Image2 + OpenAI API generators.
- Distributable agent skill in `skill-package/story-to-handdrawn-video/`
  with `STORY_VIDEO_PROJECT` discovery and upward directory walk.
- Example story, style references, and the Ma Shan Zheng font (OFL).

[Unreleased]: https://github.com/gnipbao/story-to-handdrawn-video/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/gnipbao/story-to-handdrawn-video/releases/tag/v1.0.0
