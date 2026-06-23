import React from 'react';
import {BrandMark} from './BrandMark';
import {thumbnailTheme} from '../theme';

const wordsFor = (text: string): string[] => text.trim().toUpperCase().split(/\s+/).filter(Boolean);

export const TopHeadlineBar: React.FC<{
  text: string;
  accentWords?: string[];
  accent?: string;
}> = ({text, accentWords = [], accent = thumbnailTheme.colors.synthBlue}) => {
  const words = wordsFor(text);
  const accents = new Set(accentWords.map((word) => word.toUpperCase().replace(/[^A-Z0-9$%.]/g, '')));
  const fontSize = text.length > 35 ? 56 : text.length > 27 ? 64 : 72;

  return (
    <div
      style={{
        position: 'absolute',
        left: thumbnailTheme.borderWidth,
        top: thumbnailTheme.borderWidth,
        right: thumbnailTheme.borderWidth,
        height: thumbnailTheme.headerHeight - thumbnailTheme.borderWidth,
        display: 'flex',
        background: `linear-gradient(90deg, ${thumbnailTheme.colors.cream} 0%, ${thumbnailTheme.colors.warmWhite} 18%, #FFFFFF 100%)`,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: 150,
          height: '100%',
          flex: '0 0 auto',
          background: `linear-gradient(135deg, ${thumbnailTheme.colors.cream}, #F9F3E8)`,
          borderRight: `2px solid ${thumbnailTheme.colors.deepNavy}`,
        }}
      >
        <BrandMark accent={accent} compact />
      </div>
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          padding: '0 30px',
          fontFamily: thumbnailTheme.font.headline,
          fontSize,
          lineHeight: 0.96,
          letterSpacing: -0.5,
          color: thumbnailTheme.colors.headlineInk,
          whiteSpace: 'nowrap',
          textTransform: 'uppercase',
        }}
      >
        {words.map((word, index) => {
          const stripped = word.replace(/[^A-Z0-9$%.]/g, '');
          return (
            <span key={`${word}-${index}`} style={{color: accents.has(stripped) || accents.has(word) ? accent : thumbnailTheme.colors.headlineInk}}>
              {word}
            </span>
          );
        })}
      </div>
    </div>
  );
};

export const CONTENT_TOP = thumbnailTheme.headerHeight + thumbnailTheme.borderWidth;
export const CONTENT_HEIGHT = thumbnailTheme.height - CONTENT_TOP - thumbnailTheme.borderWidth;
