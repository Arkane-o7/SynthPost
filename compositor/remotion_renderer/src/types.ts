export type PublicMedia = {
  publicPath: string;
  absolutePath?: string;
  kind: "image" | "video";
  remote?: boolean;
};

export type TimedVisual = PublicMedia & {
  start: number;
  end: number;
  fit?: "cover" | "contain";
  sourceLabel?: string;
  audio?: boolean;
  hasAudio?: boolean;
  volume?: number;
  mediaType?:
    | "video"
    | "image"
    | "photo"
    | "screenshot"
    | "document"
    | "map"
    | "chart"
    | "satellite"
    | "stock"
    | "generated_card"
    | string;
  contentRole?:
    | "evidence"
    | "primary_footage"
    | "context"
    | "explanation"
    | "location"
    | "person"
    | "document"
    | "data"
    | "atmosphere"
    | "fallback"
    | string;
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
  trimStart?: number;
  trimEnd?: number;
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
    preset?:
      | "push_in"
      | "pan_left"
      | "document_scan"
      | "map_zoom"
      | "chart_reveal"
      | "screenshot_focus";
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

export type TimelineSegmentProps = {
  segmentId: string;
  sectionId: string;
  start: number;
  end: number;
  duration: number;
  narrationStart?: number;
  scriptText: string;
  anchor: {
    visible: boolean;
    speaking: boolean;
    camera?: string;
  };
  visual?: TimedVisual;
  template: {
    templateId: string;
    layout?: string;
  };
  audio?: {
    mode?: "narration" | "source" | "mixed" | "silent";
    narrationVolume?: number;
    sourceVolume?: number;
    ducking?: boolean;
  };
  overlays: {
    lowerThird?: string;
    chyron?: string;
    attribution?: string;
    quoteText?: string;
    documentSource?: string;
    data?: Record<string, unknown>;
  };
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
  timelineSegments?: TimelineSegmentProps[];
};
