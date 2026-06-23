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
  mediaType?: 'video' | 'photo' | 'screenshot' | 'document' | 'map' | 'chart' | 'satellite' | 'stock';
  contentRole?: 'evidence' | 'context' | 'explanation' | 'atmosphere';
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
  durationSeconds: number;
  headline: string;
  headlineItems: HeadlineItem[];
  category: string;
  sourceLabel: string;
  sourceDate: string;
  anchor?: PublicMedia;
  visuals: TimedVisual[];
  points: NewsPoint[];
  logo?: PublicMedia;
};
