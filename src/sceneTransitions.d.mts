import type {SceneData, Storyboard} from './types';

export const DEFAULT_SCENE_FADE_SECONDS: number;
export const MIN_SCENE_FADE_SECONDS: number;
export const MAX_SCENE_FADE_SECONDS: number;
export const MAX_FADE_SHARE_OF_INCOMING_SCENE: number;

export type SceneTransitionKind = 'cut' | 'fade' | 'terminal';

export type SceneLayerOpacity =
  | {
      kind: 'constant';
      value: number;
    }
  | {
      kind: 'fade-out';
      from: number;
      to: number;
      startFrame: number;
      endFrame: number;
      easing: 'smoothstep';
    };

export type SceneLayerPlan = {
  scene: SceneData;
  index: number;
  from: number;
  nominalDurationInFrames: number;
  sequenceDurationInFrames: number;
  sequenceEnd: number;
  compositionDurationInFrames: number;
  zIndex: number;
  transitionToNext: SceneTransitionKind;
  fadeFrames: number;
  freezeFrame: number | null;
  opacity: SceneLayerOpacity;
};

export const sceneTransitionKindFor: (
  scene: SceneData,
  isLast?: boolean,
) => SceneTransitionKind;

export const transitionContractErrorsFor: (
  value: Storyboard,
) => string[];

export const sceneFadeFramesFor: (
  value: Storyboard,
  sceneIndex: number,
) => number;

export const sceneLayerPlanFor: (
  value: Storyboard,
) => SceneLayerPlan[];

export const sceneLayerOpacityForFrame: (
  layer: SceneLayerPlan,
  frame: number,
) => number;

export const sceneContentFrameForLayerFrame: (
  layer: SceneLayerPlan,
  frame: number,
) => number;
