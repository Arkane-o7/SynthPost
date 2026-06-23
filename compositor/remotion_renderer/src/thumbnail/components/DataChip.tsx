import React from 'react';
import {thumbnailTheme} from '../theme';

export const DataChip: React.FC<{label: string; value: string; accent: string}> = ({label, value, accent}) => {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 12,
        padding: '11px 16px',
        borderRadius: 3,
        background: `${thumbnailTheme.colors.warmWhite}E8`,
        borderLeft: `6px solid ${accent}`,
        boxShadow: '0 14px 36px rgba(0,0,0,0.34)',
        fontFamily: thumbnailTheme.font.body,
        color: thumbnailTheme.colors.deepNavy,
      }}
    >
      <span style={{fontSize: 17, color: thumbnailTheme.colors.deepNavy, fontWeight: 900, textTransform: 'uppercase'}}>{label}</span>
      <span style={{fontSize: 28, color: accent, fontWeight: 950}}>{value}</span>
    </div>
  );
};
