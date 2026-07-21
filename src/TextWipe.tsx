import type {CSSProperties} from 'react';
import {Img, staticFile, useCurrentFrame} from 'remotion';
import {revealProgress} from './easing';

type TextWipeProps = {
  text: string;
  textAsset?: string | null;
  startFrame: number;
  durationFrames: number;
};

const textStyle = (fontSize: number): CSSProperties => ({
  fontFamily: 'OriginalDiaryHand, STKaiti, serif',
  fontSize,
  fontWeight: 400,
  lineHeight: 1.34,
  letterSpacing: '0.025em',
  color: '#171714',
  WebkitTextStroke: '0.7px #171714',
  margin: 0,
  maxWidth: 852,
  textAlign: 'left',
  whiteSpace: 'pre-line',
  transform: 'rotate(-0.35deg)',
});

const fallbackFontSize = (text: string) => {
  const lines = text.split('\n').filter(Boolean);
  const lineCount = Math.max(1, lines.length);
  const longestLine = Math.max(...lines.map((line) => line.length), 1);
  const widthLimited = Math.floor(850 / (longestLine * 1.08));
  const heightLimited = Math.floor(306 / (lineCount * 1.28));
  return Math.max(48, Math.min(82, widthLimited, heightLimited));
};

export const TextWipe: React.FC<TextWipeProps> = ({
  text,
  textAsset,
  startFrame,
  durationFrames,
}) => {
  const frame = useCurrentFrame();
  const progress = revealProgress(frame, startFrame, durationFrames);
  const fontSize = fallbackFontSize(text);

  if (textAsset) {
    return (
      <div
        style={{
          position: 'absolute',
          zIndex: 40,
          top: 86,
          left: 96,
          width: 888,
          height: 288,
          clipPath: `inset(0 ${100 - progress * 100}% 0 0)`,
          overflow: 'hidden',
        }}
      >
        <Img
          src={staticFile(textAsset)}
          style={{
            display: 'block',
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            objectPosition: 'left top',
            filter: 'brightness(1.025) contrast(1.035)',
          }}
        />
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'absolute',
        zIndex: 40,
        top: 92,
        left: 104,
        right: 96,
        display: 'flex',
        justifyContent: 'flex-start',
        clipPath: `inset(0 ${100 - progress * 100}% 0 0)`,
      }}
    >
      <p style={textStyle(fontSize)}>{text}</p>
    </div>
  );
};
