import type {CSSProperties, PropsWithChildren} from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import motionProfiles from '../../common/motion-profiles.json';
import type {MotionId} from '../../types';

const smoothstep = (value: number) => value * value * (3 - 2 * value);

/** 与 handdrawn 侧同一条曲线：头尾各留一段沉降区，避免机械感的匀速运镜。 */
const settledProgress = (value: number) => {
  const head = 0.1;
  const tail = 0.14;
  const moving = Math.min(1, Math.max(0, (value - head) / (1 - head - tail)));
  return smoothstep(moving);
};

const focusOrigin = (focus: string): string => {
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

const transformOriginFor = (motion: MotionId, focus: string): string => {
  switch (motion) {
    case 'push_left':
      return '30% 50%';
    case 'push_right':
      return '70% 50%';
    case 'push_down':
      return '50% 30%';
    case 'push_up':
      return '50% 70%';
    default:
      return focusOrigin(focus);
  }
};

const motionStyle = (
  motion: MotionId,
  focus: string,
  progress: number,
): CSSProperties => {
  const eased = settledProgress(progress);
  const key = motion && motion in motionProfiles ? motion : 'hold';
  const profile = motionProfiles[key as keyof typeof motionProfiles];
  return {
    transform: `translate3d(${interpolate(eased, [0, 1], [profile.startXPercent, profile.endXPercent])}%, ${interpolate(eased, [0, 1], [profile.startYPercent, profile.endYPercent])}%, 0) scale(${interpolate(eased, [0, 1], [profile.startScale, profile.endScale])})`,
    transformOrigin: transformOriginFor(motion, focus),
    willChange: 'transform',
  };
};

// 运镜安全余量。运动词汇里 push_soft 收在 1.024、push_left/right 收在 1.036、
// pan 全程 1.04——这些缩放会把图元边缘推出画布，因此内容区必须先内缩，
// 否则边缘在运镜过程中被裁掉（s2hdv 的 audit-motion-storyboard 把这条叫 safety zoom）。
const MOTION_SAFETY_SCALE = 1.045;

/**
 * 运镜内缩量（占安全区尺寸的百分比）。图元必须按内缩后的实际尺寸绘制，
 * 否则 SVG 会被 inset:0 拉伸到容器大小、viewBox 与实际尺寸不再是 1:1，
 * 边缘元素会在运镜放大时被裁掉。
 */
export const motionInsetPercent = (): number =>
  (1 - 1 / MOTION_SAFETY_SCALE) * 50;

export const motionInsetPx = (width: number, height: number): {x: number; y: number} => {
  const percent = motionInsetPercent();
  return {x: (width * percent) / 100, y: (height * percent) / 100};
};

/**
 * 运镜舞台。handdrawn 与 motiongraphics 两条 composition 共用同一套运动词汇，
 * 因此同一份 storyboard.json 在两种形态下的节奏是一致的。
 */
export const CameraStage: React.FC<
  PropsWithChildren<{
    motion?: MotionId;
    focus?: string;
    durationSec: number;
    intervalStart?: number;
    intervalEnd?: number;
    safeArea?: {top: number; right: number; bottom: number; left: number};
  }>
> = ({motion = 'hold', focus = 'center', durationSec, intervalStart = 0, intervalEnd = 1, safeArea, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const totalFrames = Math.max(1, Math.round(durationSec * fps));
  const local = interpolate(
    frame,
    [0, Math.max(1, totalFrames - 1)],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  const progress = intervalStart + (intervalEnd - intervalStart) * local;

  const inset = `${((1 - 1 / MOTION_SAFETY_SCALE) * 50).toFixed(3)}%`;

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        ...(safeArea
          ? {
              top: safeArea.top,
              right: safeArea.right,
              bottom: safeArea.bottom,
              left: safeArea.left,
            }
          : {}),
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          // 内容先按运镜最大缩放内缩，运动过程中边缘不会被推出画布
          margin: safeArea ? inset : 0,
          ...motionStyle(motion, focus, progress),
        }}
      >
        {children}
      </div>
    </div>
  );
};
