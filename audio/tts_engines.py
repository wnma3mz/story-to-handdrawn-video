#!/usr/bin/env python3
"""多引擎旁白预合成：把非 edge-tts 引擎的产出写进渲染器的 TTS 缓存。

    python3 audio/tts_engines.py \
      --voiceover voiceover.json --workspace "$STORY_VIDEO_WORKSPACE" \
      --episode ep01 --engine piper

为什么需要这个
--------------
渲染器自带的 `npm run build:audio` 只支持两个后端：edge-tts（云端，需联网）
与 macos-say（仅 macOS 且音色机械）。本地 CPU 引擎（kokoro / kokoro-onnx /
piper）与远端高质量引擎（IndexTTS-2.5）都用不上。

本脚本不改动 build_story_audio.py，而是按它已有的缓存契约预填文件：

    <workspace>/.work/<episode>/raw-groups/<GID>.mp3     整组一次合成的音频
    <workspace>/.work/<episode>/raw-groups/<GID>.vtt     与 scene_ids 一一对应的字幕轴
    <workspace>/.work/<episode>/raw-groups/<GID>.sha256  tts_cache_key 的值

sha256 一致时 build_story_audio.py 会跳过合成直接用缓存，因此
「一组一次 TTS、组内不切句」的硬契约依然成立。

来源：本文件的引擎实现移植自
https://github.com/wnma3mz/anything2explainer （PolyForm Noncommercial 1.0.0，
原作者 Vincent Wei）。原作者记录了一个关键坑：edge-tts 7.2.0 起
`boundary` 默认值从 WordBoundary 改成 SentenceBoundary，不显式传就收不到词边界，
字幕会静默退化成按字数插值。这里只用非 edge 引擎，字幕轴按字数权重分配，
偏差在可接受范围内；需要精确字幕轴请用渲染器原生的 edge-tts 后端。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 与 build_story_audio.py 的 write_proportional_vtt 保持一致的字幕切分规则：
# cue 数必须等于 scene_ids 数，空白台词镜次用零时长 cue 占位。
def format_vtt_timestamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def write_proportional_vtt(path: Path, cue_texts: list[str], duration: float) -> None:
    import re

    texts = [str(text).strip() for text in cue_texts]
    if not any(texts):
        raise ValueError("requires at least one non-empty cue_text")
    weights = [
        max(1, len(re.sub(r"\s+", "", text))) if text else 0 for text in texts
    ]
    total_weight = sum(weights)
    cursor = 0.0
    rows = ["WEBVTT", ""]
    for index, (text, weight) in enumerate(zip(texts, weights), start=1):
        if weight == 0:
            end = cursor
        elif index == len(texts):
            end = duration
        else:
            end = cursor + duration * weight / total_weight
        rows.extend(
            [
                str(index),
                f"{format_vtt_timestamp(cursor)} --> {format_vtt_timestamp(end)}",
                text,
                "",
            ]
        )
        cursor = end
    path.write_text("\n".join(rows), encoding="utf-8")


def tts_cache_key(text: str, profile: dict, cue_texts: list[str] | None) -> str:
    """与 build_story_audio.py 逐字节一致的缓存键算法。

    profile 必须是 voiceover.json 里的原对象——改动任何一个字段都会让
    build_story_audio.py 判定缓存失效并重新合成。
    """
    payload = json.dumps(
        {"text": text, "profile": profile, "cue_texts": cue_texts},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def media_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


# --------------------------------------------------------------------------
# 引擎实现。全部返回本地音频文件路径，格式不限（下游 ffmpeg 会转码）。
# --------------------------------------------------------------------------


def synth_piper(text: str, out: Path, lang: str = "zh") -> Path:
    """piper-tts：本地 CPU，最快，音色偏机械。"""
    model = os.environ.get("PIPER_MODEL", "en_US-ryan-medium.onnx")
    subprocess.run(
        ["piper", "--model", model, "--output_file", str(out)],
        input=text.encode("utf-8"),
        check=True,
    )
    return out


def synth_kokoro(text: str, out: Path, lang: str = "zh") -> Path:
    """kokoro：本地 CPU，需 espeak-ng。实测散文约 2.3 词/秒。"""
    from kokoro import KPipeline  # type: ignore

    voice = os.environ.get("KOKORO_VOICE", "am_liam")
    lang = os.environ.get("KOKORO_LANG", "a")
    speed = float(os.environ.get("KOKORO_SPEED", "1.0"))
    pipeline = KPipeline(lang_code=lang)
    chunks = [segment.audio for segment in pipeline(text, voice=voice, speed=speed)]
    if not chunks:
        raise RuntimeError("kokoro 未产出音频")
    return _concat_to_wav(chunks, out, 24000)


def synth_kokoro_onnx(text: str, out: Path, lang: str = "zh") -> Path:
    """kokoro-onnx：ARM 友好，只要 onnxruntime，不要 torch/spaCy。"""
    from kokoro_onnx import Kokoro  # type: ignore

    model = os.environ.get("KOKORO_ONNX_MODEL", "kokoro-v1.0.onnx")
    voices = os.environ.get("KOKORO_ONNX_VOICES", "voices-v1.0.bin")
    voice = os.environ.get("KOKORO_ONNX_VOICE", "am_michael")
    kokoro = Kokoro(model, voices)
    samples, _ = kokoro.create(text, voice=voice, speed=1.0, lang="en-us")
    return _pcm_to_wav(samples, out, 24000)


# 参考音频按语言自动选择，沿用 anything2explainer 的约定；路径是远端主机上的
# 绝对路径，用 INDEXTTS_REF_AUDIO 覆盖。
INDEXTTS_DEFAULT_REFS = {
    "zh": "/home/lu/projects/video-cn-dubber/f5-tts/zh_male_bj.wav",
    "en": "/home/lu/projects/video-cn-dubber/f5-tts/en_female_1.wav",
}


def synth_indextts2_5(text: str, out: Path, lang: str = "zh") -> Path:
    """IndexTTS-2.5：经 SSH 调远端 vLLM-Omni 的 OpenAI 兼容接口。

    参考音频与接口都只需远端可达，音频响应直接写回本地。
    不返回词边界，因此字幕轴由字数权重分配。
    """
    host = os.environ.get("INDEXTTS_SSH_HOST", "xpark")
    url = os.environ.get("INDEXTTS_URL", "http://127.0.0.1:8000/v1/audio/speech")
    ref = os.environ.get("INDEXTTS_REF_AUDIO", INDEXTTS_DEFAULT_REFS.get(lang, INDEXTTS_DEFAULT_REFS["zh"]))
    speed = os.environ.get("INDEXTTS_SPEED", "1.0")
    seed = os.environ.get("INDEXTTS_SEED", "42")
    remote_lang = lang

    params = json.dumps(
        {
            "url": url,
            "ref_audio": ref,
            "text": text,
            "speed": speed,
            "seed": seed,
            "lang": remote_lang,
        },
        ensure_ascii=False,
    )
    remote_script = f"""\
import base64, json, mimetypes, pathlib, sys, urllib.error, urllib.request

params = json.loads({params!r})
ref = pathlib.Path(params['ref_audio'])
if not ref.is_file():
    raise SystemExit(f"IndexTTS 参考音频不存在: {{ref}}")
mime = mimetypes.guess_type(ref.name)[0] or 'audio/wav'
reference = "data:" + mime + ";base64," + base64.b64encode(ref.read_bytes()).decode('ascii')
payload = {{
    'input': params['text'],
    'response_format': 'wav',
    'speed': params['speed'],
    'seed': params['seed'],
    'ref_audio': reference,
    'extra_params': {{'lang': params['lang'], 'emo_audio': reference}},
}}
request = urllib.request.Request(
    params['url'],
    data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
    headers={{'Content-Type': 'application/json'}},
)
try:
    with urllib.request.urlopen(request, timeout=3600) as response:
        sys.stdout.buffer.write(response.read())
except urllib.error.HTTPError as exc:
    raise SystemExit(f"IndexTTS HTTP {{exc.code}}: {{exc.read()[:500]!r}}") from exc
"""
    try:
        result = subprocess.run(
            ["ssh", host, "python3", "-"],
            input=remote_script.encode("utf-8"),
            capture_output=True,
            timeout=3700,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SystemExit("找不到 ssh 命令，无法连接 IndexTTS 主机") from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"IndexTTS 请求超时：ssh {host}") from exc

    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-800:]
        raise SystemExit(f"IndexTTS 调用失败（ssh {host}）：{detail}")
    if not result.stdout.startswith((b"RIFF", b"fLaC", b"ID3")):
        raise SystemExit("IndexTTS 没有返回有效音频")
    out.write_bytes(result.stdout)
    return out


def _pcm_to_wav(samples, out: Path, sample_rate: int) -> Path:
    import numpy as np

    wave = np.asarray(samples, dtype=np.float32)
    if wave.ndim > 1:
        wave = wave.mean(axis=1)
    pcm = np.clip(wave * 32767.0, -32768, 32767).astype("<i2")
    out.write_bytes(_wav_bytes(pcm.tobytes(), sample_rate, channels=1, width=2))
    return out


def _concat_to_wav(chunks: list, out: Path, sample_rate: int) -> Path:
    import numpy as np

    arrays = [np.asarray(chunk, dtype=np.float32).reshape(-1) for chunk in chunks]
    return _pcm_to_wav(np.concatenate(arrays), out, sample_rate)


def _wav_bytes(pcm: bytes, sample_rate: int, channels: int, width: int) -> bytes:
    import wave

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        temp = Path(handle.name)
    try:
        with wave.open(str(temp), "wb") as writer:
            writer.setnchannels(channels)
            writer.setsampwidth(width)
            writer.setframerate(sample_rate)
            writer.writeframes(pcm)
        return temp.read_bytes()
    finally:
        temp.unlink(missing_ok=True)


ENGINES = {
    "piper": synth_piper,
    "kokoro": synth_kokoro,
    "kokoro_onnx": synth_kokoro_onnx,
    "indextts2_5": synth_indextts2_5,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="用本地或远端引擎预合成旁白，写入渲染器的 TTS 缓存"
    )
    parser.add_argument("--voiceover", required=True, type=Path)
    parser.add_argument("--workspace", type=Path, default=Path(os.environ.get("STORY_VIDEO_WORKSPACE", ".")))
    parser.add_argument("--episode", default=os.environ.get("EPISODE", "default"))
    parser.add_argument("--engine", required=True, choices=sorted(ENGINES))
    parser.add_argument(
        "--lang",
        default="zh",
        choices=("zh", "en"),
        help="IndexTTS-2.5 按语言选参考音频；其余引擎忽略",
    )
    parser.add_argument("--voice", default="", help="覆盖 voiceover.json 里的 voice（仅 piper/kokoro 有意义）")
    parser.add_argument("--jobs", type=int, default=1, help="并发组数；远端引擎建议保持 1")
    parser.add_argument("--force", action="store_true", help="忽略已有缓存重新合成")
    args = parser.parse_args()

    if not args.voiceover.exists():
        print(f"错误：找不到 voiceover 配置 {args.voiceover}", file=sys.stderr)
        return 2

    config = json.loads(args.voiceover.read_text(encoding="utf-8"))
    profile = config["profile"]
    groups = config["continuity"]["groups"]
    if not groups:
        print("voiceover.json 里没有旁白组", file=sys.stderr)
        return 2

    raw_dir = args.workspace / ".work" / args.episode / "raw-groups"
    raw_dir.mkdir(parents=True, exist_ok=True)

    synthesize = ENGINES[args.engine]
    prepared = 0

    for group in groups:
        group_id = str(group["id"])
        speech_text = group["speech_text"]
        cue_texts = group.get("cue_texts")

        raw = raw_dir / f"{group_id}.mp3"
        vtt = raw_dir / f"{group_id}.vtt"
        key_path = raw_dir / f"{group_id}.sha256"
        expected = tts_cache_key(speech_text, profile, cue_texts)

        if (
            not args.force
            and raw.exists()
            and vtt.exists()
            and key_path.exists()
            and key_path.read_text(encoding="utf-8").strip() == expected
        ):
            print(f"  {group_id} 缓存命中，跳过")
            continue

        if args.voice:
            os.environ["KOKORO_VOICE"] = args.voice
            os.environ["KOKORO_ONNX_VOICE"] = args.voice
            os.environ["PIPER_MODEL"] = args.voice

        print(f"  {group_id} 合成中（{len(speech_text)} 字）…")
        with tempfile.TemporaryDirectory() as temp_dir:
            produced = synthesize(
                speech_text, Path(temp_dir) / f"{group_id}.audio", args.lang
            )
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(produced),
                 "-c:a", "libmp3lame", "-q:a", "2", str(raw)],
                check=True,
            )

        write_proportional_vtt(vtt, cue_texts or [speech_text], media_duration(raw))
        key_path.write_text(expected + "\n", encoding="utf-8")
        prepared += 1

    print(
        f"\n已写入 {prepared} 组到 {raw_dir}\n"
        f"接着运行：npm run build:audio -- --episode {args.episode} --workspace {args.workspace}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
