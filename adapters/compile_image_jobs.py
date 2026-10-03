#!/usr/bin/env python3
"""把上游的资产登记与资产提示词编译成渲染器的出图依赖图。

    adapters/compile_image_jobs.py \
      --registry   "05_全局资产登记.md" \
      --prompts    "05_资产提示词.md" \
      --panel      "07_分镜面板_EPxx.md" \
      --storyboard "storyboard.json" \
      --output     "codex-image-jobs.json" \
      --prompt-dir "prompts/generated/upstream"

产出与渲染器 scripts/story-to-video.mjs 完全同构的 codex-image-jobs.json，
因此下游的 `npm run import:codex`、image:plan、image:register 全部照常可用。

依赖图分三级，严格按拓扑序：

    references（角色 1xx 四视图 + 道具 2xx 四宫格）   并发 1
        ↓
    shots（每镜一张合成图，引用该镜声明的全部资产）    并发 N

场景 3xx 单独作为第三级：场景主视图自带全部光影（上游红线 2 的归属方），
镜次合成图以场景主视图为底再叠人物与道具，避免每镜重画一次场景导致光影漂移。
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
    Asset,
    AssetRegistry,
    ParseError,
    load_motion_map,
    parse_asset_registry,
    parse_storyboard_panel,
)

# 三类资产的出图规格，对应上游 art_skills 的 art_character / art_prop / art_scene。
KIND_SPEC = {
    "role": {
        "role": "reference",
        "stage": "references",
        "aspect": "4:1",
        "master_size": None,
        "gate": "四视图设定图：素颜、基础服装、无配饰、月白背景 #E8EAF5、四视图一致",
    },
    "tool": {
        "role": "reference",
        "stage": "references",
        "aspect": "1:1",
        "master_size": None,
        "gate": "四宫格纯静物：无人、无手、无肢体，不处于被握持或佩戴状态",
    },
    "scene": {
        "role": "reference",
        "stage": "scenes",
        "aspect": None,
        "master_size": None,
        "gate": "单画面主视图：无人，前中后景分层，本镜全部光影由该图承担",
    },
}

_ASSET_PROMPT_HEADING = re.compile(
    r"^#{2,4}\s*(?P<id>[0-9]+(?:-[A-Za-z0-9]+)?)\s*(?P<name>.*?)\s*$"
)
_FENCE = re.compile(r"^```")


class CompileError(ValueError):
    pass


def parse_asset_prompts(path: Path) -> dict[str, str]:
    """解析 05_资产提示词.md，返回 {资产ID: 提示词正文}。

    章节标题形如 `### 101 舒十七（男主）`，后面紧跟一个围栏代码块。
    """
    prompts: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    opened = False

    def flush() -> None:
        nonlocal current, lines, opened
        if current is not None:
            prompts[current] = "\n".join(lines).strip()
        current = None
        lines = []
        opened = False

    for raw in path.read_text(encoding="utf-8").splitlines():
        heading = _ASSET_PROMPT_HEADING.match(raw.strip())
        if heading and not raw.strip().startswith("```"):
            flush()
            current = heading.group("id")
            continue

        if current is None:
            continue

        if _FENCE.match(raw.strip()):
            if opened:
                flush()
                continue
            opened = True
            continue

        if opened:
            lines.append(raw)

    flush()
    return prompts


def asset_job_id(asset: Asset) -> str:
    return f"asset_{asset.id.replace('-', '_')}"


def scene_job_id(shot_key: str) -> str:
    return shot_key


def relative_to_public(path: Path, public_dir: Path) -> str:
    try:
        return path.resolve().relative_to(public_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def build_jobs(
    registry: AssetRegistry,
    asset_prompts: dict[str, str],
    shots: list[Any],
    storyboard: dict[str, Any],
    *,
    asset_set: str,
    prompt_dir: Path,
    public_dir: Path,
    style_lock: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """构造全部出图任务，返回 (jobs, problems)。"""
    problems: list[str] = []
    jobs: list[dict[str, Any]] = []
    master_size = storyboard["project"].get("gen_size")
    ratio = storyboard["project"]["ratio"]

    def prompt_path(asset_id: str) -> Path:
        return prompt_dir / f"asset_{asset_id.replace('-', '_')}.txt"

    def shot_prompt_path(shot_key: str) -> Path:
        return prompt_dir / f"{shot_key}_master.txt"

    def write_prompt(path: Path, body: str) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.strip() + "\n", encoding="utf-8")
        return str(path)

    # ---- 第一级：角色与道具参考图 -------------------------------------
    for asset in sorted(
        registry.by_kind("role") + registry.by_kind("tool"),
        key=lambda a: a.numeric_id or 0,
    ):
        prompt = asset_prompts.get(asset.id)
        if not prompt:
            problems.append(f"资产 {asset.id} {asset.name}：05_资产提示词.md 中缺少提示词")
            continue

        spec = KIND_SPEC[asset.kind]
        master = public_dir / "assets" / "generated" / asset_set / f"asset_{asset.id.replace('-', '_')}.png"
        target = write_prompt(prompt_path(asset.id), prompt)
        jobs.append(
            {
                "id": asset_job_id(asset),
                "role": spec["role"],
                "stage": spec["stage"],
                "kind": asset.kind,
                "asset_id": asset.id,
                "depends_on": [],
                "prompt_file": target,
                "prompt": prompt,
                "output_master": str(master),
                "references": [],
                "aspect": spec["aspect"],
                "gate": spec["gate"],
            }
        )

    # ---- 第二级：场景主视图 -------------------------------------------
    # 每镜只引用自己用到的场景；未被任何镜次引用的场景资产不生成，省一次出图。
    used_scene_ids: list[str] = []
    for shot in shots:
        for scene_id in shot.asset_ids:
            if scene_id in registry.scene_ids() and scene_id not in used_scene_ids:
                used_scene_ids.append(scene_id)

    for scene_id in used_scene_ids:
        asset = registry.assets[scene_id]
        prompt = asset_prompts.get(scene_id)
        if not prompt:
            problems.append(f"场景 {scene_id} {asset.name}：05_资产提示词.md 中缺少提示词")
            continue

        master = public_dir / "assets" / "generated" / asset_set / f"scene_{scene_id.replace('-', '_')}.png"
        target = write_prompt(prompt_path(scene_id), prompt)
        jobs.append(
            {
                "id": f"scene_{scene_id.replace('-', '_')}",
                "role": "reference",
                "stage": "scenes",
                "kind": "scene",
                "asset_id": scene_id,
                # 场景主视图按规格「无人物、无道具」，因此不依赖任何参考图。
                # 若在此挂上角色参考图，生图模型会把人物画进场景，破坏「无人」约束。
                "depends_on": [],
                "prompt_file": target,
                "prompt": prompt,
                "output_master": str(master),
                "references": [],
                "aspect": ratio,
                "gate": KIND_SPEC["scene"]["gate"],
            }
        )

    # ---- 第三级：逐镜合成图 -------------------------------------------
    motion_map = load_motion_map()
    composition_table = motion_map["shot_scale_composition"]

    storyboard_scenes = {s["id"]: s for s in storyboard["scenes"]}

    for shot in shots:
        shot_key = f"{shot.track:02d}"
        scene_meta = storyboard_scenes.get(shot_key)
        if scene_meta is None:
            problems.append(f"track {shot.track}：storyboard.json 中没有对应镜次 {shot_key}")
            continue

        if not shot.should_generate_image:
            # shouldGenerateImage=false 的镜次复用上一镜的图，不生成新任务
            continue

        scene_id = scene_meta["scene_asset_id"]
        deps: list[str] = []
        references: list[str] = []
        for asset_id in shot.asset_ids:
            if asset_id not in registry.assets:
                continue
            if asset_id == scene_id:
                continue
            deps.append(asset_job_id(registry.assets[asset_id]))
            references.append(
                str(
                    public_dir
                    / "assets"
                    / "generated"
                    / asset_set
                    / f"asset_{asset_id.replace('-', '_')}.png"
                )
            )
        if scene_id:
            deps.append(f"scene_{scene_id.replace('-', '_')}")
            references.append(
                str(
                    public_dir
                    / "assets"
                    / "generated"
                    / asset_set
                    / f"scene_{scene_id.replace('-', '_')}.png"
                )
            )

        composition = composition_table.get(scene_meta.get("shot_scale") or "", "")
        body = build_shot_prompt(shot, registry, style_lock, composition)

        master = (
            public_dir
            / "assets"
            / "generated"
            / asset_set
            / f"{shot_key}_master.png"
        )
        target = write_prompt(shot_prompt_path(shot_key), body)
        jobs.append(
            {
                "id": scene_job_id(shot_key),
                "role": "scene",
                "stage": "shots",
                "kind": "shot",
                "shot_id": shot_key,
                "depends_on": sorted(set(deps)),
                "prompt_file": target,
                "prompt": body,
                "output_master": str(master),
                "references": references,
                "aspect": ratio,
                "master_size": master_size,
                "gate": "首帧构图：主体占画面主位，场景光影与场景主视图一致，人物外观与角色四视图一致",
            }
        )

    return jobs, problems


def build_shot_prompt(
    shot: Any,
    registry: AssetRegistry,
    style_lock: str,
    composition: str,
) -> str:
    """把分镜面板的 videoDesc 与提示词合成一条可直接出图的提示词。

    上游提示词里的 `@图N` 是给人读的占位符，这里换成具名资产，
    并附上明确的构图指令（景别）与参考图清单。
    """
    cited = [registry.assets[i] for i in shot.asset_ids if i in registry.assets]
    roles = [a for a in cited if a.kind == "role"]
    props = [a for a in cited if a.kind == "tool"]
    scenes = [a for a in cited if a.kind == "scene"]

    lines: list[str] = []
    lines.append(f"镜次 {shot.track:02d}｜{shot.scene_name}")
    lines.append(f"景别：{shot.shot_size}" + (f"（{composition}）" if composition else ""))
    lines.append(f"运镜：{shot.camera_move}")
    if shot.emotion:
        lines.append(f"情绪：{shot.emotion}")
    lines.append("")

    if roles:
        lines.append(
            "人物参考（须与参考图的面部特征、发型、服饰完全一致）："
            + "、".join(f"{a.id} {a.name}" for a in roles)
        )
    if props:
        lines.append("道具参考：" + "、".join(f"{a.id} {a.name}" for a in props))
    if scenes:
        lines.append(
            "场景参考（光影、构图基底一律以该图为准，不得另设光照）："
            + "、".join(f"{a.id} {a.name}" for a in scenes)
        )
    lines.append("")

    lines.append("画面：" + shot.picture)
    action = shot.fields.get("角色动作")
    if action and action not in ("空镜", "—"):
        lines.append("动作：" + action)
    lines.append("")

    if shot.prompt:
        lines.append("分镜提示词：")
        lines.append(shot.prompt)
        lines.append("")

    if style_lock:
        lines.append(f"画风锁定：{style_lock}")

    lines.append(
        "硬约束：画面内不得出现字幕、字幕条、水印、标题叠字、页码；"
        "不得凭空添加未列出的角色或道具；不得改变场景参考图的光影方向与色温。"
    )
    return "\n".join(lines)


def topological_check(jobs: list[dict[str, Any]]) -> list[str]:
    """确认 depends_on 全部指向已存在的任务，且无环。"""
    problems: list[str] = []
    known = {job["id"] for job in jobs}
    for job in jobs:
        for dep in job["depends_on"]:
            if dep not in known:
                problems.append(f"任务 {job['id']} 依赖不存在的 {dep}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把上游资产提示词与分镜面板编译成出图依赖图 codex-image-jobs.json"
    )
    parser.add_argument("--registry", required=True, type=Path, help="05_全局资产登记.md")
    parser.add_argument("--prompts", required=True, type=Path, help="05_资产提示词.md")
    parser.add_argument("--panel", required=True, type=Path, help="07_分镜面板_EPxx.md")
    parser.add_argument("--storyboard", required=True, type=Path, help="compile_storyboard.py 的产物")
    parser.add_argument("--output", required=True, type=Path, help="codex-image-jobs.json")
    parser.add_argument("--prompt-dir", required=True, type=Path, help="提示词落盘目录")
    parser.add_argument("--public-dir", default=Path("public"), help="渲染器 public 目录")
    parser.add_argument("--asset-set", default="upstream")
    parser.add_argument("--jobs", type=int, default=4, help="并发出图上限")
    parser.add_argument("--style-lock", default="")
    args = parser.parse_args()

    for path in (args.registry, args.prompts, args.panel, args.storyboard):
        if not path.exists():
            print(f"错误：找不到输入文件 {path}", file=sys.stderr)
            return 2

    try:
        registry = parse_asset_registry(args.registry)
        shots = parse_storyboard_panel(args.panel)
        asset_prompts = parse_asset_prompts(args.prompts)
    except ParseError as exc:
        print(f"解析失败：{exc}", file=sys.stderr)
        return 2

    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))

    jobs, problems = build_jobs(
        registry,
        asset_prompts,
        shots,
        storyboard,
        asset_set=args.asset_set,
        prompt_dir=args.prompt_dir,
        public_dir=args.public_dir,
        style_lock=args.style_lock,
    )
    problems.extend(topological_check(jobs))

    if problems:
        print(f"编译失败，共 {len(problems)} 处问题：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    manifest = {
        "version": 1,
        "generator": "codex-image2",
        "source": "upstream-content-layer",
        "visual_mode": storyboard["project"].get("visual_mode"),
        "master_size": storyboard["project"].get("gen_size"),
        "asset_set": args.asset_set,
        "storyboard": str(args.storyboard),
        "execution": {
            "max_concurrency": args.jobs,
            "stages": [
                {"id": "references", "roles": ["reference"], "max_concurrency": 1},
                {"id": "scenes", "roles": ["reference"], "max_concurrency": 1},
                {"id": "shots", "roles": ["scene"], "max_concurrency": args.jobs},
            ],
        },
        "jobs": jobs,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    counts: dict[str, int] = {}
    for job in jobs:
        counts[job["stage"]] = counts.get(job["stage"], 0) + 1
    summary = "、".join(f"{stage} {count}" for stage, count in counts.items())
    print(f"image jobs → {args.output}\n  共 {len(jobs)} 个任务：{summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
