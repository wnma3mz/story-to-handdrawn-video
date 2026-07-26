import rawStoryboard from '@storyboard-data';
import motionProfiles from './motion-profiles.json';
import type {Storyboard} from './types';

export const parseStoryboard = (
  value: unknown,
  label = 'Selected storyboard',
): Storyboard => {
  if (!value || typeof value !== 'object') {
    throw new Error(`${label} must be an object`);
  }
  const candidate = value as Partial<Storyboard>;
  if (
    !candidate.project ||
    !Number.isFinite(candidate.project.width) ||
    !Number.isFinite(candidate.project.height) ||
    !Number.isFinite(candidate.project.fps) ||
    !Array.isArray(candidate.scenes) ||
    candidate.scenes.length === 0
  ) {
    throw new Error(`${label} is missing a valid project or scenes`);
  }
  for (const scene of candidate.scenes) {
    if (
      !scene ||
      typeof scene.id !== 'string' ||
      !Number.isFinite(scene.duration_sec) ||
      !Array.isArray(scene.layers) ||
      !scene.assets
    ) {
      throw new Error(`${label} contains an invalid scene`);
    }
    if (scene.motion && !(scene.motion in motionProfiles)) {
      throw new Error(`${label} scene ${scene.id} has unsupported motion ${scene.motion}`);
    }
  }
  return candidate as Storyboard;
};

export const storyboard = parseStoryboard(rawStoryboard);

export const transitionFramesFor = (value: Storyboard) => {
  if (value.project.transition !== 'page-flip') return 0;
  const requested = Math.max(
    1,
    Math.round((value.project.transition_sec ?? 0.7) * value.project.fps),
  );
  const shortestScene = Math.min(
    ...value.scenes.map((scene) =>
      Math.round(scene.duration_sec * value.project.fps),
    ),
  );
  return Math.min(requested, Math.max(1, Math.floor(shortestScene * 0.45)));
};

export const totalFramesFor = (value: Storyboard) => {
  const sceneFrames = value.scenes.reduce(
    (sum, scene) =>
      sum + Math.round(scene.duration_sec * value.project.fps),
    0,
  );
  const overlap = transitionFramesFor(value) * Math.max(0, value.scenes.length - 1);
  return Math.max(1, sceneFrames - overlap);
};

export const totalFrames = totalFramesFor(storyboard);
