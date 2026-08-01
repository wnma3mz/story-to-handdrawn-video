import {AbsoluteFill, useVideoConfig} from 'remotion';
import {MotionStage} from './MotionStage';
import {
  inkComicBottomGradient,
  inkComicSceneFilter,
  inkComicSubtitleBackground,
} from './inkComicColorGrade';
import {resolvePlateMode, sceneHasIllustrationPlate} from './plateMode';
import {ScenePlate} from './ScenePlate';
import type {SceneData} from './types';

const safeAccent = (scene: SceneData) => scene.accent || '#A93B32';

export const InkComicScene: React.FC<{scene: SceneData}> = ({scene}) => {
  const {width, height} = useVideoConfig();
  const portrait = height > width;
  // Verbatim subtitles are timing evidence, not decorative cards.  They must
  // appear on the first frame of the machine scene that starts the TTS cue.
  const captionIn = 1;
  const accent = safeAccent(scene);
  const hasPlate = sceneHasIllustrationPlate(scene);
  const plateMode = resolvePlateMode(scene);
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
            right: portrait ? 38 : 86,
            top: portrait ? -48 : -116,
            color: '#DED9CE',
            fontSize: portrait ? 430 : 590,
            lineHeight: 1,
            opacity: 0.09,
            transform: 'rotate(-4deg)',
            whiteSpace: 'nowrap',
          }}
        >
          {scene.glyph}
        </div>
      ) : null}

      {portrait ? (
        <div
          style={{
            position: 'absolute',
            zIndex: 3,
            left: 34,
            right: 34,
            top: 146,
            bottom: 450,
            backgroundColor: '#222220',
            border: `3px solid ${accent}99`,
            boxShadow: '0 18px 48px rgba(0,0,0,0.36)',
          }}
        />
      ) : null}

      {hasPlate ? (
        <MotionStage scene={scene}>
          <div
            style={{
              position: 'absolute',
              inset: 0,
              filter:
                plateMode === 'raster'
                  ? inkComicSceneFilter(scene.color_grade, scene.scene_kind)
                  : undefined,
              // SceneTransitionStoryVideo owns cuts and fades. Keeping the
              // plate opaque prevents a second scene-local fade from creating
              // a black flash on every machine-scene boundary.
              opacity: 1,
            }}
          >
            <ScenePlate
              scene={scene}
              monochrome
              objectFit={
                plateMode !== 'raster' ? 'contain' : 'cover'
              }
            />
          </div>
        </MotionStage>
      ) : null}

      <AbsoluteFill
        style={{
          zIndex: 25,
          background: inkComicBottomGradient(scene.color_grade, portrait),
          pointerEvents: 'none',
        }}
      />

      {scene.case_label ? (
        <div
          style={{
            position: 'absolute',
            zIndex: 32,
            left: portrait ? 48 : 56,
            top: portrait ? 62 : 48,
            color: '#F3EEE4',
            fontSize: portrait ? 31 : 35,
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
            left: portrait ? 58 : 92,
            right: portrait ? 58 : 92,
            bottom: portrait ? 56 : 38,
            display: 'flex',
            justifyContent: 'center',
            opacity: captionIn,
          }}
        >
          <div
            style={{
              maxWidth: portrait ? 940 : 1620,
              padding: portrait ? '20px 30px 24px' : '11px 30px 14px',
              color: '#F8F5EE',
              backgroundColor: inkComicSubtitleBackground(
                scene.color_grade,
                portrait,
              ),
              borderBottom: `4px solid ${accent}`,
              // Songti is preferred locally; the bundled font prevents tofu
              // glyphs in minimal Linux/Chromium render containers.
              fontFamily: 'Songti SC, STSong, OriginalDiaryHand, serif',
              fontSize: portrait
                ? Math.min(44, subtitleFontSize + 2)
                : subtitleFontSize,
              lineHeight: portrait ? 1.38 : 1.26,
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
