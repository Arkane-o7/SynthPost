import type {ThumbnailEmotion} from './types';

export const thumbnailTheme = {
  width: 1280,
  height: 720,
  headerHeight: 118,
  borderWidth: 6,
  colors: {
    obsidian: '#070A0F',
    graphite: '#111827',
    slate: '#1F2937',
    offWhite: '#F8FAFC',
    muted: '#CBD5E1',
    cream: '#E4D4C6',
    warmWhite: '#F4EFE7',
    deepNavy: '#000C1E',
    synthBlue: '#006AA6',
    headlineInk: '#050A14',
    cyan: '#18D4FF',
    blue: '#2563EB',
    red: '#EF233C',
    green: '#22C55E',
    gold: '#F5C542',
    saffron: '#FF8A00',
  },
  font: {
    headline: '"Arial Black", Impact, "Avenir Next Condensed", sans-serif',
    body: '"Avenir Next", Inter, "Helvetica Neue", Arial, sans-serif',
  },
};

export const accentForEmotion = (emotion: ThumbnailEmotion): string => {
  switch (emotion) {
    case 'urgent':
    case 'warning':
    case 'shocking':
    case 'conflict':
      return thumbnailTheme.colors.red;
    case 'optimistic':
      return thumbnailTheme.colors.green;
    case 'mysterious':
      return '#8B5CF6';
    case 'analytical':
      return thumbnailTheme.colors.synthBlue;
    case 'serious':
    default:
      return thumbnailTheme.colors.blue;
  }
};
