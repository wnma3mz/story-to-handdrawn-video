import {Config} from '@remotion/cli/config';
import {existsSync} from 'node:fs';
import {isAbsolute, resolve} from 'node:path';

const root = process.cwd();
const resolveFromRoot = (value: string | undefined, fallback: string) => {
  const selected = value || fallback;
  return isAbsolute(selected) ? selected : resolve(root, selected);
};

const storyboardPath = resolveFromRoot(
  process.env.STORYBOARD_PATH,
  'storyboard.json',
);
const uploadedStoryboardPath = resolveFromRoot(
  process.env.UPLOADED_STORYBOARD_PATH,
  'storyboard.uploaded.json',
);
const publicDir = resolveFromRoot(process.env.REMOTION_PUBLIC_DIR, 'public');

Config.setPublicDir(publicDir);
Config.setOverwriteOutput(true);
Config.setVideoImageFormat('jpeg');
// A single browser worker is slower but avoids intermittent local-server races
// observed with multi-tab Chrome rendering on macOS.
Config.setConcurrency(1);
Config.overrideWebpackConfig((current) => ({
  ...current,
  resolve: {
    ...current.resolve,
    alias: {
      ...current.resolve?.alias,
      '@storyboard-data': storyboardPath,
      '@uploaded-storyboard-data': uploadedStoryboardPath,
    },
  },
}));

const macChrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
if (existsSync(macChrome)) {
  Config.setBrowserExecutable(macChrome);
}
