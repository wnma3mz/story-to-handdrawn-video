#!/usr/bin/env python3
"""Build a deterministic labeled contact sheet from ordered illustration PNGs."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def default_label(path: Path) -> str:
    parent = path.parent.name
    if parent.startswith("scene-"):
        return f"Scene {parent.removeprefix('scene-')}"
    return path.stem


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="ordered PNG inputs")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--cell-width", type=int, default=300)
    parser.add_argument("--cell-height", type=int, default=330)
    parser.add_argument("--label-height", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.columns < 1:
        raise SystemExit("--columns must be at least 1")
    if args.cell_width < 1 or args.cell_height <= args.label_height:
        raise SystemExit("cell dimensions must leave positive image space")

    inputs = [path.resolve() for path in args.inputs]
    missing = [path for path in inputs if not path.is_file()]
    if missing:
        raise SystemExit("missing input: " + ", ".join(path.as_posix() for path in missing))

    rows = math.ceil(len(inputs) / args.columns)
    canvas = Image.new(
        "RGB",
        (args.columns * args.cell_width, rows * args.cell_height),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=18)
    image_box = (
        args.cell_width - 20,
        args.cell_height - args.label_height - 20,
    )

    for index, path in enumerate(inputs):
        column = index % args.columns
        row = index // args.columns
        x = column * args.cell_width
        y = row * args.cell_height
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            thumbnail = ImageOps.contain(
                image,
                image_box,
                method=Image.Resampling.LANCZOS,
            )
        image_x = x + (args.cell_width - thumbnail.width) // 2
        image_y = y + args.label_height + (
            args.cell_height - args.label_height - thumbnail.height
        ) // 2
        canvas.paste(thumbnail, (image_x, image_y))
        draw.text((x + 10, y + 6), default_label(path), fill="black", font=font)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output, format="PNG", optimize=False)
    print(f"{args.output} | {canvas.width}x{canvas.height} | {len(inputs)} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
