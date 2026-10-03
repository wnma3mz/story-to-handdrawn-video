#!/usr/bin/env python3
"""把 storyboard.json 的镜次区间换算成 qc/frame_metrics.py 与 qc/motion_check.py 的输入。

这两个量化质检脚本来自 anything2explainer，用的是「显式帧区间」接口
（`--shots SC11:1627-1806,SC12:1852-1965`），原本由 a2e 自己解析 `分镜表.md` 得到。
本项目没有 `分镜表.md`，区间要从 storyboard.json 算，因此加这一层适配。

帧区间必须与渲染器完全一致，所以这里复用渲染器自己的时间轴算法
（scripts/story_timeline.py），而不是另写一份四舍五入。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from story_timeline import compute_scene_timeline  # noqa: E402


def shot_ranges(storyboard_path: Path) -> tuple[list[tuple[str, int, int]], float, int]:
    """返回 ([(镜次ID, 起始帧, 结束帧)], 总秒数, 总帧数)。

    帧号从 1 起，与 ffmpeg 抽帧出来的 f_%04d.jpg 对齐。
    """
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    timeline, total_sec = compute_scene_timeline(storyboard)
    fps = int(storyboard["project"]["fps"])

    ranges: list[tuple[str, int, int]] = []
    for scene_id, info in timeline.items():
        # 渲染器的帧号从 0 起，ffmpeg 抽帧出的 f_%04d.jpg 从 1 起，两边差 1
        lo = int(info["start_frame"]) + 1
        hi = int(info["end_frame"])
        ranges.append((str(scene_id), lo, hi))
    total_frames = round(total_sec * fps)
    return ranges, total_sec, total_frames


def main() -> int:
    parser = argparse.ArgumentParser(
        description="输出 frame_metrics / motion_check 需要的镜次帧区间"
    )
    parser.add_argument("--storyboard", required=True, type=Path)
    parser.add_argument(
        "--format",
        choices=("shots", "tsv", "json"),
        default="shots",
        help="shots 供 --shots 参数；tsv 供 motion_check；json 供程序消费",
    )
    args = parser.parse_args()

    if not args.storyboard.exists():
        print(f"错误：找不到 storyboard {args.storyboard}", file=sys.stderr)
        return 2

    ranges, total_sec, total_frames = shot_ranges(args.storyboard)

    if args.format == "shots":
        print(",".join(f"{sid}:{lo}-{hi}" for sid, lo, hi in ranges))
    elif args.format == "tsv":
        for sid, lo, hi in ranges:
            print(f"{sid}\t{(hi - lo + 1) / 30:.2f}s\t{sid}\thold")
    else:
        print(
            json.dumps(
                {
                    "fps": 30,
                    "total_sec": total_sec,
                    "total_frames": total_frames,
                    "shots": [
                        {"id": sid, "from": lo, "to": hi} for sid, lo, hi in ranges
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
