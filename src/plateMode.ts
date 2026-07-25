import type {CodePlateSpec, PlateMode, SceneData} from './types';

/** Motifs shipped with CodePlate. Unknown keys fall back to abstract_wash. */
export const CODE_PLATE_MOTIFS = [
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
] as const;

export type CodePlateMotif = (typeof CODE_PLATE_MOTIFS)[number];

export const isCodePlateMotif = (value: string): value is CodePlateMotif =>
  (CODE_PLATE_MOTIFS as readonly string[]).includes(value);

/**
 * Resolve how a scene's illustration plate should be drawn.
 * Explicit plate_mode wins; otherwise infer from code_plate / svg / color.
 */
export const resolvePlateMode = (scene: SceneData): PlateMode => {
  if (scene.plate_mode === 'code' || scene.plate_mode === 'svg' || scene.plate_mode === 'raster') {
    return scene.plate_mode;
  }
  if (scene.code_plate && typeof scene.code_plate === 'object') return 'code';
  if (scene.assets?.svg) return 'svg';
  return 'raster';
};

export const isNonRasterPlate = (scene: SceneData): boolean => {
  const mode = resolvePlateMode(scene);
  return mode === 'code' || mode === 'svg';
};

/** Identity key so visual-interval continuity checks stay meaningful for non-raster plates. */
export const plateIdentityKey = (scene: SceneData): string => {
  const mode = resolvePlateMode(scene);
  if (mode === 'code') {
    const plate = scene.code_plate || ({motif: 'abstract_wash'} as CodePlateSpec);
    return `code:${JSON.stringify({
      motif: plate.motif,
      background: plate.background || null,
      ink: plate.ink || null,
      accents: plate.accents || null,
      seed: plate.seed ?? null,
    })}`;
  }
  if (mode === 'svg') {
    return `svg:${scene.assets?.svg || ''}`;
  }
  return `raster:${scene.assets?.color || ''}`;
};

export const sceneHasIllustrationPlate = (scene: SceneData): boolean => {
  const mode = resolvePlateMode(scene);
  if (mode === 'code') return Boolean(scene.code_plate?.motif);
  if (mode === 'svg') return Boolean(scene.assets?.svg);
  return Boolean(scene.assets?.color);
};
