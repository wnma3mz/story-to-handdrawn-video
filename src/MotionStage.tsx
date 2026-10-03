import type {CSSProperties, PropsWithChildren} from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import framing from './common/framing.json';
import motionProfiles from './common/motion-profiles.json';
import type {SceneData} from './types';

type FramingBox = {left: number; right: number; top: number; bottom: number};
type RatioKey = '9:16' | '3:4' | '16:9';

const RATIOS: {key: RatioKey; value: number}[] = [
  {key: '9:16', value: 9 / 16},
  {key: '3:4', value: 3 / 4},
  {key: '16:9', value: 16 / 9},
];

/** 由画布尺寸反查画幅键。取景框按画幅查表，不匹配时退回 3:4。 */
const ratioKey = (width: number, height: number): RatioKey => {
  const ratio = width / height;
  for (const entry of RATIOS) {
    if (Math.abs(ratio - entry.value) < 0.01) {
      return entry.key;
    }
  }
  return '3:4';
};

/**
 * 取景框按画幅查表。历史实现在此写死成一串三元表达式，换画幅只能改代码；
 * 抽成配置后新增 9:16 不必再动组件，且 3:4 / 16:9 的取值与原实现完全一致。
 */
const framingBox = (
  mode: SceneData['visual_mode'],
  width: number,
  height: number,
): FramingBox => {
  const modeKey =
    mode === 'ink-comic' ? 'ink-comic' : mode === 'essay' ? 'essay' : 'diary';
  const key = ratioKey(width, height);
  const bucket = key === '16:9' ? framing.landscape['16:9'] : framing.portrait[key];
  return bucket[modeKey] as FramingBox;
};

const smoothstep = (value: number) => value * value * (3 - 2 * value);

// One eased path belongs to the full visual interval, even when that interval
// is split into several subtitle-timed machine scenes.  A settled head/tail
// keeps the camera from looking like a mechanical screensaver.
const settledProgress = (value: number) => {
  const head = 0.1;
  const tail = 0.14;
  const moving = Math.min(1, Math.max(0, (value - head) / (1 - head - tail)));
  return smoothstep(moving);
};

const focusOrigin = (focus: SceneData['focus']): string => {
  switch (focus) {
    case 'left':
      return '30% 50%';
    case 'right':
      return '70% 50%';
    case 'top':
      return '50% 30%';
    case 'bottom':
      return '50% 70%';
    default:
      return '50% 50%';
  }
};

const motionStyle = (
  motion: SceneData['motion'],
  focus: SceneData['focus'],
  progress: number,
): CSSProperties => {
  const eased = settledProgress(progress);
  const key = motion && motion in motionProfiles ? motion : 'hold';
  const profile = motionProfiles[key as keyof typeof motionProfiles];
  const scale = interpolate(eased, [0, 1], [profile.startScale, profile.endScale]);
  const translateX = interpolate(
    eased,
    [0, 1],
    [profile.startXPercent, profile.endXPercent],
  );
  const translateY = interpolate(
    eased,
    [0, 1],
    [profile.startYPercent, profile.endYPercent],
  );
  let transformOrigin = focusOrigin(focus);

  switch (motion) {
    case 'push_left':
      transformOrigin = '30% 50%';
      break;
    case 'push_right':
      transformOrigin = '70% 50%';
      break;
    case 'push_down':
      transformOrigin = '50% 30%';
      break;
    case 'push_up':
      transformOrigin = '50% 70%';
      break;
    default:
      break;
  }

  return {
    transform: `translate3d(${translateX}%, ${translateY}%, 0) scale(${scale})`,
    transformOrigin,
    willChange: 'transform',
  };
};

export const MotionStage: React.FC<
  PropsWithChildren<{scene: SceneData}>
> = ({scene, children}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const box = framingBox(scene.visual_mode, width, height);
  const totalFrames = Math.max(1, Math.round(scene.duration_sec * fps));
  const localLinear = interpolate(
    frame,
    [0, Math.max(1, totalFrames - 1)],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  const intervalStart = scene.visual_interval_progress_start ?? 0;
  const intervalEnd = scene.visual_interval_progress_end ?? 1;
  const linear = intervalStart + (intervalEnd - intervalStart) * localLinear;

  return (
    <div
      style={{
        position: 'absolute',
        zIndex: 10,
        left: box.left,
        right: box.right,
        top: box.top,
        bottom: box.bottom,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          ...motionStyle(scene.motion, scene.focus, linear),
        }}
      >
        {children}
      </div>
    </div>
  );
};
