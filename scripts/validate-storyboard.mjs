import {existsSync, readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const files = process.argv.slice(2);
const storyboardFiles = files.length > 0
  ? files
  : ['storyboard.json', 'storyboard.uploaded.json'];

const allowedMotions = new Set([
  'hold',
  'push_soft',
  'push',
  'push_left',
  'push_right',
  'pull_soft',
  'pull',
  'pan_left',
  'pan_right',
  'pan_up',
  'pan_down',
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

  if (!['3:4', '16:9'].includes(project.ratio)) {
    errors.push('project.ratio must be 3:4 or 16:9');
  }
  const expectedRatio = project.ratio === '16:9' ? 16 / 9 : 3 / 4;
  if (Math.abs(project.width / project.height - expectedRatio) > 0.001) {
    errors.push(`project width/height must be ${project.ratio}`);
  }
  if (!['diary', 'ink-comic', undefined].includes(project.visual_mode)) {
    errors.push('project.visual_mode must be diary or ink-comic');
  }
  if (!['draft_summary', 'verbatim_tts', undefined].includes(project.subtitle_contract)) {
    errors.push('project.subtitle_contract must be draft_summary or verbatim_tts');
  }
  if (project.subtitle_contract === 'verbatim_tts' && project.visual_mode !== 'ink-comic') {
    errors.push('verbatim_tts subtitle contract is reserved for ink-comic mode');
  }
  if (project.visual_mode === 'ink-comic' && project.ratio !== '16:9') {
    errors.push('ink-comic mode requires 16:9');
  }
  if (!Number.isFinite(project.fps) || project.fps <= 0) {
    errors.push('project.fps must be positive');
  }
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
    } else if ([...scene.text.replace(/\s/g, '')].length > (project.visual_mode === 'ink-comic' ? 72 : 45)) {
      errors.push(`${label}: text exceeds ${project.visual_mode === 'ink-comic' ? 72 : 45} characters`);
    }
    if (project.subtitle_contract === 'verbatim_tts') {
      const normalizedText = String(scene.text || '').replace(/\s/g, '');
      const normalizedNarration = String(scene.narration || '').replace(/\s/g, '');
      if (!normalizedNarration || normalizedText !== normalizedNarration) {
        errors.push(`${label}: verbatim_tts requires scene.text to match final scene.narration`);
      }
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
    if (project.visual_mode === 'ink-comic') {
      if (scene.visual_mode !== 'ink-comic') {
        errors.push(`${label}: scene.visual_mode must be ink-comic`);
      }
      if (illustrated) {
        errors.push(`${label}: ink-comic scenes use one full-screen color master, not bw_full reveal`);
      }
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
        errors.push(`${label}: missing ${key} asset at public/${path}`);
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
        if (
          project.visual_mode === 'ink-comic' &&
          key === 'color' &&
          Math.abs(dimensions.width / dimensions.height - 16 / 9) > 0.01
        ) {
          errors.push(`${label}: ink-comic color asset must be 16:9`);
        }
      }
    }
    if (illustrated && new Set(plateSizes).size > 1) {
      errors.push(`${label}: bw/detail/color plate dimensions must match exactly`);
    }
  }

  const seenIntervals = new Set();
  let previousInterval = null;
  for (const scene of storyboard.scenes) {
    const interval = String(scene.visual_interval_id || scene.id);
    if (interval !== previousInterval) {
      if (seenIntervals.has(interval)) {
        errors.push(`${scene.id}: visual interval ${JSON.stringify(interval)} is non-contiguous`);
      }
      seenIntervals.add(interval);
    }
    previousInterval = interval;
  }

  for (const interval of seenIntervals) {
    const scenes = storyboard.scenes.filter(
      (scene) => String(scene.visual_interval_id || scene.id) === interval,
    );
    const first = scenes[0];
    const asset = first.assets?.color;
    const motion = first.motion || 'hold';
    const focus = first.focus || 'center';
    if (first.visual_interval_start === false) {
      errors.push(`${first.id}: first scene of visual interval ${JSON.stringify(interval)} must start the interval`);
    }
    for (let index = 0; index < scenes.length; index += 1) {
      const scene = scenes[index];
      if (scene.assets?.color !== asset || (scene.motion || 'hold') !== motion || (scene.focus || 'center') !== focus) {
        errors.push(`${scene.id}: asset, motion, and focus must stay fixed inside visual interval ${JSON.stringify(interval)}`);
      }
      if (index > 0 && scene.visual_interval_start !== false) {
        errors.push(`${scene.id}: repeated machine scene must not restart visual interval ${JSON.stringify(interval)}`);
      }
      const start = scene.visual_interval_progress_start;
      const end = scene.visual_interval_progress_end;
      if (Number.isFinite(start) && Number.isFinite(end)) {
        const expectedStart = index === 0
          ? 0
          : scenes[index - 1].visual_interval_progress_end;
        if (Math.abs(start - expectedStart) > 1e-6 || end <= start) {
          errors.push(`${scene.id}: visual interval progress must be contiguous and increasing`);
        }
        if (index === scenes.length - 1 && Math.abs(end - 1) > 1e-6) {
          errors.push(`${scene.id}: visual interval ${JSON.stringify(interval)} must end at progress 1`);
        }
      }
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

console.log('✓ all storyboards valid · silent picture tracks');
