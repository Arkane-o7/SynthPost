import React from 'react';
import type {ThumbnailConceptProps} from './types';
import {AuthorityWarning} from './templates/AuthorityWarning';
import {CleanMarketSurge} from './templates/CleanMarketSurge';
import {LogoCollision} from './templates/LogoCollision';
import {MoneyDealBomb} from './templates/MoneyDealBomb';

export const fallbackThumbnailProps: ThumbnailConceptProps = {
  briefId: 'preview',
  conceptId: 'concept_01',
  templateId: 'authority_warning',
  videoTitle: 'SynthPost AI briefing',
  episodeHeadline: 'AI infrastructure becomes the next global policy battleground.',
  topic: 'AI',
  emotion: 'analytical',
  headlineText: 'THE COMPUTE RACE',
  accentWords: ['COMPUTE'],
  sourceTag: 'SYNTHPOST BRIEFING',
  mainSubjects: [{type: 'company', name: 'SynthPost', importance: 'primary'}],
  keyNumbers: [{label: 'Signal', value: 'v1'}],
  assets: [{id: 'fallback_bg', type: 'background_image', publicPath: 'news/datacenter-server-racks.jpg'}],
};

export const ThumbnailRoot: React.FC<ThumbnailConceptProps> = (props) => {
  switch (props.templateId) {
    case 'money_deal_bomb':
      return <MoneyDealBomb {...props} />;
    case 'clean_market_surge':
    case 'device_shock':
      return <CleanMarketSurge {...props} />;
    case 'logo_collision':
    case 'global_ai_faceoff':
      return <LogoCollision {...props} />;
    case 'authority_warning':
    default:
      return <AuthorityWarning {...props} />;
  }
};
