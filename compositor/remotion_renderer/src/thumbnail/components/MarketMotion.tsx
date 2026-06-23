import React from 'react';
import {thumbnailTheme} from '../theme';

export const MarketMotion: React.FC<{accent?: string}> = ({accent = '#4764F6'}) => {
  return (
    <svg
      width="1280"
      height="720"
      viewBox="0 0 1280 720"
      style={{
        position: 'absolute',
        inset: 0,
        overflow: 'visible',
      }}
    >
      <defs>
        <linearGradient id="motionBlue" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor={accent} stopOpacity="0" />
          <stop offset="52%" stopColor={accent} stopOpacity="0.34" />
          <stop offset="100%" stopColor={accent} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="motionGray" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#8A96A8" stopOpacity="0" />
          <stop offset="54%" stopColor="#8A96A8" stopOpacity="0.38" />
          <stop offset="100%" stopColor="#8A96A8" stopOpacity="0" />
        </linearGradient>
        <filter id="softBlur">
          <feGaussianBlur stdDeviation="2.4" />
        </filter>
      </defs>
      <g opacity="0.84" transform="translate(150 0)">
        <path d="M0 680 C260 560, 455 485, 700 410 C840 365, 945 310, 1080 220" stroke="url(#motionGray)" strokeWidth="18" fill="none" filter="url(#softBlur)" />
        <path d="M-20 710 C240 575, 500 510, 725 430 C900 370, 1020 308, 1160 235" stroke="url(#motionBlue)" strokeWidth="8" fill="none" />
        <path d="M-10 646 C280 540, 530 488, 758 392 C890 336, 1010 278, 1168 210" stroke="url(#motionBlue)" strokeWidth="4" fill="none" opacity="0.54" />
        <path d="M12 615 C280 534, 522 458, 720 374 C890 300, 1018 245, 1160 174" stroke="url(#motionGray)" strokeWidth="4" fill="none" opacity="0.48" />
      </g>
      <g transform="translate(0 0)" opacity="0.88">
        <path d="M930 390 C1015 346, 1080 284, 1186 216" stroke={accent} strokeWidth="34" strokeLinecap="round" fill="none" />
        <polygon points="1184,216 1102,224 1153,292" fill={accent} />
      </g>
      <g opacity="0.2" stroke={thumbnailTheme.colors.deepNavy} strokeWidth="2">
        <path d="M930 428 L930 330" />
        <path d="M974 410 L974 300" />
        <path d="M1018 390 L1018 274" />
        <path d="M1062 366 L1062 250" />
      </g>
    </svg>
  );
};

