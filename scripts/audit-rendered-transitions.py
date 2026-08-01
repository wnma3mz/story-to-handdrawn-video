#!/usr/bin/env python3
"""Audit whether a rendered MP4 honors scene-level cut/fade declarations.

The tool is deliberately stricter than a codec/decode check.  It proves the
rendered timeline matches the exact storyboard, extracts visual evidence for
every internal transition, and fails closed when fade frame zero cannot be
shown to retain the completed outgoing frame.

Outputs, written only inside a new/empty evidence directory:

- ``transition-evidence.json``: deterministic machine-readable evidence;
- ``TRANSITION_QC.md``: concise human review surface;
- ``frames/``: labeled PNGs for every requested transition frame;
- ``contact-sheets/``: per-transition sheets plus fade/cut overviews.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


SCHEMA = "rendered-transition-evidence/v1"
REPORT_JSON = "transition-evidence.json"
REPORT_MARKDOWN = "TRANSITION_QC.md"


class AuditError(RuntimeError):
    """Raised when evidence cannot be produced safely."""


def js_math_round(value: float) -> int:
    """Match JavaScript Math.round for the non-negative values used here."""

    if not math.isfinite(value) or value < 0:
        raise AuditError(f"cannot round invalid non-negative frame value: {value}")
    return math.floor(value + 0.5)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(
    command: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def require_number(mapping: dict[str, Any], key: str, label: str) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditError(f"{label}.{key} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise AuditError(f"{label}.{key} must be finite")
    return result


def require_nonempty_id(scene: dict[str, Any], index: int) -> str:
    value = scene.get("id")
    if not isinstance(value, str) or not value.strip():
        raise AuditError(f"scene {index + 1} must have a non-empty string id")
    return value


def build_transition_plan(storyboard: dict[str, Any]) -> dict[str, Any]:
    project = storyboard.get("project")
    scenes = storyboard.get("scenes")
    if not isinstance(project, dict):
        raise AuditError("storyboard.project must be an object")
    if not isinstance(scenes, list) or not scenes:
        raise AuditError("storyboard.scenes must be a non-empty array")

    fps_value = require_number(project, "fps", "storyboard.project")
    if fps_value <= 0:
        raise AuditError("storyboard.project.fps must be positive")
    fps_fraction = Fraction(str(project["fps"]))
    if fps_fraction.denominator != 1:
        raise AuditError(
            "storyboard.project.fps must be an integer for exact JS-compatible "
            "scene-frame planning"
        )
    fps = int(fps_fraction)

    transition_seconds = project.get("transition_sec", 0.7)
    if isinstance(transition_seconds, bool) or not isinstance(
        transition_seconds, (int, float)
    ):
        raise AuditError("storyboard.project.transition_sec must be a number")
    transition_seconds = float(transition_seconds)
    if not math.isfinite(transition_seconds) or transition_seconds <= 0:
        raise AuditError("storyboard.project.transition_sec must be positive")
    fade_frames = js_math_round(transition_seconds * fps)
    if fade_frames < 2:
        raise AuditError("scene fade duration must be at least two frames")

    project_transition = project.get("transition", "cut")
    declared_internal_fades = any(
        isinstance(scene, dict) and scene.get("transition_to_next") == "fade"
        for scene in scenes[:-1]
    )
    if project_transition == "page-flip" and declared_internal_fades:
        raise AuditError(
            "project-level page-flip cannot be audited as scene-level fade"
        )

    frame_cursor = 0
    scene_rows: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, raw_scene in enumerate(scenes):
        if not isinstance(raw_scene, dict):
            raise AuditError(f"scene {index + 1} must be an object")
        scene_id = require_nonempty_id(raw_scene, index)
        if scene_id in seen_ids:
            raise AuditError(f"duplicate scene id: {scene_id}")
        seen_ids.add(scene_id)
        duration_seconds = require_number(raw_scene, "duration_sec", f"scene {scene_id}")
        if duration_seconds <= 0:
            raise AuditError(f"scene {scene_id} duration_sec must be positive")
        duration_frames = js_math_round(duration_seconds * fps)
        if duration_frames < 1:
            raise AuditError(f"scene {scene_id} rounds to zero frames")
        start_frame = frame_cursor
        end_frame = start_frame + duration_frames - 1
        frame_cursor += duration_frames

        declared = raw_scene.get("transition_to_next", "cut")
        if declared not in {"cut", "fade"}:
            raise AuditError(
                f"scene {scene_id} transition_to_next must be cut or fade"
            )

        scene_rows.append(
            {
                "id": scene_id,
                "duration_sec": duration_seconds,
                "duration_frames": duration_frames,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "declared_transition_to_next": declared,
            }
        )

        if index == len(scenes) - 1:
            continue
        next_scene = scenes[index + 1]
        if not isinstance(next_scene, dict):
            raise AuditError(f"scene {index + 2} must be an object")
        next_id = require_nonempty_id(next_scene, index + 1)
        boundary_frame = frame_cursor
        kind = declared
        if kind == "fade":
            offsets = sorted(
                {
                    offset
                    for offset in (0, 5, 10, 15, fade_frames - 1)
                    if 0 <= offset < fade_frames
                }
            )
            samples = [
                {"role": "out_end", "frame": boundary_frame - 1, "offset": -1}
            ]
            samples.extend(
                {
                    "role": f"fade_{offset:02d}",
                    "frame": boundary_frame + offset,
                    "offset": offset,
                }
                for offset in offsets
            )
            samples.append(
                {
                    "role": "in_live",
                    "frame": boundary_frame + fade_frames,
                    "offset": fade_frames,
                }
            )
        else:
            samples = [
                {"role": "out_end", "frame": boundary_frame - 1, "offset": -1},
                {"role": "in_start", "frame": boundary_frame, "offset": 0},
            ]
        transitions.append(
            {
                "ordinal": len(transitions) + 1,
                "kind": kind,
                "from_scene": scene_id,
                "to_scene": next_id,
                "boundary_frame": boundary_frame,
                "fade_frames": fade_frames if kind == "fade" else 0,
                "samples": samples,
            }
        )

    terminal_declared = scene_rows[-1]["declared_transition_to_next"]
    return {
        "fps": fps,
        "fps_rational": f"{fps}/1",
        "transition_sec": transition_seconds,
        "fade_frames": fade_frames,
        "expected_frame_count": frame_cursor,
        "expected_duration_sec": frame_cursor / fps,
        "project_transition": project_transition,
        "scenes": scene_rows,
        "transitions": transitions,
        "route_counts": {
            "fade": sum(row["kind"] == "fade" for row in transitions),
            "cut": sum(row["kind"] == "cut" for row in transitions),
            "terminal_ignored": 1,
        },
        "terminal_transition_ignored": {
            "scene": scene_rows[-1]["id"],
            "declared": terminal_declared,
        },
    }


def parse_fraction(value: str, label: str) -> Fraction:
    try:
        fraction = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise AuditError(f"invalid {label}: {value}") from exc
    if fraction <= 0:
        raise AuditError(f"{label} must be positive")
    return fraction


def probe_video(video: Path) -> dict[str, Any]:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            (
                "stream=index,codec_type,codec_name,width,height,pix_fmt,"
                "r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames"
                ":format=duration,size"
            ),
            "-of",
            "json",
            str(video),
        ]
    )
    data = json.loads(result.stdout)
    streams = data.get("streams")
    if not isinstance(streams, list):
        raise AuditError("ffprobe returned no streams array")
    video_streams = [
        stream for stream in streams if stream.get("codec_type") == "video"
    ]
    if len(video_streams) != 1:
        raise AuditError(
            f"rendered MP4 must contain exactly one video stream, found "
            f"{len(video_streams)}"
        )
    stream = video_streams[0]
    counted = stream.get("nb_read_frames")
    if counted in {None, "N/A"}:
        counted = stream.get("nb_frames")
    try:
        frame_count = int(counted)
    except (TypeError, ValueError) as exc:
        raise AuditError("ffprobe could not count all video frames") from exc
    duration_raw = data.get("format", {}).get("duration")
    try:
        duration = float(duration_raw)
    except (TypeError, ValueError) as exc:
        raise AuditError("ffprobe returned no valid container duration") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise AuditError("rendered MP4 duration must be positive")
    return {
        "codec": stream.get("codec_name"),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "pixel_format": stream.get("pix_fmt"),
        "r_frame_rate": stream.get("r_frame_rate"),
        "avg_frame_rate": stream.get("avg_frame_rate"),
        "frame_count": frame_count,
        "duration_sec": duration,
        "size_bytes": int(data.get("format", {}).get("size") or video.stat().st_size),
        "stream_count": len(streams),
        "audio_stream_count": sum(
            stream.get("codec_type") == "audio" for stream in streams
        ),
    }


def full_decode(video: Path) -> dict[str, Any]:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-xerror",
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-f",
        "null",
        "-",
    ]
    result = run(command, check=False)
    return {
        "command": " ".join(command),
        "exit_code": result.returncode,
        "passed": result.returncode == 0,
        "stderr": result.stderr.strip(),
    }


def ensure_empty_output(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise AuditError(f"output evidence path is not a directory: {path}")
        if any(path.iterdir()):
            raise AuditError(
                "output evidence directory must be new or empty; use a versioned "
                f"path instead of overwriting evidence: {path}"
            )
    else:
        path.mkdir(parents=True)


def extract_frames(video: Path, frames: list[int], temporary: Path) -> dict[int, Path]:
    if not frames:
        return {}
    unique = sorted(set(frames))
    if unique[0] < 0:
        raise AuditError("transition evidence requested a negative frame")
    select = "+".join(f"eq(n\\,{frame})" for frame in unique)
    pattern = temporary / "selected-%06d.png"
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-xerror",
        "-i",
        str(video),
        "-vf",
        f"select='{select}'",
        "-fps_mode",
        "vfr",
        "-start_number",
        "0",
        str(pattern),
    ]
    run(command)
    extracted = sorted(temporary.glob("selected-*.png"))
    if len(extracted) != len(unique):
        raise AuditError(
            f"requested {len(unique)} evidence frames but FFmpeg extracted "
            f"{len(extracted)}"
        )
    return dict(zip(unique, extracted))


def image_metrics(path: Path, *, white_luma_threshold: float) -> dict[str, Any]:
    with Image.open(path) as opened:
        rgb = np.asarray(ImageOps.exif_transpose(opened).convert("RGB"), dtype=np.float32)
    luma = (
        rgb[:, :, 0] * 0.2126
        + rgb[:, :, 1] * 0.7152
        + rgb[:, :, 2] * 0.0722
    )
    return {
        "width": int(rgb.shape[1]),
        "height": int(rgb.shape[0]),
        "yavg": round(float(np.mean(luma)), 6),
        "nonwhite_ratio": round(
            float(np.mean(luma < white_luma_threshold)),
            8,
        ),
    }


def frame_similarity(reference: Path, candidate: Path) -> dict[str, Any]:
    with Image.open(reference) as opened:
        first = np.asarray(
            ImageOps.exif_transpose(opened).convert("RGB"), dtype=np.float64
        )
    with Image.open(candidate) as opened:
        second = np.asarray(
            ImageOps.exif_transpose(opened).convert("RGB"), dtype=np.float64
        )
    if first.shape != second.shape:
        raise AuditError(
            f"evidence frame dimensions differ: {first.shape} vs {second.shape}"
        )

    difference = first - second
    mean_absolute_error = float(np.mean(np.abs(difference)))
    mean_squared_error = float(np.mean(np.square(difference)))
    normalized_similarity = 1.0 - mean_absolute_error / 255.0

    first_luma = (
        first[:, :, 0] * 0.2126
        + first[:, :, 1] * 0.7152
        + first[:, :, 2] * 0.0722
    )
    second_luma = (
        second[:, :, 0] * 0.2126
        + second[:, :, 1] * 0.7152
        + second[:, :, 2] * 0.0722
    )
    mean_first = float(np.mean(first_luma))
    mean_second = float(np.mean(second_luma))
    variance_first = float(np.var(first_luma))
    variance_second = float(np.var(second_luma))
    covariance = float(
        np.mean((first_luma - mean_first) * (second_luma - mean_second))
    )
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    denominator = (
        (mean_first**2 + mean_second**2 + c1)
        * (variance_first + variance_second + c2)
    )
    ssim = (
        ((2 * mean_first * mean_second + c1) * (2 * covariance + c2))
        / denominator
        if denominator
        else 1.0
    )
    return {
        "global_luma_ssim": round(float(ssim), 8),
        "normalized_rgb_similarity": round(normalized_similarity, 8),
        "mean_absolute_error": round(mean_absolute_error, 6),
        "mean_squared_error": round(mean_squared_error, 6),
        "psnr_db": (
            None
            if mean_squared_error == 0
            else round(10 * math.log10((255.0**2) / mean_squared_error), 6)
        ),
    }


def evaluate_fade(
    sample_rows: list[dict[str, Any]],
    *,
    minimum_boundary_ssim: float,
    minimum_boundary_similarity: float,
    minimum_nonwhite_retention: float,
    maximum_boundary_yavg_delta: float,
    minimum_outgoing_nonwhite_ratio: float,
    white_frame_yavg: float,
    white_frame_nonwhite_ratio: float,
    minimum_tail_similarity_drop: float,
) -> dict[str, Any]:
    by_role = {row["role"]: row for row in sample_rows}
    outgoing = by_role["out_end"]
    boundary = by_role["fade_00"]
    tail_roles = [
        role
        for role in by_role
        if role.startswith("fade_") and role != "fade_00"
    ]
    if not tail_roles:
        raise AuditError("fade evidence has no tail sample")
    tail = max((by_role[role] for role in tail_roles), key=lambda row: row["offset"])

    outgoing_nonwhite = outgoing["metrics"]["nonwhite_ratio"]
    boundary_nonwhite = boundary["metrics"]["nonwhite_ratio"]
    retention = (
        boundary_nonwhite / outgoing_nonwhite if outgoing_nonwhite > 0 else 0.0
    )
    boundary_similarity = boundary["similarity_to_out_end"]
    tail_similarity = tail["similarity_to_out_end"]
    hard_cut_to_white = (
        boundary["metrics"]["yavg"] >= white_frame_yavg
        and boundary_nonwhite <= white_frame_nonwhite_ratio
        and outgoing_nonwhite >= minimum_outgoing_nonwhite_ratio
    )
    checks = {
        "outgoing_frame_has_measurable_content": (
            outgoing_nonwhite >= minimum_outgoing_nonwhite_ratio
        ),
        "fade_frame_zero_ssim_retains_outgoing": (
            boundary_similarity["global_luma_ssim"] >= minimum_boundary_ssim
        ),
        "fade_frame_zero_rgb_retains_outgoing": (
            boundary_similarity["normalized_rgb_similarity"]
            >= minimum_boundary_similarity
        ),
        "fade_frame_zero_nonwhite_retention": (
            retention >= minimum_nonwhite_retention
        ),
        "fade_frame_zero_yavg_stable": (
            abs(boundary["metrics"]["yavg"] - outgoing["metrics"]["yavg"])
            <= maximum_boundary_yavg_delta
        ),
        "fade_frame_zero_is_not_hard_cut_to_white": not hard_cut_to_white,
        "fade_tail_releases_outgoing": (
            tail_similarity["global_luma_ssim"]
            <= boundary_similarity["global_luma_ssim"]
            - minimum_tail_similarity_drop
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "measurements": {
            "boundary_nonwhite_retention_ratio": round(retention, 8),
            "boundary_yavg_delta": round(
                boundary["metrics"]["yavg"] - outgoing["metrics"]["yavg"], 6
            ),
            "hard_cut_to_white_detected": hard_cut_to_white,
            "tail_role": tail["role"],
            "tail_ssim_drop_from_boundary": round(
                boundary_similarity["global_luma_ssim"]
                - tail_similarity["global_luma_ssim"],
                8,
            ),
        },
    }


def save_contact_sheet(
    rows: list[dict[str, Any]],
    output: Path,
    *,
    columns: int,
    title: str,
) -> None:
    if not rows:
        return
    cell_width = 240
    cell_height = 360
    title_height = 34
    label_height = 66
    row_count = math.ceil(len(rows) / columns)
    canvas = Image.new(
        "RGB",
        (columns * cell_width, title_height + row_count * cell_height),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=15)
    title_font = ImageFont.load_default(size=18)
    draw.text((10, 7), title, fill="black", font=title_font)
    image_box = (cell_width - 16, cell_height - label_height - 16)

    for index, row in enumerate(rows):
        column = index % columns
        line = index // columns
        x = column * cell_width
        y = title_height + line * cell_height
        with Image.open(row["path"]) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            thumbnail = ImageOps.contain(
                image,
                image_box,
                method=Image.Resampling.LANCZOS,
            )
        image_x = x + (cell_width - thumbnail.width) // 2
        image_y = y + label_height + (
            cell_height - label_height - thumbnail.height
        ) // 2
        canvas.paste(thumbnail, (image_x, image_y))
        label = (
            f"{row['transition_label']} {row['role']} f{row['frame']}\n"
            f"Y {row['metrics']['yavg']:.2f} "
            f"NW {row['metrics']['nonwhite_ratio']:.4f}"
        )
        draw.multiline_text((x + 8, y + 5), label, fill="black", font=font, spacing=2)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=False)


def materialize_evidence(
    plan: dict[str, Any],
    video: Path,
    output: Path,
    *,
    white_luma_threshold: float,
    thresholds: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    requested_frames = [
        sample["frame"]
        for transition in plan["transitions"]
        for sample in transition["samples"]
    ]
    if requested_frames and max(requested_frames) >= plan["expected_frame_count"]:
        raise AuditError(
            "transition evidence reaches beyond the planned composition frame count"
        )

    frame_root = output / "frames"
    sheet_root = output / "contact-sheets"
    frame_root.mkdir(parents=True, exist_ok=True)
    sheet_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="transition-evidence-") as directory:
        extracted = extract_frames(video, requested_frames, Path(directory))
        metric_cache: dict[int, dict[str, Any]] = {}
        transitions: list[dict[str, Any]] = []
        overview_rows: dict[str, list[dict[str, Any]]] = {"fade": [], "cut": []}

        for transition in plan["transitions"]:
            label = (
                f"{transition['kind']}-{transition['ordinal']:03d}-"
                f"s{transition['from_scene']}-to-s{transition['to_scene']}"
            )
            transition_dir = frame_root / label
            transition_dir.mkdir()
            sample_rows: list[dict[str, Any]] = []
            for sample in transition["samples"]:
                frame = sample["frame"]
                filename = f"{sample['role']}-f{frame:06d}.png"
                destination = transition_dir / filename
                shutil.copyfile(extracted[frame], destination)
                if frame not in metric_cache:
                    metric_cache[frame] = image_metrics(
                        destination,
                        white_luma_threshold=white_luma_threshold,
                    )
                row = {
                    **sample,
                    "transition_label": label,
                    "path": destination,
                    "relative_path": destination.relative_to(output).as_posix(),
                    "sha256": sha256(destination),
                    "metrics": metric_cache[frame],
                }
                sample_rows.append(row)

            outgoing_path = next(
                row["path"] for row in sample_rows if row["role"] == "out_end"
            )
            for row in sample_rows:
                row["similarity_to_out_end"] = frame_similarity(
                    outgoing_path,
                    row["path"],
                )

            if transition["kind"] == "fade":
                evaluation = evaluate_fade(
                    sample_rows,
                    minimum_boundary_ssim=thresholds["minimum_boundary_ssim"],
                    minimum_boundary_similarity=thresholds[
                        "minimum_boundary_similarity"
                    ],
                    minimum_nonwhite_retention=thresholds[
                        "minimum_nonwhite_retention"
                    ],
                    maximum_boundary_yavg_delta=thresholds[
                        "maximum_boundary_yavg_delta"
                    ],
                    minimum_outgoing_nonwhite_ratio=thresholds[
                        "minimum_outgoing_nonwhite_ratio"
                    ],
                    white_frame_yavg=thresholds["white_frame_yavg"],
                    white_frame_nonwhite_ratio=thresholds[
                        "white_frame_nonwhite_ratio"
                    ],
                    minimum_tail_similarity_drop=thresholds[
                        "minimum_tail_similarity_drop"
                    ],
                )
                columns = len(sample_rows)
            else:
                evaluation = {
                    "status": "PASS",
                    "checks": {
                        "cut_boundary_frames_extracted": True,
                    },
                    "measurements": {
                        "boundary_similarity_is_informational_only": True,
                    },
                }
                columns = 2

            per_sheet = sheet_root / f"{label}.png"
            save_contact_sheet(
                sample_rows,
                per_sheet,
                columns=columns,
                title=label,
            )
            overview_rows[transition["kind"]].extend(sample_rows)
            transitions.append(
                {
                    **{key: value for key, value in transition.items() if key != "samples"},
                    "label": label,
                    "status": evaluation["status"],
                    "checks": evaluation["checks"],
                    "measurements": evaluation["measurements"],
                    "contact_sheet": {
                        "path": per_sheet.relative_to(output).as_posix(),
                        "sha256": sha256(per_sheet),
                    },
                    "samples": [
                        {
                            key: value
                            for key, value in row.items()
                            if key not in {"path", "transition_label"}
                        }
                        for row in sample_rows
                    ],
                }
            )

        overview: dict[str, Any] = {}
        for kind, rows in overview_rows.items():
            if not rows:
                continue
            columns = (
                len(plan["transitions"][0]["samples"])
                if kind == "fade"
                and plan["transitions"]
                and plan["transitions"][0]["kind"] == "fade"
                else (max(
                    len(transition["samples"])
                    for transition in plan["transitions"]
                    if transition["kind"] == kind
                ))
            )
            overview_path = sheet_root / f"{kind}-overview.png"
            save_contact_sheet(
                rows,
                overview_path,
                columns=columns,
                title=f"{kind.upper()} transition overview",
            )
            overview[kind] = {
                "path": overview_path.relative_to(output).as_posix(),
                "sha256": sha256(overview_path),
                "sample_count": len(rows),
            }

    return transitions, overview


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    video = report["video"]
    lines = [
        "# Rendered Transition QC",
        "",
        f"结论：`{report['status']}`。",
        "",
        "完整解码只证明码流可读取，不证明声明的视觉转场被执行；"
        "最终结论同时要求时间线合同和逐个 fade 视觉证据通过。",
        "",
        "## 输入与时间线",
        "",
        f"- Storyboard：`{report['inputs']['storyboard']['path']}`",
        f"- Storyboard SHA-256：`{report['inputs']['storyboard']['sha256']}`",
        f"- Video：`{report['inputs']['video']['path']}`",
        f"- Video SHA-256：`{report['inputs']['video']['sha256']}`",
        f"- 计划/实际帧数：{video['expected_frame_count']} / "
        f"{video['probe']['frame_count']}",
        f"- 计划/实际 FPS：{video['expected_fps']} / "
        f"{video['probe']['r_frame_rate']}",
        f"- 内部 fade / cut：{summary['fade_count']} / {summary['cut_count']}",
        f"- 终镜 transition：已忽略 "
        f"(`{report['timeline']['terminal_transition_ignored']['declared']}`)",
        "",
        "## 独立门禁",
        "",
        f"- Full decode：`{'PASS' if video['full_decode']['passed'] else 'FAIL'}`",
        f"- Timeline / probe contract："
        f"`{'PASS' if video['contract_checks_passed'] else 'FAIL'}`",
        f"- Visual transition evidence："
        f"`{'PASS' if summary['visual_transition_checks_passed'] else 'FAIL'}`",
        "",
        "## Fade 逐条结果",
        "",
        "| Boundary | Frames | Status | Frame-0 SSIM | Nonwhite retention | "
        "Hard white cut |",
        "|---|---:|---|---:|---:|---|",
    ]
    fades = [
        transition
        for transition in report["transitions"]
        if transition["kind"] == "fade"
    ]
    if fades:
        for transition in fades:
            boundary = next(
                sample
                for sample in transition["samples"]
                if sample["role"] == "fade_00"
            )
            measurements = transition["measurements"]
            lines.append(
                f"| {transition['from_scene']}→{transition['to_scene']} | "
                f"{transition['boundary_frame']} | {transition['status']} | "
                f"{boundary['similarity_to_out_end']['global_luma_ssim']:.6f} | "
                f"{measurements['boundary_nonwhite_retention_ratio']:.4f} | "
                f"{'YES' if measurements['hard_cut_to_white_detected'] else 'NO'} |"
            )
    else:
        lines.append("| — | — | PASS | — | — | NO |")
    lines.extend(
        [
            "",
            "## 证据",
            "",
            f"- JSON：`{REPORT_JSON}`",
            "- PNG：`frames/`",
            "- Labeled contact sheets：`contact-sheets/`",
            "",
            "所有 PASS 仍需正常速度人工检查；本工具只承担可重复的技术与"
            "转场视觉合同门禁。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("storyboard", type=Path, help="exact storyboard JSON")
    parser.add_argument("video", type=Path, help="rendered MP4 to audit")
    parser.add_argument("output_evidence_dir", type=Path)
    parser.add_argument("--white-luma-threshold", type=float, default=250.0)
    parser.add_argument("--minimum-boundary-ssim", type=float, default=0.995)
    parser.add_argument(
        "--minimum-boundary-similarity",
        type=float,
        default=0.995,
    )
    parser.add_argument("--minimum-nonwhite-retention", type=float, default=0.85)
    parser.add_argument("--maximum-boundary-yavg-delta", type=float, default=2.0)
    parser.add_argument(
        "--minimum-outgoing-nonwhite-ratio",
        type=float,
        default=0.002,
    )
    parser.add_argument("--white-frame-yavg", type=float, default=253.5)
    parser.add_argument(
        "--white-frame-nonwhite-ratio",
        type=float,
        default=0.001,
    )
    parser.add_argument(
        "--minimum-tail-similarity-drop",
        type=float,
        default=0.001,
    )
    return parser.parse_args()


def validate_thresholds(args: argparse.Namespace) -> dict[str, float]:
    thresholds = {
        "white_luma_threshold": args.white_luma_threshold,
        "minimum_boundary_ssim": args.minimum_boundary_ssim,
        "minimum_boundary_similarity": args.minimum_boundary_similarity,
        "minimum_nonwhite_retention": args.minimum_nonwhite_retention,
        "maximum_boundary_yavg_delta": args.maximum_boundary_yavg_delta,
        "minimum_outgoing_nonwhite_ratio": args.minimum_outgoing_nonwhite_ratio,
        "white_frame_yavg": args.white_frame_yavg,
        "white_frame_nonwhite_ratio": args.white_frame_nonwhite_ratio,
        "minimum_tail_similarity_drop": args.minimum_tail_similarity_drop,
    }
    if not all(math.isfinite(value) for value in thresholds.values()):
        raise AuditError("all thresholds must be finite")
    for key in (
        "minimum_boundary_ssim",
        "minimum_boundary_similarity",
        "minimum_nonwhite_retention",
        "minimum_outgoing_nonwhite_ratio",
        "white_frame_nonwhite_ratio",
        "minimum_tail_similarity_drop",
    ):
        if thresholds[key] < 0:
            raise AuditError(f"{key} must be non-negative")
    if not 0 <= thresholds["white_luma_threshold"] <= 255:
        raise AuditError("white_luma_threshold must be in [0,255]")
    if not 0 <= thresholds["white_frame_yavg"] <= 255:
        raise AuditError("white_frame_yavg must be in [0,255]")
    return thresholds


def main() -> int:
    args = parse_args()
    for executable in ("ffmpeg", "ffprobe"):
        if shutil.which(executable) is None:
            raise SystemExit(f"required executable not found: {executable}")

    storyboard_path = args.storyboard.resolve()
    video_path = args.video.resolve()
    output = args.output_evidence_dir.resolve()
    if not storyboard_path.is_file():
        raise SystemExit(f"missing storyboard: {storyboard_path}")
    if not video_path.is_file():
        raise SystemExit(f"missing video: {video_path}")

    try:
        thresholds = validate_thresholds(args)
        ensure_empty_output(output)
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
        if not isinstance(storyboard, dict):
            raise AuditError("storyboard root must be an object")
        plan = build_transition_plan(storyboard)
        probe = probe_video(video_path)
        probed_fps = parse_fraction(probe["r_frame_rate"], "video r_frame_rate")
        duration_delta = abs(probe["duration_sec"] - plan["expected_duration_sec"])
        duration_tolerance = 1.0 / plan["fps"] + 0.001
        contract_checks = {
            "fps_matches_storyboard": probed_fps == Fraction(plan["fps"], 1),
            "frame_count_matches_js_rounded_storyboard": (
                probe["frame_count"] == plan["expected_frame_count"]
            ),
            "duration_within_one_frame": duration_delta <= duration_tolerance,
            "video_dimensions_positive": (
                probe["width"] > 0 and probe["height"] > 0
            ),
            "all_evidence_frames_inside_video": all(
                sample["frame"] < probe["frame_count"]
                for transition in plan["transitions"]
                for sample in transition["samples"]
            ),
        }
        decode = full_decode(video_path)
        transitions, overview = materialize_evidence(
            plan,
            video_path,
            output,
            white_luma_threshold=thresholds["white_luma_threshold"],
            thresholds=thresholds,
        )
        visual_pass = all(
            transition["status"] == "PASS" for transition in transitions
        )
        contract_pass = all(contract_checks.values())
        overall_pass = decode["passed"] and contract_pass and visual_pass

        report = {
            "schema": SCHEMA,
            "status": "PASS" if overall_pass else "FAIL",
            "inputs": {
                "storyboard": {
                    "path": storyboard_path.as_posix(),
                    "sha256": sha256(storyboard_path),
                },
                "video": {
                    "path": video_path.as_posix(),
                    "sha256": sha256(video_path),
                },
            },
            "thresholds": thresholds,
            "timeline": {
                key: value
                for key, value in plan.items()
                if key not in {"transitions"}
            },
            "video": {
                "expected_fps": plan["fps_rational"],
                "expected_frame_count": plan["expected_frame_count"],
                "expected_duration_sec": round(plan["expected_duration_sec"], 9),
                "probe": probe,
                "duration_delta_sec": round(duration_delta, 9),
                "duration_tolerance_sec": round(duration_tolerance, 9),
                "contract_checks": contract_checks,
                "contract_checks_passed": contract_pass,
                "full_decode": decode,
                "decode_is_not_visual_transition_proof": True,
            },
            "summary": {
                "transition_count": len(transitions),
                "fade_count": sum(row["kind"] == "fade" for row in transitions),
                "cut_count": sum(row["kind"] == "cut" for row in transitions),
                "fade_passed": sum(
                    row["kind"] == "fade" and row["status"] == "PASS"
                    for row in transitions
                ),
                "fade_failed": sum(
                    row["kind"] == "fade" and row["status"] == "FAIL"
                    for row in transitions
                ),
                "visual_transition_checks_passed": visual_pass,
                "full_decode_passed": decode["passed"],
                "overall_passed": overall_pass,
            },
            "contact_sheet_overviews": overview,
            "transitions": transitions,
        }
        json_path = output / REPORT_JSON
        json_path.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        markdown_path = output / REPORT_MARKDOWN
        markdown_path.write_text(markdown_report(report), encoding="utf-8")
        print(
            f"{report['status']} | fades "
            f"{report['summary']['fade_passed']}/"
            f"{report['summary']['fade_count']} | "
            f"{json_path}"
        )
        return 0 if overall_pass else 1
    except (AuditError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
