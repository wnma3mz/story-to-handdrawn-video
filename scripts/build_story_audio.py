#!/usr/bin/env python3
"""Build continuous narration, an audible cover, and release files from JSON.

Each narration group is synthesized once and remains one uninterrupted waveform.
VTT cues measure semantic alignment; they are never used to cut sentences apart.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


def run(command: list[str], *, attempts: int = 1) -> subprocess.CompletedProcess[str]:
    failure: subprocess.CalledProcessError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return subprocess.run(
                command, check=True, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as exc:
            failure = exc
            if attempt < attempts:
                time.sleep(1.5 * attempt)
    assert failure is not None
    sys.stderr.write(failure.stdout or "")
    sys.stderr.write(failure.stderr or "")
    raise failure


def media_duration(path: Path) -> float:
    result = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(result.stdout.strip())


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_vtt(path: Path) -> list[dict]:
    stamp = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    cues: list[dict] = []
    for index, line in enumerate(lines):
        if "-->" not in line:
            continue
        left, right = line.split("-->", 1)
        starts = stamp.search(left)
        ends = stamp.search(right)
        if not starts or not ends:
            continue

        def seconds(match: re.Match[str]) -> float:
            hour, minute, second, millis = (int(value) for value in match.groups())
            return hour * 3600 + minute * 60 + second + millis / 1000

        text_lines: list[str] = []
        cursor = index + 1
        while cursor < len(lines) and lines[cursor].strip():
            text_lines.append(lines[cursor].strip())
            cursor += 1
        cues.append({
            "start_sec": seconds(starts),
            "end_sec": seconds(ends),
            "text": "".join(text_lines),
        })
    return cues


def synthesize(text: str, media: Path, subtitles: Path, profile: dict) -> None:
    backend = profile.get("backend", "edge-tts")
    if backend != "edge-tts":
        raise ValueError("This portable builder currently requires backend=edge-tts")
    run([
        sys.executable, "-m", "edge_tts",
        "-v", profile["voice"],
        f"--rate={profile.get('rate', '+0%')}",
        f"--pitch={profile.get('pitch', '+0Hz')}",
        f"--volume={profile.get('volume', '+0%')}",
        "-t", text,
        "--write-media", str(media),
        "--write-subtitles", str(subtitles),
    ], attempts=3)


def loudnorm_filter(path: Path, mastering: dict) -> str:
    target_i = float(mastering.get("integrated_lufs", -16.0))
    target_tp = float(mastering.get("true_peak_dbtp", -1.5))
    target_lra = float(mastering.get("lra", 7.0))
    result = run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
        "-f", "null", "-",
    ])
    matches = re.findall(r'\{\s*"input_i".*?\}', result.stderr, flags=re.DOTALL)
    if not matches:
        raise RuntimeError("ffmpeg did not return loudnorm measurements")
    measured = json.loads(matches[-1])
    return (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
        f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true:print_format=summary"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", type=Path, default=Path("storyboard.json"))
    parser.add_argument("--episode", type=str, default=os.environ.get("EPISODE", "default"))
    parser.add_argument("--picture", type=Path)
    parser.add_argument("--cover", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    episode = args.episode
    picture = args.picture or Path(f"out/{episode}/silent.mp4")
    cover = args.cover or Path(f"out/{episode}/cover.png")
    output = args.output_dir or Path(f"out/{episode}/voiced")
    args.picture = picture
    args.cover = cover
    output.mkdir(parents=True, exist_ok=True)

    work_dir = Path(f".work/{episode}")
    raw_dir = work_dir / "raw-groups"
    group_dir = work_dir / "continuous-groups"
    work_dir = work_dir / "work"
    for directory in (raw_dir, group_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=True)

    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    profile = config["profile"]
    continuity = config["continuity"]
    if not continuity.get("groups"):
        raise ValueError("continuity.groups must contain at least one narration group")

    scene_list = storyboard["scenes"]
    fps = int(storyboard["project"]["fps"])
    overlap = 0.0
    if storyboard["project"].get("transition") == "page-flip" and len(scene_list) > 1:
        requested_frames = max(
            1, round(float(storyboard["project"].get("transition_sec", 0.7)) * fps)
        )
        shortest_frames = min(round(float(scene["duration_sec"]) * fps) for scene in scene_list)
        overlap = min(requested_frames, max(1, int(shortest_frames * 0.45))) / fps
    scenes: dict[str, dict] = {}
    cursor = 0.0
    for index, scene in enumerate(scene_list):
        scenes[scene["id"]] = {
            "start_sec": cursor,
            "end_sec": cursor + float(scene["duration_sec"]),
        }
        cursor += float(scene["duration_sec"])
        if index < len(scene_list) - 1:
            cursor -= overlap
    total = cursor
    picture_duration = media_duration(args.picture)
    if abs(picture_duration - total) > 0.08:
        raise RuntimeError(
            f"Storyboard is {total:.3f}s but picture is {picture_duration:.3f}s; rebuild or fix the timeline"
        )

    group_rows: list[dict] = []
    cue_rows: list[dict] = []
    group_paths: list[Path] = []
    for group in continuity["groups"]:
        group_id = str(group["id"])
        raw = raw_dir / f"{group_id}.mp3"
        vtt = raw_dir / f"{group_id}.vtt"
        trimmed = work_dir / f"{group_id}-outer-trim.wav"
        aligned = group_dir / f"{group_id}.wav"
        if args.force or not raw.exists() or not vtt.exists():
            synthesize(group["speech_text"], raw, vtt, profile)
        cues = parse_vtt(vtt)
        scene_ids = group["scene_ids"]
        if len(cues) != len(scene_ids):
            raise RuntimeError(
                f"{group_id}: {len(cues)} VTT cues but {len(scene_ids)} scene_ids; "
                "adjust punctuation so one semantic sentence maps to one scene"
            )
        cue_origin = float(cues[0]["start_sec"])
        outer_end = min(media_duration(raw), float(cues[-1]["end_sec"]) + 0.03)
        run([
            "ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af",
            f"atrim=start={cue_origin:.6f}:end={outer_end:.6f},asetpts=PTS-STARTPTS",
            "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(trimmed),
        ])
        tempo = float(group.get("whole_group_tempo", 1.0))
        if not 0.95 <= tempo <= 1.05:
            raise RuntimeError(f"{group_id}: whole_group_tempo must remain within 0.95..1.05")
        if abs(tempo - 1.0) <= 0.0005:
            shutil.copyfile(trimmed, aligned)
        else:
            run([
                "ffmpeg", "-y", "-v", "error", "-i", str(trimmed),
                "-af", f"atempo={tempo:.8f}", "-ar", "48000", "-ac", "1",
                "-c:a", "pcm_s24le", str(aligned),
            ])
        start = float(group["start_sec"])
        speech_duration = media_duration(aligned)
        end = start + speech_duration
        if end > total - float(continuity.get("minimum_final_tail_sec", 0.5)):
            raise RuntimeError(f"{group_id}: narration clips the final tail at {end:.3f}s")
        group_paths.append(aligned)
        group_rows.append({
            "id": group_id,
            "scene_ids": scene_ids,
            "start_sec": round(start, 3),
            "speech_sec": round(speech_duration, 3),
            "end_sec": round(end, 3),
            "speech_text": group["speech_text"],
            "tts_was_synthesized_as_one_connected_group": True,
            "group_internal_cut_count": 0,
            "sentence_level_tempo_variants": 0,
            "whole_group_tempo": tempo,
            "outer_encoder_silence_trim_only": True,
            "trimmed_group_sha256": file_hash(trimmed),
            "aligned_group_sha256": file_hash(aligned),
            "aligned_bit_identical_to_trimmed_group": file_hash(trimmed) == file_hash(aligned),
            "path": str(aligned.resolve()),
            "vtt": str(vtt.resolve()),
        })
        for cue, scene_id in zip(cues, scene_ids):
            if scene_id not in scenes:
                raise RuntimeError(f"{group_id}: unknown scene id {scene_id}")
            actual = start + (float(cue["start_sec"]) - cue_origin) / tempo
            target = float(scenes[scene_id]["start_sec"])
            cue_rows.append({
                "group_id": group_id,
                "scene_id": scene_id,
                "text": cue["text"],
                "target_start_sec": round(target, 3),
                "actual_start_sec": round(actual, 3),
                "semantic_start_error_sec": round(actual - target, 3),
                "is_bridge": False,
            })

    minimum_gap = float(continuity.get("minimum_group_gap_sec", 0.35))
    maximum_gap = float(continuity.get("maximum_group_gap_sec", 0.8))
    for index, row in enumerate(group_rows[:-1]):
        gap = float(group_rows[index + 1]["start_sec"]) - float(row["end_sec"])
        row["gap_to_next_sec"] = round(gap, 3)
        if not minimum_gap - 0.01 <= gap <= maximum_gap + 0.01:
            raise RuntimeError(
                f"{row['id']}: gap to next group is {gap:.3f}s; expected {minimum_gap:.3f}..{maximum_gap:.3f}s"
            )
    group_rows[-1]["gap_to_next_sec"] = None

    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for index, (path, row) in enumerate(zip(group_paths, group_rows)):
        inputs.extend(["-i", str(path)])
        label = f"g{index}"
        filters.append(f"[{index}:a]adelay={round(float(row['start_sec']) * 1000)}:all=1[{label}]")
        labels.append(f"[{label}]")
    filters.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,"
        + f"apad=whole_dur={total:.6f},atrim=duration={total:.6f},"
        + "highpass=f=70,lowpass=f=15000,"
        + "acompressor=threshold=-20dB:ratio=2:attack=15:release=120[timeline]"
    )
    unmastered = work_dir / "narration-unmastered.wav"
    run([
        "ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters),
        "-map", "[timeline]", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le",
        str(unmastered),
    ])
    master = output / "narration-master.wav"
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(unmastered), "-af",
        loudnorm_filter(unmastered, config.get("mastering", {})),
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(master),
    ])

    voiced = output / "preview.mp4"
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(args.picture), "-i", str(master),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-ar", "48000", "-ac", "2", str(voiced),
    ])

    cover_cfg = config.get("cover") or config.get("release", {})
    cover_voice = cover_cfg.get("cover_voice", {})
    cover_duration = float(cover_cfg.get("duration_sec", cover_cfg.get("cover_duration_sec", 2.7)))
    title_text = str(
        cover_cfg.get("title_audio_text") or cover_voice.get("text") or storyboard["project"]["title"]
    )
    title_profile = {
        **profile,
        **{key: cover_voice[key] for key in ("rate", "pitch", "volume") if key in cover_voice},
    }
    title_head = float(cover_voice.get("head_sec", cover_cfg.get("title_head_sec", 0.12)))
    title_raw = work_dir / "cover-title.mp3"
    title_vtt = work_dir / "cover-title.vtt"
    title_base = work_dir / "cover-title-base.wav"
    title_trimmed = work_dir / "cover-title.wav"
    synthesize(title_text, title_raw, title_vtt, title_profile)
    title_cues = parse_vtt(title_vtt)
    if not title_cues:
        raise RuntimeError("Cover title TTS did not produce VTT cues")
    title_start = float(title_cues[0]["start_sec"])
    title_end = min(media_duration(title_raw), float(title_cues[-1]["end_sec"]) + 0.03)
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(title_raw), "-af",
        f"atrim=start={title_start:.6f}:end={title_end:.6f},asetpts=PTS-STARTPTS",
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(title_base),
    ])
    base_title_duration = media_duration(title_base)
    title_available = cover_duration - title_head - 0.08
    title_tempo = max(1.0, base_title_duration / title_available)
    maximum_title_tempo = float(cover_cfg.get("maximum_title_tempo", 1.15))
    if title_tempo > maximum_title_tempo + 0.001:
        raise RuntimeError(
            f"Cover title needs {title_tempo:.3f}x tempo, above {maximum_title_tempo:.3f}; shorten title_audio_text"
        )
    if title_tempo > 1.0005:
        run([
            "ffmpeg", "-y", "-v", "error", "-i", str(title_base),
            "-af", f"atempo={title_tempo:.8f}", "-ar", "48000", "-ac", "1",
            "-c:a", "pcm_s24le", str(title_trimmed),
        ])
    else:
        shutil.copyfile(title_base, title_trimmed)

    width = int(storyboard["project"]["width"])
    height = int(storyboard["project"]["height"])
    frames = max(1, round(cover_duration * fps))
    release = output / "release.mp4"
    cover_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"zoompan=z='min(zoom+0.00003,1.008)':d={frames}:s={width}x{height}:fps={fps},"
        f"trim=duration={cover_duration:.6f},setpts=PTS-STARTPTS,format=yuv420p[cv]"
    )
    filter_complex = ";".join([
        f"[0:v]{cover_filter}",
        "[1:v]setpts=PTS-STARTPTS,format=yuv420p[mv]",
        f"[cv][mv]concat=n=2:v=1:a=0[v]",
        f"[2:a]adelay={round(title_head * 1000)}:all=1,atrim=duration={cover_duration:.6f},"
        f"afade=t=in:st={title_head:.6f}:d=0.03,"
        f"apad=whole_dur={cover_duration:.6f},atrim=duration={cover_duration:.6f}[ca]",
        "[3:a]asetpts=PTS-STARTPTS[ma]",
        "[ca][ma]concat=n=2:v=0:a=1[a]",
    ])
    run([
        "ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(fps),
        "-i", str(args.cover), "-i", str(args.picture), "-i", str(title_trimmed), "-i", str(master),
        "-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(release),
    ])

    releases_dir = Path("out/releases")
    releases_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(release, releases_dir / f"{episode}.mp4")

    primary_errors = [abs(float(row["semantic_start_error_sec"])) for row in cue_rows]
    max_error = max(primary_errors, default=0.0)
    sync_map = {
        "cues": cue_rows,
        "summary": {"maximum_non_bridge_scene_start_offset_sec": round(max_error, 3)},
        "release_timeline": {
            "cover_duration_sec": cover_duration,
            "main_video_start_sec": cover_duration,
            "story_audio_start_sec": cover_duration,
            "main_video_story_audio_delta_sec": 0.0,
        },
    }
    build = {
        "config": str(args.config.resolve()),
        "layout": "continuous_groups_synced",
        "groups": group_rows,
        "total_sec": total,
        "master": str(master.resolve()),
        "voiced_video": str(voiced.resolve()),
        "release_video": str(release.resolve()),
    }
    (output / "build.json").write_text(json.dumps(build, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "sync-map.json").write_text(json.dumps(sync_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    max_allowed_error = float(
        continuity.get("maximum_sync_error_sec", continuity.get("maximum_semantic_start_error_sec", 0.6))
    )
    print(json.dumps({
        "status": "PASS" if max_error <= max_allowed_error else "REVIEW",
        "maximum_sync_error_sec": round(max_error, 3),
        "master": str(master),
        "voiced_video": str(voiced),
        "release_video": str(release),
    }, ensure_ascii=False, indent=2))
    return 0 if max_error <= max_allowed_error else 2


if __name__ == "__main__":
    raise SystemExit(main())
