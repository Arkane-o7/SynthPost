import React from "react";
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type {
  MeridianInternalEvent,
  MeridianPresenterCue,
  TimedVisual,
  TimelineSegmentProps,
} from "../../types";
import { mediaSrc } from "../../components/media";
import {
  BoardPin,
  CorkBoard,
  CrumpledPaperTexture,
  MaskingTape,
  MarkerHighlight,
  MeridianDeskSurface,
  ThreadConnector,
  TornPaper,
  isRightPlacement,
  meridianPalette,
} from "./MeridianEditorialPrimitives";

export const prototypeTemplateIds = new Set([
  "meridian_torn_headline",
  "meridian_evidence_stack",
  "meridian_narrator_evidence",
  "meridian_framed_chart",
  "meridian_mechanism",
  "meridian_document_highlight",
  "meridian_narrator_tokens",
  "meridian_footage_montage",
  "meridian_sparse_thesis",
]);

const C = meridianPalette;

type Props = {
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

const allAssets = (segments: TimelineSegmentProps[]): Record<string, TimedVisual> =>
  Object.assign({}, ...segments.map((segment) => segment.sceneAssets ?? {}));

const allEvents = (segments: TimelineSegmentProps[]): MeridianInternalEvent[] =>
  segments
    .flatMap((segment) => segment.internalEvents ?? [])
    .sort((left, right) => left.at - right.at);

const eventProgress = (
  elapsed: number,
  at: number,
  duration = 0.42,
): number =>
  interpolate(elapsed, [at, at + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const payloadText = (
  event: MeridianInternalEvent | undefined,
  key: string,
  fallback: string,
): string => String(event?.payload?.[key] ?? fallback);

const asset = (
  assets: Record<string, TimedVisual>,
  name: string,
): TimedVisual | undefined => assets[name];

const sceneData = (segments: TimelineSegmentProps[]): Record<string, unknown> =>
  Object.assign(
    {},
    ...segments.map((segment) =>
      segment.overlays.data &&
      typeof segment.overlays.data === "object" &&
      !Array.isArray(segment.overlays.data)
        ? segment.overlays.data
        : {},
    ),
  );

const dataText = (
  data: Record<string, unknown>,
  key: string,
  fallback: string,
): string => String(data[key] ?? fallback).trim();

const dataArray = <T,>(
  data: Record<string, unknown>,
  key: string,
  fallback: T[],
): T[] => (Array.isArray(data[key]) ? (data[key] as T[]) : fallback);

export const meridianHeadlineFontSize = (
  text: string,
  sizes: [number, number, number] = [92, 76, 62],
): number => {
  const length = text.replace(/\s+/g, " ").trim().length;
  if (length <= 54) return sizes[0];
  if (length <= 92) return sizes[1];
  return sizes[2];
};

const PaperTexture: React.FC<{ tone?: "green" | "cream" }> = ({
  tone = "green",
}) => (
  <AbsoluteFill
    style={{
      background:
        tone === "green"
          ? `radial-gradient(ellipse at 50% 42%, rgba(119,168,113,.48) 0%, transparent 52%), radial-gradient(ellipse at 50% 48%, transparent 48%, rgba(8,28,17,.42) 100%), ${C.forest}`
          : `radial-gradient(circle at 18% 12%, rgba(210,166,74,.15), transparent 34%), ${C.paper}`,
    }}
  >
    <AbsoluteFill
      style={{
        opacity: tone === "green" ? 0.12 : 0.09,
        backgroundImage:
          tone === "green"
            ? "linear-gradient(rgba(238,242,232,.7) 1px, transparent 1px),linear-gradient(90deg,rgba(238,242,232,.7) 1px,transparent 1px)"
            : "linear-gradient(rgba(23,61,50,.7) 1px, transparent 1px),linear-gradient(90deg,rgba(23,61,50,.7) 1px,transparent 1px)",
        backgroundSize: "56px 56px",
      }}
    />
    <AbsoluteFill
      style={{
        opacity: 0.06,
        backgroundImage:
          "radial-gradient(circle,#fff 0 1px,transparent 1.5px),radial-gradient(circle,#000 0 1px,transparent 1.5px)",
        backgroundPosition: "0 0, 12px 16px",
        backgroundSize: "29px 31px",
        mixBlendMode: "overlay",
      }}
    />
    <CrumpledPaperTexture
      opacity={tone === "green" ? 0.16 : 0.34}
      blendMode={tone === "green" ? "soft-light" : "multiply"}
    />
  </AbsoluteFill>
);

const SourceTag: React.FC<{ children: React.ReactNode; dark?: boolean }> = ({
  children,
  dark = false,
}) => (
  <div
    style={{
      position: "absolute",
      left: 62,
      bottom: 34,
      zIndex: 50,
      padding: "9px 15px",
      border: `1px solid ${dark ? "rgba(255,255,255,.26)" : "rgba(23,34,29,.24)"}`,
      background: dark ? "rgba(7,17,14,.78)" : "rgba(255,250,240,.9)",
      color: dark ? C.chalk : C.inkMuted,
      font: "700 20px/1.1 Inter, ui-sans-serif, system-ui",
      letterSpacing: ".04em",
    }}
  >
    {children}
  </div>
);

const TornHeadline: React.FC<Props> = ({ sceneSegments }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const assets = allAssets(sceneSegments);
  const data = sceneData(sceneSegments);
  const screenshot = asset(assets, "primary_source");
  const headline = dataText(
    data,
    "headline",
    "OpenAI releases\nopen-weight models.",
  );
  const deck = dataText(
    data,
    "deck",
    "The closed-model leader just published weights customers can run themselves.",
  );
  const sourceTag = dataText(data, "source_tag", "OPENAI · AUGUST 5, 2025");
  const headlineSize = meridianHeadlineFontSize(headline);
  const enter = spring({
    frame,
    fps,
    durationInFrames: Math.round(fps * 0.42),
    config: { damping: 17, stiffness: 125, mass: 0.85 },
  });
  const cameraPush = interpolate(frame, [0, fps * 6], [1, 1.026], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const marker = interpolate(frame, [fps * 0.62, fps * 1.18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <MeridianDeskSurface shade={0.18}>
      <MaskingTape left={236} top={82} width={214} rotate={-7} zIndex={42} />
      <MaskingTape left={1466} top={83} width={208} rotate={6} zIndex={42} />
      {screenshot ? (
        <div
          style={{
            position: "absolute",
            inset: "108px 154px 112px",
            overflow: "hidden",
            background: C.paperBright,
            transform: `translateY(${(1 - enter) * 96}px) rotate(${-(1 - enter) * 3 - 0.65}deg) scale(${cameraPush})`,
            boxShadow: "0 42px 86px rgba(0,0,0,.42)",
            clipPath:
              "polygon(.4% 1%,12% .1%,25% .9%,38% .1%,51% .8%,64% .1%,78% .9%,100% .2%,99.5% 98.7%,84% 99.4%,68% 98.8%,52% 99.5%,36% 98.8%,18% 99.4%,.2% 98.6%)",
          }}
        >
          <Img
            src={mediaSrc(screenshot)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: "50% 18%",
              filter: "saturate(.82) contrast(1.04) brightness(.88)",
            }}
          />
          <CrumpledPaperTexture opacity={0.13} blendMode="soft-light" />
          <div
            style={{
              position: "absolute",
              inset: 0,
              background:
                "linear-gradient(90deg,rgba(10,24,19,.9) 0%,rgba(10,24,19,.76) 50%,rgba(10,24,19,.12) 100%)",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: 78,
              top: 164,
              width: 960,
              color: C.paperBright,
              font: `800 ${headlineSize}px/.96 Georgia, 'Times New Roman', serif`,
              letterSpacing: "-.045em",
              maxHeight: 286,
              overflow: "hidden",
            }}
          >
            {headline.split("\n").map((line, index, lines) => (
              <React.Fragment key={`${line}-${index}`}>
                {index === lines.length - 1 ? (
                  <MarkerHighlight progress={marker} thickness={24}>
                    {line}
                  </MarkerHighlight>
                ) : (
                  line
                )}
                {index < lines.length - 1 ? <br /> : null}
              </React.Fragment>
            ))}
          </div>
          <div
            style={{
              position: "absolute",
              left: 84,
              top: 438,
              width: 790,
              color: "rgba(255,250,240,.82)",
              font: "600 34px/1.3 Inter, ui-sans-serif, system-ui",
              display: "-webkit-box",
              WebkitBoxOrient: "vertical",
              WebkitLineClamp: 3,
              overflow: "hidden",
            }}
          >
            {deck}
          </div>
        </div>
      ) : null}
      <SourceTag dark>{sourceTag}</SourceTag>
    </MeridianDeskSurface>
  );
};

const EvidenceStack: React.FC<Props> = ({ sceneSegments, sceneElapsed }) => {
  const assets = allAssets(sceneSegments);
  const data = sceneData(sceneSegments);
  const events = allEvents(sceneSegments).filter(
    (event) => event.type === "add_evidence",
  );
  const cameraDrift = Math.min(1, sceneElapsed / 10);
  const heading = dataText(
    data,
    "heading",
    "Open weights stopped being a niche",
  );
  const sourceTag = dataText(
    data,
    "source_tag",
    "PRIMARY RELEASE PAGES · META · DEEPSEEK · MISTRAL · OPENAI",
  );
  return (
    <AbsoluteFill>
      <CorkBoard />
      <div
        style={{
          position: "absolute",
          left: 90,
          top: 58,
          color: C.paper,
          font: "800 28px/1 Inter, ui-sans-serif, system-ui",
          letterSpacing: ".16em",
          textTransform: "uppercase",
        }}
      >
        {heading}
      </div>
      {events.slice(0, 4).map((event, index) => {
        const key = payloadText(event, "asset", "");
        const media = asset(assets, key);
        const reveal = eventProgress(sceneElapsed, event.at, 0.34);
        const positions = [
          { left: 84, top: 166, rotate: -2.4 },
          { left: 514, top: 224, rotate: 1.7 },
          { left: 956, top: 142, rotate: -1.1 },
          { left: 1384, top: 226, rotate: 2.1 },
        ];
        const pos = positions[index] ?? positions[positions.length - 1];
        return (
          <TornPaper
            key={event.eventId}
            pin
            pinColor={index % 2 ? "brass" : "coral"}
            pinX={`${48 + (index % 2) * 5}%`}
            style={{
              left: pos.left - (index - 1.5) * cameraDrift * 7,
              top: pos.top + (1 - reveal) * 110 - index * cameraDrift * 3,
              width: 452,
              height: 684,
              zIndex: 5 + index,
              opacity: reveal,
              transform: `rotate(${pos.rotate + (1 - reveal) * 4}deg) scale(${0.92 + reveal * 0.08 + cameraDrift * 0.008})`,
              transformOrigin: "50% 100%",
              filter: "drop-shadow(0 34px 44px rgba(3,18,14,.38))",
            }}
          >
            {media ? (
              <Img
                src={mediaSrc(media)}
                style={{
                  width: "100%",
                  height: 508,
                  objectFit: media.mediaType === "document" ? "contain" : "cover",
                  objectPosition: "50% 12%",
                  padding: media.mediaType === "document" ? "22px 20px 4px" : 0,
                  boxSizing: "border-box",
                  filter: "saturate(.78) contrast(1.04)",
                }}
              />
            ) : null}
            <div
              style={{
                padding: "25px 28px",
                color: C.ink,
                font: "800 29px/1.08 Georgia, 'Times New Roman', serif",
              }}
            >
              {payloadText(event, "label", key)}
            </div>
          </TornPaper>
        );
      })}
      <SourceTag>{sourceTag}</SourceTag>
    </AbsoluteFill>
  );
};

const NarratorEvidence: React.FC<Props> = ({
  sceneSegments,
  sceneElapsed,
  presenterCue,
}) => {
  const data = sceneData(sceneSegments);
  const presenterRight = isRightPlacement(presenterCue?.placement);
  const headline = dataText(data, "quote_headline", "“Good enough”\nis the awkward part.");
  const body = dataText(
    data,
    "quote_body",
    "A model does not need to win every benchmark to become a credible substitute.",
  );
  const bubbleText = dataText(
    data,
    "bubble_text",
    "Annoyingly, that may be enough.",
  );
  const bubbleIn = eventProgress(sceneElapsed, 3.12, 0.18);
  const bubbleOut = interpolate(sceneElapsed, [5.15, 5.42], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bubble = bubbleIn * bubbleOut;
  return (
  <AbsoluteFill>
    <PaperTexture />
    <TornPaper
      pin
      pinColor="brass"
      pinX={presenterRight ? "74%" : "26%"}
      style={{
        left: presenterRight ? 82 : 1038,
        top: 132,
        width: 800,
        height: 420,
        transform: `rotate(${presenterRight ? -1 : 1}deg)`,
        filter: "drop-shadow(0 34px 48px rgba(3,17,13,.38))",
      }}
      innerStyle={{ background: C.paper }}
    >
      <div style={{ position: "absolute", inset: "50px 58px", color: C.ink }}>
      <div
        style={{
          font: `800 ${meridianHeadlineFontSize(headline, [70, 60, 52])}px/.98 Georgia, 'Times New Roman', serif`,
          letterSpacing: "-.04em",
        }}
      >
        {headline.split("\n").map((line, index, lines) => (
          <React.Fragment key={`${line}-${index}`}>
            {index === lines.length - 1 ? (
              <MarkerHighlight
                progress={eventProgress(sceneElapsed, 1.4, 0.5)}
                thickness={24}
              >
                {line}
              </MarkerHighlight>
            ) : (
              line
            )}
            {index < lines.length - 1 ? <br /> : null}
          </React.Fragment>
        ))}
      </div>
      <div
        style={{
          marginTop: 28,
          color: C.inkMuted,
          font: "600 28px/1.3 Inter, ui-sans-serif, system-ui",
          display: "-webkit-box",
          WebkitBoxOrient: "vertical",
          WebkitLineClamp: 3,
          overflow: "hidden",
        }}
      >
        {body}
      </div>
      </div>
    </TornPaper>
    <div
      style={{
        position: "absolute",
        left: presenterRight ? 1110 : 355,
        top: 238,
        zIndex: 36,
        width: 455,
        padding: "29px 38px 31px",
        boxSizing: "border-box",
        background: C.paperBright,
        color: C.ink,
        border: `4px solid ${C.ink}`,
        borderRadius: "50% 47% 46% 51% / 48% 52% 46% 54%",
        boxShadow: "0 18px 34px rgba(4,18,14,.28)",
        opacity: bubble,
        transform: `translateY(${(1 - bubbleIn) * 34}px) rotate(-2deg) scale(${0.82 + bubbleIn * 0.18})`,
        transformOrigin: "70% 100%",
        font: "800 38px/1.04 Georgia, 'Times New Roman', serif",
        textAlign: "center",
      }}
    >
      {bubbleText}
      <div
        style={{
          position: "absolute",
          right: presenterRight ? 90 : undefined,
          left: presenterRight ? undefined : 90,
          bottom: -31,
          width: 46,
          height: 46,
          background: C.paperBright,
          borderRight: `4px solid ${C.ink}`,
          borderBottom: `4px solid ${C.ink}`,
          transform: "rotate(38deg) skew(-8deg)",
        }}
      />
    </div>
  </AbsoluteFill>
  );
};

const FramedChart: React.FC<Props> = ({ sceneSegments, sceneElapsed }) => {
  const data = sceneData(sceneSegments);
  const rawPoints = dataArray<Record<string, unknown>>(data, "chart_points", [
    { name: "GPT-4o", value: 9.3 },
    { name: "o1-mini", value: 63.6 },
    { name: "o1", value: 79.2 },
    { name: "DeepSeek R1", value: 79.8 },
  ]);
  const points = rawPoints.map((point, index) => ({
    name: String(point.name ?? `Point ${index + 1}`),
    value: Number(point.value ?? 0),
  }));
  const chartTitle = dataText(
    data,
    "chart_title",
    "An open model reaches the same neighborhood",
  );
  const chartSubtitle = dataText(
    data,
    "chart_subtitle",
    "AIME 2024 · PASS@1 · PUBLISHED EVALUATION",
  );
  const chartConclusion = dataText(
    data,
    "chart_conclusion",
    "Same neighborhood. Different distribution model.",
  );
  const sourceTag = dataText(
    data,
    "source_tag",
    "DEEPSEEK-R1 OFFICIAL REPOSITORY · AIME 2024 TABLE",
  );
  const chartProgress = eventProgress(sceneElapsed, 1.1, 7.2);
  const boardPush = interpolate(sceneElapsed, [0, 12], [1, 1.018], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const equivalenceFocus = eventProgress(sceneElapsed, 6.35, 0.48);
  const maxValue = Math.max(1, ...points.map((point) => point.value));
  const roundedMax = Math.ceil((maxValue * 1.08) / 10) * 10;
  const pathLength = 1560;
  const xFor = (index: number) =>
    190 + index * (1320 / Math.max(1, points.length - 1));
  const yFor = (value: number) => 720 - (value / roundedMax) * 570;
  const ticks = [0.25, 0.5, 0.75, 1].map((ratio) =>
    Math.round(roundedMax * ratio),
  );
  const d = points
    .map((point, index) => `${index ? "L" : "M"} ${xFor(index)} ${yFor(point.value)}`)
    .join(" ");
  return (
    <AbsoluteFill>
      <CorkBoard />
      <div
        style={{
          position: "absolute",
          left: 154,
          top: 66,
          width: 1612,
          height: 930,
          padding: 28,
          boxSizing: "border-box",
          background: "#94694c",
          border: "5px solid rgba(50,30,20,.48)",
          boxShadow: "0 42px 90px rgba(2,16,12,.48)",
          transform: `rotate(-.35deg) scale(${boardPush})`,
        }}
      >
        <div
          style={{
            width: "100%",
            height: "100%",
            background: C.paperBright,
            color: C.ink,
            position: "relative",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              position: "absolute",
              left: 66,
              top: 44,
              font: "800 54px/1 Georgia, 'Times New Roman', serif",
            }}
          >
            {chartTitle}
          </div>
          <div
            style={{
              position: "absolute",
              left: 70,
              top: 112,
              color: C.inkMuted,
              font: "650 23px/1 Inter, ui-sans-serif, system-ui",
              letterSpacing: ".08em",
              textTransform: "uppercase",
            }}
          >
            {chartSubtitle}
          </div>
          <svg
            viewBox="0 0 1600 820"
            style={{ position: "absolute", left: 0, top: 130, width: "100%", height: 760 }}
          >
            {ticks.map((tick) => (
              <g key={tick}>
                <line
                  x1="120"
                  x2="1510"
                  y1={yFor(tick)}
                  y2={yFor(tick)}
                  stroke="rgba(23,34,29,.14)"
                  strokeWidth="2"
                />
                <text
                  x="72"
                  y={yFor(tick) + 8}
                  fill={C.inkMuted}
                  fontFamily="Inter, sans-serif"
                  fontSize="24"
                >
                  {tick}
                </text>
              </g>
            ))}
            <path
              d={d}
              fill="none"
              stroke={C.coral}
              strokeWidth="12"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={pathLength}
              strokeDashoffset={pathLength * (1 - chartProgress)}
            />
            {points.map((point, index) => {
              const revealAt = 1.3 + index * 1.45;
              const reveal = eventProgress(sceneElapsed, revealAt, 0.34);
              return (
                <g
                  key={point.name}
                  opacity={reveal}
                  transform={`translate(${xFor(index)} ${yFor(point.value)}) scale(${reveal})`}
                >
                  <circle r="17" fill={index === 3 ? C.brass : C.coral} />
                  <text
                    x="0"
                    y="-36"
                    textAnchor="middle"
                    fill={C.ink}
                    fontFamily="Inter, sans-serif"
                    fontWeight="800"
                    fontSize="28"
                  >
                    {point.value}
                  </text>
                  <text
                    x="0"
                    y="53"
                    textAnchor="middle"
                    fill={C.inkMuted}
                    fontFamily="Inter, sans-serif"
                    fontWeight="700"
                    fontSize="25"
                  >
                    {point.name}
                  </text>
                </g>
              );
            })}
            <ellipse
              cx={xFor(points.length - 1)}
              cy={yFor(points[points.length - 1]?.value ?? 0)}
              rx="150"
              ry="86"
              fill="none"
              stroke={C.brass}
              strokeWidth="9"
              strokeDasharray="1120"
              strokeDashoffset={1120 * (1 - equivalenceFocus)}
              opacity={equivalenceFocus}
              transform={`rotate(-2 ${xFor(points.length - 1)} ${yFor(points[points.length - 1]?.value ?? 0)})`}
            />
            <text
              x="1425"
              y="760"
              textAnchor="middle"
              fill={C.ink}
              opacity={equivalenceFocus}
              fontFamily="Georgia, serif"
              fontWeight="800"
              fontSize="28"
            >
              {chartConclusion}
            </text>
          </svg>
        </div>
      </div>
      <SourceTag>{sourceTag}</SourceTag>
    </AbsoluteFill>
  );
};

const Mechanism: React.FC<Props> = ({ sceneSegments, sceneElapsed }) => {
  const data = sceneData(sceneSegments);
  const rawNodes = dataArray<Record<string, unknown>>(data, "mechanism_nodes", [
    { number: "1", title: "Downloadable weights", body: "A customer can hold the model" },
    { number: "2", title: "More ways to run", body: "Self-host, cloud host, or switch" },
    { number: "3", title: "Buyer leverage", body: "Closed APIs must earn the premium" },
  ]);
  const nodes = rawNodes.slice(0, 3).map((node, index) => [
    String(node.number ?? index + 1),
    String(node.title ?? ""),
    String(node.body ?? ""),
  ]);
  const heading = dataText(
    data,
    "heading",
    "The mechanism is not mysterious.",
  );
  return (
    <AbsoluteFill>
      <PaperTexture tone="cream" />
      <div
        style={{
          position: "absolute",
          left: 124,
          top: 92,
          width: 1660,
          color: C.ink,
          font: "800 70px/.98 Georgia, 'Times New Roman', serif",
          letterSpacing: "-.04em",
        }}
      >
        {heading}
      </div>
      <svg
        viewBox="0 0 1920 1080"
        style={{ position: "absolute", inset: 0 }}
      >
        {[0, 1].map((index) => {
          const reveal = eventProgress(sceneElapsed, 2.1 + index * 1.5, 0.65);
          return (
            <line
              key={index}
              x1={632 + index * 590}
              x2={760 + index * 590}
              y1="550"
              y2="550"
              stroke={C.coral}
              strokeWidth="13"
              strokeLinecap="round"
              strokeDasharray="240"
              strokeDashoffset={240 * (1 - reveal)}
            />
          );
        })}
      </svg>
      {nodes.map(([number, title, body], index) => {
        const reveal = eventProgress(sceneElapsed, 0.5 + index * 1.45, 0.38);
        return (
          <div
            key={number}
            style={{
              position: "absolute",
              left: 102 + index * 590,
              top: 340 + (1 - reveal) * 44,
              width: 530,
              minHeight: 410,
              padding: "48px 46px",
              boxSizing: "border-box",
              background: index === 2 ? C.forest : C.paperBright,
              color: index === 2 ? C.paperBright : C.ink,
              opacity: reveal,
              transform: `rotate(${[-1.2, 0.7, -0.45][index]}deg)`,
              boxShadow: "0 28px 54px rgba(33,45,39,.2)",
              clipPath:
                "polygon(.5% .9%,99% 0,100% 98.7%,82% 99.4%,64% 98.7%,46% 99.4%,27% 98.8%,0 99.4%)",
            }}
          >
            <div
              style={{
                color: index === 2 ? C.brass : C.coral,
                font: "900 84px/1 Inter, ui-sans-serif, system-ui",
              }}
            >
              {number}
            </div>
            <div
              style={{
                marginTop: 20,
                font: "800 42px/1.04 Georgia, 'Times New Roman', serif",
              }}
            >
              {title}
            </div>
            <div
              style={{
                marginTop: 22,
                color: index === 2 ? "rgba(255,250,240,.76)" : C.inkMuted,
                font: "600 29px/1.32 Inter, ui-sans-serif, system-ui",
              }}
            >
              {body}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const DocumentHighlight: React.FC<Props> = ({ sceneSegments, sceneElapsed }) => {
  const assets = allAssets(sceneSegments);
  const data = sceneData(sceneSegments);
  const document = asset(assets, "document");
  const quote = dataText(
    data,
    "document_quote",
    "“Not available through the OpenAI API, so API pricing and rate limits do not apply.”",
  );
  const source = dataText(
    data,
    "document_source",
    "OPENAI HELP CENTER · OPEN-WEIGHT MODELS",
  );
  const highlight = eventProgress(sceneElapsed, 3.25, 0.78);
  const settle = eventProgress(sceneElapsed, 0, 0.42);
  const cameraPush = interpolate(sceneElapsed, [3.25, 9], [1, 1.035], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const quoteFontSize = quote.length > 165 ? 29 : quote.length > 110 ? 32 : 36;
  return (
    <AbsoluteFill
      style={{
        background:
          "repeating-linear-gradient(92deg,#72553f 0 8px,#806149 8px 17px,#896b51 17px 31px)",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 258,
          top: 50,
          width: 1405,
          height: 972,
          overflow: "hidden",
          background: C.paperBright,
          transform: `translateY(${(1 - settle) * 86}px) rotate(${-(1 - settle) * 2.5 - 0.8}deg) scale(${cameraPush})`,
          boxShadow: "0 48px 92px rgba(23,13,8,.48)",
          clipPath:
            "polygon(.4% .9%,99% .1%,99.5% 98.9%,84% 99.5%,67% 98.8%,51% 99.6%,34% 98.9%,17% 99.5%,.2% 98.7%)",
        }}
      >
        {document ? (
          <Img
            src={mediaSrc(document)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: "50% 12%",
              filter: "saturate(.78) contrast(1.02)",
            }}
          />
        ) : null}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(180deg,rgba(255,250,240,.04),rgba(255,250,240,.19))",
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 116,
            right: 116,
            bottom: 70,
            padding: "25px 36px 28px",
            background: "rgba(255,250,240,.96)",
            color: C.ink,
            boxShadow: "0 16px 40px rgba(15,28,23,.22)",
          }}
        >
          <div
            style={{
              position: "relative",
              font: `700 ${quoteFontSize}px/1.28 Georgia, 'Times New Roman', serif`,
            }}
          >
            <MarkerHighlight progress={highlight}>{quote}</MarkerHighlight>
          </div>
          <div
            style={{
              marginTop: 15,
              color: C.inkMuted,
              font: "700 23px/1 Inter, ui-sans-serif, system-ui",
              letterSpacing: ".05em",
            }}
          >
            {source}
          </div>
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          right: 96,
          top: 262,
          width: 25,
          height: 350,
          borderRadius: 13,
          background: `linear-gradient(90deg,#b5312d 0 72%,#e6c58c 72% 88%,${C.ink} 88%)`,
          boxShadow: "0 18px 24px rgba(28,15,8,.38)",
          transform: `rotate(14deg) translateY(${(1 - settle) * -90}px)`,
        }}
      />
    </AbsoluteFill>
  );
};

const NarratorTokens: React.FC<Props> = ({
  sceneSegments,
  sceneElapsed,
  presenterCue,
}) => {
  const data = sceneData(sceneSegments);
  const events = allEvents(sceneSegments).filter(
    (event) => event.type === "add_token",
  );
  const presenterRight = isRightPlacement(presenterCue?.placement);
  const heading = dataText(
    data,
    "heading",
    "Competition moves from models\nto everything around them.",
  );
  const hubLabel = dataText(data, "hub_label", "THE NEW MOAT");
  const rightSafePositions = [
    {
      left: 72,
      top: 330,
      width: 340,
      accent: C.coral,
      rotate: -1.4,
      pinX: 0.94,
      pinY: 68,
    },
    {
      left: 478,
      top: 284,
      width: 360,
      accent: C.brass,
      rotate: 1.1,
      pinX: 0.82,
      pinY: 112,
    },
    {
      left: 92,
      top: 606,
      width: 350,
      accent: C.brass,
      rotate: 0.8,
      pinX: 0.94,
      pinY: 64,
    },
    {
      left: 470,
      top: 560,
      width: 360,
      accent: C.forest,
      rotate: -0.9,
      pinX: 0.97,
      pinY: 66,
    },
    {
      left: 300,
      top: 838,
      width: 380,
      accent: C.coral,
      rotate: 1.2,
      pinX: 0.88,
      pinY: 30,
    },
  ];
  const positions = presenterRight
    ? rightSafePositions
    : rightSafePositions.map((position) => ({
        ...position,
        left: 1920 - position.left - position.width,
        rotate: -position.rotate,
        pinX: 1 - position.pinX,
      }));
  const hub = presenterRight ? { x: 1030, y: 830 } : { x: 890, y: 830 };
  const titleLeft = presenterRight ? 68 : 982;
  const titleLines = heading.split("\n");
  return (
    <AbsoluteFill>
      <CorkBoard />
      <MaskingTape
        left={titleLeft + 334}
        top={47}
        width={210}
        rotate={presenterRight ? -2 : 2}
      />
      <TornPaper
        style={{
          zIndex: 8,
          left: titleLeft,
          top: 68,
          width: 890,
          height: 174,
          transform: `rotate(${presenterRight ? -0.55 : 0.55}deg)`,
          filter: "drop-shadow(0 22px 34px rgba(4,18,14,.28))",
        }}
        innerStyle={{ background: C.paperBright }}
      >
        <div
          style={{
            position: "absolute",
            inset: "25px 38px 24px",
            color: C.ink,
          }}
        >
          <div
            style={{
              color: C.coral,
              font: "850 20px/1 Inter, ui-sans-serif, system-ui",
              letterSpacing: ".16em",
              textTransform: "uppercase",
            }}
          >
            Liquidity map
          </div>
          <div
            style={{
              marginTop: 12,
              font: "800 47px/.98 Georgia, 'Times New Roman', serif",
              letterSpacing: "-.035em",
            }}
          >
            {titleLines.map((line, index) => (
              <React.Fragment key={`${line}-${index}`}>
                {line}
                {index < titleLines.length - 1 ? <br /> : null}
              </React.Fragment>
            ))}
          </div>
        </div>
      </TornPaper>
      {events.slice(0, 5).map((event, index) => {
        const reveal = eventProgress(sceneElapsed, event.at + 0.16, 0.42);
        const position = positions[index] ?? positions[positions.length - 1];
        const start = {
          x: position.left + position.width * position.pinX,
          y: position.top + position.pinY,
        };
        return (
          <ThreadConnector
            key={`${event.eventId}-thread`}
            start={start}
            end={{ x: hub.x, y: hub.y - 68 }}
            progress={reveal}
            bend={[44, -34, -42, 34, 52][index] ?? 36}
          />
        );
      })}
      <TornPaper
        style={{
          left: hub.x - 158,
          top: hub.y - 70,
          zIndex: 16,
          width: 316,
          height: 146,
          transform: `rotate(${presenterRight ? -1.2 : 1.2}deg)`,
          filter: "drop-shadow(0 22px 34px rgba(4,18,14,.36))",
        }}
        innerStyle={{
          display: "grid",
          placeItems: "center",
          padding: "26px 34px",
          boxSizing: "border-box",
          background: C.forestDark,
          color: C.paperBright,
          border: `5px solid ${C.brass}`,
          font: "850 27px/1.02 Inter, ui-sans-serif, system-ui",
          letterSpacing: ".08em",
          textAlign: "center",
        }}
      >
        {hubLabel}
      </TornPaper>
      <BoardPin
        x={hub.x}
        y={hub.y - 68}
        color="green"
        size={38}
        rotate={1}
      />
      {events.slice(0, 5).map((event, index) => {
        const reveal = eventProgress(sceneElapsed, event.at, 0.3);
        const position = positions[index] ?? positions[positions.length - 1];
        return (
          <TornPaper
            key={event.eventId}
            pin
            pinColor={index % 2 ? "brass" : "coral"}
            pinX={`${position.pinX * 100}%`}
            pinY={position.pinY}
            pinSize={32}
            pinRotate={[-4, 3, -2, 4, -3][index]}
            style={{
              zIndex: 8,
              left: position.left,
              top: position.top + (1 - reveal) * 35,
              width: position.width,
              height: 128,
              opacity: reveal,
              transform: `rotate(${position.rotate}deg) scale(${0.8 + reveal * 0.2})`,
              filter: "drop-shadow(0 20px 28px rgba(4,18,14,.32))",
            }}
            innerStyle={{
              display: "flex",
              alignItems: "center",
              gap: 18,
              padding: "24px 28px",
              boxSizing: "border-box",
              background: index === 3 ? "#E8E6DA" : C.paperBright,
              color: C.ink,
              boxShadow: `inset 9px 0 0 ${position.accent}`,
            }}
          >
            <span
              style={{
                color: position.accent,
                font: "900 25px/1 Inter, ui-sans-serif, system-ui",
                letterSpacing: ".04em",
              }}
            >
              {String(index + 1).padStart(2, "0")}
            </span>
            <span
              style={{
                font: "850 25px/1.02 Inter, ui-sans-serif, system-ui",
                letterSpacing: ".015em",
                textAlign: "left",
              }}
            >
              {payloadText(event, "label", "COMPANY")}
            </span>
          </TornPaper>
        );
      })}
    </AbsoluteFill>
  );
};

const FootageMontage: React.FC<Props> = ({ sceneSegments, sceneElapsed }) => {
  const assets = allAssets(sceneSegments);
  const data = sceneData(sceneSegments);
  const server = asset(assets, "datacenter");
  const developer = asset(assets, "developer");
  const firstHeadline = dataText(
    data,
    "first_headline",
    "Infrastructure still decides the bill.",
  );
  const secondHeadline = dataText(
    data,
    "second_headline",
    "Open tooling improves the substitute.",
  );
  const firstSource = dataText(
    data,
    "first_source",
    "HLRS / USER:CHRISTOPHSEHN · CC BY-SA 3.0 · WIKIMEDIA COMMONS",
  );
  const secondSource = dataText(
    data,
    "second_source",
    "FRIBBLEDOM · CC BY 3.0 · WIKIMEDIA COMMONS",
  );
  const headlinePlacement = dataText(data, "headline_placement", "top_right");
  const headlineOnRight = headlinePlacement !== "top_left";
  const switchAt = Number(data.switch_at ?? 4.45);
  const { fps } = useVideoConfig();
  const switchFrame = Math.round(switchAt * fps);
  const showDeveloper = sceneElapsed >= switchAt;
  return (
    <AbsoluteFill style={{ background: "#080c0a" }}>
      {server?.kind === "video" ? (
        <Sequence durationInFrames={switchFrame}>
          <OffthreadVideo
            src={mediaSrc(server)}
            muted
            startFrom={Math.round((server.trimStart ?? 0) * fps)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              filter: "saturate(.64) contrast(1.12) brightness(.78)",
              transform: `scale(${1 + Math.min(sceneElapsed, switchAt) * 0.006})`,
            }}
          />
        </Sequence>
      ) : server?.kind === "image" ? (
        <Sequence durationInFrames={switchFrame}>
          <Img
            src={mediaSrc(server)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              filter: "saturate(.64) contrast(1.12) brightness(.78)",
              transform: `scale(${1 + Math.min(sceneElapsed, switchAt) * 0.006})`,
            }}
          />
        </Sequence>
      ) : null}
      {developer?.kind === "video" ? (
        <Sequence from={switchFrame}>
          <OffthreadVideo
            src={mediaSrc(developer)}
            muted
            startFrom={Math.round((developer.trimStart ?? 0) * fps)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              filter: "saturate(.64) contrast(1.12) brightness(.78)",
              transform: `scale(${1 + Math.max(0, sceneElapsed - switchAt) * 0.006})`,
            }}
          />
        </Sequence>
      ) : developer?.kind === "image" ? (
        <Sequence from={switchFrame}>
          <Img
            src={mediaSrc(developer)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              filter: "saturate(.64) contrast(1.12) brightness(.78)",
              transform: `scale(${1 + Math.max(0, sceneElapsed - switchAt) * 0.006})`,
            }}
          />
        </Sequence>
      ) : null}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg,rgba(5,12,9,.16),transparent 38%,rgba(5,12,9,.7))",
        }}
      />
      <MaskingTape
        left={headlineOnRight ? 1184 : 186}
        top={63}
        width={176}
        rotate={headlineOnRight ? 5 : -5}
      />
      <TornPaper
        style={{
          left: headlineOnRight ? 1010 : 74,
          top: 84,
          width: 820,
          height: 188,
          transform: `rotate(${headlineOnRight ? 0.8 : -0.8}deg)`,
          filter: "drop-shadow(0 22px 40px rgba(3,12,9,.42))",
        }}
        innerStyle={{ background: "rgba(255,250,240,.94)" }}
      >
        <div
          style={{
            position: "absolute",
            inset: "30px 40px",
            display: "flex",
            alignItems: "center",
            color: C.ink,
            font: `800 ${meridianHeadlineFontSize(showDeveloper ? secondHeadline : firstHeadline, [54, 48, 43])}px/.98 Georgia, 'Times New Roman', serif`,
            letterSpacing: "-.038em",
          }}
        >
          {showDeveloper ? secondHeadline : firstHeadline}
        </div>
      </TornPaper>
      <SourceTag dark>
        {showDeveloper ? secondSource : firstSource}
      </SourceTag>
    </AbsoluteFill>
  );
};

const SparseThesis: React.FC<Props> = ({ sceneSegments, sceneElapsed }) => {
  const data = sceneData(sceneSegments);
  const lead = dataText(
    data,
    "thesis_lead",
    "Open models do not need\nto win the frontier.",
  );
  const support = dataText(
    data,
    "thesis_support",
    "They only need to make capable intelligence",
  );
  const keywordText = dataText(data, "thesis_keyword", "INTERCHANGEABLE.");
  const finalLine = dataText(
    data,
    "thesis_final",
    "That is enough to weaken differentiation.",
  );
  const reveal = eventProgress(sceneElapsed, 0.35, 0.55);
  const keyword = eventProgress(sceneElapsed, 2.65, 0.28);
  return (
    <AbsoluteFill>
      <PaperTexture />
      <div
        style={{
          position: "absolute",
          left: 168,
          top: 184,
          width: 1520,
          color: C.paperBright,
          opacity: reveal,
          transform: `translateY(${(1 - reveal) * 28}px)`,
          font: "800 99px/.96 Georgia, 'Times New Roman', serif",
          letterSpacing: "-.052em",
        }}
      >
        {lead.split("\n").map((line, index) => (
          <React.Fragment key={`${line}-${index}`}>
            {line}
            {index < lead.split("\n").length - 1 ? <br /> : null}
          </React.Fragment>
        ))}
      </div>
      <div
        style={{
          position: "absolute",
          left: 174,
          top: 536,
          width: 980 * eventProgress(sceneElapsed, 1.5, 0.7),
          height: 18,
          background: C.brass,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 174,
          top: 604,
          width: 900,
          color: "rgba(255,250,240,.82)",
          opacity: eventProgress(sceneElapsed, 1.7, 0.5),
          font: "650 43px/1.22 Inter, ui-sans-serif, system-ui",
          letterSpacing: "-.02em",
        }}
      >
        {support}
      </div>
      <div
        style={{
          position: "absolute",
          left: 1040,
          top: 576 + (1 - keyword) * 62,
          padding: "23px 42px 25px",
          background: C.brass,
          color: C.ink,
          opacity: keyword,
          transform: `rotate(-1.5deg) scale(${0.86 + keyword * 0.14})`,
          boxShadow: "0 24px 44px rgba(3,18,14,.36)",
          clipPath:
            "polygon(.5% 2%,99% 0,100% 97%,83% 100%,67% 97%,51% 100%,33% 97%,16% 100%,0 97%)",
          font: "900 61px/.94 Inter, ui-sans-serif, system-ui",
          letterSpacing: "-.045em",
        }}
      >
        {keywordText}
      </div>
      <div
        style={{
          position: "absolute",
          left: 174,
          top: 708,
          width: 1280,
          color: "rgba(255,250,240,.68)",
          opacity: eventProgress(sceneElapsed, 3.15, 0.4),
          font: "650 35px/1.18 Inter, ui-sans-serif, system-ui",
        }}
      >
        {finalLine}
      </div>
    </AbsoluteFill>
  );
};

export const MeridianPrototypeScene: React.FC<Props> = (props) => {
  switch (props.segment.template.templateId) {
    case "meridian_torn_headline":
      return <TornHeadline {...props} />;
    case "meridian_evidence_stack":
      return <EvidenceStack {...props} />;
    case "meridian_narrator_evidence":
      return <NarratorEvidence {...props} />;
    case "meridian_framed_chart":
      return <FramedChart {...props} />;
    case "meridian_mechanism":
      return <Mechanism {...props} />;
    case "meridian_document_highlight":
      return <DocumentHighlight {...props} />;
    case "meridian_narrator_tokens":
      return <NarratorTokens {...props} />;
    case "meridian_footage_montage":
      return <FootageMontage {...props} />;
    default:
      return <SparseThesis {...props} />;
  }
};
