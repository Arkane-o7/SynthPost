import React from 'react';
import {AbsoluteFill} from 'remotion';
import {BackgroundLayer} from '../components/BackgroundLayer';
import {Frame} from '../components/Frame';
import {HeadlineBlock} from '../components/HeadlineBlock';
import {HeroSubject} from '../components/HeroSubject';
import {LogoCard} from '../components/LogoCard';
import {TopHeadlineBar} from '../components/TopHeadlineBar';
import {assetsByType, firstAsset, primarySubject, subjectByType} from '../layout';
import {thumbnailTheme} from '../theme';
import type {ThumbnailConceptProps} from '../types';

export const MoneyDealBomb: React.FC<ThumbnailConceptProps> = (props) => {
  const accent = thumbnailTheme.colors.gold;
  const background = firstAsset(props.assets, ['background_image', 'generated_background']);
  const logo = assetsByType(props.assets, 'logo')[0];
  const personAsset = assetsByType(props.assets, 'person_image')[0];
  const company = subjectByType(props.mainSubjects, 'company') || primarySubject(props.mainSubjects);
  const person = subjectByType(props.mainSubjects, 'person') || primarySubject(props.mainSubjects);
  const keyNumber = props.keyNumbers?.find((item) => {
    const value = String(item.value || '');
    const label = String(item.label || '').toLowerCase();
    return /[$₹£]|billion|million|crore|lakh|trillion|%/i.test(value) || /deal|capex|valuation|market|exports|ipo/.test(label);
  });
  const number = keyNumber?.value || props.headlineText.match(/[$₹£][A-Za-z0-9.$₹£ ]+/)?.[0];

  return (
    <AbsoluteFill style={{background: thumbnailTheme.colors.obsidian}}>
      <BackgroundLayer asset={background} emotion="optimistic" />
      <TopHeadlineBar text={props.headlineText} accentWords={props.accentWords} accent={accent} />
      {number ? (
        <>
          <div
            style={{
              position: 'absolute',
              left: 58,
              top: 166,
              fontFamily: thumbnailTheme.font.headline,
              fontSize: 132,
              lineHeight: 0.9,
              color: accent,
              textShadow: `0 0 50px ${accent}55, 0 10px 34px rgba(0,0,0,0.8)`,
              maxWidth: 650,
              textTransform: 'uppercase',
            }}
          >
            {number}
          </div>
          <div style={{position: 'absolute', left: 58, top: 336}}>
            <HeadlineBlock text={props.headlineText.replace(number, '').trim() || props.headlineText} accentWords={props.accentWords} accent={accent} maxWidth={620} size={74} />
          </div>
        </>
      ) : (
        null
      )}
      <div style={{position: 'absolute', left: number ? 680 : 120, top: number ? 178 : 178}}>
        <LogoCard asset={logo} subject={company} accent={accent} width={number ? 340 : 420} height={number ? 210 : 250} />
      </div>
      <div style={{position: 'absolute', right: 58, top: 178}}>
        <HeroSubject subject={person} asset={personAsset} accent={accent} width={360} height={450} />
      </div>
      <div
        style={{
          position: 'absolute',
          left: 58,
          bottom: 64,
          fontFamily: thumbnailTheme.font.body,
          color: thumbnailTheme.colors.warmWhite,
          fontSize: 32,
          fontWeight: 900,
          maxWidth: 560,
          lineHeight: 1.12,
          textShadow: '0 8px 30px rgba(0,0,0,0.82)',
        }}
      >
        {props.subtitleText || props.episodeHeadline}
      </div>
      <Frame accent={accent} />
    </AbsoluteFill>
  );
};
