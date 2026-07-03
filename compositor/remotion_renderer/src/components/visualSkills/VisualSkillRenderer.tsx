import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import { brand, typography } from "../../styles/brand";
import type { TimedVisual } from "../../types";
import { VisualMediaLayer } from "../VisualMediaLayer";

export const supportedVisualSkillTypes = [
  "map",
  "chart",
  "timeline",
  "document_callout",
  "quote_card",
  "data_callout",
  "context_card",
  "entity_card",
  "source_card",
  "broll_clip",
  "still_image",
] as const;

export type SupportedVisualSkillType =
  (typeof supportedVisualSkillTypes)[number];

const supportedSet = new Set<string>(supportedVisualSkillTypes);

type SkillSpec = Record<string, unknown>;

type SkillPayload = {
  type: SupportedVisualSkillType;
  spec: SkillSpec;
  placeholder: SkillSpec;
};

const text = (value: unknown): string =>
  String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();

const upper = (value: unknown): string => text(value).toUpperCase();

const list = (value: unknown, limit = 4): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map(text).filter(Boolean).slice(0, limit);
};

const objectValue = (value: unknown): SkillSpec =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as SkillSpec)
    : {};

const firstText = (...values: unknown[]): string => {
  for (const value of values) {
    if (Array.isArray(value)) {
      const candidate = value.map(text).filter(Boolean).join(" ");
      if (candidate) {
        return candidate;
      }
      continue;
    }
    const candidate = text(value);
    if (candidate) {
      return candidate;
    }
  }
  return "";
};

const safeLine = (value: unknown, maxLength = 120): string => {
  const candidate = text(value);
  if (candidate.length <= maxLength) {
    return candidate;
  }
  return `${candidate.slice(0, maxLength - 1).replace(/\s+\S*$/, "")}...`;
};

const clampStyle = (lines: number): React.CSSProperties => ({
  overflow: "hidden",
  display: "-webkit-box",
  WebkitLineClamp: lines,
  WebkitBoxOrient: "vertical",
  overflowWrap: "anywhere",
});

export const visualSkillPayload = (visual: TimedVisual): SkillPayload => {
  const skill = objectValue(visual.visualSkill);
  const placeholder = objectValue(visual.skillPlaceholder);
  const rawType = firstText(
    visual.visualSkillType,
    skill.skill_type,
    placeholder.type,
    visual.mediaType,
    "context_card",
  );
  const type = supportedSet.has(rawType)
    ? (rawType as SupportedVisualSkillType)
    : "context_card";
  return { type, spec: objectValue(skill.spec), placeholder };
};

export const visualAttributionText = (visual: TimedVisual): string => {
  const parts = [
    firstText(visual.attributionText, visual.sourceLabel, visual.provider),
    firstText(visual.sourceDomain),
    firstText(visual.license),
    firstText(visual.rightsCategory),
  ].filter(Boolean);
  return parts.join(" / ");
};

export const isFirstPartyVisual = (visual: TimedVisual): boolean => {
  return (
    visual.rightsCategory === "first_party_generated" ||
    visual.provider === "synthpost_generated"
  );
};

const skillTitle = (visual: TimedVisual, payload: SkillPayload): string => {
  return upper(
    firstText(
      payload.placeholder.title,
      payload.spec.title,
      payload.spec.source_title,
      payload.spec.metric,
      visual.sectionType,
      visual.sourceLabel,
      "SynthPost Context",
    ),
  );
};

const subtitle = (visual: TimedVisual, payload: SkillPayload): string => {
  return firstText(
    payload.placeholder.subtitle,
    payload.spec.subtitle,
    payload.spec.context,
    visual.visualRole,
    visual.sectionType,
  );
};

const CardShell: React.FC<{
  visual: TimedVisual;
  payload: SkillPayload;
  progress: number;
  children: React.ReactNode;
  eyebrow?: string;
}> = ({ visual, payload, progress, children, eyebrow }) => {
  const reveal = interpolate(progress, [0, 0.16, 1], [0, 1, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const lift = interpolate(progress, [0, 0.16], [24, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(135deg, rgba(5,10,20,0.98) 0%, rgba(7,27,51,0.94) 52%, rgba(2,6,16,0.98) 100%)",
        overflow: "hidden",
      }}
    >
      <AbsoluteFill
        style={{
          opacity: 0.22,
          background:
            "repeating-linear-gradient(90deg, rgba(245,247,250,0.12) 0 1px, transparent 1px 96px), repeating-linear-gradient(0deg, rgba(245,247,250,0.07) 0 1px, transparent 1px 96px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 54,
          right: 54,
          top: 54,
          bottom: 58,
          opacity: reveal,
          transform: `translateY(${lift}px)`,
          border: "1px solid rgba(245,247,250,0.18)",
          background: "rgba(2,8,16,0.54)",
          boxShadow: "0 24px 58px rgba(0,0,0,0.34)",
          padding: 40,
          display: "flex",
          flexDirection: "column",
          gap: 24,
        }}
      >
        <div
          style={{ display: "flex", justifyContent: "space-between", gap: 24 }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <div
              style={{
                color: brand.yellow,
                fontFamily: typography.sans,
                fontSize: 18,
                fontWeight: 800,
                textTransform: "uppercase",
              }}
            >
              {eyebrow ?? payload.type.replace(/_/g, " ")}
            </div>
            <div
              style={{
                marginTop: 10,
                maxWidth: 880,
                color: brand.white,
                fontFamily: typography.serif,
                fontSize: 56,
                lineHeight: 1.02,
                fontWeight: 800,
                ...clampStyle(3),
              }}
            >
              {skillTitle(visual, payload)}
            </div>
          </div>
          <SafetyBadge visual={visual} />
        </div>
        {subtitle(visual, payload) ? (
          <div
            style={{
              maxWidth: 860,
              color: "rgba(245,247,250,0.76)",
              fontFamily: typography.sans,
              fontSize: 24,
              lineHeight: 1.34,
              fontWeight: 600,
              ...clampStyle(2),
            }}
          >
            {subtitle(visual, payload)}
          </div>
        ) : null}
        <div style={{ flex: 1, minHeight: 0 }}>{children}</div>
        <AttributionStrip visual={visual} />
      </div>
    </AbsoluteFill>
  );
};

const SafetyBadge: React.FC<{ visual: TimedVisual; floating?: boolean }> = ({
  visual,
  floating = false,
}) => {
  if (visual.renderSafetyStatus !== "review_only") {
    return null;
  }
  return (
    <div
      style={{
        ...(floating
          ? {
              position: "absolute",
              top: 24,
              right: 24,
              zIndex: 6,
            }
          : {}),
        alignSelf: "flex-start",
        border: `2px solid ${brand.yellow}`,
        color: brand.yellow,
        background: "rgba(255,216,74,0.10)",
        padding: "10px 14px",
        fontFamily: typography.sans,
        fontSize: 15,
        fontWeight: 900,
        textTransform: "uppercase",
      }}
    >
      Review Only
    </div>
  );
};

const AttributionStrip: React.FC<{ visual: TimedVisual }> = ({ visual }) => {
  const attribution = isFirstPartyVisual(visual)
    ? "SynthPost generated visual"
    : visualAttributionText(visual);
  if (!attribution) {
    return null;
  }
  return (
    <div
      style={{
        color: "rgba(245,247,250,0.58)",
        fontFamily: typography.sans,
        fontSize: 15,
        fontWeight: 700,
        textTransform: "uppercase",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
      }}
    >
      {attribution}
    </div>
  );
};

const Lines: React.FC<{ items: string[] }> = ({ items }) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      gap: 13,
      maxHeight: "100%",
      overflow: "hidden",
    }}
  >
    {items.map((item) => (
      <div
        key={item}
        style={{
          borderLeft: `4px solid ${brand.signalBlue}`,
          paddingLeft: 16,
          color: "rgba(245,247,250,0.84)",
          fontFamily: typography.sans,
          fontSize: 27,
          lineHeight: 1.22,
          fontWeight: 700,
          ...clampStyle(2),
        }}
      >
        {safeLine(item, 150)}
      </div>
    ))}
  </div>
);

const MapSkill: React.FC<{
  visual: TimedVisual;
  payload: SkillPayload;
  progress: number;
}> = ({ visual, payload, progress }) => {
  const locations = list(payload.spec.location_names, 5);
  const labels = list(payload.spec.labels, 5);
  const items = locations.length
    ? locations
    : labels.length
      ? labels
      : ["Verified location context"];
  return (
    <CardShell
      visual={visual}
      payload={payload}
      progress={progress}
      eyebrow="Location Context"
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 34,
          height: "100%",
        }}
      >
        <div
          style={{
            border: "1px solid rgba(92,127,166,0.52)",
            background:
              "radial-gradient(circle at 48% 44%, rgba(31,123,255,0.30), transparent 26%), linear-gradient(135deg, rgba(92,127,166,0.18), rgba(5,10,20,0.35))",
            position: "relative",
            overflow: "hidden",
          }}
        >
          <AbsoluteFill
            style={{
              opacity: 0.44,
              background:
                "repeating-linear-gradient(25deg, rgba(245,247,250,0.14) 0 1px, transparent 1px 46px), repeating-linear-gradient(115deg, rgba(245,247,250,0.08) 0 1px, transparent 1px 62px)",
            }}
          />
          {items.slice(0, 3).map((item, index) => (
            <div
              key={item}
              style={{
                position: "absolute",
                left: `${26 + index * 18}%`,
                top: `${30 + index * 15}%`,
                color: brand.white,
                fontFamily: typography.sans,
                fontSize: 18,
                fontWeight: 900,
                textTransform: "uppercase",
                maxWidth: "44%",
                ...clampStyle(2),
              }}
            >
              <span
                style={{
                  display: "inline-block",
                  width: 14,
                  height: 14,
                  borderRadius: 14,
                  background: brand.yellow,
                  marginRight: 10,
                }}
              />
              {safeLine(item, 56)}
            </div>
          ))}
        </div>
        <Lines items={items.map((item) => `Focus: ${item}`)} />
      </div>
    </CardShell>
  );
};

const ChartSkill: React.FC<{
  visual: TimedVisual;
  payload: SkillPayload;
  progress: number;
}> = ({ visual, payload, progress }) => {
  const values = Array.isArray(payload.spec.values)
    ? payload.spec.values.slice(0, 5)
    : [];
  const fallbackLines = list(payload.placeholder.lines, 3);
  return (
    <CardShell
      visual={visual}
      payload={payload}
      progress={progress}
      eyebrow="Grounded Data"
    >
      {values.length ? (
        <div
          style={{
            display: "flex",
            alignItems: "end",
            gap: 22,
            height: "100%",
            paddingTop: 30,
          }}
        >
          {values.map((record, index) => {
            const item = objectValue(record);
            const label = firstText(item.label, item.name, `Item ${index + 1}`);
            const numeric = Number(item.value);
            const height = Number.isFinite(numeric)
              ? Math.max(18, Math.min(100, numeric))
              : 42 + index * 14;
            const reveal = interpolate(progress, [0.08, 0.5], [0, height], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return (
              <div key={`${label}-${index}`} style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    height: `${reveal}%`,
                    background: `linear-gradient(180deg, ${brand.signalBlue}, ${brand.yellow})`,
                  }}
                />
                <div
                  style={{
                    marginTop: 14,
                    color: brand.white,
                    fontFamily: typography.sans,
                    fontSize: 18,
                    fontWeight: 800,
                    ...clampStyle(2),
                  }}
                >
                  {safeLine(label, 54)}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <Lines
          items={
            fallbackLines.length
              ? fallbackLines
              : ["Grounded values only", "No invented chart data"]
          }
        />
      )}
    </CardShell>
  );
};

const TimelineSkill: React.FC<{
  visual: TimedVisual;
  payload: SkillPayload;
  progress: number;
}> = ({ visual, payload, progress }) => {
  const events = Array.isArray(payload.spec.events)
    ? payload.spec.events.slice(0, 5)
    : [];
  const lines = events.map((event) => {
    const item = objectValue(event);
    return `${firstText(item.date, item.year, "DATE")}: ${safeLine(firstText(item.label, item.title, item.event), 110)}`;
  });
  return (
    <CardShell
      visual={visual}
      payload={payload}
      progress={progress}
      eyebrow="Timeline"
    >
      <Lines
        items={
          lines.filter(Boolean).length
            ? lines.filter(Boolean)
            : list(payload.placeholder.lines, 4)
        }
      />
    </CardShell>
  );
};

const DocumentSkill: React.FC<{
  visual: TimedVisual;
  payload: SkillPayload;
  progress: number;
}> = ({ visual, payload, progress }) => {
  const excerpt = firstText(
    payload.spec.excerpt,
    payload.spec.summary,
    payload.spec.highlight,
    payload.placeholder.lines,
  );
  return (
    <CardShell
      visual={visual}
      payload={payload}
      progress={progress}
      eyebrow="Source Document"
    >
      <div
        style={{
          border: "1px solid rgba(245,247,250,0.22)",
          background: "rgba(245,247,250,0.08)",
          padding: 34,
          color: brand.white,
          fontFamily: typography.serif,
          fontSize: 38,
          lineHeight: 1.22,
          fontWeight: 800,
          ...clampStyle(5),
        }}
      >
        {safeLine(excerpt || "Source-backed document callout", 360)}
      </div>
    </CardShell>
  );
};

const QuoteSkill: React.FC<{
  visual: TimedVisual;
  payload: SkillPayload;
  progress: number;
}> = ({ visual, payload, progress }) => (
  <CardShell
    visual={visual}
    payload={payload}
    progress={progress}
    eyebrow="Quoted Source"
  >
    <div
      style={{
        color: brand.white,
        fontFamily: typography.serif,
        fontSize: 46,
        lineHeight: 1.14,
        fontWeight: 800,
        ...clampStyle(5),
      }}
    >
      "
      {safeLine(
        firstText(
          payload.spec.quote_text,
          payload.spec.quote,
          payload.placeholder.lines,
          "Source-backed quote",
        ),
        260,
      )}
      "
    </div>
    <div
      style={{
        marginTop: 26,
        color: brand.yellow,
        fontFamily: typography.sans,
        fontSize: 22,
        fontWeight: 900,
        textTransform: "uppercase",
        ...clampStyle(2),
      }}
    >
      {safeLine(
        firstText(
          payload.spec.speaker,
          payload.spec.source,
          visual.sourceLabel,
          "Source",
        ),
        96,
      )}
    </div>
  </CardShell>
);

const DataCalloutSkill: React.FC<{
  visual: TimedVisual;
  payload: SkillPayload;
  progress: number;
}> = ({ visual, payload, progress }) => (
  <CardShell
    visual={visual}
    payload={payload}
    progress={progress}
    eyebrow="Key Number"
  >
    <div style={{ display: "flex", alignItems: "baseline", gap: 18 }}>
      <div
        style={{
          color: brand.yellow,
          fontFamily: typography.serif,
          fontSize: 132,
          lineHeight: 0.9,
          fontWeight: 900,
          maxWidth: "74%",
          ...clampStyle(1),
        }}
      >
        {safeLine(
          firstText(
            payload.spec.number,
            payload.spec.value,
            payload.placeholder.lines,
            "DATA",
          ),
          22,
        )}
      </div>
      <div
        style={{
          color: brand.white,
          fontFamily: typography.sans,
          fontSize: 42,
          fontWeight: 900,
        }}
      >
        {firstText(payload.spec.unit)}
      </div>
    </div>
    <div
      style={{
        marginTop: 24,
        color: "rgba(245,247,250,0.82)",
        fontFamily: typography.sans,
        fontSize: 30,
        fontWeight: 800,
        ...clampStyle(3),
      }}
    >
      {safeLine(
        firstText(
          payload.spec.label,
          payload.spec.context,
          subtitle(visual, payload),
        ),
        160,
      )}
    </div>
  </CardShell>
);

const ContextSkill: React.FC<{
  visual: TimedVisual;
  payload: SkillPayload;
  progress: number;
}> = ({ visual, payload, progress }) => {
  const bullets = list(payload.spec.bullets, 4);
  const entities = list(payload.spec.entities, 5);
  const lines = bullets.length ? bullets : list(payload.placeholder.lines, 4);
  return (
    <CardShell
      visual={visual}
      payload={payload}
      progress={progress}
      eyebrow="SynthPost Context"
    >
      <Lines
        items={lines.length ? lines : entities.map((item) => `Entity: ${item}`)}
      />
    </CardShell>
  );
};

const EntitySkill: React.FC<{
  visual: TimedVisual;
  payload: SkillPayload;
  progress: number;
}> = ({ visual, payload, progress }) => (
  <CardShell
    visual={visual}
    payload={payload}
    progress={progress}
    eyebrow="Entity Focus"
  >
    <Lines
      items={
        list(payload.spec.entities, 5).length
          ? list(payload.spec.entities, 5)
          : [skillTitle(visual, payload)]
      }
    />
  </CardShell>
);

const SourceSkill: React.FC<{
  visual: TimedVisual;
  payload: SkillPayload;
  progress: number;
}> = ({ visual, payload, progress }) => (
  <CardShell
    visual={visual}
    payload={payload}
    progress={progress}
    eyebrow="Source Note"
  >
    <Lines
      items={[
        firstText(
          visual.sourceDomain,
          payload.spec.source_domain,
          "Verified source",
        ),
        firstText(
          visual.attributionText,
          payload.spec.source_name,
          "Attribution available",
        ),
      ]}
    />
  </CardShell>
);

const MediaSkill: React.FC<{
  visual: TimedVisual;
  progress: number;
  muted?: boolean;
  volume?: number;
  mediaStyle?: React.CSSProperties;
}> = ({ visual, progress, muted, volume, mediaStyle }) => (
  <AbsoluteFill style={{ backgroundColor: brand.ink }}>
    <VisualMediaLayer
      visual={visual}
      progress={progress}
      muted={muted}
      volume={volume}
      mediaStyle={mediaStyle}
    />
    <div
      style={{
        position: "absolute",
        left: 28,
        right: 28,
        bottom: 28,
        display: "flex",
        alignItems: "end",
        justifyContent: "flex-end",
        pointerEvents: "none",
      }}
    >
      <AttributionStrip visual={visual} />
    </div>
    <SafetyBadge visual={visual} floating />
  </AbsoluteFill>
);

export const VisualSkillRenderer: React.FC<{
  visual: TimedVisual;
  progress: number;
  muted?: boolean;
  volume?: number;
  mediaStyle?: React.CSSProperties;
}> = ({ visual, progress, muted = true, volume, mediaStyle }) => {
  const payload = visualSkillPayload(visual);
  if (payload.type === "broll_clip" || payload.type === "still_image") {
    return (
      <MediaSkill
        visual={visual}
        progress={progress}
        muted={muted}
        volume={volume}
        mediaStyle={mediaStyle}
      />
    );
  }
  if (
    !visual.visualSkillType &&
    !visual.visualSkill &&
    !visual.skillPlaceholder
  ) {
    return (
      <MediaSkill
        visual={visual}
        progress={progress}
        muted={muted}
        volume={volume}
        mediaStyle={mediaStyle}
      />
    );
  }
  if (payload.type === "map") {
    return <MapSkill visual={visual} payload={payload} progress={progress} />;
  }
  if (payload.type === "chart") {
    return <ChartSkill visual={visual} payload={payload} progress={progress} />;
  }
  if (payload.type === "timeline") {
    return (
      <TimelineSkill visual={visual} payload={payload} progress={progress} />
    );
  }
  if (payload.type === "document_callout") {
    return (
      <DocumentSkill visual={visual} payload={payload} progress={progress} />
    );
  }
  if (payload.type === "quote_card") {
    return <QuoteSkill visual={visual} payload={payload} progress={progress} />;
  }
  if (payload.type === "data_callout") {
    return (
      <DataCalloutSkill visual={visual} payload={payload} progress={progress} />
    );
  }
  if (payload.type === "entity_card") {
    return (
      <EntitySkill visual={visual} payload={payload} progress={progress} />
    );
  }
  if (payload.type === "source_card") {
    return (
      <SourceSkill visual={visual} payload={payload} progress={progress} />
    );
  }
  return <ContextSkill visual={visual} payload={payload} progress={progress} />;
};
