# content/ — 上游内容生产线

本目录是**上游内容层（L1）**，负责把原始文本变成结构化的、可渲染的中间产物。
它不渲染视频，不生成图片，只产出 Markdown 与 JSON。

## 来源

全部内容提取自 **[Toonflow-app](https://github.com/HBAI-Ltd/Toonflow-app)**（MIT），
经 [toonflow-adapter-kit](https://github.com/wnma3mz/toonflow-adapter-kit)
整理为无运行时依赖的提示词工具包后原样并入。**文件内容未做修改。**

- `AGENTS_upstream.md` — 上游 S0–S8 阶段契约原文
- `skills/` — 183 个提示词文件，原项目提取
- `docs/` — 流程详解、关键概念、快速上手、Agent 标准作业流程
- `templates/` — 新项目建档模板
- `examples/中间人/` — EP01 实跑样例（S1–S7 全链路）

## 三维正交提示词

`skills/` 的设计核心是三条互相正交的轴，运行时按项目配置组装：

```
题材  skills/story_skills/    12 类   → 叙事技法（景别偏好、节奏、反转套路）
× 画风  skills/art_skills/     11 种   → 视觉技法（色板、风格锚点、资产图规格）
× 制作  skills/production_skills/ 2 个  → 与题材画风无关的通用方法
```

换掉任意一轴，管线骨架不变。示例组合：`Xianxia_fantasy`（武侠归入此类的导演
叙事技法）× `2D_chinese_guofeng`。

## L1 产物如何接到渲染器

L1 停在 Markdown，`adapters/` 负责把它编译成渲染器认识的格式：

| L1 产物 | 编译器 | 渲染器格式 |
|---|---|---|
| `03_剧本_EPxx.md` | `adapters/compile_narration.py` | `narration.txt`（TTS 输入） |
| `05_资产提示词.md` | `adapters/compile_image_jobs.py` | `codex-image-jobs.json`（出图依赖图） |
| `07_分镜面板_EPxx.md` | `adapters/compile_storyboard.py` | `storyboard.json`（渲染器输入） |
| 全部 | `adapters/verify_lock.py` | 三重锁校验：台词逐字、资产 ID 合法、时长不超限 |

## 十条红线（跨阶段不变量）

L1 与渲染器共享同一组硬约束，违反即视为不合格：

1. 台词逐字一致 —— 剧本 → 分镜表 → 分镜面板 → storyboard.json → 字幕
2. 分镜表与分镜提示词**禁止**出现光影、色温、明暗、色调词；光影只由场景参考图承载
3. 无 BGM，音效单独标注
4. 台词与音效不得进入出图提示词
5. 片段 ≤15s，单镜 ≤8s
6. 超过 20 字的台词必须拆到多个镜头
7. 每个上场角色都必须入画
8. 每镜必须引用场景 ID；每个可辨认角色/道具（含背面、局部）必须引用其 ID
9. 角色四视图：素颜、基础服装、无配饰、`#E8EAF5` 背景、四视图一致
10. 道具四宫格为纯静物，无人物无手；场景主视图无人物

第 2 条是三者合并后最关键的架构约定：光影归属给**场景参考图**，
分镜层只描述人物位置、朝向、动作、景别、运镜。
