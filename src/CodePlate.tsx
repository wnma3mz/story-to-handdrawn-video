import type {SceneData} from './types';
import {isCodePlateMotif, type CodePlateMotif} from './plateMode';

type Props = {
  scene: SceneData;
  /** When true, desaturate for ink-comic full-bleed. */
  monochrome?: boolean;
};

const mulberry32 = (seed: number) => {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
};

const defaultBackground = (monochrome: boolean, visualMode?: string) => {
  if (monochrome) return '#1A1A1A';
  if (visualMode === 'essay') return '#FCFAF5';
  return '#FFFFFF';
};

const MotifPaths: React.FC<{
  motif: CodePlateMotif;
  ink: string;
  a1: string;
  a2: string;
}> = ({motif, ink, a1, a2}) => {
  switch (motif) {
    case 'window':
      return (
        <g stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round">
          <rect x="360" y="280" width="300" height="440" />
          <line x1="510" y1="280" x2="510" y2="720" />
          <line x1="360" y1="500" x2="660" y2="500" />
          <circle cx="580" cy="420" r="48" fill={a1} fillOpacity={0.35} stroke="none" />
        </g>
      );
    case 'desk_night':
      return (
        <g stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round">
          <rect x="250" y="480" width="170" height="220" />
          <circle cx="320" cy="360" r="36" fill={a1} fillOpacity={0.55} stroke="none" />
          <rect x="560" y="500" width="220" height="220" fill={a2} fillOpacity={0.25} />
        </g>
      );
    case 'bike':
      return (
        <g stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round">
          <circle cx="360" cy="580" r="60" />
          <circle cx="580" cy="580" r="60" />
          <path d="M360 580 L480 470 L580 580" />
          <line x1="480" y1="470" x2="480" y2="420" />
          <circle cx="700" cy="300" r="70" fill={a2} fillOpacity={0.3} stroke="none" />
        </g>
      );
    case 'street':
      return (
        <g stroke={ink} strokeWidth={4} fill="none" strokeLinecap="round">
          <path d="M200 700 L400 420 L500 420 L360 700 Z" fill={a1} fillOpacity={0.28} />
          <path d="M520 700 L560 380 L680 380 L760 700 Z" fill={a2} fillOpacity={0.22} />
          <line x1="120" y1="720" x2="900" y2="720" />
        </g>
      );
    case 'two_figures':
      return (
        <g stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round">
          <circle cx="400" cy="380" r="40" />
          <path d="M400 420 L340 700 L460 700 Z" />
          <circle cx="600" cy="380" r="40" />
          <path d="M600 420 L540 700 L660 700 Z" />
          <line x1="440" y1="520" x2="560" y2="520" />
        </g>
      );
    case 'temple_gate':
      return (
        <g stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round">
          <path d="M300 420 L512 280 L724 420 Z" fill={a1} fillOpacity={0.3} />
          <rect x="360" y="420" width="304" height="280" />
          <rect x="470" y="520" width="84" height="180" />
        </g>
      );
    case 'empty_cup':
      return (
        <g stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round">
          <ellipse cx="510" cy="650" rx="60" ry="28" />
          <path d="M470 420 L470 640" />
          <path d="M550 420 L550 640" />
          <ellipse cx="510" cy="420" rx="50" ry="20" />
          <rect x="490" y="360" width="40" height="50" />
        </g>
      );
    case 'ghost_window':
      return (
        <g stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round">
          <rect x="300" y="500" width="420" height="220" />
          <circle cx="380" cy="300" r="42" fill={a2} fillOpacity={0.35} stroke="none" />
          <circle cx="520" cy="260" r="50" fill={a2} fillOpacity={0.28} stroke="none" />
          <circle cx="640" cy="320" r="38" fill={a1} fillOpacity={0.3} stroke="none" />
          <circle cx="372" cy="292" r="5" fill={ink} stroke="none" />
          <circle cx="392" cy="292" r="5" fill={ink} stroke="none" />
        </g>
      );
    case 'detour':
      return (
        <g stroke={ink} strokeWidth={6} fill="none" strokeLinecap="round">
          <path d="M280 560 Q512 320 740 560" />
          <path d="M320 520 L280 480" />
          <path d="M320 520 L280 560" />
          <path d="M700 300 L760 360" stroke={a1} />
          <path d="M760 300 L700 360" stroke={a1} />
        </g>
      );
    case 'farewell':
      return (
        <g stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round">
          <line x1="200" y1="700" x2="820" y2="700" />
          <path d="M300 700 L420 380 L500 380 L420 700 Z" fill={a2} fillOpacity={0.22} />
          <circle cx="700" cy="320" r="80" fill={a1} fillOpacity={0.32} stroke="none" />
          <circle cx="490" cy="530" r="28" />
          <line x1="490" y1="558" x2="490" y2="680" />
        </g>
      );
    case 'book_lamp':
      return (
        <g stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round">
          <rect x="300" y="560" width="420" height="50" fill={a1} fillOpacity={0.25} />
          <path d="M360 560 L400 420 L480 420 L460 560 Z" />
          <path d="M520 560 L540 400 L620 400 L640 560 Z" />
          <line x1="700" y1="560" x2="700" y2="380" />
          <circle cx="700" cy="340" r="28" fill={a2} fillOpacity={0.5} stroke="none" />
        </g>
      );
    case 'abstract_wash':
    default:
      return (
        <g fill="none">
          <circle cx="380" cy="420" r="120" fill={a1} fillOpacity={0.28} />
          <circle cx="620" cy="520" r="150" fill={a2} fillOpacity={0.22} />
          <circle cx="540" cy="300" r="90" fill={a1} fillOpacity={0.18} />
        </g>
      );
  }
};

/**
 * Procedural illustration plate drawn entirely in code (SVG).
 * Used when Image2 is unavailable or a scene opts into plate_mode=code.
 */
export const CodePlate: React.FC<Props> = ({scene, monochrome = false}) => {
  const spec = scene.code_plate;
  const rawMotif = spec?.motif || 'abstract_wash';
  const motif: CodePlateMotif = isCodePlateMotif(rawMotif) ? rawMotif : 'abstract_wash';
  const background =
    spec?.background || defaultBackground(monochrome, scene.visual_mode);
  const ink = spec?.ink || (monochrome ? '#E8E2D6' : '#2C2926');
  const accents = spec?.accents && spec.accents.length >= 2
    ? spec.accents
    : monochrome
      ? ['#8A8580', '#5C5854']
      : ['#B4786E', '#7A8B7A'];
  const a1 = accents[0];
  const a2 = accents[1] || accents[0];
  const seed = spec?.seed ?? Number.parseInt(scene.id, 10) || 1;
  const rand = mulberry32(seed * 9973);
  const washes = Array.from({length: 5}, (_, index) => ({
    cx: 180 + rand() * 660,
    cy: 200 + rand() * 620,
    r: 60 + rand() * 140,
    color: index % 2 === 0 ? a1 : a2,
    opacity: 0.08 + rand() * 0.12,
  }));

  return (
    <svg
      viewBox="0 0 1024 1024"
      width="100%"
      height="100%"
      style={{
        display: 'block',
        width: '100%',
        height: '100%',
        objectFit: 'contain',
        filter: monochrome
          ? 'grayscale(0.75) contrast(1.12)'
          : scene.visual_mode === 'essay'
            ? 'contrast(0.95) saturate(0.82)'
            : undefined,
      }}
      aria-hidden="true"
    >
      <rect x="0" y="0" width="1024" height="1024" fill={background} />
      {washes.map((wash, index) => (
        <circle
          key={index}
          cx={wash.cx}
          cy={wash.cy}
          r={wash.r}
          fill={wash.color}
          fillOpacity={wash.opacity}
        />
      ))}
      <MotifPaths motif={motif} ink={ink} a1={a1} a2={a2} />
    </svg>
  );
};
