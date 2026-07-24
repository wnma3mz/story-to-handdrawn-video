#!/usr/bin/env python3
"""Audit a narrated story release and its continuous-group evidence."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def probe(path: Path) -> dict:
    result = run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate,sample_rate,channels",
        "-of", "json", str(path),
    ])
    return json.loads(result.stdout)


def first_frame_luma(path: Path) -> float:
    result = run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vf",
        "select=eq(n\\,0),signalstats,metadata=print:file=-", "-frames:v", "1", "-f", "null", "-",
    ])
    match = re.search(r"lavfi\.signalstats\.YAVG=([0-9.]+)", result.stdout + result.stderr)
    if not match:
        raise RuntimeError("Could not measure first-frame luma")
    return float(match.group(1))


def interval_mean_volume(path: Path, duration_sec: float) -> float:
    result = run([
        "ffmpeg", "-hide_banner", "-nostats", "-t", str(duration_sec), "-i", str(path),
        "-af", "volumedetect", "-f", "null", "-",
    ])
    match = re.search(r"mean_volume:\s*(-?(?:[0-9.]+|inf)) dB", result.stderr)
    if not match:
        raise RuntimeError("Could not measure cover volume")
    return float("-inf") if match.group(1) == "-inf" else float(match.group(1))


def loudness(path: Path) -> dict:
    result = run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=7:print_format=json", "-f", "null", "-",
    ])
    matches = re.findall(r'\{\s*"input_i".*?\}', result.stderr, flags=re.DOTALL)
    if not matches:
        raise RuntimeError("Could not measure loudness")
    return json.loads(matches[-1])


def detect_silences(path: Path, threshold_db: float = -42.0, minimum_sec: float = 0.18) -> list[dict]:
    result = run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
        f"silencedetect=noise={threshold_db}dB:d={minimum_sec}", "-f", "null", "-",
    ])
    starts = [float(value) for value in re.findall(r"silence_start: ([0-9.]+)", result.stderr)]
    ends = [
        (float(end), float(duration))
        for end, duration in re.findall(
            r"silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)", result.stderr
        )
    ]
    return [
        {"start_sec": start, "end_sec": end, "duration_sec": duration}
        for start, (end, duration) in zip(starts, ends)
    ]


def read_json(path: Path | None) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path else None


def frame_rate(value: str | int | float) -> float:
    """Accept ffprobe rationals (30/1) and human CLI values (30)."""
    return float(Fraction(str(value)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--master", type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--sync-map", type=Path)
    parser.add_argument("--cover-duration", type=float, default=0.0)
    parser.add_argument("--expected-duration", type=float)
    parser.add_argument("--expect-width", type=int)
    parser.add_argument("--expect-height", type=int)
    parser.add_argument("--expect-fps")
    parser.add_argument("--max-sync-error", type=float, default=0.6)
    parser.add_argument("--max-group-gap", type=float, default=0.8)
    parser.add_argument("--ordinary-pause-limit", type=float, default=1.25)
    parser.add_argument("--max-global-silence", type=float, default=2.0)
    parser.add_argument("--max-cover-luma", type=float, default=200.0)
    parser.add_argument("--min-cover-mean-db", type=float, default=-45.0)
    parser.add_argument("--target-lufs", type=float, default=-16.0)
    parser.add_argument("--lufs-tolerance", type=float, default=0.5)
    parser.add_argument("--max-true-peak", type=float, default=-1.45)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not 0.5 <= args.ordinary_pause_limit <= 1.5:
        parser.error("--ordinary-pause-limit must stay within 0.5..1.5 seconds")

    metadata = probe(args.video)
    streams = metadata.get("streams", [])
    video_stream = next((row for row in streams if row.get("codec_type") == "video"), None)
    audio_stream = next((row for row in streams if row.get("codec_type") == "audio"), None)
    duration = float(metadata["format"]["duration"])
    checks: dict[str, bool] = {
        "has_video_stream": video_stream is not None,
        "has_audio_stream": audio_stream is not None,
    }
    decode = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(args.video), "-f", "null", "-"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    checks["full_decode"] = decode.returncode == 0
    if audio_stream:
        checks["audio_48khz"] = audio_stream.get("sample_rate") == "48000"
        checks["audio_stereo"] = int(audio_stream.get("channels", 0)) == 2
    if video_stream and args.expect_width is not None:
        checks["expected_width"] = video_stream.get("width") == args.expect_width
    if video_stream and args.expect_height is not None:
        checks["expected_height"] = video_stream.get("height") == args.expect_height
    if video_stream and args.expect_fps is not None:
        checks["expected_fps"] = abs(
            frame_rate(video_stream.get("r_frame_rate", "0")) - frame_rate(args.expect_fps)
        ) <= 0.001
    if args.expected_duration is not None:
        checks["duration_within_50ms"] = abs(duration - args.expected_duration) <= 0.05

    details: dict[str, object] = {"probe": metadata}
    if args.cover_duration > 0:
        luma = first_frame_luma(args.video)
        cover_db = interval_mean_volume(args.video, args.cover_duration)
        details["cover"] = {"first_frame_yavg": luma, "mean_volume_db": cover_db}
        checks["cover_first_frame_not_white"] = luma < args.max_cover_luma
        checks["cover_interval_audible"] = cover_db > args.min_cover_mean_db
    build = read_json(args.build)
    if args.master:
        measured = loudness(args.master)
        details["loudness"] = measured
        checks["loudness_within_tolerance"] = abs(float(measured["input_i"]) - args.target_lufs) <= args.lufs_tolerance
        checks["true_peak_within_limit"] = float(measured["input_tp"]) <= args.max_true_peak
        master_duration = float(probe(args.master)["format"]["duration"])
        silences = detect_silences(args.master)
        long_silences = [
            row for row in silences
            if float(row["duration_sec"]) > args.ordinary_pause_limit
        ]
        unplanned_long_silences = [
            row for row in long_silences
            if float(row["end_sec"]) < master_duration - 0.05
        ]
        maximum_silence = max((float(row["duration_sec"]) for row in silences), default=0.0)
        details["acoustic_silence"] = {
            "threshold_db": -42.0,
            "minimum_silence_sec": 0.18,
            "ordinary_pause_limit_sec": args.ordinary_pause_limit,
            "maximum_global_silence_sec": args.max_global_silence,
            "maximum_detected_silence_sec": round(maximum_silence, 3),
            "long_silences": long_silences,
            "unplanned_long_silences": unplanned_long_silences,
        }
        checks["no_unplanned_acoustic_silence_over_limit"] = not unplanned_long_silences
        checks["global_acoustic_silence_within_limit"] = maximum_silence <= args.max_global_silence

    if build:
        groups = build.get("groups", [])
        checks["continuous_group_layout"] = build.get("layout") == "continuous_groups_synced"
        checks["zero_internal_group_cuts"] = bool(groups) and all(row.get("group_internal_cut_count") == 0 for row in groups)
        checks["zero_sentence_tempo_variants"] = bool(groups) and all(row.get("sentence_level_tempo_variants") == 0 for row in groups)
        checks["whole_group_tempo_within_five_percent"] = bool(groups) and all(0.95 <= float(row.get("whole_group_tempo", 0)) <= 1.05 for row in groups)
        gaps = [float(row["gap_to_next_sec"]) for row in groups[:-1] if row.get("gap_to_next_sec") is not None]
        details["group_gaps_sec"] = gaps
        checks["group_gaps_within_limit"] = len(groups) == 1 or (bool(gaps) and max(gaps) <= args.max_group_gap + 0.001)

    sync_map = read_json(args.sync_map)
    if sync_map:
        summary = sync_map.get("summary", {})
        release = sync_map.get("release_timeline", {})
        checks["semantic_sync_within_limit"] = float(summary.get("maximum_non_bridge_scene_start_offset_sec", float("inf"))) <= args.max_sync_error + 0.001
        checks["main_video_and_story_audio_same_start"] = abs(float(release.get("main_video_story_audio_delta_sec", float("inf")))) <= 0.001
        details["sync_summary"] = summary
        details["release_timeline"] = release

    report = {
        "status": "PASS" if checks and all(checks.values()) else "FAIL",
        "video": str(args.video.resolve()),
        "checks": checks,
        "details": details,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
