import {Config} from '@remotion/cli/config';
import {existsSync} from 'node:fs';

Config.setPublicDir('./public');
Config.setOverwriteOutput(true);
Config.setVideoImageFormat('jpeg');
// A single browser worker is slower but avoids intermittent local-server races
// observed with multi-tab Chrome rendering on macOS.
Config.setConcurrency(1);

const macChrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
if (existsSync(macChrome)) {
  Config.setBrowserExecutable(macChrome);
}
