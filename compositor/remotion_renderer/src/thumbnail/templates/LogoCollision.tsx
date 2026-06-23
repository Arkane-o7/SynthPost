import React from 'react';
import {AbsoluteFill} from 'remotion';
import {BackgroundLayer} from '../components/BackgroundLayer';
import {Frame} from '../components/Frame';
import {LogoCard} from '../components/LogoCard';
import {TopHeadlineBar} from '../components/TopHeadlineBar';
import {assetsByType, firstAsset} from '../layout';
import {accentForEmotion, thumbnailTheme} from '../theme';
import type {ThumbnailConceptProps} from '../types';

export const LogoCollision: React.FC<ThumbnailConceptProps> = (props) => {
  const accent = accentForEmotion(props.emotion);
  const background = firstAsset(props.assets, ['background_image', 'generated_background']);
  const logos = assetsByType(props.assets, 'logo');
  const subjects = props.mainSubjects.filter((subject) => ['company', 'model', 'product', 'organization', 'object', 'country'].includes(subject.type));
  const leftSubject = subjects[0] || props.mainSubjects[0];
  const rightSubject = subjects[1] || props.mainSubjects[1] || props.mainSubjects[0];

  return (
    <AbsoluteFill style={{background: thumbnailTheme.colors.obsidian}}>
      <BackgroundLayer asset={background} emotion={props.emotion} />
      <TopHeadlineBar text={props.headlineText} accentWords={props.accentWords} accent={accent} />
      <div
        style={{
          position: 'absolute',
          left: 60,
          top: 150,
          width: 530,
          height: 420,
          background: 'linear-gradient(145deg, rgba(244,239,231,0.16), rgba(0,106,166,0.12))',
          clipPath: 'polygon(0 0, 94% 8%, 78% 100%, 0 92%)',
          borderLeft: `8px solid ${thumbnailTheme.colors.synthBlue}`,
          opacity: 0.88,
        }}
      />
      <div
        style={{
          position: 'absolute',
          right: 60,
          top: 150,
          width: 530,
          height: 420,
          background: 'linear-gradient(215deg, rgba(239,35,60,0.18), rgba(0,12,30,0.08))',
          clipPath: 'polygon(22% 8%, 100% 0, 100% 92%, 6% 100%)',
          borderRight: `8px solid ${accent}`,
          opacity: 0.88,
        }}
      />
      <div style={{position: 'absolute', left: 96, top: 210}}>
        <LogoCard asset={logos[0]} subject={leftSubject} accent={thumbnailTheme.colors.synthBlue} width={370} height={238} />
      </div>
      <div style={{position: 'absolute', right: 96, top: 210}}>
        <LogoCard asset={logos[1]} subject={rightSubject} accent={thumbnailTheme.colors.red} width={370} height={238} />
      </div>
      <div
        style={{
          position: 'absolute',
          left: 548,
          top: 250,
          width: 180,
          height: 180,
          borderRadius: 90,
          background: `${thumbnailTheme.colors.deepNavy}E8`,
          border: `2px solid ${accent}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: thumbnailTheme.font.headline,
          color: accent,
          fontSize: 76,
          boxShadow: `0 0 70px ${accent}33`,
        }}
      >
        VS
      </div>
      <div
        style={{
          position: 'absolute',
          left: 120,
          right: 120,
          bottom: 78,
          color: thumbnailTheme.colors.warmWhite,
          fontFamily: thumbnailTheme.font.body,
          fontSize: 34,
          fontWeight: 900,
          textAlign: 'center',
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
