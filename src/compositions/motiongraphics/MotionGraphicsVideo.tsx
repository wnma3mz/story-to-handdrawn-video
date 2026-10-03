import {AbsoluteFill, Sequence, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {CameraStage, motionInsetPx} from './CameraStage';
import {MOTIF_BACKGROUND, Motif} from './Motif';
import type {SceneData, Storyboard} from '../../types';

// 竖屏下的字幕带与顶部信息条，按 1080 宽等比换算到其他画幅。
const SUBS_BAND_RATIO = 0.14;
const TOP_BAR_RATIO = 0.08;

const safeArea = (width: number, height: number) => ({
  top: Math.round(height * TOP_BAR_RATIO),
  bottom: Math.round(height * SUBS_BAND_RATIO),
  left: Math.round(width * 0.06),
  right: Math.round(width * 0.06),
});

/** 字幕：台词逐字显示，与 handdrawn 的 ink-comic 字幕遵守同一份台词锁。 */
const Subtitle: React.FC<{text: string; bottom: number; width: number}> = ({text, bottom, width}) => {
  if (!text) {
    return null;
  }
  return (
    <div
      style={{
        position: 'absolute',
        left: Math.round(width * 0.08),
        right: Math.round(width * 0.08),
        bottom: Math.round(bottom * 0.4),
        textAlign: 'center',
        fontFamily: 'OriginalDiaryHand, Songti SC, serif',
        fontSize: Math.round(width * 0.052),
        lineHeight: 1.45,
        color: '#2b2b2b',
        textShadow: '0 1px 0 #fdfbf6',
      }}
    >
      {text}
    </div>
  );
};

const SceneLayer: React.FC<{scene: SceneData}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const box = safeArea(width, height);

  const inset = motionInsetPx(width - box.left - box.right, height - box.top - box.bottom);
  const motif = scene.mg_plate?.motif ?? 'empty';
  const opacity = interpolate(frame, [0, 5], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{backgroundColor: MOTIF_BACKGROUND, opacity}}>
      <CameraStage
        motion={scene.motion}
        focus={scene.focus}
        durationSec={scene.duration_sec}
        intervalStart={scene.visual_interval_progress_start}
        intervalEnd={scene.visual_interval_progress_end}
        safeArea={box}
      >
        <Motif
          motif={motif}
          width={width - box.left - box.right - inset.x * 2}
          height={height - box.top - box.bottom - inset.y * 2}
          seed={scene.mg_plate?.seed ?? (Number(scene.id) || 1)}
          headline={scene.mg_plate?.headline ?? scene.shot ?? ''}
          detail={scene.mg_plate?.detail}
        />
      </CameraStage>
      <Subtitle text={scene.text ?? ''} bottom={box.bottom} width={width} />
    </AbsoluteFill>
  );
};

/**
 * 纯代码绘制的成片：不经过出图环节，直接由分镜 + 程序化图元渲染。
 * 与 handdrawn composition 读同一份 storyboard.json，区别只在画面来源。
 */
export const MotionGraphicsVideo: React.FC<{value: Storyboard}> = ({value}) => {
  const {fps} = useVideoConfig();
  let cursor = 0;

  return (
    <AbsoluteFill style={{backgroundColor: MOTIF_BACKGROUND}}>
      {value.scenes.map((scene) => {
        const durationInFrames = Math.round(scene.duration_sec * fps);
        const from = cursor;
        cursor += durationInFrames;
        return (
          <Sequence
            key={scene.id}
            from={from}
            durationInFrames={durationInFrames}
            name={`MG ${scene.id}`}
          >
            <SceneLayer scene={scene} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
