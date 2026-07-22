import {AbsoluteFill, Img, staticFile} from 'remotion';
import {storyboard} from './storyboard';

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

export const EpisodeCover: React.FC = () => {
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
