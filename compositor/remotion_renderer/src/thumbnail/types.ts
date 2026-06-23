export type ThumbnailTemplateId =
  | 'authority_warning'
  | 'global_ai_faceoff'
  | 'sovereign_ai_stack'
  | 'money_deal_bomb'
  | 'clean_market_surge'
  | 'map_crisis_marker'
  | 'factory_boom'
  | 'logo_collision'
  | 'device_shock'
  | 'agent_swarm'
  | 'document_exposed'
  | 'infrastructure_race'
  | 'inside_the_deal';

export type ThumbnailEmotion =
  | 'urgent'
  | 'analytical'
  | 'shocking'
  | 'mysterious'
  | 'serious'
  | 'optimistic'
  | 'conflict'
  | 'warning';

export type ThumbnailSubject = {
  type: string;
  name: string;
  role?: string;
  importance?: 'primary' | 'secondary' | 'context';
  visual_priority?: number;
};

export type ThumbnailAsset = {
  id: string;
  type: string;
  path_or_url?: string;
  publicPath?: string;
  subject_name?: string;
  label?: string;
  usage_status?: string;
};

export type ThumbnailKeyNumber = {
  label: string;
  value: string;
  unit?: string;
  confidence?: string;
};

export type ThumbnailConceptProps = {
  briefId: string;
  conceptId: string;
  templateId: ThumbnailTemplateId;
  videoTitle: string;
  episodeHeadline: string;
  topic: string;
  emotion: ThumbnailEmotion;
  headlineText: string;
  subtitleText?: string;
  accentWords?: string[];
  sourceTag?: string;
  visualHook?: string;
  mainSubjects: ThumbnailSubject[];
  keyNumbers?: ThumbnailKeyNumber[];
  assets: ThumbnailAsset[];
  score?: number;
};
