# Reusable style profiles

Use a catalog profile by ID:

```bash
python3 scripts/run_story_video.py \
  --input /absolute/adapted-story.txt \
  --style-profile qin-bamboo-noir \
  --mode plan
```

Available profiles:

- `celadon-kiln-scroll` — celadon, craft history, material culture
- `pompeii-scratch-fresco` — Roman fresco, body and power
- `qin-bamboo-noir` — Qin-era chamber political thriller
- `luxury-food-atlas` — food history and pricing narratives
- `zhengding-blueprint` — architecture, television production design, urban renewal
- `hengdian-storyboard` — film-industry documentary storyboard
- `indigo-pearl-woodcut` — maritime labor and resource extraction
- `maoshan-letter-wash` — classical letters, landscape prose, withdrawal and duty
- `jiuzhou-cangfeng-epic` — Jiuzhou grassland, youth, war geography, and epic ensemble drama
- `tianluo-snow-noir` — Jiuzhou assassin pursuit, intimacy, betrayal, and snow-night noir

The JSON contract is defined in `../style-profile.schema.json`. A profile ID must
match its filename. Profiles inherit a structural `base_mode`; their
`style_overrides` replace the visual language without duplicating the rendering,
subtitle, narration, motion, and delivery pipeline.

Profiles may set `episode_defaults.color_grade` to one of:

- `monochrome` — neutral near-black-and-white rendering
- `warm_bronze` — restrained warm gray and aged-bronze rendering
- `snow_cinnabar` — cold snow-gray rendering with preserved cinnabar accents

The Jiuzhou profiles use `warm_bronze` for `jiuzhou-cangfeng-epic` and
`snow_cinnabar` for `tianluo-snow-noir`. A scene may override the project grade
only when the storyboard explicitly requires it.
