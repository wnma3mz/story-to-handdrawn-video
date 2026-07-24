# story-to-handdrawn-video

[中文](#中文) | [English](#english)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 中文

把中文故事文案或一组有序图片转换成三类成片：3:4 竖屏**手绘日记漫画**、3:4 竖屏**文学随笔**（文字主导+水彩氛围插图），或 16:9 横屏**黑白历史动态漫 / 案卷剧场**。三种模式都提供自然连续运镜、非白底有声封面、按情节分组的连续配音与交付质检。基于 [Remotion](https://www.remotion.dev/) 与 FFmpeg；静音画面母版、无封面配音版和最终发布版分别保留。

本仓库包含两部分:

- **渲染器项目**(根目录):Remotion 工程,负责实际的分镜、动效和渲染。
- **Codex / Agent Skill**(`skill-package/`):可分发的 Skill,装进 Codex 等 Agent 后用自然语言驱动渲染器,无需手动跑脚本。

### 功能特性

- 中文故事自动分句和动态分镜,保留原文措辞
- `diary`、`essay`、`ink-comic` 三种视觉模式：日记用白纸手账构图逐句配图；随笔以文字为主、搭配柔和水彩氛围插图仅做呼吸式运镜；历史动态漫使用 16:9 全屏黑白画面、代码字幕和单一线索色
- 上传漫画页或完整图片,保持原顺序和构图
- 自动拆分上方文字区与下方插画区
- 本地生成与彩色插画对齐的黑白层
- `文字 → 黑白画稿 → 彩色插画` 从左到右揭示
- 按叙事目的选择轻推、轻拉、平移或静止，避免同图运镜重置和机械抖动
- 支持逐镜 `cut` / `fade`；淡出层冻结在本镜最后一帧并覆盖下一镜开头，不改变总时长
- 可选右下角卷页翻书转场(纸背保留淡化的原页纹理)
- 可配置的非白底系列封面，标题由代码精确排版并带可听见的标题音频
- 3–6 个连续叙事组配音，VTT 只用于同步测量，不切碎句子
- 语义同步、响度、首帧、封面音频、完整解码等自动质检
- `diary` 输出 1080×1440，`ink-comic` 输出 1920×1080；两者都支持快速预览
- Codex Image2 工作流,以及显式选择的 OpenAI API 工作流

### 环境要求

- Node.js 20 或更高版本
- Python 3.10 或更高版本，以及 Pillow、NumPy
- FFmpeg,且 `ffmpeg`、`ffprobe` 可从终端调用
- `edge-tts`（需要自动生成配音时：`python3 -m pip install edge-tts`）
- npm
- Google Chrome,或由 Remotion 管理的兼容浏览器
- 支持 Skill 的 Agent 运行时(Codex、Claude Code、Kimi Code 等)

### 安装

1. 准备渲染器项目:

```bash
git clone https://github.com/gnipbao/story-to-handdrawn-video.git
cd story-to-handdrawn-video
npm ci
npm run check      # TypeScript 检查 + 分镜结构校验,不访问网络
```

2. 把 Skill 装进 Agent 的 skills 目录:

```bash
# Codex
cp -R skill-package/story-to-handdrawn-video ~/.codex/skills/

# Claude Code / 通用 Agent
cp -R skill-package/story-to-handdrawn-video ~/.claude/skills/

# Kimi Code
cp -R skill-package/story-to-handdrawn-video ~/.agents/skills/
```

3. 告诉 Skill 渲染器项目在哪里(在渲染器项目目录内运行 Agent 时可省略):

```bash
export STORY_VIDEO_PROJECT=/absolute/path/to/story-to-handdrawn-video
```

### 使用方法(Codex Skill 示例)

装好 Skill 后,全部通过自然语言驱动,分句、分镜、图片生成、导入、渲染由 Agent 按 Skill 约定自动完成。

**故事文本 → 手绘动画**(Skill 的默认提示词):

```text
使用 $story-to-handdrawn-video 把这段故事生成带连续配音和有声封面的手绘动画成片。

<在这里粘贴故事文本>
```

也可以把故事放在 UTF-8 文本文件里:

```text
使用 $story-to-handdrawn-video 把 /absolute/story.txt 生成手绘动画,标题叫「纸上的夏天」。
```

**历史故事 / 悬疑案件 → 16:9 黑白动态漫**：

```text
使用 $story-to-handdrawn-video 的 ink-comic 模式，把 /absolute/story.txt
做成 16:9 黑白历史动态漫；只在关键线索上保留一处朱红色。
```

**上传图片 → 手绘动画**(图片按播放顺序给出):

```text
使用 $story-to-handdrawn-video 把这几张图片按顺序生成手绘动画:
/absolute/01.jpg /absolute/02.jpg /absolute/03.jpg
```

**翻书效果**(保留原始页面,从右下角卷页):

```text
使用 $story-to-handdrawn-video 把这些图片做成翻书效果的手绘动画:
/absolute/01.jpg /absolute/02.jpg
```

**先出预览**(`diary` 为 720×960，`ink-comic` 为 1280×720；确认后再出正式版):

```text
使用 $story-to-handdrawn-video 先给这个故事生成一个预览版。
```

使用建议:

- 故事文本默认一个完整句子一个节拍;想控制节奏,直接在故事里按句分行即可。
- 需要精确的一行一镜时，使用 `--scene-contract` 并让 `visual-plan.json` 从 `01` 起连续覆盖全部非空行：长旁白保持在该镜内，不再被自动子句切分；每镜必须提供 1–3 行 `caption` 和 2–15 秒 `duration_sec`，从而把"完整旁白"和"可读字幕"分开。`ink-comic` 的正式字幕随后从最终 TTS 配置逐句回填。未显式启用时仍使用原有自动分句。
- 新集只需新增某个角色时，把"本集新角色参考图"的窄范围描述放进独立文件并传给 `--character-reference-prompt`；完整的 `--character-lock` 仍负责全剧连续性，但不会把其中提到的所有旧角色都画进新参考图。
- 并行制作多集时，为每集同时指定独立的 `--output /episode/storyboard.json` 与 `--manifest /episode/codex-image-jobs.json`；manifest 会绑定该 storyboard，避免后生成的集数覆盖前集 import 目标。
- 遇到时间跳跃、指代不明、医疗场景或年龄敏感角色时,建议先让 Agent 给出视觉规划(两位场景编号为键的 JSON),确认后再生成。
- 默认使用 Codex Image2 生成图片;只有明确要求时才会走 OpenAI API(需 `OPENAI_API_KEY`)。
- 先验收静音视觉预览，再冻结连续配音文案；`ink-comic` 回填逐字字幕后才渲染正式静音画面母版。不要用逐镜头 TTS 或逐句变速。

导入或预览前先审计本集运动时间线，并再跑渲染器自身校验：

```bash
python3 scripts/audit_motion_timeline.py \
  /absolute/episode/motion-timeline.tsv \
  --expected-duration <本集实际秒数>
node scripts/validate-storyboard.mjs /absolute/episode/storyboard.json
```

审计器与渲染器统一只接受 `hold`、`push_soft`、`push_left`、`push_right`、`pull_soft`、`pan_left`、`pan_right`；旧的泛化标签 `push`、`pull` 会直接失败。
插画尚未生成的规划阶段可加 `--allow-missing-assets`，只校验结构、时长、层级和运镜；正式导入、预览和交付前必须去掉该参数，恢复素材存在性与尺寸检查。

逐镜转场遵循一个明确契约：`transition_to_next` 缺省时按 `cut` 处理；`fade`
使用 `project.transition_sec`（默认 0.7 秒，允许 0.5–0.9 秒），把已经完成
运镜的出镜画面冻结在本镜最后一帧，再叠在下一镜开头平滑淡出。下一镜的
起点、整集总帧数和旁白时间轴均不移动；淡出最多占下一镜的 45%。项目级
`page-flip` 与任何逐镜 `fade` 属于两个互斥的转场系统，校验器会直接拒绝
混用。`npm run check` 会同时执行这套通用 layer-plan 边界测试。

如果原始生成图在全分辨率语义审查中已经通过，但背景只是“近白”而非精确
`#FFFFFF`，先保留原图，再做全画布机械归一化；它不能用于修复裁断、错误
人物、错误物件或构图泄漏：

```bash
python3 scripts/normalize-illustration-master.py \
  /absolute/episode/candidates/scene-01/attempt-01-original.png \
  /absolute/episode/candidates/scene-01/candidate-final.png \
  --json-report /absolute/episode/candidates/scene-01/candidate-final-normalization.json
python3 scripts/audit-illustration-masters.py \
  /absolute/episode/candidates/scene-01/candidate-final.png \
  --min-margin 126
```

生成封面、连续配音和最终发布版：

```bash
npm run render:cover
python3 scripts/build_story_audio.py \
  --config examples/voiceover.example.json \
  --episode <slug>
python3 scripts/audit_story_delivery.py \
  out/<slug>/voiced/release.mp4 \
  --master out/<slug>/voiced/narration-master.wav \
  --build out/<slug>/voiced/build.json \
  --sync-map out/<slug>/voiced/sync-map.json \
  --cover-duration 2.7
```

`ink-comic` 的底部字幕必须逐句对应最终实际配音。配音文案冻结后，先回填并校验字幕，再渲染正式画面：

```bash
python3 scripts/apply_verbatim_subtitles.py \
  --storyboard storyboard.json \
  --config /absolute/voiceover.json
npm run check
npm run render
```

示例配置只展示结构；请按真实分镜填写每组 `scene_ids`、`start_sec` 和 `speech_text`。一组旁白一次合成，组内不切句、不逐句变速。QC 会同时检查计划组间 gap 与母带的真实声学静音；默认普通停顿上限为 1.25 秒，只有正常速度人工听感明确通过时，才可用 `--ordinary-pause-limit` 记录不高于 1.50 秒的单集例外。

示例以温和女声 `zh-CN-XiaoxiaoNeural` 作为亲密叙事或寓言题材的起点，但这不是跨故事硬编码。`profile` 中的 `voice`、`rate`、`pitch` 和 `volume` 均可配置；更换故事类型、受众或叙述关系时，应重新用开篇和后半段样本做正常速度 A/B，再冻结该系列的声音配置。

### 输出契约

| 输入 | 模式 | 输出路径 |
| --- | --- | --- |
| 故事文本 | 正式 | `out/<episode>/silent.mp4` |
| 故事文本 | 预览 | `out/<episode>/silent-preview.mp4` |
| 上传图片 | 正式 | `out/<episode>/uploaded.mp4` |
| 上传图片 | 预览 | `out/<episode>/uploaded-preview.mp4` |
| 封面 | 静态图 | `out/<episode>/cover.png` |
| 配音 | 审片版 | `out/<episode>/voiced/preview.mp4` |
| 配音 | 发布版 | `out/<episode>/voiced/release.mp4` · `out/releases/<episode>.mp4`（快查副本） |

多集并发时设置 `EPISODE` 环境变量互不覆盖：`EPISODE=s01-e05 npm run render`。
中间产物（TTS 分组、VTT）写入 `.work/<episode>/`。

- 分辨率：`diary`/`essay` 正式版 1080×1440；`ink-comic` 正式版 1920×1080
- 画面母版:H.264,静音
- 旁白母版:48 kHz / 24-bit PCM / mono，默认约 -16 LUFS、真峰值不高于 -1.5 dBTP
- 发布版:H.264 + 48 kHz stereo AAC；封面时段可听，主画面与故事旁白同一时刻开始

Skill 的完整行为约定见 [skill-package/story-to-handdrawn-video/SKILL.md](skill-package/story-to-handdrawn-video/SKILL.md)。

### 项目结构

```text
.
├── src/                    # Remotion 组件(场景、擦除动效、翻页、缓动)
├── scripts/                # 渲染器入口与导入/校验/打包脚本(由 Skill 调用)
├── skill-package/          # 可分发的 Codex / Agent Skill
├── examples/               # 示例故事文本
├── references/             # 黑白/彩色风格参考图
├── public/                 # 字体与素材(generated/ 为运行时产物)
├── storyboard.json         # 默认文本故事分镜示例
├── storyboard.uploaded.json # 上传图片分镜示例
└── DESIGN.md               # 设计说明
```

渲染器项目的维护命令:`npm run dev`(Remotion Studio)、`npm run check`(类型与分镜校验)、`npm run build`(生产构建)、`npm run package:share`(生成源码分享包)。

### 字体

项目使用随附的站酷马善政毛笔字体(Ma Shan Zheng),许可证见 [public/fonts/OFL-MaShanZheng.txt](public/fonts/OFL-MaShanZheng.txt)(SIL Open Font License)。

### 贡献

欢迎贡献——请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。注意 `skill-package/` 下的 Skill 契约与 `src/`、`scripts/` 下的渲染器逻辑是核心部分,修改需要充分理由。

### 开源协议

[MIT](LICENSE)

---

## English

Convert story copy—or ordered images—into either a 3:4 vertical **hand-drawn diary comic** or a 16:9 **monochrome historical motion comic / case-file theater**. Both modes include motivated continuous motion, an audible non-white cover, connected narration groups, and delivery QC. Built on [Remotion](https://www.remotion.dev/) and FFmpeg; it preserves separate silent-picture, voiced-review, and public-release masters.

This repo contains:

- **The renderer project** (root): the Remotion app that storyboards, animates, and renders.
- **A Codex / agent skill** (`skill-package/`): a distributable skill that drives the renderer with natural language — no scripts to run by hand.

### Requirements

- Node.js 20+, Python 3.10+ with Pillow and NumPy, npm, and `edge-tts` when narration generation is needed
- FFmpeg (`ffmpeg` and `ffprobe` on PATH)
- Google Chrome or a Remotion-managed compatible browser
- An agent runtime with skill support (Codex, Claude Code, Kimi Code, …)

### Install

1. Set up the renderer project:

```bash
git clone https://github.com/gnipbao/story-to-handdrawn-video.git
cd story-to-handdrawn-video
npm ci
npm run check
```

2. Install the skill into your agent's skills directory:

```bash
# Codex
cp -R skill-package/story-to-handdrawn-video ~/.codex/skills/

# Claude Code / generic agents
cp -R skill-package/story-to-handdrawn-video ~/.claude/skills/

# Kimi Code
cp -R skill-package/story-to-handdrawn-video ~/.agents/skills/
```

3. Point the skill at the renderer project (skip when the agent runs inside it):

```bash
export STORY_VIDEO_PROJECT=/absolute/path/to/story-to-handdrawn-video
```

### Usage (Codex skill examples)

Everything is driven in natural language; sentence splitting, storyboarding, image generation, import, and rendering are handled by the agent per the skill contract.

Story text → animation (the skill's default prompt):

```text
使用 $story-to-handdrawn-video 把这段故事生成带连续配音和有声封面的手绘动画成片。

<paste your story here>
```

Ordered images → animation:

```text
使用 $story-to-handdrawn-video 把这几张图片按顺序生成手绘动画:
/absolute/01.jpg /absolute/02.jpg /absolute/03.jpg
```

Page-flip effect (uploaded pages shown untouched, curled from the bottom-right corner):

```text
使用 $story-to-handdrawn-video 把这些图片做成翻书效果的手绘动画:
/absolute/01.jpg /absolute/02.jpg
```

Preview first (720×960 for `diary`, 1280×720 for `ink-comic`, before committing to a full render):

```text
使用 $story-to-handdrawn-video 先给这个故事生成一个预览版。
```

Notes: one complete sentence per beat by default; Codex Image2 is the default image generator. For exact one-line-per-scene planning, pass `--scene-contract` with a consecutive `01..NN` visual plan covering every non-empty source line. Each entry must include a 1–3 line `caption` and `duration_sec` in `2..15`; without the flag, the established automatic sentence splitter remains active. Keep the full spoken thought in the source line and the shorter screen copy in `caption`. In `ink-comic`, freeze the final voiceover config and run `scripts/apply_verbatim_subtitles.py` before the final render so the bottom transcript matches the actual TTS; the shorter planning caption is retained only as `summary_text`. When an episode introduces only one new recurring character, pass a narrow brief with `--character-reference-prompt`; the broader `--character-lock` remains continuity context and no longer expands the reference-sheet cast. For parallel episodes, pair an episode-specific `--output` with its `--manifest` so later planning cannot redirect an earlier import. Preserve and inspect every untouched illustration original. If a semantic PASS has only a near-white generated field, `scripts/normalize-illustration-master.py` may perform whole-frame normalization, uniform downscale, and exact-white centering; it must never rescue a cropped, semantically wrong, or identity-leaking image, and the derivative must still pass `scripts/audit-illustration-masters.py`. Before import or preview, run `python3 scripts/audit_motion_timeline.py <timeline> --expected-duration <seconds>` and the renderer's storyboard validator. During planning only, `validate-storyboard.mjs --allow-missing-assets <storyboard>` checks structure before illustrations exist; omit that flag for every import, preview, and delivery gate. The audit deliberately accepts only the same seven motions as the renderer: `hold`, `push_soft`, `push_left`, `push_right`, `pull_soft`, `pan_left`, and `pan_right`. Approve the silent master first, then use `scripts/build_story_audio.py` with an episode config. Narration is synthesized as connected acts; VTT timestamps measure sync but never cut prose into sentence clips.

Per-scene transitions use a strict contract. A missing
`transition_to_next` means `cut`. A `fade` uses
`project.transition_sec` (0.7 seconds by default; 0.5–0.9 allowed), freezes
the completed outgoing scene on its nominal final frame, and fades that layer
over the incoming scene without moving scene starts or changing the
composition duration. The fade is capped at 45% of the incoming scene.
Project-level `page-flip` and per-scene `fade` are mutually exclusive and the
validator rejects a mixed timeline. `npm run check` includes the generic
layer-plan boundary tests.

### Outputs

| Input | Mode | Path |
| --- | --- | --- |
| Story text | final | `out/<episode>/silent.mp4` |
| Story text | preview | `out/<episode>/silent-preview.mp4` |
| Uploaded images | final | `out/<episode>/uploaded.mp4` |
| Uploaded images | preview | `out/<episode>/uploaded-preview.mp4` |
| Narrated review | no cover | `out/<episode>/voiced/preview.mp4` |
| Public release | audible cover | `out/<episode>/voiced/release.mp4` · `out/releases/<episode>.mp4` (quick-find copy) |

Set `EPISODE=...` for multi-episode isolation. Intermediates (TTS groups, VTT) reside in `.work/<episode>/`.

Final picture is 1080×1440 H.264 in `diary`/`essay` mode or 1920×1080 in `ink-comic`; previews follow the same aspect ratio. Narration defaults to a 48 kHz PCM master around -16 LUFS and a stereo AAC release. The full behavior contract lives in [SKILL.md](skill-package/story-to-handdrawn-video/SKILL.md).

### License

[MIT](LICENSE). The bundled Ma Shan Zheng font is under the [SIL Open Font License](public/fonts/OFL-MaShanZheng.txt).
