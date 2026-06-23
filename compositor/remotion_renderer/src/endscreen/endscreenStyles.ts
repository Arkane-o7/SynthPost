import {brand, typography} from '../styles/brand';

export const ENDSCREEN_WIDTH = 1920;
export const ENDSCREEN_HEIGHT = 1080;

export const ENDSCREEN_SAFE_ZONES = {
  primary_video: {
    x: 1080,
    y: 168,
    width: 650,
    height: 366,
    youtubeElement: 'video',
  },
  secondary_video: {
    x: 1080,
    y: 590,
    width: 650,
    height: 366,
    youtubeElement: 'video',
  },
  subscribe: {
    x: 132,
    y: 684,
    width: 260,
    height: 260,
    youtubeElement: 'subscribe',
  },
} as const;

export type EndscreenZoneName = keyof typeof ENDSCREEN_SAFE_ZONES;

export const endscreenTiming = {
  introEnd: 1.5,
  primaryEnd: 4,
  secondaryEnd: 6.5,
  subscribeEnd: 9,
  calmStart: 15,
};

export const endscreenStyles = {
  colors: brand,
  typography,
  cardBorder: '1px solid rgba(245,247,250,0.26)',
  cardShadow: '0 18px 54px rgba(0,0,0,0.38)',
  gridColor: 'rgba(245,247,250,0.055)',
};

export const validateSafeZones = (): void => {
  for (const [name, zone] of Object.entries(ENDSCREEN_SAFE_ZONES)) {
    if (zone.x < 0 || zone.y < 0 || zone.width <= 0 || zone.height <= 0) {
      throw new Error(`Invalid endscreen safe zone '${name}': dimensions must be positive and positioned inside canvas.`);
    }
    if (zone.x + zone.width > ENDSCREEN_WIDTH || zone.y + zone.height > ENDSCREEN_HEIGHT) {
      throw new Error(`Invalid endscreen safe zone '${name}': zone exceeds ${ENDSCREEN_WIDTH}x${ENDSCREEN_HEIGHT}.`);
    }
  }
};

export const safeZoneMetadata = (durationSeconds: number, fps: number) => {
  validateSafeZones();
  return {
    canvas: {
      width: ENDSCREEN_WIDTH,
      height: ENDSCREEN_HEIGHT,
    },
    durationSeconds,
    fps,
    zones: ENDSCREEN_SAFE_ZONES,
  };
};
