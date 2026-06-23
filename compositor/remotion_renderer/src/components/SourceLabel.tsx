import React from 'react';
import {brand, typography} from '../styles/brand';

export const SourceLabel: React.FC<{label: string; date: string; left?: number; bottom?: number}> = ({
  label,
  date,
  left = 44,
  bottom = 38,
}) => {
  return (
    <div
      style={{
        position: 'absolute',
        left,
        bottom,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        color: brand.white,
        fontFamily: typography.serif,
        textTransform: 'uppercase',
        textShadow: '0 2px 18px rgba(0,0,0,0.62)',
      }}
    >
      <div style={{fontSize: 34, lineHeight: 1, letterSpacing: 0}}>{label || 'SYNTHPOST'}</div>
      <div
        style={{
          width: 164,
          height: 3,
          background: `linear-gradient(90deg, ${brand.signalBlue}, rgba(31,123,255,0.12))`,
          boxShadow: `0 0 18px ${brand.signalBlue}`,
        }}
      />
      <div style={{fontSize: 30, lineHeight: 1, letterSpacing: 0}}>{date}</div>
    </div>
  );
};
