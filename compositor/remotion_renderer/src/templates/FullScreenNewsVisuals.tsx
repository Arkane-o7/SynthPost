import React from 'react';
import {AbsoluteFill, interpolate, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {LowerThird} from '../components/LowerThird';
import {SourceLabel} from '../components/SourceLabel';
import {activeVisual, clampUnit, VisualMediaLayer} from '../components/VisualMediaLayer';
import {brand, layout, typography} from '../styles/brand';
import type {StoryProps, TimedVisual} from '../types';

const fallbackVisual: TimedVisual = {
  publicPath: 'placeholders/news-visual-placeholder.svg',
  kind: 'image',
  start: 0,
  end: 30,
  fit: 'cover',
  sourceLabel: 'SYNTHPOST',
  motion: {preset: 'push_in', intensity: 0.24, focus: [0.5, 0.5]},
};

const visualVolume = (visual: TimedVisual): number => {
  const value = Number(visual.volume ?? 1);
  if (!Number.isFinite(value)) {
    return 1;
  }
  return Math.max(0, Math.min(1.4, value));
};

export const FullScreenNewsVisuals: React.FC<StoryProps> = (props) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const second = frame / fps;
  const visuals = props.visuals.length ? props.visuals : [fallbackVisual];
  const active = activeVisual(visuals, second);
  const activeHasSourceAudio = active.kind === 'video' && active.audio !== false;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: brand.ink,
        overflow: 'hidden',
        color: brand.white,
      }}
    >
      {visuals.map((visual, index) => {
        const startFrame = Math.max(0, Math.round(visual.start * fps));
        const durationFrames = Math.max(1, Math.round(Math.max(0.01, visual.end - visual.start) * fps));
        const localFrame = frame - startFrame;
        const fadeFrames = Math.min(Math.round(fps * 0.35), Math.floor(durationFrames / 3));
        const fadeIn = fadeFrames > 0 ? interpolate(localFrame, [0, fadeFrames], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : 1;
        const fadeOut =
          fadeFrames > 0
            ? interpolate(localFrame, [durationFrames - fadeFrames, durationFrames], [1, 0], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
              })
            : 1;
        const progress = clampUnit(localFrame / durationFrames);
        const muted = visual.kind !== 'video' || visual.audio === false;

        return (
          <Sequence key={`${visual.publicPath}-${visual.start}-${index}`} from={startFrame} durationInFrames={durationFrames}>
            <AbsoluteFill style={{opacity: Math.min(fadeIn, fadeOut)}}>
              <VisualMediaLayer
                visual={visual}
                progress={progress}
                muted={muted}
                volume={muted ? 0 : visualVolume(visual)}
                mediaStyle={{
                  width: '100%',
                  height: '100%',
                  objectFit: visual.fit ?? 'cover',
                  objectPosition: 'center center',
                  filter: 'saturate(0.94) contrast(1.02) brightness(0.96)',
                }}
              />
            </AbsoluteFill>
          </Sequence>
        );
      })}

      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg, rgba(2,8,16,0.04) 0%, rgba(2,8,16,0.00) 46%, rgba(2,8,16,0.22) 78%, rgba(2,8,16,0.50) 100%), linear-gradient(90deg, rgba(2,8,16,0.10) 0%, transparent 30%, transparent 74%, rgba(2,8,16,0.14) 100%)',
          pointerEvents: 'none',
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.1,
          background:
            'repeating-linear-gradient(90deg, rgba(245,247,250,0.08) 0 1px, transparent 1px 110px), repeating-linear-gradient(0deg, rgba(245,247,250,0.04) 0 1px, transparent 1px 110px)',
          mixBlendMode: 'screen',
          pointerEvents: 'none',
        }}
      />

      <SourceLabel
        label={active.sourceLabel || props.sourceLabel}
        date={props.sourceDate}
        left={54}
        bottom={layout.lower.height + 42}
      />

      {activeHasSourceAudio ? (
        <div
          style={{
            position: 'absolute',
            right: 54,
            top: 46,
            padding: '10px 16px',
            border: '1px solid rgba(245,247,250,0.28)',
            background: 'rgba(2,8,16,0.58)',
            color: 'rgba(245,247,250,0.82)',
            fontFamily: typography.sans,
            fontSize: 16,
            fontWeight: 800,
            letterSpacing: 0,
            textTransform: 'uppercase',
            boxShadow: '0 12px 32px rgba(0,0,0,0.24)',
          }}
        >
          Source Audio
        </div>
      ) : null}

      <LowerThird
        headline={props.headline}
        headlineItems={props.headlineItems}
        sourceLabel={props.sourceLabel}
        sourceDate={props.sourceDate}
        logo={props.logo}
      />
    </AbsoluteFill>
  );
};
