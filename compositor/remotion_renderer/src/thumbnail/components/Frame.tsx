import React from 'react';
import {thumbnailTheme} from '../theme';

export const Frame: React.FC<{accent: string}> = ({accent}) => {
  return (
    <>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          border: `${thumbnailTheme.borderWidth}px solid ${thumbnailTheme.colors.cream}`,
          boxShadow: 'inset 0 0 0 1px rgba(0, 12, 30, 0.38)',
        }}
      />
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 5, background: accent}} />
      <div
        style={{
          position: 'absolute',
          left: thumbnailTheme.borderWidth,
          right: thumbnailTheme.borderWidth,
          top: thumbnailTheme.headerHeight - 1,
          height: 2,
          background: thumbnailTheme.colors.deepNavy,
          opacity: 0.9,
        }}
      />
    </>
  );
};
