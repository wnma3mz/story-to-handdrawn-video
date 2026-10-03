#!/usr/bin/env python3
"""把编译后的 storyboard.json 转成旁白配置 voiceover.json。

    adapters/compile_narration.py --storyboard storyboard.json --output voiceover.json

为什么不直接用渲染器的 `npm run config:voiceover`：
那个脚本按固定镜数（默认 3 镜一组）切分，而上游分镜表有「场」的概念。
场次切换是天然的旁白停顿点，跨场连读会让配音听起来把两个场景黏在一起。
本脚本改为**按场边界分组**，场内再按字数上限细分。

与渲染器配音契约的衔接（scripts/build_story_audio.py）：
  - 一组一次 TTS，组内不切句、不逐句变速（whole_group_tempo 只能整体微调）
  - cue_texts 与 scene_ids 一一对应，用于字幕切分点测量
  - 无台词镜次填空字符串：build_story_audio 会过滤空 cue，只按非空 cue 切字幕
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 中文配音速度的经验值。上游台词时长换算：常态约 3 字/秒，愤怒约 4 字/秒。
DEFAULT_CHARS_PER_SEC = 3.4

# 单组旁白字数上限。超过则继续细分，避免一个组太长导致字幕同步误差累积。
DEFAULT_MAX_GROUP_CHARS = 46

# 单组覆盖的画面秒数上限。旁白不该横跨太多镜头，否则观众与画面的关系会脱节。
DEFAULT_MAX_GROUP_SEC = 14.0


def group_scenes(
    scenes: list[dict[str, Any]],
    *,
    max_group_chars: int,
    max_group_sec: int,
) -> list[list[dict[str, Any]]]:
    """按场边界分组，场内再按字数与时长上限细分。

    场次边界来自上游分镜表的「场N」标记（编译时写入 upstream_scene_index）。
    没有该字段时退化为按镜序切分。
    """
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_scene: Any = object()
    current_chars = 0
    current_sec = 0.0

    for scene in scenes:
        scene_index = scene.get("upstream_scene_index")
        duration = float(scene.get("duration_sec", 0.0))
        speech = scene.get("narration", "").strip()

        scene_changed = current and scene_index is not None and scene_index != current_scene
        would_overflow = current and (
            current_chars + len(speech) > max_group_chars
            or current_sec + duration > max_group_sec
        )

        if scene_changed or would_overflow:
            groups.append(current)
            current = []
            current_chars = 0
            current_sec = 0.0

        current.append(scene)
        current_scene = scene_index
        current_chars += len(speech)
        current_sec += duration

    if current:
        groups.append(current)
    return groups


def build_voiceover(
    storyboard: dict[str, Any],
    *,
    voice: str,
    rate: str,
    pitch: str,
    volume: str,
    backend: str,
    chars_per_sec: float,
    max_group_chars: int,
    max_group_sec: float,
    group_gap_sec: float,
    initial_head_sec: float,
    minimum_final_tail_sec: float,
    cover_title_audio: str,
    cover_duration_sec: float,
) -> tuple[dict[str, Any], list[str]]:
    scenes = storyboard["scenes"]
    project = storyboard["project"]

    groups = group_scenes(
        scenes, max_group_chars=max_group_chars, max_group_sec=max_group_sec
    )

    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    cursor = initial_head_sec

    for index, group in enumerate(groups, start=1):
        # cue_texts 与 scene_ids 一一对应；无台词镜次留空串，由 build_story_audio 过滤
        cue_texts = [scene.get("narration", "").strip() for scene in group]
        speech_parts = [text for text in cue_texts if text]
        speech_text = "".join(speech_parts)

        if not speech_text:
            warnings.append(
                f"第 {index} 组（镜 {group[0]['id']}-{group[-1]['id']}）整组无台词，"
                "该组不会产生旁白；若本该有旁白，请检查分镜面板的台词段"
            )
            continue

        estimated = len(speech_text) / chars_per_sec
        rows.append(
            {
                "id": f"G{index:02d}",
                "scene_ids": [scene["id"] for scene in group],
                "start_sec": round(cursor, 3),
                "whole_group_tempo": 1.0,
                "speech_text": speech_text,
                "cue_texts": cue_texts,
            }
        )
        cursor += estimated + group_gap_sec

    total_sec = sum(float(scene.get("duration_sec", 0.0)) for scene in scenes)
    available = total_sec - minimum_final_tail_sec
    if rows:
        narration_end = cursor - group_gap_sec
        if narration_end > available:
            warnings.append(
                f"预计旁白在 {narration_end:.1f}s 结束，但画面只有 {available:.1f}s 可用"
                f"（总时长 {total_sec:.1f}s − 尾部留白 {minimum_final_tail_sec}s）。"
                "缩短单组字数、提高 --rate，或延长对应镜次的 duration_sec"
            )

    voiceover = {
        "profile": {
            "backend": backend,
            "voice": voice,
            "rate": rate,
            "pitch": pitch,
            "volume": volume,
        },
        "continuity": {
            "minimum_group_gap_sec": 0.35,
            "maximum_group_gap_sec": max(group_gap_sec, 0.8),
            "ordinary_pause_limit_sec": 1.25,
            "maximum_global_silence_sec": 2.0,
            "minimum_final_tail_sec": minimum_final_tail_sec,
            "maximum_sync_error_sec": 0.6,
            "groups": rows,
        },
        "cover": {
            "duration_sec": cover_duration_sec,
            "title_audio_text": cover_title_audio or project.get("title", ""),
        },
        "background_music": {
            "enabled": False,
            "path": "",
            "target_lufs": -28.0,
            "fade_in_sec": 1.2,
            "fade_out_sec": 2.0,
            "ducking": {
                "threshold_db": -32.0,
                "ratio": 8.0,
                "attack_ms": 25.0,
                "release_ms": 450.0,
            },
        },
        "mastering": {
            "integrated_lufs": -16.0,
            "true_peak_dbtp": -1.5,
            "lra": 7.0,
        },
    }
    return voiceover, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按场次边界把 storyboard.json 转成旁白配置 voiceover.json"
    )
    parser.add_argument("--storyboard", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--backend", default="edge-tts", choices=("edge-tts", "macos-say"))
    parser.add_argument("--voice", default="zh-CN-YunxiNeural")
    parser.add_argument("--rate", default="+8%")
    parser.add_argument("--pitch", default="+0Hz")
    parser.add_argument("--volume", default="+0%")
    parser.add_argument("--chars-per-sec", type=float, default=DEFAULT_CHARS_PER_SEC)
    parser.add_argument("--max-group-chars", type=int, default=DEFAULT_MAX_GROUP_CHARS)
    parser.add_argument("--max-group-sec", type=float, default=DEFAULT_MAX_GROUP_SEC)
    parser.add_argument("--group-gap-sec", type=float, default=0.5)
    parser.add_argument("--initial-head-sec", type=float, default=0.15)
    parser.add_argument("--minimum-final-tail-sec", type=float, default=0.6)
    parser.add_argument("--cover-title-audio", default="")
    parser.add_argument("--cover-duration-sec", type=float, default=2.7)
    args = parser.parse_args()

    if not args.storyboard.exists():
        print(f"错误：找不到 storyboard {args.storyboard}", file=sys.stderr)
        return 2

    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))

    voiceover, warnings = build_voiceover(
        storyboard,
        voice=args.voice,
        rate=args.rate,
        pitch=args.pitch,
        volume=args.volume,
        backend=args.backend,
        chars_per_sec=args.chars_per_sec,
        max_group_chars=args.max_group_chars,
        max_group_sec=args.max_group_sec,
        group_gap_sec=args.group_gap_sec,
        initial_head_sec=args.initial_head_sec,
        minimum_final_tail_sec=args.minimum_final_tail_sec,
        cover_title_audio=args.cover_title_audio,
        cover_duration_sec=args.cover_duration_sec,
    )

    for warning in warnings:
        print(f"警告：{warning}", file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(voiceover, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    groups = voiceover["continuity"]["groups"]
    total_sec = sum(float(s["duration_sec"]) for s in storyboard["scenes"])
    print(
        f"voiceover → {args.output}\n"
        f"  {len(groups)} 个旁白组 / {len(storyboard['scenes'])} 镜 / 画面 {total_sec:.1f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
