import type {CSSProperties} from 'react';
import {Img, staticFile, useCurrentFrame} from 'remotion';
import {revealProgress} from './easing';

type TextWipeVariant = 'diary' | 'essay';

type TextWipeProps = {
  text: string;
  textAsset?: string | null;
  startFrame: number;
  durationFrames: number;
  variant?: TextWipeVariant;
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

const fallbackFontSize = (text: string, variant: TextWipeVariant = 'diary') => {
  const lines = text.split('\n').filter(Boolean);
  const lineCount = Math.max(1, lines.length);
  const longestLine = Math.max(...lines.map((line) => line.length), 1);
  if (variant === 'essay') {
    const widthLimited = Math.floor(870 / (longestLine * 1.12));
    const heightLimited = Math.floor(560 / (lineCount * 1.36));
    return Math.max(52, Math.min(96, widthLimited, heightLimited));
  }
  const widthLimited = Math.floor(850 / (longestLine * 1.08));
  const heightLimited = Math.floor(306 / (lineCount * 1.28));
  return Math.max(48, Math.min(82, widthLimited, heightLimited));
};

export const TextWipe: React.FC<TextWipeProps> = ({
  text,
  textAsset,
  startFrame,
  durationFrames,
  variant = 'diary',
}) => {
  const frame = useCurrentFrame();
  const progress = revealProgress(frame, startFrame, durationFrames);
  const fontSize = fallbackFontSize(text, variant);

  if (variant === 'essay') {
    return (
      <div
        style={{
          position: 'absolute',
          zIndex: 40,
          top: 84,
          left: 120,
          right: 106,
          bottom: 420,
          display: 'flex',
          alignItems: 'flex-start',
          clipPath: `inset(0 0 ${(1 - progress) * 100}% 0)`,
        }}
      >
        <p
          style={{
            ...textStyle(fontSize),
            maxWidth: 840,
            lineHeight: 1.48,
            letterSpacing: '0.03em',
          }}
        >
          {text}
        </p>
      </div>
    );
  }

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
