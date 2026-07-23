import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, resolve} from 'node:path';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
import {
  MAX_FADE_SHARE_OF_INCOMING_SCENE,
  sceneContentFrameForLayerFrame,
  sceneLayerOpacityForFrame,
  sceneLayerPlanFor,
  transitionContractErrorsFor,
} from '../src/sceneTransitions.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const fixture = ({
  fps = 10,
  projectTransition = 'cut',
  transitionSeconds = 0.7,
  scenes,
} = {}) => ({
  project: {
    fps,
    transition: projectTransition,
    transition_sec: transitionSeconds,
  },
  scenes:
    scenes ??
    [
      {id: 'alpha', duration_sec: 1.2, transition_to_next: 'fade'},
      {id: 'beta', duration_sec: 1},
      {id: 'gamma', duration_sec: 0.8, transition_to_next: 'cut'},
    ],
});

const validatorFixture = ({transition = 'cut', firstSceneTransition} = {}) => ({
  project: {
    title: 'transition fixture',
    ratio: '3:4',
    width: 1080,
    height: 1440,
    fps: 30,
    transition,
    transition_sec: 0.7,
    style_lock: 'fixture',
    character_lock: 'fixture',
    cover: {background: '#5E7468'},
    audio: {
      voiceover: 'post',
      bgm: 'optional_bed_only',
      bgm_follows_text: false,
    },
  },
  scenes: [
    {
      id: 'fixture-1',
      duration_sec: 1,
      text: '',
      transition_to_next: firstSceneTransition,
      layers: ['color'],
      assets: {
        text_image: null,
        bw: null,
        detail: null,
        color: 'fixtures/missing-1.png',
      },
    },
    {
      id: 'fixture-2',
      duration_sec: 1,
      text: '',
      layers: ['color'],
      assets: {
        text_image: null,
        bw: null,
        detail: null,
        color: 'fixtures/missing-2.png',
      },
    },
  ],
});

const runValidator = (storyboard) => {
  const temporaryDirectory = mkdtempSync(
    resolve(tmpdir(), 'story-transition-validator-'),
  );
  const storyboardPath = resolve(temporaryDirectory, 'storyboard.json');
  writeFileSync(storyboardPath, `${JSON.stringify(storyboard)}\n`);
  const result = spawnSync(
    process.execPath,
    [
      'scripts/validate-storyboard.mjs',
      '--allow-missing-assets',
      storyboardPath,
    ],
    {
      cwd: root,
      encoding: 'utf8',
    },
  );
  rmSync(temporaryDirectory, {recursive: true, force: true});
  return result;
};

test('the complete layer plan preserves starts, total duration, stacking, and opacity metadata', () => {
  const value = fixture();
  const layers = sceneLayerPlanFor(value);

  assert.deepEqual(
    layers.map(
      ({
        from,
        nominalDurationInFrames,
        sequenceDurationInFrames,
        sequenceEnd,
        zIndex,
        transitionToNext,
        fadeFrames,
        freezeFrame,
        opacity,
      }) => ({
        from,
        nominalDurationInFrames,
        sequenceDurationInFrames,
        sequenceEnd,
        zIndex,
        transitionToNext,
        fadeFrames,
        freezeFrame,
        opacity,
      }),
    ),
    [
      {
        from: 0,
        nominalDurationInFrames: 12,
        sequenceDurationInFrames: 16,
        sequenceEnd: 16,
        zIndex: 3,
        transitionToNext: 'fade',
        fadeFrames: 4,
        freezeFrame: 11,
        opacity: {
          kind: 'fade-out',
          from: 1,
          to: 0,
          startFrame: 12,
          endFrame: 15,
          easing: 'smoothstep',
        },
      },
      {
        from: 12,
        nominalDurationInFrames: 10,
        sequenceDurationInFrames: 10,
        sequenceEnd: 22,
        zIndex: 2,
        transitionToNext: 'cut',
        fadeFrames: 0,
        freezeFrame: null,
        opacity: {kind: 'constant', value: 1},
      },
      {
        from: 22,
        nominalDurationInFrames: 8,
        sequenceDurationInFrames: 8,
        sequenceEnd: 30,
        zIndex: 1,
        transitionToNext: 'terminal',
        fadeFrames: 0,
        freezeFrame: null,
        opacity: {kind: 'constant', value: 1},
      },
    ],
  );

  assert.ok(
    layers.every(
      (layer) =>
        layer.sequenceEnd <= layer.compositionDurationInFrames &&
        layer.compositionDurationInFrames === 30,
    ),
  );
  assert.equal(
    layers.at(-1).from + layers.at(-1).nominalDurationInFrames,
    30,
  );
});

test('an omitted transition_to_next is formally a cut, including legacy uploaded fixtures', () => {
  const value = fixture({
    scenes: [
      {id: 'uploaded-1', duration_sec: 1},
      {id: 'uploaded-2', duration_sec: 1},
    ],
  });

  assert.deepEqual(transitionContractErrorsFor(value), []);
  assert.equal(sceneLayerPlanFor(value)[0].transitionToNext, 'cut');
});

test('a short incoming scene caps the fade at no more than 45 percent', () => {
  const value = fixture({
    fps: 30,
    scenes: [
      {id: 'outgoing', duration_sec: 1, transition_to_next: 'fade'},
      {id: 'short-incoming', duration_sec: 0.3},
    ],
  });
  const [outgoing, incoming] = sceneLayerPlanFor(value);

  assert.equal(incoming.nominalDurationInFrames, 9);
  assert.equal(outgoing.fadeFrames, 4);
  assert.ok(
    outgoing.fadeFrames <=
      incoming.nominalDurationInFrames *
        MAX_FADE_SHARE_OF_INCOMING_SCENE,
  );
});

test('an impossibly short incoming scene is rejected instead of violating the 45 percent cap', () => {
  const value = fixture({
    scenes: [
      {id: 'outgoing', duration_sec: 1, transition_to_next: 'fade'},
      {id: 'one-frame-incoming', duration_sec: 0.1},
    ],
  });

  assert.match(
    transitionContractErrorsFor(value).join('\n'),
    /too short for a fade capped at 45%/,
  );
  assert.throws(
    () => sceneLayerPlanFor(value),
    /too short for a fade capped at 45%/,
  );
});

test('fade opacity has exact opaque and transparent boundaries and is monotonic', () => {
  const [layer] = sceneLayerPlanFor(fixture());
  const samples = Array.from({length: layer.fadeFrames}, (_, offset) =>
    sceneLayerOpacityForFrame(
      layer,
      layer.nominalDurationInFrames + offset,
    ),
  );

  assert.equal(
    sceneLayerOpacityForFrame(
      layer,
      layer.nominalDurationInFrames - 1,
    ),
    1,
  );
  assert.equal(samples[0], 1);
  assert.equal(samples.at(-1), 0);
  assert.ok(samples.slice(1, -1).every((opacity) => opacity > 0 && opacity < 1));
  assert.ok(
    samples.every(
      (opacity, index) => index === 0 || opacity <= samples[index - 1],
    ),
  );
});

test('an outgoing fade freezes content on its nominal final frame', () => {
  const [layer] = sceneLayerPlanFor(fixture());

  assert.equal(
    sceneContentFrameForLayerFrame(
      layer,
      layer.nominalDurationInFrames - 1,
    ),
    layer.nominalDurationInFrames - 1,
  );
  assert.equal(
    sceneContentFrameForLayerFrame(
      layer,
      layer.nominalDurationInFrames,
    ),
    layer.nominalDurationInFrames - 1,
  );
  assert.equal(
    sceneContentFrameForLayerFrame(
      layer,
      layer.sequenceDurationInFrames - 1,
    ),
    layer.nominalDurationInFrames - 1,
  );
});

test('page-flip and per-scene fade are an explicit rejected conflict', () => {
  const value = fixture({projectTransition: 'page-flip'});

  assert.match(
    transitionContractErrorsFor(value).join('\n'),
    /conflicts with per-scene "fade"/,
  );
  assert.throws(
    () => sceneLayerPlanFor(value),
    /conflicts with per-scene "fade"/,
  );
});

test('the storyboard validator accepts omitted cuts and rejects page-flip plus per-scene fade', () => {
  const legacyUploaded = runValidator(validatorFixture());
  assert.equal(legacyUploaded.status, 0, legacyUploaded.stderr);

  const conflicting = runValidator(
    validatorFixture({
      transition: 'page-flip',
      firstSceneTransition: 'fade',
    }),
  );
  assert.equal(conflicting.status, 1);
  assert.match(conflicting.stderr, /conflicts with per-scene "fade"/);
});

test('fade duration outside the 0.5–0.9 second contract is rejected', () => {
  for (const transitionSeconds of [0.49, 0.91]) {
    assert.match(
      transitionContractErrorsFor(
        fixture({transitionSeconds}),
      ).join('\n'),
      /between 0.5 and 0.9 seconds/,
    );
  }
});

test('planning is deterministic and does not mutate the fixture', () => {
  const value = fixture();
  const before = structuredClone(value);

  assert.deepEqual(sceneLayerPlanFor(value), sceneLayerPlanFor(value));
  assert.deepEqual(value, before);
});
