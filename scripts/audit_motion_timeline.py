#!/usr/bin/env python3
import argparse
import csv
import pathlib
import sys
from collections import Counter


ALLOWED = {
    "hold",
    "push_soft",
    "pull_soft",
    "push_left",
    "push_right",
    "pan_left",
    "pan_right",
}
SETTLED = {"hold", "push_soft", "pull_soft"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a still-image motion TSV.")
    parser.add_argument("timeline", type=pathlib.Path)
    parser.add_argument("--image-dir", type=pathlib.Path)
    parser.add_argument("--expected-duration", type=float)
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    rows: list[dict[str, object]] = []

    with args.timeline.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader((line for line in handle if not line.lstrip().startswith("#")), delimiter="\t")
        for line_no, fields in enumerate(reader, start=1):
            if not fields or all(not item.strip() for item in fields):
                continue
            if len(fields) < 4:
                errors.append(f"row {line_no}: expected 4 columns")
                continue
            scene, duration_text, image, motion = (item.strip() for item in fields[:4])
            try:
                duration = float(duration_text)
            except ValueError:
                errors.append(f"row {line_no}: invalid duration {duration_text!r}")
                continue
            if duration <= 0:
                errors.append(f"row {line_no}: duration must be positive")
            if motion not in ALLOWED:
                errors.append(f"row {line_no}: unsupported motion {motion!r}")
            if args.image_dir and not (args.image_dir / image).is_file():
                errors.append(f"row {line_no}: missing image {image}")
            if duration < 3:
                warnings.append(f"row {line_no}: {duration:.2f}s may be too short for readable still-image motion")
            if duration > 30:
                warnings.append(f"row {line_no}: {duration:.2f}s may feel visually under-varied")
            rows.append({"scene": scene, "duration": duration, "image": image, "motion": motion})

    if len(rows) < 2:
        errors.append("timeline needs at least two scenes")

    for index in range(1, len(rows)):
        if rows[index]["image"] == rows[index - 1]["image"]:
            warnings.append(
                f"rows {index} and {index + 1}: adjacent image {rows[index]['image']} should usually be merged"
            )

    for index in range(2, len(rows)):
        current = rows[index]["motion"]
        if current == rows[index - 1]["motion"] == rows[index - 2]["motion"] and current not in SETTLED:
            warnings.append(f"rows {index - 1}-{index + 1}: strong motion {current!r} repeats three times")

    total = sum(float(row["duration"]) for row in rows)
    if args.expected_duration is not None and abs(total - args.expected_duration) > 0.05:
        errors.append(f"duration mismatch: timeline={total:.3f}s expected={args.expected_duration:.3f}s")

    counts = Counter(str(row["motion"]) for row in rows)
    settled = sum(1 for row in rows if row["motion"] in SETTLED)
    ratio = settled / len(rows) if rows else 0
    if rows and ratio < 0.20:
        warnings.append(f"settled-shot ratio {ratio:.0%} is low; the episode may feel continuously animated")

    for warning in warnings:
        print(f"WARN\t{warning}")
    for error in errors:
        print(f"FAIL\t{error}")
    print(f"SUMMARY\tscenes={len(rows)}\tduration={total:.3f}s\tsettled={ratio:.0%}\tmotions={dict(counts)}")
    if errors:
        return 1
    print("RESULT\tPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
