import React from 'react';
import {Img} from 'remotion';
import {assetSrc, initialsFor} from '../layout';
import {thumbnailTheme} from '../theme';
import type {ThumbnailAsset, ThumbnailSubject} from '../types';

export const HeroSubject: React.FC<{
  subject?: ThumbnailSubject;
  asset?: ThumbnailAsset;
  accent: string;
  width: number;
  height: number;
}> = ({subject, asset, accent, width, height}) => {
  const src = assetSrc(asset);
  if (src) {
    return (
      <div style={{width, height, position: 'relative'}}>
        <Img
          src={src}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            objectPosition: 'center top',
            filter: 'saturate(1.03) contrast(1.05)',
            borderRadius: 3,
            boxShadow: '0 18px 60px rgba(0,0,0,0.45)',
          }}
        />
      </div>
    );
  }

  return (
    <div
      style={{
        width,
        height,
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          position: 'absolute',
          width: Math.min(width, height) * 1.04,
          height: Math.min(width, height) * 1.04,
          borderRadius: '50%',
          background: `radial-gradient(circle at 50% 36%, rgba(244,239,231,0.88), rgba(0,106,166,0.45) 45%, rgba(0,12,30,0.02) 72%)`,
          boxShadow: `0 0 96px ${accent}44, inset 0 0 70px rgba(255,255,255,0.18)`,
          opacity: 0.92,
        }}
      />
      <div
        style={{
          position: 'relative',
          fontFamily: thumbnailTheme.font.headline,
          fontSize: Math.min(width, height) * 0.4,
          lineHeight: 0.9,
          color: thumbnailTheme.colors.warmWhite,
          textShadow: `0 0 42px ${accent}88, 0 12px 34px rgba(0,0,0,0.72)`,
        }}
      >
        {initialsFor(subject)}
      </div>
      <div
        style={{
          position: 'absolute',
          bottom: 34,
          left: 20,
          right: 20,
          textAlign: 'center',
          fontFamily: thumbnailTheme.font.body,
          color: thumbnailTheme.colors.cream,
          textShadow: '0 6px 22px rgba(0,0,0,0.8)',
        }}
      >
        <div style={{fontSize: 30, fontWeight: 950}}>{subject?.name || 'SynthPost'}</div>
        {subject?.role ? <div style={{fontSize: 20, opacity: 0.9, marginTop: 6}}>{subject.role}</div> : null}
      </div>
    </div>
  );
};
