#!/usr/bin/env python3
"""Build a technical audible-cover candidate without assembling a release.

The script is deliberately story-agnostic.  It reads the narrator and cover
title contract from an episode JSON config, consumes an already-approved
cover.png, and writes only cover-local artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List


SCHEMA = "audible-cover-candidate/v1"


class BuildError(RuntimeError):
    pass


def run(command: List[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        raise BuildError(f"command failed ({result.returncode}): {' '.join(command)}\n{detail}")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: Path) -> Dict[str, Any]:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )
    return json.loads(result.stdout)


def media_duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def stream_for(data: Dict[str, Any], kind: str) -> Dict[str, Any]:
    matches = [stream for stream in data["streams"] if stream.get("codec_type") == kind]
    if len(matches) != 1:
        raise BuildError(f"expected exactly one {kind} stream, found {len(matches)}")
    return matches[0]


def parse_loudnorm_raw(text: str) -> Dict[str, str]:
    blocks = re.findall(r"\{\s*\"input_i\".*?\}", text, flags=re.DOTALL)
    if not blocks:
        raise BuildError("ffmpeg loudnorm did not emit JSON")
    return json.loads(blocks[-1])


def parse_loudnorm(text: str) -> Dict[str, float]:
    raw = parse_loudnorm_raw(text)
    return {
        "integrated_lufs": float(raw["input_i"]),
        "true_peak_dbtp": float(raw["input_tp"]),
        "loudness_range_lu": float(raw["input_lra"]),
    }


def loudness(path: Path) -> Dict[str, float]:
    result = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=7:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture=True,
    )
    return parse_loudnorm((result.stdout or "") + (result.stderr or ""))


def loudnorm_measurement(
    path: Path, target_i: float, target_tp: float, target_lra: float
) -> Dict[str, str]:
    result = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            (
                f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
                "print_format=json"
            ),
            "-f",
            "null",
            "-",
        ],
        capture=True,
    )
    return parse_loudnorm_raw((result.stdout or "") + (result.stderr or ""))


def render_loudnorm_master(source: Path, output: Path, plan: Dict[str, Any]) -> None:
    measured = loudnorm_measurement(
        source,
        plan["target_lufs"],
        plan["target_true_peak"],
        plan["target_lra"],
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-af",
            (
                f"loudnorm=I={plan['target_lufs']}:TP={plan['target_true_peak']}:"
                f"LRA={plan['target_lra']}:"
                f"measured_I={measured['input_i']}:"
                f"measured_LRA={measured['input_lra']}:"
                f"measured_TP={measured['input_tp']}:"
                f"measured_thresh={measured['input_thresh']}:"
                f"offset={measured['target_offset']}:"
                "linear=true:print_format=summary"
            ),
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s24le",
            str(output),
        ]
    )


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def vtt_text(path: Path) -> str:
    rows: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if (
            not line
            or line == "WEBVTT"
            or "-->" in line
            or line.isdigit()
            or line.startswith("NOTE")
        ):
            continue
        rows.append(re.sub(r"<[^>]+>", "", line))
    return "".join(rows)


def choose_effective_duration(
    configured_sec: float,
    natural_title_sec: float,
    head_sec: float,
    tail_sec: float,
    fps: int,
    maximum_extension_sec: float,
) -> Dict[str, Any]:
    if min(configured_sec, natural_title_sec, head_sec, tail_sec) < 0 or fps <= 0:
        raise BuildError("durations must be non-negative and fps must be positive")
    required = head_sec + natural_title_sec + tail_sec
    target = max(configured_sec, required)
    frames = max(2, math.ceil(target * fps - 1e-9))
    effective = frames / fps
    extension = effective - configured_sec
    if extension > maximum_extension_sec + 1e-9:
        raise BuildError(
            f"natural title needs a {extension:.3f}s cover extension, above "
            f"the {maximum_extension_sec:.3f}s safety limit"
        )
    return {
        "configured_duration_sec": round(configured_sec, 6),
        "natural_title_duration_sec": round(natural_title_sec, 6),
        "head_sec": round(head_sec, 6),
        "minimum_tail_sec": round(tail_sec, 6),
        "required_duration_sec": round(required, 6),
        "effective_duration_sec": round(effective, 6),
        "effective_frame_count": frames,
        "override_applied": extension > 1e-6,
        "extension_sec": round(max(0.0, extension), 6),
        "override_reason": (
            "natural_title_plus_head_and_tail_did_not_fit"
            if required > configured_sec + 1e-9
            else ("frame_alignment" if extension > 1e-6 else None)
        ),
        "whole_title_tempo": 1.0,
        "atempo_filter_used": False,
        "last_syllable_trimmed": False,
    }


def decode_check(path: Path, log_path: Path) -> bool:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-map",
            "0",
            "-f",
            "null",
            "-",
        ],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    log_path.write_text(result.stderr or "", encoding="utf-8")
    return result.returncode == 0 and not (result.stderr or "").strip()


def first_frame_luma(video: Path) -> float:
    result = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-vf",
            "select=eq(n\\,0),signalstats,metadata=print:file=-",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ],
        capture=True,
    )
    match = re.search(
        r"lavfi\.signalstats\.YAVG=([0-9.]+)",
        (result.stdout or "") + (result.stderr or ""),
    )
    if not match:
        raise BuildError("could not measure first-frame YAVG")
    return float(match.group(1))


def video_stream_hash(path: Path) -> str:
    result = run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-c",
            "copy",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        capture=True,
    )
    value = result.stdout.strip()
    if not value.startswith("SHA256="):
        raise BuildError("could not hash video elementary stream")
    return value.split("=", 1)[1]


def parse_motion_delta(value: str) -> float:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", value or "")
    delta = float(match.group(1)) / 100 if match else 0.006
    if not 0.003 <= delta <= 0.008:
        raise BuildError("cover motion must stay within the SOP's 0.3%..0.8% push range")
    return delta


def load_plan(config_path: Path, cover_path: Path) -> Dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    profile = config.get("profile") or {}
    release = config.get("release") or config.get("cover") or {}
    cover_voice = release.get("cover_voice") or {}
    if profile.get("backend") != "edge-tts":
        raise BuildError("minimal candidate builder currently requires profile.backend=edge-tts")
    for key in ("voice",):
        if not profile.get(key):
            raise BuildError(f"profile.{key} is required")
    if not cover_voice.get("text"):
        raise BuildError("release.cover_voice.text is required")
    cover_probe = probe(cover_path)
    video = stream_for(cover_probe, "video")
    fps = int(release.get("fps", 30))
    mastering = config.get("mastering") or {}
    return {
        "config": config,
        "profile": profile,
        "release": release,
        "cover_voice": cover_voice,
        "title_text": str(cover_voice["text"]),
        "voice": str(cover_voice.get("voice", profile["voice"])),
        "rate": str(cover_voice.get("rate", profile.get("rate", "+0%"))),
        "pitch": str(cover_voice.get("pitch", profile.get("pitch", "+0Hz"))),
        "volume": str(cover_voice.get("volume", profile.get("volume", "+0%"))),
        "configured_duration_sec": float(
            release.get("duration_sec", release.get("cover_duration_sec", 2.7))
        ),
        "head_sec": float(cover_voice.get("head_sec", 0.15)),
        "tail_sec": max(0.2, float(cover_voice.get("tail_sec", 0.15))),
        "fps": fps,
        "width": int(video["width"]),
        "height": int(video["height"]),
        "motion_delta": parse_motion_delta(str(release.get("cover_motion", ""))),
        "first_frame_max_yavg": float(release.get("first_frame_max_yavg", 200.0)),
        "target_lufs": float(mastering.get("integrated_lufs", -16.0)),
        "loudness_tolerance_lu": float(
            mastering.get("integrated_lufs_tolerance_lu", 1.0)
        ),
        "target_true_peak": float(mastering.get("true_peak_dbtp", -1.5)),
        "target_lra": float(mastering.get("lra", 7.0)),
    }


def build(args: argparse.Namespace) -> Dict[str, Any]:
    config_path = args.config.resolve()
    cover_path = args.cover.resolve()
    if not config_path.is_file() or not cover_path.is_file():
        raise BuildError("config and cover must be existing files")
    plan = load_plan(config_path, cover_path)
    protected_before = {str(path.resolve()): sha256(path.resolve()) for path in args.protect}
    dry = {
        "schema": SCHEMA,
        "mode": "dry-run",
        "config": str(config_path),
        "cover": str(cover_path),
        "output_dir": str(args.output_dir.resolve()),
        "title_text": plan["title_text"],
        "voice": plan["voice"],
        "configured_duration_sec": plan["configured_duration_sec"],
        "human_listen": "PENDING",
        "release_assembled": False,
    }
    if args.dry_run:
        return dry

    output = args.output_dir.resolve()
    if output.exists():
        raise BuildError(f"output directory already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.build-", dir=str(output.parent)))
    complete = False
    try:
        raw = staging / "raw"
        work = staging / "work"
        evidence = staging / "evidence"
        for directory in (raw, work, evidence):
            directory.mkdir()
        raw_media = raw / "cover-title.mp3"
        raw_vtt = raw / "cover-title.vtt"
        run(
            [
                sys.executable,
                "-m",
                "edge_tts",
                "--voice",
                plan["voice"],
                f"--rate={plan['rate']}",
                f"--pitch={plan['pitch']}",
                f"--volume={plan['volume']}",
                "--text",
                plan["title_text"],
                "--write-media",
                str(raw_media),
                "--write-subtitles",
                str(raw_vtt),
            ]
        )
        if normalize_text(vtt_text(raw_vtt)) != normalize_text(plan["title_text"]):
            raise BuildError("edge-tts VTT text does not exactly match cover_voice.text")

        natural = work / "cover-title-outer-trim.wav"
        trim_filter = (
            "silenceremove=start_periods=1:start_duration=0.01:start_threshold=-50dB:"
            "start_silence=0.02,areverse,"
            "silenceremove=start_periods=1:start_duration=0.03:start_threshold=-50dB:"
            "start_silence=0.05,areverse"
        )
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(raw_media),
                "-af",
                trim_filter,
                "-ar",
                "48000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s24le",
                str(natural),
            ]
        )
        natural_duration = media_duration(natural)
        fit = choose_effective_duration(
            plan["configured_duration_sec"],
            natural_duration,
            plan["head_sec"],
            plan["tail_sec"],
            plan["fps"],
            args.maximum_extension_sec,
        )
        effective = float(fit["effective_duration_sec"])
        frames = int(fit["effective_frame_count"])

        unmastered = work / "cover-title-unmastered.wav"
        master = staging / "cover-title-master.wav"
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(natural),
                "-af",
                (
                    "afade=t=in:st=0:d=0.015,"
                    f"adelay={round(plan['head_sec'] * 1000)}:all=1,"
                    f"apad=whole_dur={effective:.6f},atrim=duration={effective:.6f},"
                    f"afade=t=out:st={max(0.0, effective - 0.015):.6f}:d=0.015"
                ),
                "-ar",
                "48000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s24le",
                str(unmastered),
            ]
        )
        render_loudnorm_master(unmastered, master, plan)
        conditioning = {
            "applied": False,
            "scope": "whole_title",
            "reason": None,
            "filter": None,
        }
        initial_master_loudness = loudness(master)
        if (
            initial_master_loudness["integrated_lufs"]
            < plan["target_lufs"] - plan["loudness_tolerance_lu"]
            and initial_master_loudness["true_peak_dbtp"]
            >= plan["target_true_peak"] - 0.1
        ):
            conditioned = work / "cover-title-conditioned.wav"
            compressor = (
                "acompressor=threshold=0.125:ratio=3:"
                "attack=5:release=120:makeup=1"
            )
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(unmastered),
                    "-af",
                    compressor,
                    "-ar",
                    "48000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s24le",
                    str(conditioned),
                ]
            )
            render_loudnorm_master(conditioned, master, plan)
            conditioning = {
                "applied": True,
                "scope": "whole_title",
                "reason": "true_peak_ceiling_prevented_loudness_target",
                "filter": compressor,
                "initial_master_loudness": initial_master_loudness,
            }

        visual = staging / "cover-visual.mp4"
        progress = f"on/{frames - 1}"
        zoom = (
            f"1+{plan['motion_delta']:.8f}*"
            f"(3*pow({progress},2)-2*pow({progress},3))"
        )
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-loop",
                "1",
                "-framerate",
                str(plan["fps"]),
                "-i",
                str(cover_path),
                "-vf",
                (
                    f"scale={plan['width'] * 2}:{plan['height'] * 2}:flags=lanczos,"
                    f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':"
                    f"y='ih/2-(ih/zoom/2)':d=1:"
                    f"s={plan['width'] * 2}x{plan['height'] * 2}:fps={plan['fps']},"
                    f"scale={plan['width']}:{plan['height']}:flags=lanczos,"
                    "setsar=1,format=yuv420p"
                ),
                "-frames:v",
                str(frames),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "16",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(visual),
            ]
        )
        candidate = staging / "audible-cover-candidate.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(visual),
                "-i",
                str(master),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(candidate),
            ]
        )

        candidate_probe = probe(candidate)
        video = stream_for(candidate_probe, "video")
        audio = stream_for(candidate_probe, "audio")
        master_probe = stream_for(probe(master), "audio")
        video_duration = float(video.get("duration") or candidate_probe["format"]["duration"])
        audio_duration = float(audio.get("duration") or candidate_probe["format"]["duration"])
        visual_hash = video_stream_hash(visual)
        candidate_hash = video_stream_hash(candidate)
        master_loudness = loudness(master)
        candidate_loudness = loudness(candidate)
        yavg = first_frame_luma(candidate)
        checks = {
            "vtt_text_exact_match": True,
            "whole_sentence_single_tts_request": True,
            "no_atempo_filter_used": not fit["atempo_filter_used"],
            "last_syllable_preserved": not fit["last_syllable_trimmed"],
            "master_pcm_s24le_48khz_mono": (
                master_probe.get("codec_name") == "pcm_s24le"
                and int(master_probe.get("sample_rate", 0)) == 48000
                and int(master_probe.get("channels", 0)) == 1
            ),
            "master_duration_matches_cover_within_50ms": (
                abs(media_duration(master) - effective) <= 0.05
            ),
            "candidate_h264_aac_48khz_stereo": (
                video.get("codec_name") == "h264"
                and audio.get("codec_name") == "aac"
                and int(audio.get("sample_rate", 0)) == 48000
                and int(audio.get("channels", 0)) == 2
            ),
            "candidate_audio_video_delta_within_50ms": (
                abs(audio_duration - video_duration) <= 0.05
            ),
            "candidate_video_bit_exact_to_visual": visual_hash == candidate_hash,
            "first_frame_non_white": yavg <= plan["first_frame_max_yavg"],
            "master_full_decode": decode_check(master, evidence / "master-decode.log"),
            "visual_full_decode": decode_check(visual, evidence / "visual-decode.log"),
            "candidate_full_decode": decode_check(
                candidate, evidence / "candidate-decode.log"
            ),
            "master_loudness_near_target": (
                abs(master_loudness["integrated_lufs"] - plan["target_lufs"])
                <= plan["loudness_tolerance_lu"]
            ),
            "master_true_peak_within_ceiling": (
                master_loudness["true_peak_dbtp"] <= plan["target_true_peak"] + 0.1
            ),
        }
        protected_after = {path: sha256(Path(path)) for path in protected_before}
        checks["protected_inputs_unchanged"] = protected_before == protected_after
        status = (
            "PASS_TECHNICAL_HUMAN_LISTEN_PENDING"
            if all(checks.values())
            else "FAIL_TECHNICAL"
        )
        report = {
            "schema": SCHEMA,
            "status": status,
            "human_review": {
                "normal_speed_title_listen": "PENDING",
                "human_approved": False,
            },
            "scope": {
                "cover_candidate_only": True,
                "release_assembled": False,
                "story_video_muxed": False,
            },
            "inputs": {
                "config": str(config_path),
                "config_sha256": sha256(config_path),
                "cover": str(cover_path),
                "cover_sha256": sha256(cover_path),
                "protected": protected_after,
            },
            "title": {
                "text": plan["title_text"],
                "backend": "edge-tts",
                "invocation": f"{sys.executable} -m edge_tts",
                "voice": plan["voice"],
                "rate": plan["rate"],
                "pitch": plan["pitch"],
                "volume": plan["volume"],
                "tts_request_count": 1,
                "raw_media_sha256": sha256(raw_media),
                "raw_vtt_sha256": sha256(raw_vtt),
                "outer_trimmed_sha256": sha256(natural),
                "master_sha256": sha256(master),
                "master_loudness": master_loudness,
                "whole_title_dynamic_conditioning": conditioning,
                "mastering_contract": {
                    "target_integrated_lufs": plan["target_lufs"],
                    "integrated_lufs_tolerance_lu": plan["loudness_tolerance_lu"],
                    "true_peak_ceiling_dbtp": plan["target_true_peak"],
                    "peak_limited": (
                        master_loudness["true_peak_dbtp"]
                        >= plan["target_true_peak"] - 0.1
                    ),
                },
            },
            "duration_fit": fit,
            "visual": {
                "motion": f"{plan['motion_delta'] * 100:g}% eased center push",
                "width": int(video["width"]),
                "height": int(video["height"]),
                "fps": video.get("avg_frame_rate"),
                "frames": int(video.get("nb_frames") or frames),
                "first_frame_yavg": yavg,
                "first_frame_max_yavg": plan["first_frame_max_yavg"],
                "visual_sha256": sha256(visual),
                "visual_elementary_stream_sha256": visual_hash,
            },
            "candidate": {
                "path": str(output / candidate.name),
                "sha256": sha256(candidate),
                "video_duration_sec": round(video_duration, 6),
                "audio_duration_sec": round(audio_duration, 6),
                "audio_video_delta_sec": round(abs(audio_duration - video_duration), 6),
                "video_elementary_stream_sha256": candidate_hash,
                "audio_loudness": candidate_loudness,
            },
            "artifacts": {
                "title_master": str(output / master.name),
                "candidate": str(output / candidate.name),
                "qc": str(output / "cover-qc.json"),
            },
            "checks": checks,
        }
        (staging / "cover-qc.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if status != "PASS_TECHNICAL_HUMAN_LISTEN_PENDING":
            failed = [key for key, value in checks.items() if not value]
            raise BuildError(
                "technical cover gates failed: "
                + ", ".join(failed)
                + f"; master_loudness={master_loudness}; "
                + f"target_lufs={plan['target_lufs']}"
            )
        for directory in (raw, work, evidence):
            shutil.rmtree(directory)
        visual.unlink()
        staging.rename(output)
        complete = True
        return report
    finally:
        if not complete and staging.exists():
            shutil.rmtree(staging)


def parse_args(argv: Iterable[str] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an audible cover candidate only; never assemble a release."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--cover", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--protect", action="append", type=Path, default=[])
    parser.add_argument("--maximum-extension-sec", type=float, default=1.5)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Iterable[str] = None) -> int:
    args = parse_args(argv)
    try:
        result = build(args)
    except (BuildError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
