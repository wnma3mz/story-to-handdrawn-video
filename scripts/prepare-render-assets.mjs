import {cpSync, existsSync, mkdirSync, readFileSync, rmSync} from 'node:fs';
import {dirname, isAbsolute, relative, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bundledPublicRoot = resolve(root, 'public');

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
const publicRoot = resolve(String(args['asset-root'] || bundledPublicRoot));
const workRoot = resolve(String(args['work-root'] || resolve(root, '.work')));
const episode = String(args.episode || process.env.EPISODE || 'default');
if (!/^[\p{Letter}\p{Number}._-]+$/u.test(episode)) {
  throw new Error('--episode may contain only letters, numbers, dots, underscores, and hyphens');
}

const storyboardPath = resolve(
  root,
  String(args.storyboard || process.env.STORYBOARD_PATH || 'storyboard.json'),
);
if (!existsSync(storyboardPath)) {
  throw new Error(`Missing storyboard: ${storyboardPath}`);
}

const stageKey = String(args['stage-key'] || 'main');
if (!/^[A-Za-z0-9._-]+$/.test(stageKey)) {
  throw new Error('--stage-key may contain only ASCII letters, numbers, dots, underscores, and hyphens');
}

const stageRoot = resolve(workRoot, 'render', `${episode}-${stageKey}`);
const stagedPublic = resolve(stageRoot, 'public');
const storyboard = JSON.parse(readFileSync(storyboardPath, 'utf8'));
const selected = new Set();

for (const scene of storyboard.scenes || []) {
  for (const value of Object.values(scene.assets || {})) {
    if (typeof value === 'string' && value.trim()) selected.add(value.trim());
  }
}

rmSync(stageRoot, {recursive: true, force: true});
mkdirSync(stagedPublic, {recursive: true});

const workspaceFonts = resolve(publicRoot, 'fonts');
const bundledFonts = resolve(bundledPublicRoot, 'fonts');
const fontsSource = existsSync(workspaceFonts) ? workspaceFonts : bundledFonts;
if (existsSync(fontsSource)) {
  cpSync(fontsSource, resolve(stagedPublic, 'fonts'), {recursive: true});
}

for (const item of selected) {
  let source = isAbsolute(item) ? item : resolve(publicRoot, item);
  let sourceRoot = publicRoot;
  if (!existsSync(source) && !isAbsolute(item)) {
    const bundledSource = resolve(bundledPublicRoot, item);
    if (existsSync(bundledSource)) {
      source = bundledSource;
      sourceRoot = bundledPublicRoot;
    }
  }
  const publicRelative = relative(sourceRoot, source);
  if (
    publicRelative === '..' ||
    publicRelative.startsWith(`..${sep}`) ||
    isAbsolute(publicRelative)
  ) {
    throw new Error(`Storyboard asset escapes public/: ${item}`);
  }
  if (!existsSync(source)) {
    throw new Error(`Missing storyboard asset: ${source}`);
  }
  const destination = resolve(stagedPublic, publicRelative);
  mkdirSync(dirname(destination), {recursive: true});
  cpSync(source, destination, {recursive: true});
}

process.stdout.write(`${stagedPublic}\n`);
