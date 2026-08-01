import {
  existsSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
} from 'node:fs';
import {dirname, relative, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {resolveWorkspace, resolveWorkspacePath} from './lib/workspace.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const workspaceIndex = process.argv.indexOf('--workspace');
if (
  workspaceIndex >= 0 &&
  (!process.argv[workspaceIndex + 1] || process.argv[workspaceIndex + 1].startsWith('--'))
) {
  throw new Error('--workspace requires a directory path');
}
const workspace = resolveWorkspace(
  workspaceIndex >= 0 ? {workspace: process.argv[workspaceIndex + 1]} : {},
  root,
);
const generatedRoot = resolveWorkspacePath(workspace, null, 'public/assets/generated');
const apply = process.argv.includes('--apply');
const daysIndex = process.argv.indexOf('--keep-days');
const keepDays = Number(daysIndex >= 0 ? process.argv[daysIndex + 1] : 30);
if (!Number.isFinite(keepDays) || keepDays < 0) {
  throw new Error('--keep-days must be a non-negative number');
}

const storyboardFiles = [
  resolve(workspace, 'storyboard.json'),
  resolve(workspace, 'storyboard.uploaded.json'),
];
const episodesRoot = resolve(workspace, 'episodes');
if (existsSync(episodesRoot)) {
  const collect = (directory) => {
    for (const entry of readdirSync(directory, {withFileTypes: true})) {
      const path = resolve(directory, entry.name);
      if (entry.isDirectory()) collect(path);
      else if (/storyboard.*\.json$/i.test(entry.name)) storyboardFiles.push(path);
    }
  };
  collect(episodesRoot);
}

const referencedSets = new Set();
for (const file of storyboardFiles) {
  if (!existsSync(file)) continue;
  const storyboard = JSON.parse(readFileSync(file, 'utf8'));
  for (const scene of storyboard.scenes || []) {
    for (const value of Object.values(scene.assets || {})) {
      if (typeof value !== 'string') continue;
      const match = /^assets\/generated\/([^/]+\/[^/]+)\//.exec(value);
      if (match) referencedSets.add(match[1]);
    }
  }
}

const candidates = [];
if (existsSync(generatedRoot)) {
  for (const family of readdirSync(generatedRoot, {withFileTypes: true})) {
    if (!family.isDirectory()) continue;
    const familyPath = resolve(generatedRoot, family.name);
    for (const assetSet of readdirSync(familyPath, {withFileTypes: true})) {
      if (!assetSet.isDirectory()) continue;
      const key = `${family.name}/${assetSet.name}`;
      const path = resolve(familyPath, assetSet.name);
      const ageDays = (Date.now() - statSync(path).mtimeMs) / 86_400_000;
      if (!referencedSets.has(key) && ageDays >= keepDays) {
        candidates.push({key, path, ageDays});
      }
    }
  }
}

for (const candidate of candidates) {
  const display = relative(workspace, candidate.path);
  if (display.startsWith(`..${sep}`)) {
    throw new Error(`Refusing to prune outside workspace: ${candidate.path}`);
  }
  console.log(
    `${apply ? 'REMOVE' : 'WOULD_REMOVE'}\t${display}\t${candidate.ageDays.toFixed(1)} days`,
  );
  if (apply) rmSync(candidate.path, {recursive: true, force: true});
}

console.log(
  `${apply ? 'Removed' : 'Found'} ${candidates.length} unreferenced asset set(s); ` +
    `${referencedSets.size} set(s) remain referenced`,
);
