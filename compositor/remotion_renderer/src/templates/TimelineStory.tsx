import React from "react";
import {
  AbsoluteFill,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { AnchorPanel } from "../components/AnchorPanel";
import { AnchorVideoLayer } from "../components/AnchorVideoLayer";
import { DesignCanvas } from "../components/DesignCanvas";
import { LowerThird } from "../components/LowerThird";
import { NewsVisualPanel } from "../components/NewsVisualPanel";
import { SourceLabel } from "../components/SourceLabel";
import { VisualMediaLayer } from "../components/VisualMediaLayer";
import { getTemplateDefinition } from "../registry/templates";
import { brand, fullAnchorCrop, layout, typography } from "../styles/brand";
import type { StoryProps, TimedVisual, TimelineSegmentProps } from "../types";
import {
  BulletSummary,
  ChartExplainer,
  ComparisonCard,
  FallbackContextCard,
  MapExplainer,
  SourceScreenshot,
  TimelineExplainer,
} from "./explainers/EditorialCards";

const fallbackVisual: TimedVisual = {
  publicPath: "placeholders/news-visual-placeholder.svg",
  kind: "image",
  start: 0,
  end: 30,
  fit: "cover",
  sourceLabel: "SYNTHPOST",
  contentRole: "fallback",
};

const segmentVisual = (segment: TimelineSegmentProps): TimedVisual =>
  segment.visual ?? fallbackVisual;
const visualMuted = (segment: TimelineSegmentProps): boolean => {
  if (segment.audio?.mode === "source" || segment.audio?.mode === "mixed") {
    return false;
  }
  return segment.visual?.kind !== "video" || segment.visual?.audio === false;
};
const sourceVolume = (segment: TimelineSegmentProps): number => {
  if (segment.audio?.mode === "source") {
    return segment.audio.sourceVolume ?? 1;
  }
  if (segment.audio?.mode === "mixed") {
    return segment.audio.sourceVolume ?? segment.visual?.volume ?? 0.45;
  }
  return segment.visual?.volume ?? 0;
};

const relativeSegmentVisual = (
  segment: TimelineSegmentProps,
  visual: TimedVisual,
): TimedVisual => ({
  ...visual,
  start: 0,
  end: Math.max(0.1, segment.duration),
  sourceLabel: visual.sourceLabel || visual.provider || "",
});

const segmentHeadlineItems = (segment: TimelineSegmentProps) => [
  {
    text:
      segment.overlays.chyron ||
      segment.overlays.lowerThird ||
      segment.sectionId.replace(/_/g, " "),
    start: 0,
    end: Math.max(0.1, segment.duration),
  },
];

const RetainedSplitSegment: React.FC<{
  segment: TimelineSegmentProps;
  story: StoryProps;
  visual: TimedVisual;
  mutedAnchor: boolean;
  startFrom: number;
}> = ({ segment, story, visual, mutedAnchor, startFrom }) => (
  <AbsoluteFill
    style={{
      backgroundColor: brand.navy,
      overflow: "hidden",
      color: brand.white,
    }}
  >
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(105deg, #020610 0%, #071B33 42%, #050A14 100%), linear-gradient(0deg, rgba(245,247,250,0.04) 1px, transparent 1px)",
        backgroundSize: "100% 100%, 96px 96px",
      }}
    />
    <AbsoluteFill
      style={{
        opacity: 0.22,
        background:
          "repeating-linear-gradient(90deg, rgba(245,247,250,0.08) 0 1px, transparent 1px 86px), repeating-linear-gradient(0deg, rgba(245,247,250,0.04) 0 1px, transparent 1px 86px)",
        mixBlendMode: "screen",
      }}
    />
    <AnchorPanel
      anchor={story.anchor}
      chromaKey={story.anchorChromaKey}
      muted={mutedAnchor}
      startFrom={startFrom}
    />
    <NewsVisualPanel
      visuals={[relativeSegmentVisual(segment, visual)]}
      sourceLabel={story.sourceLabel}
      sourceDate={story.sourceDate}
    />
    <LowerThird
      headline={story.headline}
      headlineItems={segmentHeadlineItems(segment)}
      sourceLabel={story.sourceLabel}
      sourceDate={story.sourceDate}
      logo={story.logo}
    />
  </AbsoluteFill>
);

const RetainedFullScreenVisualSegment: React.FC<{
  segment: TimelineSegmentProps;
  story: StoryProps;
  visual: TimedVisual;
  progress: number;
}> = ({ segment, story, visual, progress }) => (
  <AbsoluteFill
    style={{
      backgroundColor: brand.ink,
      overflow: "hidden",
      color: brand.white,
    }}
  >
    <VisualMediaLayer
      visual={relativeSegmentVisual(segment, visual)}
      progress={progress}
      muted={visualMuted(segment)}
      volume={sourceVolume(segment)}
      mediaStyle={{
        width: "100%",
        height: "100%",
        objectFit: visual.fit ?? "cover",
        objectPosition: "center center",
        filter: "saturate(0.94) contrast(1.02) brightness(0.96)",
      }}
    />
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(180deg, rgba(2,8,16,0.04) 0%, rgba(2,8,16,0.00) 46%, rgba(2,8,16,0.22) 78%, rgba(2,8,16,0.50) 100%), linear-gradient(90deg, rgba(2,8,16,0.10) 0%, transparent 30%, transparent 74%, rgba(2,8,16,0.14) 100%)",
        pointerEvents: "none",
      }}
    />
    <AbsoluteFill
      style={{
        opacity: 0.1,
        background:
          "repeating-linear-gradient(90deg, rgba(245,247,250,0.08) 0 1px, transparent 1px 110px), repeating-linear-gradient(0deg, rgba(245,247,250,0.04) 0 1px, transparent 1px 110px)",
        mixBlendMode: "screen",
        pointerEvents: "none",
      }}
    />
    <SourceLabel
      label={visual.sourceLabel || story.sourceLabel}
      date={story.sourceDate}
      left={54}
      bottom={layout.lower.height + 42}
    />
    <LowerThird
      headline={story.headline}
      headlineItems={segmentHeadlineItems(segment)}
      sourceLabel={story.sourceLabel}
      sourceDate={story.sourceDate}
      logo={story.logo}
    />
  </AbsoluteFill>
);

const RetainedFullScreenAnchorSegment: React.FC<{
  segment: TimelineSegmentProps;
  story: StoryProps;
  mutedAnchor: boolean;
  startFrom: number;
}> = ({ segment, story, mutedAnchor, startFrom }) => (
  <AbsoluteFill
    style={{
      backgroundColor: brand.navy,
      overflow: "hidden",
      color: brand.white,
    }}
  >
    <AnchorVideoLayer
      anchor={story.anchor}
      chromaKey={story.anchorChromaKey}
      crop={fullAnchorCrop}
      muted={mutedAnchor}
      startFrom={startFrom}
      mediaFilter="saturate(0.92) contrast(1.03) brightness(0.88)"
      overlay="linear-gradient(180deg, rgba(2,8,16,0.10) 0%, rgba(2,8,16,0.04) 44%, rgba(2,8,16,0.42) 78%, rgba(2,8,16,0.68) 100%), linear-gradient(90deg, rgba(2,8,16,0.28) 0%, transparent 26%, transparent 74%, rgba(2,8,16,0.30) 100%)"
      style={{ left: 0, top: 0, width: "100%", height: "100%" }}
    />
    <AbsoluteFill
      style={{
        opacity: 0.12,
        background:
          "repeating-linear-gradient(90deg, rgba(245,247,250,0.08) 0 1px, transparent 1px 110px), repeating-linear-gradient(0deg, rgba(245,247,250,0.04) 0 1px, transparent 1px 110px)",
        mixBlendMode: "screen",
        pointerEvents: "none",
      }}
    />
    <LowerThird
      headline={story.headline}
      headlineItems={segmentHeadlineItems(segment)}
      sourceLabel={story.sourceLabel}
      sourceDate={story.sourceDate}
      logo={story.logo}
    />
  </AbsoluteFill>
);

const SegmentLowerThird: React.FC<{
  segment: TimelineSegmentProps;
  sourceLabel: string;
  sourceDate: string;
}> = ({ segment, sourceLabel, sourceDate }) => (
  <div
    style={{
      position: "absolute",
      left: layout.lower.left,
      right: 54,
      bottom: 42,
      minHeight: 118,
      background:
        "linear-gradient(90deg, rgba(2,8,16,0.98), rgba(8,20,36,0.92))",
      borderTop: "1px solid rgba(245,247,250,0.28)",
      boxShadow: "0 -18px 58px rgba(0,0,0,0.34)",
      padding: "22px 28px",
      display: "flex",
      flexDirection: "column",
      justifyContent: "center",
      gap: 10,
    }}
  >
    <div
      style={{
        fontFamily: typography.sans,
        fontSize: 15,
        fontWeight: 900,
        letterSpacing: 1.2,
        color: brand.red,
        textTransform: "uppercase",
      }}
    >
      {sourceLabel} · {sourceDate}
    </div>
    <div
      style={{
        fontFamily: typography.serif,
        fontSize: 42,
        lineHeight: 1.05,
        color: brand.white,
        textTransform: "uppercase",
      }}
    >
      {segment.overlays.chyron ||
        segment.overlays.lowerThird ||
        segment.sectionId.replace(/_/g, " ")}
    </div>
  </div>
);

const QuoteCard: React.FC<{ segment: TimelineSegmentProps }> = ({
  segment,
}) => (
  <AbsoluteFill style={{ display: "grid", placeItems: "center", padding: 120 }}>
    <div
      style={{
        maxWidth: 1180,
        borderLeft: `10px solid ${brand.red}`,
        padding: "34px 46px",
        background: "rgba(2,8,16,0.72)",
        boxShadow: "0 28px 80px rgba(0,0,0,0.32)",
      }}
    >
      <div
        style={{
          fontSize: 34,
          color: brand.red,
          fontFamily: typography.sans,
          fontWeight: 900,
          marginBottom: 20,
        }}
      >
        QUOTE
      </div>
      <div
        style={{
          fontSize: 64,
          lineHeight: 1.05,
          fontFamily: typography.serif,
          color: brand.white,
        }}
      >
        “{segment.overlays.quoteText || segment.scriptText}”
      </div>
      <div
        style={{
          marginTop: 28,
          color: "rgba(245,247,250,0.72)",
          fontSize: 24,
          fontFamily: typography.sans,
          fontWeight: 800,
        }}
      >
        {segment.overlays.attribution ||
          segment.visual?.attributionText ||
          "Source attribution pending"}
      </div>
    </div>
  </AbsoluteFill>
);

const DocumentCallout: React.FC<{
  segment: TimelineSegmentProps;
  progress: number;
}> = ({ segment, progress }) => {
  const visual = segmentVisual(segment);
  return (
    <AbsoluteFill
      style={{
        padding: 74,
        display: "grid",
        gridTemplateColumns: "1.2fr .8fr",
        gap: 44,
        alignItems: "center",
      }}
    >
      <div
        style={{
          height: "82%",
          border: "1px solid rgba(245,247,250,0.24)",
          background: "rgba(245,247,250,0.04)",
          boxShadow: "0 28px 80px rgba(0,0,0,0.36)",
          overflow: "hidden",
        }}
      >
        <VisualMediaLayer
          visual={visual}
          progress={progress}
          muted
          volume={0}
          mediaStyle={{ objectFit: "contain", background: "#08101c" }}
        />
      </div>
      <div>
        <div
          style={{
            fontFamily: typography.sans,
            color: brand.red,
            fontWeight: 900,
            fontSize: 18,
            letterSpacing: 1.8,
            textTransform: "uppercase",
            marginBottom: 18,
          }}
        >
          Document Callout
        </div>
        <h2
          style={{
            fontFamily: typography.serif,
            fontSize: 62,
            lineHeight: 1.02,
            color: brand.white,
            fontWeight: 400,
          }}
        >
          {segment.overlays.lowerThird ||
            segment.overlays.chyron ||
            "What the source document says"}
        </h2>
        <p
          style={{
            marginTop: 24,
            fontFamily: typography.sans,
            fontSize: 24,
            lineHeight: 1.45,
            color: "rgba(245,247,250,0.74)",
          }}
        >
          {segment.scriptText}
        </p>
        <div
          style={{
            marginTop: 26,
            color: "rgba(245,247,250,0.58)",
            fontSize: 18,
          }}
        >
          Source:{" "}
          {segment.overlays.documentSource ||
            segment.visual?.sourceLabel ||
            "editor approved source"}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Segment: React.FC<{
  segment: TimelineSegmentProps;
  story: StoryProps;
}> = ({ segment, story }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // Inside a Remotion <Sequence>, useCurrentFrame() is already relative to
  // that segment. Keep the anchor video globally offset with startFrom, but do
  // not subtract segment.start here or later segments render invisible/late.
  const localFrame = frame;
  const progress = Math.max(
    0,
    Math.min(1, localFrame / Math.max(1, Math.round(segment.duration * fps))),
  );
  const visual = segmentVisual(segment);
  const template = getTemplateDefinition(
    segment.template.templateId,
  ).template_id;
  const muteAnchor =
    !segment.anchor.speaking ||
    segment.audio?.mode === "source" ||
    segment.audio?.mode === "silent";
  const retainedTemplate = [
    "split_anchor_visual",
    "fullscreen_news_visual",
    "fullscreen_anchor",
    "fallback_anchor",
  ].includes(template);
  const explainerProps = {
    segment,
    storySourceLabel: story.sourceLabel,
    storySourceDate: story.sourceDate,
    visual,
    progress,
  };

  const isCardTemplate = [
    "chart_explainer",
    "map_explainer",
    "timeline_explainer",
    "comparison_card",
    "bullet_summary",
    "source_screenshot",
    "fallback_context_card",
  ].includes(template);
  const standaloneTemplate =
    retainedTemplate ||
    isCardTemplate ||
    template === "quote_card" ||
    template === "document_callout";

  return (
    <DesignCanvas background="linear-gradient(115deg, #020610, #07182c 52%, #04070d)">
      <AbsoluteFill
        style={{
          background: "linear-gradient(115deg, #020610, #07182c 52%, #04070d)",
          color: brand.white,
          overflow: "hidden",
        }}
      >
        <AbsoluteFill
          style={{
            opacity: 0.12,
            background:
              "repeating-linear-gradient(90deg, rgba(245,247,250,.08) 0 1px, transparent 1px 96px), repeating-linear-gradient(0deg, rgba(245,247,250,.04) 0 1px, transparent 1px 96px)",
            mixBlendMode: "screen",
          }}
        />

        {template === "quote_card" ? <QuoteCard segment={segment} /> : null}
        {template === "document_callout" ? (
          <DocumentCallout segment={segment} progress={progress} />
        ) : null}
        {template === "chart_explainer" ? (
          <ChartExplainer {...explainerProps} />
        ) : null}
        {template === "map_explainer" ? (
          <MapExplainer {...explainerProps} />
        ) : null}
        {template === "timeline_explainer" ? (
          <TimelineExplainer {...explainerProps} />
        ) : null}
        {template === "comparison_card" ? (
          <ComparisonCard {...explainerProps} />
        ) : null}
        {template === "bullet_summary" ? (
          <BulletSummary {...explainerProps} />
        ) : null}
        {template === "source_screenshot" ? (
          <SourceScreenshot {...explainerProps} />
        ) : null}
        {template === "fallback_context_card" ? (
          <FallbackContextCard {...explainerProps} />
        ) : null}

        {template === "split_anchor_visual" ? (
          <RetainedSplitSegment
            segment={segment}
            story={story}
            visual={visual}
            mutedAnchor={muteAnchor}
            startFrom={Math.round(segment.start * fps)}
          />
        ) : null}

        {template === "fullscreen_news_visual" ? (
          <RetainedFullScreenVisualSegment
            segment={segment}
            story={story}
            visual={visual}
            progress={progress}
          />
        ) : null}

        {template === "fullscreen_anchor" || template === "fallback_anchor" ? (
          <RetainedFullScreenAnchorSegment
            segment={segment}
            story={story}
            mutedAnchor={muteAnchor}
            startFrom={Math.round(segment.start * fps)}
          />
        ) : null}

        {!standaloneTemplate ? (
          <SegmentLowerThird
            segment={segment}
            sourceLabel={story.sourceLabel}
            sourceDate={story.sourceDate}
          />
        ) : null}
      </AbsoluteFill>
    </DesignCanvas>
  );
};

export const TimelineStory: React.FC<StoryProps> = (props) => {
  const { fps } = useVideoConfig();
  const segments =
    props.timelineSegments && props.timelineSegments.length
      ? props.timelineSegments
      : [];
  if (!segments.length) {
    return <AbsoluteFill style={{ background: brand.navy }} />;
  }
  return (
    <AbsoluteFill style={{ background: brand.navy }}>
      {segments.map((segment) => {
        const startFrame = Math.round(segment.start * fps);
        const endFrame = Math.round(segment.end * fps);
        return (
          <Sequence
            key={segment.segmentId}
            from={startFrame}
            durationInFrames={Math.max(1, endFrame - startFrame)}
          >
            <Segment segment={segment} story={props} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
