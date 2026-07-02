import React from 'react';
import {AbsoluteFill, interpolate, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {AnchorVideoLayer} from '../components/AnchorVideoLayer';
import {SourceLabel} from '../components/SourceLabel';
import {VisualMediaLayer} from '../components/VisualMediaLayer';
import {brand, fullAnchorCrop, layout, typography} from '../styles/brand';
import type {StoryProps, TimedVisual, TimelineSegmentProps} from '../types';

const fallbackVisual: TimedVisual = {
  publicPath: 'placeholders/news-visual-placeholder.svg',
  kind: 'image',
  start: 0,
  end: 30,
  fit: 'cover',
  sourceLabel: 'SYNTHPOST',
};

const segmentVisual = (segment: TimelineSegmentProps): TimedVisual => segment.visual ?? fallbackVisual;
const visualMuted = (segment: TimelineSegmentProps): boolean => segment.visual?.kind !== 'video' || segment.visual?.audio === false;

const SegmentLowerThird: React.FC<{segment: TimelineSegmentProps; sourceLabel: string; sourceDate: string}> = ({segment, sourceLabel, sourceDate}) => (
  <div
    style={{
      position: 'absolute',
      left: layout.lower.left,
      right: 54,
      bottom: 42,
      minHeight: 118,
      background: 'linear-gradient(90deg, rgba(2,8,16,0.98), rgba(8,20,36,0.92))',
      borderTop: '1px solid rgba(245,247,250,0.28)',
      boxShadow: '0 -18px 58px rgba(0,0,0,0.34)',
      padding: '22px 28px',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      gap: 10,
    }}
  >
    <div style={{fontFamily: typography.sans, fontSize: 15, fontWeight: 900, letterSpacing: 1.2, color: brand.red, textTransform: 'uppercase'}}>
      {sourceLabel} · {sourceDate}
    </div>
    <div style={{fontFamily: typography.serif, fontSize: 42, lineHeight: 1.05, color: brand.white, textTransform: 'uppercase'}}>
      {segment.overlays.chyron || segment.overlays.lowerThird || segment.sectionId.replace(/_/g, ' ')}
    </div>
  </div>
);

const QuoteCard: React.FC<{segment: TimelineSegmentProps}> = ({segment}) => (
  <AbsoluteFill style={{display: 'grid', placeItems: 'center', padding: 120}}>
    <div style={{maxWidth: 1180, borderLeft: `10px solid ${brand.red}`, padding: '34px 46px', background: 'rgba(2,8,16,0.72)', boxShadow: '0 28px 80px rgba(0,0,0,0.32)'}}>
      <div style={{fontSize: 34, color: brand.red, fontFamily: typography.sans, fontWeight: 900, marginBottom: 20}}>QUOTE</div>
      <div style={{fontSize: 64, lineHeight: 1.05, fontFamily: typography.serif, color: brand.white}}>
        “{segment.overlays.quoteText || segment.scriptText}”
      </div>
      <div style={{marginTop: 28, color: 'rgba(245,247,250,0.72)', fontSize: 24, fontFamily: typography.sans, fontWeight: 800}}>
        {segment.overlays.attribution || segment.visual?.attributionText || 'Source attribution pending'}
      </div>
    </div>
  </AbsoluteFill>
);

const DocumentCallout: React.FC<{segment: TimelineSegmentProps; progress: number}> = ({segment, progress}) => {
  const visual = segmentVisual(segment);
  return (
    <AbsoluteFill style={{padding: 74, display: 'grid', gridTemplateColumns: '1.2fr .8fr', gap: 44, alignItems: 'center'}}>
      <div style={{height: '82%', border: '1px solid rgba(245,247,250,0.24)', background: 'rgba(245,247,250,0.04)', boxShadow: '0 28px 80px rgba(0,0,0,0.36)', overflow: 'hidden'}}>
        <VisualMediaLayer visual={visual} progress={progress} muted volume={0} mediaStyle={{objectFit: 'contain', background: '#08101c'}} />
      </div>
      <div>
        <div style={{fontFamily: typography.sans, color: brand.red, fontWeight: 900, fontSize: 18, letterSpacing: 1.8, textTransform: 'uppercase', marginBottom: 18}}>
          Document Callout
        </div>
        <h2 style={{fontFamily: typography.serif, fontSize: 62, lineHeight: 1.02, color: brand.white, fontWeight: 400}}>
          {segment.overlays.lowerThird || segment.overlays.chyron || 'What the source document says'}
        </h2>
        <p style={{marginTop: 24, fontFamily: typography.sans, fontSize: 24, lineHeight: 1.45, color: 'rgba(245,247,250,0.74)'}}>{segment.scriptText}</p>
        <div style={{marginTop: 26, color: 'rgba(245,247,250,0.58)', fontSize: 18}}>Source: {segment.overlays.documentSource || segment.visual?.sourceLabel || 'editor approved source'}</div>
      </div>
    </AbsoluteFill>
  );
};

const Segment: React.FC<{segment: TimelineSegmentProps; story: StoryProps}> = ({segment, story}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const localFrame = frame - Math.round(segment.start * fps);
  const progress = Math.max(0, Math.min(1, localFrame / Math.max(1, Math.round(segment.duration * fps))));
  const visual = segmentVisual(segment);
  const template = segment.template.templateId;
  const fade = interpolate(localFrame, [0, Math.round(fps * 0.3)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const showAnchor = segment.anchor.visible && story.anchor;
  const muteAnchor = !segment.anchor.speaking;

  return (
    <AbsoluteFill style={{opacity: fade, background: 'linear-gradient(115deg, #020610, #07182c 52%, #04070d)', color: brand.white, overflow: 'hidden'}}>
      <AbsoluteFill style={{opacity: 0.12, background: 'repeating-linear-gradient(90deg, rgba(245,247,250,.08) 0 1px, transparent 1px 96px), repeating-linear-gradient(0deg, rgba(245,247,250,.04) 0 1px, transparent 1px 96px)', mixBlendMode: 'screen'}} />

      {template === 'quote_card' ? <QuoteCard segment={segment} /> : null}
      {template === 'document_callout' ? <DocumentCallout segment={segment} progress={progress} /> : null}

      {template === 'fullscreen_news_visual' ? (
        <AbsoluteFill>
          <VisualMediaLayer visual={visual} progress={progress} muted={visualMuted(segment)} volume={segment.visual?.volume ?? 1} mediaStyle={{filter: 'saturate(.94) contrast(1.03) brightness(.96)'}} />
          <SourceLabel label={visual.sourceLabel || story.sourceLabel} date={story.sourceDate} left={54} bottom={layout.lower.height + 42} />
        </AbsoluteFill>
      ) : null}

      {template === 'split_anchor_visual' ? (
        <>
          {showAnchor ? (
            <AnchorVideoLayer anchor={story.anchor} chromaKey={story.anchorChromaKey} crop={fullAnchorCrop} muted={muteAnchor} startFrom={Math.round(segment.start * fps)} style={{left: 54, top: 74, width: 650, height: 780, border: '1px solid rgba(245,247,250,.18)'}} />
          ) : null}
          <div style={{position: 'absolute', left: showAnchor ? 760 : 74, top: 74, right: 54, bottom: 210, border: '1px solid rgba(245,247,250,.18)', overflow: 'hidden', background: brand.ink}}>
            <VisualMediaLayer visual={visual} progress={progress} muted={visualMuted(segment)} volume={segment.visual?.volume ?? 0} />
          </div>
        </>
      ) : null}

      {(template === 'fullscreen_anchor' || template === 'fallback_anchor') && story.anchor ? (
        <AnchorVideoLayer anchor={story.anchor} chromaKey={story.anchorChromaKey} crop={fullAnchorCrop} muted={muteAnchor} startFrom={Math.round(segment.start * fps)} mediaFilter="saturate(.92) contrast(1.03) brightness(.88)" overlay="linear-gradient(180deg, rgba(2,8,16,.04), rgba(2,8,16,.68))" style={{left: 0, top: 0, width: '100%', height: '100%'}} />
      ) : null}

      <SegmentLowerThird segment={segment} sourceLabel={story.sourceLabel} sourceDate={story.sourceDate} />
    </AbsoluteFill>
  );
};

export const TimelineStory: React.FC<StoryProps> = (props) => {
  const {fps} = useVideoConfig();
  const segments = props.timelineSegments && props.timelineSegments.length ? props.timelineSegments : [];
  if (!segments.length) {
    return <AbsoluteFill style={{background: brand.navy}} />;
  }
  return (
    <AbsoluteFill style={{background: brand.navy}}>
      {segments.map((segment) => (
        <Sequence key={segment.segmentId} from={Math.round(segment.start * fps)} durationInFrames={Math.max(1, Math.round(segment.duration * fps))}>
          <Segment segment={segment} story={props} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
