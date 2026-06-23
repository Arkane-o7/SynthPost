import React from 'react';
import {AbsoluteFill, OffthreadVideo} from 'remotion';
import {brand} from '../styles/brand';
import type {PublicMedia} from '../types';
import {mediaSrc} from './media';

type AnchorCrop = {
  scale: number;
  offsetX: number;
  offsetY: number;
  objectPosition: string;
};

export const AnchorVideoLayer: React.FC<{
  anchor?: PublicMedia;
  crop: AnchorCrop;
  style?: React.CSSProperties;
  mediaFilter?: string;
  overlay?: React.CSSProperties['background'];
}> = ({anchor, crop, style, mediaFilter, overlay}) => {
  return (
    <div
      style={{
        position: 'absolute',
        overflow: 'hidden',
        backgroundColor: brand.ink,
        ...style,
      }}
    >
      {anchor ? (
        <AbsoluteFill>
          <OffthreadVideo
            src={mediaSrc(anchor)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              objectPosition: crop.objectPosition,
              transform: `translate(${crop.offsetX}px, ${crop.offsetY}px) scale(${crop.scale})`,
              transformOrigin: 'center top',
              filter: mediaFilter ?? 'saturate(0.9) contrast(1.04) brightness(0.96)',
            }}
          />
        </AbsoluteFill>
      ) : null}
      <AbsoluteFill
        style={{
          background: overlay,
          boxShadow: 'inset 0 0 90px rgba(2, 6, 16, 0.46)',
          pointerEvents: 'none',
        }}
      />
    </div>
  );
};
