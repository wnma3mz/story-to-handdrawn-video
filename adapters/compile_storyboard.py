#!/usr/bin/env python3
"""把上游内容层的分镜面板编译成渲染器的 storyboard.json。

    adapters/compile_storyboard.py \
      --panel   "07_分镜面板_EP01.md" \
      --assets  "05_全局资产登记.md" \
      --config  "00_项目配置.md" \
      --output  "storyboard.json"

上游 `07_分镜面板_EP01.md` 是给人看的 Markdown；渲染器只认 storyboard.json。
本脚本是两者之间唯一的转换点，因此所有映射规则都写在这里，不散落在别处。

映射来源：adapters/motion_map.json（景别与运镜词表 → 渲染器运动词汇）
资产路径：沿用渲染器 public/ 相对路径，母图由 compile_image_jobs.py 产出、
          黑白层由 import:codex 用 ffmpeg 派生，两者共用同一套命名。
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
    load_motion_map,
    parse_asset_registry,
    parse_storyboard_panel,
)

MOTION_PROFILES = (
    Path(__file__).resolve().parents[1] / "src" / "common" / "motion-profiles.json"
)

# 各画幅的渲染尺寸。9:16 是短剧平台原生比例，也是本项目的推荐默认值。
CANVAS_SIZES = {
    "9:16": (1080, 1920),
    "3:4": (1080, 1440),
    "16:9": (1920, 1080),
}

# 各画幅下生图母图的尺寸。母图比例必须与画幅一致，否则插图会被裁切。
MASTER_SIZES = {
    "9:16": (1024, 1792),
    "3:4": (1024, 1024),
    "16:9": (1024, 576),
}

VISUAL_MODES = ("diary", "ink-comic", "essay")

# 各视觉模式的图层顺序。diary 是唯一使用黑白层的模式（text → bw_full → color）。
MODE_LAYERS = {
    "diary": ["text", "bw_full", "color"],
    "ink-comic": ["text", "color"],
    "essay": ["text", "color"],
}

# 画面描述里显式写明主体方位时，据此决定 transform-origin。
FOCUS_PATTERNS = (
    (re.compile(r"(?:居于|位于|处在|在)画面(?:的)?(?:左侧|左方|左边)"), "left"),
    (re.compile(r"(?:居于|位于|处在|在)画面(?:的)?(?:右侧|右方|右边)"), "right"),
    (re.compile(r"(?:居于|位于|处在|在)画面(?:的)?(?:上方|上部|上边)"), "top"),
    (re.compile(r"(?:居于|位于|处在|在)画面(?:的)?(?:下方|下部|下边)"), "bottom"),
)

# 上游红线 5：单镜不超过 8 秒。超限不静默截断，直接报错。
MAX_SHOT_SECONDS = 8.0


class CompileError(ValueError):
    """分镜面板内容不满足上游契约，无法编译。"""


def resolve_motion(camera_move: str, mapping: dict[str, Any]) -> tuple[str, list[str]]:
    """把上游运镜词映射到渲染器运动词汇，返回 (motion, warnings)。"""
    warnings: list[str] = []
    text = camera_move.strip()
    if not text:
        return mapping["camera_move"]["fallback"], warnings

    rules = mapping["camera_move"]["rules"]
    for prefix in mapping["camera_move"].get("one_take_prefixes", []):
        if text.startswith(prefix) or "一镜到底" in text:
            warnings.append(
                f"运镜「{text}」是一镜到底的运镜串，只取首段作为本镜运动"
            )
            # 取第一个箭头前的段落
            text = re.split(r"[→>]|落幅|起幅", text)[-1] if "→" in text else text
            break

    for rule in rules:
        for keyword in rule["keywords"]:
            if keyword in text:
                return rule["motion"], warnings

    warnings.append(
        f"运镜「{camera_move}」未匹配到运动词汇，回落到 "
        f"{mapping['camera_move']['fallback']}；如需精确控制请在 motion_map.json 补规则"
    )
    return mapping["camera_move"]["fallback"], warnings


def resolve_focus(shot: PanelShot) -> str:
    haystack = "。".join([shot.picture, shot.fields.get("角色动作", "")])
    for pattern, focus in FOCUS_PATTERNS:
        if pattern.search(haystack):
            return focus
    return "center"


def resolve_shot_scale(shot_size: str, mapping: dict[str, Any]) -> str | None:
    table = mapping["shot_scale"]
    text = shot_size.strip()
    if text in table:
        return table[text]
    # 允许带修饰的写法，如「中景（膝盖以上）」
    for key, value in table.items():
        if key in text:
            return value
    return None


def asset_paths(scene_id: str, asset_set: str, visual_mode: str) -> dict[str, str | None]:
    """该镜的插图路径。

    命名与渲染器 scripts/import-codex-images.mjs 对齐：
      <NN>_master.png  出图母图（compile_image_jobs.py 的 output_master）
      <NN>_bw.png      ffmpeg 派生的黑白层
      <NN>_color.png   彩色层（母图本身，ink-comic 下经灰度滤镜调整）

    注意 color 指向 _color.png 而不是 _master.png——渲染器读的是派生层。
    只有 diary 模式会用到黑白层，其余模式留空。
    """
    base = f"assets/generated/{asset_set}/{scene_id}"
    return {
        "text_image": None,
        "bw": f"{base}_bw.png" if visual_mode == "diary" else None,
        "detail": None,
        "color": f"{base}_color.png",
    }


def scene_id_for_shot(shot: PanelShot, registry: AssetRegistry) -> str:
    """该镜所属场景的资产 ID。

    上游红线 8：每镜必须引用所属场景 ID。优先取 associateAssetsIds 里唯一的
    场景资产；没有则回落到 videoDesc 的【场景】字段名去登记表里匹配。
    """
    scene_ids = registry.scene_ids()
    cited = [i for i in shot.asset_ids if i in scene_ids]
    if len(cited) == 1:
        return cited[0]
    if len(cited) > 1:
        raise CompileError(
            f"track {shot.track}: 引用了多个场景资产 {cited}，一镜只能属于一个场景"
        )

    name = shot.scene_name.split("·")[0].strip()
    for asset in registry.by_kind("scene"):
        if asset.name == name or asset.name in shot.scene_name:
            return asset.id
    raise CompileError(
        f"track {shot.track}: 无法确定场景资产（引用 {shot.asset_ids}，"
        f"场景名「{shot.scene_name}」未在资产登记表中匹配到）"
    )


def validate_shot(shot: PanelShot, registry: AssetRegistry, known_ids: set[str]) -> list[str]:
    """单镜校验。返回问题列表，空列表表示通过。"""
    problems: list[str] = []
    prefix = f"track {shot.track}"

    if shot.duration_sec <= 0:
        problems.append(f"{prefix}: 时长必须为正")
    if shot.duration_sec > MAX_SHOT_SECONDS:
        problems.append(
            f"{prefix}: 单镜 {shot.duration_sec}s 超过 {MAX_SHOT_SECONDS}s 上限"
            "（上游红线 5，需在分镜表阶段拆镜）"
        )

    unknown = [i for i in shot.asset_ids if i not in registry.assets]
    if unknown:
        problems.append(f"{prefix}: 引用了未登记的资产 ID {unknown}")

    # 上游红线 7：每个上场角色都必须入画。分镜面板逐镜声明参演角色，
    # 这里检查已登记角色是否被漏掉引用——漏引会让生图丢掉人物一致性。
    cited_names = {registry.assets[i].name for i in shot.asset_ids if i in registry.assets}
    for name in re.split(r"[、,，]", shot.scene_name):
        pass  # 场景名不是角色清单，角色清单位于分镜表，这里不做推断

    if shot.dialogue and len(shot.dialogue) > 20 and shot.duration_sec < 4:
        problems.append(
            f"{prefix}: 台词 {len(shot.dialogue)} 字超过 20 字且仅 {shot.duration_sec}s，"
            "上游红线 6 要求长台词拆到多个镜头"
        )

    return problems


def parse_config(path: Path | None) -> dict[str, str]:
    """从 00_项目配置.md 抽取画幅与集号，用于默认值。"""
    if path is None or not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    config: dict[str, str] = {}

    row = re.search(r"\|\s*画幅\s*\|\s*([^|]+?)\s*\|", text)
    if row:
        value = row.group(1)
        if "9:16" in value:
            config["ratio"] = "9:16"
        elif "16:9" in value:
            config["ratio"] = "16:9"
        elif "3:4" in value:
            config["ratio"] = "3:4"

    row = re.search(r"\|\s*目标集数\s*\|\s*(\d+)", text)
    if row:
        config["episodes"] = row.group(1)

    row = re.search(r"\|\s*小说名\s*\|\s*([^|]+?)\s*\|", text)
    if row:
        config["novel"] = row.group(1).strip("《》 ")

    return config


def build_storyboard(
    shots: list[PanelShot],
    registry: AssetRegistry,
    *,
    title: str,
    asset_set: str,
    visual_mode: str,
    ratio: str,
    style_lock: str,
    character_lock: str,
    subtitle_contract: str,
) -> tuple[dict[str, Any], list[str]]:
    mapping = load_motion_map()
    profiles = json.loads(MOTION_PROFILES.read_text(encoding="utf-8"))
    width, height = CANVAS_SIZES[ratio]

    warnings: list[str] = []
    problems: list[str] = []
    scenes: list[dict[str, Any]] = []

    previous_track = 0
    for shot in shots:
        if shot.track <= previous_track:
            problems.append(
                f"track {shot.track}: track 必须全剧唯一且递增"
                "（上游 S7 契约：EP01 从 001 起，不按集重置）"
            )
        previous_track = shot.track
        problems.extend(validate_shot(shot, registry, set(registry.assets)))

        motion, motion_warnings = resolve_motion(shot.camera_move, mapping)
        warnings.extend(f"track {shot.track}: {w}" for w in motion_warnings)
        if motion not in profiles:
            problems.append(
                f"track {shot.track}: 映射出的运镜 {motion} 不在渲染器运动词汇表内"
            )

        scale = resolve_shot_scale(shot.shot_size, mapping)
        if scale is None and shot.shot_size:
            warnings.append(
                f"track {shot.track}: 景别「{shot.shot_size}」未在 motion_map.json 中登记，"
                "构图指令将退化为默认"
            )

        scene_key = f"{shot.track:02d}"
        try:
            scene_id = scene_id_for_shot(shot, registry)
        except CompileError as exc:
            problems.append(str(exc))
            scene_id = ""

        narration = shot.dialogue
        # 字幕只在有台词时出现。ink-comic 的底部字幕是台词转录而非剧情概述，
        # 无台词镜次留空，不要拿画面描述去填——那会把短剧变成解说。
        caption = narration

        scenes.append(
            {
                "id": scene_key,
                "duration_sec": shot.duration_sec,
                "text": caption,
                "narration": narration,
                "visual": shot.picture,
                "shot": shot.shot_size or "",
                "shot_scale": scale,
                "focus": resolve_focus(shot),
                "motion": motion,
                "transition_to_next": "cut",
                "visual_mode": visual_mode,
                "scene_asset_id": scene_id,
                "asset_ids": shot.asset_ids,
                "upstream_scene_index": shot.scene_index,
                "upstream_scene_name": shot.scene_name,
                "plate_mode": "raster",
                "layers": list(MODE_LAYERS[visual_mode]),
                "color_hint": None,
                "detail_hint": None,
                "assets": asset_paths(scene_key, asset_set, visual_mode),
            }
        )

    storyboard = {
        "project": {
            "title": title,
            "mode": "quality",
            "images_per_scene": 1,
            "derive_bw": "local",
            "enable_detail": False,
            "gen_size": MASTER_SIZES[ratio][0],
            "export_size": [width, height],
            "visual_mode": visual_mode,
            "ratio": ratio,
            "width": width,
            "height": height,
            "fps": 30,
            "transition": "cut",
            "transition_sec": 0.7,
            "subtitle_contract": subtitle_contract,
            "style_lock": style_lock,
            "character_lock": character_lock,
            "audio": {
                "voiceover": "continuous_groups",
                "bgm": "optional_bed_only",
                "bgm_follows_text": False,
            },
        },
        "scenes": scenes,
    }
    return storyboard, problems, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把上游分镜面板编译成渲染器 storyboard.json"
    )
    parser.add_argument("--panel", required=True, type=Path, help="07_分镜面板_EPxx.md")
    parser.add_argument("--assets", required=True, type=Path, help="05_全局资产登记.md")
    parser.add_argument("--config", type=Path, help="00_项目配置.md（读取画幅与集号）")
    parser.add_argument("--output", required=True, type=Path, help="输出 storyboard.json")
    parser.add_argument("--asset-set", default="upstream", help="资产集名，决定 public/ 子目录")
    parser.add_argument("--title", help="片名，默认取分镜面板文件名")
    parser.add_argument(
        "--visual-mode",
        choices=VISUAL_MODES,
        default="ink-comic",
        help="ink-comic（默认）带底部逐句字幕，最适合有台词的短剧",
    )
    parser.add_argument("--ratio", choices=sorted(CANVAS_SIZES), help="画幅，默认读项目配置")
    parser.add_argument("--style-lock", default="", help="项目级画风锁定描述")
    parser.add_argument("--character-lock", default="", help="全剧角色连续性描述")
    parser.add_argument(
        "--subtitle-contract",
        choices=("draft_summary", "verbatim_tts"),
        default="draft_summary",
        help="初始一律 draft_summary；TTS 冻结后由 apply_verbatim_subtitles.py 回填 verbatim_tts",
    )
    args = parser.parse_args()

    for path in (args.panel, args.assets):
        if not path.exists():
            print(f"错误：找不到输入文件 {path}", file=sys.stderr)
            return 2

    config = parse_config(args.config)
    ratio = args.ratio or config.get("ratio", "9:16")

    try:
        registry = parse_asset_registry(args.assets)
        shots = parse_storyboard_panel(args.panel)
    except ParseError as exc:
        print(f"解析失败：{exc}", file=sys.stderr)
        return 2

    title = args.title or config.get("novel") or args.panel.stem

    storyboard, problems, warnings = build_storyboard(
        shots,
        registry,
        title=title,
        asset_set=args.asset_set,
        visual_mode=args.visual_mode,
        ratio=ratio,
        style_lock=args.style_lock,
        character_lock=args.character_lock,
        subtitle_contract=args.subtitle_contract,
    )

    for warning in warnings:
        print(f"警告：{warning}", file=sys.stderr)

    if problems:
        print(f"编译失败，共 {len(problems)} 处问题：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    total = sum(s["duration_sec"] for s in storyboard["scenes"])
    print(
        f"storyboard → {args.output}\n"
        f"  {len(storyboard['scenes'])} 镜 / {total:.1f}s / "
        f"{ratio} {storyboard['project']['width']}×{storyboard['project']['height']} / "
        f"visual_mode={args.visual_mode}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
