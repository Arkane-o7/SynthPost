import React from 'react';
import {Img} from 'remotion';
import {assetSrc} from '../layout';
import {thumbnailTheme} from '../theme';
import type {ThumbnailAsset} from '../types';

export const GpuProp: React.FC<{asset?: ThumbnailAsset; label?: string}> = ({asset, label = 'RTX 4090'}) => {
  const src = assetSrc(asset);
  if (src) {
    return (
      <Img
        src={src}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          filter: 'drop-shadow(0 24px 28px rgba(0,0,0,0.34))',
        }}
      />
    );
  }
  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        transform: 'rotate(-8deg)',
        filter: 'drop-shadow(0 24px 28px rgba(0,0,0,0.36))',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: 18,
          right: 12,
          top: 30,
          bottom: 24,
          borderRadius: 26,
          background: 'linear-gradient(135deg, #171A21 0%, #343943 52%, #090A0D 100%)',
          border: '4px solid #C6CCD5',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: 62,
          top: 96,
          width: 142,
          height: 118,
          borderRadius: 20,
          background: 'linear-gradient(135deg, #4B505A, #1E2229)',
          border: '3px solid #DDE2EA',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: thumbnailTheme.colors.offWhite,
          fontFamily: thumbnailTheme.font.body,
          fontSize: 23,
          fontWeight: 800,
        }}
      >
        {label}
      </div>
      <div
        style={{
          position: 'absolute',
          right: 48,
          top: 76,
          width: 128,
          height: 128,
          borderRadius: '50%',
          background: 'radial-gradient(circle, #B9C0CA 0 8%, #2B3039 9% 24%, #0D0F14 25% 100%)',
          border: '6px solid #0A0B0E',
          boxShadow: 'inset 0 0 24px rgba(255,255,255,0.22)',
        }}
      />
    </div>
  );
};

