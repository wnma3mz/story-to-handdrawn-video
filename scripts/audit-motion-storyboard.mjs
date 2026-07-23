import {existsSync, readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const file = resolve(root, process.argv[2] || 'storyboard.json');
if (!existsSync(file)) throw new Error(`missing storyboard: ${file}`);

const storyboard = JSON.parse(readFileSync(file, 'utf8'));
const profiles = JSON.parse(readFileSync(resolve(root, 'src/motion-profiles.json'), 'utf8'));
const {width, height} = storyboard.project;
const intervals = [];

for (const scene of storyboard.scenes) {
  const id = String(scene.visual_interval_id || scene.id);
  const last = intervals.at(-1);
  if (!last || last.id !== id) {
    intervals.push({
      id,
      motion: scene.motion || 'hold',
      durationSec: 0,
      sceneIds: [],
    });
  }
  const interval = intervals.at(-1);
  interval.durationSec += Number(scene.duration_sec);
  interval.sceneIds.push(scene.id);
}

const errors = [];
const rows = [];
for (const interval of intervals) {
  const profile = profiles[interval.motion];
  if (!profile) {
    errors.push(`${interval.id}: missing renderer profile for ${interval.motion}`);
    continue;
  }
  const scaleDeltaPct = Math.abs(profile.endScale - profile.startScale) * 100;
  const panTraversePx = Math.hypot(
    ((profile.endXPercent - profile.startXPercent) / 100) * width,
    ((profile.endYPercent - profile.startYPercent) / 100) * height,
  );
  const safetyZoomPct = (Math.min(profile.startScale, profile.endScale) - 1) * 100;
  if (interval.motion === 'push_soft' || interval.motion === 'pull_soft') {
    if (scaleDeltaPct < 1.4) errors.push(`${interval.id}: soft zoom is below 1.4%`);
  } else if (['push', 'pull', 'push_left', 'push_right'].includes(interval.motion)) {
    if (scaleDeltaPct < 2.4) errors.push(`${interval.id}: active zoom is below 2.4%`);
  } else if (interval.motion.startsWith('pan_')) {
    if (panTraversePx < 24) errors.push(`${interval.id}: pan traverse is below 24px`);
    if (safetyZoomPct < 3.2) errors.push(`${interval.id}: pan safety zoom is below 3.2%`);
  }
  rows.push({
    interval: interval.id,
    motion: interval.motion,
    duration_sec: Number(interval.durationSec.toFixed(3)),
    scale_delta_pct: Number(scaleDeltaPct.toFixed(2)),
    pan_traverse_px: Number(panTraversePx.toFixed(1)),
    safety_zoom_pct: Number(safetyZoomPct.toFixed(2)),
  });
}

const vocabulary = new Set(intervals.map(({motion}) => motion));
const settled = intervals.filter(({motion}) => ['hold', 'push_soft'].includes(motion)).length;
const summary = {
  status: errors.length ? 'FAIL' : 'PASS',
  intervals: intervals.length,
  motions: [...vocabulary],
  settled_interval_ratio: Number((settled / Math.max(1, intervals.length)).toFixed(3)),
  rows,
  errors,
};
console.log(JSON.stringify(summary, null, 2));
if (errors.length) process.exit(1);
