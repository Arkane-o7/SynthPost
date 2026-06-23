import React from 'react';
import {thumbnailTheme} from '../theme';

export const BrandMark: React.FC<{accent?: string; compact?: boolean}> = ({accent = thumbnailTheme.colors.synthBlue, compact = false}) => {
  if (compact) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 9,
          width: '100%',
          height: '100%',
          color: thumbnailTheme.colors.deepNavy,
        }}
      >
        <div style={{width: 5, height: 48, borderRadius: 3, background: accent}} />
        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'flex-start', justifyContent: 'center'}}>
          <div
            style={{
              fontFamily: 'Georgia, "Times New Roman", serif',
              fontStyle: 'italic',
              fontSize: 27,
              lineHeight: 0.92,
              color: thumbnailTheme.colors.deepNavy,
            }}
          >
            SP
          </div>
          <div
            style={{
              fontFamily: thumbnailTheme.font.body,
              fontSize: 11,
              fontWeight: 950,
              letterSpacing: 0.7,
              lineHeight: 1,
              color: thumbnailTheme.colors.synthBlue,
              textTransform: 'uppercase',
            }}
          >
            SynthPost
          </div>
        </div>
      </div>
    );
  }
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        fontFamily: thumbnailTheme.font.body,
        color: thumbnailTheme.colors.deepNavy,
        fontWeight: 950,
        fontSize: 24,
        letterSpacing: 0.4,
        width: '100%',
        height: '100%',
      }}
    >
      <div style={{width: compact ? 5 : 6, height: compact ? 44 : 42, borderRadius: 3, background: accent}} />
      <div>
        <div style={{lineHeight: 1}}>SYNTH</div>
        <div style={{lineHeight: 1, color: thumbnailTheme.colors.synthBlue}}>POST</div>
      </div>
    </div>
  );
};
