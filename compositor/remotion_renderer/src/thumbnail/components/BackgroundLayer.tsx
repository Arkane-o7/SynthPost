import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import type {ThumbnailAsset, ThumbnailEmotion} from '../types';
import {assetSrc} from '../layout';
import {accentForEmotion, thumbnailTheme} from '../theme';

export const BackgroundLayer: React.FC<{asset?: ThumbnailAsset; emotion: ThumbnailEmotion}> = ({asset, emotion}) => {
  const src = assetSrc(asset);
  const accent = accentForEmotion(emotion);
  return (
    <AbsoluteFill style={{background: thumbnailTheme.colors.obsidian, overflow: 'hidden'}}>
      {src ? (
        <Img
          src={src}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            filter: 'saturate(1.12) contrast(1.1) brightness(0.82)',
            transform: 'scale(1.025)',
          }}
        />
      ) : (
        <div
          style={{
            width: '100%',
            height: '100%',
            background: `radial-gradient(circle at 70% 35%, ${accent}55 0, transparent 34%), linear-gradient(135deg, #070A0F 0%, #111827 54%, #020617 100%)`,
          }}
        />
      )}
      <Img
        src={staticFile('brand/synthpost-gradient-landscape.png')}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          opacity: 0.42,
          mixBlendMode: 'soft-light',
        }}
      />
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(90deg, rgba(228,212,198,0.22) 0%, rgba(0,106,166,0.16) 34%, rgba(0,12,30,0.76) 100%), linear-gradient(180deg, rgba(0,12,30,0.04), rgba(0,12,30,0.48))',
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.22,
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.08) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
          maskImage: 'linear-gradient(90deg, black, transparent 82%)',
        }}
      />
    </AbsoluteFill>
  );
};
