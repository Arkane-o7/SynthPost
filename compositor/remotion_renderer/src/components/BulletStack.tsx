import React from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {brand, typography} from '../styles/brand';
import type {NewsPoint} from '../types';

export const BulletStack: React.FC<{points: NewsPoint[]}> = ({points}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const second = frame / fps;
  const visible = points.filter((point) => second + 0.15 >= point.start);
  const selected = visible.length ? visible.slice(-3) : points.slice(0, 2);

  return (
    <div style={{display: 'flex', gap: 14, alignItems: 'stretch', width: '100%'}}>
      {selected.map((point, index) => {
        const opacity = interpolate(frame, [point.start * fps, point.start * fps + 10], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        return (
          <div
            key={`${point.text}-${index}`}
            style={{
              flex: 1,
              minWidth: 0,
              opacity,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              color: brand.muted,
              fontFamily: typography.sans,
              fontSize: 22,
              lineHeight: 1.18,
              letterSpacing: 0,
              textTransform: 'uppercase',
            }}
          >
            <span
              style={{
                width: 8,
                height: 42,
                flex: '0 0 auto',
                backgroundColor: index === selected.length - 1 ? brand.yellow : brand.signalBlue,
              }}
            />
            <span>{point.text}</span>
          </div>
        );
      })}
    </div>
  );
};
