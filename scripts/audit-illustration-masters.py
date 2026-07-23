#!/usr/bin/env python3
"""Audit exact white-field and margin requirements for illustration PNG masters."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops, UnidentifiedImageError
except ImportError as exc:  # pragma: no cover - depends on the runtime environment
    raise SystemExit(
        "ERROR Pillow is required; install it with: python3 -m pip install Pillow"
    ) from exc


WHITE = (255, 255, 255)
EXPECTED_MODE = "RGB"
EXPECTED_FORMAT = "PNG"
DEFAULT_EXPECTED_SIZE = (1254, 1254)
DEFAULT_MARGIN_PERCENT = 10


def parse_size(value: str) -> tuple[int, int]:
    """Parse WIDTHxHEIGHT into a positive integer pair."""
    normalized = value.lower().replace("×", "x")
    parts = normalized.split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT, for example 1254x1254")
    try:
        width, height = (int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("width and height must be integers") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("width and height must be positive")
    return width, height


def display_path(path: Path, cwd: Path) -> str:
    """Return a stable, readable path relative to cwd when possible."""
    try:
        return path.relative_to(cwd).as_posix()
    except ValueError:
        return path.as_posix()


def pngs_below(directory: Path) -> list[Path]:
    return sorted(
        (
            path.resolve()
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() == ".png"
        ),
        key=lambda path: path.as_posix(),
    )


def resolve_inputs(tokens: list[str], cwd: Path) -> tuple[list[Path], list[dict[str, str]]]:
    """Resolve explicit files, recursive directories, and Python-style globs."""
    collected: dict[str, Path] = {}
    errors: list[dict[str, str]] = []

    for token in tokens:
        expanded_token = str(Path(token).expanduser())
        if glob.has_magic(expanded_token):
            matches = sorted(
                (Path(match).expanduser() for match in glob.glob(expanded_token, recursive=True)),
                key=lambda path: path.as_posix(),
            )
            if not matches:
                errors.append({"input": token, "reason": "glob_matched_nothing"})
                continue
            token_pngs: list[Path] = []
            for match in matches:
                if match.is_dir():
                    token_pngs.extend(pngs_below(match))
                elif match.is_file() and match.suffix.lower() == ".png":
                    token_pngs.append(match.resolve())
            if not token_pngs:
                errors.append({"input": token, "reason": "glob_matched_no_png_files"})
                continue
            for path in token_pngs:
                collected[path.as_posix()] = path
            continue

        path = Path(expanded_token)
        if not path.is_absolute():
            path = cwd / path
        if not path.exists():
            errors.append({"input": token, "reason": "path_does_not_exist"})
        elif path.is_dir():
            token_pngs = pngs_below(path)
            if not token_pngs:
                errors.append({"input": token, "reason": "directory_contains_no_png_files"})
            for png in token_pngs:
                collected[png.as_posix()] = png
        elif not path.is_file():
            errors.append({"input": token, "reason": "path_is_not_a_regular_file"})
        elif path.suffix.lower() != ".png":
            errors.append({"input": token, "reason": "path_is_not_a_png"})
        else:
            resolved = path.resolve()
            collected[resolved.as_posix()] = resolved

    return [collected[key] for key in sorted(collected)], errors


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def border_findings(image: Image.Image) -> tuple[int, list[list[int]]]:
    """Count unique non-white pixels on the outermost one-pixel border."""
    width, height = image.size
    pixels = image.load()
    positions: list[tuple[int, int]] = []
    positions.extend((x, 0) for x in range(width))
    if height > 1:
        positions.extend((x, height - 1) for x in range(width))
    positions.extend((0, y) for y in range(1, max(1, height - 1)))
    if width > 1:
        positions.extend((width - 1, y) for y in range(1, max(1, height - 1)))

    count = 0
    samples: list[list[int]] = []
    for x, y in positions:
        if pixels[x, y] != WHITE:
            count += 1
            if len(samples) < 8:
                samples.append([x, y])
    return count, samples


def exact_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Return Pillow's exclusive bbox for every pixel not exactly #FFFFFF."""
    white_field = Image.new(EXPECTED_MODE, image.size, WHITE)
    return ImageChops.difference(image, white_field).getbbox()


def margin_requirements(
    width: int, height: int, fixed_margin: int | None
) -> tuple[int, int]:
    if fixed_margin is not None:
        return fixed_margin, fixed_margin
    return (
        math.ceil(width * DEFAULT_MARGIN_PERCENT / 100),
        math.ceil(height * DEFAULT_MARGIN_PERCENT / 100),
    )


def audit_file(
    path: Path,
    *,
    cwd: Path,
    expected_size: tuple[int, int],
    fixed_margin: int | None,
) -> dict:
    result: dict = {
        "path": display_path(path, cwd),
        "sha256": None,
        "status": "FAIL",
        "format": None,
        "size": None,
        "mode": None,
        "checks": {
            "format_png": False,
            "expected_size": False,
            "mode_rgb": False,
            "four_corners_pure_white": False,
            "outer_border_pure_white": False,
            "contains_nonwhite_pixels": False,
            "minimum_margin": False,
        },
        "corners": None,
        "outer_border_nonwhite_count": None,
        "outer_border_nonwhite_samples": [],
        "bbox_exclusive": None,
        "bbox_inclusive": None,
        "margins_px": None,
        "required_margin_px": None,
        "failures": [],
    }

    try:
        result["sha256"] = sha256_file(path)
        if path.stat().st_size == 0:
            result["failures"].append("empty_file")
            return result
        with Image.open(path) as opened:
            opened.load()
            image = opened.copy()
            result["format"] = opened.format
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        result["failures"].append(f"unreadable_png:{type(exc).__name__}")
        return result

    width, height = image.size
    result["size"] = [width, height]
    result["mode"] = image.mode
    result["checks"]["format_png"] = result["format"] == EXPECTED_FORMAT
    result["checks"]["expected_size"] = image.size == expected_size
    result["checks"]["mode_rgb"] = image.mode == EXPECTED_MODE

    if not result["checks"]["format_png"]:
        result["failures"].append(
            f"format={result['format'] or 'unknown'}(expected {EXPECTED_FORMAT})"
        )
    if not result["checks"]["expected_size"]:
        result["failures"].append(
            f"size={width}x{height}(expected {expected_size[0]}x{expected_size[1]})"
        )
    if not result["checks"]["mode_rgb"]:
        result["failures"].append(f"mode={image.mode}(expected {EXPECTED_MODE})")
        result["failures"].append("exact_white_checks_require_rgb")
        return result

    corner_coordinates = [
        ("top_left", 0, 0),
        ("top_right", width - 1, 0),
        ("bottom_left", 0, height - 1),
        ("bottom_right", width - 1, height - 1),
    ]
    pixels = image.load()
    corners = {
        name: list(pixels[x, y])
        for name, x, y in corner_coordinates
    }
    result["corners"] = corners
    result["checks"]["four_corners_pure_white"] = all(
        tuple(color) == WHITE for color in corners.values()
    )
    if not result["checks"]["four_corners_pure_white"]:
        bad_corners = [
            name for name, color in corners.items() if tuple(color) != WHITE
        ]
        result["failures"].append(f"corners_not_pure_white={','.join(bad_corners)}")

    border_count, border_samples = border_findings(image)
    result["outer_border_nonwhite_count"] = border_count
    result["outer_border_nonwhite_samples"] = border_samples
    result["checks"]["outer_border_pure_white"] = border_count == 0
    if border_count:
        result["failures"].append(f"outer_border_nonwhite={border_count}")

    bbox = exact_bbox(image)
    if bbox is None:
        result["failures"].append("no_nonwhite_pixels")
        return result

    left, top, right_exclusive, bottom_exclusive = bbox
    result["checks"]["contains_nonwhite_pixels"] = True
    result["bbox_exclusive"] = [left, top, right_exclusive, bottom_exclusive]
    result["bbox_inclusive"] = [
        left,
        top,
        right_exclusive - 1,
        bottom_exclusive - 1,
    ]
    margins = {
        "left": left,
        "top": top,
        "right": width - right_exclusive,
        "bottom": height - bottom_exclusive,
    }
    required_x, required_y = margin_requirements(width, height, fixed_margin)
    result["margins_px"] = margins
    result["required_margin_px"] = {
        "horizontal": required_x,
        "vertical": required_y,
    }

    margin_limits = {
        "left": required_x,
        "top": required_y,
        "right": required_x,
        "bottom": required_y,
    }
    margin_failures = [
        f"margin_{side}={margins[side]}<{minimum}"
        for side, minimum in margin_limits.items()
        if margins[side] < minimum
    ]
    result["checks"]["minimum_margin"] = not margin_failures
    result["failures"].extend(margin_failures)

    if all(result["checks"].values()):
        result["status"] = "PASS"
    return result


def format_file_result(result: dict) -> str:
    identity = (
        f"{result['size'][0]}x{result['size'][1]} {result['mode']}"
        if result["size"]
        else "unreadable"
    )
    parts = [result["status"], result["path"], identity]
    if result["outer_border_nonwhite_count"] is not None:
        border = (
            "pure-white"
            if result["outer_border_nonwhite_count"] == 0
            else f"nonwhite:{result['outer_border_nonwhite_count']}"
        )
        parts.append(f"border={border}")
    if result["bbox_inclusive"] is not None:
        left, top, right, bottom = result["bbox_inclusive"]
        parts.append(f"bbox=({left},{top})-({right},{bottom}) inclusive")
    if result["margins_px"] is not None:
        margins = result["margins_px"]
        parts.append(
            "margins(L/T/R/B)="
            f"{margins['left']}/{margins['top']}/{margins['right']}/{margins['bottom']}px"
        )
        required = result["required_margin_px"]
        parts.append(
            f"required(H/V)={required['horizontal']}/{required['vertical']}px"
        )
    if result["failures"]:
        parts.append("reasons=" + ",".join(result["failures"]))
    return " | ".join(parts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit PNG illustration masters using exact #FFFFFF pixels. "
            "Directories are scanned recursively; quote globs so this script expands them."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="one or more PNG paths, directories, or glob patterns",
    )
    parser.add_argument(
        "--expected-size",
        type=parse_size,
        default=DEFAULT_EXPECTED_SIZE,
        metavar="WIDTHxHEIGHT",
        help="required dimensions (default: 1254x1254)",
    )
    parser.add_argument(
        "--min-margin",
        type=int,
        default=None,
        metavar="PIXELS",
        help=(
            "fixed minimum for all four sides; default is ceil(10%% of each "
            "actual image dimension)"
        ),
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        metavar="PATH",
        help="also write the deterministic audit report as JSON",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.min_margin is not None and args.min_margin < 0:
        parser.error("--min-margin must be zero or greater")

    cwd = Path.cwd().resolve()
    paths, input_errors = resolve_inputs(args.inputs, cwd)
    results = [
        audit_file(
            path,
            cwd=cwd,
            expected_size=args.expected_size,
            fixed_margin=args.min_margin,
        )
        for path in paths
    ]
    passed = sum(result["status"] == "PASS" for result in results)
    failed = len(results) - passed
    overall_pass = bool(results) and failed == 0 and not input_errors

    margin_policy = (
        {"kind": "fixed_pixels", "value": args.min_margin}
        if args.min_margin is not None
        else {
            "kind": "ceil_percent_of_actual_dimension",
            "percent": DEFAULT_MARGIN_PERCENT,
        }
    )
    report = {
        "schema_version": 1,
        "status": "PASS" if overall_pass else "FAIL",
        "policy": {
            "format": EXPECTED_FORMAT,
            "expected_size": list(args.expected_size),
            "mode": EXPECTED_MODE,
            "white_pixel": "#FFFFFF",
            "bbox": "all pixels not exactly #FFFFFF; right and bottom are exclusive",
            "margin": margin_policy,
        },
        "inputs": args.inputs,
        "input_errors": input_errors,
        "files": results,
        "summary": {
            "files": len(results),
            "passed": passed,
            "failed": failed,
            "input_errors": len(input_errors),
        },
    }

    policy_text = (
        f"fixed {args.min_margin}px on every side"
        if args.min_margin is not None
        else "ceil(10% of each actual dimension)"
    )
    print(
        "Illustration master gate: "
        f"PNG {args.expected_size[0]}x{args.expected_size[1]} RGB, "
        "exact white=#FFFFFF, minimum margin="
        f"{policy_text}"
    )
    for error in input_errors:
        print(f"FAIL input={error['input']} | reason={error['reason']}")
    for result in results:
        print(format_file_result(result))
    print(
        f"RESULT {report['status']} | files={len(results)} | passed={passed} | "
        f"failed={failed} | input_errors={len(input_errors)}"
    )

    if args.json_report:
        report_path = args.json_report.expanduser()
        if not report_path.is_absolute():
            report_path = cwd / report_path
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            print(
                f"ERROR could not write JSON report {display_path(report_path, cwd)}: {exc}",
                file=sys.stderr,
            )
            return 2

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
