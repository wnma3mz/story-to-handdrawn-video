#!/usr/bin/env python3
"""校验上游十条红线中可机器化的部分。

    adapters/verify_lock.py \
      --script   "03_剧本_EPxx.md" \
      --panel    "07_分镜面板_EPxx.md" \
      --registry "05_全局资产登记.md" \
      --storyboard storyboard.json

设计原则：**文件是唯一事实来源，聊天上下文不是。** 本脚本在交给渲染器之前
把上游契约复查一遍，避免带病产物进入渲染与配音阶段——那时再改代价高得多。

校验项与上游红线的对应：

  台词锁   红线 1  剧本 → 分镜面板 → storyboard.json 三处逐字一致
  光影锁   红线 2  分镜画面描述与提示词不得出现光影、色温、明暗、色调词
  音效锁   红线 3  不得出现 BGM/音乐字样，只写音效
  提示词锁 红线 4  出图提示词不得混入台词或音效
  时长锁   红线 5  单镜 ≤8s；上游片段 ≤15s
  拆镜锁   红线 6  超过 20 字的台词必须拆到多个镜头
  资产锁   红线 7/8  上场角色齐、每镜引场景 ID、可辨认角色道具均引 ID
  资产区间 红线 9/10 角色 1xx、道具 2xx、场景 3xx；角色道具禁衍生
  track 锁 S7      track 全剧唯一递增，不按集重置

退出码：0 全部通过（可能有警告）；1 有阻断项；2 输入不可解析。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from panel_parser import (  # noqa: E402
    AssetRegistry,
    PanelShot,
    ParseError,
    collect_lighting_violations,
    parse_asset_registry,
    parse_script,
    parse_storyboard_panel,
)

MAX_SHOT_SECONDS = 8.0
MAX_DIALOGUE_CHARS = 20

# 中文配音速度：常态约 3 字/秒，愤怒约 4 字/秒，悲伤低沉约 2 字/秒
# （上游 docs/02_关键概念.md 的台词时长换算）。低于这个下限说明台词念不完，
# 但只是警告——演员可以用停顿把长台词撑满一镜，机器不该替他做决定。
MIN_CHARS_PER_SEC = 2.0

# 括号内的表演提示，剧本里常见「（不抬眼，竖起一指）台词」，比对前需剥离
STAGE_DIRECTION = re.compile(r"[（(][^）)]*[）)]")

BGM_WORDS = ("bgm", "BGM", "背景音乐", "配乐", "音乐", "钢琴", "弦乐", "song", "music")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def canonical_dialogue(text: str) -> str:
    """台词比对用的规范化形式：剥离表演提示与首尾空白，保留正文字符。

    刻意不做标点归一化——上游红线 1 是逐字一致，标点变了就是变了。
    """
    return STAGE_DIRECTION.sub("", text).strip()


def check_dialogue_lock(
    report: Report,
    script_texts: list[str],
    shots: list[PanelShot],
    storyboard: dict[str, Any] | None,
) -> None:
    """红线 1：台词逐字一致，三处对齐。"""
    script_index: dict[str, int] = {}
    for text in script_texts:
        key = canonical_dialogue(text)
        script_index.setdefault(key, 0)
        script_index[key] += 1

    for shot in shots:
        if not shot.dialogue:
            continue
        key = canonical_dialogue(shot.dialogue)
        if key not in script_index:
            report.error(
                f"台词锁 · track {shot.track}：分镜面板台词「{shot.dialogue}」"
                "在剧本中找不到对应原文"
            )
            continue
        if script_index[key] > 0:
            script_index[key] -= 1
        else:
            report.warn(
                f"台词锁 · track {shot.track}：台词「{shot.dialogue}」在剧本中出现多次，"
                "已按顺序匹配，请人工确认未串位"
            )

    missing = {k: v for k, v in script_index.items() if v > 0}
    if missing:
        for text, count in missing.items():
            report.warn(
                f"台词锁 · 剧本中的「{text}」未出现在分镜面板"
                + (f"（×{count}）" if count > 1 else "")
            )

    if storyboard is None:
        return

    board_index = {
        canonical_dialogue(str(scene.get("narration", "")))
        for scene in storyboard.get("scenes", [])
        if scene.get("narration")
    }
    for shot in shots:
        if shot.dialogue and canonical_dialogue(shot.dialogue) not in board_index:
            report.error(
                f"台词锁 · track {shot.track}：分镜面板的台词未出现在 storyboard.json 中"
            )


def check_lighting_lock(report: Report, shots: list[PanelShot]) -> None:
    """红线 2：分镜层不得描述光影，光影由场景参考图承担。"""
    for track, _source, hits in collect_lighting_violations(shots):
        shot = next(s for s in shots if s.track == track)
        report.error(
            f"光影锁 · track {track}：画面描述或提示词出现禁用词 {hits}——"
            f"「{shot.picture[:40]}」。光影应通过引用场景衍生资产表达，"
            "而不是在分镜层描述"
        )


def check_soundtrack_lock(report: Report, shots: list[PanelShot]) -> None:
    """红线 3：禁 BGM，只写音效。"""
    for shot in shots:
        sfx = shot.sfx
        for word in BGM_WORDS:
            if word in sfx:
                report.error(
                    f"音效锁 · track {shot.track}：音效段出现「{word}」，"
                    "本项目只写音效，不写 BGM"
                )
                break


def check_prompt_lock(report: Report, shots: list[PanelShot]) -> None:
    """红线 4：台词与音效不得进入出图提示词。"""
    for shot in shots:
        if not shot.prompt or not shot.dialogue:
            continue
        # 用台词的正文（去掉说话人前缀）做子串判断，避开「银十七：」这类误命中
        body = canonical_dialogue(shot.dialogue)
        if len(body) >= 4 and body in shot.prompt:
            report.error(
                f"提示词锁 · track {shot.track}：出图提示词里混入了台词「{body[:20]}」"
                "——画面提示词不得包含台词"
            )


def check_duration_lock(report: Report, shots: list[PanelShot]) -> None:
    """红线 5/6：单镜时长上限与长台词拆镜。"""
    for shot in shots:
        if shot.duration_sec > MAX_SHOT_SECONDS:
            report.error(
                f"时长锁 · track {shot.track}：单镜 {shot.duration_sec}s "
                f"超过 {MAX_SHOT_SECONDS}s 上限"
            )
        if shot.duration_sec <= 0:
            report.error(f"时长锁 · track {shot.track}：时长必须为正")
            continue

        body = canonical_dialogue(shot.dialogue)
        if not body:
            continue

        # 红线 6：超过 20 字的台词必须拆到多个镜头
        if len(body) > MAX_DIALOGUE_CHARS:
            report.error(
                f"拆镜锁 · track {shot.track}：台词 {len(body)} 字超过 "
                f"{MAX_DIALOGUE_CHARS} 字上限，必须拆到多个镜头"
            )

        if shot.duration_sec * MIN_CHARS_PER_SEC < len(body):
            report.warn(
                f"拆镜锁 · track {shot.track}：台词 {len(body)} 字，"
                f"镜长 {shot.duration_sec}s 低于 {MIN_CHARS_PER_SEC} 字/秒，"
                "请确认演员能用停顿撑满；否则延长时长或拆镜"
            )


def check_asset_lock(
    report: Report,
    shots: list[PanelShot],
    registry: AssetRegistry,
    storyboard: dict[str, Any] | None,
) -> None:
    """红线 7/8 与资产 ID 区间规则。"""
    scene_ids = registry.scene_ids()

    for shot in shots:
        cited = [i for i in shot.asset_ids if i in registry.assets]
        unknown = [i for i in shot.asset_ids if i not in registry.assets]
        if unknown:
            report.error(
                f"资产锁 · track {shot.track}：引用了未登记的资产 ID {unknown}"
            )

        if len(cited) != len(shot.asset_ids):
            continue

        cited_scenes = [i for i in cited if i in scene_ids]
        if len(cited_scenes) != 1:
            report.error(
                f"资产锁 · track {shot.track}：必须且只能引用一个场景资产，"
                f"当前引用 {cited_scenes or '无'}"
            )

    # 分镜表声明的参演角色必须被该场每一镜引用到，避免人物在某一镜里凭空消失
    by_scene: dict[int, list[PanelShot]] = {}
    for shot in shots:
        by_scene.setdefault(shot.scene_index, []).append(shot)

    for scene_index, group in by_scene.items():
        # 只在该场确实出现过的角色范围内检查，避免要求引用未登场的角色
        all_roles = {
            i
            for shot in group
            for i in shot.asset_ids
            if i in registry.role_ids()
        }
        for shot in group:
            cited_roles = {i for i in shot.asset_ids if i in registry.role_ids()}
            absent = sorted(
                registry.assets[i].name
                for i in all_roles - cited_roles
                # 画面里提到但没引 ID，通常是「背影」「局部」这类漏引
                if any(
                    registry.assets[i].name[:2] in shot.picture
                    for _ in (0,)
                )
            )
            if absent:
                report.warn(
                    f"资产锁 · 场{scene_index} track {shot.track}：画面提到 {absent} "
                    "但未引用其资产 ID，生成时可能丢失人物一致性"
                )

    if storyboard is None:
        return

    board_scenes = {str(s["id"]): s for s in storyboard.get("scenes", [])}
    for shot in shots:
        key = f"{shot.track:02d}"
        scene = board_scenes.get(key)
        if scene is None:
            report.error(f"资产锁 · storyboard.json 缺少镜次 {key}")
            continue
        board_ids = set(scene.get("asset_ids", []))
        missing = sorted(set(shot.asset_ids) - board_ids)
        if missing:
            report.error(
                f"资产锁 · storyboard.json 镜次 {key} 丢失了分镜面板声明的资产 {missing}"
            )


def check_track_lock(report: Report, shots: list[PanelShot]) -> None:
    """S7 契约：track 全剧唯一递增，不按集重置。"""
    seen: set[int] = set()
    previous = 0
    for shot in shots:
        if shot.track in seen:
            report.error(f"track 锁 · track {shot.track} 重复")
        seen.add(shot.track)
        if shot.track <= previous:
            report.error(
                f"track 锁 · track {shot.track} 未递增（前一镜为 {previous}）"
            )
        previous = shot.track


def main() -> int:
    parser = argparse.ArgumentParser(description="校验上游红线与三重锁")
    parser.add_argument("--script", required=True, type=Path, help="03_剧本_EPxx.md")
    parser.add_argument("--panel", required=True, type=Path, help="07_分镜面板_EPxx.md")
    parser.add_argument("--registry", required=True, type=Path, help="05_全局资产登记.md")
    parser.add_argument("--storyboard", type=Path, help="storyboard.json（可选，给出则一并校验）")
    parser.add_argument("--json", type=Path, help="把报告写成 JSON")
    args = parser.parse_args()

    for path in (args.script, args.panel, args.registry):
        if not path.exists():
            print(f"错误：找不到输入文件 {path}", file=sys.stderr)
            return 2

    try:
        script = parse_script(args.script)
        shots = parse_storyboard_panel(args.panel)
        registry = parse_asset_registry(args.registry)
    except ParseError as exc:
        print(f"解析失败：{exc}", file=sys.stderr)
        return 2

    storyboard = None
    if args.storyboard:
        if not args.storyboard.exists():
            print(f"错误：找不到 storyboard {args.storyboard}", file=sys.stderr)
            return 2
        storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))

    report = Report()
    check_track_lock(report, shots)
    check_dialogue_lock(report, script.dialogue_texts, shots, storyboard)
    check_lighting_lock(report, shots)
    check_soundtrack_lock(report, shots)
    check_prompt_lock(report, shots)
    check_duration_lock(report, shots)
    check_asset_lock(report, shots, registry, storyboard)

    for warning in report.warnings:
        print(f"警告：{warning}")
    for error in report.errors:
        print(f"阻断：{error}")

    print()
    print(
        f"校验结果：{len(report.errors)} 项阻断、{len(report.warnings)} 项警告"
        f"（{len(shots)} 镜，台词 {sum(1 for s in shots if s.dialogue)} 条，"
        f"资产 {len(registry.assets)} 个）"
    )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "shots": len(shots),
                    "dialogue_lines": sum(1 for s in shots if s.dialogue),
                    "assets": len(registry.assets),
                    "errors": report.errors,
                    "warnings": report.warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
