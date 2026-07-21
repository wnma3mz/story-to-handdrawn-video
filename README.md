# story-to-handdrawn-video

[English](#english) | [中文](#中文)

---

## English

An agent skill that converts Chinese story copy — or ordered local images — into a **hand-drawn diary-comic animation**: handwritten captions, left-to-right black-and-white → color reveals, optional page-flip transitions, safe uncropped framing, and a silent MP4 picture track ready for post-production voiceover.

### Features

- **Story text → beats**: keeps the author's wording; one complete sentence per beat, splitting only long compound sentences at natural narrative turns.
- **Uploaded pages → animation**: automatically crops handwritten captions and illustrations from composite pages and derives an aligned black-and-white plate locally.
- **Two transitions**: direct-cut (`text → bw_full → color`, revealed left to right) and page-flip (untouched master page, curled from the bottom-right corner).
- **Safe framing**: all illustration marks stay inside the white safe border; contained framing only, never `cover` cropping.
- **Silent MP4 output**: H.264, final 1080×1440 / preview 720×960 — voiceover and BGM are post-production tasks.

### Requirements

- An agent runtime that supports skills (Claude Code, Kimi Code, Codex, etc.).
- A compatible Remotion-based renderer project. The skill is a thin wrapper: `scripts/run_story_video.py` locates the renderer via the `STORY_VIDEO_PROJECT` environment variable or by walking up from the current working directory. The renderer must provide `package.json` and `scripts/run_story_video.py`.
- Python 3, Node.js, and the renderer project's dependencies installed.

### Installation

Clone this repository into your agent's skills directory so the folder name matches the skill name:

```bash
# Claude Code / generic agents
git clone https://github.com/gnipbao/story-to-handdrawn-video.git ~/.claude/skills/story-to-handdrawn-video

# Kimi Code
git clone https://github.com/gnipbao/story-to-handdrawn-video.git ~/.agents/skills/story-to-handdrawn-video
```

Then point the skill at your renderer project:

```bash
export STORY_VIDEO_PROJECT=/absolute/path/to/renderer-project
```

### Usage

Preview with uploaded images:

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "故事标题" \
  --mode preview \
  --transition cut
```

Final direct-cut render:

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "故事标题" \
  --mode full \
  --transition cut \
  --page-duration 4.4
```

Final page-flip render:

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "故事标题" \
  --mode full \
  --transition page-flip \
  --transition-sec 0.7
```

Story text (plan → generate → import → render):

```bash
python3 scripts/run_story_video.py --input /absolute/story.txt --title "故事标题" --mode plan
python3 scripts/run_story_video.py --input /absolute/story.txt --title "故事标题" --mode generate
python3 scripts/run_story_video.py --mode import
python3 scripts/run_story_video.py --mode render
```

See [SKILL.md](SKILL.md) for the full workflow contract the agent follows.

### Output contract

| Input | Mode | Output |
| --- | --- | --- |
| Story text | final | `<project>/out/picture_silent.mp4` |
| Story text | preview | `<project>/out/picture_silent-preview.mp4` |
| Uploaded images | final | `<project>/out/uploaded_picture_silent.mp4` |
| Uploaded images | preview | `<project>/out/uploaded_picture_silent-preview.mp4` |

### Project structure

```
.
├── SKILL.md                    # Skill manifest: name, description, workflow contract
├── agents/
│   └── openai.yaml             # Agent-facing display metadata (中文)
└── scripts/
    └── run_story_video.py      # Portable wrapper that locates the renderer project
```

### Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Please note that `SKILL.md` and `scripts/run_story_video.py` define the core behavior contract; changes there need a clear rationale.

### License

[MIT](LICENSE)

---

## 中文

一个 Agent Skill：把中文故事文案（或有序的本地图片）转换成**手绘日记漫画动画**——手写体字幕、从左到右的黑白→上色渐变揭示、可选的翻页转场、安全不裁剪的画面构图,输出静音 MP4 画面轨,方便后期配音。

### 功能特性

- **故事文本 → 分镜**:保留原文措辞,默认一个完整句子一个节拍,只在自然叙事转折处拆分长复合句。
- **上传页面 → 动画**:自动裁切合成页中的手写字幕与插画,并在本地生成对齐的黑白底版。
- **两种转场**:直接切换(`text → bw_full → color`,从左到右揭示)与翻页(保留原始上传页,从右下角卷起)。
- **安全构图**:所有插画内容保持在白色安全边框内,只使用 contained 构图,绝不 `cover` 裁剪。
- **静音 MP4 输出**:H.264,正式版 1080×1440 / 预览版 720×960;配音与 BGM 属于后期工作。

### 环境要求

- 支持 Skill 的 Agent 运行时(Claude Code、Kimi Code、Codex 等)。
- 一个兼容的 Remotion 渲染器项目。本 Skill 是一个薄封装:`scripts/run_story_video.py` 通过 `STORY_VIDEO_PROJECT` 环境变量或从当前目录向上查找渲染器项目(需包含 `package.json` 与 `scripts/run_story_video.py`)。
- Python 3、Node.js,以及渲染器项目的依赖。

### 安装

把本仓库克隆到 Agent 的 skills 目录,保持目录名与 Skill 名一致:

```bash
# Claude Code / 通用 Agent
git clone https://github.com/gnipbao/story-to-handdrawn-video.git ~/.claude/skills/story-to-handdrawn-video

# Kimi Code
git clone https://github.com/gnipbao/story-to-handdrawn-video.git ~/.agents/skills/story-to-handdrawn-video
```

然后指向你的渲染器项目:

```bash
export STORY_VIDEO_PROJECT=/absolute/path/to/renderer-project
```

### 使用方法

见上方英文部分的命令示例,或直接阅读 [SKILL.md](SKILL.md) 中的完整工作流约定。

### 贡献

欢迎贡献——请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。注意 `SKILL.md` 与 `scripts/run_story_video.py` 定义了核心行为约定,修改需要充分理由。

### 开源协议

[MIT](LICENSE)
