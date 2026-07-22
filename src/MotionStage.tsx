import type {CSSProperties, PropsWithChildren} from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import type {SceneData} from './types';

const smoothstep = (value: number) => value * value * (3 - 2 * value);

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
  const eased = smoothstep(progress);
  let scale = 1.002;
  let translateX = 0;
  let translateY = 0;
  let transformOrigin = focusOrigin(focus);

  switch (motion) {
    case 'push_soft':
      scale = 1 + 0.008 * eased;
      break;
    case 'push_left':
      scale = 1 + 0.016 * eased;
      transformOrigin = '30% 50%';
      break;
    case 'push_right':
      scale = 1 + 0.016 * eased;
      transformOrigin = '70% 50%';
      break;
    case 'pull_soft':
      scale = 1.01 - 0.01 * eased;
      break;
    case 'pan_left':
      scale = 1.022;
      translateX = -0.48 + 0.96 * eased;
      break;
    case 'pan_right':
      scale = 1.022;
      translateX = 0.48 - 0.96 * eased;
      break;
    case 'hold':
    default:
      scale = 1.002;
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
  const linear = interpolate(
    frame,
    [totalFrames * 0.12, totalFrames * 0.85],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );

  return (
    <div
      style={{
        position: 'absolute',
        zIndex: 10,
        left: 74,
        right: 74,
        top: 382,
        bottom: 42,
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
