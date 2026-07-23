#!/usr/bin/env python3
"""Mechanically normalize a semantic-pass illustration onto an exact-white canvas.

This script performs only whole-frame operations:

1. turn pixels whose three RGB channels are all near white into exact white;
2. uniformly resize the complete source frame without cropping;
3. center it on a new exact-white RGB canvas;
4. repeat the near-white normalization after interpolation.

It is not a semantic repair tool. Preserve and review the untouched generated
original before using this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import tempfile
import zlib
from pathlib import Path

import numpy as np
import PIL
from PIL import Image


def parse_size(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("size must look like WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size dimensions must be positive")
    return width, height


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_near_white(image: Image.Image, threshold: int) -> tuple[Image.Image, int]:
    array = np.asarray(image).copy()
    mask = np.all(array >= threshold, axis=2)
    changed = int(np.count_nonzero(mask & np.any(array != 255, axis=2)))
    array[mask] = 255
    return Image.fromarray(array, mode="RGB"), changed


def install_new_file_atomically(temp_path: Path, output_path: Path) -> None:
    """Publish a completed same-filesystem temp file without overwriting."""
    try:
        os.link(temp_path, output_path)
    except FileExistsError as exc:
        raise FileExistsError(f"refusing to overwrite existing file: {output_path}") from exc
    finally:
        temp_path.unlink(missing_ok=True)


def write_new_bytes_atomically(output_path: Path, content: bytes) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    install_new_file_atomically(temp_path, output_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--canvas-size", type=parse_size, default=(1254, 1254))
    parser.add_argument("--inner-size", type=parse_size, default=(940, 940))
    parser.add_argument("--near-white-threshold", type=int, default=245)
    parser.add_argument("--min-outer-padding", type=int, default=126)
    parser.add_argument("--json-report", type=Path)
    args = parser.parse_args()

    if not 245 <= args.near_white_threshold <= 255:
        raise ValueError("near-white threshold must be between 245 and 255")
    if args.min_outer_padding < 0:
        raise ValueError("minimum outer padding must be non-negative")
    if not args.input.is_file():
        raise FileNotFoundError(args.input)

    input_resolved = args.input.resolve()
    output_resolved = args.output.resolve()
    if input_resolved == output_resolved:
        raise ValueError("input and output paths must differ")
    if args.json_report:
        report_resolved = args.json_report.resolve()
        if report_resolved in {input_resolved, output_resolved}:
            raise ValueError("JSON report path must differ from input and output")
        if args.json_report.exists():
            raise FileExistsError(
                f"refusing to overwrite existing JSON report: {args.json_report}"
            )
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {args.output}")

    source = Image.open(args.input)
    if source.format != "PNG":
        raise ValueError(f"input must be PNG, got {source.format}")
    if source.mode != "RGB":
        raise ValueError(f"input must already be RGB, got {source.mode}")
    source.load()
    normalized_source, source_changed = normalize_near_white(
        source, args.near_white_threshold
    )

    inner_width, inner_height = args.inner_size
    scale = min(
        inner_width / normalized_source.width,
        inner_height / normalized_source.height,
    )
    if scale > 1:
        raise ValueError("refusing to upscale the semantic-pass source")
    resized_size = (
        max(1, round(normalized_source.width * scale)),
        max(1, round(normalized_source.height * scale)),
    )
    resized = normalized_source.resize(resized_size, Image.Resampling.LANCZOS)
    normalized_resized, resized_changed = normalize_near_white(
        resized, args.near_white_threshold
    )

    canvas_width, canvas_height = args.canvas_size
    if resized_size[0] > canvas_width or resized_size[1] > canvas_height:
        raise ValueError("inner size does not fit on the requested canvas")
    horizontal_padding = canvas_width - resized_size[0]
    vertical_padding = canvas_height - resized_size[1]
    if (
        horizontal_padding // 2 < args.min_outer_padding
        or horizontal_padding - horizontal_padding // 2 < args.min_outer_padding
        or vertical_padding // 2 < args.min_outer_padding
        or vertical_padding - vertical_padding // 2 < args.min_outer_padding
    ):
        raise ValueError(
            "resized full frame would not preserve the requested minimum outer padding"
        )
    offset = (
        (canvas_width - resized_size[0]) // 2,
        (canvas_height - resized_size[1]) // 2,
    )
    canvas = Image.new("RGB", args.canvas_size, (255, 255, 255))
    canvas.paste(normalized_resized, offset)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{args.output.name}.",
        suffix=".png",
        dir=args.output.parent,
        delete=False,
    ) as handle:
        temp_output = Path(handle.name)
    try:
        canvas.save(temp_output, format="PNG")
        install_new_file_atomically(temp_output, args.output)
    finally:
        temp_output.unlink(missing_ok=True)

    report = {
        "schema_version": 1,
        "operation": "whole_frame_near_white_normalize_uniform_scale_center",
        "input": str(args.input),
        "input_sha256": sha256_file(args.input),
        "input_size": list(source.size),
        "input_mode_after_decode": "RGB",
        "near_white_threshold_all_channels_gte": args.near_white_threshold,
        "semantic_review_required_before_normalization": True,
        "near_white_pixels_changed_before_resize": source_changed,
        "resampling": "PIL.Image.Resampling.LANCZOS",
        "inner_box": list(args.inner_size),
        "resized_size": list(resized_size),
        "near_white_pixels_changed_after_resize": resized_changed,
        "canvas_size": list(args.canvas_size),
        "canvas_mode": "RGB",
        "paste_offset": list(offset),
        "minimum_outer_padding_px": args.min_outer_padding,
        "crop": False,
        "local_edit": False,
        "runtime": {
            "python": platform.python_version(),
            "pillow": PIL.__version__,
            "numpy": np.__version__,
            "zlib": zlib.ZLIB_VERSION,
        },
        "output": str(args.output),
        "output_sha256": sha256_file(args.output),
    }
    if args.json_report:
        write_new_bytes_atomically(
            args.json_report,
            (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )

    print(
        f"NORMALIZED {args.input} -> {args.output} | "
        f"resized={resized_size[0]}x{resized_size[1]} | "
        f"offset={offset[0]},{offset[1]} | sha256={report['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
