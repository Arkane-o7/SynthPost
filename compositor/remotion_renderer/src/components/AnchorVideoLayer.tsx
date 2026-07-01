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

const chromaKeyFilterId = 'synthpost-anchor-chroma-key';
const defaultAnchorFilter = 'saturate(0.9) contrast(1.04) brightness(0.96)';

const ChromaKeyFilter: React.FC = () => (
  <svg width="0" height="0" style={{position: 'absolute'}} aria-hidden="true">
    <defs>
      <filter id={chromaKeyFilterId} colorInterpolationFilters="sRGB">
        <feColorMatrix
          type="matrix"
          values="
            1 0 0 0 0
            0 1 0 0 0
            0 0 1 0 0
            1 -1.2 1 1 0
          "
        />
      </filter>
    </defs>
  </svg>
);

export const AnchorVideoLayer: React.FC<{
  anchor?: PublicMedia;
  crop: AnchorCrop;
  style?: React.CSSProperties;
  mediaFilter?: string;
  overlay?: React.CSSProperties['background'];
  chromaKey?: boolean;
}> = ({anchor, crop, style, mediaFilter, overlay, chromaKey}) => {
  const toneFilter = mediaFilter ?? defaultAnchorFilter;
  const videoFilter = chromaKey ? `url(#${chromaKeyFilterId}) ${toneFilter}` : toneFilter;

  return (
    <div
      style={{
        position: 'absolute',
        overflow: 'hidden',
        backgroundColor: brand.ink,
        ...style,
      }}
    >
      {chromaKey ? <ChromaKeyFilter /> : null}
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
              filter: videoFilter,
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
