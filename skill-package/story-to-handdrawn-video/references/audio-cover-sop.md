# Continuous Narration and Release Cover SOP

## Delivery contract

Keep these artifacts separate and versioned:

1. approved `picture_silent.mp4`;
2. lossless `narration-master.wav` on the picture timeline;
3. `episode_with_voiceover.mp4` without a cover, for sync review;
4. `episode_release_with_cover.mp4` with a real audible opening interval.

Use a series config for narrator identity, listening relationship, visual locks, cover template, loudness, and codecs. Use an episode config for title, narration groups, scene timing, cover copy, and content-specific pronunciation. Re-evaluate voice samples when changing genre or audience.

## Choose and freeze a voice

Test at least two 20–40 second samples with identical text and timing. Include an opening and a later explanatory or emotional passage. Judge whether a listener wants to continue, clarity of names/numbers, sentence-to-sentence continuity, and fatigue. Reject advertising, newsreader, cartoon, or synthetic sing-song delivery unless the format requires it.

Record backend, voice ID, rate, pitch, volume, pronunciation choices, and intent. Do not direct emotion with shot-by-shot rate or pitch changes.

The bundled example uses the warm female `zh-CN-XiaoxiaoNeural` as a useful
starting profile for intimate or allegorical Chinese narration. Treat that as a
configurable strategy, not a gender rule: keep `voice`, `rate`, `pitch`, and
`volume` in configuration, and run the same normal-speed A/B gate again when a
new story, genre, audience, or listening relationship calls for another voice.

## Continuous narration groups

Organize an episode into 3–6 genuine acts. Submit each full act to TTS once. Save the raw media and its VTT. Remove only codec padding outside the group. Keep every internal pause. Place the whole waveform once on the picture timeline.

Required invariants:

```text
group_internal_cut_count = 0
sentence_level_tempo_variants = 0
whole_group_tempo in [0.95, 1.05]
```

Normal group gaps are 0.35–0.8 seconds. Do not produce the repeated pattern “speak, long silence, restart.” Treat that planned waveform gap only as a layout constraint: TTS may include low-level sentence-tail silence, so also measure the finished master acoustically at about -42 dB. A valid plan gap does not prove that the audible pause is valid.

## Semantic synchronization

VTT is a ruler, not a cutting guide. For each cue record target scene start, actual group-relative start, signed error, and bridge/primary status. Primary cues should normally land within ±0.6 seconds; ±0.8 seconds needs a narrative reason.

Fix drift in this order:

1. Adjust wording inside the same scene sentence: add already-visible detail when the next cue arrives too early, remove repetition when it arrives late.
2. Adjust punctuation without adding an unassigned bridge sentence.
3. Move the entire narration group while preserving its neighboring gap.
4. Apply one uniform group tempo change no larger than 5%.
5. Regenerate, remeasure, and listen through the second half for cumulative drift.

## Cover and release timeline

The release cover is an editorial interval, not merely a PNG beside the video.

- Use a deliberate non-white dominant field by default.
- Keep series name, episode/chapter label, number, title, and focal image inside safe margins.
- Render exact glyphs in code; generated art supplies imagery, not critical title text.
- Balance long title lines deliberately. Reject automatic wraps that leave a one- or two-character orphan line; use an explicit break or a deterministic code-based balancer, then inspect the rendered cover.
- Keep one series template while changing copy and focal art.
- Use about 2–3 seconds with a restrained eased push and stable endpoints.
- Give the interval audible title audio in the series voice.
- Extract and inspect the actual first frame of the release.

Preferred non-overlapping timeline:

```text
cover video + title audio: 0.000 -> cover_duration
main video start:          cover_duration
story audio start:         cover_duration
start delta:               0.000
```

If a crossfade is intentionally used, account for the overlap in both picture and audio. Never shift only one side.

## Mastering

House defaults:

- narration master: mono, 48 kHz, 24-bit PCM;
- integrated loudness around -16 LUFS;
- true peak no higher than -1.5 dBTP;
- release AAC: stereo, 48 kHz, 192 kb/s;
- audio/picture duration mismatch no greater than 50 ms.

Apply filtering, compression, and loudness processing consistently to the whole narration timeline. For the no-cover voiced master, copy the approved picture stream when possible. Do not end that mux with FFmpeg `-shortest`: a sub-frame audio/picture rounding difference can otherwise discard the final video packet. Let the complete picture stream determine the container duration, and keep the narration-master duration difference within 50 ms.

## Acceptance gates

- Listen at normal speed across every group boundary and representative visual transition.
- Reject clipped tails, voice resets, sentence-level gear changes, and unexplained dead air.
- Ordinary narration should default to no unplanned acoustic silence over 1.25 seconds; the longest silence is normally under 2 seconds except an approved ending. If a normal-speed human listen explicitly approves a naturally longer pause, record an episode-specific limit no higher than 1.50 seconds. Never raise the limit merely to turn a failing report green.
- Every primary sentence must substantially overlap the image that supports it.
- Full-file decode must pass; verify resolution, frame rate, stream count, 48 kHz audio, duration, and pixel format.
- Cover first-frame luma below about 200 is a useful non-white warning test, not a replacement for viewing.
- Cover mean volume should be clearly audible, commonly above -45 dB.
- Preserve build, sync, loudness, first-frame, and decode evidence beside the release.

Run `scripts/audit_story_delivery.py`, then perform the human listening gate.

## Failure record

Two approaches are prohibited because they produced audible discontinuity in a validated production:

1. One TTS request per visual shot, followed by silence padding to fill every shot. This repeatedly resets breath and cadence.
2. One connected TTS request later split into sentences, independently silence-trimmed, time-stretched, and repositioned. Timing can look precise while every boundary sounds like a gear change.

The accepted correction was to synthesize a small number of narrative acts, preserve each act as one waveform, tune prose and punctuation against VTT measurements, and move only the whole act. This rule applies across voices, episodes, and stories.

A later production exposed a second failure mode: every configured group gap passed, yet sentence-tail low-level silence plus the planned gap produced a longer acoustic pause. The correction is to keep both measurements in QC: configured group gaps for timeline construction and -42 dB acoustic silence on the mastered waveform for listening continuity. The acoustic threshold is configurable only within 0.50–1.50 seconds, defaults to 1.25 seconds, and any exception requires an explicit listening note. Do not fix this by cutting the connected group, shifting individual sentences, or laying noise under silence.

## Parallel episodic production

Parallelize episode ownership, but serialize shared manifests and final delivery folders. Before image generation, run a continuity gate for chronology, recurring appearance, location, newly introduced objects, and world state. Validate one representative episode before batching. Freeze voice, cover template, motion vocabulary, delivery codecs, and QC thresholds; change only series/episode configs for later work.
