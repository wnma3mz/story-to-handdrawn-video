---
name: story-to-handdrawn-video
description: Convert Chinese story copy or ordered local images into a finished illustrated story video in either 3:4 hand-drawn diary mode or 16:9 monochrome historical motion-comic mode, with safe framing, natural motion, continuous narration, an audible cover, and delivery QC. Use for one-off stories, historical storytelling, mystery and case-file series, or continuity-sensitive episodic production from storyboard and image generation through final validation.
---

# Story to Hand-drawn Video

Use this skill as a complete editorial pipeline. Keep story-specific names, voices, timings, cover copy, and colors in configuration; keep scripts reusable.

## Required references

Read `references/audio-cover-sop.md` completely whenever narration or a release cover is requested.

Read `references/ink-comic-sop.md` completely whenever `--visual-mode ink-comic` is requested or a story needs full-screen 16:9 monochrome historical-comic treatment.

## Choose the visual mode

- Use `diary` for intimate recollection, family stories, simple fables, and uploaded illustrated pages. Keep the established 3:4 white-page text-and-picture composition.
- Use `ink-comic` for historical narrative, mystery, ensemble drama, institutional explanation, geography, or long-form storytelling. Render full-screen 16:9 panels, code subtitles at the bottom, and reserve selective color for one active clue.
- Do not convert an existing series between modes without first rendering a representative 45–60 second pilot.

## Workflow

1. Accept inline Chinese text, a UTF-8 file, or ordered local images. Audit source coverage before deciding episode count.
2. For a series, freeze a continuity bible: chronology, recurring character appearance, world state, object ownership, visual style, aspect ratio, caption rules, and narrator intent.
3. Preserve meaning and chronology. Use one complete sentence per beat by default; split only at natural narrative turns. Distinguish an editorial visual interval from a machine subtitle scene: when one planned illustration supports several spoken sentences, expand it into one machine scene per actual TTS/VTT sentence, reuse the same asset, and carry one continuous motion path across the interval without image fade or transform reset. For an explicitly planned episode, keep one non-empty source line per scene, create a complete consecutive scene-keyed visual plan, and pass `--scene-contract`. Put the full spoken thought in the source line and a shorter 1–3 line draft screen copy in `caption`; every machine entry also needs `duration_sec` within 2–15 seconds. In `ink-comic`, treat that short copy only as a planning summary: final bottom subtitles must be replaced from the actual TTS config. Without the explicit flag, keep the established automatic splitter.
4. Generate/import illustrations. Keep all critical marks inside the safe border, use contained framing, and never crop recurring characters or clues. In `ink-comic`, classify every scene as `host`, `narrative`, `evidence`, `map`, or `title` and give it at most one accent color.
5. Assign one motivated motion per continuous image interval. Do not restart a path while the same image stays onscreen. Use settled shots as well as pushes, pulls, or directional pans whose endpoint change remains clearly visible at delivery resolution. For 16:9 `ink-comic`, use the shared motion profiles as the floor: `push_soft`/`pull_soft` change scale by at least 1.4%, active pushes/pulls by at least 2.4%, and pans traverse at least 24 delivery pixels with at least 3.2% safety zoom. Keep a stable 8–12% head and 10–16% tail and ease the middle; do not add oscillation or random drift.
6. Render and approve a visual preview first. Never start batch production before composition, subtitle-safe framing, and motion pass at normal speed.
7. Render `cover.png` from the code-based `EpisodeCover` composition. Use a deliberate non-white dominant background and exact typeset title text. Inspect long-title wrapping and reject a one- or two-character orphan line.
8. Choose the narrator from the listening relationship. A/B at least two voices on both an opening and a later explanatory/emotional passage, then freeze one profile per series.
9. Divide the episode into 3–6 genuine narrative acts. Synthesize each act once as one connected waveform. Keep its internal breath and timing intact.
10. Use VTT cues only to measure scene alignment. Tune wording and punctuation first, then the whole-group start, then at most ±5% whole-group tempo. Never split or independently stretch sentences.
11. In `ink-comic`, make the final voiceover config the subtitle source of truth. Run `scripts/apply_verbatim_subtitles.py`; require every bottom subtitle to equal the actual scene-level TTS sentence and appear on the first frame of that cue's machine scene, without a decorative fade-in delay. Keep the former short copy only as `summary_text` for an optional non-subtitle card. Render the final `picture_silent.mp4` only after this step.
12. Build the lossless narration master, no-cover voiced master, and audible-cover release with `scripts/build_story_audio.py`.
13. Run `scripts/audit_story_delivery.py`, then listen at normal speed across every group boundary and representative visual transition. Automated PASS never replaces listening.
14. Version every material revision and report scene count, duration, output paths, voice profile, cover status, and QC evidence.

## Picture commands

Plan text without image generation:

```bash
python3 scripts/run_story_video.py --input /absolute/story.txt --title "故事标题" --mode plan
```

Prepare Codex Image2 jobs, import, render, and create a non-white cover:

```bash
python3 scripts/run_story_video.py \
  --input /absolute/story.txt \
  --title "第一章｜故事标题" \
  --series-title "系列名 · 手绘动画" \
  --episode-number 1 \
  --cover-background '#5E7468' \
  --visual-plan /absolute/episode/visual-plan.json \
  --scene-contract \
  --output /absolute/episode/storyboard.json \
  --manifest /absolute/episode/codex-image-jobs.json \
  --mode generate
python3 scripts/run_story_video.py --mode import
python3 scripts/run_story_video.py --mode render
npm run render:cover
```

For a full-screen historical motion comic, add:

```bash
python3 scripts/run_story_video.py \
  --input /absolute/story.txt \
  --title "风篇｜劣童案" \
  --visual-mode ink-comic \
  --text-mode font \
  --visual-plan /absolute/episode/visual-plan.json \
  --scene-contract \
  --output /absolute/episode/storyboard.json \
  --manifest /absolute/episode/codex-image-jobs.json \
  --mode generate
```

Uploaded-image preview or final:

```bash
python3 scripts/run_story_video.py --images /absolute/01.jpg /absolute/02.jpg --mode preview
python3 scripts/run_story_video.py --images /absolute/01.jpg /absolute/02.jpg --mode full
```

Use `--transition cut|page-flip`, `--layout auto|composite|full`, `--asset-set`, and `--character-reference` as needed. Reuse a reviewed character reference across episodes.

When episodes are prepared in parallel, never reuse the default generated storyboard path. Pair each episode-specific `--output` with its own `--manifest`; the manifest binds that exact storyboard for later import.

## Narration and release commands

Copy `examples/voiceover.example.json`, then replace its group text, scene IDs, start times, voice, and cover title. Run:

```bash
python3 scripts/build_story_audio.py \
  --storyboard storyboard.json \
  --picture out/picture_silent.mp4 \
  --cover out/cover.png \
  --config /absolute/voiceover.json \
  --output-dir out/voiceover/v01
```

Each `speech_text` must yield exactly one VTT cue per `scene_id`. If sync is outside the configured limit, revise the episode config and regenerate. Do not modify the audio by sentence.

For `ink-comic`, freeze the voiceover wording, apply it verbatim to the subtitle field, validate, and then render the final silent picture:

```bash
python3 scripts/apply_verbatim_subtitles.py \
  --storyboard storyboard.json \
  --config /absolute/voiceover.json
npm run check
npm run render
```

`npm run check` also runs `scripts/audit-motion-storyboard.mjs`. It must confirm contiguous progress, fixed asset/motion/focus inside every repeated-image interval, and the minimum endpoint scale or pan travel above. For the representative preview, extract the first, midpoint, and last settled frame of at least one push/pull and one pan; reject a path that passes numeric checks but still reads as static, crops an edge, or calls attention to the renderer at normal speed.

Audit:

```bash
python3 scripts/audit_story_delivery.py \
  out/voiceover/v01/episode_release_with_cover.mp4 \
  --master out/voiceover/v01/narration-master.wav \
  --build out/voiceover/v01/build.json \
  --sync-map out/voiceover/v01/sync-map.json \
  --cover-duration 2.7 \
  --expect-width 1080 --expect-height 1440 --expect-fps 30/1
```

## Hard rules

- Do not use one TTS request per shot with padded silence.
- Do not synthesize connected prose and later cut, trim, or time-stretch every sentence.
- Keep `group_internal_cut_count = 0`, `sentence_level_tempo_variants = 0`, and whole-group tempo within `0.95..1.05`.
- Keep ordinary group gaps around `0.35..0.8s`; reject repeated speak–silence–restart rhythm.
- Keep primary semantic starts within `±0.6s` normally; `±0.8s` is a justified hard ceiling.
- Keep the cover audible and visually non-white. The story picture and story audio must start at exactly the same post-cover timestamp.
- Keep four separate artifacts: silent picture, narration WAV, no-cover voiced MP4, and cover release MP4.
- Never batch later episodes until one representative episode passes picture, listening, sync, cover, and technical gates.
- In `ink-comic`, never generate subtitles, large calligraphy, labels, seals, or exact title text inside raster art; render them in code.
- In `ink-comic`, the bottom subtitle is a transcript, not a synopsis. It must match the exact final TTS sentence for that scene. Put summaries, hooks, and keywords in a visibly different case card, label, or glyph.
- In `ink-comic`, keep 90–95% of a scene monochrome and color only one clue, boundary, flame, seal, or host identifier.
- Do not use the host on every beat. Return to the host only for a true act change, explanation, recap, or question.
- Do not accept an episode where descriptive motion notes silently collapse into `push_soft`. The compiled motion vocabulary must preserve motivated `push`, `pull`, and directional `pan` changes from the storyboard; review the motion-audit rows before rendering.
- A subtitle change inside a repeated-image interval must not fade the plate, reset its transform, change focus, or restart easing. Only the first machine scene of a new visual interval may use the brief image fade.

## Output contract

- `out/picture_silent.mp4`: approved H.264 silent picture master, 1080×1440 in `diary` or 1920×1080 in `ink-comic`.
- `out/cover.png`: exact code-typeset, non-white cover still.
- `out/voiceover/<version>/narration-master.wav`: 48 kHz, 24-bit PCM, mono narration timeline.
- `out/voiceover/<version>/episode_with_voiceover.mp4`: no-cover archive/review master.
- `out/voiceover/<version>/episode_release_with_cover.mp4`: H.264/AAC public release with audible cover.
- `build.json`, `sync-map.json`, and QC report: reproducibility and acceptance evidence.
