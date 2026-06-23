import {staticFile} from 'remotion';
import type {PublicMedia} from '../types';

export const mediaSrc = (media: PublicMedia): string => {
  if (media.remote) {
    return media.publicPath;
  }
  return staticFile(media.publicPath);
};
