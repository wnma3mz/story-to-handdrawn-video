import rawStoryboard from '../storyboard.json';
import type {Storyboard} from './types';

export const storyboard = rawStoryboard as Storyboard;

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
