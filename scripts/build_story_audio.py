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
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from story_timeline import compute_scene_timeline


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


def format_vtt_timestamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def write_proportional_vtt(path: Path, cue_texts: list[str], duration: float) -> None:
    texts = [str(text).strip() for text in cue_texts if str(text).strip()]
    if not texts:
        raise ValueError("macos-say requires at least one non-empty cue_text")
    weights = [max(1, len(re.sub(r"\s+", "", text))) for text in texts]
    total_weight = sum(weights)
    cursor = 0.0
    rows = ["WEBVTT", ""]
    for index, (text, weight) in enumerate(zip(texts, weights), start=1):
        end = duration if index == len(texts) else cursor + duration * weight / total_weight
        rows.extend([
            str(index),
            f"{format_vtt_timestamp(cursor)} --> {format_vtt_timestamp(end)}",
            text,
            "",
        ])
        cursor = end
    path.write_text("\n".join(rows), encoding="utf-8")


def lexical_text(value: str) -> str:
    return re.sub(
        r"[\s，。；：！？、,.!?;:“”‘’\"'（）()《》〈〉—…·]",
        "",
        str(value),
    )


def expand_edge_vtt_to_cue_texts(path: Path, cue_texts: list[str]) -> None:
    """Subdivide native Edge sentence cues without cutting the waveform."""
    native = parse_vtt(path)
    targets = [str(value).strip() for value in cue_texts if str(value).strip()]
    if not native or not targets:
        raise ValueError("Edge TTS cue expansion requires native and target cues")

    grouped: list[tuple[dict, list[str]]] = []
    target_index = 0
    for cue in native:
        expected = lexical_text(cue["text"])
        collected: list[str] = []
        combined = ""
        while target_index < len(targets) and len(combined) < len(expected):
            candidate = targets[target_index]
            candidate_lexical = lexical_text(candidate)
            if not expected.startswith(combined + candidate_lexical):
                raise ValueError(
                    "target subtitle cues do not reconstruct the native Edge cue "
                    f"{cue['text']!r}"
                )
            collected.append(candidate)
            combined += candidate_lexical
            target_index += 1
        if combined != expected:
            raise ValueError(
                "target subtitle cues do not fully reconstruct the native Edge cue "
                f"{cue['text']!r}"
            )
        grouped.append((cue, collected))
    if target_index != len(targets):
        raise ValueError("target subtitle cues contain text beyond native Edge cues")

    rows = ["WEBVTT", ""]
    output_index = 1
    for cue, fragments in grouped:
        start = float(cue["start_sec"])
        end = float(cue["end_sec"])
        weights = [max(1, len(lexical_text(fragment))) for fragment in fragments]
        total_weight = sum(weights)
        cursor = start
        for fragment_index, (fragment, weight) in enumerate(
            zip(fragments, weights)
        ):
            fragment_end = (
                end
                if fragment_index == len(fragments) - 1
                else cursor + (end - start) * weight / total_weight
            )
            rows.extend(
                [
                    str(output_index),
                    (
                        f"{format_vtt_timestamp(cursor)} --> "
                        f"{format_vtt_timestamp(fragment_end)}"
                    ),
                    fragment,
                    "",
                ]
            )
            output_index += 1
            cursor = fragment_end
    path.write_text("\n".join(rows), encoding="utf-8")


def synthesize(
    text: str,
    media: Path,
    subtitles: Path,
    profile: dict,
    cue_texts: list[str] | None = None,
) -> None:
    backend = profile.get("backend", "edge-tts")
    if backend == "edge-tts":
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
        if cue_texts:
            expand_edge_vtt_to_cue_texts(subtitles, cue_texts)
        return
    if backend != "macos-say":
        raise ValueError("backend must be edge-tts or macos-say")
    if sys.platform != "darwin" or shutil.which("say") is None:
        raise ValueError("backend=macos-say requires the macOS say command")
    selected_cues = cue_texts or [text]
    with tempfile.TemporaryDirectory(prefix="story-audio-") as temporary:
        aiff = Path(temporary) / "speech.aiff"
        run([
            "say",
            "-v", profile["voice"],
            "-r", str(int(profile.get("speaking_rate_wpm", 165))),
            "-o", str(aiff),
            "--", text,
        ])
        run([
            "ffmpeg", "-y", "-v", "error", "-i", str(aiff),
            "-codec:a", "libmp3lame", "-q:a", "2", str(media),
        ])
    write_proportional_vtt(subtitles, selected_cues, media_duration(media))


def tts_cache_key(
    text: str,
    profile: dict,
    cue_texts: list[str] | None = None,
) -> str:
    payload = json.dumps(
        {"text": text, "profile": profile, "cue_texts": cue_texts},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def synthesize_cached(
    text: str,
    media: Path,
    subtitles: Path,
    profile: dict,
    cache_key_path: Path,
    expected_key: str,
    cue_texts: list[str] | None = None,
) -> None:
    synthesize(text, media, subtitles, profile, cue_texts)
    cache_key_path.write_text(f"{expected_key}\n", encoding="utf-8")


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


def resolve_background_music(config: dict, config_path: Path) -> dict | None:
    music = config.get("background_music", {})
    if not music or not music.get("enabled", False):
        return None

    source_value = str(music.get("path", "")).strip()
    if not source_value:
        raise ValueError("background_music.path is required when BGM is enabled")
    source = Path(source_value).expanduser()
    if not source.is_absolute():
        source = (config_path.parent / source).resolve()
    if not source.is_file():
        raise ValueError(f"background_music.path does not exist: {source}")

    target_lufs = float(music.get("target_lufs", -28.0))
    if not -36.0 <= target_lufs <= -20.0:
        raise ValueError("background_music.target_lufs must stay within -36..-20")
    fade_in_sec = float(music.get("fade_in_sec", 1.2))
    fade_out_sec = float(music.get("fade_out_sec", 2.0))
    if not 0.0 <= fade_in_sec <= 10.0:
        raise ValueError("background_music.fade_in_sec must stay within 0..10")
    if not 0.0 <= fade_out_sec <= 10.0:
        raise ValueError("background_music.fade_out_sec must stay within 0..10")

    ducking = music.get("ducking", {})
    threshold_db = float(ducking.get("threshold_db", -32.0))
    ratio = float(ducking.get("ratio", 8.0))
    attack_ms = float(ducking.get("attack_ms", 25.0))
    release_ms = float(ducking.get("release_ms", 450.0))
    if not -48.0 <= threshold_db <= -12.0:
        raise ValueError("background_music.ducking.threshold_db must stay within -48..-12")
    if not 2.0 <= ratio <= 20.0:
        raise ValueError("background_music.ducking.ratio must stay within 2..20")
    if not 1.0 <= attack_ms <= 200.0:
        raise ValueError("background_music.ducking.attack_ms must stay within 1..200")
    if not 50.0 <= release_ms <= 2000.0:
        raise ValueError("background_music.ducking.release_ms must stay within 50..2000")

    return {
        "path": source,
        "target_lufs": target_lufs,
        "fade_in_sec": fade_in_sec,
        "fade_out_sec": fade_out_sec,
        "threshold": 10 ** (threshold_db / 20.0),
        "threshold_db": threshold_db,
        "ratio": ratio,
        "attack_ms": attack_ms,
        "release_ms": release_ms,
    }


def build_program_master(
    narration_master: Path,
    program_master: Path,
    total_sec: float,
    music: dict | None,
) -> None:
    if music is None:
        shutil.copyfile(narration_master, program_master)
        return

    fade_out_start = max(0.0, total_sec - music["fade_out_sec"])
    bed_filters = [
        "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
        (
            f"loudnorm=I={music['target_lufs']}:TP=-3:LRA=11"
        ),
        f"atrim=duration={total_sec:.6f}",
        "asetpts=PTS-STARTPTS",
    ]
    if music["fade_in_sec"] > 0:
        bed_filters.append(
            f"afade=t=in:st=0:d={min(music['fade_in_sec'], total_sec):.6f}"
        )
    if music["fade_out_sec"] > 0:
        bed_filters.append(
            f"afade=t=out:st={fade_out_start:.6f}:"
            f"d={min(music['fade_out_sec'], total_sec):.6f}"
        )
    filter_complex = ";".join([
        (
            "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:"
            "channel_layouts=stereo[narration]"
        ),
        f"[1:a]{','.join(bed_filters)}[bed]",
        (
            f"[bed][narration]sidechaincompress=threshold={music['threshold']:.8f}:"
            f"ratio={music['ratio']:.3f}:attack={music['attack_ms']:.3f}:"
            f"release={music['release_ms']:.3f}[ducked]"
        ),
        (
            "[narration][ducked]amix=inputs=2:normalize=0:dropout_transition=0,"
            f"apad=whole_dur={total_sec:.6f},atrim=duration={total_sec:.6f},"
            "alimiter=limit=0.891251[program]"
        ),
    ])
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(narration_master),
        "-stream_loop", "-1", "-i", str(music["path"]),
        "-filter_complex", filter_complex, "-map", "[program]",
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", str(program_master),
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", type=Path, default=Path("storyboard.json"))
    parser.add_argument("--episode", type=str, default=os.environ.get("EPISODE", "default"))
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Task-owned root for inputs, caches, and outputs",
    )
    parser.add_argument("--picture", type=Path)
    parser.add_argument("--cover", type=Path)
    parser.add_argument(
        "--approved-cover-candidate",
        type=Path,
        help=(
            "Exact human-approved audible cover MP4 to concatenate before the story. "
            "When supplied, cover title TTS is not regenerated."
        ),
    )
    parser.add_argument(
        "--no-cover-release",
        action="store_true",
        help=(
            "Build narration masters and the no-cover voiced preview only. "
            "Do not synthesize title audio or assemble/copy a release."
        ),
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--tts-concurrency",
        type=int,
        default=int(os.environ.get("TTS_JOBS", "4")),
        help="Parallel connected-group TTS requests (default: 4)",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.no_cover_release and args.approved_cover_candidate:
        parser.error(
            "--no-cover-release cannot be combined with "
            "--approved-cover-candidate"
        )
    if not 1 <= args.tts_concurrency <= 16:
        parser.error("--tts-concurrency must stay within 1..16")

    workspace = (
        args.workspace
        or (Path(os.environ["STORY_VIDEO_WORKSPACE"]) if os.environ.get("STORY_VIDEO_WORKSPACE") else None)
        or Path.cwd()
    ).expanduser().resolve()

    def workspace_path(path: Path) -> Path:
        expanded = path.expanduser()
        return expanded.resolve() if expanded.is_absolute() else (workspace / expanded).resolve()

    episode = args.episode
    if not re.fullmatch(r"[\w.-]+", episode) or episode in {".", ".."}:
        parser.error(
            "--episode may contain only letters, numbers, dots, underscores, and hyphens"
        )
    args.storyboard = workspace_path(args.storyboard)
    args.config = workspace_path(args.config)
    picture = workspace_path(args.picture or Path(f"out/{episode}/silent.mp4"))
    cover = workspace_path(args.cover or Path(f"out/{episode}/cover.png"))
    output = workspace_path(args.output_dir or Path(f"out/{episode}/voiced"))
    args.picture = picture
    args.cover = cover
    output.mkdir(parents=True, exist_ok=True)

    work_dir = workspace / ".work" / episode
    raw_dir = work_dir / "raw-groups"
    group_dir = work_dir / "continuous-groups"
    work_dir = work_dir / "work"
    for directory in (raw_dir, group_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=True)

    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    profile = config["profile"]
    continuity = config["continuity"]
    background_music = resolve_background_music(config, args.config.resolve())
    if not continuity.get("groups"):
        raise ValueError("continuity.groups must contain at least one narration group")

    cover_cfg = config.get("cover") or config.get("release", {})
    cover_voice = cover_cfg.get("cover_voice", {})
    approved_cover_candidate = (
        workspace_path(args.approved_cover_candidate)
        if args.approved_cover_candidate
        else None
    )
    if approved_cover_candidate and not approved_cover_candidate.is_file():
        raise FileNotFoundError(
            f"approved cover candidate not found: {approved_cover_candidate}"
        )
    cover_duration = (
        0.0
        if args.no_cover_release
        else (
            media_duration(approved_cover_candidate)
            if approved_cover_candidate
            else float(
                cover_cfg.get(
                    "duration_sec",
                    cover_cfg.get("cover_duration_sec", 2.7),
                )
            )
        )
    )
    title_text = str(
        cover_cfg.get("title_audio_text")
        or cover_voice.get("text")
        or storyboard["project"]["title"]
    )
    title_profile = {
        **profile,
        **{
            key: cover_voice[key]
            for key in ("rate", "pitch", "volume")
            if key in cover_voice
        },
    }
    title_head = float(
        cover_voice.get("head_sec", cover_cfg.get("title_head_sec", 0.12))
    )
    title_raw = work_dir / "cover-title.mp3"
    title_vtt = work_dir / "cover-title.vtt"
    title_base = work_dir / "cover-title-base.wav"
    title_trimmed = work_dir / "cover-title.wav"

    tts_requests: list[
        tuple[str, Path, Path, dict, Path, str, list[str] | None]
    ] = []
    for group in continuity["groups"]:
        group_id = str(group["id"])
        raw = raw_dir / f"{group_id}.mp3"
        vtt = raw_dir / f"{group_id}.vtt"
        cache_key_path = raw_dir / f"{group_id}.sha256"
        cue_texts = group.get("cue_texts")
        expected_key = tts_cache_key(group["speech_text"], profile, cue_texts)
        cached_key = (
            cache_key_path.read_text(encoding="utf-8").strip()
            if cache_key_path.exists()
            else ""
        )
        if (
            args.force
            or not raw.exists()
            or not vtt.exists()
            or cached_key != expected_key
        ):
            tts_requests.append(
                (
                    group["speech_text"],
                    raw,
                    vtt,
                    profile,
                    cache_key_path,
                    expected_key,
                    cue_texts,
                )
            )
    title_cache_key_path = work_dir / "cover-title.sha256"
    title_cue_texts = [title_text]
    expected_title_key = tts_cache_key(title_text, title_profile, title_cue_texts)
    cached_title_key = (
        title_cache_key_path.read_text(encoding="utf-8").strip()
        if title_cache_key_path.exists()
        else ""
    )
    if (
        not args.no_cover_release
        and approved_cover_candidate is None
        and (
            args.force
            or not title_raw.exists()
            or not title_vtt.exists()
            or cached_title_key != expected_title_key
        )
    ):
        tts_requests.append(
            (
                title_text,
                title_raw,
                title_vtt,
                title_profile,
                title_cache_key_path,
                expected_title_key,
                title_cue_texts,
            )
        )

    fps = int(storyboard["project"]["fps"])
    scenes, total = compute_scene_timeline(storyboard)
    picture_duration = media_duration(args.picture)
    if abs(picture_duration - total) > 0.08:
        raise RuntimeError(
            f"Storyboard is {total:.3f}s but picture is {picture_duration:.3f}s; rebuild or fix the timeline"
        )

    if tts_requests:
        worker_count = min(args.tts_concurrency, len(tts_requests))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(
                    synthesize_cached,
                    text,
                    media,
                    subtitles,
                    selected_profile,
                    cache_key_path,
                    expected_key,
                    cue_texts,
                )
                for (
                    text,
                    media,
                    subtitles,
                    selected_profile,
                    cache_key_path,
                    expected_key,
                    cue_texts,
                ) in tts_requests
            ]
            for future in as_completed(futures):
                future.result()
        print(
            f"Synthesized {len(tts_requests)} connected TTS item(s) "
            f"with {worker_count} worker(s)"
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
    program_master = output / "program-master.wav"
    build_program_master(master, program_master, total, background_music)

    voiced = output / "preview.mp4"
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(args.picture), "-i", str(program_master),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-ar", "48000", "-ac", "2", str(voiced),
    ])

    width = int(storyboard["project"]["width"])
    height = int(storyboard["project"]["height"])
    release = None if args.no_cover_release else output / "release.mp4"
    approved_cover_hash = None
    if args.no_cover_release:
        pass
    elif approved_cover_candidate is not None:
        approved_cover_hash = file_hash(approved_cover_candidate)
        run([
            "ffmpeg", "-y", "-v", "error",
            "-i", str(approved_cover_candidate), "-i", str(voiced),
            "-filter_complex",
            ";".join(
                [
                    f"[0:v]fps={fps},setpts=PTS-STARTPTS,"
                    "format=yuv420p[cv]",
                    f"[1:v]fps={fps},setpts=PTS-STARTPTS,"
                    "format=yuv420p[mv]",
                    "[cv][mv]concat=n=2:v=1:a=0[v]",
                    "[0:a]aresample=48000,asetpts=PTS-STARTPTS[ca]",
                    "[1:a]aresample=48000,asetpts=PTS-STARTPTS[ma]",
                    "[ca][ma]concat=n=2:v=0:a=1[a]",
                ]
            ),
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(release),
        ])
        if file_hash(approved_cover_candidate) != approved_cover_hash:
            raise RuntimeError("approved cover candidate changed during release assembly")
    else:
        title_cues = parse_vtt(title_vtt)
        if not title_cues:
            raise RuntimeError("Cover title TTS did not produce VTT cues")
        title_start = float(title_cues[0]["start_sec"])
        title_end = min(
            media_duration(title_raw),
            float(title_cues[-1]["end_sec"]) + 0.03,
        )
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
                f"Cover title needs {title_tempo:.3f}x tempo, above "
                f"{maximum_title_tempo:.3f}; shorten title_audio_text"
            )
        if title_tempo > 1.0005:
            run([
                "ffmpeg", "-y", "-v", "error", "-i", str(title_base),
                "-af", f"atempo={title_tempo:.8f}", "-ar", "48000", "-ac", "1",
                "-c:a", "pcm_s24le", str(title_trimmed),
            ])
        else:
            shutil.copyfile(title_base, title_trimmed)

        frames = max(1, round(cover_duration * fps))
        cover_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            f"zoompan=z='min(zoom+0.00003,1.008)':d={frames}:"
            f"s={width}x{height}:fps={fps},"
            f"trim=duration={cover_duration:.6f},"
            "setpts=PTS-STARTPTS,format=yuv420p[cv]"
        )
        filter_complex = ";".join([
            f"[0:v]{cover_filter}",
            "[1:v]setpts=PTS-STARTPTS,format=yuv420p[mv]",
            f"[cv][mv]concat=n=2:v=1:a=0[v]",
            f"[2:a]adelay={round(title_head * 1000)}:all=1,"
            f"atrim=duration={cover_duration:.6f},"
            f"afade=t=in:st={title_head:.6f}:d=0.03,"
            f"apad=whole_dur={cover_duration:.6f},"
            f"atrim=duration={cover_duration:.6f}[ca]",
            "[3:a]asetpts=PTS-STARTPTS[ma]",
            "[ca][ma]concat=n=2:v=0:a=1[a]",
        ])
        run([
            "ffmpeg", "-y", "-v", "error", "-loop", "1",
            "-framerate", str(fps),
            "-i", str(args.cover), "-i", str(args.picture),
            "-i", str(title_trimmed), "-i", str(program_master),
            "-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(release),
        ])

    if release is not None:
        releases_dir = workspace / "out" / "releases"
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
        "program_master": str(program_master.resolve()),
        "background_music": (
            {
                "enabled": True,
                "path": str(background_music["path"]),
                "target_lufs": background_music["target_lufs"],
                "fade_in_sec": background_music["fade_in_sec"],
                "fade_out_sec": background_music["fade_out_sec"],
                "ducking": {
                    "threshold_db": background_music["threshold_db"],
                    "ratio": background_music["ratio"],
                    "attack_ms": background_music["attack_ms"],
                    "release_ms": background_music["release_ms"],
                },
            }
            if background_music is not None
            else {"enabled": False}
        ),
        "approved_cover_candidate": (
            {
                "path": str(approved_cover_candidate),
                "sha256": approved_cover_hash,
                "human_approved": True,
                "concatenated_without_regenerating_title_tts": True,
            }
            if approved_cover_candidate is not None
            else None
        ),
        "release_assembled": release is not None,
        "voiced_video": str(voiced.resolve()),
        "release_video": str(release.resolve()) if release is not None else None,
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
        "release_video": str(release) if release is not None else None,
    }, ensure_ascii=False, indent=2))
    return 0 if max_error <= max_allowed_error else 2


if __name__ == "__main__":
    raise SystemExit(main())
