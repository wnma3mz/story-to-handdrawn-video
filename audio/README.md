# audio/ — 旁白

两条路径，**契约不同，不要混用**。选哪条取决于你要不要精确到帧的字幕轴。

| 文件 | 架构 | 适用 |
|---|---|---|
| `tts_engines.py` | **整组一次 TTS**，按字数权重切 cue | **短剧**（默认）。遵守渲染器「一组一次 TTS、组内不切句」的硬契约 |
| `tts_build_frame_accurate.py` | 逐句或逐字幕块合成，块边界天然精确 | 解说片。需要字幕与语音严格对齐、且能接受分块合成 |

## 为什么渲染器默认不支持更多引擎

`npm run build:audio` 只认两个后端：`edge-tts`（云端）与 `macos-say`（macOS）。
本地 CPU 引擎（piper / kokoro）与远端 IndexTTS-2.5 都用不上。

`tts_engines.py` 的做法是**不改 `build_story_audio.py`**，而是按它已有的缓存契约预填：

```
<workspace>/.work/<episode>/raw-groups/<GID>.mp3     整组合成的音频
<workspace>/.work/<episode>/raw-groups/<GID>.vtt     与 scene_ids 一一对应的字幕轴
<workspace>/.work/<episode>/raw-groups/<GID>.sha256  tts_cache_key 的值
```

sha256 与 `build_story_audio.py` 逐字节一致时，它会跳过合成直接用缓存。
因此「一组一次 TTS」的契约依然成立，审计链也完整。

```bash
# 用 piper 预合成，然后照常 build:audio
python3 audio/tts_engines.py --voiceover voiceover.json \
  --workspace "$STORY_VIDEO_WORKSPACE" --episode ep01 --engine piper
npm run build:audio -- --episode ep01
```

## 引擎

| 引擎 | 类型 | 词边界 | 说明 |
|---|---|---|---|
| `edge-tts` | 云端 | 有 | **渲染器原生**。字幕节拍最准 |
| `macos-say` | 本地 | 无 | **渲染器原生**。仅 macOS，音色机械 |
| `indextts2_5` | 远端 | 无 | 经 SSH 调 vLLM-Omni；`--lang` 选参考音频 |
| `piper` | 本地 CPU | 无 | 装最快，音色偏机械；树莓派可用 |
| `kokoro` | 本地 CPU | 无 | 需 espeak-ng；散文约 2.3 词/秒 |
| `kokoro_onnx` | 本地 CPU | 无 | ARM 友好，只要 onnxruntime，不要 torch/spaCy |

### IndexTTS-2.5 环境变量

```bash
export INDEXTTS_SSH_HOST=xpark
export INDEXTTS_URL=http://127.0.0.1:8000/v1/audio/speech
export INDEXTTS_REF_AUDIO=/path/to/ref.wav   # 覆盖按语言选的默认值
export INDEXTTS_SPEED=1.0
export INDEXTTS_SEED=42
```

默认参考音频按 `--lang` 选择，沿用 anything2explainer 的约定：

| lang | 默认参考音频（远端主机上的绝对路径） |
|---|---|
| `zh` | `/home/lu/projects/video-cn-dubber/f5-tts/zh_male_bj.wav` |
| `en` | `/home/lu/projects/video-cn-dubber/f5-tts/en_female_1.wav` |

## 两个未移植的能力，以及为什么

anything2explainer 的 `tts_build.py` 有两项本项目**没有**移植：

**能量谷字幕切分**（`energy_chunk_starts`）。它在整段音频里找能量低谷作为字幕切换点，
比按字数权重分配准。但渲染器要求 VTT cue 数**严格等于** `scene_ids` 数
（用这个等式把字幕和镜次一一绑定），而能量谷检出的数量取决于音频内容、不等于镜次数；
无台词镜次还要额外占零时长 cue。两者语义冲突，因此短剧路径仍用字数权重分配。

**逐字幕块分别合成再拼接**。这样块起始帧精确，但块界断句略生硬。
这正是 `tts_build_frame_accurate.py` 保留的价值——它把这条路径完整带过来了。

如果你的片子是解说而不是短剧，直接用 `tts_build_frame_accurate.py`；
如果需要精确字幕轴又想留在渲染器的审计链里，用 `tts_engines.py` 并接受
±0.6s 的同步误差上限（`continuity.maximum_sync_error_sec`）。

## 来源

`tts_build_frame_accurate.py` 与引擎实现移植自
[anything2explainer](https://github.com/wnma3mz/anything2explainer)
（PolyForm Noncommercial 1.0.0，原作者 Vincent Wei）。

原作者记录了一个必须知道的坑：**edge-tts 7.2.0 起 `boundary` 默认值从
`WordBoundary` 改成 `SentenceBoundary`**，不显式传就收不到词边界，
字幕会静默退化成按字数插值、偏半秒。本项目只用非 edge 引擎做预合成，
字幕轴按字数权重分配；要精确字幕轴请走渲染器原生的 edge-tts 后端。
