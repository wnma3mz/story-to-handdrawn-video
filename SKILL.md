---
name: story-to-handdrawn-video
description: Convert Chinese story copy or ordered local images into a hand-drawn diary-comic animation with handwritten captions, left-to-right black-and-white-to-color reveals, optional page-flip transitions, safe uncropped framing, and a silent Remotion picture track.
---

# Story to Hand-drawn Video

Use the project renderer through this Skill's `scripts/run_story_video.py`. Set `STORY_VIDEO_PROJECT` when the project is not the current working directory. The wrapper must not rely on an author-specific absolute path.

## Workflow

1. Accept inline Chinese story text, a UTF-8 text file, or ordered local images.
2. Preserve the user's wording. For text input, keep one complete sentence as one beat by default and split only long compound sentences at natural narrative turns.
3. For uploaded composite pages, automatically crop the handwritten caption and illustration, then derive an aligned black-and-white plate locally.
4. In direct-cut mode, keep the order `text → bw_full → color`; reveal every stage from left to right.
5. In page-flip mode, preserve the untouched uploaded master and show it statically before curling the page from the bottom-right corner. Do not add caption, black-and-white, or recoloring stages. Retain a faded version of the source page on the paper underside.
6. Keep all illustration marks inside the white safe border. Use contained framing and never `cover` cropping.
7. Produce a silent MP4. Voiceover and optional BGM are post-production tasks.
8. Report the scene count, duration, output path, and whether the result is plan-only, preview, or final.

## Uploaded images

Preview:

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "故事标题" \
  --mode preview \
  --transition cut
```

Final direct-cut render:

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "故事标题" \
  --mode full \
  --transition cut \
  --page-duration 4.4
```

Final page-flip render:

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "故事标题" \
  --mode full \
  --transition page-flip \
  --transition-sec 0.7
```

Use `--layout auto|composite|full` to control how uploaded pages are interpreted.

## Story text

Plan without generating images:

```bash
python3 scripts/run_story_video.py --input /absolute/story.txt --title "故事标题" --mode plan
```

Prepare Codex Image2 jobs, then import and render:

```bash
python3 scripts/run_story_video.py --input /absolute/story.txt --title "故事标题" --mode generate
python3 scripts/run_story_video.py --mode import
python3 scripts/run_story_video.py --mode render
```

Use `--generator codex` by default. Use `--generator api` only when the user explicitly selects the API fallback and `OPENAI_API_KEY` is available. Use `--force` only when the user explicitly wants an existing generated batch replaced.

For time jumps, ambiguous pronouns, medical scenes, or age-sensitive characters, provide a JSON visual plan keyed by two-digit scene id through `--visual-plan`.

## Output contract

- Text-story final: `<project>/out/picture_silent.mp4`
- Text-story preview: `<project>/out/picture_silent-preview.mp4`
- Uploaded-image final: `<project>/out/uploaded_picture_silent.mp4`
- Uploaded-image preview: `<project>/out/uploaded_picture_silent-preview.mp4`
- Resolution: final 1080×1440; preview 720×960
- Codec/audio: H.264, silent

Do not run a separate validation or test command unless the user explicitly requests it.
