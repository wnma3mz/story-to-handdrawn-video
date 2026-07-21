import {execFileSync, spawnSync} from 'node:child_process';
import {copyFileSync, existsSync, readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const parseArgs = (tokens) => {
  const parsed = {};
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
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
const manifestPath = resolve(root, String(args.manifest || 'codex-image-jobs.json'));
if (!existsSync(manifestPath)) throw new Error(`Missing Codex manifest: ${manifestPath}`);

const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
if (manifest.generator !== 'codex-image2' || !Array.isArray(manifest.jobs)) {
  throw new Error('Unsupported Codex Image2 manifest');
}

const missing = manifest.jobs
  .map((job) => job.output_master)
  .filter((master) => !existsSync(master));
if (missing.length > 0) {
  throw new Error(
    `Codex Image2 masters are incomplete (${missing.length} missing):\n${missing.join('\n')}`,
  );
}

const captionCropHeight = 342;
const captionScanHeight = 400;

const detectCaptionCropY = (masterPath) => {
  const detection = spawnSync(
    'ffmpeg',
    [
      '-hide_banner',
      '-loglevel',
      'verbose',
      '-loop',
      '1',
      '-i',
      masterPath,
      '-vf',
      `crop=1024:${captionScanHeight}:0:0,negate,format=gray,lut=y='if(gt(val,80),255,0)',cropdetect=limit=0.1:round=2:reset=0`,
      '-frames:v',
      '3',
      '-f',
      'null',
      '-',
    ],
    {cwd: root, encoding: 'utf8'},
  );
  const log = `${detection.stdout || ''}\n${detection.stderr || ''}`;
  const matches = [...log.matchAll(/crop=(\d+):(\d+):(\d+):(\d+)/g)];
  const last = matches.at(-1);
  if (detection.status !== 0 || !last) {
    console.warn(`Could not detect caption bounds for ${masterPath}; using top-aligned crop`);
    return 0;
  }

  const contentHeight = Number(last[2]);
  const contentY = Number(last[4]);
  const centeredY = Math.round(contentY + contentHeight / 2 - captionCropHeight / 2);
  return Math.max(0, Math.min(captionScanHeight - captionCropHeight, centeredY));
};

for (const job of manifest.jobs.filter((item) => item.role !== 'reference')) {
  const masterPath = resolve(job.output_master);
  const assetDir = dirname(masterPath);
  const textPath = resolve(assetDir, `${job.id}_text.png`);
  const bwPath = resolve(assetDir, `${job.id}_bw.png`);
  const colorPath = resolve(assetDir, `${job.id}_color.png`);

  if (manifest.text_mode === 'image2') {
    const captionCropY = detectCaptionCropY(masterPath);
    execFileSync(
      'ffmpeg',
      [
        '-hide_banner',
        '-loglevel',
        'error',
        '-i',
        masterPath,
        '-vf',
        `crop=1024:${captionCropHeight}:0:${captionCropY},scale=1536:512:flags=lanczos`,
        '-frames:v',
        '1',
        '-y',
        textPath,
      ],
      {cwd: root, stdio: 'inherit'},
    );
  }

  execFileSync(
    'ffmpeg',
    [
      '-hide_banner',
      '-loglevel',
      'error',
      '-i',
      masterPath,
      '-vf',
      manifest.text_mode === 'image2'
        ? 'crop=1024:1024:0:512,format=gray,eq=contrast=1.18:brightness=0.035,unsharp=5:5:0.55:5:5:0'
        : 'format=gray,eq=contrast=1.18:brightness=0.035,unsharp=5:5:0.55:5:5:0',
      '-frames:v',
      '1',
      '-y',
      bwPath,
    ],
    {cwd: root, stdio: 'inherit'},
  );

  execFileSync(
    'ffmpeg',
    [
      '-hide_banner',
      '-loglevel',
      'error',
      '-i',
      masterPath,
      '-vf',
      manifest.text_mode === 'image2' ? 'crop=1024:1024:0:512' : 'null',
      '-frames:v',
      '1',
      '-y',
      colorPath,
    ],
    {cwd: root, stdio: 'inherit'},
  );

  console.log(`Imported scene ${job.id} → ${assetDir}`);
}

if (args.apply === true) {
  copyFileSync(resolve(manifest.storyboard), resolve(root, 'storyboard.json'));
  console.log(`Activated storyboard → ${resolve(root, 'storyboard.json')}`);
}

if (args.render === true) {
  if (args.apply !== true) throw new Error('--render requires --apply');
  execFileSync('npm', ['run', 'render'], {cwd: root, stdio: 'inherit'});
}
