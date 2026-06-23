import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, interpolate} from 'remotion';
import type {TimedVisual} from '../types';
import {mediaSrc} from './media';

export const activeVisual = (visuals: TimedVisual[], second: number): TimedVisual => {
  return visuals.find((visual) => second >= visual.start && second < visual.end) ?? visuals[0];
};

export const clampUnit = (value: number): number => Math.max(0, Math.min(1, value));

export const visualMotionStyle = (visual: TimedVisual, progress: number): React.CSSProperties => {
  if (visual.kind === 'video') {
    return {};
  }
  const preset = visual.motion?.preset ?? 'push_in';
  const intensity = clampUnit(Number(visual.motion?.intensity ?? 0.28));
  const focus = visual.motion?.focus ?? [0.5, 0.5];
  const origin = `${focus[0] * 100}% ${focus[1] * 100}%`;
  const ease = interpolate(progress, [0, 1], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const scaleSmall = 1 + 0.045 * intensity;
  const scaleLarge = 1 + 0.16 * intensity;
  const pan = 80 * intensity;

  if (preset === 'pan_left') {
    return {
      transform: `scale(${scaleSmall + 0.04 * ease}) translateX(${pan * (0.5 - ease)}px)`,
      transformOrigin: origin,
    };
  }
  if (preset === 'document_scan') {
    return {
      transform: `scale(${1.02 + 0.075 * ease * intensity}) translateY(${pan * (0.22 - ease * 0.44)}px)`,
      transformOrigin: origin,
    };
  }
  if (preset === 'map_zoom') {
    return {
      transform: `scale(${1 + 0.14 * ease * intensity})`,
      transformOrigin: origin,
    };
  }
  if (preset === 'chart_reveal') {
    return {
      transform: `scale(${scaleSmall}) translateX(${pan * 0.14 * (1 - ease)}px)`,
      transformOrigin: origin,
      clipPath: `inset(0 ${Math.max(0, 16 * (1 - ease))}% 0 0)`,
    };
  }
  if (preset === 'screenshot_focus') {
    return {
      transform: `scale(${1 + 0.1 * ease * intensity}) translateY(${pan * 0.1 * (1 - ease)}px)`,
      transformOrigin: origin,
    };
  }
  return {
    transform: `scale(${scaleSmall + (scaleLarge - scaleSmall) * ease})`,
    transformOrigin: origin,
  };
};

export const VisualMediaLayer: React.FC<{
  visual: TimedVisual;
  progress: number;
  muted?: boolean;
  volume?: number;
  mediaStyle?: React.CSSProperties;
}> = ({visual, progress, muted = true, volume, mediaStyle}) => {
  const src = mediaSrc(visual);
  const style: React.CSSProperties = {
    width: '100%',
    height: '100%',
    objectFit: visual.fit ?? 'cover',
    objectPosition: 'center center',
    ...mediaStyle,
  };

  if (visual.kind === 'video') {
    return <OffthreadVideo muted={muted} volume={volume} src={src} style={style} />;
  }

  return (
    <AbsoluteFill style={{...visualMotionStyle(visual, progress), willChange: 'transform'}}>
      <Img src={src} style={style} />
    </AbsoluteFill>
  );
};
