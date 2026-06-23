import {ENDSCREEN_SAFE_ZONES, safeZoneMetadata} from './endscreenStyles';

export type EndscreenProps = {
  episodeId: string;
  episodeTitle: string;
  episodeTopic: string;
  nextVideoTitle: string;
  nextVideoThumbnail?: string;
  recommendedVideoTitle?: string;
  recommendedVideoThumbnail?: string;
  channelLogo?: string;
  backgroundVisual?: string;
  anchorVideo?: string;
  ctaText?: string;
  bridgeText?: string;
  durationSeconds: number;
  fps?: number;
  debugSafeZones?: boolean;
};

export type NormalizedEndscreenProps = EndscreenProps & {
  fps: number;
  durationSeconds: number;
  ctaText: string;
  bridgeText: string;
  recommendedVideoTitle: string;
};

export const defaultEndscreenProps: NormalizedEndscreenProps = {
  episodeId: 'preview',
  episodeTitle: 'SynthPost Briefing',
  episodeTopic: 'global news',
  nextVideoTitle: 'The Next Signal To Watch',
  recommendedVideoTitle: 'Latest Briefing',
  ctaText: 'Continue the briefing',
  bridgeText: 'The next signal follows the story behind the headline.',
  durationSeconds: 20,
  fps: 24,
  debugSafeZones: false,
};

export const clampDurationSeconds = (value: unknown): number => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 20;
  }
  return Math.max(5, Math.min(20, numeric));
};

export const normalizeFps = (value: unknown): number => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return 24;
  }
  return Math.max(1, Math.min(60, Math.round(numeric)));
};

const clean = (value: unknown): string => String(value ?? '').replace(/\s+/g, ' ').trim();

export const requireEndscreenFields = (props: Partial<EndscreenProps>): void => {
  const missing = ['episodeTitle', 'episodeTopic', 'nextVideoTitle'].filter((field) => !clean((props as Record<string, unknown>)[field]));
  if (missing.length) {
    throw new Error(`Endscreen input is missing required field(s): ${missing.join(', ')}`);
  }
};

export const normalizeEndscreenProps = (props: Partial<EndscreenProps> = {}): NormalizedEndscreenProps => {
  const episodeTopic = clean(props.episodeTopic) || defaultEndscreenProps.episodeTopic;
  return {
    ...defaultEndscreenProps,
    ...props,
    episodeId: clean(props.episodeId) || defaultEndscreenProps.episodeId,
    episodeTitle: clean(props.episodeTitle) || defaultEndscreenProps.episodeTitle,
    episodeTopic,
    nextVideoTitle: clean(props.nextVideoTitle) || defaultEndscreenProps.nextVideoTitle,
    recommendedVideoTitle: clean(props.recommendedVideoTitle) || defaultEndscreenProps.recommendedVideoTitle,
    ctaText: clean(props.ctaText) || defaultEndscreenProps.ctaText,
    bridgeText:
      clean(props.bridgeText) ||
      `The next signal follows the ${episodeTopic.toLowerCase()} story behind the headline.`,
    durationSeconds: clampDurationSeconds(props.durationSeconds),
    fps: normalizeFps(props.fps),
    debugSafeZones: Boolean(props.debugSafeZones),
  };
};

export const endscreenDurationInFrames = (props: Partial<EndscreenProps>): number => {
  const normalized = normalizeEndscreenProps(props);
  return Math.max(1, Math.round(normalized.durationSeconds * normalized.fps));
};

export const endscreenSafeZoneMetadata = (props: Partial<EndscreenProps>) => {
  const normalized = normalizeEndscreenProps(props);
  return safeZoneMetadata(normalized.durationSeconds, normalized.fps);
};

export {ENDSCREEN_SAFE_ZONES};
