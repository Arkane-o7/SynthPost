import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {SourceLabel} from '../../components/SourceLabel';
import {VisualMediaLayer} from '../../components/VisualMediaLayer';
import {brand, layout, typography} from '../../styles/brand';
import type {TimedVisual, TimelineSegmentProps} from '../../types';

type Props = {
  segment: TimelineSegmentProps;
  storySourceLabel: string;
  storySourceDate: string;
  visual: TimedVisual;
  progress: number;
};

const data = (segment: TimelineSegmentProps): Record<string, unknown> => segment.overlays.data ?? {};
const strings = (value: unknown): string[] => Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
const title = (segment: TimelineSegmentProps, fallback: string): string => String(data(segment).title ?? segment.overlays.chyron ?? segment.overlays.lowerThird ?? fallback);

const CardBase: React.FC<{eyebrow: string; title: string; children: React.ReactNode}> = ({eyebrow, title, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const reveal = interpolate(frame, [0, fps * 0.45], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{background: 'linear-gradient(120deg, #020610, #07182c 55%, #050a14)', color: brand.white, overflow: 'hidden', padding: 74}}>
      <AbsoluteFill style={{opacity: 0.16, background: 'radial-gradient(circle at 18% 12%, rgba(228,28,35,.42), transparent 28%), radial-gradient(circle at 82% 18%, rgba(245,247,250,.14), transparent 24%), repeating-linear-gradient(90deg, rgba(245,247,250,.07) 0 1px, transparent 1px 96px)'}} />
      <div style={{position: 'relative', zIndex: 2, transform: `translateY(${(1 - reveal) * 22}px)`, opacity: reveal}}>
        <div style={{fontFamily: typography.sans, color: brand.red, fontSize: 18, fontWeight: 900, letterSpacing: 2, textTransform: 'uppercase', marginBottom: 18}}>{eyebrow}</div>
        <h2 style={{fontFamily: typography.serif, fontSize: 74, lineHeight: 0.98, fontWeight: 400, margin: 0, maxWidth: 1280, textTransform: 'uppercase'}}>{title}</h2>
        <div style={{marginTop: 42}}>{children}</div>
      </div>
    </AbsoluteFill>
  );
};

export const ChartExplainer: React.FC<Props> = ({segment}) => {
  const values = Array.isArray(data(segment).values) ? (data(segment).values as Array<Record<string, unknown>>) : [];
  const fallback = strings(data(segment).bullets);
  return (
    <CardBase eyebrow="Chart Explainer" title={title(segment, 'What the numbers show')}>
      <div style={{display: 'flex', alignItems: 'flex-end', gap: 26, height: 430, maxWidth: 1260}}>
        {(values.length ? values : fallback.map((label, index) => ({label, value: 45 + index * 14}))).slice(0, 7).map((item, index) => {
          const numeric = Math.max(8, Math.min(100, Number(item.value ?? 30 + index * 10)));
          return (
            <div key={index} style={{flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 16}}>
              <div style={{height: `${numeric}%`, background: `linear-gradient(180deg, ${brand.red}, rgba(228,28,35,.38))`, boxShadow: '0 18px 44px rgba(228,28,35,.22)'}} />
              <div style={{fontFamily: typography.sans, fontSize: 20, fontWeight: 900, color: 'rgba(245,247,250,.82)'}}>{String(item.label ?? `Item ${index + 1}`)}</div>
            </div>
          );
        })}
      </div>
    </CardBase>
  );
};

export const MapExplainer: React.FC<Props> = ({segment}) => {
  const locations = strings(data(segment).locations).slice(0, 5);
  return (
    <CardBase eyebrow="Map Explainer" title={title(segment, 'Where this is happening')}>
      <div style={{display: 'grid', gridTemplateColumns: '1.1fr .9fr', gap: 46, alignItems: 'center'}}>
        <div style={{height: 460, border: '1px solid rgba(245,247,250,.22)', background: 'radial-gradient(circle at 35% 38%, rgba(245,247,250,.18), transparent 12%), radial-gradient(circle at 62% 56%, rgba(228,28,35,.52), transparent 8%), linear-gradient(135deg, rgba(245,247,250,.08), rgba(245,247,250,.02))', position: 'relative', overflow: 'hidden'}}>
          <div style={{position: 'absolute', inset: 0, opacity: .22, background: 'repeating-linear-gradient(0deg, transparent 0 42px, rgba(245,247,250,.16) 43px), repeating-linear-gradient(90deg, transparent 0 54px, rgba(245,247,250,.10) 55px)'}} />
          <div style={{position: 'absolute', left: '58%', top: '49%', width: 28, height: 28, borderRadius: 999, background: brand.red, boxShadow: '0 0 0 16px rgba(228,28,35,.18), 0 0 58px rgba(228,28,35,.6)'}} />
        </div>
        <div style={{display: 'flex', flexDirection: 'column', gap: 18}}>
          {(locations.length ? locations : ['Primary location', 'Regional context', 'Affected area']).map((item, index) => (
            <div key={index} style={{fontFamily: typography.sans, fontSize: 30, fontWeight: 900, borderLeft: `6px solid ${brand.red}`, paddingLeft: 18, color: brand.white}}>{item}</div>
          ))}
        </div>
      </div>
    </CardBase>
  );
};

export const TimelineExplainer: React.FC<Props> = ({segment}) => {
  const events = Array.isArray(data(segment).events) ? (data(segment).events as Array<Record<string, unknown>>) : [];
  const items = events.length ? events : strings(data(segment).bullets).map((label, index) => ({date: `T+${index}`, text: label}));
  return (
    <CardBase eyebrow="Timeline" title={title(segment, 'How the story unfolded')}>
      <div style={{display: 'flex', flexDirection: 'column', gap: 22, maxWidth: 1260}}>
        {items.slice(0, 6).map((item, index) => (
          <div key={index} style={{display: 'grid', gridTemplateColumns: '180px 1fr', gap: 28, alignItems: 'center'}}>
            <div style={{fontFamily: typography.sans, fontSize: 22, color: brand.red, fontWeight: 900, textTransform: 'uppercase'}}>{String(item.date ?? `Step ${index + 1}`)}</div>
            <div style={{fontFamily: typography.serif, fontSize: 38, color: brand.white, lineHeight: 1.08, borderBottom: '1px solid rgba(245,247,250,.16)', paddingBottom: 16}}>{String(item.text ?? item.label ?? '')}</div>
          </div>
        ))}
      </div>
    </CardBase>
  );
};

export const ComparisonCard: React.FC<Props> = ({segment}) => {
  const left = data(segment).left as Record<string, unknown> | undefined;
  const right = data(segment).right as Record<string, unknown> | undefined;
  const renderColumn = (label: string, payload?: Record<string, unknown>) => (
    <div style={{border: '1px solid rgba(245,247,250,.18)', background: 'rgba(245,247,250,.05)', padding: 34, minHeight: 360}}>
      <div style={{fontFamily: typography.sans, color: brand.red, fontSize: 18, fontWeight: 900, textTransform: 'uppercase', marginBottom: 18}}>{String(payload?.title ?? label)}</div>
      {strings(payload?.bullets ?? data(segment).bullets).slice(0, 4).map((item, index) => (
        <div key={index} style={{fontFamily: typography.serif, color: brand.white, fontSize: 34, lineHeight: 1.12, marginBottom: 18}}>— {item}</div>
      ))}
    </div>
  );
  return (
    <CardBase eyebrow="Comparison" title={title(segment, 'The contrast that matters')}>
      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 34, maxWidth: 1320}}>{renderColumn('Side A', left)}{renderColumn('Side B', right)}</div>
    </CardBase>
  );
};

export const BulletSummary: React.FC<Props> = ({segment}) => {
  const bullets = strings(data(segment).bullets).length ? strings(data(segment).bullets) : [segment.scriptText];
  return (
    <CardBase eyebrow="Summary" title={title(segment, 'What to know')}>
      <div style={{display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 1220}}>
        {bullets.slice(0, 5).map((item, index) => (
          <div key={index} style={{display: 'grid', gridTemplateColumns: '56px 1fr', gap: 20, alignItems: 'start'}}>
            <div style={{width: 42, height: 42, borderRadius: 999, background: brand.red, display: 'grid', placeItems: 'center', fontFamily: typography.sans, fontWeight: 900}}>{index + 1}</div>
            <div style={{fontFamily: typography.serif, fontSize: 44, lineHeight: 1.06, color: brand.white}}>{item}</div>
          </div>
        ))}
      </div>
    </CardBase>
  );
};

export const SourceScreenshot: React.FC<Props> = ({segment, visual, progress, storySourceLabel, storySourceDate}) => (
  <AbsoluteFill style={{background: brand.ink, color: brand.white, padding: 74}}>
    <div style={{position: 'absolute', left: 92, right: 92, top: 110, bottom: 190, border: '1px solid rgba(245,247,250,.22)', background: 'rgba(245,247,250,.03)', overflow: 'hidden', boxShadow: '0 30px 90px rgba(0,0,0,.42)'}}>
      <VisualMediaLayer visual={visual} progress={progress} muted volume={0} mediaStyle={{objectFit: 'contain', background: '#050a14'}} />
    </div>
    <SourceLabel label={segment.overlays.attribution || visual.sourceLabel || storySourceLabel} date={storySourceDate} left={92} bottom={layout.lower.height + 42} />
  </AbsoluteFill>
);

export const FallbackContextCard: React.FC<Props> = ({segment}) => (
  <CardBase eyebrow="Context" title={title(segment, segment.overlays.lowerThird || 'Context') }>
    <p style={{fontFamily: typography.serif, fontSize: 48, lineHeight: 1.16, maxWidth: 1160, color: 'rgba(245,247,250,.9)', margin: 0}}>{segment.scriptText}</p>
  </CardBase>
);
