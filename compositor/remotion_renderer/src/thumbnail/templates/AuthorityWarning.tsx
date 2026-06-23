import React from 'react';
import {AbsoluteFill} from 'remotion';
import {BackgroundLayer} from '../components/BackgroundLayer';
import {DataChip} from '../components/DataChip';
import {Frame} from '../components/Frame';
import {HeroSubject} from '../components/HeroSubject';
import {TopHeadlineBar} from '../components/TopHeadlineBar';
import {assetsByType, firstAsset, primarySubject} from '../layout';
import {accentForEmotion, thumbnailTheme} from '../theme';
import type {ThumbnailConceptProps} from '../types';

export const AuthorityWarning: React.FC<ThumbnailConceptProps> = (props) => {
  const accent = accentForEmotion(props.emotion);
  const background = firstAsset(props.assets, ['background_image', 'generated_background', 'map']);
  const person = primarySubject(props.mainSubjects);
  const personAsset = assetsByType(props.assets, 'person_image')[0];
  const keyNumber = props.keyNumbers?.find((item) => {
    const value = String(item.value || '');
    const label = String(item.label || '').toLowerCase();
    return /[$%]|billion|million|crore|lakh|trillion/i.test(value) || /market|deal|drop|growth|exports|share|score/.test(label);
  });

  return (
    <AbsoluteFill style={{background: thumbnailTheme.colors.obsidian}}>
      <BackgroundLayer asset={background} emotion={props.emotion} />
      <TopHeadlineBar text={props.headlineText} accentWords={props.accentWords} accent={accent} />
      <div
        style={{
          position: 'absolute',
          left: 58,
          top: 160,
          width: 520,
          height: 410,
          opacity: 0.5,
          background:
            'radial-gradient(circle at 28% 44%, rgba(244,239,231,0.22), transparent 36%), linear-gradient(115deg, rgba(244,239,231,0.2), rgba(0,106,166,0.08) 44%, transparent 70%)',
          clipPath: 'polygon(0 0, 82% 12%, 62% 100%, 0 88%)',
        }}
      />
      <div style={{position: 'absolute', left: 58, bottom: 72}}>
        {props.subtitleText ? (
          <div
            style={{
              maxWidth: 620,
              color: thumbnailTheme.colors.warmWhite,
              fontFamily: thumbnailTheme.font.body,
              fontSize: 32,
              fontWeight: 900,
              lineHeight: 1.16,
              textShadow: '0 8px 30px rgba(0,0,0,0.82)',
            }}
          >
            {props.subtitleText}
          </div>
        ) : null}
      </div>
      <div style={{position: 'absolute', right: 64, top: 142}}>
        <HeroSubject subject={person} asset={personAsset} accent={accent} width={500} height={522} />
      </div>
      {keyNumber ? (
        <div style={{position: 'absolute', left: 58, top: 154}}>
          <DataChip label={keyNumber.label} value={`${keyNumber.value}${keyNumber.unit ? ` ${keyNumber.unit}` : ''}`} accent={accent} />
        </div>
      ) : null}
      <Frame accent={accent} />
    </AbsoluteFill>
  );
};
