import {
  AbsoluteFill,
  Img,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {LayerWipe} from './LayerWipe';
import {InkComicScene} from './InkComicScene';
import {MotionStage} from './MotionStage';
import {TextWipe} from './TextWipe';
import type {SceneData} from './types';

export const Scene: React.FC<{scene: SceneData}> = ({scene}) => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const total = Math.round(scene.duration_sec * fps);
  const at = (ratio: number) => Math.round(total * ratio);
  const has = (layer: string) => scene.layers.includes(layer as never);
  const speedMode = !has('detail');
  const staticColor = has('color') && !has('bw_full') && !has('detail');
  const fullUploadedPage =
    scene.shot === 'full_uploaded_page' && scene.assets.color;

  if (scene.visual_mode === 'ink-comic') {
    return <InkComicScene scene={scene} />;
  }

  if (scene.visual_mode === 'essay') {
    const colorAsset = scene.assets.color;
    const colorFadeIn = Math.round(total * 0.18);
    const colorOpacity = Math.min(1, colorAsset ? Math.max(0, frame / Math.max(1, colorFadeIn)) : 0);
    return (
      <AbsoluteFill style={{backgroundColor: '#FCFAF5', overflow: 'hidden'}}>
        <MotionStage scene={scene}>
          {colorAsset ? (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                opacity: colorOpacity,
              }}
            >
              <Img
                src={staticFile(colorAsset)}
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'contain',
                  objectPosition: 'center center',
                  filter: 'contrast(0.95) saturate(0.82)',
                }}
              />
            </div>
          ) : null}
        </MotionStage>

        <TextWipe
          text={scene.text}
          startFrame={0}
          durationFrames={total}
          variant="essay"
        />
      </AbsoluteFill>
    );
  }

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
      <MotionStage scene={scene}>
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
      </MotionStage>

      <TextWipe
        text={scene.text}
        textAsset={scene.assets.text_image}
        startFrame={0}
        durationFrames={at(speedMode ? 0.22 : 0.16)}
      />
    </AbsoluteFill>
  );
};
