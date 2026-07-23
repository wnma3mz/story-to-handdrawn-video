# Natural Motion SOP

Use this reference for every still-image story render. The renderer uses a fixed motion vocabulary; unsupported names must fail validation instead of silently becoming a hold.

## Supported motions

| Motion | Intended use |
| --- | --- |
| `hold` | Dense evidence, diagrams, or a needed reading pause |
| `push_soft` | Quiet emphasis on a centered clue or reaction |
| `push_left` | Emphasis on a subject in the left focal region |
| `push_right` | Emphasis on a subject in the right focal region |
| `pull_soft` | A restrained reveal from detail to relationship |
| `pan_left` | A wide environment whose reading direction moves left |
| `pan_right` | A wide environment whose reading direction moves right |

Do not use generic `push` or `pull`. Do not add aliases only to make a planned timeline pass.

## Planning

1. Give each scene one narrative job and one focal region.
2. Let durations follow narration and clue-reading time rather than an equal grid.
3. Merge adjacent uses of the same image into one continuous interval.
4. Avoid three consecutive strong moves in the same direction.
5. Keep roughly 25–50% of the episode visually settled with `hold`, `push_soft`, or `pull_soft`, adjusted for story density.
6. Keep the focal subject and every meaningful mark inside the safe border at the start, midpoint, and endpoint.

Recommended temporal shape:

- Stable head: 8–15% of the scene.
- Eased movement: 65–80%.
- Stable tail: 10–20%.
- Crossfade: 0.5–0.9 seconds only when time, place, or mental state changes.

## Validation order

1. Run the auxiliary motion-timeline audit.
2. Run the renderer's own storyboard validator against the exact episode-local storyboard that will render.
3. Require both checks to pass before preview rendering.
4. Preserve failed reports and fix the episode timeline. Never weaken the renderer validator or its allowed vocabulary.
5. Render an isolated preview before a formal silent master.
6. Inspect order, midpoint, endpoint, and every transition at normal speed.
7. Fully decode the preview and verify duration, frame rate, resolution, and absence of unintended audio.

A threshold-based planning audit is not proof that the renderer accepts the same motion names. The episode-local storyboard, renderer source, and validator must agree.
