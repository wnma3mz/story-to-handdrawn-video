# 第三方来源与授权

本项目是三个独立开源项目的合并产物。合并**不改变**任何上游组件的授权，
也不吞掉任何版权声明。逐项说明如下。

---

## 1. story-to-handdrawn-video — 渲染器主干

- **来源**：https://github.com/gnipbao/story-to-handdrawn-video
- **本仓库 fork**：https://github.com/wnma3mz/story-to-handdrawn-video
- **作者**：gnipbao
- **授权**：MIT（原文保留在 `LICENSE-MIT-gnipbao.txt`）
- **并入本仓库的部分**：`src/`、`scripts/`、`config/`、`references/`、
  `public/`、`skill-package/`、`DESIGN.md`

本项目以它的 Remotion 渲染器为主干，在其上扩展 9:16 竖屏、多 composition
共用工程、以及来自另外两个项目的能力。

## 2. Toonflow Adapter Kit — 上游内容生产线

- **提示词原始项目**：https://github.com/HBAI-Ltd/Toonflow-app
- **提取整理后的工具包**：https://github.com/wnma3mz/toonflow-adapter-kit
  （本地路径 `toonflow-adapter-kit/`）
- **作者**：HBAI-Ltd
- **授权**：MIT
- **并入本仓库的部分**：`content/skills/`（183 个提示词文件）、
  `content/docs/`、`content/templates/`、`content/examples/`

`content/skills/` 下的文件是从 Toonflow-app **原样提取**的提示词，未做修改。
本项目只在此之上追加了 `adapters/` 编译器，把这些提示词的产物接到渲染器上。

## 3. anything2explainer — 配音、量化质检、多 Agent 协议

- **来源**：https://github.com/wnma3mz/anything2explainer
- **原作者**：Vincent Wei — https://github.com/Vincentwei1021/anything2explainer
- **授权**：PolyForm Noncommercial 1.0.0
- **并入本仓库的部分**：
  - `agent-rules/` — `reference/` 全部 9 个方法论文档（688 行），含原作者
    切换到 IndexTTS-2.5 后的最新版本
  - `audio/tts_build_frame_accurate.py` — 帧精确时间轴模式的完整实现（603 行）
  - `audio/tts_engines.py` — 引擎实现移植，但改为适配本项目渲染器的配音契约
  - `qc/frame_metrics.py`、`qc/motion_check.py` — 逐镜量化质检
  - `qc/shot_ranges.py` — 新写，把 `storyboard.json` 换算成这两个脚本的帧区间接口
  - `projects/` — 用原作者方法产出的两部成片及其过程文件（见 `projects/README.md`）
    **不随本仓库分发**，仅作本地归档；作者本人可自由使用

**这是本项目整体转为非商用授权的原因。** 上游 a2e 的非商用条款要求合并后的
衍生作品同样只能非商用使用，因此本仓库的 `LICENSE` 采用 PolyForm
Noncommercial 1.0.0。若需要商用，必须先取得 a2e 原作者的单独授权。

`agent-rules/reference/lessons.md` 记录的是原作者在 5 部片子中踩过的坑，属于
其个人经验总结，引用时同样受非商用条款约束。

## 4. 字体

| 路径 | 字体 | 授权 |
|---|---|---|
| `public/fonts/MaShanZheng` | 站酷马善政毛笔字体 | SIL OFL 1.1（见 `public/fonts/OFL-MaShanZheng.txt`） |
| `public/fonts/*`（a2e 引入） | Noto Sans SC / Orbitron / Exo 2 / Audiowide | SIL OFL 1.1（见 `public/fonts/LICENSE.md`） |

字体为独立授权，不受本项目非商用条款影响：可商用、可嵌入、可再分发。
渲染出的视频成品也不受本项目授权限制。

---

## 合并后的授权结论

| 用途 | 是否允许 |
|---|---|
| 个人学习、研究、非商业创作 | ✅ 允许 |
| 商业项目 | ❌ 需先取得 a2e 原作者（Vincent Wei）的书面授权 |
| 分发本工具包 | ✅ 允许，须附带本文件与 `LICENSE` |
| 用本工具产出的视频 | ✅ 归创作者所有，不受本工具授权限制 |

## 修改声明

本仓库对上游文件做了实质性修改。按 PolyForm Noncommercial 1.0.0 的
Redistribution 第 2 条，凡修改过的文件均已在文件头或本文件中标明来源与
改动性质。详细改动清单见 `CHANGELOG.md`。
