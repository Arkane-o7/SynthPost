import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { VisualMediaLayer } from "../../components/VisualMediaLayer";
import type {
  MeridianPresenterCue,
  TimedVisual,
  TimelineSegmentProps,
} from "../../types";
import {
  MeridianPrototypeScene,
  prototypeTemplateIds,
} from "./MeridianPrototypeScene";
import {
  MarkerHighlight,
  MarkerStroke,
  TornPaper,
  isRightPlacement,
} from "./MeridianEditorialPrimitives";

const palette = {
  forest: "#153A31",
  forestDark: "#0E2A24",
  paper: "#F2EBDD",
  paperBright: "#FBF8F0",
  ink: "#15201B",
  mutedInk: "#617069",
  brass: "#D5A94E",
  coral: "#D56B59",
  desk: "#81634A",
};

const firstThought = (segment: TimelineSegmentProps): string => {
  const cueData = segment.overlays.data?.headline_cues;
  if (Array.isArray(cueData)) {
    const first = cueData[0];
    if (first && typeof first === "object" && "text" in first) {
      const value = String((first as { text?: unknown }).text ?? "").trim();
      if (value) {
        return value;
      }
    }
  }
  return (
    segment.scriptText
      .split(/(?<=[.!?])\s+/)[0]
      ?.trim()
      .replace(/\s+/g, " ") || ""
  );
};

const objectData = (segment: TimelineSegmentProps): Record<string, unknown> =>
  segment.overlays.data &&
  typeof segment.overlays.data === "object" &&
  !Array.isArray(segment.overlays.data)
    ? segment.overlays.data
    : {};

const dataText = (
  segment: TimelineSegmentProps,
  key: string,
  fallback = "",
): string => String(objectData(segment)[key] ?? fallback).trim();

export const meridianClippingFontSize = (
  text: string,
  kind: "headline" | "social",
): number => {
  const length = text.replace(/\s+/g, " ").trim().length;
  if (kind === "social") {
    if (length <= 105) return 55;
    if (length <= 175) return 47;
    return 39;
  }
  if (length <= 58) return 76;
  if (length <= 96) return 63;
  return 51;
};

const SocialActionIcon: React.FC<{
  kind: "reply" | "repost" | "like";
}> = ({ kind }) => {
  const path =
    kind === "reply"
      ? "M4 5.5h16v10H9l-5 4v-14Z"
      : kind === "repost"
        ? "M7 5h10l3 3-3 3M17 19H7l-3-3 3-3"
        : "M12 20S4 15.5 4 9.5C4 5 9.5 3.5 12 7c2.5-3.5 8-2 8 2.5 0 6-8 10.5-8 10.5Z";
  return (
    <svg width="25" height="25" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
};

const GraphPaper: React.FC<{
  children?: React.ReactNode;
  tone?: "forest" | "paper";
}> = ({ children, tone = "forest" }) => (
  <AbsoluteFill
    style={{
      overflow: "hidden",
      background:
        tone === "forest"
          ? `radial-gradient(circle at 78% 12%, rgba(213,169,78,.12), transparent 32%), ${palette.forest}`
          : `radial-gradient(circle at 14% 8%, rgba(213,169,78,.15), transparent 28%), ${palette.paper}`,
    }}
  >
    <AbsoluteFill
      style={{
        opacity: tone === "forest" ? 0.18 : 0.13,
        backgroundImage:
          tone === "forest"
            ? "linear-gradient(rgba(232,239,229,.55) 1px, transparent 1px), linear-gradient(90deg, rgba(232,239,229,.55) 1px, transparent 1px)"
            : "linear-gradient(rgba(21,58,49,.52) 1px, transparent 1px), linear-gradient(90deg, rgba(21,58,49,.52) 1px, transparent 1px)",
        backgroundSize: "52px 52px",
      }}
    />
    <AbsoluteFill
      style={{
        opacity: 0.08,
        backgroundImage:
          "radial-gradient(circle at 20% 35%, #fff 0 1px, transparent 1.4px), radial-gradient(circle at 72% 64%, #000 0 1px, transparent 1.5px)",
        backgroundSize: "19px 23px, 29px 31px",
        mixBlendMode: "overlay",
      }}
    />
    {children}
  </AbsoluteFill>
);

const SceneVisual: React.FC<{
  visual: TimedVisual;
  progress: number;
  muted: boolean;
  volume: number;
  style?: React.CSSProperties;
}> = ({ visual, progress, muted, volume, style }) => (
  <VisualMediaLayer
    visual={visual}
    progress={progress}
    muted={muted}
    volume={volume}
    mediaStyle={{
      width: "100%",
      height: "100%",
      objectFit: visual.fit ?? "cover",
      objectPosition: "center",
      ...style,
    }}
  />
);

const EvidenceReel: React.FC<MeridianSceneProps> = ({
  visual,
  progress,
  muted,
  volume,
}) => (
  <AbsoluteFill style={{ background: "#090C0B" }}>
    <SceneVisual
      visual={visual}
      progress={progress}
      muted={muted}
      volume={volume}
      style={{
        objectFit: visual.mediaType === "document" ? "contain" : "cover",
        filter: "saturate(.92) contrast(1.04) brightness(.96)",
      }}
    />
    <AbsoluteFill
      style={{
        pointerEvents: "none",
        background:
          "linear-gradient(180deg, rgba(6,10,8,.08), transparent 62%, rgba(6,10,8,.25)), radial-gradient(circle at 50% 42%, transparent 45%, rgba(5,8,7,.14))",
      }}
    />
  </AbsoluteFill>
);

const DocumentDesk: React.FC<MeridianSceneProps> = ({
  visual,
  progress,
  muted,
  volume,
}) => {
  const frame = useCurrentFrame();
  const entrance = interpolate(frame, [0, 16], [70, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(112deg, rgba(255,255,255,.1), transparent 23%), repeating-linear-gradient(92deg, #73563F 0 5px, #7E6047 5px 12px, #87684F 12px 22px)",
      }}
    >
      <AbsoluteFill
        style={{
          opacity: 0.22,
          background:
            "radial-gradient(circle at 18% 20%, rgba(0,0,0,.28), transparent 25%), radial-gradient(circle at 84% 82%, rgba(255,255,255,.14), transparent 26%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 230,
          top: 54 + entrance,
          width: 1460,
          height: 970,
          overflow: "hidden",
          background: palette.paperBright,
          transform: "rotate(-1.15deg)",
          boxShadow:
            "0 45px 75px rgba(27,17,10,.42), 0 4px 0 rgba(255,255,255,.7) inset",
          clipPath:
            "polygon(0.4% 1%, 99.6% 0.2%, 99.1% 98.9%, 92% 99.6%, 84% 99.1%, 74% 99.7%, 65% 99.1%, 55% 99.8%, 45% 99.2%, 34% 99.7%, 24% 99.1%, 14% 99.8%, 0.2% 98.8%)",
        }}
      >
        <SceneVisual
          visual={{ ...visual, fit: "contain" }}
          progress={progress}
          muted={muted}
          volume={volume}
          style={{
            objectFit: "contain",
            padding: 42,
            boxSizing: "border-box",
            filter: "saturate(.86) contrast(1.05)",
          }}
        />
      </div>
      <div
        style={{
          position: "absolute",
          left: 918,
          top: 24,
          width: 84,
          height: 30,
          borderRadius: 20,
          border: "7px solid rgba(35,38,34,.5)",
          borderBottom: 0,
          transform: "rotate(-3deg)",
        }}
      />
    </AbsoluteFill>
  );
};

const ClippingBoard: React.FC<MeridianSceneProps> = ({
  segment,
  visual,
  progress,
  muted,
  volume,
  presenterCue,
  presenterVisible,
}) => {
  const frame = useCurrentFrame();
  const kind = dataText(segment, "clipping_kind", "headline");
  const title = dataText(
    segment,
    "headline",
    segment.overlays.lowerThird?.trim() || firstThought(segment),
  );
  const deck = dataText(segment, "deck");
  const source = dataText(segment, "source", segment.overlays.attribution);
  const date = dataText(segment, "date");
  const titleY = interpolate(frame, [0, 15], [-76, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyReveal = interpolate(frame, [9, 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const markerProgress = interpolate(frame, [18, 34], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const presenterRight = isRightPlacement(presenterCue?.placement);

  if (kind === "social") {
    const displayName = dataText(segment, "display_name", "Meridian Desk");
    const handle = dataText(segment, "handle", "@meridianbrief");
    const post = dataText(segment, "post", title);
    const context = dataText(segment, "context", deck);
    const replies = dataText(segment, "replies", "184");
    const reposts = dataText(segment, "reposts", "1.2K");
    const likes = dataText(segment, "likes", "6.8K");
    const socialWidth = presenterVisible ? 910 : 1260;
    const socialLeft = presenterVisible
      ? presenterRight
        ? 72
        : 938
      : 214;
    const socialFontSize = meridianClippingFontSize(post, "social");
    const initials = displayName
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "M";
    return (
      <GraphPaper>
        <TornPaper
          pin
          pinColor="brass"
          pinX="54%"
          pinY={17}
          pinSize={38}
          pinRotate={2}
          style={{
            left: socialLeft,
            top: 132 + titleY,
            width: socialWidth,
            height: 758,
            transform: "rotate(-1.15deg)",
            filter: "drop-shadow(0 38px 56px rgba(5,21,17,.38))",
          }}
          innerStyle={{ background: palette.paperBright }}
        >
          <div
            style={{
              position: "absolute",
              inset: "52px 58px 50px",
              color: palette.ink,
              fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
              <div
                style={{
                  width: 76,
                  height: 76,
                  borderRadius: "50%",
                  display: "grid",
                  placeItems: "center",
                  background: palette.forest,
                  color: palette.paperBright,
                  fontSize: 34,
                  fontWeight: 900,
                  boxShadow: "inset 0 0 0 4px rgba(255,255,255,.18)",
                }}
              >
                {initials}
              </div>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontSize: 34, fontWeight: 850 }}>{displayName}</span>
                  <span
                    style={{
                      width: 25,
                      height: 25,
                      borderRadius: "50%",
                      display: "grid",
                      placeItems: "center",
                      background: palette.forest,
                      color: palette.paperBright,
                      fontSize: 17,
                      fontWeight: 900,
                    }}
                  >
                    ✓
                  </span>
                </div>
                <div style={{ marginTop: 4, fontSize: 26, color: palette.mutedInk }}>
                  {handle}
                </div>
              </div>
              <div
                style={{
                  marginLeft: "auto",
                  width: 44,
                  height: 44,
                  borderRadius: "50%",
                  border: "3px solid rgba(23,32,27,.25)",
                  display: "grid",
                  placeItems: "center",
                  fontSize: 25,
                  fontWeight: 900,
                  color: palette.mutedInk,
                }}
              >
                  𝕏
              </div>
            </div>
            <div
              style={{
                marginTop: 38,
                maxWidth: socialWidth - 120,
                fontSize: socialFontSize,
                lineHeight: 1.12,
                fontWeight: 650,
                letterSpacing: "-.027em",
                overflowWrap: "anywhere",
                display: "-webkit-box",
                WebkitBoxOrient: "vertical",
                WebkitLineClamp: socialFontSize >= 50 ? 4 : 5,
                overflow: "hidden",
              }}
            >
              {post}
            </div>
            {context ? (
              <div
                style={{
                  marginTop: 24,
                  paddingLeft: 26,
                  borderLeft: `8px solid ${palette.brass}`,
                  fontSize: 27,
                  lineHeight: 1.3,
                  color: palette.mutedInk,
                  opacity: bodyReveal,
                  display: "-webkit-box",
                  WebkitBoxOrient: "vertical",
                  WebkitLineClamp: 2,
                  overflow: "hidden",
                }}
              >
                {context}
              </div>
            ) : null}
            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                bottom: 0,
                paddingTop: 23,
                borderTop: "2px solid rgba(23,32,27,.14)",
                display: "grid",
                gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
                color: palette.mutedInk,
                fontSize: 25,
                fontWeight: 750,
                letterSpacing: ".02em",
              }}
            >
              {[
                ["reply", replies],
                ["repost", reposts],
                ["like", likes],
              ].map(([action, count]) => (
                <span
                  key={action}
                  style={{ display: "flex", alignItems: "center", gap: 12 }}
                >
                  <SocialActionIcon
                    kind={action as "reply" | "repost" | "like"}
                  />
                  {count}
                </span>
              ))}
            </div>
          </div>
        </TornPaper>
        <div
          style={{
            position: "absolute",
            left: socialLeft + 32,
            bottom: 96,
            padding: "12px 18px",
            background: "rgba(255,250,240,.9)",
            color: palette.mutedInk,
            font: "750 21px/1 Inter, ui-sans-serif, system-ui",
            letterSpacing: ".05em",
          }}
        >
          {[source, date].filter(Boolean).join(" · ") || "MERIDIAN DESK"}
        </div>
      </GraphPaper>
    );
  }

  const headlineWidth = presenterVisible ? 860 : 1120;
  const headlineLeft = presenterVisible
    ? presenterRight
      ? 72
      : 988
    : 108;
  const headlineFontSize = meridianClippingFontSize(title, "headline");
  return (
    <GraphPaper>
      <TornPaper
        pin
        pinColor="coral"
        pinX="72%"
        pinY={17}
        pinSize={40}
        pinRotate={-3}
        style={{
          left: headlineLeft,
          top: 152 + titleY,
          width: headlineWidth,
          height: 766,
          transform: "rotate(-1.1deg)",
          filter: "drop-shadow(0 38px 60px rgba(5,21,17,.4))",
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: "54px 64px 58px",
            color: palette.ink,
            fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 18,
              paddingBottom: 24,
              borderBottom: "4px solid rgba(23,32,27,.72)",
            }}
          >
            <div
              style={{
                fontFamily: "Georgia, 'Times New Roman', serif",
                fontSize: 36,
                fontWeight: 900,
                letterSpacing: "-.035em",
              }}
            >
              {source || "THE MERIDIAN LEDGER"}
            </div>
            <div
              style={{
                marginLeft: "auto",
                color: palette.mutedInk,
                fontSize: 21,
                fontWeight: 800,
                letterSpacing: ".08em",
                textTransform: "uppercase",
              }}
            >
              {date}
            </div>
          </div>
          <div
            style={{
              marginTop: 42,
              fontFamily: "Georgia, 'Times New Roman', serif",
              fontSize: headlineFontSize,
              lineHeight: 0.98,
              fontWeight: 900,
              letterSpacing: "-.045em",
              overflowWrap: "anywhere",
              display: "-webkit-box",
              WebkitBoxOrient: "vertical",
              WebkitLineClamp: headlineFontSize >= 70 ? 4 : 5,
              overflow: "hidden",
            }}
          >
            <MarkerHighlight progress={markerProgress} thickness={22}>
              {title}
            </MarkerHighlight>
          </div>
          {deck ? (
            <div
              style={{
                marginTop: 34,
                maxWidth: 880,
                color: palette.mutedInk,
                fontSize: 31,
                lineHeight: 1.28,
                fontWeight: 620,
                opacity: bodyReveal,
                display: "-webkit-box",
                WebkitBoxOrient: "vertical",
                WebkitLineClamp: 4,
                overflow: "hidden",
              }}
            >
              {deck}
            </div>
          ) : null}
        </div>
      </TornPaper>
      {!presenterVisible ? (
        <TornPaper
          pin
          pinColor="brass"
          pinX="48%"
          pinY={17}
          pinSize={37}
          pinRotate={3}
          style={{
            left: 1280,
            top: 245,
            width: 530,
            height: 590,
            transform: "rotate(2.2deg)",
            filter: "drop-shadow(0 32px 52px rgba(5,21,17,.38))",
          }}
        >
          <SceneVisual
            visual={visual}
            progress={progress}
            muted={muted}
            volume={volume}
            style={{
              objectFit: visual.mediaType === "document" ? "contain" : "cover",
              objectPosition: "50% 18%",
              padding: visual.mediaType === "document" ? 26 : 0,
              boxSizing: "border-box",
              filter: "saturate(.78) contrast(1.04)",
            }}
          />
        </TornPaper>
      ) : null}
    </GraphPaper>
  );
};

const DataBoard: React.FC<MeridianSceneProps> = ({
  segment,
  visual,
  progress,
  muted,
  volume,
}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, 18], [0.92, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <GraphPaper>
      <div
        style={{
          position: "absolute",
          left: 220,
          top: 112,
          width: 1480,
          height: 850,
          padding: 28,
          boxSizing: "border-box",
          background: "#B77A52",
          border: "6px solid rgba(65,38,25,.4)",
          boxShadow: "0 34px 80px rgba(3,18,14,.45)",
          transform: `scale(${scale}) rotate(-.35deg)`,
        }}
      >
        <div
          style={{
            width: "100%",
            height: "100%",
            overflow: "hidden",
            background: palette.paperBright,
            position: "relative",
          }}
        >
          <SceneVisual
            visual={{ ...visual, fit: "contain" }}
            progress={progress}
            muted={muted}
            volume={volume}
            style={{
              objectFit: "contain",
              padding: 26,
              boxSizing: "border-box",
              filter: "saturate(.88) contrast(1.04)",
            }}
          />
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          left: 258,
          bottom: 38,
          maxWidth: 1160,
          color: "rgba(244,239,223,.8)",
          fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
          fontSize: 24,
          letterSpacing: ".02em",
        }}
      >
        {firstThought(segment)}
      </div>
    </GraphPaper>
  );
};

const ExplainerStage: React.FC<MeridianSceneProps> = ({
  segment,
  visual,
  progress,
  muted,
  volume,
}) => {
  const frame = useCurrentFrame();
  const visualX = interpolate(frame, [0, 18], [120, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <GraphPaper tone="paper">
      <div
        style={{
          position: "absolute",
          left: 72 + visualX,
          top: 74,
          width: 1110,
          height: 932,
          overflow: "hidden",
          background: palette.paperBright,
          boxShadow: "0 30px 65px rgba(23,38,31,.22)",
          clipPath:
            "polygon(.5% .8%, 99% 0, 100% 98.8%, 88% 99.5%, 74% 98.9%, 60% 99.6%, 46% 98.9%, 32% 99.5%, 17% 98.8%, 0 99.4%)",
        }}
      >
        <SceneVisual
          visual={visual}
          progress={progress}
          muted={muted}
          volume={volume}
          style={{
            objectFit: "cover",
            filter: "saturate(.82) contrast(1.04)",
          }}
        />
      </div>
      <div
        style={{
          position: "absolute",
          left: 1240,
          top: 160,
          width: 550,
          color: palette.ink,
          fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
        }}
      >
        <div
          style={{
            width: 78,
            height: 12,
            marginBottom: 32,
            background: palette.coral,
            transform: "rotate(-2deg)",
          }}
        />
        <div
          style={{
            fontSize: 55,
            lineHeight: 1.04,
            fontWeight: 840,
            letterSpacing: "-.045em",
          }}
        >
          {firstThought(segment)}
        </div>
      </div>
    </GraphPaper>
  );
};

const PresenterCanvas: React.FC<MeridianSceneProps> = ({
  segment,
  presenterCue,
}) => {
  const frame = useCurrentFrame();
  const presenterRight =
    !presenterCue?.placement || presenterCue.placement.includes("right");
  const noteX = interpolate(frame, [0, 16], [-90, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <GraphPaper>
      <div
        style={{
          position: "absolute",
          left: (presenterRight ? 110 : 770) + noteX * (presenterRight ? 1 : -1),
          top: 110,
          width: 1040,
          minHeight: 310,
          padding: "64px 72px",
          boxSizing: "border-box",
          background: palette.paper,
          color: palette.ink,
          transform: "rotate(-1.1deg)",
          boxShadow: "0 32px 70px rgba(4,19,15,.4)",
          clipPath:
            "polygon(.4% 1%, 13% .1%, 27% .8%, 40% .2%, 55% .9%, 69% .1%, 84% .8%, 100% .2%, 99.4% 98.7%, 83% 99.4%, 66% 98.7%, 50% 99.4%, 33% 98.8%, 16% 99.5%, .2% 98.6%)",
          fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
          fontSize: 84,
          lineHeight: 1.02,
          fontWeight: 850,
          letterSpacing: "-.052em",
        }}
      >
        {firstThought(segment)}
      </div>
      <MarkerStroke
        progress={interpolate(frame, [12, 30], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })}
        style={{
          left: presenterRight ? 150 : 810,
          top: 456,
          width: 620,
          height: 40,
        }}
      />
    </GraphPaper>
  );
};

type MeridianSceneProps = {
  segment: TimelineSegmentProps;
  sceneSegments: TimelineSegmentProps[];
  sceneElapsed: number;
  visual: TimedVisual;
  progress: number;
  muted: boolean;
  volume: number;
  presenterCue?: MeridianPresenterCue;
  presenterVisible?: boolean;
};

export const MeridianScene: React.FC<MeridianSceneProps> = (props) => {
  const templateId = props.segment.template.templateId;
  if (prototypeTemplateIds.has(templateId)) {
    return <MeridianPrototypeScene {...props} />;
  }
  if (templateId === "meridian_evidence_reel") {
    return <EvidenceReel {...props} />;
  }
  if (templateId === "meridian_document_desk") {
    return <DocumentDesk {...props} />;
  }
  if (templateId === "meridian_clipping_board") {
    return <ClippingBoard {...props} />;
  }
  if (templateId === "meridian_data_board") {
    return <DataBoard {...props} />;
  }
  if (templateId === "meridian_explainer_stage") {
    return <ExplainerStage {...props} />;
  }
  return <PresenterCanvas {...props} />;
};
