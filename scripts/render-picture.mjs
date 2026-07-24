import {execFileSync} from 'node:child_process';
import {mkdirSync} from 'node:fs';

const args = process.argv.slice(2);
const episode = process.env.EPISODE || 'default';
const isPreview = args.includes('--preview');
const isCover = args.includes('--cover');
const isUploaded = args.includes('--uploaded');
const outDir = `out/${episode}`;

mkdirSync('out/releases', {recursive: true});
mkdirSync(outDir, {recursive: true});

if (isCover) {
  execFileSync(
    'npx',
    ['remotion', 'still', 'src/index.ts', 'EpisodeCover', `${outDir}/cover.png`],
    {stdio: 'inherit'},
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
    {stdio: 'inherit'},
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
    {stdio: 'inherit'},
  );
}
