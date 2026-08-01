#!/usr/bin/env python3
"""Assemble a narrated release from approved, prebuilt media.

The assembler is deliberately story-agnostic.  Every content-specific path,
hash, cover duration, frame count, and timeline boundary is supplied by the
caller or an explicit timeline config.  It never falls back to a preview,
generates title audio, or assumes the historical 2.7-second cover duration.

Two immutable-input derivatives are produced:

1. a no-cover voiced master whose video elementary stream is copied from the
   approved silent picture (and which never uses FFmpeg ``-shortest``);
2. a release made by strict, non-overlapping concatenation of an already
   audible cover clip and the no-cover voiced master.

The timeline config may use the compact generic schema documented by
``load_contract`` or the existing ``release-assembly-config.json`` schema used
by the episodic production tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any


class AssemblyError(RuntimeError):
    """Raised when an input or output violates the release contract."""


@dataclass(frozen=True)
class Contract:
    cover_duration_sec: float
    cover_frame_count: int
    cover_video_start_sec: float
    cover_video_end_sec: float
    main_video_start_sec: float
    story_audio_start_sec: float
    transition_overlap_sec: float
    width: int
    height: int
    fps: str
    cover_video_codec: str
    picture_video_codec: str
    cover_audio_codec: str
    cover_audio_sample_rate_hz: int
    cover_audio_channels: int
    narration_audio_codec: str
    narration_sample_rate_hz: int
    narration_channels: int
    delivery_audio_sample_rate_hz: int
    delivery_audio_channels: int
    delivery_audio_bitrate: str
    release_video_encoder: str
    release_video_preset: str
    release_video_crf: int
    duration_tolerance_sec: float
    timeline_tolerance_sec: float


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(mapping: dict[str, Any], path: str) -> Any:
    value: Any = mapping
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise AssemblyError(f"timeline config is missing required field: {path}")
        value = value[part]
    return value


def optional(mapping: dict[str, Any], path: str, fallback: Any) -> Any:
    value: Any = mapping
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return fallback
        value = value[part]
    return value


def load_contract(path: Path) -> Contract:
    """Load a compact generic contract or the existing release-prep contract.

    Compact schema (all timing and media identity fields are required):

    {
      "schema_version": 1,
      "cover": {
        "duration_sec": 3.6, "frame_count": 108,
        "video_codec": "h264", "audio_codec": "aac",
        "audio_sample_rate_hz": 48000, "audio_channels": 2
      },
      "picture": {"video_codec": "h264"},
      "narration": {
        "audio_codec": "pcm_s24le",
        "sample_rate_hz": 48000, "channels": 1
      },
      "timeline": {
        "cover_video_start_sec": 0.0, "cover_video_end_sec": 3.6,
        "main_video_start_sec": 3.6, "story_audio_start_sec": 3.6,
        "transition_overlap_sec": 0.0
      },
      "delivery": {
        "width": 1080, "height": 1440, "fps": "30/1",
        "audio_sample_rate_hz": 48000, "audio_channels": 2,
        "audio_bitrate": "192k", "video_encoder": "libx264",
        "video_preset": "slow", "video_crf": 16
      },
      "tolerances": {"duration_sec": 0.05, "timeline_sec": 0.001}
    }

    The duration and frame count intentionally have no defaults.  This is the
    stale-cover-duration guard.
    """

    data = json.loads(path.read_text(encoding="utf-8"))
    if "timeline_contract" in data and "artifact_contract" in data:
        artifacts = data["artifact_contract"]
        timeline = data["timeline_contract"]
        cover = artifacts["cover_with_title_audio"]
        picture = artifacts["silent_picture"]["expected_video"]
        narration = artifacts["narration_master"]
        no_cover = artifacts["no_cover_voiced"]
        release = artifacts["release"]
        release_video = release["video"]
        cover_video_timeline = timeline["cover_video"]
        return Contract(
            cover_duration_sec=float(require(cover, "duration_sec")),
            cover_frame_count=int(require(cover, "video_frames")),
            cover_video_start_sec=float(require(cover_video_timeline, "start_sec")),
            cover_video_end_sec=float(require(cover_video_timeline, "end_sec")),
            main_video_start_sec=float(require(timeline, "main_video_start_sec")),
            story_audio_start_sec=float(require(timeline, "story_audio_start_sec")),
            transition_overlap_sec=float(require(timeline, "transition_overlap_sec")),
            width=int(require(release_video, "width")),
            height=int(require(release_video, "height")),
            fps=str(require(release_video, "fps")),
            cover_video_codec=str(require(cover, "video_codec")),
            picture_video_codec=str(require(picture, "codec")),
            cover_audio_codec=str(require(cover, "audio_codec")),
            cover_audio_sample_rate_hz=int(require(cover, "audio_sample_rate_hz")),
            cover_audio_channels=int(require(cover, "audio_channels")),
            narration_audio_codec=str(require(narration, "codec")),
            narration_sample_rate_hz=int(require(narration, "sample_rate_hz")),
            narration_channels=int(require(narration, "channels")),
            delivery_audio_sample_rate_hz=int(require(no_cover, "audio.sample_rate_hz")),
            delivery_audio_channels=int(require(no_cover, "audio.channels")),
            delivery_audio_bitrate=str(require(no_cover, "audio.bitrate")),
            release_video_encoder=str(optional(release_video, "reference_encoder_settings.encoder", "libx264")),
            release_video_preset=str(optional(release_video, "reference_encoder_settings.preset", "slow")),
            release_video_crf=int(optional(release_video, "reference_encoder_settings.crf", 16)),
            duration_tolerance_sec=float(
                min(
                    require(no_cover, "maximum_allowed_duration_error_sec"),
                    require(release, "maximum_allowed_duration_error_sec"),
                )
            ),
            timeline_tolerance_sec=float(
                optional(
                    data,
                    "qc_thresholds.main_video_story_audio_start_delta_max_sec",
                    0.001,
                )
            ),
        )

    return Contract(
        cover_duration_sec=float(require(data, "cover.duration_sec")),
        cover_frame_count=int(require(data, "cover.frame_count")),
        cover_video_start_sec=float(require(data, "timeline.cover_video_start_sec")),
        cover_video_end_sec=float(require(data, "timeline.cover_video_end_sec")),
        main_video_start_sec=float(require(data, "timeline.main_video_start_sec")),
        story_audio_start_sec=float(require(data, "timeline.story_audio_start_sec")),
        transition_overlap_sec=float(require(data, "timeline.transition_overlap_sec")),
        width=int(require(data, "delivery.width")),
        height=int(require(data, "delivery.height")),
        fps=str(require(data, "delivery.fps")),
        cover_video_codec=str(require(data, "cover.video_codec")),
        picture_video_codec=str(require(data, "picture.video_codec")),
        cover_audio_codec=str(require(data, "cover.audio_codec")),
        cover_audio_sample_rate_hz=int(require(data, "cover.audio_sample_rate_hz")),
        cover_audio_channels=int(require(data, "cover.audio_channels")),
        narration_audio_codec=str(require(data, "narration.audio_codec")),
        narration_sample_rate_hz=int(require(data, "narration.sample_rate_hz")),
        narration_channels=int(require(data, "narration.channels")),
        delivery_audio_sample_rate_hz=int(require(data, "delivery.audio_sample_rate_hz")),
        delivery_audio_channels=int(require(data, "delivery.audio_channels")),
        delivery_audio_bitrate=str(require(data, "delivery.audio_bitrate")),
        release_video_encoder=str(require(data, "delivery.video_encoder")),
        release_video_preset=str(require(data, "delivery.video_preset")),
        release_video_crf=int(require(data, "delivery.video_crf")),
        duration_tolerance_sec=float(require(data, "tolerances.duration_sec")),
        timeline_tolerance_sec=float(require(data, "tolerances.timeline_sec")),
    )


def canonical_fps(value: str) -> str:
    try:
        rate = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise AssemblyError(f"invalid frame rate: {value}") from exc
    if rate <= 0:
        raise AssemblyError(f"frame rate must be positive: {value}")
    return f"{rate.numerator}/{rate.denominator}"


def validate_contract(contract: Contract) -> None:
    if contract.cover_duration_sec <= 0:
        raise AssemblyError("cover duration must be positive and explicit")
    if contract.cover_frame_count <= 0:
        raise AssemblyError("cover frame count must be positive and explicit")
    if contract.duration_tolerance_sec <= 0 or contract.duration_tolerance_sec > 0.05:
        raise AssemblyError("duration tolerance must be in (0, 0.05] seconds")
    if contract.timeline_tolerance_sec <= 0 or contract.timeline_tolerance_sec > 0.001:
        raise AssemblyError("timeline tolerance must be in (0, 0.001] seconds")
    if abs(contract.cover_video_start_sec) > contract.timeline_tolerance_sec:
        raise AssemblyError("strict concat requires cover_video_start_sec == 0")
    if abs(contract.cover_video_end_sec - contract.cover_duration_sec) > contract.timeline_tolerance_sec:
        raise AssemblyError("configured cover end does not equal the explicit cover duration")
    if abs(contract.main_video_start_sec - contract.cover_duration_sec) > contract.timeline_tolerance_sec:
        raise AssemblyError("main_video_start_sec must equal the explicit cover duration")
    if abs(contract.story_audio_start_sec - contract.cover_duration_sec) > contract.timeline_tolerance_sec:
        raise AssemblyError("story_audio_start_sec must equal the explicit cover duration")
    if abs(contract.main_video_start_sec - contract.story_audio_start_sec) > contract.timeline_tolerance_sec:
        raise AssemblyError("main video and story audio must start together")
    if abs(contract.transition_overlap_sec) > contract.timeline_tolerance_sec:
        raise AssemblyError("this assembler supports strict non-overlap only")
    fps = Fraction(canonical_fps(contract.fps))
    frame_locked_duration = contract.cover_frame_count / float(fps)
    half_frame = 0.5 / float(fps)
    if abs(frame_locked_duration - contract.cover_duration_sec) > half_frame + 1e-9:
        raise AssemblyError(
            "cover duration/frame-count/fps disagree; refusing a stale duration assumption "
            f"({contract.cover_duration_sec:.6f}s vs {contract.cover_frame_count} frames at {contract.fps})"
        )


def probe(path: Path, *, count_frames: bool = False) -> dict[str, Any]:
    command = ["ffprobe", "-v", "error"]
    if count_frames:
        command.append("-count_frames")
    command.extend(
        [
            "-show_entries",
            (
                "format=duration,size:"
                "stream=index,codec_name,codec_type,width,height,pix_fmt,"
                "r_frame_rate,avg_frame_rate,duration,nb_frames,nb_read_frames,"
                "sample_rate,channels"
            ),
            "-of",
            "json",
            str(path),
        ]
    )
    result = run(command)
    return json.loads(result.stdout)


def streams(metadata: dict[str, Any], media_type: str) -> list[dict[str, Any]]:
    return [
        stream
        for stream in metadata.get("streams", [])
        if stream.get("codec_type") == media_type
    ]


def media_duration(metadata: dict[str, Any]) -> float:
    try:
        return float(metadata["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AssemblyError("media has no usable container duration") from exc


def video_frame_count(stream: dict[str, Any]) -> int:
    value = stream.get("nb_read_frames") or stream.get("nb_frames")
    if value in (None, "N/A"):
        raise AssemblyError("ffprobe could not count video frames")
    return int(value)


def full_decode(path: Path) -> None:
    result = run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], check=False)
    if result.returncode != 0:
        raise AssemblyError(f"full decode failed for {path}: {result.stderr.strip()}")


def stream_hash(path: Path, media_type: str) -> str:
    result = run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            f"0:{media_type}:0",
            "-c",
            "copy",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ]
    )
    return result.stdout.strip().removeprefix("SHA256=")


def verify_expected_hash(path: Path, expected: str, label: str) -> str:
    actual = sha256(path)
    if not expected or len(expected) != 64:
        raise AssemblyError(f"{label} approval SHA-256 must be an explicit 64-character digest")
    if actual.lower() != expected.lower():
        raise AssemblyError(f"{label} SHA-256 does not match the approved digest")
    return actual


def ensure_distinct_paths(inputs: list[Path], outputs: list[Path]) -> None:
    resolved_inputs = {path.resolve() for path in inputs}
    resolved_outputs = [path.resolve() for path in outputs]
    if len(set(resolved_outputs)) != len(resolved_outputs):
        raise AssemblyError("all output paths must be distinct")
    collisions = resolved_inputs.intersection(resolved_outputs)
    if collisions:
        raise AssemblyError(f"output would overwrite an immutable input: {next(iter(collisions))}")


def inspect_inputs(
    cover: Path,
    picture: Path,
    narration: Path,
    contract: Contract,
) -> dict[str, Any]:
    for path in (cover, picture, narration):
        if not path.is_file():
            raise AssemblyError(f"required input is missing: {path}")

    cover_probe = probe(cover, count_frames=True)
    picture_probe = probe(picture, count_frames=True)
    narration_probe = probe(narration)
    cover_videos = streams(cover_probe, "video")
    cover_audios = streams(cover_probe, "audio")
    picture_videos = streams(picture_probe, "video")
    picture_audios = streams(picture_probe, "audio")
    narration_videos = streams(narration_probe, "video")
    narration_audios = streams(narration_probe, "audio")
    if len(cover_videos) != 1 or len(cover_audios) != 1:
        raise AssemblyError("prebuilt cover must contain exactly one video and one audio stream")
    if len(picture_videos) != 1 or picture_audios:
        raise AssemblyError("approved picture must contain exactly one video stream and no audio")
    if narration_videos or len(narration_audios) != 1:
        raise AssemblyError("narration master must contain exactly one audio stream and no video")

    cover_video = cover_videos[0]
    cover_audio = cover_audios[0]
    picture_video = picture_videos[0]
    narration_audio = narration_audios[0]
    expected_fps = canonical_fps(contract.fps)
    checks = {
        "cover_video_codec": cover_video.get("codec_name") == contract.cover_video_codec,
        "cover_dimensions": (
            cover_video.get("width") == contract.width
            and cover_video.get("height") == contract.height
        ),
        "cover_fps": canonical_fps(str(cover_video.get("r_frame_rate"))) == expected_fps,
        "cover_frame_count": video_frame_count(cover_video) == contract.cover_frame_count,
        "cover_audio_codec": cover_audio.get("codec_name") == contract.cover_audio_codec,
        "cover_audio_sample_rate": int(cover_audio.get("sample_rate", 0)) == contract.cover_audio_sample_rate_hz,
        "cover_audio_channels": int(cover_audio.get("channels", 0)) == contract.cover_audio_channels,
        "picture_video_codec": picture_video.get("codec_name") == contract.picture_video_codec,
        "picture_dimensions": (
            picture_video.get("width") == contract.width
            and picture_video.get("height") == contract.height
        ),
        "picture_fps": canonical_fps(str(picture_video.get("r_frame_rate"))) == expected_fps,
        "narration_audio_codec": narration_audio.get("codec_name") == contract.narration_audio_codec,
        "narration_sample_rate": int(narration_audio.get("sample_rate", 0)) == contract.narration_sample_rate_hz,
        "narration_channels": int(narration_audio.get("channels", 0)) == contract.narration_channels,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssemblyError("input media contract failed: " + ", ".join(failed))

    fps = Fraction(expected_fps)
    cover_frame_duration = contract.cover_frame_count / float(fps)
    cover_duration = media_duration(cover_probe)
    cover_duration_tolerance = max(0.001, 0.5 / float(fps))
    if abs(cover_duration - contract.cover_duration_sec) > cover_duration_tolerance:
        raise AssemblyError(
            "prebuilt cover duration disagrees with explicit config; refusing a stale/default duration "
            f"({cover_duration:.6f}s media vs {contract.cover_duration_sec:.6f}s config)"
        )
    if abs(cover_frame_duration - contract.cover_duration_sec) > cover_duration_tolerance:
        raise AssemblyError("prebuilt cover frame-locked duration disagrees with explicit config")

    picture_duration = media_duration(picture_probe)
    narration_duration = media_duration(narration_probe)
    picture_narration_delta = narration_duration - picture_duration
    if abs(picture_narration_delta) > contract.duration_tolerance_sec:
        raise AssemblyError(
            "narration/picture duration difference exceeds the configured maximum "
            f"({picture_narration_delta:+.6f}s)"
        )

    for path in (cover, picture, narration):
        full_decode(path)
    return {
        "cover": {
            "probe": cover_probe,
            "duration_sec": cover_duration,
            "frame_count": video_frame_count(cover_video),
        },
        "picture": {
            "probe": picture_probe,
            "duration_sec": picture_duration,
            "frame_count": video_frame_count(picture_video),
        },
        "narration": {
            "probe": narration_probe,
            "duration_sec": narration_duration,
        },
        "picture_narration_duration_delta_sec": picture_narration_delta,
        "checks": checks,
    }


def temporary_media_path(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        prefix=f".{output.stem}.",
        suffix=f".tmp{output.suffix}",
        dir=output.parent,
    )
    os.close(handle)
    Path(name).unlink()
    return Path(name)


def mux_no_cover(
    picture: Path,
    narration: Path,
    output: Path,
    contract: Contract,
) -> list[str]:
    temp = temporary_media_path(output)
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(picture),
        "-i",
        str(narration),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        contract.delivery_audio_bitrate,
        "-ar",
        str(contract.delivery_audio_sample_rate_hz),
        "-ac",
        str(contract.delivery_audio_channels),
        "-movflags",
        "+faststart",
        str(temp),
    ]
    try:
        run(command)
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)
    return command


def assemble_release(
    cover: Path,
    no_cover: Path,
    narration_duration_sec: float,
    output: Path,
    contract: Contract,
) -> list[str]:
    temp = temporary_media_path(output)
    fps = canonical_fps(contract.fps)
    cover_duration = contract.cover_duration_sec
    filter_complex = (
        f"[0:v:0]trim=start_frame=0:end_frame={contract.cover_frame_count},"
        f"setpts=PTS-STARTPTS,fps={fps},format=yuv420p[cover_v];"
        f"[1:v:0]setpts=PTS-STARTPTS,fps={fps},format=yuv420p[main_v];"
        "[cover_v][main_v]concat=n=2:v=1:a=0[release_v];"
        f"[0:a:0]aresample={contract.delivery_audio_sample_rate_hz},"
        f"aformat=sample_rates={contract.delivery_audio_sample_rate_hz}:"
        f"channel_layouts={'stereo' if contract.delivery_audio_channels == 2 else 'mono'},"
        f"apad=whole_dur={cover_duration:.9f},atrim=duration={cover_duration:.9f},"
        "asetpts=PTS-STARTPTS[cover_a];"
        f"[1:a:0]aresample={contract.delivery_audio_sample_rate_hz},"
        f"aformat=sample_rates={contract.delivery_audio_sample_rate_hz}:"
        f"channel_layouts={'stereo' if contract.delivery_audio_channels == 2 else 'mono'},"
        f"atrim=duration={narration_duration_sec:.9f},asetpts=PTS-STARTPTS[main_a];"
        "[cover_a][main_a]concat=n=2:v=0:a=1[release_a]"
    )
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(cover),
        "-i",
        str(no_cover),
        "-filter_complex",
        filter_complex,
        "-map",
        "[release_v]",
        "-map",
        "[release_a]",
        "-c:v",
        contract.release_video_encoder,
        "-preset",
        contract.release_video_preset,
        "-crf",
        str(contract.release_video_crf),
        "-pix_fmt",
        "yuv420p",
        "-r",
        fps,
        "-c:a",
        "aac",
        "-b:a",
        contract.delivery_audio_bitrate,
        "-ar",
        str(contract.delivery_audio_sample_rate_hz),
        "-ac",
        str(contract.delivery_audio_channels),
        "-movflags",
        "+faststart",
        str(temp),
    ]
    try:
        run(command)
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)
    return command


def shift_sync_map(source: dict[str, Any], shift_sec: float) -> dict[str, Any]:
    cue_key = "sentences" if isinstance(source.get("sentences"), list) else "cues"
    source_cues = source.get(cue_key)
    if not isinstance(source_cues, list) or not source_cues:
        raise AssemblyError("planned sync map must contain a non-empty sentences or cues array")

    shifted: list[dict[str, Any]] = []
    for index, cue in enumerate(source_cues, start=1):
        for key in ("actual_start_sec", "actual_end_sec", "scene_start_sec", "scene_end_sec"):
            if key not in cue:
                raise AssemblyError(f"sync cue {index} is missing required timing field: {key}")
        row = dict(cue)
        row["release_actual_start_sec"] = round(shift_sec + float(cue["actual_start_sec"]), 6)
        row["release_actual_end_sec"] = round(shift_sec + float(cue["actual_end_sec"]), 6)
        row["release_scene_start_sec"] = round(shift_sec + float(cue["scene_start_sec"]), 6)
        row["release_scene_end_sec"] = round(shift_sec + float(cue["scene_end_sec"]), 6)
        if "target_start_sec" in cue:
            row["release_target_start_sec"] = round(shift_sec + float(cue["target_start_sec"]), 6)
        shifted.append(row)

    def offset(row: dict[str, Any]) -> float:
        if "actual_offset_from_scene_start_sec" in row:
            return float(row["actual_offset_from_scene_start_sec"])
        return float(row["actual_start_sec"]) - float(row["scene_start_sec"])

    def target_error(row: dict[str, Any]) -> float:
        if "semantic_start_error_sec" in row:
            return float(row["semantic_start_error_sec"])
        if "target_start_sec" in row:
            return float(row["actual_start_sec"]) - float(row["target_start_sec"])
        return offset(row)

    non_bridge = [row for row in shifted if not bool(row.get("is_bridge", False))]
    gaps = [
        float(row["gap_to_next_sec"])
        for row in shifted[:-1]
        if row.get("gap_to_next_sec") is not None
    ]
    overlaps = [
        float(row["scene_overlap_ratio"])
        for row in non_bridge
        if row.get("scene_overlap_ratio") is not None
    ]
    prior_summary = source.get("summary", {})
    summary = {
        **prior_summary,
        "sentence_count": len(shifted),
        "maximum_sentence_gap_sec": round(max(gaps, default=0.0), 6),
        "maximum_non_bridge_scene_start_offset_sec": round(
            max((abs(offset(row)) for row in non_bridge), default=0.0),
            6,
        ),
        "maximum_target_start_error_sec": round(
            max((abs(target_error(row)) for row in shifted), default=0.0),
            6,
        ),
        "minimum_scene_overlap_ratio": round(min(overlaps, default=0.0), 6),
    }
    if isinstance(source.get("groups"), list):
        summary["group_count"] = len(source["groups"])

    story_timeline = dict(source.get("story_timeline", {}))
    story_timeline["picture_timeline_status"] = "approved-silent-picture-assembled"
    release_timeline = {
        "status": "ASSEMBLED_PREBUILT_AUDIBLE_COVER",
        "composition": "strict non-overlapping concatenation",
        "cover_video_start_sec": 0.0,
        "cover_video_end_sec": shift_sec,
        "main_video_start_sec": shift_sec,
        "story_audio_start_sec": shift_sec,
        "main_video_story_audio_delta_sec": 0.0,
        "transition_overlap_sec": 0.0,
    }
    result: dict[str, Any] = {
        "schema_version": 1,
        "mode": "prebuilt_audible_cover_release",
        "story_timeline": story_timeline,
        "release_timeline": release_timeline,
        "summary": summary,
    }
    if isinstance(source.get("groups"), list):
        result["groups"] = source["groups"]
    result["sentences" if cue_key == "sentences" else "cues"] = shifted
    return result


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def inspect_outputs(
    picture: Path,
    no_cover: Path,
    release: Path,
    input_evidence: dict[str, Any],
    contract: Contract,
) -> dict[str, Any]:
    no_cover_probe = probe(no_cover, count_frames=True)
    release_probe = probe(release, count_frames=True)
    no_cover_videos = streams(no_cover_probe, "video")
    no_cover_audios = streams(no_cover_probe, "audio")
    release_videos = streams(release_probe, "video")
    release_audios = streams(release_probe, "audio")
    if not all(
        (
            len(no_cover_videos) == 1,
            len(no_cover_audios) == 1,
            len(release_videos) == 1,
            len(release_audios) == 1,
        )
    ):
        raise AssemblyError("assembled outputs do not each contain exactly one video and one audio stream")

    no_cover_video = no_cover_videos[0]
    no_cover_audio = no_cover_audios[0]
    release_video = release_videos[0]
    release_audio = release_audios[0]
    picture_hash = stream_hash(picture, "v")
    no_cover_hash = stream_hash(no_cover, "v")
    expected_release_frames = (
        contract.cover_frame_count + int(input_evidence["picture"]["frame_count"])
    )
    expected_no_cover_duration = max(
        float(input_evidence["picture"]["duration_sec"]),
        float(input_evidence["narration"]["duration_sec"]),
    )
    expected_release_duration = contract.cover_duration_sec + expected_no_cover_duration
    checks = {
        "no_cover_picture_stream_bit_exact": picture_hash == no_cover_hash,
        "no_cover_picture_frame_count_preserved": (
            video_frame_count(no_cover_video) == int(input_evidence["picture"]["frame_count"])
        ),
        "no_cover_audio_codec_aac": no_cover_audio.get("codec_name") == "aac",
        "no_cover_audio_sample_rate": (
            int(no_cover_audio.get("sample_rate", 0)) == contract.delivery_audio_sample_rate_hz
        ),
        "no_cover_audio_channels": (
            int(no_cover_audio.get("channels", 0)) == contract.delivery_audio_channels
        ),
        "no_cover_duration_within_tolerance": (
            abs(media_duration(no_cover_probe) - expected_no_cover_duration)
            <= contract.duration_tolerance_sec
        ),
        "release_dimensions": (
            release_video.get("width") == contract.width
            and release_video.get("height") == contract.height
        ),
        "release_fps": (
            canonical_fps(str(release_video.get("r_frame_rate"))) == canonical_fps(contract.fps)
        ),
        "release_frame_count": video_frame_count(release_video) == expected_release_frames,
        "release_audio_codec_aac": release_audio.get("codec_name") == "aac",
        "release_audio_sample_rate": (
            int(release_audio.get("sample_rate", 0)) == contract.delivery_audio_sample_rate_hz
        ),
        "release_audio_channels": (
            int(release_audio.get("channels", 0)) == contract.delivery_audio_channels
        ),
        "release_duration_within_tolerance": (
            abs(media_duration(release_probe) - expected_release_duration)
            <= contract.duration_tolerance_sec
        ),
        "main_video_and_story_audio_same_start": (
            abs(contract.main_video_start_sec - contract.story_audio_start_sec)
            <= contract.timeline_tolerance_sec
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssemblyError("assembled output contract failed: " + ", ".join(failed))
    full_decode(no_cover)
    full_decode(release)
    return {
        "checks": checks,
        "picture_video_stream_sha256": picture_hash,
        "no_cover_video_stream_sha256": no_cover_hash,
        "no_cover": {
            "probe": no_cover_probe,
            "duration_sec": media_duration(no_cover_probe),
        },
        "release": {
            "probe": release_probe,
            "duration_sec": media_duration(release_probe),
            "frame_count": video_frame_count(release_video),
        },
        "expected_no_cover_duration_sec": expected_no_cover_duration,
        "expected_release_duration_sec": expected_release_duration,
        "expected_release_frame_count": expected_release_frames,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline-config", type=Path, required=True)
    parser.add_argument("--cover-clip", type=Path, required=True)
    parser.add_argument("--picture", type=Path, required=True)
    parser.add_argument("--narration", type=Path, required=True)
    parser.add_argument("--planned-sync-map", type=Path, required=True)
    parser.add_argument("--no-cover-output", type=Path, required=True)
    parser.add_argument("--release-output", type=Path, required=True)
    parser.add_argument("--release-build-output", type=Path, required=True)
    parser.add_argument("--release-sync-map-output", type=Path, required=True)
    parser.add_argument("--cover-sha256", required=True)
    parser.add_argument("--picture-sha256", required=True)
    parser.add_argument("--narration-sha256", required=True)
    parser.add_argument(
        "--confirm-cover-approved",
        action="store_true",
        help="assert that the exact cover digest has passed normal-speed human approval",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.confirm_cover_approved:
        parser.error(
            "--confirm-cover-approved is required; technical cover QC does not replace "
            "normal-speed human approval"
        )
    for executable in ("ffmpeg", "ffprobe"):
        if not shutil.which(executable):
            raise AssemblyError(f"missing required executable: {executable}")

    contract = load_contract(args.timeline_config)
    validate_contract(contract)
    inputs = [
        args.timeline_config,
        args.cover_clip,
        args.picture,
        args.narration,
        args.planned_sync_map,
    ]
    outputs = [
        args.no_cover_output,
        args.release_output,
        args.release_build_output,
        args.release_sync_map_output,
    ]
    ensure_distinct_paths(inputs, outputs)
    approved_hashes = {
        "cover": verify_expected_hash(args.cover_clip, args.cover_sha256, "cover"),
        "picture": verify_expected_hash(args.picture, args.picture_sha256, "picture"),
        "narration": verify_expected_hash(args.narration, args.narration_sha256, "narration"),
    }
    input_evidence = inspect_inputs(
        args.cover_clip,
        args.picture,
        args.narration,
        contract,
    )
    planned_sync = json.loads(args.planned_sync_map.read_text(encoding="utf-8"))
    release_sync = shift_sync_map(planned_sync, contract.cover_duration_sec)

    no_cover_command = mux_no_cover(
        args.picture,
        args.narration,
        args.no_cover_output,
        contract,
    )
    release_command = assemble_release(
        args.cover_clip,
        args.no_cover_output,
        float(input_evidence["narration"]["duration_sec"]),
        args.release_output,
        contract,
    )
    try:
        output_evidence = inspect_outputs(
            args.picture,
            args.no_cover_output,
            args.release_output,
            input_evidence,
            contract,
        )
    except Exception:
        args.no_cover_output.unlink(missing_ok=True)
        args.release_output.unlink(missing_ok=True)
        raise

    release_sync["assembly_evidence"] = {
        "cover_clip": str(args.cover_clip.resolve()),
        "approved_cover_sha256": approved_hashes["cover"],
        "silent_picture": str(args.picture.resolve()),
        "approved_picture_sha256": approved_hashes["picture"],
        "narration_master": str(args.narration.resolve()),
        "approved_narration_sha256": approved_hashes["narration"],
        "no_cover_voiced": str(args.no_cover_output.resolve()),
        "release_video": str(args.release_output.resolve()),
    }
    build = {
        "schema_version": 1,
        "status": "PASS_TECHNICAL_ASSEMBLY_HUMAN_RELEASE_LISTEN_REQUIRED",
        "contract": asdict(contract),
        "timeline": release_sync["release_timeline"],
        "approved_input_sha256": approved_hashes,
        "input_evidence": input_evidence,
        "output_evidence": output_evidence,
        "commands": {
            "no_cover_mux": no_cover_command,
            "release_concat": release_command,
            "no_cover_uses_shortest": "-shortest" in no_cover_command,
            "no_cover_video_codec_policy": "copy",
        },
        "files": {
            "cover_clip": str(args.cover_clip.resolve()),
            "silent_picture": str(args.picture.resolve()),
            "narration_master": str(args.narration.resolve()),
            "planned_sync_map": str(args.planned_sync_map.resolve()),
            "no_cover_voiced": str(args.no_cover_output.resolve()),
            "release_video": str(args.release_output.resolve()),
            "release_sync_map": str(args.release_sync_map_output.resolve()),
        },
    }
    write_json_atomic(args.release_sync_map_output, release_sync)
    write_json_atomic(args.release_build_output, build)
    print(f"PASS: {args.release_output}")
    print(f"NO_COVER: {args.no_cover_output}")
    print(f"BUILD: {args.release_build_output}")
    print(f"SYNC: {args.release_sync_map_output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssemblyError, FileNotFoundError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        raise SystemExit(2)
