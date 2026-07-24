import {execFileSync, spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {existsSync, mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

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

if (!['image2', 'font'].includes(textMode)) {
  throw new Error('--text-mode must be image2 or font');
}
if (!['codex', 'api'].includes(generator)) {
  throw new Error('--generator must be codex or api');
}
if (!['diary', 'ink-comic'].includes(visualMode)) {
  throw new Error('--visual-mode must be diary or ink-comic');
}
if (visualMode === 'ink-comic' && textMode === 'image2') {
  throw new Error('--visual-mode ink-comic uses code subtitles; choose --text-mode font');
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

const terminalPunctuation = /[。！？!?；;]$/;
const narrativeTurn = /^(后来|然后|接着|突然|可是|但是|但|却|于是|直到|最后|没想到|第二天|那天|这时)/;

const hardChunk = (value, maxLength = 36) => {
  const chunks = [];
  let remaining = value.trim();

  while (remaining.length > maxLength) {
    const window = remaining.slice(0, maxLength + 1);
    let cut = Math.max(
      window.lastIndexOf('，'),
      window.lastIndexOf('、'),
      window.lastIndexOf('；'),
    );
    if (cut < Math.floor(maxLength * 0.55)) cut = maxLength;
    else cut += 1;
    chunks.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
};

const splitLongBeat = (sentence, softLimit = 36) => {
  const value = sentence.trim();
  if (value.length <= softLimit) return [value];

  const ending = value.match(/[。！？!?；;]$/)?.[0] || '';
  const body = ending ? value.slice(0, -1) : value;
  const clauses = body
    .split(/(?<=，|、)|(?=(?:后来|然后|接着|突然|可是|但是|但|却|于是|直到|最后|没想到|第二天|那天|这时))/)
    .map((part) => part.trim())
    .filter(Boolean);

  if (clauses.length === 1) return hardChunk(value, softLimit);

  const beats = [];
  let current = '';
  for (const clause of clauses) {
    const candidate = `${current}${clause}`;
    const startsNewBeat = narrativeTurn.test(clause) && current.length >= 12;
    if (current && (candidate.length > softLimit || startsNewBeat)) {
      beats.push(current.replace(/[，、]$/, '。'));
      current = clause;
    } else {
      current = candidate;
    }
  }
  if (current) beats.push(`${current.replace(/[，、]$/, '')}${ending || '。'}`);
  return beats.flatMap((beat) => hardChunk(beat, softLimit));
};

const splitStory = (text) => {
  const normalized = text.replace(/\r/g, '').replace(/[ \t]+/g, ' ').trim();
  const paragraphs = normalized.split(/\n+/).map((part) => part.trim()).filter(Boolean);
  const beats = [];

  for (const paragraph of paragraphs) {
    const sentences = paragraph.match(/[^。！？!?；;]+[。！？!?；;]?/g) || [];
    for (const sentence of sentences) {
      beats.push(...splitLongBeat(sentence));
    }
  }

  return beats
    .map((beat) => beat.trim())
    .filter(Boolean)
    .map((beat) => (terminalPunctuation.test(beat) ? beat : `${beat}。`));
};

const formatCaption = (text, maxCharsPerLine = 13, maxLines = 3) => {
  const lines = [];
  let remaining = text.trim();
  while (remaining) {
    if (remaining.length <= maxCharsPerLine) {
      lines.push(remaining);
      break;
    }
    const window = remaining.slice(0, maxCharsPerLine + 1);
    let cut = Math.max(
      window.lastIndexOf('，'),
      window.lastIndexOf('、'),
      window.lastIndexOf('；'),
      window.lastIndexOf('：'),
    );
    if (cut < Math.floor(maxCharsPerLine * 0.45)) cut = maxCharsPerLine;
    else cut += 1;
    lines.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
    if (/^[。！？!?；;：:,，、]/.test(remaining)) {
      lines[lines.length - 1] += remaining[0];
      remaining = remaining.slice(1).trim();
    }
  }
  if (lines.length > maxLines) {
    throw new Error(`Caption needs ${lines.length} lines; story beat must be split before rendering`);
  }
  return lines.join('\n');
};

const durationFor = (caption) => {
  const lineCount = caption.split('\n').length;
  const characterCount = caption.replace(/\n/g, '').length;
  return Number(Math.min(6.2, Math.max(4.4, 3.8 + lineCount * 0.48 + characterCount * 0.035)).toFixed(1));
};

const styleLock = visualMode === 'ink-comic'
  ? 'full-screen Northern Song monochrome motion-comic illustration, bold black ink outlines, expressive adult faces, grayscale ink-wash depth, restrained paper grain, dramatic but readable staging, selective vermilion or muted field-green color only on the active clue, no fixed white diary page, no photorealism, glossy 3D, anime styling, modern collage typography or watermark'
  : 'minimalist Chinese diary comic reconstructed from the supplied reference video, pure white background, uneven black felt-tip pen outlines, naive wobbly proportions, rough dense black crayon scribbles for dark areas, sparse props, abundant negative space, selective muted wax-crayon color only, no realistic shading, no paper texture, no watermark';
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
  .map((part) => (terminalPunctuation.test(part) ? part : `${part}。`));
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
if (generator === 'codex') {
  const suppliedCharacterReference = args['character-reference']
    ? resolve(root, String(args['character-reference']))
    : null;
  if (suppliedCharacterReference && !existsSync(suppliedCharacterReference)) {
    throw new Error(`Missing supplied character reference: ${suppliedCharacterReference}`);
  }
  codexCharacterReference = suppliedCharacterReference || absoluteAsset('00_character_reference.png');
  if (!suppliedCharacterReference) {
    const characterPrompt = writePrompt(
      '00_character_reference.txt',
      `Use case: ${visualMode === 'ink-comic' ? 'historical-scene' : 'illustration-story'}
Asset type: fixed recurring-character reference sheet for a ${visualMode === 'ink-comic' ? 'Northern Song monochrome motion-comic' : 'hand-drawn Chinese diary-comic'} video
Input images: ${visualMode === 'ink-comic' ? 'none; establish the requested original visual language' : 'the supplied black-and-white and color frames are style references only; ignore their people, composition and Chinese text'}.
Primary request: follow ONLY the episode-specific character-reference brief below. Do not add any identity mentioned only by the broader episode continuity lock.
Character-reference brief:
${characterReferenceBrief}
Episode continuity lock (context only; it does not expand the reference-sheet cast):
${characterLock}
Style: ${styleLock}
Composition: neutral light-gray reference sheet, all uncropped full-body poses centered with generous spacing and a clean 10% safe border. No scenery, furniture, extra people, props or decorative marks.
Color: ${visualMode === 'ink-comic' ? 'almost entirely grayscale; reserve one muted vermilion accent for a small clothing fastener so identity remains trackable' : 'selective muted wax-crayon color only; follow the clothing colors in the character lock, use black scribbles for hair and dark trousers, and leave skin and most of the canvas white'}.
Constraints: this is an identity reference only; no text, letters, numbers, labels, captions, speech bubbles, logo, signature or watermark; no photorealism, glossy 3D or anime styling.`,
    );
    codexJobs.push({
      id: 'character_reference',
      role: 'reference',
      prompt_file: characterPrompt,
      prompt: readFileSync(characterPrompt, 'utf8').trim(),
      output_master: codexCharacterReference,
      references: visualMode === 'ink-comic' ? [] : [referenceBw, referenceColor],
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
  const sceneTransition = String(structuredVisualPlan.transition || 'cut');
  const sceneKind = String(structuredVisualPlan.scene_kind || 'narrative');
  const glyph = structuredVisualPlan.glyph ? String(structuredVisualPlan.glyph) : null;
  const caseLabel = structuredVisualPlan.case_label ? String(structuredVisualPlan.case_label) : null;
  const accent = structuredVisualPlan.accent ? String(structuredVisualPlan.accent) : '#A93B32';
  const plannedDuration = Number(structuredVisualPlan.duration_sec);
  const usesImage2Text = visualMode === 'diary' && textMode === 'image2';
  const masterSize = visualMode === 'ink-comic'
    ? '1536x1024'
    : usesImage2Text ? '1024x1536' : '1024x1024';
  const captionPanel = usesImage2Text
    ? `Top copy panel (pixels y=0–342): pure white background. Write ONLY this Simplified Chinese caption verbatim, preserving the explicit line breaks:
"${caption}"
Use thick casual black felt-tip handwriting, 1–3 lines only, generous 48-pixel left/right margins, and a large readable letter size. Do not put any illustration or decorative mark in this panel. Do not place text below y=342.`
    : 'Use the entire canvas only for the illustration; do not add any text.';
  const textConstraint = usesImage2Text
    ? 'no extra text outside the exact top caption, no letters or numbers in the illustration, no labels, captions, speech bubbles, logo, signature or watermark'
    : 'no text, letters, numbers, labels, captions, speech bubbles, logo, signature or watermark';
  const illustrationPanel = visualMode === 'ink-comic'
    ? 'Use the entire landscape canvas for the illustration. Do not reserve a white caption panel.'
    : usesImage2Text
      ? 'Illustration panel (pixels y=512–1536): use this exact lower 1024×1024 square for the scene. Leave the 342–512 transition band completely white.'
      : 'Use the entire 1024×1024 square for the scene.';
  const assetType = visualMode === 'ink-comic'
    ? 'one full-bleed 16:9 production panel for a historical monochrome motion-comic'
    : usesImage2Text
      ? 'one vertical production master that will be split into a handwritten caption plate and a color illustration plate'
      : 'one square color illustration master';
  const compositionRule = visualMode === 'ink-comic'
    ? 'Compose for a 16:9 full-screen frame. Use cinematic foreground, middle ground and background separation suitable for a restrained 2.5D push. Keep every face, hand and active clue inside the central 82% safe area and the bottom 18% free of essential detail for subtitles. Cropping secondary architecture at the frame edge is allowed; never crop the active clue.'
    : 'Use a comfortably wide camera view. Keep the entire sparse scene in the lower-middle of its illustration square with generous white negative space. Reserve a clean white safe border of at least 10% on the left and right and 8% on the top and bottom. Every figure, limb, prop, building edge, roof, tree branch, rain stroke and motion mark must stay completely inside that safe border. Scale the scene down when necessary; never let any visible mark touch or cross a canvas edge.';
  const colorRule = visualMode === 'ink-comic'
    ? `Render 90–95% of the frame in black, charcoal and warm gray. Use ${accent} only on the single active clue or emotional focal object; do not color whole costumes or backgrounds.`
    : 'Use selective muted wax-crayon color only: sage green, dusty blue, warm tan, brick red and warm yellow. Keep hair, trousers and other dark areas as black scribbles. Leave skin and most of the canvas pure white.';
  const isolationRule = visualMode === 'ink-comic'
    ? 'Show only characters and objects required by this beat. Large background calligraphy, subtitles, labels and exact title text will be added in code; generate none inside the illustration.'
    : 'The character lock defines identities, not an automatic cast list. Show only characters explicitly named in the current sentence or strictly required for its immediate action. Never add family bystanders. Never show a future daughter, rescued child, grandmother, father or any other supporting character before that person is introduced by the narration. Do not carry any person, prop or setting forward merely because it appeared in another scene.';

  const hasContinuityReference = Boolean(previousColor) || Boolean(codexCharacterReference);
  const masterPrompt = writePrompt(
    `${id}_master.txt`,
    `Use case: historical-scene
Asset type: ${assetType}.
Input images: ${visualMode === 'ink-comic' ? 'the fixed character sheet, when supplied, controls identity only' : 'the supplied original-video frames are style references'}${hasContinuityReference ? '; the fixed protagonist character sheet is the identity reference' : ''}. Ignore all text in references.
Narrative sentence to illustrate: "${text}"
Scene direction: ${visualDirection}
Narrative shot type: ${shotType}
Primary focal area: ${focus}
Create one concrete, immediately readable tableau for that sentence. Use the locked recurring protagonists whenever the current sentence requires them.
Character lock: ${characterLock}
Style: ${styleLock}
${captionPanel}
${illustrationPanel}
Composition: ${compositionRule}
Color: ${colorRule}
Continuity: preserve the locked character design. Use the fixed character sheet only for the protagonist's identity, never copy its pose or composition. Include only people required by the current narrative sentence.
Narrative isolation: ${isolationRule}
Constraints: non-graphic historical suspense, no gore; period-accurate Northern Song clothing, architecture and objects; ${textConstraint}; no photorealism, glossy 3D, anime styling, modern props or watermark.`,
  );

  if (shouldGenerateWithApi) {
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

  if (generator === 'codex') {
    codexJobs.push({
      id,
      role: 'scene',
      prompt_file: masterPrompt,
      prompt: readFileSync(masterPrompt, 'utf8').trim(),
      output_master: absoluteAsset(masterName),
      references: [
        ...(visualMode === 'ink-comic' ? [] : [referenceBw, referenceColor]),
        codexCharacterReference,
      ].filter(Boolean),
    });
  }

  scenes.push({
    id,
    duration_sec:
      Number.isFinite(plannedDuration) && plannedDuration >= 2 && plannedDuration <= 15
        ? plannedDuration
        : durationFor(caption),
    text: caption,
    narration: text,
    visual: visualDirection,
    shot: shotType,
    focus,
    motion,
    transition_to_next: sceneTransition,
    visual_mode: visualMode,
    scene_kind: sceneKind,
    glyph,
    case_label: caseLabel,
    accent,
    layers: visualMode === 'ink-comic' ? ['text', 'color'] : ['text', 'bw_full', 'color'],
    color_hint: visualMode === 'ink-comic'
      ? `全画面黑白灰，仅用 ${accent} 强调一个关键证物或情绪焦点`
      : '仅使用元视频的鼠尾草绿、灰蓝、浅棕、砖红、暖黄等低饱和蜡笔色，保留大量纯白',
    detail_hint: null,
    assets: {
      text_image: usesImage2Text ? projectAsset(textName) : null,
      bw: projectAsset(bwName),
      detail: null,
      color: projectAsset(colorName),
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

const outputPath = shouldApply
  ? resolve(root, 'storyboard.json')
  : resolve(root, String(args.output || 'storyboard.generated.json'));
writeFileSync(outputPath, `${JSON.stringify(storyboard, null, 2)}\n`);

if (generator === 'codex') {
  const manifestPath = resolve(root, String(args.manifest || 'codex-image-jobs.json'));
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
        ? `Codex built-in Image2 queue prepared. Generate each manifest job, then import it with npm run import:codex -- --apply.`
        : `Plan-only mode. Codex Image2 is the default and does not require OPENAI_API_KEY; add --generate to prepare its job manifest.`),
);

if (shouldRender) {
  execFileSync('npm', ['run', 'render'], {cwd: root, stdio: 'inherit'});
}
