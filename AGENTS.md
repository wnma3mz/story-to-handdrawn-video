# Agent 作业入口

本仓库把小说或故事文本变成可发布的视频。**文件是唯一事实来源，聊天上下文不是。**
接手任务时先读本文件，再读状态文件列出的已批准产物，不要凭摘要继续工作。

## 三个上游项目

本仓库由三个开源项目合并而成，各承担一层职责：

| 层 | 项目 | 链接 | 授权 |
|---|---|---|---|
| L1 内容层 | Toonflow Adapter Kit（提示词提取自 Toonflow-app） | https://github.com/wnma3mz/toonflow-adapter-kit ・ https://github.com/HBAI-Ltd/Toonflow-app | MIT |
| L2/L3 渲染器 | story-to-handdrawn-video | https://github.com/wnma3mz/story-to-handdrawn-video ・ https://github.com/gnipbao/story-to-handdrawn-video | MIT |
| L3 配音与质检 | anything2explainer | https://github.com/wnma3mz/anything2explainer | PolyForm Noncommercial |

**因为 anything2explainer 是非商用授权，本仓库整体为非商用。**
详见 `THIRD_PARTY_NOTICES.md`。

## 三层管线

```
输入：小说 / 故事文案
  │
  ├─ L1 内容层  content/skills/*.md 作为系统提示词，产出 Markdown
  │    S1 故事骨架 → S2 改编策略 → S3 分集剧本 → S4 导演规划
  │    S5 全局资产登记 + 资产提示词 → S6 分镜表 → S7 分镜面板
  │
  ├─ 编译层  adapters/
  │    分镜面板 → storyboard.json
  │    资产提示词 → codex-image-jobs.json（三级依赖图）
  │    storyboard.json → voiceover.json（按场分组）
  │    verify_lock.py 复查十条红线
  │
  ├─ 出图  按依赖图执行 codex-image-jobs.json
  │    references（角色四视图 + 道具四宫格）并发 1
  │      → scenes（场景主视图，无人）
  │        → shots（逐镜合成图）并发 N
  │    import:codex 派生黑白层与彩色层
  │
  ├─ 渲染  Remotion，两条 composition 共用一份 storyboard.json
  │    PictureSilent        handdrawn：AI 生图 + 代码动效
  │    MotionGraphicsSilent 纯代码绘制，不经过出图
  │
  ├─ 配音  一组一次 TTS，组内不切句；5 个后端可选
  │
  └─ 交付  封面 + 配音版 + 发布版 + 审计报告
```

## 阶段与唯一产物

| 阶段 | 产物 | 门禁 |
|---|---|---|
| S0 项目建档 | `00_项目配置.md`、`00_项目状态.md` | 配置无空项；集数与画幅固定 |
| S1 故事骨架 | `01_故事骨架.md` | 每集有独立戏剧目标与结尾钩子 |
| S2 改编策略 | `02_改编策略.md` | 每处改动可追溯到原著；核心故事不动 |
| S3 分集剧本 | `03_剧本/03_剧本_EPxx.md` | EP01→末集严格串行；**批准后台词锁定** |
| S4 导演规划 | `04_导演规划/04_导演规划_EPxx.md` | 覆盖剧本；角色齐；逐场目标与情绪 |
| S5 全局资产 | `05_全局资产登记.md`、`05_资产提示词.md`、`assets_ref/` | 先合并同实体再建衍生；ID 全剧不重置 |
| S6 分镜表 | `06_分镜表/06_分镜表_EPxx.md` | 场景与台词 100% 覆盖；单镜 ≤8s |
| S7 分镜面板 | `07_分镜面板/07_分镜面板_EPxx.md` | 一镜一 track，**track 全剧唯一递增** |
| S8 编译与校验 | `storyboard.json`、`codex-image-jobs.json`、`voiceover.json`、`verify.json` | `adapt:verify` 零阻断 |
| S9 出图与导入 | `assets_ref/*.png`、`*_color.png` | 素材存在且尺寸一致 |
| S10 渲染与配音 | `out/<ep>/silent.mp4`、`voiced/*.mp4` | 画面母版与旁白同时起 |
| S11 交付验收 | `out/releases/<ep>.mp4`、`audit` 报告 | `audit:delivery` 零 FAIL |

## 十条红线

跨阶段不变量，违反即视为不合格。`adapters/verify_lock.py` 机器校验其中九条。

1. 台词逐字一致 —— 剧本 → 分镜表 → 分镜面板 → storyboard.json → 字幕
2. 分镜表与分镜提示词**禁**光影、色温、明暗、色调词；光影只由场景参考图承载
3. 禁 BGM，只写音效
4. 台词与音效不得进入出图提示词
5. 片段 ≤15s，单镜 ≤8s
6. 超过 20 字的台词必须拆到多个镜头
7. 每个上场角色都必须入画
8. 每镜恰引一个场景 ID；每个可辨认角色道具（含背面、局部）均引其 ID
9. 角色四视图：素颜、基础服装、无配饰、`#E8EAF5` 背景、四视图一致
10. 道具四宫格为纯静物（无人无手）；场景主视图无人物

## 执行规则

- 严格按 S0→S11 顺序执行，不越过未通过的质量门。
- 每次只负责状态文件中标记为 `IN_PROGRESS` 的一个阶段。
- 开始前把该阶段写为 `IN_PROGRESS`；完成自审后写 `REVIEW`；验收通过写 `APPROVED`。
- 上游产物 `APPROVED` 后视为锁定。必须修改时，先把所有受影响下游回退 `NOT_STARTED`。
- 全剧共用一份资产登记表。角色 `1xx`、道具 `2xx`、场景 `3xx`，不按集重置。
- **track 全局递增**，EP01 从 001 起，任何一集都不重置。
- 剧本批准后台词锁定。导演规划、分镜表、分镜面板中的台词必须逐字一致。
- 渲染器仓库是只读基础设施。当前任务的产物全部写入 `STORY_VIDEO_WORKSPACE`，
  路径只用相对量，以便整目录拷到另一台机器继续。
- 不生成 BGM。`background_music.enabled` 默认关闭。

## 完成定义

只有当状态文件中 S0–S11 全部 `APPROVED`、所有目标集都有剧本与分镜、
所有被引用资产都有本地参考图、`audit:delivery` 与 `adapt:verify` 均零 FAIL 时，
才可以宣称「整部小说流程完成」。

## 不要做的事

- 不要把 `content/skills/*_agent_decision.md` 与 `*_agent_supervision.md` 里
  依赖 Toonflow 运行时工具的调用指令照搬到本流程。只吸收其决策、执行与监督原则。
- 不要用画面描述填 `narration`。无台词镜次的 `narration` 应为空串——
  填了会把短剧变成解说。
- 不要给场景主视图挂角色参考图。场景规格是「无人」，挂了人物会被画进场景。
- 不要在 motiongraphics 路径上用 `plate_mode=code`（12 图元白名单与
  `mg_plate` 词汇表互不重叠），`Scene.tsx` 会直接报错。
- 不要跨过 `verify_lock` 直接渲染。台词对不上是最贵的一类返工。
- 不要用画面描述填 `narration`，不要给场景母图挂角色参考图（详见 README 与本文件上文）。

## 参考资料

`agent-rules/` 是多 Agent 作业的规范集，做 motiongraphics 或解说片时必读：

| 文件 | 作用 |
|---|---|
| `motion-vocabulary.md` | 入场/强调/光效/离场/运镜的公式与帧数 |
| `composition-and-light.md` | 三级字号、光随主体走、set-piece 编排、量化阈值 |
| `narration-storyboard.md` | 解说词格式、TTS 参数、22 类镜头设计模式表 |
| `agent-build-rules.md` / `agent-qc-rules.md` | 构建与质检 Agent 的协议 |
| `prompts.md` | 6 段可直接贴的 Agent 提示词 |
| `lessons.md` | 原作者 5 部片子踩过的坑，199 行——**动 renderer 前先读** |
| `research-brief.md` | 调研 Agent 规范，含提示词注入防护 |
| `style-guide.md` | 画布安全区、调色板、字体、图元目录 |
