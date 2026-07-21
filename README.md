# story-to-handdrawn-video

[中文](#中文) | [English](#english)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 中文

把中文故事文案或一组有序的手绘图片,转换成 3:4 竖屏**手绘日记漫画动画**:手写体字幕、从左到右的「文字 → 黑白画稿 → 彩色插画」揭示、可选的右下角卷页翻书转场、安全不裁剪的画面构图。基于 [Remotion](https://www.remotion.dev/),默认输出无配音、无音乐的 H.264 画面轨,方便后期配音。

本仓库包含两部分:

- **渲染器项目**(根目录):Remotion 工程,负责实际的分镜、动效和渲染。
- **Codex / Agent Skill**(`skill-package/`):可分发的 Skill,装进 Codex 等 Agent 后用自然语言驱动渲染器,无需手动跑脚本。

### 功能特性

- 中文故事自动分句和动态分镜,保留原文措辞
- 上传漫画页或完整图片,保持原顺序和构图
- 自动拆分上方文字区与下方插画区
- 本地生成与彩色插画对齐的黑白层
- `文字 → 黑白画稿 → 彩色插画` 从左到右揭示
- 可选右下角卷页翻书转场(纸背保留淡化的原页纹理)
- 1080×1440 正式渲染和 720×960 快速预览
- Codex Image2 工作流,以及显式选择的 OpenAI API 工作流

### 环境要求

- Node.js 20 或更高版本
- Python 3.10 或更高版本
- FFmpeg,且 `ffmpeg`、`ffprobe` 可从终端调用
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
使用 $story-to-handdrawn-video 把这段故事生成可后期配音的手绘动画。

<在这里粘贴故事文本>
```

也可以把故事放在 UTF-8 文本文件里:

```text
使用 $story-to-handdrawn-video 把 /absolute/story.txt 生成手绘动画,标题叫「纸上的夏天」。
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

**先出预览**(720×960,确认效果后再出正式版):

```text
使用 $story-to-handdrawn-video 先给这个故事生成一个预览版。
```

使用建议:

- 故事文本默认一个完整句子一个节拍;想控制节奏,直接在故事里按句分行即可。
- 遇到时间跳跃、指代不明、医疗场景或年龄敏感角色时,建议先让 Agent 给出视觉规划(两位场景编号为键的 JSON),确认后再生成。
- 默认使用 Codex Image2 生成图片;只有明确要求时才会走 OpenAI API(需 `OPENAI_API_KEY`)。
- 输出是静音画面轨,配音和 BGM 属于后期工作。

### 输出契约

| 输入 | 模式 | 输出路径 |
| --- | --- | --- |
| 故事文本 | 正式 | `out/picture_silent.mp4` |
| 故事文本 | 预览 | `out/picture_silent-preview.mp4` |
| 上传图片 | 正式 | `out/uploaded_picture_silent.mp4` |
| 上传图片 | 预览 | `out/uploaded_picture_silent-preview.mp4` |

- 分辨率:正式 1080×1440,预览 720×960
- 编码:H.264,静音

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

Convert Chinese story copy — or ordered hand-drawn images — into a 3:4 vertical **hand-drawn diary-comic animation**: handwritten captions, left-to-right `text → bw plate → color illustration` reveals, an optional bottom-right page-curl flip transition, and safe uncropped framing. Built on [Remotion](https://www.remotion.dev/); outputs a silent H.264 picture track ready for post-production voiceover.

This repo contains:

- **The renderer project** (root): the Remotion app that storyboards, animates, and renders.
- **A Codex / agent skill** (`skill-package/`): a distributable skill that drives the renderer with natural language — no scripts to run by hand.

### Requirements

- Node.js 20+, Python 3.10+, npm
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
使用 $story-to-handdrawn-video 把这段故事生成可后期配音的手绘动画。

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

Preview first (720×960, before committing to a full render):

```text
使用 $story-to-handdrawn-video 先给这个故事生成一个预览版。
```

Notes: one complete sentence per beat by default; Codex Image2 is the default image generator (the OpenAI API path is only used when explicitly requested and requires `OPENAI_API_KEY`); output is a silent picture track — voiceover and BGM are post-production.

### Outputs

| Input | Mode | Path |
| --- | --- | --- |
| Story text | final | `out/picture_silent.mp4` |
| Story text | preview | `out/picture_silent-preview.mp4` |
| Uploaded images | final | `out/uploaded_picture_silent.mp4` |
| Uploaded images | preview | `out/uploaded_picture_silent-preview.mp4` |

Final 1080×1440, preview 720×960, H.264, silent. The full behavior contract lives in [SKILL.md](skill-package/story-to-handdrawn-video/SKILL.md).

### License

[MIT](LICENSE). The bundled Ma Shan Zheng font is under the [SIL Open Font License](public/fonts/OFL-MaShanZheng.txt).
