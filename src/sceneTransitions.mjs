export const DEFAULT_SCENE_FADE_SECONDS = 0.7;
export const MIN_SCENE_FADE_SECONDS = 0.5;
export const MAX_SCENE_FADE_SECONDS = 0.9;
export const MAX_FADE_SHARE_OF_INCOMING_SCENE = 0.45;

const allowedProjectTransitions = new Set(['cut', 'page-flip']);
const allowedSceneTransitions = new Set(['cut', 'fade']);

const clamp = (value, minimum, maximum) =>
  Math.min(maximum, Math.max(minimum, value));

const smoothstep = (value) => value * value * (3 - 2 * value);

const framesForScene = (scene, fps) =>
  Math.max(1, Math.round(scene.duration_sec * fps));

export const sceneTransitionKindFor = (scene, isLast = false) => {
  if (isLast) return 'terminal';
  return scene.transition_to_next === 'fade' ? 'fade' : 'cut';
};

export const transitionContractErrorsFor = (value) => {
  const errors = [];
  const project = value?.project ?? {};
  const scenes = Array.isArray(value?.scenes) ? value.scenes : [];
  const projectTransition = project.transition ?? 'cut';

  if (!allowedProjectTransitions.has(projectTransition)) {
    errors.push(
      `unsupported project transition ${JSON.stringify(projectTransition)}`,
    );
  }

  scenes.forEach((scene, index) => {
    const transition = scene?.transition_to_next;
    if (
      transition !== undefined &&
      transition !== null &&
      !allowedSceneTransitions.has(transition)
    ) {
      errors.push(
        `${scene?.id || `scene ${index + 1}`}: transition_to_next must be "cut", "fade", or omitted`,
      );
    }
  });

  const fadeSceneIndexes = scenes
    .map((scene, index) =>
      scene?.transition_to_next === 'fade' ? index : -1,
    )
    .filter((index) => index >= 0);
  const actionableFadeIndexes = fadeSceneIndexes.filter(
    (index) => index < scenes.length - 1,
  );

  if (projectTransition === 'page-flip' && fadeSceneIndexes.length > 0) {
    errors.push(
      'project.transition "page-flip" conflicts with per-scene "fade"; choose exactly one transition system',
    );
  }

  if (actionableFadeIndexes.length > 0) {
    const fadeSeconds =
      project.transition_sec ?? DEFAULT_SCENE_FADE_SECONDS;
    if (
      !Number.isFinite(fadeSeconds) ||
      fadeSeconds < MIN_SCENE_FADE_SECONDS ||
      fadeSeconds > MAX_SCENE_FADE_SECONDS
    ) {
      errors.push(
        `project.transition_sec must be between ${MIN_SCENE_FADE_SECONDS} and ${MAX_SCENE_FADE_SECONDS} seconds when per-scene fades are present`,
      );
    }

    if (Number.isFinite(project.fps) && project.fps > 0) {
      for (const sceneIndex of actionableFadeIndexes) {
        const nextScene = scenes[sceneIndex + 1];
        if (
          Number.isFinite(nextScene?.duration_sec) &&
          nextScene.duration_sec > 0
        ) {
          const nextSceneFrames = framesForScene(nextScene, project.fps);
          const maximumFadeFrames = Math.floor(
            nextSceneFrames * MAX_FADE_SHARE_OF_INCOMING_SCENE,
          );
          if (maximumFadeFrames < 1) {
            errors.push(
              `${scenes[sceneIndex]?.id || `scene ${sceneIndex + 1}`}: incoming scene is too short for a fade capped at 45%`,
            );
          }
        }
      }
    }
  }

  return errors;
};

export const sceneFadeFramesFor = (value, sceneIndex) => {
  const scene = value.scenes[sceneIndex];
  const nextScene = value.scenes[sceneIndex + 1];
  if (
    !scene ||
    !nextScene ||
    sceneTransitionKindFor(scene, false) !== 'fade'
  ) {
    return 0;
  }

  const requestedSeconds =
    value.project.transition_sec ?? DEFAULT_SCENE_FADE_SECONDS;
  const requestedFrames = Math.max(
    1,
    Math.round(requestedSeconds * value.project.fps),
  );
  const nextSceneFrames = framesForScene(nextScene, value.project.fps);
  const maximumFadeFrames = Math.floor(
    nextSceneFrames * MAX_FADE_SHARE_OF_INCOMING_SCENE,
  );

  if (maximumFadeFrames < 1) {
    throw new Error(
      `${scene.id}: incoming scene is too short for a fade capped at 45%`,
    );
  }

  return Math.min(requestedFrames, maximumFadeFrames);
};

export const sceneLayerPlanFor = (value) => {
  const contractErrors = transitionContractErrorsFor(value);
  if (contractErrors.length > 0) {
    throw new Error(contractErrors.join('\n'));
  }
  if (!Number.isFinite(value.project.fps) || value.project.fps <= 0) {
    throw new Error('project.fps must be positive');
  }
  if ((value.project.transition ?? 'cut') === 'page-flip') {
    throw new Error(
      'sceneLayerPlanFor handles cut/per-scene-fade timelines, not page-flip timelines',
    );
  }

  const nominalDurations = value.scenes.map((scene) => {
    if (!Number.isFinite(scene.duration_sec) || scene.duration_sec <= 0) {
      throw new Error(`${scene.id}: duration must be positive`);
    }
    return framesForScene(scene, value.project.fps);
  });
  const compositionDurationInFrames = nominalDurations.reduce(
    (sum, duration) => sum + duration,
    0,
  );
  let from = 0;

  return value.scenes.map((scene, index) => {
    const nominalDurationInFrames = nominalDurations[index];
    const isLast = index === value.scenes.length - 1;
    const transitionToNext = sceneTransitionKindFor(scene, isLast);
    const fadeFrames =
      transitionToNext === 'fade' ? sceneFadeFramesFor(value, index) : 0;
    const sequenceDurationInFrames =
      nominalDurationInFrames + fadeFrames;
    const sequenceEnd = from + sequenceDurationInFrames;
    if (sequenceEnd > compositionDurationInFrames) {
      throw new Error(
        `${scene.id}: sequence ends at ${sequenceEnd}, beyond composition frame ${compositionDurationInFrames}`,
      );
    }

    const opacity =
      transitionToNext === 'fade'
        ? {
            kind: 'fade-out',
            from: 1,
            to: 0,
            startFrame: nominalDurationInFrames,
            endFrame: nominalDurationInFrames + fadeFrames - 1,
            easing: 'smoothstep',
          }
        : {
            kind: 'constant',
            value: 1,
          };
    const layer = {
      scene,
      index,
      from,
      nominalDurationInFrames,
      sequenceDurationInFrames,
      sequenceEnd,
      compositionDurationInFrames,
      zIndex: value.scenes.length - index,
      transitionToNext,
      fadeFrames,
      freezeFrame:
        transitionToNext === 'fade'
          ? nominalDurationInFrames - 1
          : null,
      opacity,
    };

    // A fade tail overlays the incoming scene. It never moves that scene's
    // start or changes the composition duration.
    from += nominalDurationInFrames;
    return layer;
  });
};

export const sceneLayerOpacityForFrame = (layer, frame) => {
  if (layer.opacity.kind === 'constant') return layer.opacity.value;
  if (frame < layer.opacity.startFrame) return layer.opacity.from;
  if (layer.fadeFrames === 1) return layer.opacity.to;

  const linear = clamp(
    (frame - layer.opacity.startFrame) /
      (layer.opacity.endFrame - layer.opacity.startFrame),
    0,
    1,
  );
  return 1 - smoothstep(linear);
};

export const sceneContentFrameForLayerFrame = (layer, frame) =>
  layer.freezeFrame === null
    ? frame
    : Math.min(frame, layer.freezeFrame);
