import {execFileSync} from 'node:child_process';
import {cpSync, existsSync, mkdirSync, mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {basename, dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const pkg = await import(resolve(root, 'package.json'), {with: {type: 'json'}});
const folderName = `${pkg.default.name}-${pkg.default.version}`;
const releaseDir = resolve(root, 'release');
const archive = resolve(releaseDir, `${folderName}-share.zip`);
const stagingRoot = mkdtempSync(resolve(tmpdir(), 'story-video-share-'));
const stagingProject = resolve(stagingRoot, folderName);

const entries = [
  '.gitignore',
  'DESIGN.md',
  'README.md',
  'examples',
  'package-lock.json',
  'package.json',
  'public/assets/02_bw.svg',
  'public/assets/02_color.svg',
  'public/assets/03_bw.svg',
  'public/assets/03_color.svg',
  'public/fonts',
  'references',
  'remotion.config.ts',
  'scripts',
  'skill-package',
  'src',
  'storyboard.json',
  'storyboard.uploaded.json',
  'tsconfig.json',
];

try {
  mkdirSync(stagingProject, {recursive: true});
  for (const entry of entries) {
    const source = resolve(root, entry);
    if (!existsSync(source)) throw new Error(`Missing package entry: ${entry}`);
    const target = resolve(stagingProject, entry);
    mkdirSync(dirname(target), {recursive: true});
    cpSync(source, target, {
      recursive: true,
      filter: (path) => basename(path) !== '.DS_Store',
    });
  }

  mkdirSync(releaseDir, {recursive: true});
  rmSync(archive, {force: true});
  execFileSync('zip', ['-qr', archive, folderName], {cwd: stagingRoot});
  console.log(`✓ share package → ${archive}`);
} finally {
  rmSync(stagingRoot, {recursive: true, force: true});
}
