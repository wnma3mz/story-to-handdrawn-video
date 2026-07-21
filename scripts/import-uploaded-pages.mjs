import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from 'node:fs';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const parseArgs = (tokens) => {
  const parsed = {images: [], splitYs: []};
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '--image') {
      const value = tokens[index + 1];
      if (!value) throw new Error('--image requires a path');
      parsed.images.push(value);
      index += 1;
      continue;
    }
    if (token === '--split-y') {
      const value = tokens[index + 1];
      if (!value) throw new Error('--split-y requires SCENE:PIXELS');
      parsed.splitYs.push(value);
      index += 1;
      continue;
    }
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const next = tokens[index + 1];
    if (next && !next.startsWith('--')) {
      parsed[key] = next;
      index += 1;
    } else {
      parsed[key] = true;
    }
  }
  return parsed;
};

const args = parseArgs(process.argv.slice(2));
if (args.images.length === 0) {
  throw new Error(
    'Usage: npm run import:uploaded -- --image /path/01.jpg --image /path/02.jpg [--transition page-flip]',
  );
}

const title = String(args.title || '上传图片手绘动画');
// Page turning is opt-in. Uploaded stories use direct cuts unless the user
// explicitly requests a paper-page transition.
const transition = String(args.transition || 'cut');
const transitionSec = Number(args['transition-sec'] || 0.7);
const pageDuration = Number(args['page-duration'] || 4.4);
const layout = String(args.layout || 'auto');
const paperFlip = transition === 'page-flip';
const splitOverrides = new Map(
  args.splitYs.map((value) => {
    const match = /^(\d+):(\d+)$/.exec(String(value));
    if (!match) throw new Error(`Invalid --split-y value: ${value}`);
    return [match[1].padStart(2, '0'), Number(match[2])];
  }),
);

if (!['cut', 'page-flip'].includes(transition)) {
  throw new Error('--transition must be cut or page-flip');
}
if (!['auto', 'composite', 'full'].includes(layout)) {
  throw new Error('--layout must be auto, composite, or full');
}
if (!Number.isFinite(transitionSec) || transitionSec <= 0 || transitionSec > 2) {
  throw new Error('--transition-sec must be greater than 0 and at most 2');
}
if (!Number.isFinite(pageDuration) || pageDuration < 2 || pageDuration > 15) {
  throw new Error('--page-duration must be between 2 and 15 seconds');
}

const resolvedInputs = args.images.map((value) => resolve(root, String(value)));
for (const input of resolvedInputs) {
  if (!existsSync(input)) throw new Error(`Uploaded image does not exist: ${input}`);
}

const seenHashes = new Set();
const inputs = [];
for (const input of resolvedInputs) {
  const hash = createHash('sha256').update(readFileSync(input)).digest('hex');
  if (seenHashes.has(hash)) {
    console.log(`Skipped exact duplicate: ${input}`);
    continue;
  }
  seenHashes.add(hash);
  inputs.push({path: input, hash});
}

if (inputs.length === 0) throw new Error('No unique uploaded images remain');

const safeTitle =
  title
    .normalize('NFKC')
    .replace(/[^\p{Letter}\p{Number}]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 32) || 'uploaded';
const batchHash = createHash('sha256')
  .update(
    [
      'uploaded-pages-v6',
      layout,
      transition,
      paperFlip ? String(transitionSec) : 'no-transition-overlap',
      String(pageDuration),
      ...inputs.map((item) => item.hash),
    ].join('\n'),
  )
  .digest('hex')
  .slice(0, 8);
const assetSet = `${safeTitle}-${batchHash}`;
const generatedRoot = `generated/uploads/${assetSet}`;
const outputDir = resolve(root, 'public/assets', generatedRoot);
mkdirSync(outputDir, {recursive: true});

const dimensionsFor = (path) => {
  const output = execFileSync(
    'ffprobe',
    [
      '-v',
      'error',
      '-select_streams',
      'v:0',
      '-show_entries',
      'stream=width,height',
      '-of',
      'json',
      path,
    ],
    {cwd: root, encoding: 'utf8'},
  );
  const stream = JSON.parse(output).streams?.[0];
  if (!stream?.width || !stream?.height) {
    throw new Error(`Could not read image dimensions: ${path}`);
  }
  return {width: Number(stream.width), height: Number(stream.height)};
};

const analyzeCompositeLayout = (path, width, height) => {
  const previewWidth = 256;
  const pixels = execFileSync(
    'ffmpeg',
    [
      '-hide_banner',
      '-loglevel',
      'error',
      '-i',
      path,
      '-vf',
      `scale=${previewWidth}:-2:flags=area,format=gray`,
      '-frames:v',
      '1',
      '-f',
      'rawvideo',
      '-pix_fmt',
      'gray',
      '-',
    ],
    {cwd: root, maxBuffer: 8 * 1024 * 1024},
  );
  const previewHeight = Math.floor(pixels.length / previewWidth);
  const rowInk = Array.from({length: previewHeight}, (_, y) => {
    let ink = 0;
    const offset = y * previewWidth;
    for (let x = 0; x < previewWidth; x += 1) {
      if (pixels[offset + x] < 238) ink += 1;
    }
    return ink / previewWidth;
  });
  const smoothed = rowInk.map((_, y) => {
    let total = 0;
    let count = 0;
    for (let offset = -2; offset <= 2; offset += 1) {
      const row = y + offset;
      if (row >= 0 && row < previewHeight) {
        total += rowInk[row];
        count += 1;
      }
    }
    return total / count;
  });

  const searchStart = Math.round(previewHeight * 0.22);
  const searchEnd = Math.round(previewHeight * 0.52);
  const runs = [];
  let runStart = null;
  for (let y = searchStart; y <= searchEnd; y += 1) {
    if (smoothed[y] < 0.012 && runStart === null) runStart = y;
    const closes = smoothed[y] >= 0.012 || y === searchEnd;
    if (closes && runStart !== null) {
      const end = smoothed[y] >= 0.012 ? y - 1 : y;
      runs.push({start: runStart, end, length: end - runStart + 1});
      runStart = null;
    }
  }
  runs.sort((a, b) => b.length - a.length || a.start - b.start);
  const bestRun = runs[0] || null;
  let splitPreview = bestRun
    ? Math.round((bestRun.start + bestRun.end) / 2)
    : searchStart;
  if (!bestRun) {
    for (let y = searchStart; y <= searchEnd; y += 1) {
      if (smoothed[y] < smoothed[splitPreview]) splitPreview = y;
    }
  }

  // Some uploaded diary-comic pages leave a wide white gutter immediately
  // after a short one-line caption. Clamping the split to 27% pushed the crop
  // down into roofs, hair, or a third caption line on those pages. The search
  // already starts at 22%, so allow the detected gutter itself to determine
  // the boundary while retaining the existing upper safety limit.
  const minSplit = searchStart;
  const maxSplit = Math.round(previewHeight * 0.5);
  splitPreview = Math.max(minSplit, Math.min(maxSplit, splitPreview));

  const contentRows = [];
  for (let y = 0; y < splitPreview; y += 1) {
    if (rowInk[y] > 0.012) contentRows.push(y);
  }
  const scaleY = height / previewHeight;
  const detectedCaption =
    contentRows.length > Math.max(4, previewHeight * 0.02) &&
    Boolean(bestRun && bestRun.length >= previewHeight * 0.012);
  const topContent = contentRows[0] ?? 0;
  const bottomContent = contentRows.at(-1) ?? splitPreview;
  const padding = Math.max(8, Math.round(previewHeight * 0.018));
  const captionY = Math.max(0, Math.round((topContent - padding) * scaleY));
  const captionBottom = Math.min(
    height,
    Math.round((bottomContent + padding) * scaleY),
  );

  return {
    hasCaption: detectedCaption,
    splitY: Math.round(splitPreview * scaleY),
    captionY,
    captionH: Math.max(24, captionBottom - captionY),
  };
};

const runFfmpeg = (input, filter, output) => {
  execFileSync(
    'ffmpeg',
    [
      '-hide_banner',
      '-loglevel',
      'error',
      '-i',
      input,
      '-vf',
      filter,
      '-frames:v',
      '1',
      '-y',
      output,
    ],
    {cwd: root, stdio: 'inherit'},
  );
};

const scenes = [];
const manifestPages = [];

for (let index = 0; index < inputs.length; index += 1) {
  const input = inputs[index];
  const id = String(index + 1).padStart(2, '0');
  const {width, height} = dimensionsFor(input.path);
  const detection = analyzeCompositeLayout(input.path, width, height);
  const hasCaption =
    layout === 'composite' || (layout === 'auto' && detection.hasCaption);
  const splitOverride = splitOverrides.get(id);
  if (
    splitOverride !== undefined &&
    (splitOverride < Math.round(height * 0.16) ||
      splitOverride > Math.round(height * 0.62))
  ) {
    throw new Error(`--split-y for scene ${id} is outside the safe range`);
  }
  const splitY = hasCaption ? splitOverride ?? detection.splitY : 0;
  const captionY = splitOverride === undefined ? detection.captionY : 0;
  const captionH =
    splitOverride === undefined ? detection.captionH : splitOverride;
  const extension = extname(input.path).toLowerCase() || '.jpg';
  const masterName = `${id}_master${extension}`;
  const textName = `${id}_text.png`;
  const colorName = `${id}_color.png`;
  const bwName = `${id}_bw.png`;
  const masterPath = resolve(outputDir, masterName);
  const textPath = resolve(outputDir, textName);
  const colorPath = resolve(outputDir, colorName);
  const bwPath = resolve(outputDir, bwName);

  copyFileSync(input.path, masterPath);

  if (!paperFlip && hasCaption) {
    runFfmpeg(
      input.path,
      `crop=${width}:${captionH}:0:${captionY},scale=1536:512:force_original_aspect_ratio=decrease:flags=lanczos,pad=1536:512:(ow-iw)/2:(oh-ih)/2:color=white`,
      textPath,
    );
  }

  if (!paperFlip) {
    const artFilter = hasCaption
      ? `crop=${width}:${height - splitY}:0:${splitY},scale=1024:1024:force_original_aspect_ratio=decrease:flags=lanczos,pad=1024:1024:(ow-iw)/2:(oh-ih)/2:color=white`
      : 'scale=1024:1024:force_original_aspect_ratio=decrease:flags=lanczos,pad=1024:1024:(ow-iw)/2:(oh-ih)/2:color=white';
    runFfmpeg(input.path, artFilter, colorPath);
    runFfmpeg(
      colorPath,
      'format=gray,eq=contrast=1.18:brightness=0.035,unsharp=5:5:0.55:5:5:0',
      bwPath,
    );
  }

  const asset = (name) => `assets/${generatedRoot}/${name}`;
  scenes.push({
    id,
    duration_sec: pageDuration,
    text: '',
    visual: `上传图片 ${id}`,
    shot: paperFlip ? 'full_uploaded_page' : 'safe_uncropped_uploaded_page',
    // Page curls use the untouched vertical master. This preserves every
    // handwritten line and avoids auto-crop errors on long captions.
    layers: paperFlip
      ? ['color']
      : hasCaption
        ? ['text', 'bw_full', 'color']
        : ['bw_full', 'color'],
    color_hint: null,
    detail_hint: null,
    caption_box: null,
    assets: {
      text_image: !paperFlip && hasCaption ? asset(textName) : null,
      bw: paperFlip ? null : asset(bwName),
      detail: null,
      color: asset(paperFlip ? masterName : colorName),
    },
  });
  manifestPages.push({
    id,
    source: input.path,
    master: masterPath,
    width,
    height,
    has_caption: hasCaption,
    detected_split_y: splitY,
    caption_crop: hasCaption
      ? {y: captionY, height: captionH}
      : null,
  });
}

const storyboard = {
  project: {
    title,
    mode: 'speed',
    images_per_scene: 1,
    derive_bw: 'local',
    enable_detail: false,
    gen_size: 1024,
    export_size: [1080, 1440],
    ratio: '3:4',
    width: 1080,
    height: 1440,
    fps: 30,
    transition,
    transition_sec: paperFlip ? transitionSec : undefined,
    style_lock: 'preserve uploaded hand-drawn diary-comic artwork',
    character_lock: 'preserve uploaded characters and composition exactly',
    audio: {
      voiceover: 'post',
      bgm: 'optional_bed_only',
      bgm_follows_text: false,
    },
  },
  scenes,
};

const storyboardPath = resolve(root, 'storyboard.uploaded.json');
const manifestPath = resolve(root, 'uploaded-pages.json');
writeFileSync(storyboardPath, `${JSON.stringify(storyboard, null, 2)}\n`);
writeFileSync(
  manifestPath,
  `${JSON.stringify(
    {
      version: 1,
      asset_set: assetSet,
      storyboard: storyboardPath,
      transition,
      pages: manifestPages,
    },
    null,
    2,
  )}\n`,
);

const transitionOverlap =
  transition === 'page-flip' ? transitionSec * Math.max(0, scenes.length - 1) : 0;
const duration = scenes.length * pageDuration - transitionOverlap;
console.log(
  `Prepared ${scenes.length} uploaded scenes (${duration.toFixed(1)}s, ${transition}) → ${storyboardPath}`,
);
console.log(`Assets → ${outputDir}`);
