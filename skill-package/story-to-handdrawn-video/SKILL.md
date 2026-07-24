---
name: story-to-handdrawn-video
description: Convert Chinese story copy or ordered local images into a finished illustrated story video in 3:4 hand-drawn diary, 3:4 literary essay, or 16:9 monochrome historical motion-comic mode, with safe framing, natural motion, continuous narration, an audible cover, and delivery QC. Use for one-off stories, personal essays and memoirs, historical storytelling, mystery and case-file series, or continuity-sensitive episodic production from storyboard and image generation through final validation.
---

# Story to Hand-drawn Video

Use this skill as a complete editorial pipeline. Keep story-specific names, voices, timings, cover copy, and colors in configuration; keep scripts reusable.

## Required references

Read `references/audio-cover-sop.md` completely whenever narration or a release cover is requested.
Read `references/motion-sop.md` completely before assigning motion or rendering a picture track.

Read `references/ink-comic-sop.md` completely whenever `--visual-mode ink-comic` is requested or a story needs full-screen 16:9 monochrome historical-comic treatment.

## Choose the visual mode

- Use `diary` for narrative stories, fables, and uploaded illustrated pages. Keeps the 3:4 hand-drawn diary format with text→bw→color reveal and scene-by-scene story beats.
- Use `essay` for personal essays, literary prose, memoirs, and reminiscence collections. Uses 3:4 format with text-dominant layout, soft watercolor mood illustrations instead of literal scenes, and gentle breathing zoom only. The text carries the narrative weight; images provide emotional atmosphere.
- Use `ink-comic` for historical narrative, mystery, ensemble drama, institutional explanation, geography, or long-form storytelling. Render full-screen 16:9 panels, code subtitles at the bottom, and reserve selective color for one active clue.
- Do not convert an existing series between modes without first rendering a representative 45–60 second pilot.

## Workflow

1. Accept inline Chinese text, a UTF-8 file, or ordered local images. Audit source coverage before deciding episode count.
2. For a series, freeze a continuity bible: chronology, recurring character appearance, world state, object ownership, visual style, aspect ratio, caption rules, and narrator intent.
3. Preserve meaning and chronology. Use one complete sentence per beat by default; split only at natural narrative turns. Distinguish an editorial visual interval from a machine subtitle scene: when one planned illustration supports several spoken sentences, expand it into one machine scene per actual TTS/VTT sentence, reuse the same asset, and carry one continuous motion path across the interval without image fade or transform reset. For an explicitly planned episode, keep one non-empty source line per scene, create a complete consecutive two-digit scene-keyed visual plan, and pass `--scene-contract`. Put the full spoken thought in the source line and a shorter 1–3 line draft screen copy in `caption`; every machine entry also needs `duration_sec` within 2–15 seconds. In `ink-comic`, treat that short copy only as a planning summary: final bottom subtitles must be replaced from the actual TTS config. Without the explicit flag, keep the established automatic splitter.
4. Generate/import illustrations. Inspect every original at full resolution and preserve rejected attempts with reasons. Keep all critical marks inside the safe border, use contained framing, and never crop recurring characters or clues. In `ink-comic`, classify every scene as `host`, `narrative`, `evidence`, `map`, or `title` and give it at most one accent color. For white-field masters, run `scripts/audit-illustration-masters.py` to prove the final border with the exact bounding box of every pixel that is not `#FFFFFF`; darkness, alpha, and near-white thresholds are rough diagnostics only because they can miss pale water, sand, roofs, and antialiased marks. Unless the project specifies a stricter value, keep every meaningful mark at least 10% of the canvas away from every edge. If a semantically approved original has only a generated near-white field, preserve it unchanged, then use `scripts/normalize-illustration-master.py` for whole-frame normalization, uniform downscale and exact-white centering. Never use normalization to rescue a cropped, semantically wrong or identity-leaking image; keep input/output/report paths distinct and rerun the exact audit on the derivative.
5. Assign one motivated motion per continuous image interval. Do not restart a path while the same image stays onscreen. In `essay` mode, use only `hold` or `push_soft` — gentle breathing zoom that never distracts from the text. In diary mode, use settled shots as well as pushes, pulls, or directional pans whose endpoint change remains clearly visible at delivery resolution. For 16:9 `ink-comic`, use the shared motion profiles as the floor: `push_soft`/`pull_soft` change scale by at least 1.4%, active pushes/pulls by at least 2.4%, and pans traverse at least 24 delivery pixels with at least 3.2% safety zoom. Keep a stable 8–12% head and 10–16% tail and ease the middle; do not add oscillation or random drift. Run `scripts/audit_motion_timeline.py` and the renderer's own validator against the exact episode-local storyboard before preview rendering. The audit accepts only `hold`, `push_soft`, `push_left`, `push_right`, `pull_soft`, `pan_left`, and `pan_right`; never substitute generic `push` or `pull`.
6. Render and approve a visual preview first. Never start batch production before composition, subtitle-safe framing, and motion pass at normal speed. Never overwrite it during audio work.
7. Render `cover.png` from the code-based `EpisodeCover` composition. Use a deliberate non-white dominant background and exact typeset title text. Inspect long-title wrapping and reject a one- or two-character orphan line.
8. Choose the narrator from the listening relationship. A/B at least two voices on both an opening and a later explanatory/emotional passage, then freeze one profile per series. The example starts with the warm female `zh-CN-XiaoxiaoNeural` for intimate or allegorical Chinese narration, but voice gender and ID remain configurable; re-evaluate them when the genre, audience, or story relationship changes.
9. Divide the episode into 3–6 genuine narrative acts. Synthesize each act once as one connected waveform. Keep its internal breath and timing intact.
10. Use VTT cues only to measure scene alignment. Tune wording and punctuation first, then the whole-group start, then at most ±5% whole-group tempo. Never split or independently stretch sentences.
11. In `ink-comic`, make the final voiceover config the subtitle source of truth. Run `scripts/apply_verbatim_subtitles.py`; require every bottom subtitle to equal the actual scene-level TTS sentence and appear on the first frame of that cue's machine scene, without a decorative fade-in delay. Keep the former short copy only as `summary_text` for an optional non-subtitle card. Render the final `picture_silent.mp4` only after this step.
12. Build the lossless narration master, no-cover voiced master, and audible-cover release with `scripts/build_story_audio.py`.
13. Run `scripts/audit_story_delivery.py`, then listen at normal speed across every group boundary and representative visual transition. Inspect both planned group gaps and measured acoustic silence; automated PASS never replaces listening.
14. Version every material revision and report scene count, duration, output paths, voice profile, cover status, and QC evidence.

## Picture commands

Normalize a full-resolution semantic PASS without cropping or local edits:

```bash
python3 scripts/normalize-illustration-master.py \
  /absolute/episode/candidates/scene-01/attempt-01-original.png \
  /absolute/episode/candidates/scene-01/candidate-final.png \
  --json-report /absolute/episode/candidates/scene-01/candidate-final-normalization.json
```

Audit approved illustration candidates before import:

```bash
python3 scripts/audit-illustration-masters.py \
  '/absolute/episode/candidates/scene-*/candidate-*.png' \
  --json-report /absolute/episode/review/illustration-gate.json
```

Audit the episode-local motion timeline before import or preview:

```bash
python3 scripts/audit_motion_timeline.py \
  /absolute/episode/motion-timeline.tsv \
  --expected-duration 266.061
node scripts/validate-storyboard.mjs /absolute/episode/storyboard.json
```

The numeric duration above is illustrative; pass the episode's actual planned duration. Both checks must pass. The Python audit deliberately shares the renderer's exact seven-motion vocabulary so an unsupported generic label cannot receive an auxiliary `PASS`.
Before illustrations exist, `node scripts/validate-storyboard.mjs --allow-missing-assets /absolute/episode/storyboard.json` may be used as a planning-only structural gate. Remove the flag for import, preview, and delivery validation so missing assets and their dimensions are checked.

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
  --character-reference-prompt /absolute/episode/new-character-brief.txt \
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

Use `--transition cut|page-flip`, `--layout auto|composite|full`, `--asset-set`, and `--character-reference` as needed. Reuse a reviewed character reference across episodes. When only a subset of the episode continuity cast needs a new reference sheet, put that narrow cast-and-pose brief in `--character-reference-prompt`; keep the broader `--character-lock` intact as context, but do not let it silently expand the sheet.

When episodes are prepared in parallel, never reuse the default generated storyboard path. Pair each episode-specific `--output` with its own `--manifest`; the manifest binds that exact storyboard for later import.

## Narration and release commands

Copy `examples/voiceover.example.json`, then replace its group text, scene IDs, start times, voice, and cover title. Run:

```bash
python3 scripts/build_story_audio.py \
  --storyboard storyboard.json \
  --episode <slug> \
  --config /absolute/voiceover.json
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
  out/<episode>/voiced/release.mp4 \
  --master out/<episode>/voiced/narration-master.wav \
  --build .work/<episode>/work/build.json \
  --sync-map .work/<episode>/work/sync-map.json \
  --cover-duration 2.7 \
  --expect-width 1080 --expect-height 1440 --expect-fps 30/1
```

## Hard rules

- Do not use one TTS request per shot with padded silence.
- Do not synthesize connected prose and later cut, trim, or time-stretch every sentence.
- Keep `group_internal_cut_count = 0`, `sentence_level_tempo_variants = 0`, and whole-group tempo within `0.95..1.05`.
- Keep ordinary group gaps around `0.35..0.8s`; reject repeated speak–silence–restart rhythm.
- Measure the mastered waveform as well as the planned gaps. Default to no unplanned acoustic silence over `1.25s`; a listened-and-recorded episode exception may rise only to `1.50s` via `--ordinary-pause-limit`.
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

- `out/<episode>/silent.mp4`: approved H.264 silent picture master, 1080×1440 in `diary`/`essay` or 1920×1080 in `ink-comic`.
- `out/<episode>/cover.png`: exact code-typeset, non-white cover still.
- `out/<episode>/voiced/narration-master.wav`: 48 kHz, 24-bit PCM, mono narration timeline.
- `out/<episode>/voiced/preview.mp4`: no-cover review master.
- `out/<episode>/voiced/release.mp4`: H.264/AAC public release with audible cover.
- `out/releases/<episode>.mp4`: flat quick-find copy of the public release.
- `.work/<episode>/`: intermediate TTS groups, VTT, build.json, sync-map.json — not committed.
