import {
  AbsoluteFill,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {MotionStage} from './MotionStage';
import type {SceneData} from './types';

const safeAccent = (scene: SceneData) => scene.accent || '#A93B32';

const sceneTreatment = (kind: SceneData['scene_kind']) => {
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

export const InkComicScene: React.FC<{scene: SceneData}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const totalFrames = Math.max(1, Math.round(scene.duration_sec * fps));
  const fadeIn = scene.visual_interval_start === false
    ? 1
    : interpolate(frame, [0, Math.min(8, totalFrames * 0.12)], [0, 1], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      });
  // Verbatim subtitles are timing evidence, not decorative cards.  They must
  // appear on the first frame of the machine scene that starts the TTS cue.
  const captionIn = 1;
  const accent = safeAccent(scene);
  const plate = scene.assets.color || scene.assets.bw;
  const subtitleLength = [...scene.text.replace(/\s/g, '')].length;
  const subtitleFontSize = subtitleLength > 60 ? 32 : subtitleLength > 46 ? 35 : subtitleLength > 32 ? 38 : 42;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#171717',
        overflow: 'hidden',
        fontFamily: 'OriginalDiaryHand, Songti SC, STSong, serif',
      }}
    >
      {scene.glyph ? (
        <div
          style={{
            position: 'absolute',
            zIndex: 2,
            right: 86,
            top: -116,
            color: '#DED9CE',
            fontSize: 590,
            lineHeight: 1,
            opacity: 0.09,
            transform: 'rotate(-4deg)',
            whiteSpace: 'nowrap',
          }}
        >
          {scene.glyph}
        </div>
      ) : null}

      {plate ? (
        <MotionStage scene={scene}>
          <Img
            src={staticFile(plate)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              objectPosition: 'center center',
              filter: sceneTreatment(scene.scene_kind),
              opacity: fadeIn,
            }}
          />
        </MotionStage>
      ) : null}

      <AbsoluteFill
        style={{
          zIndex: 25,
          background:
            'linear-gradient(180deg, rgba(12,12,12,0.04) 48%, rgba(12,12,12,0.84) 100%)',
          pointerEvents: 'none',
        }}
      />

      {scene.case_label ? (
        <div
          style={{
            position: 'absolute',
            zIndex: 32,
            left: 56,
            top: 48,
            color: '#F3EEE4',
            fontSize: 35,
            letterSpacing: '0.12em',
            textShadow: '0 2px 8px rgba(0,0,0,0.85)',
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <span
            style={{
              display: 'inline-block',
              width: 10,
              height: 38,
              backgroundColor: accent,
              boxShadow: `0 0 18px ${accent}66`,
            }}
          />
          {scene.case_label}
        </div>
      ) : null}

      {scene.text ? (
        <div
          style={{
            position: 'absolute',
            zIndex: 40,
            left: 92,
            right: 92,
            bottom: 38,
            display: 'flex',
            justifyContent: 'center',
            opacity: captionIn,
          }}
        >
          <div
            style={{
              maxWidth: 1620,
              padding: '11px 30px 14px',
              color: '#F8F5EE',
              backgroundColor: 'rgba(10,10,10,0.7)',
              borderBottom: `4px solid ${accent}`,
              fontFamily: 'Songti SC, STSong, serif',
              fontSize: subtitleFontSize,
              lineHeight: 1.26,
              letterSpacing: '0.025em',
              textAlign: 'center',
              whiteSpace: 'pre-line',
              textShadow: '0 2px 5px rgba(0,0,0,0.9)',
              boxShadow: '0 8px 30px rgba(0,0,0,0.28)',
            }}
          >
            {scene.text}
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
