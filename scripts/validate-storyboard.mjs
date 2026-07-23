import {existsSync, readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {transitionContractErrorsFor} from '../src/sceneTransitions.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const allowMissingAssets = process.argv.includes('--allow-missing-assets');
const files = process.argv.slice(2).filter((value) => value !== '--allow-missing-assets');
const storyboardFiles = files.length > 0
  ? files
  : ['storyboard.json', 'storyboard.uploaded.json'];

const allowedMotions = new Set([
  'hold',
  'push_soft',
  'push_left',
  'push_right',
  'pull_soft',
  'pan_left',
  'pan_right',
]);

const pngDimensions = (path) => {
  if (!path.toLowerCase().endsWith('.png')) return null;
  const bytes = readFileSync(path);
  if (bytes.length < 24 || bytes.toString('ascii', 1, 4) !== 'PNG') return null;
  return {width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20)};
};

const validate = (file) => {
  const absoluteFile = resolve(root, file);
  const errors = [];
  if (!existsSync(absoluteFile)) return [`missing storyboard: ${file}`];

  let storyboard;
  try {
    storyboard = JSON.parse(readFileSync(absoluteFile, 'utf8'));
  } catch (error) {
    return [`invalid JSON: ${error.message}`];
  }

  const ids = new Set();
  const project = storyboard.project;
  if (!project || !Array.isArray(storyboard.scenes) || storyboard.scenes.length === 0) {
    return ['storyboard must contain project and at least one scene'];
  }

  if (project.ratio !== '3:4') errors.push('project.ratio must be 3:4');
  if (project.width / project.height !== 0.75) {
    errors.push('project width/height must be 3:4');
  }
  if (!Number.isFinite(project.fps) || project.fps <= 0) {
    errors.push('project.fps must be positive');
  }
  errors.push(...transitionContractErrorsFor(storyboard));
  if (!['post', 'continuous_groups'].includes(project.audio?.voiceover)) {
    errors.push('audio.voiceover must be post or continuous_groups');
  }
  if (project.audio?.bgm_follows_text !== false) {
    errors.push('audio.bgm_follows_text must be false');
  }
  const coverBackground = String(project.cover?.background || '').toLowerCase();
  if (['#fff', '#ffffff', 'white', 'rgb(255,255,255)'].includes(coverBackground.replaceAll(' ', ''))) {
    errors.push('project.cover.background must not be white');
  }
  if (project.mode === 'speed') {
    if (project.images_per_scene !== 1) {
      errors.push('speed mode requires images_per_scene=1');
    }
    if (project.derive_bw !== 'local') {
      errors.push('speed mode requires derive_bw=local');
    }
    if (project.enable_detail !== false) {
      errors.push('speed mode requires enable_detail=false');
    }
  }

  for (const scene of storyboard.scenes) {
    const label = scene?.id || '(unknown scene)';
    if (!scene || !Array.isArray(scene.layers) || !scene.assets) {
      errors.push(`${label}: layers and assets are required`);
      continue;
    }
    if (ids.has(scene.id)) errors.push(`duplicate scene id: ${scene.id}`);
    ids.add(scene.id);
    if (!Number.isFinite(scene.duration_sec) || scene.duration_sec <= 0) {
      errors.push(`${label}: duration must be positive`);
    }
    if (scene.motion && !allowedMotions.has(scene.motion)) {
      errors.push(`${label}: unsupported motion ${JSON.stringify(scene.motion)}`);
    }
    if (typeof scene.text !== 'string') {
      errors.push(`${label}: text must be a string`);
    } else if ([...scene.text].length > 45) {
      errors.push(`${label}: text exceeds 45 characters`);
    }

    const hasText = scene.layers.includes('text');
    const illustrated = scene.layers.includes('bw_full');
    const colorIndex = scene.layers.indexOf('color');
    if ((scene.text || scene.assets.text_image) && !hasText) {
      errors.push(`${label}: text content requires a text layer`);
    }
    if (illustrated && (!scene.assets.bw || !scene.assets.color)) {
      errors.push(`${label}: illustrated scenes require bw and color assets`);
    }
    if (illustrated && scene.layers.indexOf('bw_full') > colorIndex) {
      errors.push(`${label}: bw_full must appear before color`);
    }
    if (!scene.assets.color || colorIndex < 0) {
      errors.push(`${label}: a color layer and asset are required`);
    }
    if (project.mode === 'speed' && scene.assets.detail) {
      errors.push(`${label}: detail asset must be null in speed mode`);
    }

    const plateSizes = [];
    for (const [key, path] of Object.entries(scene.assets)) {
      if (path !== null && typeof path !== 'string') {
        errors.push(`${label}: ${key} asset must be a path or null`);
        continue;
      }
      if (!path) continue;
      const absolute = resolve(root, 'public', path);
      if (!existsSync(absolute)) {
        if (!allowMissingAssets) {
          errors.push(`${label}: missing ${key} asset at public/${path}`);
        }
        continue;
      }
      const dimensions = pngDimensions(absolute);
      if (
        key === 'text_image' &&
        dimensions &&
        Math.abs(dimensions.width / dimensions.height - 3) > 0.08
      ) {
        errors.push(`${label}: Image 2 text plate must use a 3:1 canvas`);
      }
      if (dimensions && ['bw', 'detail', 'color'].includes(key)) {
        plateSizes.push(`${dimensions.width}x${dimensions.height}`);
      }
    }
    if (illustrated && new Set(plateSizes).size > 1) {
      errors.push(`${label}: bw/detail/color plate dimensions must match exactly`);
    }
  }

  if (errors.length === 0) {
    const duration = storyboard.scenes.reduce(
      (sum, scene) => sum + scene.duration_sec,
      0,
    );
    console.log(
      `✓ ${file} · ${storyboard.scenes.length} scenes · ${duration.toFixed(1)}s`,
    );
  }
  return errors;
};

const errors = storyboardFiles.flatMap((file) =>
  validate(file).map((error) => `${file}: ${error}`),
);

if (errors.length > 0) {
  console.error(errors.map((error) => `✗ ${error}`).join('\n'));
  process.exit(1);
}

console.log(
  allowMissingAssets
    ? '✓ all storyboards structurally valid · planned assets may be pending'
    : '✓ all storyboards valid · silent picture tracks',
);
