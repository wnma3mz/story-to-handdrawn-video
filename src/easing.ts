import {interpolate} from 'remotion';

const smoothstep = (value: number) => value * value * (3 - 2 * value);

export const revealProgress = (
  frame: number,
  startFrame: number,
  durationFrames: number,
) => {
  const linear = interpolate(
    frame,
    [startFrame, startFrame + Math.max(1, durationFrames)],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );

  return smoothstep(linear);
};
