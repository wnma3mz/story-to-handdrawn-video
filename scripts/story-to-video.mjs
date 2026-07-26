import {execFileSync, spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {existsSync, mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {
  durationFor,
  formatCaption,
  hasTerminalPunctuation,
  splitStory,
} from './lib/story-text.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const styles = JSON.parse(readFileSync(resolve(root, 'config/styles.json'), 'utf8'));
const motionProfiles = JSON.parse(
  readFileSync(resolve(root, 'src/motion-profiles.json'), 'utf8'),
);
const allowedMotions = new Set(Object.keys(motionProfiles));
const fill = (text, vars) => text.replace(/\{(\w+)\}/g, (_, key) => (vars && key in vars) ? String(vars[key]) : `{${key}}`);

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
if (!args.input && !args.text) {
  console.error(
    'Usage: npm run story -- --input examples/story.txt [--generate --apply --render]\n' +
      '       npm run story -- --text "第一句。第二句。"',
  );
  process.exit(1);
}

const sourceText = args.input
  ? readFileSync(resolve(root, String(args.input)), 'utf8')
  : String(args.text);
const title = String(args.title || '手绘故事');
const cover = {
  series_title: String(args['series-title'] || '手绘故事 · 动画'),
  ...(args['episode-label'] ? {episode_label: String(args['episode-label'])} : {}),
  ...(args['episode-number'] ? {episode_number: String(args['episode-number'])} : {}),
  ...(args['cover-title'] ? {title: String(args['cover-title'])} : {}),
  ...(args['cover-background'] ? {background: String(args['cover-background'])} : {}),
};
const textMode = String(args['text-mode'] || 'font');
const visualPlanPath = args['visual-plan']
  ? resolve(root, String(args['visual-plan']))
  : null;
const visualPlan = visualPlanPath
  ? JSON.parse(readFileSync(visualPlanPath, 'utf8'))
  : {};
const generator = String(args.generator || 'codex');
const transition = String(args.transition || 'cut');
const transitionSec = Number(args['transition-sec'] || 0.7);
const shouldGenerate = args.generate === true;
const shouldGenerateWithApi = shouldGenerate && generator === 'api';
const shouldPrepareCodex = shouldGenerate && generator === 'codex';
const shouldApply = args.apply === true;
const shouldRender = args.render === true;
const shouldForce = args.force === true;
const sceneContract = args['scene-contract'] === true;
const visualMode = String(args['visual-mode'] || 'diary');
const generationConcurrency = Number(args.jobs || 4);

if (!['image2', 'font'].includes(textMode)) {
  throw new Error('--text-mode must be image2 or font');
}
if (!['codex', 'api'].includes(generator)) {
  throw new Error('--generator must be codex or api');
}
if (!['diary', 'ink-comic', 'essay'].includes(visualMode)) {
  throw new Error('--visual-mode must be diary, ink-comic, or essay');
}
if (
  !Number.isInteger(generationConcurrency) ||
  generationConcurrency < 1 ||
  generationConcurrency > 16
) {
  throw new Error('--jobs must be an integer within 1..16');
}
if (visualMode === 'ink-comic' && textMode === 'image2') {
  throw new Error('--visual-mode ink-comic uses code subtitles; choose --text-mode font');
}
if (visualMode === 'essay' && textMode === 'image2') {
  throw new Error('--visual-mode essay uses code typesetting; choose --text-mode font');
}
if (generator === 'codex' && args.manifest && !args.output) {
  throw new Error(
    '--manifest requires an episode-specific --output so later planning cannot redirect import',
  );
}
if (!['cut', 'page-flip'].includes(transition)) {
  throw new Error('--transition must be cut or page-flip');
}
if (!Number.isFinite(transitionSec) || transitionSec <= 0 || transitionSec > 2) {
  throw new Error('--transition-sec must be greater than 0 and at most 2');
}
if (shouldApply && !shouldGenerateWithApi) {
  if (shouldPrepareCodex) {
    throw new Error(
      '--apply cannot run before Codex has generated the masters. Generate from codex-image-jobs.json, then run npm run import:codex -- --apply.',
    );
  }
  throw new Error('--apply requires --generate so storyboard.json never points at missing files');
}
if (shouldRender && !shouldApply) {
  throw new Error('--render requires --apply');
}
if (shouldGenerateWithApi && !process.env.OPENAI_API_KEY) {
  throw new Error(
    'OPENAI_API_KEY is missing. The plan and prompts can be created without it; real Image 2 generation requires the key.',
  );
}

const style = styles[visualMode];
const styleLock = style.styleLock;
const characterLock = String(
  args['character-lock'] ||
    '重复出现的主角须保持同一张脸、发型、年龄、服装配色和身体比例；具体人物身份以故事原文为准；不得添加原文未提及的配角、道具或文字',
);
const characterReferencePromptPath = args['character-reference-prompt']
  ? resolve(root, String(args['character-reference-prompt']))
  : null;
if (characterReferencePromptPath && !existsSync(characterReferencePromptPath)) {
  throw new Error(`Missing character reference prompt: ${characterReferencePromptPath}`);
}
const characterReferenceBrief = characterReferencePromptPath
  ? readFileSync(characterReferencePromptPath, 'utf8').trim()
  : characterLock;

const sourceParagraphs = sourceText
  .replace(/\r/g, '')
  .split(/\n+/)
  .map((part) => part.trim())
  .filter(Boolean)
  .map((part) => (hasTerminalPunctuation(part) ? part : `${part}。`));
const plannedSceneIds = Object.keys(visualPlan).filter((key) => /^\d+$/.test(key));
const hasCompleteParagraphPlan =
  plannedSceneIds.length === sourceParagraphs.length &&
  sourceParagraphs.every((_, index) =>
    Object.hasOwn(visualPlan, String(index + 1).padStart(2, '0')),
  );
if (sceneContract && !hasCompleteParagraphPlan) {
  throw new Error(
    '--scene-contract requires visual-plan keys 01..NN to match every non-empty source line exactly',
  );
}
if (sceneContract) {
  for (let index = 0; index < sourceParagraphs.length; index += 1) {
    const id = String(index + 1).padStart(2, '0');
    const entry = visualPlan[id];
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      throw new Error(`--scene-contract requires ${id} to be an object`);
    }
    const caption = typeof entry.caption === 'string' ? entry.caption.trim() : '';
    const captionLines = caption ? caption.split('\n') : [];
    if (!caption || captionLines.length > 3 || captionLines.some((line) => !line.trim())) {
      throw new Error(`--scene-contract requires ${id}.caption to contain 1–3 non-empty lines`);
    }
    const duration = Number(entry.duration_sec);
    if (!Number.isFinite(duration) || duration < 2 || duration > 15) {
      throw new Error(`--scene-contract requires ${id}.duration_sec within 2..15 seconds`);
    }
  }
}
// A requested scene contract preserves one non-empty source line per planned scene,
// allowing full narration to stay on one visual beat while the shorter `caption`
// remains readable. Ordinary prose keeps the established automatic clause splitter.
const storyParts = sceneContract ? sourceParagraphs : splitStory(sourceText);
if (storyParts.length === 0) throw new Error('No usable story sentences found');

const safeTitle =
  title
    .normalize('NFKC')
    .replace(/[^\p{Letter}\p{Number}]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 32) || 'story';
const codePlateMotifs = new Set([
  'window',
  'desk_night',
  'bike',
  'street',
  'two_figures',
  'temple_gate',
  'empty_cup',
  'ghost_window',
  'detour',
  'farewell',
  'abstract_wash',
  'book_lamp',
]);

const illustrationPlan = Object.fromEntries(
  Object.entries(visualPlan).map(([id, entry]) => {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      return [id, entry];
    }
    return [id, {
      visual: entry.visual,
      shot_type: entry.shot_type,
      focus: entry.focus,
      scene_kind: entry.scene_kind,
      accent: entry.accent,
      plate_mode: entry.plate_mode,
      code_plate: entry.code_plate,
      svg: entry.svg,
    }];
  }),
);
const hashInput = [
  generator === 'codex' ? 'codex-illustration-v5' : 'api-v3',
  visualMode,
  title,
  textMode,
  characterLock,
  characterReferenceBrief,
  JSON.stringify(illustrationPlan),
  sourceText,
].join('\n');
const storyHash = createHash('sha256').update(hashInput).digest('hex').slice(0, 8);
const requestedAssetSet = args['asset-set'] ? String(args['asset-set']) : null;
if (requestedAssetSet && !/^[\p{Letter}\p{Number}._-]+$/u.test(requestedAssetSet)) {
  throw new Error('--asset-set may contain only letters, numbers, dots, underscores, and hyphens');
}
const assetSet = requestedAssetSet || `${safeTitle}-${storyHash}`;

const referenceBw = resolve(root, 'references/style-bw.png');
const referenceColor = resolve(root, 'references/style-color.png');
if (!existsSync(referenceBw) || !existsSync(referenceColor)) {
  throw new Error('Missing references/style-bw.png or references/style-color.png');
}

const generatedRoot = generator === 'codex' ? `generated/codex/${assetSet}` : 'generated/auto';
const promptDir = resolve(root, 'prompts', generatedRoot);
const assetDir = resolve(root, 'public/assets', generatedRoot);
mkdirSync(promptDir, {recursive: true});
mkdirSync(assetDir, {recursive: true});

const projectAsset = (name) => `assets/${generatedRoot}/${name}`;
const absoluteAsset = (name) => resolve(assetDir, name);
const writePrompt = (name, value) => {
  const path = resolve(promptDir, name);
  writeFileSync(path, `${value.trim()}\n`);
  return path;
};

const imageCli = resolve(
  process.env.CODEX_HOME || resolve(homedir(), '.codex'),
  'skills/.system/imagegen/scripts/image_gen.py',
);

const runImage2Edit = ({images, promptFile, size, out}) => {
  if (!existsSync(imageCli)) throw new Error(`Image 2 CLI not found: ${imageCli}`);
  const commandArgs = [
    imageCli,
    'edit',
    '--model',
    'gpt-image-2',
    ...images.flatMap((image) => ['--image', image]),
    '--prompt-file',
    promptFile,
    '--size',
    size,
    '--quality',
    'high',
    '--out',
    out,
    ...(shouldForce ? ['--force'] : []),
  ];
  execFileSync(process.env.PYTHON || 'python3', commandArgs, {
    cwd: root,
    stdio: 'inherit',
  });
};

const captionCropHeight = 342;
const captionScanHeight = 400;

const detectCaptionCropY = (masterPath) => {
  const detection = spawnSync(
    'ffmpeg',
    [
      '-hide_banner',
      '-loglevel',
      'verbose',
      '-loop',
      '1',
      '-i',
      masterPath,
      '-vf',
      `crop=1024:${captionScanHeight}:0:0,negate,format=gray,lut=y='if(gt(val,80),255,0)',cropdetect=limit=0.1:round=2:reset=0`,
      '-frames:v',
      '3',
      '-f',
      'null',
      '-',
    ],
    {cwd: root, encoding: 'utf8'},
  );
  const log = `${detection.stdout || ''}\n${detection.stderr || ''}`;
  const matches = [...log.matchAll(/crop=(\d+):(\d+):(\d+):(\d+)/g)];
  const last = matches.at(-1);
  if (detection.status !== 0 || !last) {
    console.warn(`Could not detect caption bounds for ${masterPath}; using top-aligned crop`);
    return 0;
  }

  const contentHeight = Number(last[2]);
  const contentY = Number(last[4]);
  const centeredY = Math.round(contentY + contentHeight / 2 - captionCropHeight / 2);
  return Math.max(0, Math.min(captionScanHeight - captionCropHeight, centeredY));
};

let previousColor = null;
const scenes = [];
const codexJobs = [];

let codexCharacterReference = null;
let suppliedCharacterReference = null;
if (generator === 'codex' && visualMode !== 'essay') {
  suppliedCharacterReference = args['character-reference']
    ? resolve(root, String(args['character-reference']))
    : null;
  if (suppliedCharacterReference && !existsSync(suppliedCharacterReference)) {
    throw new Error(`Missing supplied character reference: ${suppliedCharacterReference}`);
  }
  codexCharacterReference = suppliedCharacterReference || absoluteAsset('00_character_reference.png');
  if (!suppliedCharacterReference) {
    const charRef = style.characterRef;
    const characterPrompt = writePrompt(
      '00_character_reference.txt',
      `Use case: ${charRef.useCase}
Asset type: fixed recurring-character reference sheet for a ${charRef.assetType} video
Input images: ${charRef.inputImagesNote}.
Primary request: follow ONLY the episode-specific character-reference brief below. Do not add any identity mentioned only by the broader episode continuity lock.
Character-reference brief:
${characterReferenceBrief}
Episode continuity lock (context only; it does not expand the reference-sheet cast):
${characterLock}
Style: ${styleLock}
Composition: neutral light-gray reference sheet, all uncropped full-body poses centered with generous spacing and a clean 10% safe border. No scenery, furniture, extra people, props or decorative marks.
Color: ${charRef.color}.
Constraints: this is an identity reference only; no text, letters, numbers, labels, captions, speech bubbles, logo, signature or watermark; no photorealism, glossy 3D or anime styling.`,
    );
    codexJobs.push({
      id: 'character_reference',
      role: 'reference',
      depends_on: [],
      prompt_file: characterPrompt,
      prompt: readFileSync(characterPrompt, 'utf8').trim(),
      output_master: codexCharacterReference,
      references: charRef.needsStyleRefs ? [referenceBw, referenceColor] : [],
    });
  }
}

for (let index = 0; index < storyParts.length; index += 1) {
  const text = storyParts[index];
  const id = String(index + 1).padStart(2, '0');
  const textName = `${id}_text.png`;
  const bwName = `${id}_bw.png`;
  const colorName = `${id}_color.png`;
  const masterName = `${id}_master.png`;
  const visualPlanEntry = visualPlan[id];
  const structuredVisualPlan =
    visualPlanEntry && typeof visualPlanEntry === 'object' && !Array.isArray(visualPlanEntry)
      ? visualPlanEntry
      : {};
  const caption = String(
    structuredVisualPlan.caption || formatCaption(text),
  );
  const visualDirection = String(
    structuredVisualPlan.visual ||
      visualPlanEntry ||
      'Stage one simple visual beat that expresses only the current sentence.',
  );
  const shotType = String(structuredVisualPlan.shot_type || 'story_beat');
  const focus = String(structuredVisualPlan.focus || 'center');
  const motion = String(structuredVisualPlan.motion || 'hold');
  if (!allowedMotions.has(motion)) {
    throw new Error(
      `${id}: unsupported motion ${JSON.stringify(motion)}; ` +
        `expected one of ${[...allowedMotions].join(', ')}`,
    );
  }
  const sceneTransition = String(structuredVisualPlan.transition || 'cut');
  const sceneKind = String(structuredVisualPlan.scene_kind || 'narrative');
  const glyph = structuredVisualPlan.glyph ? String(structuredVisualPlan.glyph) : null;
  const caseLabel = structuredVisualPlan.case_label ? String(structuredVisualPlan.case_label) : null;
  const accent = structuredVisualPlan.accent ? String(structuredVisualPlan.accent) : '#A93B32';
  const plannedDuration = Number(structuredVisualPlan.duration_sec);
  const plateModeRaw = String(structuredVisualPlan.plate_mode || '').trim();
  let plateMode = ['raster', 'svg', 'code'].includes(plateModeRaw)
    ? plateModeRaw
    : structuredVisualPlan.code_plate
      ? 'code'
      : structuredVisualPlan.svg
        ? 'svg'
        : 'raster';
  let codePlate = null;
  let svgAsset = null;
  if (plateMode === 'code') {
    const rawPlate = structuredVisualPlan.code_plate;
    if (!rawPlate || typeof rawPlate !== 'object' || Array.isArray(rawPlate)) {
      throw new Error(`${id}: plate_mode=code requires code_plate object with motif`);
    }
    const motif = String(rawPlate.motif || '').trim();
    if (!codePlateMotifs.has(motif)) {
      throw new Error(
        `${id}: unknown code_plate.motif ${JSON.stringify(motif)}; ` +
          `expected one of ${[...codePlateMotifs].join(', ')}`,
      );
    }
    codePlate = {
      motif,
      ...(rawPlate.background ? {background: String(rawPlate.background)} : {}),
      ...(rawPlate.ink ? {ink: String(rawPlate.ink)} : {}),
      ...(Array.isArray(rawPlate.accents)
        ? {accents: rawPlate.accents.map((value) => String(value))}
        : {}),
      ...(Number.isFinite(Number(rawPlate.seed)) ? {seed: Number(rawPlate.seed)} : {}),
    };
  } else if (plateMode === 'svg') {
    const rawSvg = String(
      structuredVisualPlan.svg ||
        (structuredVisualPlan.assets && structuredVisualPlan.assets.svg) ||
        '',
    ).trim();
    if (!rawSvg) {
      throw new Error(`${id}: plate_mode=svg requires svg path relative to public/`);
    }
    svgAsset = rawSvg.replace(/^public\//, '');
  }
  const needsRasterMaster = plateMode === 'raster';
  const usesImage2Text = needsRasterMaster && visualMode === 'diary' && textMode === 'image2';
  const textVariant = usesImage2Text ? 'image2text' : 'font';
  const masterSize = visualMode === 'ink-comic'
    ? style.masterSize.default
    : usesImage2Text ? '1024x1536' : '1024x1024';
  const captionPanel = fill(style.captionPanel[textVariant] || style.captionPanel.font, {caption});
  const textConstraint = style.textConstraint[textVariant] || style.textConstraint.font;
  const illustrationPanel = style.illustrationPanel[textVariant] || style.illustrationPanel.font;
  const assetType = style.assetType[textVariant] || style.assetType.font;
  const compositionRule = style.compositionRule;
  const colorRule = fill(style.colorRule, {accent});
  const isolationRule = style.isolationRule;

  const hasContinuityReference = Boolean(previousColor) || Boolean(codexCharacterReference);

  // Non-raster plates skip Image2 entirely: code motifs render in Remotion,
  // svg plates load static public assets. Only raster scenes write prompts/jobs.
  let masterPrompt = null;
  if (needsRasterMaster) {
    const sp = style.scenePrompt;
    const isEssay = visualMode === 'essay';
    const inputImagesLine = [
      `Input images: ${sp.inputImagesNote}`,
      !isEssay && hasContinuityReference ? '; the fixed protagonist character sheet is the identity reference' : '',
      '. ',
      isEssay ? 'These are mood illustrations for a personal memoir; each image should feel like a faded memory, a half-remembered moment, not a documentary photograph.' : 'Ignore all text in references.',
    ].join('');

    const lines = [
      `Use case: ${sp.useCase}`,
      `Asset type: ${assetType}.`,
      inputImagesLine,
      isEssay ? `Essay passage to evoke: "${text}"` : `Narrative sentence to illustrate: "${text}"`,
    ];
    if (isEssay) {
      lines.push(`Emotional register: ${visualDirection}`);
    } else {
      lines.push(`Scene direction: ${visualDirection}`);
      lines.push(`Narrative shot type: ${shotType}`);
      lines.push(`Primary focal area: ${focus}`);
    }
    lines.push(`Create ${sp.createLine}`);
    if (!isEssay) {
      lines.push(`Character lock: ${characterLock}`);
    }
    lines.push(
      `Style: ${styleLock}`,
      captionPanel,
      illustrationPanel,
      `Composition: ${compositionRule}`,
      `Color: ${colorRule}`,
    );
    if (!isEssay) {
      lines.push(
        `Continuity: preserve the locked character design. Use the fixed character sheet only for the protagonist's identity, never copy its pose or composition. Include only people required by the current narrative sentence.`,
        `Narrative isolation: ${isolationRule}`,
      );
    }
    lines.push(`Constraints: ${sp.constraintsPrefix}${textConstraint}${sp.constraintsSuffix}.`);

    masterPrompt = writePrompt(`${id}_master.txt`, lines.join('\n'));
  } else {
    writePrompt(
      `${id}_plate.txt`,
      `plate_mode: ${plateMode}
${plateMode === 'code' ? `code_plate: ${JSON.stringify(codePlate)}` : `svg: ${svgAsset}`}
source: ${text}
note: no Image2 master; renderer draws this plate in code or loads the static SVG.`,
    );
  }

  if (needsRasterMaster && shouldGenerateWithApi) {
    runImage2Edit({
      images: [
        ...(visualMode === 'ink-comic' ? [] : [referenceBw, referenceColor]),
        ...(previousColor ? [previousColor] : []),
      ],
      promptFile: masterPrompt,
      size: masterSize,
      out: absoluteAsset(masterName),
    });
    if (usesImage2Text) {
      const captionCropY = detectCaptionCropY(absoluteAsset(masterName));
      execFileSync(
        'ffmpeg',
        [
          '-hide_banner',
          '-loglevel',
          'error',
          '-i',
          absoluteAsset(masterName),
          '-vf',
          `crop=1024:${captionCropHeight}:0:${captionCropY},scale=1536:512:flags=lanczos`,
          '-frames:v',
          '1',
          '-y',
          absoluteAsset(textName),
        ],
        {cwd: root, stdio: 'inherit'},
      );
    }
    if (visualMode !== 'essay') {
      execFileSync(
        'ffmpeg',
        [
          '-hide_banner',
          '-loglevel',
          'error',
          '-i',
          absoluteAsset(masterName),
          '-vf',
          visualMode === 'ink-comic'
            ? 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=gray,eq=contrast=1.16:brightness=-0.02,unsharp=5:5:0.42:5:5:0'
            : usesImage2Text
            ? 'crop=1024:1024:0:512,format=gray,eq=contrast=1.18:brightness=0.035,unsharp=5:5:0.55:5:5:0'
            : 'format=gray,eq=contrast=1.18:brightness=0.035,unsharp=5:5:0.55:5:5:0',
          '-frames:v',
          '1',
          '-y',
          absoluteAsset(bwName),
        ],
        {cwd: root, stdio: 'inherit'},
      );
    }
    execFileSync(
      'ffmpeg',
      [
        '-hide_banner',
        '-loglevel',
        'error',
        '-i',
        absoluteAsset(masterName),
        '-vf',
        visualMode === 'essay'
          ? 'scale=868:698:force_original_aspect_ratio=decrease,pad=868:698:(ow-iw)/2:(oh-ih)/2:#FCFAF5'
          : visualMode === 'ink-comic'
            ? 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080'
            : usesImage2Text ? 'crop=1024:1024:0:512' : 'null',
        '-frames:v',
        '1',
        '-y',
        absoluteAsset(colorName),
      ],
      {cwd: root, stdio: 'inherit'},
    );
    previousColor = absoluteAsset(colorName);
  }

  if (needsRasterMaster && generator === 'codex') {
    codexJobs.push({
      id,
      role: 'scene',
      depends_on:
        visualMode !== 'essay' &&
        codexCharacterReference &&
        !suppliedCharacterReference
          ? ['character_reference']
          : [],
      prompt_file: masterPrompt,
      prompt: readFileSync(masterPrompt, 'utf8').trim(),
      output_master: absoluteAsset(masterName),
      references: [
        ...(visualMode === 'ink-comic' ? [] : [referenceBw, referenceColor]),
        ...(visualMode === 'essay' ? [] : [codexCharacterReference].filter(Boolean)),
      ].filter(Boolean),
    });
  }

  const essayMotion = visualMode === 'essay'
    ? (['hold', 'push_soft'].includes(motion) ? motion : 'push_soft')
    : motion;
  const useSimpleLayers =
    !needsRasterMaster || visualMode === 'essay' || visualMode === 'ink-comic';

  scenes.push({
    id,
    duration_sec: visualMode === 'essay'
      ? (Number.isFinite(plannedDuration) && plannedDuration >= 8 && plannedDuration <= 30
          ? plannedDuration
          : Math.max(10, durationFor(caption) * 2.2))
      : (Number.isFinite(plannedDuration) && plannedDuration >= 2 && plannedDuration <= 15
          ? plannedDuration
          : durationFor(caption)),
    text: caption,
    narration: text,
    visual: visualDirection,
    shot: shotType,
    focus,
    motion: essayMotion,
    transition_to_next: sceneTransition,
    visual_mode: visualMode,
    plate_mode: plateMode,
    code_plate: codePlate,
    scene_kind: sceneKind,
    glyph,
    case_label: caseLabel,
    accent,
    layers: useSimpleLayers
      ? ['text', 'color']
      : ['text', 'bw_full', 'color'],
    color_hint: !needsRasterMaster
      ? (plateMode === 'code'
          ? `code plate motif=${codePlate?.motif}`
          : `static svg plate ${svgAsset}`)
      : visualMode === 'essay'
      ? '柔和暖调水彩：暖赭石、褪色靛蓝、灰玫瑰、鼠尾草绿、羊皮纸奶油色，纸上可见笔触纹理，留白25%以上'
      : visualMode === 'ink-comic'
        ? `全画面黑白灰，仅用 ${accent} 强调一个关键证物或情绪焦点`
        : '仅使用元视频的鼠尾草绿、灰蓝、浅棕、砖红、暖黄等低饱和蜡笔色，保留大量纯白',
    detail_hint: null,
    assets: {
      text_image: needsRasterMaster && !['essay', 'ink-comic'].includes(visualMode) && usesImage2Text
        ? projectAsset(textName)
        : null,
      bw: needsRasterMaster && visualMode !== 'essay' ? projectAsset(bwName) : null,
      detail: null,
      color: needsRasterMaster ? projectAsset(colorName) : null,
      svg: plateMode === 'svg' ? svgAsset : null,
    },
  });
}

const storyboard = {
  project: {
    title,
    mode: 'speed',
    images_per_scene: 1,
    derive_bw: 'local',
    enable_detail: false,
    gen_size: 1024,
    visual_mode: visualMode,
    subtitle_contract: visualMode === 'ink-comic' ? 'draft_summary' : undefined,
    export_size: visualMode === 'ink-comic' ? [1920, 1080] : [1080, 1440],
    ratio: visualMode === 'ink-comic' ? '16:9' : '3:4',
    width: visualMode === 'ink-comic' ? 1920 : 1080,
    height: visualMode === 'ink-comic' ? 1080 : 1440,
    fps: 30,
    transition,
    transition_sec: transitionSec,
    style_lock: styleLock,
    character_lock: characterLock,
    cover,
    audio: {
      voiceover: 'continuous_groups',
      bgm: 'optional_bed_only',
      bgm_follows_text: false,
    },
  },
  scenes,
};

const outputPath = resolve(
  root,
  String(args.output || (shouldApply ? 'storyboard.json' : 'storyboard.generated.json')),
);
mkdirSync(dirname(outputPath), {recursive: true});
writeFileSync(outputPath, `${JSON.stringify(storyboard, null, 2)}\n`);

let codexManifestPath = null;
if (generator === 'codex') {
  const manifestPath = resolve(root, String(args.manifest || 'codex-image-jobs.json'));
  codexManifestPath = manifestPath;
  mkdirSync(dirname(manifestPath), {recursive: true});
  writeFileSync(
    manifestPath,
    `${JSON.stringify(
      {
        version: 1,
        generator: 'codex-image2',
        visual_mode: visualMode,
        master_size: visualMode === 'ink-comic' ? '1536x1024' : null,
        asset_set: assetSet,
        storyboard: outputPath,
        text_mode: textMode,
        execution: {
          max_concurrency: generationConcurrency,
          stages: [
            {
              id: 'references',
              roles: ['reference'],
              max_concurrency: 1,
            },
            {
              id: 'scenes',
              roles: ['scene'],
              max_concurrency: generationConcurrency,
            },
          ],
        },
        jobs: codexJobs,
      },
      null,
      2,
    )}\n`,
  );
  console.log(`Codex Image2 jobs → ${manifestPath}`);
}

console.log(
  `Prepared ${scenes.length} scenes → ${outputPath}\n` +
    `Prompts → ${promptDir}\n` +
    (shouldGenerateWithApi
      ? `Image 2 API assets → ${assetDir}`
      : shouldPrepareCodex
        ? `Codex Image2 queue prepared at ${codexManifestPath}. Run reference jobs first, then scene jobs concurrently, and import that manifest after generation.`
        : `Plan-only mode. Codex Image2 is the default and does not require OPENAI_API_KEY; add --generate to prepare its job manifest.`),
);

if (shouldRender) {
  execFileSync(
    'npm',
    ['run', 'render', '--', '--storyboard', outputPath],
    {cwd: root, stdio: 'inherit'},
  );
}
