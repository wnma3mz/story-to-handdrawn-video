#!/usr/bin/env python3
"""解析上游内容层（content/）产出的 Markdown 中间产物。

上游 content/skills 的执行提示词产出的是给人看的 Markdown，不是给程序读的
JSON。本模块是唯一的解析入口，把三份 Markdown 归一化成 dataclass：

  05_资产登记_EPxx.md        → AssetRegistry
  07_分镜面板_EPxx.md        → list[PanelShot]
  03_剧本_EPxx.md            → ScriptDoc

其余编译器（compile_storyboard / compile_image_jobs / compile_narration /
verify_lock）都只依赖本模块，不各自重复解析。

来源格式见 content/examples/中间人/。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ADAPTERS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ADAPTERS_DIR.parent
MOTION_MAP_PATH = ADAPTERS_DIR / "motion_map.json"

# 上游红线 2：分镜表与分镜提示词禁止出现光影、色温、明暗、色调词。
# 光影由场景参考图承担，这里做机器校验，而不是只写在文档里。
#
# 分两级，避免子串误报：
#   phrases —— 多字词，命中即违规（高置信）
#   chars   —— 单字，命中才违规，但需先剔除普通词白名单（低置信）
# 早期版本用单字「光」「影」直接判违规，会把「电影质感」「背影」一起报上来。
LIGHTING_BANNED_PHRASES = (
    "光线", "光影", "光晕", "轮廓光", "丁达尔", "色温", "色调",
    "暖色", "冷色", "冷调", "暖调", "逆光", "侧光", "顶光", "底光",
    "明暗", "高对比", "低对比", "曝光", "亮度", "阴影", "高光",
    "柔光", "硬光", "环境光", "自然光", "人造光", "打光",
)

LIGHTING_BANNED_CHARS = ("光", "影")

# 含「光」「影」但与光影无关的普通词
LIGHTING_ALLOWED_TERMS = (
    "电影", "电视", "影像", "影响", "背影", "倩影", "摄影", "掠影",
    "目光", "眼光", "月光下的人", "视线",
)


def load_motion_map() -> dict[str, Any]:
    return json.loads(MOTION_MAP_PATH.read_text(encoding="utf-8"))


class ParseError(ValueError):
    """Markdown 结构与上游契约不符。"""


def normalize(text: str) -> str:
    """全角转半角、去空白、统一标点，供关键词匹配使用。"""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", text)


def find_lighting_violations(text: str) -> list[str]:
    """返回文本中命中的光影类禁用词，按多字词优先、保持出现顺序。

    先在原文上剔除白名单普通词，再做单字判定，避免「电影质感」被误报。
    """
    hits: list[str] = []
    for phrase in LIGHTING_BANNED_PHRASES:
        if phrase in text and phrase not in hits:
            hits.append(phrase)

    scrubbed = text
    for allowed in LIGHTING_ALLOWED_TERMS:
        scrubbed = scrubbed.replace(allowed, "　" * len(allowed))
    for char in LIGHTING_BANNED_CHARS:
        if char in scrubbed and char not in hits:
            hits.append(char)
    return hits


# --------------------------------------------------------------------------
# 资产登记
# --------------------------------------------------------------------------

ASSET_KINDS = {"role": "角色", "tool": "道具", "scene": "场景"}

# 全剧一张资产表，ID 不按集重置（上游 S5 契约）
ROLE_ID_RANGE = (100, 199)
PROP_ID_RANGE = (200, 299)
SCENE_ID_RANGE = (300, 399)


@dataclass(frozen=True)
class Asset:
    id: str
    name: str
    note: str
    kind: str

    @property
    def numeric_id(self) -> int | None:
        """衍生资产 ID 形如 301-N，取其数字前缀用于区间校验。"""
        match = re.match(r"^(\d+)", self.id)
        return int(match.group(1)) if match else None

    @property
    def derivative_suffix(self) -> str | None:
        match = re.match(r"^\d+-(.+)$", self.id)
        return match.group(1) if match else None

    @property
    def is_derivative(self) -> bool:
        return self.derivative_suffix is not None


@dataclass
class AssetRegistry:
    assets: dict[str, Asset] = field(default_factory=dict)

    def by_kind(self, kind: str) -> list[Asset]:
        return [a for a in self.assets.values() if a.kind == kind]

    def scene_ids(self) -> set[str]:
        return {a.id for a in self.by_kind("scene")}

    def role_ids(self) -> set[str]:
        return {a.id for a in self.by_kind("role")}

    def prop_ids(self) -> set[str]:
        return {a.id for a in self.by_kind("tool")}

    def describe(self) -> str:
        lines = []
        for kind, label in ASSET_KINDS.items():
            group = self.by_kind(kind)
            if not group:
                continue
            lines.append(f"{label}（{kind}）：")
            for asset in sorted(group, key=lambda a: a.numeric_id or 0):
                lines.append(f"  {asset.id:<6} {asset.name}")
        return "\n".join(lines)


_ASSET_TABLE_ROW = re.compile(
    r"^\|\s*(?P<id>[0-9]+(?:-[A-Za-z0-9]+)?)\s*\|\s*(?P<name>[^|]+?)\s*\|\s*(?P<note>[^|]*?)\s*\|?\s*$"
)
_ASSET_SECTION = re.compile(
    r"^#{1,4}\s*[（(\[]?\s*(?P<kind>role|tool|scene)\s*[)）\]]?\s*(?:资产)?\s*$",
    re.IGNORECASE,
)


def parse_asset_registry(path: Path) -> AssetRegistry:
    """解析 05_资产登记_EPxx.md。

    上游示例的章节标题是「## 角色资产（role）」这类形式，这里按 role/tool/
    scene 关键字识别，不依赖标题的完整写法。
    """
    registry = AssetRegistry()
    current_kind: str | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue

        heading = re.match(r"^#{1,4}\s+(.*)$", line)
        if heading:
            title = heading.group(1)
            for kind, label in ASSET_KINDS.items():
                if kind in title.lower() or label in title:
                    current_kind = kind
                    break
            continue

        if current_kind is None or not line.startswith("|"):
            continue

        row = _ASSET_TABLE_ROW.match(line)
        if not row:
            continue

        asset_id = row.group("id")
        if asset_id in registry.assets:
            raise ParseError(
                f"{path.name}: 资产 ID 重复 {asset_id}（全剧 ID 不得重复或改号）"
            )
        registry.assets[asset_id] = Asset(
            id=asset_id,
            name=row.group("name").strip(),
            note=row.group("note").strip(),
            kind=current_kind,
        )

    if not registry.assets:
        raise ParseError(f"{path.name}: 未解析出任何资产，检查章节标题是否含 role/tool/scene")

    errors = validate_registry_ids(registry)
    if errors:
        raise ParseError(f"{path.name}: " + "；".join(errors))

    return registry


def validate_registry_ids(registry: AssetRegistry) -> list[str]:
    """校验 ID 落在约定区间：角色 1xx、道具 2xx、场景 3xx。"""
    errors: list[str] = []
    ranges = {"role": ROLE_ID_RANGE, "tool": PROP_ID_RANGE, "scene": SCENE_ID_RANGE}
    for asset in registry.assets.values():
        numeric = asset.numeric_id
        if numeric is None:
            errors.append(f"资产 {asset.id} 不是合法 ID")
            continue
        low, high = ranges[asset.kind]
        if not low <= numeric <= high:
            errors.append(
                f"资产 {asset.id}（{asset.kind}）超出区间 "
                f"{low}-{high}：角色 1xx、道具 2xx、场景 3xx"
            )
        if asset.kind in ("role", "prop") and asset.is_derivative:
            errors.append(
                f"资产 {asset.id}：{asset.kind} 不允许衍生资产"
                "（角色衍生仅限服装/变身特效，道具永不衍生）"
            )
    return errors


# --------------------------------------------------------------------------
# 分镜面板
# --------------------------------------------------------------------------

_PANEL_HEADING = re.compile(
    r"^###\s*track\s+(?P<track>\d+)\s*·\s*镜(?P<shot>\d+)\s*"
    r"（\s*(?P<duration>[\d.]+)\s*s\s*）"
    r"(?:\s*｜\s*shouldGenerateImage\s*[:：]\s*(?P<should_image>true|false))?"
    r"(?:\s*｜\s*associateAssetsIds\s*[:：]\s*[\[【]\s*(?P<asset_ids>[^\]】]*)\s*[\]】])?"
    r"\s*$"
)
_PANEL_SCENE_HEADING = re.compile(r"^##\s*场(?P<index>\d+)[：:]\s*(?P<name>.+?)\s*$")
_PROMPT_FENCE = re.compile(r"^\*\*prompt[^*]*\*\*[：:]\s*$")
_VIDEODESC = re.compile(r"^\*\*videoDesc\*\*[：:]\s*(?P<body>.+?)\s*$")
_VIDEODESC_FIELD = re.compile(r"【(?P<key>[^】]+)】(?P<value>.*?)(?=【|$)", re.DOTALL)

# 台词是唯一不允许剥尾部句号的字段：上游红线 1 要求台词逐字一致，
# 句号属于台词原文。videoDesc 用句号分隔字段，非台词字段的尾句号是分隔符。
PUNCT_STRIPPED_FIELDS = ("场景", "景别", "运镜", "画面描述", "角色动作", "朝向", "情绪", "音效")

# videoDesc 的【台词】段写「无。」表示本镜无台词
NO_DIALOGUE_MARKERS = frozenset({"无", "无台词", "无对白", "-", "—"})

# 分镜面板正文里的角色朝向标记，例如「3/4正面朝右」
ORIENTATION_RE = re.compile(r"(?:(?P<name>[一-鿿]{2,4})[-－])?(?P<orient>(?:\d/\d)?正面朝[左右]|背面朝[左右]|侧面对?[左右]|面朝[左右])")


@dataclass
class PanelShot:
    track: int
    shot_index: int
    scene_index: int
    scene_name: str
    duration_sec: float
    should_generate_image: bool
    asset_ids: list[str]
    video_desc: str
    fields: dict[str, str]
    prompt: str

    @property
    def scene_id(self) -> str:
        return self.fields.get("场景", "")

    @property
    def shot_size(self) -> str:
        return self.fields.get("景别", "")

    @property
    def camera_move(self) -> str:
        return self.fields.get("运镜", "")

    @property
    def picture(self) -> str:
        return self.fields.get("画面描述", "")

    @property
    def sfx(self) -> str:
        return self.fields.get("音效", "")

    @property
    def emotion(self) -> str:
        return self.fields.get("情绪", "")

    @property
    def dialogue_raw(self) -> str:
        return self.fields.get("台词", "")

    @property
    def _speech_parts(self) -> tuple[str | None, str]:
        """把【台词】段拆成 (说话人, 台词正文)。

        上游格式为 `角色名：台词`，OS 画外音写作 `OS角色名：台词`，
        也存在 `角色名：（低声）台词` 这类情绪前缀。

        台词正文保留尾部句号——上游红线 1 要求台词逐字一致，句号是原文的一部分。
        只有整段就是「无。」这类占位符时才判定为本镜无台词。
        """
        raw = self.dialogue_raw.strip()
        if not raw or raw.rstrip("。").strip() in NO_DIALOGUE_MARKERS:
            return None, ""
        speaker, sep, content = raw.partition("：")
        if not sep or len(speaker) > 12:
            # 冒号前不是说话人标签，视为台词自身内容
            return None, raw
        return re.sub(r"^OS", "", speaker).strip() or None, content.strip()

    @property
    def dialogue(self) -> str:
        """台词正文，已剥离说话人前缀与尾部分隔句号。"""
        return self._speech_parts[1]

    @property
    def speaker(self) -> str | None:
        return self._speech_parts[0]

    @property
    def is_voiceover(self) -> bool:
        """OS（画外音）标记的台词不写在字幕里，但计入旁白时长。"""
        return self.dialogue_raw.strip().startswith("OS")

    @property
    def orientations(self) -> list[tuple[str | None, str]]:
        return [
            (m.group("name"), m.group("orient"))
            for m in ORIENTATION_RE.finditer(self.picture + self.fields.get("朝向", ""))
        ]


def parse_storyboard_panel(path: Path) -> list[PanelShot]:
    """解析 07_分镜面板_EPxx.md（首位帧模式）。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    shots: list[PanelShot] = []

    scene_index = 0
    scene_name = ""
    current: PanelShot | None = None
    in_prompt = False
    prompt_lines: list[str] = []
    prompt_opened = False

    def flush() -> None:
        nonlocal current
        if current is not None:
            current.prompt = "\n".join(prompt_lines).strip()
            shots.append(current)
            current = None

    for raw in lines:
        line = raw.rstrip()

        if current is None:
            scene_heading = _PANEL_SCENE_HEADING.match(line.strip())
            if scene_heading:
                scene_index = int(scene_heading.group("index"))
                scene_name = scene_heading.group("name").strip()
                continue
            heading = _PANEL_HEADING.match(line.strip())
            if heading:
                ids = heading.group("asset_ids") or ""
                current = PanelShot(
                    track=int(heading.group("track")),
                    shot_index=int(heading.group("shot")),
                    scene_index=scene_index,
                    scene_name=scene_name,
                    duration_sec=float(heading.group("duration")),
                    should_generate_image=(heading.group("should_image") or "true") == "true",
                    asset_ids=[i.strip() for i in ids.split(",") if i.strip()],
                    video_desc="",
                    fields={},
                    prompt="",
                )
                prompt_lines = []
                in_prompt = False
                prompt_opened = False
            continue

        if in_prompt:
            if line.strip().startswith("```"):
                if prompt_opened:
                    in_prompt = False
                    flush()
                    continue
                prompt_opened = True
                continue
            prompt_lines.append(line)
            continue

        if _PROMPT_FENCE.match(line.strip()):
            in_prompt = True
            prompt_lines = []
            prompt_opened = False
            continue

        desc = _VIDEODESC.match(line.strip())
        if desc:
            body = desc.group("body")
            current.video_desc = body
            fields: dict[str, str] = {}
            for match in _VIDEODESC_FIELD.finditer(body):
                key = match.group("key")
                value = match.group("value").strip()
                if key in PUNCT_STRIPPED_FIELDS:
                    value = value.rstrip("。 ").strip()
                fields[key] = value
            current.fields = fields
            continue

        if line.strip() == "---":
            flush()

    flush()

    if not shots:
        raise ParseError(f"{path.name}: 未解析出任何镜次，检查是否使用首位帧模式的 track 标题格式")

    return shots


# --------------------------------------------------------------------------
# 剧本
# --------------------------------------------------------------------------

# 说话人标签。允许 `名字` 与 `名字（情绪）` 两种形式，画外音写作 `OS（名字，情绪）：`
# 且台词另起一行。冒号右侧允许为空，那种情况说话人留给下一行。
_SCRIPT_SPEECH = re.compile(
    r"^(?P<speaker>[A-Za-z0-9一-鿿·]{1,12}(?:[（(][^）)]{0,30}[）)])?)[：:](?P<line>.*?)\s*$"
)
_SCRIPT_SCENE = re.compile(r"^\{(?P<index>[^}]+)\}\s*(?P<rest>.*)$")
_SCRIPT_CAST = re.compile(r"^人物[：:]\s*(?P<cast>.+?)\s*$")


@dataclass
class ScriptLine:
    speaker: str
    text: str
    scene_index: str | None
    is_voiceover: bool


@dataclass
class ScriptDoc:
    title: str
    lines: list[ScriptLine] = field(default_factory=list)

    @property
    def dialogue_texts(self) -> list[str]:
        """按出现顺序的全部台词正文，供逐字比对使用。"""
        return [line.text for line in self.lines]


def parse_script(path: Path) -> ScriptDoc:
    """解析 03_剧本_EPxx.md，抽取全部台词（上游红线 1 的基准文本）。

    上游对画外音用两行写法，说话人与台词分行：

        OS（舒十七，漫不经心）：
        着急就露了底牌，价，也就抬不上去了。

    而分镜面板写成单行 `OS舒十七：着急就露了底牌……`。两种写法都要认，
    否则台词锁会把画外音全部误报成「剧本中找不到原文」。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    title = ""
    scene_index: str | None = None
    doc = ScriptDoc(title=title)
    pending_speaker: str | None = None

    # 集标题写在 <scriptItem name="作品名 EP01：集标题"> 上，其次是首个 # 标题
    item_name = re.search(r'<scriptItem\s+name="([^"]+)"', "\n".join(lines))
    if item_name:
        title = item_name.group(1).strip()
        doc.title = title

    def clean_speaker(raw: str) -> str:
        """剥掉括号里的情绪标注：`OS（舒十七，漫不经心）` → `OS舒十七`。"""
        base = raw.split("（")[0].split("(")[0].strip()
        return base

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if line.startswith("# ") and not title:
            title = line[2:].strip()
            doc.title = title
            continue

        if line.startswith(("---", "===")):
            continue

        scene = _SCRIPT_SCENE.match(line)
        if scene:
            scene_index = scene.group("index").strip()
            pending_speaker = None
            continue

        if _SCRIPT_CAST.match(line):
            continue

        # △ 动作行、转场标记、自检清单一律跳过
        if line.startswith(("△", "[", ">", "-", "*", "|")):
            pending_speaker = None
            continue

        speech = _SCRIPT_SPEECH.match(line)
        if speech:
            speaker = clean_speaker(speech.group("speaker"))
            body = speech.group("line").strip()
            if body:
                doc.lines.append(
                    ScriptLine(
                        speaker=speaker,
                        text=body,
                        scene_index=scene_index,
                        is_voiceover=speaker.startswith("OS"),
                    )
                )
                pending_speaker = None
            else:
                # `OS（角色，情绪）：` 单独成行，台词在下一行
                pending_speaker = speaker
            continue

        # 承接上一行的说话人标签
        if pending_speaker is not None:
            doc.lines.append(
                ScriptLine(
                    speaker=pending_speaker,
                    text=line,
                    scene_index=scene_index,
                    is_voiceover=pending_speaker.startswith("OS"),
                )
            )
            pending_speaker = None
            continue

    if not doc.lines:
        raise ParseError(f"{path.name}: 未解析出任何台词，无法作为台词锁的基准")

    return doc


def collect_lighting_violations(shots: list[PanelShot]) -> list[tuple[int, str, list[str]]]:
    """扫描分镜面板的画面描述与提示词，回报光影禁用词命中情况。

    只查画面描述与提示词——videoDesc 的【音效】段写「楼下市声」是正常的，
    但为免误报，这里精确取画面描述、角色动作、情绪三段。
    """
    findings: list[tuple[int, str, list[str]]] = []
    for shot in shots:
        checked = "。".join(
            [
                shot.picture,
                shot.fields.get("角色动作", ""),
                shot.emotion,
                shot.prompt,
            ]
        )
        hits = find_lighting_violations(checked)
        if hits:
            findings.append((shot.track, "分镜面板", hits))
    return findings
