import React from 'react';
import {thumbnailTheme} from '../theme';

const splitWords = (text: string): string[] => text.trim().split(/\s+/).filter(Boolean);

export const HeadlineBlock: React.FC<{
  text: string;
  accentWords?: string[];
  accent: string;
  maxWidth?: number;
  align?: 'left' | 'right' | 'center';
  size?: number;
}> = ({text, accentWords = [], accent, maxWidth = 650, align = 'left', size = 88}) => {
  const accents = new Set(accentWords.map((word) => word.toUpperCase()));
  const words = splitWords(text.toUpperCase());
  return (
    <div
      style={{
        maxWidth,
        fontFamily: thumbnailTheme.font.headline,
        fontSize: size,
        lineHeight: 0.9,
        letterSpacing: 0,
        color: thumbnailTheme.colors.offWhite,
        textAlign: align,
        textShadow: '0 8px 28px rgba(0,0,0,0.7)',
        textTransform: 'uppercase',
      }}
    >
      {words.map((word, index) => {
        const stripped = word.replace(/[^A-Z0-9$%.]/g, '');
        return (
          <React.Fragment key={`${word}-${index}`}>
            <span style={{color: accents.has(stripped) || accents.has(word) ? accent : thumbnailTheme.colors.offWhite}}>
              {word}
            </span>
            {index < words.length - 1 ? ' ' : null}
          </React.Fragment>
        );
      })}
    </div>
  );
};

