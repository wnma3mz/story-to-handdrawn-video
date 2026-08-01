import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {
  mkdtempSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import {tmpdir} from 'node:os';
import {basename, resolve} from 'node:path';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
import {deepMerge, loadStyleProfile, validateStyleProfile} from './lib/style-profile.mjs';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const styles = JSON.parse(readFileSync(resolve(root, 'config/styles.json'), 'utf8'));

const profileFor = (id, overrides = {}) => ({
  schema_version: 1,
  id,
  display_name: `Profile ${id}`,
  description: 'A reusable test profile',
  base_mode: 'essay',
  recommended_for: ['historical essays'],
  style_overrides: {
    styleLock: `style lock ${id}`,
    scenePrompt: {createLine: `create line ${id}`},
    ...overrides,
  },
  episode_defaults: {
    accent: '#123ABC',
    cover: {
      background: '#112233',
      accent: '#445566',
      dark_accent: '#223344',
    },
  },
  editorial: {avoid: ['generic imagery']},
});

test('deepMerge merges nested objects and replaces arrays without mutating inputs', () => {
  const base = {nested: {left: 1, right: 2}, palette: ['old']};
  const overrides = {nested: {right: 3}, palette: ['new']};
  const merged = deepMerge(base, overrides);
  assert.deepEqual(merged, {nested: {left: 1, right: 3}, palette: ['new']});
  assert.deepEqual(base, {nested: {left: 1, right: 2}, palette: ['old']});
});

test('validator rejects missing fields, unknown top-level keys, bad modes, colors and objects', () => {
  assert.throws(
    () => validateStyleProfile({...profileFor('valid'), description: undefined}, styles),
    /description must be a non-empty string/,
  );
  assert.throws(
    () => validateStyleProfile({...profileFor('valid'), surprise: true}, styles),
    /unknown key "surprise"/,
  );
  assert.throws(
    () => validateStyleProfile({...profileFor('valid'), base_mode: 'poster'}, styles),
    /base_mode must be one of/,
  );
  assert.throws(
    () => validateStyleProfile({...profileFor('valid'), base_mode: '_description'}, styles),
    /base_mode must be one of/,
  );
  assert.throws(
    () =>
      validateStyleProfile({
        ...profileFor('valid'),
        episode_defaults: {...profileFor('valid').episode_defaults, accent: 'red'},
      }, styles),
    /accent must be #RRGGBB/,
  );
  assert.throws(
    () => validateStyleProfile({...profileFor('valid'), editorial: []}, styles),
    /editorial must be a JSON object/,
  );
  assert.throws(
    () =>
      validateStyleProfile({
        ...profileFor('valid'),
        episode_defaults: {
          ...profileFor('valid').episode_defaults,
          color_grade: 'neon',
        },
      }, styles),
    /color_grade must be monochrome, warm_bronze, or snow_cinnabar/,
  );
});

test('loader accepts a project-relative path and a profile id', () => {
  const fixtureId = `profile-test-${process.pid}`;
  const profileDir = resolve(root, 'config/style-profiles');
  const profilePath = resolve(profileDir, `${fixtureId}.json`);
  mkdirSync(profileDir, {recursive: true});
  writeFileSync(profilePath, `${JSON.stringify(profileFor(fixtureId))}\n`);
  try {
    const byId = loadStyleProfile(fixtureId, {root, styles});
    const byPath = loadStyleProfile(`config/style-profiles/${fixtureId}.json`, {root, styles});
    assert.equal(byId.profile.id, fixtureId);
    assert.equal(byId.trace.path, `config/style-profiles/${fixtureId}.json`);
    assert.deepEqual(byPath.trace, byId.trace);
  } finally {
    rmSync(profilePath);
  }
});

test('every catalog profile loads by id and matches its filename', () => {
  const profileDir = resolve(root, 'config/style-profiles');
  const ids = readdirSync(profileDir)
    .filter((name) => name.endsWith('.json'))
    .map((name) => basename(name, '.json'))
    .sort();
  assert.ok(ids.length > 0, 'expected at least one catalog style profile');
  for (const id of ids) {
    const loaded = loadStyleProfile(id, {root, styles});
    assert.equal(loaded.profile.id, id);
    assert.equal(loaded.trace.path, `config/style-profiles/${id}.json`);
  }
});

test('CLI applies profile defaults, explicit cover values and trace metadata', () => {
  const temp = mkdtempSync(resolve(tmpdir(), 'story-style-profile-'));
  const profilePath = resolve(temp, 'profile.json');
  const outputPath = resolve(temp, 'storyboard.json');
  const manifestPath = resolve(temp, 'manifest.json');
  const assetSet = `style-profile-cli-${process.pid}`;
  const promptDir = resolve(temp, 'prompts/generated/codex', assetSet);
  const assetDir = resolve(temp, 'public/assets/generated/codex', assetSet);
  writeFileSync(profilePath, `${JSON.stringify(profileFor('integration'))}\n`);
  try {
    const result = spawnSync(
      process.execPath,
      [
        'scripts/story-to-video.mjs',
        '--workspace',
        temp,
        '--text',
        '只有一句话。',
        '--style-profile',
        profilePath,
        '--cover-background',
        '#ABCDEF',
        '--output',
        outputPath,
        '--manifest',
        manifestPath,
        '--asset-set',
        assetSet,
      ],
      {cwd: root, encoding: 'utf8'},
    );
    assert.equal(result.status, 0, result.stderr);
    const storyboard = JSON.parse(readFileSync(outputPath, 'utf8'));
    assert.equal(storyboard.project.visual_mode, 'essay');
    assert.equal(storyboard.project.style_lock, 'style lock integration');
    assert.equal(storyboard.project.accent, '#123ABC');
    assert.equal(storyboard.project.color_grade, undefined);
    assert.equal(storyboard.project.cover.background, '#ABCDEF');
    assert.equal(storyboard.project.cover.accent, '#445566');
    assert.equal(storyboard.scenes[0].accent, '#123ABC');
    assert.equal(storyboard.scenes[0].color_grade, undefined);
    assert.deepEqual(storyboard.project.style_profile, {
      id: 'integration',
      path: profilePath,
      schema_version: 1,
    });
    const prompt = readFileSync(resolve(promptDir, '01_master.txt'), 'utf8');
    assert.match(prompt, /create line integration/);
  } finally {
    rmSync(temp, {recursive: true, force: true});
    rmSync(promptDir, {recursive: true, force: true});
    rmSync(assetDir, {recursive: true, force: true});
  }
});

test('profile identity changes automatic asset set and conflicting visual mode fails', () => {
  const temp = mkdtempSync(resolve(tmpdir(), 'story-style-identity-'));
  const createdAssetSets = [];
  try {
    for (const id of ['identity-a', 'identity-b']) {
      const profilePath = resolve(temp, `${id}.json`);
      const outputPath = resolve(temp, `${id}-storyboard.json`);
      const manifestPath = resolve(temp, `${id}-manifest.json`);
      writeFileSync(profilePath, `${JSON.stringify(profileFor(id))}\n`);
      const result = spawnSync(
        process.execPath,
        [
          'scripts/story-to-video.mjs',
          '--workspace',
          temp,
          '--text',
          '相同的文章。',
          '--style-profile',
          profilePath,
          '--output',
          outputPath,
          '--manifest',
          manifestPath,
        ],
        {cwd: root, encoding: 'utf8'},
      );
      assert.equal(result.status, 0, result.stderr);
      createdAssetSets.push(JSON.parse(readFileSync(manifestPath, 'utf8')).asset_set);
    }
    assert.notEqual(createdAssetSets[0], createdAssetSets[1]);

    const mismatch = spawnSync(
      process.execPath,
      [
        'scripts/story-to-video.mjs',
        '--workspace',
        temp,
        '--text',
        '冲突。',
        '--style-profile',
        resolve(temp, 'identity-a.json'),
        '--visual-mode',
        'diary',
        '--output',
        resolve(temp, 'mismatch.json'),
      ],
      {cwd: root, encoding: 'utf8'},
    );
    assert.notEqual(mismatch.status, 0);
    assert.match(mismatch.stderr, /conflicts with style profile/);
  } finally {
    rmSync(temp, {recursive: true, force: true});
  }
});

test('ink-comic profile propagates its reusable color grade', () => {
  const temp = mkdtempSync(resolve(tmpdir(), 'story-style-grade-'));
  const profile = profileFor('graded-ink');
  profile.base_mode = 'ink-comic';
  profile.episode_defaults.color_grade = 'warm_bronze';
  const profilePath = resolve(temp, 'profile.json');
  const outputPath = resolve(temp, 'storyboard.json');
  const assetSet = `style-profile-grade-${process.pid}`;
  writeFileSync(profilePath, `${JSON.stringify(profile)}\n`);
  try {
    const result = spawnSync(
      process.execPath,
      [
        'scripts/story-to-video.mjs',
        '--workspace',
        temp,
        '--text',
        '有色黑白。',
        '--style-profile',
        profilePath,
        '--output',
        outputPath,
        '--asset-set',
        assetSet,
      ],
      {cwd: root, encoding: 'utf8'},
    );
    assert.equal(result.status, 0, result.stderr);
    const storyboard = JSON.parse(readFileSync(outputPath, 'utf8'));
    assert.equal(storyboard.project.color_grade, 'warm_bronze');
    assert.equal(storyboard.scenes[0].color_grade, 'warm_bronze');
  } finally {
    rmSync(temp, {recursive: true, force: true});
  }
});

test('custom diary profile can opt out of bundled scene style references', () => {
  const temp = mkdtempSync(resolve(tmpdir(), 'story-style-refs-'));
  const assetSet = `style-profile-refs-${process.pid}`;
  const profile = profileFor('no-bundled-refs');
  profile.base_mode = 'diary';
  profile.style_overrides = {
    scenePrompt: {needsStyleRefs: false},
    characterRef: {needsStyleRefs: false},
  };
  const profilePath = resolve(temp, 'profile.json');
  const manifestPath = resolve(temp, 'manifest.json');
  writeFileSync(profilePath, `${JSON.stringify(profile)}\n`);
  try {
    const result = spawnSync(
      process.execPath,
      [
        'scripts/story-to-video.mjs',
        '--workspace',
        temp,
        '--text',
        '建立一种新画风。',
        '--style-profile',
        profilePath,
        '--output',
        resolve(temp, 'storyboard.json'),
        '--manifest',
        manifestPath,
        '--asset-set',
        assetSet,
      ],
      {cwd: root, encoding: 'utf8'},
    );
    assert.equal(result.status, 0, result.stderr);
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
    const referenceJob = manifest.jobs.find((job) => job.role === 'reference');
    const sceneJob = manifest.jobs.find((job) => job.role === 'scene');
    assert.deepEqual(referenceJob.references, []);
    assert.equal(
      sceneJob.references.some((path) => /references\/style-(?:bw|color)\.png$/.test(path)),
      false,
    );
  } finally {
    rmSync(temp, {recursive: true, force: true});
  }
});

test('CLI without a profile keeps the legacy diary default', () => {
  const temp = mkdtempSync(resolve(tmpdir(), 'story-style-legacy-'));
  const assetSet = `style-profile-legacy-${process.pid}`;
  try {
    const outputPath = resolve(temp, 'storyboard.json');
    const result = spawnSync(
      process.execPath,
      [
        'scripts/story-to-video.mjs',
        '--workspace',
        temp,
        '--text',
        '旧工作流。',
        '--output',
        outputPath,
        '--manifest',
        resolve(temp, 'manifest.json'),
        '--asset-set',
        assetSet,
      ],
      {cwd: root, encoding: 'utf8'},
    );
    assert.equal(result.status, 0, result.stderr);
    const storyboard = JSON.parse(readFileSync(outputPath, 'utf8'));
    assert.equal(storyboard.project.visual_mode, 'diary');
    assert.equal(Object.hasOwn(storyboard.project, 'style_profile'), false);
  } finally {
    rmSync(temp, {recursive: true, force: true});
  }
});
