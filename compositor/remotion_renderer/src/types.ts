export type PublicMedia = {
  publicPath: string;
  absolutePath?: string;
  kind: "image" | "video" | "audio";
  remote?: boolean;
};

export type AnchorRenderWindow = {
  timelineStart: number;
  timelineEnd: number;
  sourceStart: number;
  sourceEnd: number;
  clipStart: number;
  clipEnd: number;
  camera?: string;
  segmentIds?: string[];
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

export type PresenterSpeechWindow = {
  start: number;
  speechEnd: number;
  end: number;
};

export type PngPresenter = {
  provider: "png_puppet";
  characterId: string;
  neutral: PublicMedia;
  speaking: PublicMedia;
  poses: Record<string, PublicMedia>;
  speechWindows: PresenterSpeechWindow[];
  talkCadenceFps: number;
  breathCycleSeconds: number;
  breathScale: number;
  entrySeconds: number;
  editorialMotion?: {
    defaultPose?: string;
    defaultPlacement?: MeridianPresenterPlacement;
    defaultMotion?: MeridianPresenterMotion;
    width?: number;
    shadow?: boolean;
  };
  layout: {
    split?: {
      width?: number;
      scale?: number;
      x?: number;
      y?: number;
    };
    fullscreen?: {
      width?: number;
      scale?: number;
      x?: number;
      y?: number;
    };
  };
};

export type MeridianPresenterPlacement =
  | "left"
  | "right"
  | "center"
  | "lower_left"
  | "lower_right"
  | "edge_left"
  | "edge_right";

export type MeridianPresenterMotion =
  | "pop"
  | "slide"
  | "drift"
  | "peek"
  | "hop";

export type MeridianPresenterCue = {
  pose?: string;
  previousPose?: string;
  poseChangeAt?: number;
  poseTransitionSeconds?: number;
  poseTransition?: "cut" | "blur" | "whip";
  placement?: MeridianPresenterPlacement;
  motion?: MeridianPresenterMotion;
  width?: number;
  x?: number;
  y?: number;
  scale?: number;
  rotate?: number;
};

export type MeridianInternalEvent = {
  eventId: string;
  type:
    | "add_evidence"
    | "replace_evidence"
    | "highlight_document"
    | "draw_chart"
    | "add_label"
    | "add_token"
    | "change_pose"
    | "reveal_prop"
    | "camera"
    | string;
  at: number;
  until?: number;
  target?: string;
  payload?: Record<string, unknown>;
};

export type TimelineSegmentProps = {
  segmentId: string;
  beatId?: string;
  sceneId?: string;
  sectionId: string;
  start: number;
  end: number;
  duration: number;
  narrationStart?: number;
  narrativeFunction?: string;
  visualRole?: string;
  transitionIn?: string;
  transitionOut?: string;
  internalEvents?: MeridianInternalEvent[];
  sceneAssets?: Record<string, TimedVisual>;
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
  channelId?: string;
  channelName?: string;
  channelTagline?: string;
  brandTheme?: {
    navy: string;
    deepBlue: string;
    accent: string;
    accentSecondary: string;
    danger: string;
    white: string;
    muted: string;
    ink: string;
  };
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
  anchorRenderWindows?: AnchorRenderWindow[];
  anchorChromaKey?: boolean;
  narrationAudio?: PublicMedia;
  backgroundMusic?: PublicMedia;
  backgroundMusicVolume?: number;
  soundEffects?: Array<{
    media: PublicMedia;
    start: number;
    volume?: number;
  }>;
  presenter?: PngPresenter;
  visuals: TimedVisual[];
  points: NewsPoint[];
  logo?: PublicMedia;
  timelineSegments?: TimelineSegmentProps[];
};
