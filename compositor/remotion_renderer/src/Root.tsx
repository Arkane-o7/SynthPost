import React from 'react';
import {Composition, registerRoot, staticFile} from 'remotion';
import {getVideoMetadata} from '@remotion/media-utils';
import {Endscreen} from './endscreen/Endscreen';
import {
  defaultEndscreenProps,
  endscreenDurationInFrames,
  normalizeEndscreenProps,
  type EndscreenProps,
} from './endscreen/endscreen.schema';
import {FullScreenAnchor} from './templates/FullScreenAnchor';
import {FullScreenNewsVisuals} from './templates/FullScreenNewsVisuals';
import {SplitMain} from './templates/SplitMain';
import {fallbackThumbnailProps, ThumbnailRoot} from './thumbnail/ThumbnailRoot';
import type {StoryProps} from './types';

const fallbackProps: StoryProps = {
  storyId: 'preview',
  episodeId: 'preview',
  fps: 24,
  durationSeconds: 12,
  headline: 'SYNTHPOST SAMPLE STORY',
  headlineItems: [
    {text: 'SYNTHPOST SAMPLE STORY', start: 0},
    {text: 'MANIFEST-DRIVEN VIDEO GENERATION', start: 4},
    {text: 'AVATAR, VISUALS, AND CHYRONS IN SYNC', start: 8},
    {text: 'BROADCAST FRAME RENDERED BY CODE', start: 12},
  ],
  category: 'TECHNOLOGY',
  sourceLabel: 'SYNTHPOST',
  sourceDate: 'JUNE 20',
  visuals: [
    {
      publicPath: 'news/datacenter-server-racks.jpg',
      kind: 'image',
      start: 0,
      end: 30,
      fit: 'cover',
      sourceLabel: 'DATA CENTER',
    },
  ],
  points: [
    {text: 'Manifest-driven video generation keeps every stage re-runnable', start: 3},
    {text: 'Avatar, visuals, and lower third share one story contract', start: 7},
  ],
};

const calculateStoryMetadata = async ({props}: {props: StoryProps}) => {
  const typed = props as StoryProps;
  const fps = typed.fps || 24;
  const width = typed.width || 1920;
  const height = typed.height || 1080;
  let durationSeconds = typed.durationSeconds || 12;
  if (typed.anchor?.publicPath) {
    try {
      const metadata = await getVideoMetadata(staticFile(typed.anchor.publicPath));
      durationSeconds = metadata.durationInSeconds || durationSeconds;
    } catch (error) {
      console.warn(`Could not read anchor metadata: ${String(error)}`);
    }
  }
  return {
    fps,
    width,
    height,
    durationInFrames: Math.max(1, Math.ceil(durationSeconds * fps)),
  };
};

const calculateEndscreenMetadata = ({props}: {props: Partial<EndscreenProps>}) => {
  const normalized = normalizeEndscreenProps(props);
  return {
    fps: normalized.fps,
    width: 1920,
    height: 1080,
    durationInFrames: endscreenDurationInFrames(normalized),
    props: normalized,
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="split-main"
        component={SplitMain}
        width={1920}
        height={1080}
        fps={24}
        durationInFrames={24 * 12}
        defaultProps={fallbackProps}
        calculateMetadata={calculateStoryMetadata}
      />
      <Composition
        id="full-screen-anchor"
        component={FullScreenAnchor}
        width={1920}
        height={1080}
        fps={24}
        durationInFrames={24 * 12}
        defaultProps={fallbackProps}
        calculateMetadata={calculateStoryMetadata}
      />
      <Composition
        id="FullScreenNewsVisuals"
        component={FullScreenNewsVisuals}
        width={1920}
        height={1080}
        fps={24}
        durationInFrames={24 * 12}
        defaultProps={fallbackProps}
        calculateMetadata={calculateStoryMetadata}
      />
      <Composition
        id="thumbnail"
        component={ThumbnailRoot}
        width={1280}
        height={720}
        fps={30}
        durationInFrames={30}
        defaultProps={fallbackThumbnailProps}
      />
      <Composition
        id="SynthPostEndscreen"
        component={Endscreen}
        width={1920}
        height={1080}
        fps={24}
        durationInFrames={24 * 20}
        defaultProps={defaultEndscreenProps}
        calculateMetadata={calculateEndscreenMetadata}
      />
    </>
  );
};

registerRoot(RemotionRoot);
