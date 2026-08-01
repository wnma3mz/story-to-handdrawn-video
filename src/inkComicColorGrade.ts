import type {ColorGrade, SceneData} from './types';

const monochromeFilter = (kind: SceneData['scene_kind']) => {
  switch (kind) {
    case 'host':
      return 'grayscale(0.82) contrast(1.15) brightness(0.9)';
    case 'evidence':
      return 'grayscale(0.72) contrast(1.19) brightness(0.94) sepia(0.08)';
    case 'map':
      return 'grayscale(0.8) contrast(1.13) brightness(0.95) sepia(0.1)';
    default:
      return 'grayscale(0.72) contrast(1.16) brightness(0.93)';
  }
};

export const inkComicSceneFilter = (
  grade: ColorGrade | undefined,
  kind: SceneData['scene_kind'],
) => {
  switch (grade) {
    case 'warm_bronze':
      return kind === 'evidence'
        ? 'grayscale(0.1) sepia(0.12) saturate(0.74) contrast(1.11) brightness(1.04)'
        : 'grayscale(0.1) sepia(0.12) saturate(0.76) contrast(1.08) brightness(1.04)';
    case 'snow_cinnabar':
      return kind === 'evidence'
        ? 'grayscale(0.04) saturate(0.96) contrast(1.12) brightness(1.05)'
        : 'grayscale(0.04) saturate(0.94) contrast(1.09) brightness(1.04)';
    default:
      return monochromeFilter(kind);
  }
};

export const inkComicCoverFilter = (
  grade: ColorGrade | undefined,
  portrait: boolean,
) => {
  if (grade === 'warm_bronze') {
    return portrait
      ? 'grayscale(0.14) sepia(0.14) saturate(0.78) contrast(1.1) brightness(0.98)'
      : 'grayscale(0.14) sepia(0.14) saturate(0.78) contrast(1.1) brightness(0.76)';
  }
  if (grade === 'snow_cinnabar') {
    return portrait
      ? 'grayscale(0.04) saturate(0.96) contrast(1.12) brightness(0.96)'
      : 'grayscale(0.04) saturate(0.96) contrast(1.12) brightness(0.73)';
  }
  return portrait
    ? 'grayscale(0.74) contrast(1.16) brightness(0.92)'
    : 'grayscale(0.74) contrast(1.18) brightness(0.67)';
};

export const inkComicBottomGradient = (
  grade: ColorGrade | undefined,
  portrait: boolean,
) => {
  if (portrait) {
    return 'linear-gradient(180deg, rgba(12,12,12,0) 55%, rgba(12,12,12,0.34) 70%, rgba(12,12,12,0.92) 100%)';
  }
  const bottomOpacity =
    grade === 'warm_bronze' ? 0.7 : grade === 'snow_cinnabar' ? 0.76 : 0.84;
  return `linear-gradient(180deg, rgba(12,12,12,0.025) 50%, rgba(12,12,12,${bottomOpacity}) 100%)`;
};

export const inkComicSubtitleBackground = (
  grade: ColorGrade | undefined,
  portrait: boolean,
) => {
  if (portrait) return 'rgba(10,10,10,0.84)';
  if (grade === 'warm_bronze') return 'rgba(10,9,8,0.62)';
  if (grade === 'snow_cinnabar') return 'rgba(8,9,10,0.66)';
  return 'rgba(10,10,10,0.7)';
};
