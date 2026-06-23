import {staticFile} from 'remotion';
import type {ThumbnailAsset, ThumbnailSubject} from './types';

export const assetSrc = (asset?: ThumbnailAsset): string | undefined => {
  const value = asset?.publicPath || asset?.path_or_url;
  if (!value) {
    return undefined;
  }
  if (/^(generated|symbolic):\/\//i.test(value)) {
    return undefined;
  }
  if (/^https?:\/\//i.test(value)) {
    return value;
  }
  return staticFile(value);
};

export const assetsByType = (assets: ThumbnailAsset[], type: string): ThumbnailAsset[] =>
  assets.filter((asset) => asset.type === type || asset.type.replace(/_/g, '-') === type.replace(/_/g, '-'));

export const firstAsset = (assets: ThumbnailAsset[], types: string[]): ThumbnailAsset | undefined => {
  for (const type of types) {
    const match = assetsByType(assets, type)[0];
    if (match) {
      return match;
    }
  }
  return undefined;
};

export const initialsFor = (subject?: ThumbnailSubject): string => {
  const name = subject?.name || 'SP';
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase();
  }
  return words
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase();
};

export const primarySubject = (subjects: ThumbnailSubject[]): ThumbnailSubject | undefined =>
  subjects.find((subject) => subject.importance === 'primary') || subjects[0];

export const subjectByType = (subjects: ThumbnailSubject[], type: string): ThumbnailSubject | undefined =>
  subjects.find((subject) => subject.type === type);
