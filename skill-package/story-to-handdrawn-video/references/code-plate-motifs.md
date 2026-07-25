# Code Plate Motif Reference

When `plate_mode=code`, each scene renders a procedural SVG illustration from one of these motifs. No image generation is needed — the renderer draws everything in code.

## Choosing a motif

Assign one motif per scene based on the emotional register of the text, not literal depiction. The motif should evoke the mood, not illustrate the narrative beat.

| Motif | Visual | Best for |
|---|---|---|
| `window` | Framed window with colored light | Looking out, longing, interior scenes |
| `desk_night` | Desk with lamp | Late-night writing, solitude, study |
| `bike` | Bicycle under sky | Youth, motion, summer memory |
| `street` | Two buildings on street | City life, neighborhood, everyday |
| `two_figures` | Two figures facing | Conversation, meeting, relationship |
| `temple_gate` | Gate with roof | History, tradition, ceremony |
| `empty_cup` | Cup on surface | Loss, emptiness, quiet reflection |
| `ghost_window` | Window with orbs | Memory, haunting, the past |
| `detour` | Curved road with obstacle | Obstacles, wrong turns, fate |
| `farewell` | Figure under sky | Parting, departure, endings |
| `abstract_wash` | Abstract color circles | Universal fallback, any mood |
| `book_lamp` | Books with lamp | Reading, knowledge, stories |

## Per-scene config

```json
{
  "01": {
    "caption": "那一年的秋天",
    "duration_sec": 12,
    "plate_mode": "code",
    "code_plate": {
      "motif": "bike",
      "background": "#FCFAF5",
      "ink": "#2C2926",
      "accents": ["#B4786E", "#7A8B7A"],
      "seed": 1
    }
  }
}
```

- `motif` (required): one of the 12 keys above
- `background`: CSS color, defaults to white / dark depending on mode
- `ink`: line color, defaults to dark gray
- `accents`: 2 accent colors for washes and fills
- `seed`: deterministic variation (defaults to scene number)

When `plate_mode` is omitted, it defaults to `raster` (existing Image2 pipeline).
