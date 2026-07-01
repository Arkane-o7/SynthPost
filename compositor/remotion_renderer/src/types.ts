export type PublicMedia = {
  publicPath: string;
  absolutePath?: string;
  kind: 'image' | 'video';
  remote?: boolean;
};

export type TimedVisual = PublicMedia & {
  start: number;
  end: number;
  fit?: 'cover' | 'contain';
  sourceLabel?: string;
  audio?: boolean;
  volume?: number;
  mediaType?:
    | 'video'
    | 'image'
    | 'photo'
    | 'screenshot'
    | 'document'
    | 'map'
    | 'chart'
    | 'satellite'
    | 'stock'
    | 'generated_card'
    | string;
  contentRole?: 'evidence' | 'context' | 'explanation' | 'atmosphere';
  candidateId?: string;
  planId?: string;
  sectionId?: string;
  sectionType?: string;
  visualRole?: string;
  sourceUrl?: string;
  sourceDomain?: string;
  provider?: string;
  license?: string;
  attributionText?: string;
  rightsCategory?: string;
  manualReviewFlag?: boolean;
  fallbackStatus?: string;
  fallbackReason?: string;
  warnings?: string[];
  visualSkillType?: string;
  visualSkill?: Record<string, unknown>;
  skillPlaceholder?: Record<string, unknown>;
  renderSafetyStatus?: string;
  motion?: {
    preset?: 'push_in' | 'pan_left' | 'document_scan' | 'map_zoom' | 'chart_reveal' | 'screenshot_focus';
    intensity?: number;
    focus?: [number, number];
  };
};

export type NewsPoint = {
  text: string;
  start: number;
};

export type HeadlineItem = {
  text: string;
  start?: number;
  end?: number;
};

export type StoryProps = {
  storyId: string;
  episodeId: string;
  fps: number;
  width?: number;
  height?: number;
  durationSeconds: number;
  headline: string;
  headlineItems: HeadlineItem[];
  category: string;
  sourceLabel: string;
  sourceDate: string;
  anchor?: PublicMedia;
  anchorChromaKey?: boolean;
  visuals: TimedVisual[];
  points: NewsPoint[];
  logo?: PublicMedia;
};
