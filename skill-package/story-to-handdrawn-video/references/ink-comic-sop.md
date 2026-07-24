# 16:9 Monochrome Historical Motion-Comic SOP

## Visual contract

- Fill the 16:9 frame. Do not place the story inside a white diary page or reserve a fixed top copy panel.
- Draw expressive adult characters with bold black ink contours, grayscale wash depth, restrained paper grain, and readable period objects.
- Keep 90–95% of each frame black, charcoal, warm gray, and paper white.
- Assign one accent to one narrative target: vermilion for fire, seal, warning, or guilt; muted field green for land, crops, or livelihood. Do not color whole costumes or scenery.
- Keep the bottom 18% free of essential faces and clues for code-rendered subtitles.
- Add exact subtitles, case labels, chapter glyphs, dates, seals, and map labels in code. Never trust generated raster text.

## Subtitle contract

- Treat the bottom bar as a transcript. After the final voiceover wording is frozen, run `scripts/apply_verbatim_subtitles.py` so every scene `text` exactly matches its actual TTS sentence.
- Keep a short planning caption only as `summary_text`. If it appears onscreen, style it as a distinct case card, chapter label, evidence tag, or large keyword—not as a bottom subtitle.
- Do not omit a name, claim, consequence, or closing question from the transcript subtitle when it is audible.
- Set `project.subtitle_contract` to `verbatim_tts` for the final storyboard. Validation must fail if `scene.text` and final `scene.narration` differ after whitespace normalization.
- Use one terminally punctuated TTS sentence per `scene_id`. Rewrite overlong sentences before rendering; do not shrink transcript text until it becomes tiring to read.

## Scene roles

Assign one role before prompting:

| Role | Job | Default motion |
|---|---|---|
| `host` | Ask a question, explain a system, or bridge acts | hold or `push_soft` |
| `narrative` | Show a character action or consequence | directional push or restrained pan |
| `evidence` | Let the viewer inspect an object or contradiction | hold or `push_soft` |
| `map` | Explain geography, ownership, or movement | hold, gentle pull, or pan |
| `title` | Establish the case, trigram, or act | hold |

Use a recurring host sparingly. A 45–60 second pilot normally needs one host shot; a three-minute episode normally needs no more than two or three unless the format is intentionally presenter-led.

## Prompt contract

Prompt one concrete tableau per scene. State:

1. time and place;
2. required characters and locked appearance;
3. the single visible action;
4. foreground, middle ground, and background separation;
5. the one colored clue and exact accent;
6. subtitle-safe lower area;
7. exclusions: no text, photorealism, glossy 3D, anime, modern props, gore, logo, or watermark.

Allow secondary architecture to crop at the frame edge when it improves scale. Never crop the active clue, face, or gesture.

## Motion and editing

- Use one eased path per continuous image interval. Motion must be visible at normal speed without becoming the subject: in 1920×1080 delivery, soft push/pull changes scale by at least 1.4%, active push/pull by at least 2.4%, and a pan traverses at least 24 pixels while retaining at least 3.2% safety zoom. These are endpoint floors, not targets to maximize.
- Hold the first 8–12% and last 10–16% near-still and ease the middle. A subtitle-timed machine-scene boundary never resets that interval progress, focus, transform, or plate opacity.
- Match direction to the composition: push toward a face/action/clue, pull from a detail into a relationship, pan across geography or an actual path. Preserve screen direction; never alternate left/right for decoration.
- Let character scenes breathe for 6–11 seconds; evidence may hold longer when it must be read.
- Use direct cuts for cause/effect and contradictions. Use a 0.5–0.8 second fade only for time, place, memory, or act changes.
- A large low-opacity Chinese glyph may sit behind the panel as atmosphere, but never place one on every shot.
- Avoid repeated line-drawing, wipe-on, or colorization rituals. Reveal only when the act of revealing itself carries meaning.

## Acceptance

- The story remains understandable with all decorative glyphs removed.
- Every colored element is narratively justified and no scene has competing accents.
- The host explains or reframes; the host never narrates an action already visible in the adjacent scene.
- Subtitles do not cover faces, hands, evidence, or land boundaries.
- Every audible scene sentence is represented verbatim in the bottom subtitle; a manual spot check includes the opening, a consequence beat, and the final hook.
- Contact-sheet review shows a deliberate alternation of host, action, evidence, and settled frames rather than one repeating template.
- Run the motion storyboard audit before rendering. Then extract start/mid/end frames from one zoom and one pan in the representative preview; confirm measurable endpoint change, no exposed edge, no subtitle-triggered reset, and a visibly different composition at normal viewing size.
