import {
  AbsoluteFill,
  Img,
  staticFile,
  useVideoConfig,
} from 'remotion';
import {LayerWipe} from './LayerWipe';
import {TextWipe} from './TextWipe';
import type {SceneData} from './types';

export const Scene: React.FC<{scene: SceneData}> = ({scene}) => {
  const {fps} = useVideoConfig();
  const total = Math.round(scene.duration_sec * fps);
  const at = (ratio: number) => Math.round(total * ratio);
  const has = (layer: string) => scene.layers.includes(layer as never);
  const speedMode = !has('detail');
  const staticColor = has('color') && !has('bw_full') && !has('detail');
  const fullUploadedPage =
    scene.shot === 'full_uploaded_page' && scene.assets.color;

  if (fullUploadedPage) {
    return (
      <AbsoluteFill style={{backgroundColor: '#FFFFFF', overflow: 'hidden'}}>
        <Img
          src={staticFile(fullUploadedPage)}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            objectPosition: 'center center',
          }}
        />
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{backgroundColor: '#FFFFFF', overflow: 'hidden'}}>
      {has('bw_full') && scene.assets.bw ? (
        <LayerWipe
          src={scene.assets.bw}
          startFrame={at(speedMode ? 0.18 : 0.16)}
          durationFrames={at(speedMode ? 0.4 : 0.32)}
          zIndex={10}
          treatment="bw"
        />
      ) : null}

      {has('detail') && scene.assets.detail ? (
        <LayerWipe
          src={scene.assets.detail}
          startFrame={at(0.48)}
          durationFrames={at(0.17)}
          zIndex={20}
          treatment="detail"
        />
      ) : null}

      {has('color') && scene.assets.color ? (
        <LayerWipe
          src={scene.assets.color}
          startFrame={staticColor ? 0 : at(speedMode ? 0.52 : 0.65)}
          durationFrames={staticColor ? 1 : at(speedMode ? 0.36 : 0.23)}
          zIndex={30}
          treatment="color"
        />
      ) : null}

      <TextWipe
        text={scene.text}
        textAsset={scene.assets.text_image}
        startFrame={0}
        durationFrames={at(speedMode ? 0.22 : 0.16)}
      />

    </AbsoluteFill>
  );
};
