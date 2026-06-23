import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import {CleanBrandRail, CLEAN_RAIL_WIDTH} from '../components/CleanBrandRail';
import {GpuProp} from '../components/GpuProp';
import {MarketMotion} from '../components/MarketMotion';
import {assetSrc, assetsByType, firstAsset, primarySubject} from '../layout';
import {thumbnailTheme} from '../theme';
import type {ThumbnailConceptProps} from '../types';

const headlineWords = (text: string): string[] => text.trim().split(/\s+/).filter(Boolean);

export const CleanMarketSurge: React.FC<ThumbnailConceptProps> = (props) => {
  const accent = '#4864F6';
  const person = primarySubject(props.mainSubjects);
  const personAsset = assetsByType(props.assets, 'person_image')[0];
  const heroComposite = firstAsset(props.assets, ['hero_composite', 'foreground_composite']);
  const propAsset = firstAsset(props.assets, ['object', 'logo']);
  const personSrc = assetSrc(personAsset);
  const heroCompositeSrc = assetSrc(heroComposite);
  const accents = new Set((props.accentWords || []).map((word) => word.toLowerCase().replace(/[^a-z0-9$%.]/g, '')));
  const words = headlineWords(props.headlineText.toLowerCase());
  const fontSize = props.headlineText.length > 30 ? 82 : props.headlineText.length > 22 ? 94 : props.headlineText.length > 16 ? 108 : 120;

  return (
    <AbsoluteFill style={{background: '#F8F6F1', overflow: 'hidden'}}>
      <style>
        {`
          @font-face {
            font-family: 'SynthPostMarketHeadline';
            src: url('${staticFile('fonts/Anton-Regular.ttf')}') format('truetype');
            font-weight: 400;
            font-style: normal;
            font-display: block;
          }
        `}
      </style>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'radial-gradient(circle at 78% 22%, rgba(255,255,255,0.98), transparent 36%), linear-gradient(135deg, #FFFFFF 0%, #F8F6F1 48%, #EFE8DA 100%)',
        }}
      />
      <CleanBrandRail />
      {!heroCompositeSrc ? <MarketMotion accent={accent} /> : null}

      <div
        style={{
          position: 'absolute',
          left: CLEAN_RAIL_WIDTH + 42,
          top: 40,
          right: 44,
          zIndex: 2,
          display: 'flex',
          alignItems: 'baseline',
          gap: 22,
          fontFamily: '"SynthPostMarketHeadline", Impact, sans-serif',
          fontSize,
          lineHeight: 0.9,
          letterSpacing: -0.8,
          color: '#050505',
          textTransform: 'lowercase',
          whiteSpace: 'nowrap',
          textShadow: '0 5px 16px rgba(0,0,0,0.06)',
        }}
      >
        {words.map((word, index) => {
          const stripped = word.replace(/[^a-z0-9$%.]/g, '');
          return (
            <span key={`${word}-${index}`} style={{color: accents.has(stripped) || accents.has(word) ? accent : '#050505'}}>
              {word}
            </span>
          );
        })}
      </div>

      {heroCompositeSrc ? (
        <Img
          src={heroCompositeSrc}
          style={{
            position: 'absolute',
            left: 170,
            top: 118,
            zIndex: 5,
            width: 1110,
            height: 625,
            objectFit: 'contain',
            objectPosition: 'center bottom',
            filter: 'drop-shadow(0 24px 28px rgba(0,0,0,0.22))',
          }}
        />
      ) : (
        <>
          <div
            style={{
              position: 'absolute',
              left: 470,
              top: 164,
              zIndex: 5,
              width: 540,
              height: 590,
              display: 'flex',
              alignItems: 'flex-end',
              justifyContent: 'center',
            }}
          >
            {personSrc ? (
          <Img
            src={personSrc}
            style={{
              maxWidth: '100%',
              maxHeight: '100%',
              objectFit: 'contain',
              objectPosition: 'center bottom',
              filter: 'drop-shadow(0 24px 22px rgba(0,0,0,0.28)) saturate(1.04) contrast(1.04)',
            }}
          />
            ) : (
          <div
            style={{
              width: 410,
              height: 410,
              borderRadius: '50%',
              background: 'radial-gradient(circle at 45% 30%, #FFFFFF 0%, #E7EDF8 34%, #6C88F6 65%, #10235A 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#FFFFFF',
              fontFamily: '"SynthPostMarketHeadline", Impact, sans-serif',
              fontSize: 154,
              boxShadow: '0 28px 46px rgba(0,0,0,0.24)',
              transform: 'translateY(-52px)',
            }}
          >
            {person?.name.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase() || 'SP'}
          </div>
            )}
          </div>

          <div style={{position: 'absolute', right: 94, bottom: 42, zIndex: 6, width: 374, height: 260}}>
            <GpuProp asset={propAsset} label={propAsset?.label || 'RTX 4090'} />
          </div>
        </>
      )}

    </AbsoluteFill>
  );
};
