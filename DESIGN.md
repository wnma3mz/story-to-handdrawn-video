# Rendering contract

## Canvas

- 1080×1440, 30fps, white background
- Captions stay in the upper safe area
- Illustrations use `object-fit: contain`; never crop with `cover`

## Motion

- Direct-cut mode: `text → bw_full → color`
- Every layer reveals from left to right
- Page-flip mode: `text → color`, followed by a left-bound 3D page turn
- No camera shake, bounce, narration, or text-synchronized music

## Assets

- Uploaded masters are copied into a content-addressed generated directory
- Caption, black-and-white, and color plates share aligned canvases
- Generated assets and rendered videos are disposable runtime outputs

## Visual style

- Flat white paper
- Uneven felt-tip outlines and sparse wax-crayon color
- Generous negative space
- No realistic shading, glossy gradients, watermark, or paper texture
