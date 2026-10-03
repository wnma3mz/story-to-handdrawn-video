import type {MotionGraphicsMotif as MotifId} from '../../types';

/**
 * 程序化画面图元：全部用 SVG 画，不调用任何图像生成。
 *
 * 来源与改编：图元分类与构图取向参考
 * https://github.com/wnma3mz/anything2explainer （PolyForm Noncommercial 1.0.0，
 * 原作者 Vincent Wei）的 narration-storyboard.md「镜头设计模式表」——
 * 那份表把「讲流程」「对比」「列清单」等叙事意图映射到具体画法。
 * 这里只保留其中不依赖具体片子的骨架，按本项目的 handdrawn 画风重画。
 *
 * 与 handdrawn composition 的区别：那条路径用 AI 生成的插图当底片，
 * 这条路径完全用代码绘制，因此不需要出图环节，适合文字密度高的解说与旁白片。
 */

const INK = '#2b2b2b';
const PAPER = '#FCFAF5';
const ACCENT = '#8B6E4E';

/** 确定性伪随机，保证每次渲染的笔触一致（可复现的渲染是硬要求）。 */
export const seededRandom = (seed: number): (() => number) => {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

const roughLine = (
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  wobble: number,
  rand: () => number,
): string => {
  const midX = (x1 + x2) / 2 + (rand() - 0.5) * wobble;
  const midY = (y1 + y2) / 2 + (rand() - 0.5) * wobble;
  return `M ${x1} ${y1} Q ${midX} ${midY} ${x2} ${y2}`;
};

export type MotifProps = {
  motif: MotifId;
  width: number;
  height: number;
  seed?: number;
  headline?: string;
  detail?: string;
};

const FlowMotif: React.FC<{w: number; h: number; rand: () => number}> = ({w, h, rand}) => {
  const steps = 4;
  const gap = w * 0.045;
  const boxW = (w - gap * (steps - 1)) / steps;
  // 高度按内容区自适应：固定像素会让 9:16 下上下各空掉六成画面
  const boxH = h * 0.34;
  const top = (h - boxH) / 2;
  return (
    <>
      {Array.from({length: steps}).map((_, i) => {
        const x = i * (boxW + gap);
        return (
          <g key={i}>
            <rect
              x={x} y={top} width={boxW} height={boxH} rx={6}
              fill={i % 2 === 0 ? PAPER : '#f2ece0'} stroke={INK} strokeWidth={2.5}
            />
            {i < steps - 1 ? (
              <path
                d={roughLine(x + boxW + 4, top + boxH / 2, x + boxW + gap - 4, top + boxH / 2, 6, rand)}
                stroke={INK} strokeWidth={2.5} fill="none"
                markerEnd="url(#mg-arrow)"
              />
            ) : null}
          </g>
        );
      })}
    </>
  );
};

const CompareMotif: React.FC<{w: number; h: number}> = ({w, h}) => {
  const gap = w * 0.07;
  const colW = (w - gap) / 2;
  const boxH = h * 0.5;
  const top = (h - boxH) / 2;
  return (
    <>
      <rect x={0} y={top} width={colW} height={boxH} rx={6} fill={PAPER} stroke={INK} strokeWidth={2.5} />
      <rect x={colW + gap} y={top} width={colW} height={boxH} rx={6} fill="#f2ece0" stroke={INK} strokeWidth={2.5} />
      <path
        d={`M ${colW + gap / 2} ${top - h * 0.04} L ${colW + gap / 2} ${top + boxH + h * 0.04}`}
        stroke={ACCENT} strokeWidth={2} strokeDasharray="6 6"
      />
    </>
  );
};

const StackMotif: React.FC<{w: number; h: number; rand: () => number}> = ({w, h, rand}) => {
  const rows = 4;
  const rowH = (h * 0.62) / rows;
  const top = (h - rowH * rows) / 2;
  const barW = (w * 0.78) / rows;
  return (
    <>
      {Array.from({length: rows}).map((_, i) => {
        const width = barW * (rows - i) * (0.85 + rand() * 0.15);
        return (
          <rect
            key={i}
            x={w / 2 - width / 2}
            y={top + i * rowH + rowH * 0.14}
            width={width}
            height={rowH * 0.72}
            rx={4}
            fill={i === rows - 1 ? '#f2ece0' : PAPER}
            stroke={INK}
            strokeWidth={2.5}
          />
        );
      })}
    </>
  );
};

const NumberMotif: React.FC<{w: number; h: number}> = ({w, h}) => (
  <text
    x={w / 2}
    y={h / 2}
    textAnchor="middle"
    dominantBaseline="central"
    fontFamily="OriginalDiaryHand, Songti SC, serif"
    fontSize={Math.min(w, h) * 0.52}
    fill={ACCENT}
  >
    壹
  </text>
);

export const Motif: React.FC<MotifProps> = ({motif, width, height, seed = 1, headline, detail}) => {
  const rand = seededRandom(seed);
  const w = width;
  const h = height;

  return (
    // 显式给出 width/height 且不加 inset:0——viewBox 与元素尺寸必须严格 1:1，
    // 否则 inset:0 会把元素拉伸到容器大小，边缘元素在运镜放大时被裁掉。
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <defs>
        <marker id="mg-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill={INK} />
        </marker>
      </defs>
      {motif === 'flow' ? <FlowMotif w={w} h={h} rand={rand} /> : null}
      {motif === 'compare' ? <CompareMotif w={w} h={h} /> : null}
      {motif === 'stack' ? <StackMotif w={w} h={h} rand={rand} /> : null}
      {motif === 'number' ? <NumberMotif w={w} h={h} /> : null}
      {motif === 'quote' ? (
        <text
          x={w / 2} y={h / 2} textAnchor="middle" dominantBaseline="central"
          fontFamily="OriginalDiaryHand, Songti SC, serif" fontSize={Math.min(w, h) * 0.16} fill={INK}
        >
          「{headline ?? ''}」
        </text>
      ) : null}
      {motif === 'title' ? (
        <text
          x={w / 2} y={h / 2} textAnchor="middle" dominantBaseline="central"
          fontFamily="OriginalDiaryHand, Songti SC, serif" fontSize={Math.min(w, h) * 0.2} fill={INK}
        >
          {headline ?? ''}
        </text>
      ) : null}
      {motif === 'empty' ? null : null}
      {detail ? (
        <text x={w / 2} y={h - 8} textAnchor="middle" fontFamily="Songti SC, serif" fontSize={20} fill="#6b6b6b">
          {detail}
        </text>
      ) : null}
    </svg>
  );
};

export const MOTIF_BACKGROUND = PAPER;
