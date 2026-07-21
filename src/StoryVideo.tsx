import {
  AbsoluteFill,
  Sequence,
  Series,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {revealProgress} from './easing';
import {Scene} from './Scene';
import {storyboard, transitionFramesFor} from './storyboard';
import type {SceneData, Storyboard} from './types';

const PageFlipScene: React.FC<{
  scene: SceneData;
  durationInFrames: number;
  transitionFrames: number;
  isLast: boolean;
}> = ({scene, durationInFrames, transitionFrames, isLast}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const flipProgress = isLast
    ? 0
    : revealProgress(
        frame,
        durationInFrames - transitionFrames,
        transitionFrames,
      );
  const bottomProgress = Math.min(1, flipProgress / 0.78);
  const topProgress = Math.max(0, (flipProgress - 0.28) / 0.72);
  const xTop = width * (1 - topProgress);
  const xBottom = width * (1 - bottomProgress);
  const curlStrength = Math.sin(flipProgress * Math.PI);
  const bow = width * 0.19 * curlStrength;
  const controlTopX = Math.min(width, xTop + bow);
  const controlBottomX = Math.min(width, xBottom + bow * 0.78);
  const foldWidth = 24 + width * 0.2 * curlStrength;
  const outerTop = Math.min(width, xTop + foldWidth);
  const outerBottom = Math.min(width, xBottom + foldWidth * 0.72);
  const outerControlTop = Math.min(width, controlTopX + foldWidth * 0.78);
  const outerControlBottom = Math.min(
    width,
    controlBottomX + foldWidth * 0.58,
  );
  const clipId = `page-front-${scene.id}`;
  const foldClipId = `page-fold-${scene.id}`;
  const foldGradientId = `page-fold-gradient-${scene.id}`;
  const foldShadowId = `page-fold-shadow-${scene.id}`;
  const frontPath = [
    `M 0 0 H ${xTop}`,
    `C ${controlTopX} ${height * 0.31} ${controlBottomX} ${height * 0.7} ${xBottom} ${height}`,
    `H 0 Z`,
  ].join(' ');
  const foldPath = [
    `M ${xTop} 0`,
    `C ${controlTopX} ${height * 0.31} ${controlBottomX} ${height * 0.7} ${xBottom} ${height}`,
    `L ${outerBottom} ${height}`,
    `C ${outerControlBottom} ${height * 0.7} ${outerControlTop} ${height * 0.31} ${outerTop} 0`,
    'Z',
  ].join(' ');
  const foldLine = [
    `M ${xTop} 0`,
    `C ${controlTopX} ${height * 0.31} ${controlBottomX} ${height * 0.7} ${xBottom} ${height}`,
  ].join(' ');

  return (
    <AbsoluteFill style={{backgroundColor: '#fff', overflow: 'hidden'}}>
      <svg
        width="0"
        height="0"
        style={{position: 'absolute'}}
        aria-hidden="true"
      >
        <defs>
          <clipPath id={clipId} clipPathUnits="userSpaceOnUse">
            <path d={frontPath} />
          </clipPath>
          <clipPath id={foldClipId} clipPathUnits="userSpaceOnUse">
            <path d={foldPath} />
          </clipPath>
        </defs>
      </svg>
      <AbsoluteFill
        style={{
          clipPath: `url(#${clipId})`,
          overflow: 'hidden',
          backgroundColor: '#fff',
        }}
      >
        <Scene scene={scene} />
      </AbsoluteFill>
      {!isLast && flipProgress > 0 ? (
        <AbsoluteFill
          style={{
            clipPath: `url(#${foldClipId})`,
            overflow: 'hidden',
            transformOrigin: `${(xTop + xBottom) / 2}px center`,
            transform: `translateX(${foldWidth * 0.12}px) scaleX(${1 - curlStrength * 0.04})`,
            filter: `brightness(${1.07 + curlStrength * 0.08}) saturate(${0.62 - curlStrength * 0.12})`,
            opacity: 0.3 + curlStrength * 0.32,
          }}
        >
          <Scene scene={scene} />
        </AbsoluteFill>
      ) : null}
      {!isLast && flipProgress > 0 ? (
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}
          aria-hidden="true"
        >
          <defs>
            <linearGradient
              id={foldGradientId}
              x1="0%"
              y1="0%"
              x2="100%"
              y2="0%"
            >
              <stop offset="0%" stopColor="#d5cfc4" stopOpacity="0.94" />
              <stop offset="28%" stopColor="#f3efe7" stopOpacity="0.98" />
              <stop offset="62%" stopColor="#fffef9" stopOpacity="1" />
              <stop offset="100%" stopColor="#d8d0c3" stopOpacity="0.88" />
            </linearGradient>
            <filter
              id={foldShadowId}
              x="-40%"
              y="-10%"
              width="180%"
              height="120%"
            >
              <feDropShadow
                dx={12 + curlStrength * 20}
                dy="3"
                stdDeviation={10 + curlStrength * 15}
                floodColor="#302b25"
                floodOpacity={0.2 + curlStrength * 0.18}
              />
            </filter>
          </defs>
          <path
            d={foldLine}
            fill="none"
            stroke="#302b25"
            strokeWidth={18 + curlStrength * 34}
            opacity={0.04 + curlStrength * 0.08}
            filter={`url(#${foldShadowId})`}
          />
          <path
            d={foldPath}
            fill={`url(#${foldGradientId})`}
            filter={`url(#${foldShadowId})`}
            opacity={0.3 + curlStrength * 0.32}
          />
          <path
            d={foldLine}
            fill="none"
            stroke="#b7ada0"
            strokeWidth={2 + curlStrength * 2.5}
            opacity={0.55 + curlStrength * 0.28}
          />
          <path
            d={foldLine}
            fill="none"
            stroke="#ffffff"
            strokeWidth={1.2 + curlStrength * 1.4}
            transform={`translate(${Math.max(1, foldWidth * 0.1)} 0)`}
            opacity={0.7}
          />
        </svg>
      ) : null}
    </AbsoluteFill>
  );
};

const CutStoryVideo: React.FC<{value: Storyboard}> = ({value}) => (
  <Series>
    {value.scenes.map((scene) => (
      <Series.Sequence
        key={scene.id}
        durationInFrames={Math.round(
          scene.duration_sec * value.project.fps,
        )}
        name={`Scene ${scene.id}`}
      >
        <Scene scene={scene} />
      </Series.Sequence>
    ))}
  </Series>
);

const PageFlipStoryVideo: React.FC<{value: Storyboard}> = ({value}) => {
  const transitionFrames = transitionFramesFor(value);
  let from = 0;

  return (
    <AbsoluteFill style={{backgroundColor: '#fff'}}>
      {value.scenes.map((scene, index) => {
        const durationInFrames = Math.round(
          scene.duration_sec * value.project.fps,
        );
        const sceneFrom = from;
        from += durationInFrames -
          (index < value.scenes.length - 1 ? transitionFrames : 0);

        return (
          <Sequence
            key={scene.id}
            from={sceneFrom}
            durationInFrames={durationInFrames}
            name={`Page ${scene.id}`}
            style={{zIndex: value.scenes.length - index}}
          >
            <PageFlipScene
              scene={scene}
              durationInFrames={durationInFrames}
              transitionFrames={transitionFrames}
              isLast={index === value.scenes.length - 1}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export const StoryboardVideo: React.FC<{value: Storyboard}> = ({value}) =>
  value.project.transition === 'page-flip' && value.scenes.length > 1 ? (
    <PageFlipStoryVideo value={value} />
  ) : (
    <CutStoryVideo value={value} />
  );

export const StoryVideo: React.FC = () => <StoryboardVideo value={storyboard} />;
