import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {brand, typography} from '../styles/brand';
import {ENDSCREEN_SAFE_ZONES, ENDSCREEN_HEIGHT, ENDSCREEN_WIDTH, endscreenStyles} from './endscreenStyles';
import {NormalizedEndscreenProps, normalizeEndscreenProps} from './endscreen.schema';

const videoExtensions = new Set(['.mp4', '.mov', '.webm', '.mkv']);

const isRemote = (value: string): boolean => /^https?:\/\//i.test(value);

const sourceFor = (value: string): string => (isRemote(value) ? value : staticFile(value));

const isVideo = (value: string | undefined): boolean => {
  if (!value) {
    return false;
  }
  const pathPart = isRemote(value) ? new URL(value).pathname : value;
  const extension = pathPart.slice(pathPart.lastIndexOf('.')).toLowerCase();
  return videoExtensions.has(extension);
};

const clamp = (value: number): number => Math.max(0, Math.min(1, value));

const seconds = (frame: number, fps: number): number => frame / fps;

const fadeIn = (time: number, start: number, end: number): number =>
  interpolate(time, [start, end], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

const drawWidth = (time: number, start: number, end: number): string => `${fadeIn(time, start, end) * 100}%`;

const Background: React.FC<{props: NormalizedEndscreenProps; time: number}> = ({props, time}) => {
  const background = props.backgroundVisual;
  const backgroundOpacity = fadeIn(time, 0, 1.5) * 0.28;
  return (
    <AbsoluteFill style={{backgroundColor: brand.navy}}>
      {background ? (
        isVideo(background) ? (
          <OffthreadVideo
            muted
            src={sourceFor(background)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              filter: 'saturate(0.72) contrast(1.05) brightness(0.46)',
              opacity: backgroundOpacity,
            }}
          />
        ) : (
          <Img
            src={sourceFor(background)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              filter: 'saturate(0.72) contrast(1.05) brightness(0.46)',
              opacity: backgroundOpacity,
            }}
          />
        )
      ) : null}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(circle at 74% 42%, rgba(31,123,255,0.20) 0%, rgba(7,27,51,0.14) 28%, transparent 58%), linear-gradient(110deg, #020610 0%, #050A14 44%, #071B33 100%)',
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.26,
          background:
            `repeating-linear-gradient(90deg, ${endscreenStyles.gridColor} 0 1px, transparent 1px 96px), repeating-linear-gradient(0deg, rgba(245,247,250,0.038) 0 1px, transparent 1px 96px)`,
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.16,
          background:
            'linear-gradient(90deg, transparent 0%, rgba(31,123,255,0.16) 45%, transparent 54%), repeating-linear-gradient(118deg, transparent 0 22px, rgba(245,247,250,0.05) 22px 23px, transparent 23px 84px)',
          transform: `translateX(${interpolate(time % 8, [0, 8], [-220, 260])}px)`,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg, rgba(2,6,16,0.24) 0%, transparent 42%, rgba(2,6,16,0.48) 100%), linear-gradient(90deg, rgba(2,6,16,0.72) 0%, transparent 52%, rgba(2,6,16,0.16) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};

const SignalLine: React.FC<{time: number; start: number; top: number; width: number}> = ({time, start, top, width}) => {
  return (
    <div
      style={{
        position: 'absolute',
        left: 84,
        top,
        width,
        height: 2,
        overflow: 'hidden',
        backgroundColor: 'rgba(245,247,250,0.12)',
      }}
    >
      <div
        style={{
          width: drawWidth(time, start, start + 1.2),
          height: '100%',
          background: `linear-gradient(90deg, ${brand.signalBlue}, rgba(31,123,255,0.18))`,
          boxShadow: `0 0 20px ${brand.signalBlue}`,
        }}
      />
    </div>
  );
};

const AnchorWindow: React.FC<{props: NormalizedEndscreenProps; time: number}> = ({props, time}) => {
  if (!props.anchorVideo) {
    return null;
  }
  const opacity = clamp(fadeIn(time, 0.8, 1.8) * (1 - fadeIn(time, 7.4, 9)));
  if (opacity <= 0.01) {
    return null;
  }
  return (
    <div
      style={{
        position: 'absolute',
        left: 86,
        top: 420,
        width: 540,
        height: 304,
        overflow: 'hidden',
        opacity,
        border: '1px solid rgba(245,247,250,0.28)',
        boxShadow: '0 20px 60px rgba(0,0,0,0.38)',
        backgroundColor: brand.ink,
      }}
    >
      <OffthreadVideo
        src={sourceFor(props.anchorVideo)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          filter: 'saturate(0.86) contrast(1.04) brightness(0.72)',
        }}
      />
    </div>
  );
};

const BrandColumn: React.FC<{props: NormalizedEndscreenProps; time: number}> = ({props, time}) => {
  const logoOpacity = fadeIn(time, 5.8, 7.2);
  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: 84,
          top: 132,
          color: brand.signalBlue,
          fontFamily: typography.sans,
          fontSize: 18,
          fontWeight: 800,
          letterSpacing: 0,
          textTransform: 'uppercase',
          opacity: fadeIn(time, 0, 1.2),
        }}
      >
        SYNTHPOST SIGNAL
      </div>
      <h1
        style={{
          position: 'absolute',
          left: 80,
          top: 166,
          width: 780,
          margin: 0,
          color: brand.white,
          fontFamily: typography.serif,
          fontSize: 66,
          lineHeight: 1.02,
          letterSpacing: 0,
          textTransform: 'uppercase',
          textShadow: '0 18px 44px rgba(0,0,0,0.48)',
          opacity: fadeIn(time, 0.2, 1.4),
          transform: `translateY(${interpolate(time, [0, 1.4], [24, 0], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          })}px)`,
        }}
      >
        {props.ctaText}
      </h1>
      <p
        style={{
          position: 'absolute',
          left: 88,
          top: 312,
          width: 650,
          margin: 0,
          color: brand.muted,
          fontFamily: typography.sans,
          fontSize: 24,
          lineHeight: 1.28,
          letterSpacing: 0,
          textTransform: 'uppercase',
          opacity: fadeIn(time, 1.0, 2.4),
        }}
      >
        {props.bridgeText}
      </p>
      <SignalLine time={time} start={1.1} top={378} width={610} />
      <AnchorWindow props={props} time={time} />
      <div
        style={{
          position: 'absolute',
          left: 84,
          top: 602,
          width: 520,
          opacity: props.anchorVideo ? logoOpacity : fadeIn(time, 2, 3.4),
        }}
      >
        {props.channelLogo ? (
          <Img src={sourceFor(props.channelLogo)} style={{maxWidth: 330, maxHeight: 86, objectFit: 'contain'}} />
        ) : (
          <div
            style={{
              color: brand.white,
              fontFamily: typography.serif,
              fontSize: 72,
              lineHeight: 1,
              letterSpacing: 0,
              textTransform: 'uppercase',
            }}
          >
            SYNTHPOST<span style={{color: brand.signalBlue}}>.</span>
          </div>
        )}
        <div
          style={{
            marginTop: 18,
            color: 'rgba(245,247,250,0.66)',
            fontFamily: typography.sans,
            fontSize: 17,
            fontWeight: 800,
            letterSpacing: 0,
            textTransform: 'uppercase',
          }}
        >
          Subscribe for the next signal
        </div>
      </div>
    </>
  );
};

const SlotMedia: React.FC<{path?: string; fallbackText: string; topic: string}> = ({path, fallbackText, topic}) => {
  if (path) {
    return isVideo(path) ? (
      <OffthreadVideo muted src={sourceFor(path)} style={{width: '100%', height: '100%', objectFit: 'cover', opacity: 0.38}} />
    ) : (
      <Img src={sourceFor(path)} style={{width: '100%', height: '100%', objectFit: 'cover', opacity: 0.42}} />
    );
  }
  return (
    <AbsoluteFill
      style={{
        background:
          'linear-gradient(135deg, rgba(31,123,255,0.20), rgba(7,27,51,0.36)), repeating-linear-gradient(0deg, rgba(245,247,250,0.06) 0 1px, transparent 1px 38px)',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'rgba(245,247,250,0.42)',
        fontFamily: typography.sans,
        fontSize: 24,
        fontWeight: 800,
        textTransform: 'uppercase',
        letterSpacing: 0,
      }}
    >
      <div style={{textAlign: 'center'}}>
        <div>{fallbackText}</div>
        <div style={{marginTop: 10, color: brand.signalBlue, fontSize: 18}}>{topic}</div>
      </div>
    </AbsoluteFill>
  );
};

const VideoSlot: React.FC<{
  label: string;
  title: string;
  thumbnail?: string;
  fallbackText: string;
  topic: string;
  zone: (typeof ENDSCREEN_SAFE_ZONES)[keyof typeof ENDSCREEN_SAFE_ZONES];
  time: number;
  revealStart: number;
}> = ({label, title, thumbnail, fallbackText, topic, zone, time, revealStart}) => {
  const opacity = fadeIn(time, revealStart, revealStart + 1);
  const compactHeader = zone.y < 300;
  const labelTop = compactHeader ? zone.y - 76 : zone.y - 36;
  const titleTop = compactHeader ? zone.y - 42 : zone.y + zone.height + 14;
  const titleFontSize = compactHeader ? 20 : 22;
  const pulse = interpolate((time - revealStart) % 4, [0, 0.6, 4], [0.18, 0.34, 0.18], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: zone.x,
          top: labelTop,
          color: brand.signalBlue,
          fontFamily: typography.sans,
          fontSize: 18,
          fontWeight: 900,
          textTransform: 'uppercase',
          opacity,
        }}
      >
        {label}
      </div>
      <div
        style={{
          position: 'absolute',
          left: zone.x,
          top: zone.y,
          width: zone.width,
          height: zone.height,
          overflow: 'hidden',
          backgroundColor: 'rgba(2,8,16,0.78)',
          border: endscreenStyles.cardBorder,
          boxShadow: `${endscreenStyles.cardShadow}, 0 0 34px rgba(31,123,255,${pulse})`,
          opacity,
        }}
      >
        <SlotMedia path={thumbnail} fallbackText={fallbackText} topic={topic} />
        <AbsoluteFill
          style={{
            background:
              'linear-gradient(180deg, rgba(2,8,16,0.08) 0%, rgba(2,8,16,0.28) 64%, rgba(2,8,16,0.58) 100%)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            height: 3,
            width: drawWidth(time, revealStart, revealStart + 1.2),
            background: `linear-gradient(90deg, ${brand.signalBlue}, rgba(31,123,255,0.1))`,
          }}
        />
      </div>
      <div
        style={{
          position: 'absolute',
          left: zone.x,
          top: titleTop,
          width: zone.width,
          maxHeight: compactHeader ? 40 : 60,
          overflow: 'hidden',
          color: brand.white,
          fontFamily: typography.sans,
          fontSize: titleFontSize,
          fontWeight: 800,
          lineHeight: 1.16,
          letterSpacing: 0,
          textTransform: 'uppercase',
          opacity: opacity * 0.94,
        }}
      >
        {title}
      </div>
    </>
  );
};

const SubscribeZoneGuide: React.FC<{time: number}> = ({time}) => {
  const zone = ENDSCREEN_SAFE_ZONES.subscribe;
  return (
    <div
      style={{
        position: 'absolute',
        left: zone.x,
        top: zone.y,
        width: zone.width,
        height: zone.height,
        borderRadius: '50%',
        border: '1px solid rgba(245,247,250,0.16)',
        boxShadow: `0 0 34px rgba(31,123,255,${0.16 + 0.08 * Math.sin(time * 1.4)})`,
        opacity: fadeIn(time, 6.2, 8.2),
      }}
    />
  );
};

const DebugSafeZones: React.FC = () => {
  const labels: Record<string, string> = {
    primary_video: 'PRIMARY VIDEO',
    secondary_video: 'SECONDARY VIDEO',
    subscribe: 'SUBSCRIBE',
  };
  return (
    <>
      {Object.entries(ENDSCREEN_SAFE_ZONES).map(([name, zone]) => (
        <div
          key={name}
          style={{
            position: 'absolute',
            left: zone.x,
            top: zone.y,
            width: zone.width,
            height: zone.height,
            border: '3px solid rgba(255,216,74,0.86)',
            backgroundColor: 'rgba(255,216,74,0.10)',
            color: brand.yellow,
            fontFamily: typography.sans,
            fontSize: 22,
            fontWeight: 900,
            textTransform: 'uppercase',
            padding: 10,
            pointerEvents: 'none',
          }}
        >
          {labels[name] ?? name}
        </div>
      ))}
    </>
  );
};

const SignalTicker: React.FC<{props: NormalizedEndscreenProps; time: number}> = ({props, time}) => {
  return (
    <div
      style={{
        position: 'absolute',
        left: 80,
        bottom: 50,
        width: ENDSCREEN_WIDTH - 160,
        height: 34,
        display: 'flex',
        alignItems: 'center',
        color: 'rgba(245,247,250,0.56)',
        fontFamily: typography.sans,
        fontSize: 16,
        fontWeight: 800,
        textTransform: 'uppercase',
        letterSpacing: 0,
        opacity: fadeIn(time, 7.2, 9),
        borderTop: '1px solid rgba(245,247,250,0.12)',
      }}
    >
      SYNTHPOST SIGNAL <span style={{color: brand.signalBlue, margin: '0 16px'}}>/</span> {props.episodeTopic}{' '}
      <span style={{color: brand.signalBlue, margin: '0 16px'}}>/</span> NEXT BRIEFING QUEUED
    </div>
  );
};

export const Endscreen: React.FC<Partial<NormalizedEndscreenProps>> = (inputProps) => {
  const props = normalizeEndscreenProps(inputProps);
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const time = seconds(frame, fps);
  const topic = props.episodeTopic.toUpperCase();

  return (
    <AbsoluteFill
      style={{
        width: ENDSCREEN_WIDTH,
        height: ENDSCREEN_HEIGHT,
        overflow: 'hidden',
        backgroundColor: brand.navy,
      }}
    >
      <Background props={props} time={time} />
      <BrandColumn props={props} time={time} />
      <SubscribeZoneGuide time={time} />
      <VideoSlot
        label="Watch next"
        title={props.nextVideoTitle}
        thumbnail={props.nextVideoThumbnail}
        fallbackText="Next signal"
        topic={topic}
        zone={ENDSCREEN_SAFE_ZONES.primary_video}
        time={time}
        revealStart={1.5}
      />
      <VideoSlot
        label="Related analysis"
        title={props.recommendedVideoTitle}
        thumbnail={props.recommendedVideoThumbnail}
        fallbackText="Latest briefing"
        topic="SYNTHPOST"
        zone={ENDSCREEN_SAFE_ZONES.secondary_video}
        time={time}
        revealStart={4.0}
      />
      <SignalTicker props={props} time={time} />
      {props.debugSafeZones ? <DebugSafeZones /> : null}
    </AbsoluteFill>
  );
};
