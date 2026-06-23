import React from 'react';
import {Img} from 'remotion';
import {assetSrc, initialsFor} from '../layout';
import {thumbnailTheme} from '../theme';
import type {ThumbnailAsset, ThumbnailSubject} from '../types';

export const LogoCard: React.FC<{
  asset?: ThumbnailAsset;
  subject?: ThumbnailSubject;
  accent: string;
  width?: number;
  height?: number;
}> = ({asset, subject, accent, width = 310, height = 190}) => {
  const src = assetSrc(asset);
  const label = subject?.name || initialsFor(subject);
  const fontSize = label.length > 18 ? 30 : label.length > 11 ? 36 : label.length > 8 ? 38 : 58;
  return (
    <div
      style={{
        width,
        height,
        borderRadius: 28,
        background: 'rgba(248,250,252,0.94)',
        border: '1px solid rgba(255,255,255,0.35)',
        boxShadow: `0 20px 60px rgba(0,0,0,0.42), 0 0 50px ${accent}22`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        padding: 28,
      }}
    >
      {src ? (
        <Img src={src} style={{maxWidth: '100%', maxHeight: '100%', objectFit: 'contain'}} />
      ) : (
        <div
          style={{
            fontFamily: thumbnailTheme.font.headline,
            fontSize,
            lineHeight: 0.95,
            textAlign: 'center',
            color: thumbnailTheme.colors.graphite,
            textTransform: 'uppercase',
            wordBreak: label.includes(' ') ? 'normal' : 'keep-all',
            overflowWrap: label.includes(' ') ? 'normal' : 'normal',
            maxWidth: '100%',
          }}
        >
          {label}
        </div>
      )}
    </div>
  );
};
