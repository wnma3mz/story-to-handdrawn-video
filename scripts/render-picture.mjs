import {execFileSync} from 'node:child_process';
import {existsSync, mkdirSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const valueFor = (flag) => {
  const index = args.indexOf(flag);
  return index >= 0 ? args[index + 1] : undefined;
};
const episode = valueFor('--episode') || process.env.EPISODE || 'default';
const isPreview = args.includes('--preview');
const isCover = args.includes('--cover');
const isUploaded = args.includes('--uploaded');
const storyboardPath = resolve(
  root,
  valueFor('--storyboard') ||
    process.env.STORYBOARD_PATH ||
    (isUploaded ? 'storyboard.uploaded.json' : 'storyboard.json'),
);
if (!existsSync(storyboardPath)) {
  throw new Error(`Missing storyboard: ${storyboardPath}`);
}
const outDir = `out/${episode}`;

mkdirSync('out/releases', {recursive: true});
mkdirSync(outDir, {recursive: true});

const stagedPublic = execFileSync(
  process.execPath,
  [
    resolve(root, 'scripts/prepare-render-assets.mjs'),
    '--episode',
    episode,
    '--stage-key',
    isUploaded ? 'uploaded' : isCover ? 'cover' : isPreview ? 'preview' : 'main',
    '--storyboard',
    storyboardPath,
  ],
  {cwd: root, encoding: 'utf8'},
).trim();
const renderEnvironment = {
  ...process.env,
  REMOTION_PUBLIC_DIR: stagedPublic,
  ...(isUploaded
    ? {UPLOADED_STORYBOARD_PATH: storyboardPath}
    : {STORYBOARD_PATH: storyboardPath}),
};

if (isCover) {
  execFileSync(
    'npx',
    ['remotion', 'still', 'src/index.ts', 'EpisodeCover', `${outDir}/cover.png`],
    {cwd: root, env: renderEnvironment, stdio: 'inherit'},
  );
} else if (isUploaded) {
  const name = isPreview ? 'uploaded-preview' : 'uploaded';
  const scaleArg = isPreview ? ['--scale=0.6666666666666666'] : [];
  const crf = isPreview ? '23' : '18';
  execFileSync(
    'npx',
    [
      'remotion', 'render', 'src/index.ts', 'UploadedPictureSilent',
      `${outDir}/${name}.mp4`,
      '--codec=h264', `--crf=${crf}`, '--pixel-format=yuv420p', '--muted',
      '--concurrency=1', ...scaleArg,
    ],
    {cwd: root, env: renderEnvironment, stdio: 'inherit'},
  );
} else {
  const name = isPreview ? 'silent-preview' : 'silent';
  const scaleArg = isPreview ? ['--scale=0.6666666666666666'] : [];
  const crf = isPreview ? '23' : '18';
  execFileSync(
    'npx',
    [
      'remotion', 'render', 'src/index.ts', 'PictureSilent',
      `${outDir}/${name}.mp4`,
      '--codec=h264', `--crf=${crf}`, '--pixel-format=yuv420p', '--muted',
      '--concurrency=1', ...scaleArg,
    ],
    {cwd: root, env: renderEnvironment, stdio: 'inherit'},
  );
}
