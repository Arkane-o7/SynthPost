import React from 'react';
import {Img} from 'remotion';
import {assetSrc, initialsFor} from '../layout';
import {thumbnailTheme} from '../theme';
import type {ThumbnailAsset, ThumbnailSubject} from '../types';

export const SubjectCard: React.FC<{
  subject?: ThumbnailSubject;
  asset?: ThumbnailAsset;
  accent: string;
  width: number;
  height: number;
  imageFit?: 'cover' | 'contain';
}> = ({subject, asset, accent, width, height, imageFit = 'cover'}) => {
  const src = assetSrc(asset);
  return (
    <div
      style={{
        width,
        height,
        borderRadius: 28,
        overflow: 'hidden',
        background: `linear-gradient(135deg, rgba(24,212,255,0.14), rgba(248,250,252,0.06))`,
        border: '1px solid rgba(248,250,252,0.18)',
        boxShadow: `0 22px 70px rgba(0,0,0,0.52), 0 0 54px ${accent}33`,
        position: 'relative',
      }}
    >
      {src ? (
        <Img
          src={src}
          style={{
            width: '100%',
            height: '100%',
            objectFit: imageFit,
            filter: 'saturate(1.02) contrast(1.04)',
          }}
        />
      ) : (
        <div
          style={{
            width: '100%',
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: thumbnailTheme.font.body,
            color: thumbnailTheme.colors.offWhite,
            textAlign: 'center',
            padding: 28,
          }}
        >
          <div
            style={{
              fontFamily: thumbnailTheme.font.headline,
              fontSize: 112,
              lineHeight: 1,
              color: accent,
              textShadow: `0 0 42px ${accent}66`,
            }}
          >
            {initialsFor(subject)}
          </div>
          <div style={{fontSize: 30, fontWeight: 800, marginTop: 16, lineHeight: 1.05}}>{subject?.name || 'SynthPost'}</div>
          {subject?.role ? <div style={{fontSize: 20, color: thumbnailTheme.colors.muted, marginTop: 8}}>{subject.role}</div> : null}
        </div>
      )}
      <div style={{position: 'absolute', inset: 0, boxShadow: 'inset 0 -90px 110px rgba(0,0,0,0.28)'}} />
    </div>
  );
};

