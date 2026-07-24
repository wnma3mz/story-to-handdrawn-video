import {AbsoluteFill, Img, staticFile} from 'remotion';
import {storyboard} from './storyboard';

const InkComicCover: React.FC = () => {
  const cover = storyboard.project.cover || {};
  const firstScene = storyboard.scenes[0];
  const title = cover.title || storyboard.project.title;
  const titleLines = balancedInkTitleLines(title);
  const longestTitleLine = Math.max(
    ...titleLines.map((line) => Array.from(line).length),
    1,
  );
  const titleFontSize =
    longestTitleLine <= 5
      ? 126
      : longestTitleLine === 6
        ? 112
        : Math.max(82, Math.floor(680 / longestTitleLine));
  const background = cover.background || '#171717';
  const accent = cover.accent || '#A93B32';

  return (
    <AbsoluteFill
      style={{
        backgroundColor: background,
        color: '#F4F0E8',
        fontFamily: 'OriginalDiaryHand, Songti SC, STSong, serif',
        overflow: 'hidden',
      }}
    >
      {firstScene.assets.color ? (
        <Img
          src={staticFile(firstScene.assets.color)}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            filter: 'grayscale(0.74) contrast(1.18) brightness(0.67)',
          }}
        />
      ) : null}
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(90deg, rgba(10,10,10,0.96) 0%, rgba(10,10,10,0.76) 43%, rgba(10,10,10,0.16) 78%, rgba(10,10,10,0.5) 100%)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: 110,
          top: 92,
          fontSize: 34,
          letterSpacing: '0.15em',
          color: '#D8D2C8',
        }}
      >
        {cover.series_title || '清明上河图谜案 · 动态漫'}
      </div>
      <div
        style={{
          position: 'absolute',
          left: 108,
          top: 230,
          width: 900,
          borderLeft: `14px solid ${accent}`,
          paddingLeft: 42,
        }}
      >
        <div style={{fontSize: 52, color: '#CFC7B9', marginBottom: 16}}>
          {cover.episode_label || '第五季 · 风篇'}
        </div>
        <div
          style={{
            fontSize: titleFontSize,
            lineHeight: 1.04,
            letterSpacing: '0.035em',
            textShadow: '0 5px 18px rgba(0,0,0,0.86)',
          }}
        >
          {titleLines.map((line, index) => (
            <div key={`${index}-${line}`} style={{whiteSpace: 'nowrap'}}>
              {line}
            </div>
          ))}
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          right: 94,
          bottom: 64,
          width: 116,
          height: 116,
          borderRadius: 12,
          backgroundColor: accent,
          color: '#F7EFE2',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 66,
          boxShadow: '0 8px 24px rgba(0,0,0,0.36)',
          transform: 'rotate(-3deg)',
        }}
      >
        田
      </div>
    </AbsoluteFill>
  );
};

const balancedInkTitleLines = (title: string) => {
  const explicitLines = title
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  if (explicitLines.length > 1) return explicitLines;

  const characters = Array.from(explicitLines[0] || title.trim());
  if (characters.length <= 5) return [characters.join('')];
  const lineCount = characters.length <= 14 ? 2 : 3;
  const lines: string[] = [];
  let offset = 0;
  for (let index = 0; index < lineCount; index += 1) {
    const remainingCharacters = characters.length - offset;
    const remainingLines = lineCount - index;
    const take = Math.ceil(remainingCharacters / remainingLines);
    lines.push(characters.slice(offset, offset + take).join(''));
    offset += take;
  }
  return lines;
};

const splitTitle = (title: string) => {
  const [chapter, ...rest] = title.split('｜');
  return {
    chapter: rest.length > 0 ? chapter : '故事',
    title: rest.join('｜') || title,
  };
};

const balancedTitleLines = (title: string) => {
  const explicitLines = title
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  if (explicitLines.length > 1) return explicitLines;

  const characters = Array.from(explicitLines[0] || title.trim());
  if (characters.length <= 8) return [characters.join('')];

  const lineCount = characters.length <= 18 ? 2 : 3;
  const lines: string[] = [];
  let offset = 0;
  for (let index = 0; index < lineCount; index += 1) {
    const remainingCharacters = characters.length - offset;
    const remainingLines = lineCount - index;
    const take = Math.ceil(remainingCharacters / remainingLines);
    lines.push(characters.slice(offset, offset + take).join(''));
    offset += take;
  }
  return lines;
};

const chineseChapterNumber = (chapter: string): number | null => {
  const value = chapter.match(/第([一二三四五六七八九十]+)章/)?.[1];
  if (!value) return null;
  const digit: Record<string, number> = {
    一: 1,
    二: 2,
    三: 3,
    四: 4,
    五: 5,
    六: 6,
    七: 7,
    八: 8,
    九: 9,
  };
  if (value === '十') return 10;
  if (value.includes('十')) {
    const [tens, ones] = value.split('十');
    return (tens ? digit[tens] : 1) * 10 + (ones ? digit[ones] : 0);
  }
  return digit[value] ?? null;
};

const EssayCover: React.FC = () => {
  const cover = storyboard.project.cover || {};
  const title = cover.title || storyboard.project.title;
  const seriesTitle = cover.series_title || '随笔 · 手绘动画';
  const background = cover.background || '#F4EDE0';
  const accent = cover.accent || '#8B6E4E';
  const titleLines = title
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  const effectiveLines =
    titleLines.length > 0 ? titleLines : balancedTitleLines(title);
  const longestLine = Math.max(
    ...effectiveLines.map((line) => Array.from(line).length),
    1,
  );
  const titleFontSize =
    longestLine <= 6
      ? 98
      : longestLine <= 10
        ? 84
        : Math.max(58, Math.floor(760 / longestLine));

  return (
    <AbsoluteFill
      style={{
        backgroundColor: background,
        color: '#3E3230',
        fontFamily: 'OriginalDiaryHand, Songti SC, STSong, serif',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background:
            'radial-gradient(ellipse 68% 58% at 50% 44%, rgba(255,250,240,0.9) 0%, rgba(232,218,195,0.4) 100%)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          top: 76,
          left: 0,
          right: 0,
          textAlign: 'center',
          fontSize: 28,
          letterSpacing: '0.2em',
          color: accent,
        }}
      >
        {seriesTitle}
      </div>
      <div
        style={{
          position: 'absolute',
          top: 140,
          left: 0,
          right: 0,
          height: 2,
        }}
      >
        <div
          style={{
            margin: '0 auto',
            width: 96,
            height: 2,
            backgroundColor: accent,
            opacity: 0.48,
          }}
        />
      </div>
      <div
        style={{
          position: 'absolute',
          top: 190,
          left: 120,
          right: 120,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            fontSize: titleFontSize,
            lineHeight: 1.22,
            letterSpacing: '0.04em',
            textAlign: 'center',
            color: '#2C2822',
          }}
        >
          {effectiveLines.map((line, index) => (
            <div key={`${index}-${line}`} style={{whiteSpace: 'nowrap'}}>
              {line}
            </div>
          ))}
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          bottom: 82,
          left: 0,
          right: 0,
          textAlign: 'center',
          fontSize: 26,
          letterSpacing: '0.15em',
          color: accent,
          opacity: 0.7,
        }}
      >
        {cover.episode_label || '一篇随笔'}
      </div>
    </AbsoluteFill>
  );
};

export const EpisodeCover: React.FC = () => {
  if (storyboard.project.visual_mode === 'ink-comic') {
    return <InkComicCover />;
  }
  if (storyboard.project.visual_mode === 'essay') {
    return <EssayCover />;
  }
  const parsed = splitTitle(storyboard.project.title);
  const cover = storyboard.project.cover || {};
  const chapter = cover.episode_label || parsed.chapter;
  const title = cover.title || parsed.title;
  const titleLines = balancedTitleLines(title);
  const longestTitleLine = Math.max(...titleLines.map((line) => Array.from(line).length), 1);
  const titleFontSize =
    longestTitleLine <= 8 ? 102 : Math.max(58, Math.floor(800 / longestTitleLine));
  const firstScene = storyboard.scenes[0];
  const episodeNumber = String(
    cover.episode_number ||
      chapter.match(/\d+/)?.[0] ||
      chineseChapterNumber(chapter) ||
      1,
  );
  const colors = {
    background: cover.background || '#5E7468',
    accent: cover.accent || '#D5A95F',
    darkAccent: cover.dark_accent || '#334C52',
    badge: cover.badge || '#C75C45',
    card: cover.card || '#E6CF9E',
    foreground: cover.foreground || '#FFF7E8',
  };

  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.background,
        color: colors.foreground,
        fontFamily: 'OriginalDiaryHand, STKaiti, serif',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          width: 610,
          height: 610,
          borderRadius: '50%',
          backgroundColor: colors.accent,
          right: -245,
          top: -250,
          opacity: 0.88,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: -180,
          bottom: -255,
          width: 760,
          height: 540,
          borderRadius: '48% 52% 42% 58%',
          backgroundColor: colors.darkAccent,
          transform: 'rotate(-9deg)',
        }}
      />

      <div
        style={{
          position: 'absolute',
          top: 94,
          left: 86,
          right: 86,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{fontSize: 39, letterSpacing: '0.08em'}}>
          {cover.series_title || '手绘故事 · 动画'}
        </div>
        <div
          style={{
            width: 112,
            height: 112,
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: colors.badge,
            border: '5px solid #282D29',
            color: colors.foreground,
            fontSize: 48,
            transform: 'rotate(4deg)',
          }}
        >
          {episodeNumber.padStart(2, '0')}
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          top: 230,
          left: 88,
          right: 88,
        }}
      >
        <div style={{fontSize: 54, color: colors.accent, marginBottom: 18}}>
          {chapter}
        </div>
        <div
          style={{
            fontSize: titleFontSize,
            lineHeight: 1.12,
            letterSpacing: '0.025em',
            WebkitTextStroke: `1.1px ${colors.foreground}`,
            textShadow: '4px 5px 0 rgba(31, 43, 37, 0.42)',
          }}
        >
          {titleLines.map((line, index) => (
            <div key={`${index}-${line}`} style={{whiteSpace: 'nowrap'}}>
              {line}
            </div>
          ))}
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          left: 76,
          right: 76,
          bottom: 82,
          height: 640,
          borderRadius: 38,
          backgroundColor: colors.card,
          border: '7px solid #282D29',
          boxShadow: '18px 20px 0 rgba(40, 45, 41, 0.35)',
          overflow: 'hidden',
          transform: 'rotate(-1.4deg)',
        }}
      >
        <Img
          src={staticFile(firstScene.assets.color || '')}
          style={{
            position: 'absolute',
            inset: 24,
            width: 'calc(100% - 48px)',
            height: 'calc(100% - 48px)',
            objectFit: 'contain',
            mixBlendMode: 'multiply',
            filter: 'contrast(1.03) saturate(0.92)',
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
