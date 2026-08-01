import {execFileSync} from 'node:child_process';
import {existsSync, mkdirSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {resolveWorkspace, resolveWorkspacePath} from './lib/workspace.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const valueFor = (flag) => {
  const index = args.indexOf(flag);
  const value = index >= 0 ? args[index + 1] : undefined;
  return value && !value.startsWith('--') ? value : undefined;
};
for (const flag of ['--workspace', '--output-root', '--work-root', '--asset-root']) {
  if (args.includes(flag) && !valueFor(flag)) {
    throw new Error(`${flag} requires a directory path`);
  }
}
const parsedArgs = Object.fromEntries(
  ['workspace', 'output-root', 'work-root', 'asset-root'].flatMap((key) => {
    const value = valueFor(`--${key}`);
    return value ? [[key, value]] : [];
  }),
);
const workspace = resolveWorkspace(parsedArgs, root);
const episode = valueFor('--episode') || process.env.EPISODE || 'default';
if (!/^[\p{Letter}\p{Number}._-]+$/u.test(episode) || episode === '.' || episode === '..') {
  throw new Error('--episode may contain only letters, numbers, dots, underscores, and hyphens');
}
const isPreview = args.includes('--preview');
const isCover = args.includes('--cover');
const isUploaded = args.includes('--uploaded');
const storyboardPath = resolve(
  workspace,
  valueFor('--storyboard') ||
    process.env.STORYBOARD_PATH ||
    (isUploaded ? 'storyboard.uploaded.json' : 'storyboard.json'),
);
if (!existsSync(storyboardPath)) {
  throw new Error(`Missing storyboard: ${storyboardPath}`);
}
const outputRoot = resolveWorkspacePath(workspace, parsedArgs['output-root'], 'out');
const workRoot = resolveWorkspacePath(workspace, parsedArgs['work-root'], '.work');
const assetRoot = resolveWorkspacePath(workspace, parsedArgs['asset-root'], 'public');
const outDir = resolve(outputRoot, episode);

mkdirSync(resolve(outputRoot, 'releases'), {recursive: true});
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
    '--asset-root',
    assetRoot,
    '--work-root',
    workRoot,
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
    ['remotion', 'still', 'src/index.ts', 'EpisodeCover', resolve(outDir, 'cover.png')],
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
      resolve(outDir, `${name}.mp4`),
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
      resolve(outDir, `${name}.mp4`),
      '--codec=h264', `--crf=${crf}`, '--pixel-format=yuv420p', '--muted',
      '--concurrency=1', ...scaleArg,
    ],
    {cwd: root, env: renderEnvironment, stdio: 'inherit'},
  );
}
