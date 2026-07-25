import {Img, staticFile} from 'remotion';
import {CodePlate} from './CodePlate';
import {resolvePlateMode} from './plateMode';
import type {SceneData} from './types';

type Props = {
  scene: SceneData;
  /**
   * Raster treatment hint for diary LayerWipe-style filters.
   * Ignored for code/svg plates except monochrome for ink-comic.
   */
  monochrome?: boolean;
  objectFit?: 'contain' | 'cover';
  style?: React.CSSProperties;
};

/**
 * Unified illustration plate: raster PNG, static SVG file, or code motif.
 * Keeps Scene / InkComicScene free of plate-source branching.
 */
export const ScenePlate: React.FC<Props> = ({
  scene,
  monochrome = false,
  objectFit = 'contain',
  style,
}) => {
  const mode = resolvePlateMode(scene);

  if (mode === 'code') {
    return (
      <div style={{position: 'absolute', inset: 0, ...style}}>
        <CodePlate scene={scene} monochrome={monochrome} />
      </div>
    );
  }

  if (mode === 'svg') {
    const svgPath = scene.assets.svg;
    if (!svgPath) return null;
    return (
      <Img
        src={staticFile(svgPath)}
        style={{
          width: '100%',
          height: '100%',
          objectFit,
          objectPosition: 'center center',
          filter: monochrome
            ? 'grayscale(0.75) contrast(1.12)'
            : scene.visual_mode === 'essay'
              ? 'contrast(0.95) saturate(0.82)'
              : undefined,
          ...style,
        }}
      />
    );
  }

  const raster = scene.assets.color || scene.assets.bw;
  if (!raster) return null;
  return (
    <Img
      src={staticFile(raster)}
      style={{
        width: '100%',
        height: '100%',
        objectFit,
        objectPosition: 'center center',
        ...style,
      }}
    />
  );
};
