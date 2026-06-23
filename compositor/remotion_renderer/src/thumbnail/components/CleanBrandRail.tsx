import React from 'react';
import {thumbnailTheme} from '../theme';

export const CLEAN_RAIL_WIDTH = 205;

export const CleanBrandRail: React.FC = () => {
  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        bottom: 0,
        width: CLEAN_RAIL_WIDTH,
        background:
          'linear-gradient(180deg, #3F63FF 0%, #6F89FF 30%, rgba(244,239,231,0.88) 83%, rgba(244,239,231,0.72) 100%)',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'radial-gradient(circle at 12% 10%, rgba(255,255,255,0.28), transparent 24%), linear-gradient(90deg, rgba(255,255,255,0.18), transparent 62%)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: 24,
          top: 78,
          right: 24,
          textAlign: 'center',
          color: thumbnailTheme.colors.offWhite,
          fontFamily: thumbnailTheme.font.body,
          fontSize: 18,
          fontWeight: 500,
          letterSpacing: 5.6,
          textTransform: 'uppercase',
          textShadow: '0 4px 18px rgba(0,0,0,0.18)',
        }}
      >
        SYNTHPOST
      </div>
      <div
        style={{
          position: 'absolute',
          left: 84,
          top: 116,
          width: 48,
          height: 2,
          background: thumbnailTheme.colors.offWhite,
          opacity: 0.92,
        }}
      />
    </div>
  );
};
