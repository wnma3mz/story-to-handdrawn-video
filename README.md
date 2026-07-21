# story-to-handdrawn-video

[中文](#中文) | [English](#english)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 中文

把中文故事文案或一组有序的手绘图片,转换成 3:4 竖屏**手绘日记漫画动画**:手写体字幕、从左到右的「文字 → 黑白画稿 → 彩色插画」揭示、可选的右下角卷页翻书转场、安全不裁剪的画面构图。基于 [Remotion](https://www.remotion.dev/),默认输出无配音、无音乐的 H.264 画面轨,方便后期配音。

### 功能特性

- 中文故事自动分句和动态分镜,保留原文措辞
- 上传漫画页或完整图片,保持原顺序和构图
- 自动拆分上方文字区与下方插画区
- 本地生成与彩色插画对齐的黑白层
- `文字 → 黑白画稿 → 彩色插画` 从左到右揭示
- 可选右下角卷页翻书转场(纸背保留淡化的原页纹理)
- 1080×1440 正式渲染和 720×960 快速预览
- Codex Image2 工作流,以及显式选择的 OpenAI API 工作流
- 附带可分发的 Agent Skill(见 [Skill 安装](#skill-安装))

### 环境要求

- Node.js 20 或更高版本
- Python 3.10 或更高版本
- FFmpeg,且 `ffmpeg`、`ffprobe` 可从终端调用
- npm
- Google Chrome,或由 Remotion 管理的兼容浏览器

### 快速开始

```bash
git clone https://github.com/gnipbao/story-to-handdrawn-video.git
cd story-to-handdrawn-video
npm ci
npm run check      # TypeScript 检查 + 分镜结构校验,不访问网络
```

打开 Remotion Studio 可视化预览:

```bash
npm run dev
```

### 使用方法

所有生成都通过统一入口 `scripts/run_story_video.py` 完成。输入三选一(互斥):

| 参数 | 说明 |
| --- | --- |
| `--input <文件>` | UTF-8 故事文本文件,见 `examples/story.txt` |
| `--text "<文本>"` | 内联故事文案 |
| `--images <图1> <图2> ...` | 有序本地图片,按播放顺序显式列出 |

#### 方式一:图片 → 手绘视频

图片按顺序列出。推荐先生成预览确认效果:

```bash
# 预览(720×960,速度快)
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg /absolute/03.jpg \
  --title "我的故事" \
  --mode preview \
  --transition cut \
  --page-duration 4.4

# 正式渲染(1080×1440)
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg /absolute/03.jpg \
  --title "我的故事" \
  --mode full \
  --transition cut \
  --page-duration 4.4
```

输出:

- 预览:`out/uploaded_picture_silent-preview.mp4`
- 正式版:`out/uploaded_picture_silent.mp4`

上传页布局识别(`--layout`):

- `auto`(默认):自动识别文字区和插画区
- `composite`:强制按「上方文字、下方插画」处理
- `full`:整张图片作为插画,不单独提取文字

如果自动切分的位置不对,可以用 `--split-y SCENE:PIXELS` 手动指定某个场景的文字/插画分界线(可多次传入),例如 `--split-y 03:512`。

#### 方式二:翻书效果

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "翻书故事" \
  --mode full \
  --transition page-flip \
  --transition-sec 0.7 \
  --page-duration 4.4
```

两种转场的区别:

- `cut`(默认):每页按「文字 → 黑白 → 彩色」顺序从左到右揭示。
- `page-flip`:纯翻页模式。每页直接显示完整原图,**不添加**文字、黑白或二次上色动效;静态停留后从右下角卷页,纸背保留淡化的原页纹理,配合弧形折痕和动态投影。`--transition-sec` 控制卷页时长(秒)。

#### 方式三:故事文本 → 手绘分镜 → 视频

文本输入默认一个完整句子一个节拍,只在自然叙事转折处拆分长复合句。分四步:

```bash
# 1. plan:只生成分镜和提示词(storyboard.generated.json),不调用图片模型
python3 scripts/run_story_video.py \
  --input examples/story.txt \
  --title "纸上的夏天" \
  --mode plan

# 2. generate:准备 codex-image-jobs.json,由 Codex Image2 生成各分镜母图
python3 scripts/run_story_video.py \
  --input examples/story.txt \
  --title "纸上的夏天" \
  --mode generate

# 3. import:把生成好的图片导入 public/assets/generated/
python3 scripts/run_story_video.py --mode import

# 4. render:正式渲染
python3 scripts/run_story_video.py --mode render
```

预览文本故事用 `--mode preview`,输出 `out/picture_silent-preview.mp4`;正式版输出 `out/picture_silent.mp4`。

如明确使用 OpenAI API 作为图片生成器(需要 `OPENAI_API_KEY`):

```bash
export OPENAI_API_KEY="..."
python3 scripts/run_story_video.py \
  --input examples/story.txt \
  --title "纸上的夏天" \
  --mode full \
  --generator api
```

对于时间跳跃、指代不明、医疗场景或年龄敏感角色,建议通过 `--visual-plan <JSON>` 提供以两位场景编号为键的视觉规划,锁定画面一致性;角色一致性约束可用 `--character-lock` 传入。

#### 完整参数表

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--title` | `手绘故事` | 视频标题 |
| `--mode` | `plan` | `plan` / `generate` / `import` / `render` / `preview` / `full` |
| `--generator` | `codex` | 图片生成器:`codex`(默认)或 `api`(需 `OPENAI_API_KEY`) |
| `--transition` | `cut` | 转场:`cut` 或 `page-flip` |
| `--transition-sec` | `0.7` | 翻页转场时长(秒) |
| `--page-duration` | `4.4` | 每页停留时长(秒) |
| `--layout` | `auto` | 上传页布局:`auto` / `composite` / `full` |
| `--split-y SCENE:PIXELS` | — | 手动指定某场景的文字/插画分界,可多次传入 |
| `--text-mode` | `font` | 字幕渲染方式:`font`(手写字体)或 `image2` |
| `--visual-plan` | — | 以两位场景编号为键的视觉规划 JSON |
| `--character-lock` | — | 角色一致性约束 |
| `--force` | 关 | 显式要求替换已存在的生成批次时使用 |
| `--manifest` | — | 自定义分镜清单路径 |
| `--project-dir` | 自动探测 | 项目根目录(也可用环境变量 `STORY_VIDEO_PROJECT`) |

### 输出契约

| 输入 | 模式 | 输出路径 |
| --- | --- | --- |
| 故事文本 | 正式 | `out/picture_silent.mp4` |
| 故事文本 | 预览 | `out/picture_silent-preview.mp4` |
| 上传图片 | 正式 | `out/uploaded_picture_silent.mp4` |
| 上传图片 | 预览 | `out/uploaded_picture_silent-preview.mp4` |

- 分辨率:正式 1080×1440,预览 720×960
- 编码:H.264,静音(配音和 BGM 属于后期工作)

### npm 脚本

| 命令 | 说明 |
| --- | --- |
| `npm run dev` | 打开 Remotion Studio |
| `npm run check` | TypeScript 检查 + 分镜结构校验(不访问网络) |
| `npm run build` | 生产构建 |
| `npm run render` / `render:preview` | 渲染文本故事正式版 / 预览版 |
| `npm run render:uploaded` / `render:uploaded:preview` | 渲染上传图片正式版 / 预览版 |
| `npm run import:codex` / `import:uploaded` | 导入 Codex 生成图 / 上传页 |
| `npm run package:share` | 先检查工程,再在 `release/` 生成源码分享包 |

### 项目结构

```text
.
├── src/                    # Remotion 组件(场景、擦除动效、翻页、缓动)
├── scripts/                # 渲染入口与导入/校验/打包脚本
├── skill-package/          # 可分发的 Agent Skill
├── examples/               # 示例故事文本
├── references/             # 黑白/彩色风格参考图
├── public/                 # 字体与素材(generated/ 为运行时产物)
├── storyboard.json         # 默认文本故事分镜示例
├── storyboard.uploaded.json # 上传图片分镜示例
└── DESIGN.md               # 设计说明
```

运行时产物(`node_modules/`、`out/`、`public/assets/generated/`、`prompts/generated/`、`codex-image-jobs.json`、`storyboard.generated.json`、`uploaded-pages.json`、`build/`)均已加入 `.gitignore`。

### Skill 安装

可分发的 Skill 位于 `skill-package/story-to-handdrawn-video/`。克隆到 Agent 的 skills 目录即可安装:

```bash
# Claude Code / 通用 Agent
git clone https://github.com/gnipbao/story-to-handdrawn-video.git
cp -R story-to-handdrawn-video/skill-package/story-to-handdrawn-video ~/.claude/skills/

# Kimi Code
cp -R story-to-handdrawn-video/skill-package/story-to-handdrawn-video ~/.agents/skills/
```

Skill 会优先使用 `STORY_VIDEO_PROJECT` 定位渲染器项目,否则从当前工作目录向上查找:

```bash
export STORY_VIDEO_PROJECT=/absolute/path/to/story-to-handdrawn-video
```

Skill 的行为契约见 [skill-package/story-to-handdrawn-video/SKILL.md](skill-package/story-to-handdrawn-video/SKILL.md)。

### 字体

项目使用随附的站酷马善政毛笔字体(Ma Shan Zheng),许可证见 [public/fonts/OFL-MaShanZheng.txt](public/fonts/OFL-MaShanZheng.txt)(SIL Open Font License)。

### 贡献

欢迎贡献——请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。注意 `skill-package/` 下的 Skill 契约与 `src/`、`scripts/` 下的渲染器逻辑是核心部分,修改需要充分理由。

### 开源协议

[MIT](LICENSE)

---

## English

Convert Chinese story copy — or ordered hand-drawn images — into a 3:4 vertical **hand-drawn diary-comic animation**: handwritten captions, left-to-right `text → bw plate → color illustration` reveals, an optional bottom-right page-curl flip transition, and safe uncropped framing. Built on [Remotion](https://www.remotion.dev/); outputs a silent H.264 picture track ready for post-production voiceover.

### Requirements

- Node.js 20+, Python 3.10+, npm
- FFmpeg (`ffmpeg` and `ffprobe` on PATH)
- Google Chrome or a Remotion-managed compatible browser

### Quick start

```bash
git clone https://github.com/gnipbao/story-to-handdrawn-video.git
cd story-to-handdrawn-video
npm ci
npm run check   # TypeScript + storyboard validation, no network
npm run dev     # Remotion Studio
```

### Usage

Everything goes through `scripts/run_story_video.py` with one of three mutually exclusive inputs: `--input <file>` (UTF-8 story text), `--text "<copy>"` (inline), or `--images <ordered images>`.

Images → video (preview first, then final):

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "My Story" --mode preview --transition cut --page-duration 4.4

python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "My Story" --mode full --transition cut --page-duration 4.4
```

Page-flip mode shows each uploaded page untouched, then curls it from the bottom-right corner:

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "翻书故事" --mode full --transition page-flip --transition-sec 0.7
```

Story text → storyboard → video (four steps: plan, generate, import, render):

```bash
python3 scripts/run_story_video.py --input examples/story.txt --title "纸上的夏天" --mode plan
python3 scripts/run_story_video.py --input examples/story.txt --title "纸上的夏天" --mode generate
python3 scripts/run_story_video.py --mode import
python3 scripts/run_story_video.py --mode render
```

Key options: `--transition cut|page-flip`, `--layout auto|composite|full`, `--generator codex|api` (`api` requires `OPENAI_API_KEY`), `--page-duration` (default 4.4s), `--transition-sec` (default 0.7s), `--visual-plan`, `--character-lock`, `--force`. See the [full parameter table](#完整参数表) above.

### Outputs

| Input | Mode | Path |
| --- | --- | --- |
| Story text | final | `out/picture_silent.mp4` |
| Story text | preview | `out/picture_silent-preview.mp4` |
| Uploaded images | final | `out/uploaded_picture_silent.mp4` |
| Uploaded images | preview | `out/uploaded_picture_silent-preview.mp4` |

Final 1080×1440, preview 720×960, H.264, silent.

### Agent skill

A distributable skill lives in `skill-package/story-to-handdrawn-video/` — copy it into your agent's skills directory and set `STORY_VIDEO_PROJECT` to this repo. See [SKILL.md](skill-package/story-to-handdrawn-video/SKILL.md) for the behavior contract.

### License

[MIT](LICENSE). The bundled Ma Shan Zheng font is under the [SIL Open Font License](public/fonts/OFL-MaShanZheng.txt).
