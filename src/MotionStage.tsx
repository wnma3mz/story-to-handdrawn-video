import type {CSSProperties, PropsWithChildren} from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import motionProfiles from './motion-profiles.json';
import type {SceneData} from './types';

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
  const {fps} = useVideoConfig();
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
        left: scene.visual_mode === 'ink-comic' ? 0 : scene.visual_mode === 'essay' ? 106 : 74,
        right: scene.visual_mode === 'ink-comic' ? 0 : scene.visual_mode === 'essay' ? 106 : 74,
        top: scene.visual_mode === 'ink-comic' ? 0 : scene.visual_mode === 'essay' ? 680 : 382,
        bottom: scene.visual_mode === 'ink-comic' ? 0 : scene.visual_mode === 'essay' ? 62 : 42,
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
