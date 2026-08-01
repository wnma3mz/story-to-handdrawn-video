#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const storyboardArg = args[0];
const groupsArg = args[1];

if (!storyboardArg || !groupsArg) {
  console.error(
    'Usage: node scripts/apply-shared-visual-intervals.mjs <storyboard.json> <01,02;03,04;05>',
  );
  process.exit(2);
}

const storyboardPath = path.resolve(storyboardArg);
const storyboard = JSON.parse(fs.readFileSync(storyboardPath, 'utf8'));
const scenesById = new Map(storyboard.scenes.map((scene) => [String(scene.id), scene]));
const groups = groupsArg
  .split(';')
  .map((group) => group.split(',').map((id) => id.trim()).filter(Boolean))
  .filter((group) => group.length > 0);

for (const [groupIndex, ids] of groups.entries()) {
  const scenes = ids.map((id) => {
    const scene = scenesById.get(id);
    if (!scene) {
      throw new Error(`Unknown scene id ${id} in ${storyboardPath}`);
    }
    return scene;
  });

  const intervalId = `shared-${String(groupIndex + 1).padStart(2, '0')}`;
  const totalDuration = scenes.reduce(
    (sum, scene) => sum + Number(scene.duration_sec),
    0,
  );
  const anchor = scenes[0];
  let elapsed = 0;

  for (const [sceneIndex, scene] of scenes.entries()) {
    const start = elapsed / totalDuration;
    elapsed += Number(scene.duration_sec);
    const end = elapsed / totalDuration;

    scene.visual_interval_id = intervalId;
    scene.visual_interval_start = sceneIndex === 0;
    scene.visual_interval_progress_start = Number(start.toFixed(6));
    scene.visual_interval_progress_end = Number(end.toFixed(6));
    scene.motion = anchor.motion;
    scene.focus = anchor.focus;
    scene.assets = {
      ...scene.assets,
      bw: anchor.assets?.bw ?? null,
      detail: anchor.assets?.detail ?? null,
      color: anchor.assets?.color ?? null,
      svg: anchor.assets?.svg ?? null,
    };
  }
}

fs.writeFileSync(storyboardPath, `${JSON.stringify(storyboard, null, 2)}\n`);
console.log(`Applied ${groups.length} shared visual intervals to ${storyboardPath}`);
