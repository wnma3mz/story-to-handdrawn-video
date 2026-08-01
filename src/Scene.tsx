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
import {isNonRasterPlate} from './plateMode';
import {ScenePlate} from './ScenePlate';
import {TextWipe} from './TextWipe';
import type {SceneData} from './types';

export const Scene: React.FC<{scene: SceneData}> = ({scene}) => {
  const {fps, width, height} = useVideoConfig();
  const portrait = height > width;
  const frame = useCurrentFrame();
  const total = Math.round(scene.duration_sec * fps);
  const at = (ratio: number) => Math.round(total * ratio);
  const has = (layer: string) => scene.layers.includes(layer as never);
  const speedMode = !has('detail');
  const staticColor = has('color') && !has('bw_full') && !has('detail');
  const fullUploadedPage =
    scene.shot === 'full_uploaded_page' && scene.assets.color;
  const nonRaster = isNonRasterPlate(scene);

  if (scene.visual_mode === 'ink-comic') {
    return <InkComicScene scene={scene} />;
  }

  if (scene.visual_mode === 'essay') {
    return (
      <AbsoluteFill style={{backgroundColor: '#FCFAF5', overflow: 'hidden'}}>
        <MotionStage scene={scene}>
          <div
            style={{
              position: 'absolute',
              inset: 0,
              // Scene-to-scene fades are owned by the transition layer.
              // Keeping the plate opaque prevents declared cuts from
              // collapsing into a near-white disappear/restart interval.
              opacity: 1,
            }}
          >
            <ScenePlate scene={scene} objectFit={portrait ? 'cover' : 'contain'} />
          </div>
        </MotionStage>

        <TextWipe
          text={scene.text}
          startFrame={0}
          durationFrames={at(0.14)}
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

  // Diary (and any non-essay) scenes with code/svg plates skip the bw→color reveal.
  if (nonRaster) {
    const fadeIn = Math.round(total * 0.12);
    const opacity = Math.min(1, Math.max(0, frame / Math.max(1, fadeIn)));
    return (
      <AbsoluteFill style={{backgroundColor: '#FFFFFF', overflow: 'hidden'}}>
        <MotionStage scene={scene}>
          <div style={{position: 'absolute', inset: 0, opacity}}>
            <ScenePlate scene={scene} objectFit="contain" />
          </div>
        </MotionStage>
        <TextWipe
          text={scene.text}
          textAsset={scene.assets.text_image}
          startFrame={0}
          durationFrames={at(speedMode ? 0.22 : 0.16)}
        />
      </AbsoluteFill>
    );
  }

  // A continued visual interval reuses the preceding scene's plate and motion.
  // By this point the first scene has completed its bw→color reveal, so keep
  // the color plate fully visible instead of restarting the reveal on the cut.
  if (scene.visual_interval_start === false) {
    return (
      <AbsoluteFill style={{backgroundColor: '#FFFFFF', overflow: 'hidden'}}>
        <MotionStage scene={scene}>
          <ScenePlate scene={scene} objectFit={portrait ? 'cover' : 'contain'} />
        </MotionStage>
        <TextWipe
          text={scene.text}
          textAsset={scene.assets.text_image}
          startFrame={0}
          durationFrames={at(speedMode ? 0.22 : 0.16)}
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
