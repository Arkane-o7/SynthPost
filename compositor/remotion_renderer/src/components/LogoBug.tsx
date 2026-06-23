import React, {useState} from 'react';
import {Img} from 'remotion';
import {brand, typography} from '../styles/brand';
import type {PublicMedia} from '../types';
import {mediaSrc} from './media';

export const LogoBug: React.FC<{logo?: PublicMedia}> = ({logo}) => {
  const [showImage, setShowImage] = useState(Boolean(logo));
  return (
    <div
      style={{
        width: 390,
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        paddingLeft: 30,
        borderRight: '1px solid rgba(245,247,250,0.34)',
      }}
    >
      {logo && showImage ? (
        <Img
          src={mediaSrc(logo)}
          onError={() => setShowImage(false)}
          style={{maxWidth: 300, maxHeight: 80, objectFit: 'contain'}}
        />
      ) : (
        <div
          style={{
            fontFamily: typography.serif,
            fontSize: 68,
            lineHeight: 1,
            color: brand.white,
            letterSpacing: 0,
          }}
        >
          Synthpost<span style={{color: brand.signalBlue}}>.</span>
        </div>
      )}
    </div>
  );
};
