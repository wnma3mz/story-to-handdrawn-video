# agent-rules/ — 多 Agent 作业规范

来自 [anything2explainer](https://github.com/wnma3mz/anything2explainer)
（PolyForm Noncommercial 1.0.0，原作者 Vincent Wei）的 `reference/` 目录，
含原作者切换到 IndexTTS-2.5 后的最新版本，**9 个文件逐字节并入、未改动**。

这些是本项目里最接近「品味」的部分——不好读的规则没法交给 Agent 执行。

| 文件 | 作用 |
|---|---|
| `motion-vocabulary.md` | 入场/强调/光效/离场/运镜的公式与帧数，含闪烁白名单规则 |
| `composition-and-light.md` | 三级字号、光随主体走、set-piece 编排、量化阈值 |
| `narration-storyboard.md` | 解说词格式、TTS 参数、22 类镜头设计模式表 |
| `style-guide.md` | 画布安全区、调色板、字体、图元目录、版式规律 |
| `agent-build-rules.md` | 构建 Agent 协议，含性能红线与自检义务 |
| `agent-qc-rules.md` | 质检 Agent 协议，10 类分级检查 |
| `prompts.md` | 6 段可直接贴的 Agent 提示词 |
| `research-brief.md` | 调研 Agent 规范，含提示词注入防护 |
| `lessons.md` | 原作者 5 部片子踩过的坑，199 行 |
| `contrast/` | 6 组 bad/good 帧对 + 对比表 |

## 什么时候读哪一份

- **动渲染器之前** → 先读 `lessons.md`。里面有 `kf` 首值陷阱、`fadeIn(0)=0`、
  字号缩到 22px 以下、滑块穿过字幕带、闪烁从 102 处滥用到 21 处等真实坑。
- **做 motiongraphics 或解说片** → `motion-vocabulary.md` + `composition-and-light.md`
  + `narration-storyboard.md` 的镜头模式表。`src/compositions/motiongraphics/Motif.tsx`
  的图元分类就是从那张表来的。
- **判断画面够不够好** → 打开 `contrast/contrast_sheet.jpg`。那 6 组帧对是客观标尺：
  主体太小、揭示没做、轴线稀疏、公式糊成 debris、背景杂乱、片尾泄气。
- **派 Agent 干活** → `prompts.md` 直接贴。注意原作者把「参考」改成了「必读」
  ——第二部片子证实没人真的去读示例帧。

## 与本项目其余部分的关系

这些规范写的是 a2e 自己的画布（1280×720 黑底、白色线稿 + 紫色强调色）。
本项目的 handdrawn 路径是白纸手账风、`src/compositions/motiongraphics/` 沿用其骨架，
因此：

- **可直接用**：多 Agent 协议、镜头设计模式表、构图与光的定量阈值、踩坑记录
- **需按本项目调整**：画布尺寸、字体栈、调色板、字幕带位置（见 `style-guide.md`）

`lessons.md` 记录的是原作者个人经验，引用时同样受非商用条款约束。
