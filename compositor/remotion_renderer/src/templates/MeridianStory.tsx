import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ChannelBrandFrame } from "../components/ChannelBrandFrame";
import { DesignCanvas } from "../components/DesignCanvas";
import { MeridianNarratorLayer } from "../components/MeridianNarratorLayer";
import { mediaSrc } from "../components/media";
import type {
  MeridianPresenterCue,
  StoryProps,
  TimedVisual,
  TimelineSegmentProps,
} from "../types";
import { MeridianScene } from "./meridian/MeridianScene";

const meridianFallbackVisual: TimedVisual = {
  publicPath: "placeholders/news-visual-placeholder.svg",
  kind: "image",
  start: 0,
  end: 30,
  fit: "contain",
  contentRole: "fallback",
  sourceLabel: "Meridian",
};

const objectValue = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const cueFor = (segment: TimelineSegmentProps): MeridianPresenterCue => {
  const data = objectValue(segment.overlays.data);
  const configured = objectValue(data.meridian_presenter);
  return {
    pose: String(configured.pose ?? ""),
    placement: configured.placement as MeridianPresenterCue["placement"],
    motion: configured.motion as MeridianPresenterCue["motion"],
    width: Number(configured.width) || undefined,
    x: Number(configured.x) || undefined,
    y: Number(configured.y) || undefined,
    scale: Number(configured.scale) || undefined,
    rotate: Number(configured.rotate) || undefined,
  };
};

const cueForScene = (
  segments: TimelineSegmentProps[],
  elapsedSeconds: number,
  activeSegment: TimelineSegmentProps,
): MeridianPresenterCue => {
  const base = cueFor(activeSegment);
  const poseEvents = segments
    .flatMap((segment) => segment.internalEvents ?? [])
    .filter(
      (event) =>
        event.type === "change_pose" &&
        Number.isFinite(event.at) &&
        event.at <= elapsedSeconds,
    )
    .sort((left, right) => left.at - right.at);
  const poseEvent = poseEvents.at(-1);
  if (!poseEvent?.payload) {
    return base;
  }
  const previousEvent = poseEvents.at(-2);
  const previousPose = previousEvent?.payload?.pose
    ? String(previousEvent.payload.pose)
    : poseEvent.at > 0.001
      ? cueFor(segments[0]).pose
      : undefined;
  return {
    ...base,
    pose: poseEvent.payload.pose
      ? String(poseEvent.payload.pose)
      : base.pose,
    previousPose,
    poseChangeAt: poseEvent.at > 0.001 ? poseEvent.at : undefined,
    poseTransitionSeconds:
      Number(poseEvent.payload.transition_seconds) || 0.2,
    poseTransition: (poseEvent.payload.transition ?? "blur") as
      | "cut"
      | "blur"
      | "whip",
    placement: (poseEvent.payload.placement ??
      base.placement) as MeridianPresenterCue["placement"],
    width: Number(poseEvent.payload.width) || base.width,
    x: Number(poseEvent.payload.x) || base.x,
    y: Number(poseEvent.payload.y) || base.y,
    scale: Number(poseEvent.payload.scale) || base.scale,
    rotate: Number(poseEvent.payload.rotate) || base.rotate,
  };
};

const hasRealVisual = (visual?: TimedVisual): visual is TimedVisual =>
  Boolean(
    visual &&
      visual.contentRole !== "fallback" &&
      visual.publicPath !== meridianFallbackVisual.publicPath,
  );

const visualAudioMuted = (segment: TimelineSegmentProps): boolean =>
  segment.audio?.mode !== "source" && segment.audio?.mode !== "mixed";

const visualAudioVolume = (segment: TimelineSegmentProps): number => {
  if (segment.audio?.mode === "source") {
    return segment.audio.sourceVolume ?? 1;
  }
  if (segment.audio?.mode === "mixed") {
    return segment.audio.sourceVolume ?? 0.38;
  }
  return 0;
};

type MeridianSceneRun = {
  runId: string;
  start: number;
  end: number;
  duration: number;
  segments: TimelineSegmentProps[];
};

const sameOptionalNumber = (
  left: number | undefined,
  right: number | undefined,
): boolean => Number(left ?? 0) === Number(right ?? 0);

const sameVisual = (
  left?: TimedVisual,
  right?: TimedVisual,
): boolean => {
  if (!left || !right) {
    return !left && !right;
  }
  return (
    left.publicPath === right.publicPath &&
    left.kind === right.kind &&
    left.candidateId === right.candidateId &&
    left.contentRole === right.contentRole &&
    left.sourceUrl === right.sourceUrl &&
    sameOptionalNumber(left.trimStart, right.trimStart) &&
    sameOptionalNumber(left.trimEnd, right.trimEnd)
  );
};

const canContinueSceneRun = (
  previous: TimelineSegmentProps,
  next: TimelineSegmentProps,
): boolean => {
  const contiguous = Math.abs(previous.end - next.start) <= 0.075;
  if (!contiguous || previous.audio?.mode === "source") {
    return false;
  }
  if (previous.sceneId || next.sceneId) {
    return Boolean(
      previous.sceneId &&
        next.sceneId &&
        previous.sceneId === next.sceneId &&
        previous.template.templateId === next.template.templateId,
    );
  }
  return (
    previous.sectionId === next.sectionId &&
    previous.template.templateId === next.template.templateId &&
    previous.template.layout === next.template.layout &&
    previous.audio?.mode === next.audio?.mode &&
    sameVisual(previous.visual, next.visual)
  );
};

/**
 * Keep a Meridian scene mounted while adjacent narration beats use the same
 * authored section, template, and visual. Text and presenter cues can still
 * change inside the run, but scene entrance and media motion use one continuous
 * frame clock instead of restarting for every sentence.
 */
export const groupMeridianSceneRuns = (
  segments: TimelineSegmentProps[],
): MeridianSceneRun[] => {
  const runs: MeridianSceneRun[] = [];
  for (const segment of segments) {
    const current = runs[runs.length - 1];
    const previous = current?.segments[current.segments.length - 1];
    if (current && previous && canContinueSceneRun(previous, segment)) {
      current.segments.push(segment);
      current.end = segment.end;
      current.duration = Math.max(0.01, current.end - current.start);
      continue;
    }
    runs.push({
      runId: segment.sceneId || `${segment.segmentId}-scene`,
      start: segment.start,
      end: segment.end,
      duration: Math.max(0.01, segment.end - segment.start),
      segments: [segment],
    });
  }
  return runs;
};

const MeridianCanvas: React.FC<{
  run: MeridianSceneRun;
  story: StoryProps;
}> = ({ run, story }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const durationInFrames = Math.max(1, Math.round(run.duration * fps));
  const progress = Math.max(0, Math.min(1, frame / durationInFrames));
  const elapsedSeconds = frame / fps;
  const absoluteSecond = Math.min(
    Math.max(run.start, run.start + elapsedSeconds),
    Math.max(run.start, run.end - 0.0001),
  );
  const segment =
    run.segments.find(
      (candidate) =>
        absoluteSecond >= candidate.start && absoluteSecond < candidate.end,
    ) ?? run.segments[run.segments.length - 1];
  const firstSegment = run.segments[0];
  const visual = firstSegment.visual ?? meridianFallbackVisual;
  const realVisual = hasRealVisual(firstSegment.visual);
  const presenterVisible =
    Boolean(story.presenter) &&
    segment.anchor.visible &&
    segment.audio?.mode !== "source";
  const source = (
    visual.attributionText ||
    visual.sourceLabel ||
    visual.sourceDomain ||
    ""
  ).trim();
  const sourceReveal = interpolate(frame, [8, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const presenterCue = cueForScene(run.segments, elapsedSeconds, segment);

  return (
    <AbsoluteFill
      style={{
        overflow: "hidden",
        background:
          "radial-gradient(circle at 74% 26%, rgba(213,169,78,.18), transparent 35%), linear-gradient(135deg, #eee8dc 0%, #d9ddcf 52%, #bbc8b9 100%)",
        color: "#111514",
      }}
    >
      {story.presenter?.provider === "png_puppet" &&
      story.narrationAudio &&
      firstSegment.audio?.mode !== "source" &&
      firstSegment.audio?.mode !== "silent" ? (
        <Audio
          src={mediaSrc(story.narrationAudio)}
          startFrom={Math.round(
            (firstSegment.narrationStart ?? firstSegment.start) * fps,
          )}
          volume={firstSegment.audio?.narrationVolume ?? 1}
        />
      ) : null}

      <MeridianScene
        segment={segment}
        sceneSegments={run.segments}
        sceneElapsed={elapsedSeconds}
        presenterCue={presenterCue}
        presenterVisible={presenterVisible}
        visual={{
          ...visual,
          start: 0,
          end: Math.max(0.1, run.duration),
        }}
        progress={progress}
        muted={visualAudioMuted(firstSegment)}
        volume={visualAudioVolume(firstSegment)}
      />

      {presenterVisible && story.presenter ? (
        <MeridianNarratorLayer
          presenter={story.presenter}
          cue={presenterCue}
          durationInFrames={durationInFrames}
        />
      ) : null}

      {source && realVisual ? (
        <div
          style={{
            position: "absolute",
            right: 34,
            top: 28,
            zIndex: 45,
            maxWidth: 620,
            color: realVisual
              ? "rgba(255,255,255,.76)"
              : "rgba(41,51,46,.7)",
            fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
            fontSize: 24,
            fontWeight: 700,
            letterSpacing: ".08em",
            textTransform: "uppercase",
            opacity: sourceReveal,
            textShadow: realVisual ? "0 1px 5px rgba(0,0,0,.5)" : undefined,
          }}
        >
          {source}
        </div>
      ) : null}

      <div
        style={{
          position: "absolute",
          right:
            presenterVisible &&
            (!presenterCue.placement || presenterCue.placement.includes("right"))
              ? undefined
              : 28,
          left:
            presenterVisible &&
            (!presenterCue.placement || presenterCue.placement.includes("right"))
              ? 28
              : undefined,
          bottom: 24,
          zIndex: 50,
          fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
          fontSize: 24,
          fontWeight: 850,
          letterSpacing: ".18em",
          textTransform: "uppercase",
          color: realVisual
            ? "rgba(255,255,255,.72)"
            : "rgba(244,239,223,.72)",
          textShadow: realVisual ? "0 2px 12px rgba(0,0,0,.42)" : undefined,
        }}
      >
        Meridian
      </div>
    </AbsoluteFill>
  );
};

export const MeridianStory: React.FC<StoryProps> = (props) => {
  const { fps } = useVideoConfig();
  const segments = props.timelineSegments ?? [];
  const sceneRuns = groupMeridianSceneRuns(segments);
  return (
    <ChannelBrandFrame story={props}>
      <DesignCanvas background="#d9ddcf">
        <AbsoluteFill style={{ background: "#d9ddcf" }}>
          {props.backgroundMusic ? (
            <Audio
              src={mediaSrc(props.backgroundMusic)}
              volume={props.backgroundMusicVolume ?? 0.075}
            />
          ) : null}
          {(props.soundEffects ?? []).map((effect, index) => (
            <Sequence
              key={`${effect.media.publicPath}-${index}`}
              from={Math.round(effect.start * fps)}
            >
              <Audio
                src={mediaSrc(effect.media)}
                volume={effect.volume ?? 0.16}
              />
            </Sequence>
          ))}
          {sceneRuns.map((run) => {
            const startFrame = Math.round(run.start * fps);
            const endFrame = Math.round(run.end * fps);
            return (
              <Sequence
                key={run.runId}
                from={startFrame}
                durationInFrames={Math.max(1, endFrame - startFrame)}
              >
                <MeridianCanvas run={run} story={props} />
              </Sequence>
            );
          })}
        </AbsoluteFill>
      </DesignCanvas>
    </ChannelBrandFrame>
  );
};
