import {execFileSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const valueFor = (flag) => {
  const index = args.indexOf(flag);
  return index >= 0 ? args[index + 1] : undefined;
};
const episode = valueFor('--episode') || process.env.EPISODE || 'default';
const storyboardPath = resolve(
  root,
  valueFor('--storyboard') || process.env.STORYBOARD_PATH || 'storyboard.json',
);
if (!existsSync(storyboardPath)) {
  throw new Error(`Missing storyboard: ${storyboardPath}`);
}

const stagedPublic = execFileSync(
  process.execPath,
  [
    resolve(root, 'scripts/prepare-render-assets.mjs'),
    '--episode',
    episode,
    '--stage-key',
    'bundle',
    '--storyboard',
    storyboardPath,
  ],
  {cwd: root, encoding: 'utf8'},
).trim();

execFileSync(
  'npx',
  ['remotion', 'bundle', 'src/index.ts', 'build'],
  {
    cwd: root,
    env: {
      ...process.env,
      STORYBOARD_PATH: storyboardPath,
      REMOTION_PUBLIC_DIR: stagedPublic,
    },
    stdio: 'inherit',
  },
);
