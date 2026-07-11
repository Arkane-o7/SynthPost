import React from "react";
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { AnchorPanel } from "../components/AnchorPanel";
import { AnchorVideoLayer } from "../components/AnchorVideoLayer";
import { DesignCanvas } from "../components/DesignCanvas";
import { LowerThird } from "../components/LowerThird";
import { mediaSrc } from "../components/media";
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
  const mode = segment.audio?.mode ?? "narration";
  const sourceHasAudio = Boolean(
    segment.visual?.kind === "video" &&
      (segment.visual.hasAudio ?? segment.visual.audio),
  );
  return !(
    sourceHasAudio &&
    (mode === "source" || mode === "mixed")
  );
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
      segment.overlays.lowerThird ||
      segment.overlays.chyron ||
      segment.sectionId.replace(/_/g, " "),
    start: 0,
    end: Math.max(0.1, segment.duration),
  },
];

const AnchorNarrationTrack: React.FC<{
  anchor?: StoryProps["anchor"];
  startFrom: number;
  enabled: boolean;
  volume: number;
}> = ({ anchor, startFrom, enabled, volume }) => {
  if (!anchor || anchor.kind !== "video" || !enabled) {
    return null;
  }
  return (
    <OffthreadVideo
      src={mediaSrc(anchor)}
      startFrom={startFrom}
      volume={volume}
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        width: 1,
        height: 1,
        opacity: 0,
        pointerEvents: "none",
      }}
    />
  );
};

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
  startFrom: number;
}> = ({ segment, story, visual, progress, startFrom }) => (
  <AbsoluteFill
    style={{
      backgroundColor: brand.ink,
      overflow: "hidden",
      color: brand.white,
    }}
  >
    <AnchorNarrationTrack
      anchor={story.anchor}
      startFrom={startFrom}
      enabled={
        segment.audio?.mode !== "source" &&
        segment.audio?.mode !== "silent"
      }
      volume={segment.audio?.narrationVolume ?? 1}
    />
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

type QuoteLine = {
  text: string;
  emphasis?: boolean;
};

const objectData = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const stringValue = (value: unknown): string =>
  String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();

const quoteLinesFor = (segment: TimelineSegmentProps): QuoteLine[] => {
  const data = objectData(segment.overlays.data);
  if (Array.isArray(data.quoteLines)) {
    const lines = data.quoteLines
      .map((line): QuoteLine | null => {
        if (typeof line === "string") {
          return { text: stringValue(line) };
        }
        const record = objectData(line);
        const text = stringValue(record.text ?? record.line);
        return text ? { text, emphasis: Boolean(record.emphasis) } : null;
      })
      .filter((line): line is QuoteLine => Boolean(line?.text));
    if (lines.length) {
      return lines.slice(0, 4);
    }
  }

  const quote = stringValue(segment.overlays.quoteText || segment.scriptText);
  if (!quote) {
    return [{ text: "Source-backed quote pending" }];
  }
  const words = quote.replace(/[“”"]/g, "").split(" ").filter(Boolean);
  const lines: QuoteLine[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > 24 && current) {
      lines.push({ text: current });
      current = word;
    } else {
      current = next;
    }
  }
  if (current) {
    lines.push({ text: current });
  }
  return lines.slice(0, 4).map((line, index, all) => ({
    ...line,
    emphasis: all.length > 1 && index === Math.min(1, all.length - 1),
  }));
};

const quoteSizeFor = (lines: QuoteLine[]): number => {
  const longest = Math.max(...lines.map((line) => line.text.length), 1);
  if (longest > 36 || lines.length >= 4) {
    return 60;
  }
  if (longest > 28) {
    return 68;
  }
  return 78;
};

const QuoteCard: React.FC<{
  segment: TimelineSegmentProps;
  sourceDate: string;
}> = ({ segment, sourceDate }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const second = frame / fps;
  const data = objectData(segment.overlays.data);
  const lines = quoteLinesFor(segment);
  const quoteSize = Number(data.quoteSize ?? quoteSizeFor(lines));
  const speaker = stringValue(
    data.speaker ?? data.speakerName ?? segment.overlays.attribution,
  );
  const role = stringValue(data.role ?? data.speakerRole ?? "Verified source");
  const sourceName = stringValue(
    data.source ??
      data.sourceName ??
      segment.visual?.sourceLabel ??
      segment.overlays.attribution ??
      "SynthPost editorial desk",
  );
  const date = stringValue(data.date ?? data.publishedDate ?? sourceDate);
  const visual = segment.visual;
  const hasPortrait = Boolean(
    visual &&
    visual.kind === "image" &&
    visual.publicPath !== fallbackVisual.publicPath &&
    visual.contentRole !== "fallback",
  );
  const reveal = (start: number, duration: number): number =>
    interpolate(second, [start, start + duration], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const quoteMarkReveal = reveal(0.16, 0.46);
  const speakerReveal = reveal(1.54, 0.42);
  const sourceReveal = reveal(1.82, 0.44);
  const portraitReveal = reveal(0.04, 0.82);

  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(circle at 78% 38%, rgba(7,27,51,.48), transparent 34%), radial-gradient(circle at 42% 112%, rgba(7,27,51,.72), transparent 55%), linear-gradient(112deg, #020610 0%, #050A14 54%, #040b16 100%)",
        color: brand.white,
        overflow: "hidden",
        isolation: "isolate",
      }}
    >
      <AbsoluteFill
        style={{
          inset: -96,
          opacity: 0.24,
          backgroundImage:
            "linear-gradient(rgba(245,247,250,.085) 1px, transparent 1px), linear-gradient(90deg, rgba(245,247,250,.085) 1px, transparent 1px), linear-gradient(rgba(245,247,250,.026) 1px, transparent 1px), linear-gradient(90deg, rgba(245,247,250,.026) 1px, transparent 1px)",
          backgroundSize: "72px 72px, 72px 72px, 288px 288px, 288px 288px",
          transform: `translate(${(second * 72) / 58}px, ${(second * 72) / 58}px)`,
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.025,
          background:
            "repeating-linear-gradient(to bottom, transparent 0 4px, rgba(245,247,250,.16) 5px)",
          mixBlendMode: "screen",
        }}
      />

      <div
        style={{
          position: "absolute",
          right: 0,
          top: 0,
          bottom: 0,
          width: 900,
          zIndex: 6,
          overflow: "hidden",
          clipPath: `inset(0 0 0 ${100 - portraitReveal * 100}%)`,
          WebkitMaskImage:
            "linear-gradient(90deg, transparent 0%, rgba(0,0,0,.28) 12%, #000 34%, #000 100%)",
          maskImage:
            "linear-gradient(90deg, transparent 0%, rgba(0,0,0,.28) 12%, #000 34%, #000 100%)",
        }}
      >
        {hasPortrait && visual ? (
          <Img
            src={mediaSrc(visual)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: "58% 14%",
              transform: `translateX(${28 - reveal(1.0, 8.0) * 18}px) scale(${1.03 + reveal(1.0, 8.0) * 0.025})`,
              filter:
                "grayscale(1) contrast(1.17) brightness(.93) saturate(.6)",
            }}
          />
        ) : (
          <AbsoluteFill
            style={{
              background:
                "radial-gradient(circle at 68% 28%, rgba(31,123,255,.22), transparent 24%), linear-gradient(120deg, rgba(31,123,255,.06), rgba(92,127,166,.08) 42%, rgba(2,6,16,.74))",
            }}
          />
        )}
        <AbsoluteFill
          style={{
            zIndex: 3,
            background:
              "linear-gradient(90deg, rgba(5,10,20,.98) 0%, rgba(5,10,20,.78) 10%, rgba(5,10,20,.28) 24%, transparent 42%), linear-gradient(180deg, transparent 60%, rgba(5,10,20,.88) 100%), radial-gradient(circle at 76% 28%, rgba(31,123,255,.10), transparent 34%)",
          }}
        />
        <div
          style={{
            position: "absolute",
            right: 38,
            top: 80,
            width: 390,
            height: 640,
            zIndex: 4,
            opacity: 0.34,
            backgroundImage:
              "radial-gradient(circle, #1F7BFF 0 2.3px, transparent 2.6px)",
            backgroundSize: "17px 17px",
            maskImage: "radial-gradient(ellipse, #000 0 22%, transparent 72%)",
            mixBlendMode: "screen",
          }}
        />
      </div>

      <section
        style={{
          position: "absolute",
          left: 138,
          top: 138,
          width: 1040,
          zIndex: 8,
        }}
      >
        <div
          style={{
            height: 95,
            color: brand.signalBlue,
            fontFamily: typography.serif,
            fontWeight: 900,
            fontSize: 132,
            lineHeight: 0.95,
            letterSpacing: "-.12em",
            opacity: quoteMarkReveal,
            transform: `translateY(${18 * (1 - quoteMarkReveal)}px) scale(${0.94 + quoteMarkReveal * 0.06})`,
            transformOrigin: "left bottom",
          }}
        >
          “
        </div>
        <div
          style={{
            marginTop: 18,
            width: 1055,
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          {lines.map((line, index) => {
            const lineReveal = reveal(0.58 + index * 0.18, 0.56);
            const highlightReveal = reveal(0.52 + index * 0.18, 0.5);
            return (
              <div
                key={`${line.text}-${index}`}
                style={{
                  position: "relative",
                  width: "max-content",
                  maxWidth: "100%",
                  overflow: "hidden",
                  clipPath: `inset(0 ${100 - lineReveal * 100}% 0 0)`,
                }}
              >
                {line.emphasis ? (
                  <div
                    style={{
                      position: "absolute",
                      inset: "7px 0 3px 0",
                      zIndex: 1,
                      background:
                        "linear-gradient(90deg, rgba(255,216,74,.92), #FFD84A 53%, rgba(255,216,74,.92))",
                      transform: `scaleX(${highlightReveal})`,
                      transformOrigin: "left",
                      boxShadow: "0 0 36px rgba(255,216,74,.12)",
                      clipPath: "polygon(0 8%, 98% 0, 100% 88%, 1% 100%)",
                    }}
                  />
                ) : null}
                <span
                  style={{
                    position: "relative",
                    zIndex: 2,
                    display: "inline-block",
                    padding: line.emphasis
                      ? "4px 17px 8px 14px"
                      : "0 7px 5px 0",
                    color: line.emphasis ? brand.ink : brand.white,
                    fontFamily: typography.sans,
                    fontSize: quoteSize,
                    lineHeight: 1.06,
                    fontWeight: 820,
                    letterSpacing: "-.045em",
                    textShadow: line.emphasis
                      ? "none"
                      : "0 10px 34px rgba(0,0,0,.45)",
                  }}
                >
                  {line.text}
                </span>
              </div>
            );
          })}
        </div>
        <div
          style={{
            marginTop: 48,
            opacity: speakerReveal,
            transform: `translateX(${-24 * (1 - speakerReveal)}px)`,
          }}
        >
          <div
            style={{
              color: brand.signalBlue,
              fontFamily: typography.sans,
              fontSize: 35,
              lineHeight: 1,
              fontWeight: 840,
              letterSpacing: ".075em",
              textTransform: "uppercase",
            }}
          >
            {speaker || "Source"}
          </div>
          <div
            style={{
              marginTop: 15,
              color: brand.muted,
              fontFamily: typography.sans,
              fontSize: 25,
              fontWeight: 600,
              letterSpacing: ".06em",
              textTransform: "uppercase",
            }}
          >
            {role}
          </div>
        </div>
      </section>

      <section
        style={{
          position: "absolute",
          left: 104,
          bottom: 82,
          width: 980,
          minHeight: 122,
          zIndex: 9,
          opacity: sourceReveal,
          transform: `translateY(${25 * (1 - sourceReveal)}px)`,
        }}
      >
        <div
          style={{
            color: brand.white,
            fontFamily: typography.serif,
            fontSize: 45,
            lineHeight: 1.06,
            fontWeight: 700,
            letterSpacing: "-.025em",
          }}
        >
          {sourceName}
        </div>
        <div
          style={{
            marginTop: 13,
            color: brand.muted,
            fontFamily: typography.sans,
            fontSize: 23,
            lineHeight: 1.2,
            fontWeight: 600,
            letterSpacing: ".055em",
            textTransform: "uppercase",
          }}
        >
          {date}
        </div>
      </section>

      <AbsoluteFill
        style={{
          boxShadow:
            "inset 0 0 190px rgba(0,0,0,.86), inset 0 -130px 180px rgba(0,0,0,.48)",
          zIndex: 20,
          pointerEvents: "none",
        }}
      />
    </AbsoluteFill>
  );
};

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

        {template === "quote_card" ? (
          <QuoteCard segment={segment} sourceDate={story.sourceDate} />
        ) : null}
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
            startFrom={Math.round(segment.start * fps)}
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
