import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ChannelBrandFrame } from "../components/ChannelBrandFrame";
import { DesignCanvas } from "../components/DesignCanvas";
import { VisualMediaLayer } from "../components/VisualMediaLayer";
import { mediaSrc } from "../components/media";
import type { StoryProps, TimelineSegmentProps } from "../types";

type StorytimeCue = {
  mood: string;
  location: string;
  action: string;
  castSize: number;
  shot: string;
  accentText: string;
  variation: number;
  speechEndOffset: number;
};

const palette = {
  paper: "#FFF8EA",
  paperDeep: "#F4E6CE",
  ink: "#292234",
  purple: "#7C5CFC",
  purpleDark: "#5941C7",
  orange: "#FFB85C",
  coral: "#E85D75",
  mint: "#72C9A5",
  sky: "#8FC8F2",
};

const objectValue = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const cueFor = (segment: TimelineSegmentProps): StorytimeCue => {
  const configured = objectValue(objectValue(segment.overlays.data).storytime);
  return {
    mood: String(configured.mood ?? "neutral"),
    location: String(configured.location ?? "memory_space"),
    action: String(configured.action ?? "talk"),
    castSize: Math.max(1, Number(configured.cast_size ?? 1)),
    shot: String(configured.shot ?? "medium"),
    accentText: String(
      configured.accent_text ?? segment.scriptText.split(/\s+/).slice(0, 6).join(" "),
    ),
    variation: Number(configured.variation ?? 0),
    speechEndOffset: Math.max(
      0,
      Number(configured.speech_end_offset ?? segment.duration),
    ),
  };
};

const quotedLines = (value: string): string[] => {
  const matches = [...value.matchAll(/[“\"]([^”\"]{1,70})[”\"]/g)];
  return matches.slice(0, 2).map((match) => match[1].trim());
};

const shortAccent = (value: string, words = 6): string => {
  const clean = value.replace(/\s+/g, " ").trim();
  const clipped = clean.split(" ").slice(0, words).join(" ");
  return clipped.length > 46 ? `${clipped.slice(0, 43)}…` : clipped;
};

const WiggleLine: React.FC<{
  width: number;
  color?: string;
  rotate?: number;
}> = ({ width, color = palette.purple, rotate = 0 }) => (
  <svg
    width={width}
    height="28"
    viewBox={`0 0 ${width} 28`}
    style={{ transform: `rotate(${rotate}deg)` }}
  >
    <path
      d={`M 4 16 C ${width * 0.2} 3, ${width * 0.34} 27, ${width * 0.52} 13 S ${width * 0.82} 8, ${width - 4} 15`}
      fill="none"
      stroke={color}
      strokeWidth="7"
      strokeLinecap="round"
    />
  </svg>
);

const Character: React.FC<{
  mood: string;
  action: string;
  color?: string;
  scale?: number;
  mirror?: boolean;
  talking?: boolean;
}> = ({
  mood,
  action,
  color = palette.purple,
  scale = 1,
  mirror = false,
  talking = true,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const bob = Math.sin((frame / fps) * Math.PI * 3.2) * (talking ? 5 : 2);
  const talkOpen = talking && Math.floor(frame / Math.max(1, Math.round(fps / 8))) % 2 === 0;
  const eyeY = mood === "sad" ? 1 : mood === "excited" ? -2 : 0;
  const armLift = action === "point" || action === "celebrate" ? -38 : 0;
  const lean = action === "run" ? 10 : action === "hide" ? -7 : 0;
  const squash = action === "freeze" ? 0.96 : action === "fall" ? 0.9 : 1;
  const mouth = mood === "sad"
    ? "M 103 94 Q 121 78 139 94"
    : `M 103 85 Q 121 ${talkOpen ? 110 : 92} 139 85`;

  return (
    <svg
      width={260 * scale}
      height={380 * scale}
      viewBox="0 0 260 380"
      style={{
        overflow: "visible",
        transform: `translateY(${bob}px) scaleX(${mirror ? -1 : 1}) rotate(${lean}deg) scaleY(${squash})`,
        transformOrigin: "50% 88%",
        filter: "drop-shadow(0 12px 0 rgba(41,34,52,.08))",
      }}
    >
      <path
        d="M 77 48 Q 91 12 128 23 Q 163 27 181 59 Q 186 98 165 122 Q 143 141 106 132 Q 70 122 68 88 Q 66 66 77 48 Z"
        fill={palette.paper}
        stroke={palette.ink}
        strokeWidth="8"
        strokeLinejoin="round"
      />
      <path
        d="M 72 60 Q 82 18 124 19 Q 163 18 181 56 Q 148 38 113 47 Q 92 55 72 60 Z"
        fill={color}
        stroke={palette.ink}
        strokeWidth="8"
        strokeLinejoin="round"
      />
      <circle cx="98" cy={72 + eyeY} r={mood === "panic" ? 8 : 6} fill={palette.ink} />
      <circle cx="143" cy={72 + eyeY} r={mood === "panic" ? 8 : 6} fill={palette.ink} />
      {mood === "awkward" || mood === "panic" ? (
        <>
          <path d="M 87 54 L 104 49" stroke={palette.ink} strokeWidth="5" strokeLinecap="round" />
          <path d="M 135 49 L 153 56" stroke={palette.ink} strokeWidth="5" strokeLinecap="round" />
        </>
      ) : null}
      <path d={mouth} fill="none" stroke={palette.ink} strokeWidth="6" strokeLinecap="round" />
      <path
        d="M 93 131 Q 121 115 151 133 L 176 251 Q 128 280 77 249 Z"
        fill={color}
        stroke={palette.ink}
        strokeWidth="9"
        strokeLinejoin="round"
      />
      <path
        d={`M 92 155 Q 57 ${166 + armLift} 37 ${230 + armLift}`}
        fill="none"
        stroke={palette.ink}
        strokeWidth="16"
        strokeLinecap="round"
      />
      <path
        d={`M 155 157 Q 194 ${170 - armLift} 218 ${218 - armLift}`}
        fill="none"
        stroke={palette.ink}
        strokeWidth="16"
        strokeLinecap="round"
      />
      <circle cx="35" cy={232 + armLift} r="12" fill={palette.paper} stroke={palette.ink} strokeWidth="7" />
      <circle cx="220" cy={220 - armLift} r="12" fill={palette.paper} stroke={palette.ink} strokeWidth="7" />
      <path d="M 104 258 L 91 347" stroke={palette.ink} strokeWidth="18" strokeLinecap="round" />
      <path d="M 150 258 L 169 347" stroke={palette.ink} strokeWidth="18" strokeLinecap="round" />
      <path d="M 64 352 Q 89 333 111 352" fill={color} stroke={palette.ink} strokeWidth="8" strokeLinecap="round" />
      <path d="M 151 352 Q 174 332 197 353" fill={color} stroke={palette.ink} strokeWidth="8" strokeLinecap="round" />
    </svg>
  );
};

const Environment: React.FC<{ location: string; variation: number }> = ({
  location,
  variation,
}) => {
  const labels: Record<string, string> = {
    school: "SCHOOL",
    office: "WORK",
    home: "HOME",
    online: "ONLINE",
    travel: "SOMEWHERE EN ROUTE",
    street: "OUT IN PUBLIC",
    memory_space: "A WHILE AGO",
  };
  const colors = [palette.sky, palette.orange, palette.mint, palette.coral];
  const accent = colors[Math.abs(variation) % colors.length];
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: 118,
          right: 118,
          bottom: 162,
          height: 12,
          borderRadius: 99,
          background: palette.ink,
          opacity: 0.82,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 116,
          top: 118,
          width: 400,
          height: 248,
          border: `8px solid ${palette.ink}`,
          borderRadius: 28,
          background: accent,
          transform: `rotate(${variation % 2 ? -1.5 : 1.2}deg)`,
          boxShadow: "12px 14px 0 rgba(41,34,52,.1)",
        }}
      >
        <div style={{ display: "flex", gap: 16, padding: 22 }}>
          {[0, 1, 2].map((item) => (
            <span key={item} style={{ width: 18, height: 18, borderRadius: 99, background: palette.paper }} />
          ))}
        </div>
        <div style={{ margin: "20px 34px", height: 16, borderRadius: 99, background: palette.ink, opacity: 0.72 }} />
        <div style={{ margin: "24px 34px", width: "58%", height: 16, borderRadius: 99, background: palette.ink, opacity: 0.42 }} />
      </div>
      <div
        style={{
          position: "absolute",
          right: 128,
          top: 102,
          padding: "18px 26px 14px",
          border: `6px solid ${palette.ink}`,
          borderRadius: 22,
          background: palette.paper,
          color: palette.ink,
          fontFamily: "AntonLocal, Impact, sans-serif",
          fontSize: 42,
          letterSpacing: ".06em",
          transform: "rotate(2deg)",
        }}
      >
        {labels[location] ?? labels.memory_space}
      </div>
    </AbsoluteFill>
  );
};

const SpeechBubble: React.FC<{
  children: React.ReactNode;
  left: number;
  top: number;
  rotate?: number;
}> = ({ children, left, top, rotate = 0 }) => (
  <div
    style={{
      position: "absolute",
      left,
      top,
      maxWidth: 520,
      padding: "24px 30px",
      border: `7px solid ${palette.ink}`,
      borderRadius: "36px 36px 36px 12px",
      background: palette.paper,
      color: palette.ink,
      fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      fontSize: 38,
      fontWeight: 850,
      lineHeight: 1.1,
      transform: `rotate(${rotate}deg)`,
      boxShadow: "10px 12px 0 rgba(41,34,52,.1)",
    }}
  >
    {children}
  </div>
);

const PaperScene: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill
    style={{
      overflow: "hidden",
      background: `radial-gradient(circle at 1px 1px, rgba(41,34,52,.09) 1.4px, transparent 1.5px) 0 0 / 30px 30px, ${palette.paper}`,
      color: palette.ink,
    }}
  >
    <div style={{ position: "absolute", left: 46, top: 38, fontFamily: "AntonLocal, Impact, sans-serif", fontSize: 30, letterSpacing: ".12em", color: palette.purple }}>
      SIDEQUEST
    </div>
    {children}
  </AbsoluteFill>
);

const ColdOpen: React.FC<{ segment: TimelineSegmentProps; cue: StorytimeCue; speaking: boolean }> = ({ cue, speaking }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 13, mass: 0.7 } });
  const rotate = interpolate(enter, [0, 1], [-8, 0]);
  return (
    <PaperScene>
      <div style={{ position: "absolute", left: 115, top: 164, width: 820, fontFamily: "AntonLocal, Impact, sans-serif", fontSize: 112, lineHeight: 0.92, letterSpacing: ".01em", textTransform: "uppercase", transform: `translateX(${(1 - enter) * -90}px) rotate(${rotate}deg)` }}>
        {shortAccent(cue.accentText, 7)}
        <div style={{ marginTop: 26 }}><WiggleLine width={520} color={palette.coral} rotate={-2} /></div>
      </div>
      <div style={{ position: "absolute", right: 230, bottom: 108, transform: `scale(${0.72 + enter * 0.28}) rotate(${cue.mood === "panic" ? 3 : -2}deg)` }}>
        <Character mood={cue.mood} action={cue.action} color={palette.purple} scale={1.6} talking={speaking} />
      </div>
      <div style={{ position: "absolute", right: 190, top: 112, width: 210, height: 210, border: `14px solid ${palette.orange}`, transform: "rotate(18deg)", borderRadius: "42% 58% 52% 48%" }} />
    </PaperScene>
  );
};

const EstablishingDoodle: React.FC<{ cue: StorytimeCue; speaking: boolean }> = ({ cue, speaking }) => (
  <PaperScene>
    <Environment location={cue.location} variation={cue.variation} />
    <div style={{ position: "absolute", left: 800, bottom: 148 }}>
      <Character mood={cue.mood} action={cue.action} color={palette.purple} scale={1.18} talking={speaking} />
    </div>
    <div style={{ position: "absolute", left: 132, bottom: 54, fontFamily: "Inter, system-ui, sans-serif", fontSize: 36, fontWeight: 850, color: palette.purpleDark }}>
      {shortAccent(cue.accentText, 7)}
    </div>
  </PaperScene>
);

const CharacterStage: React.FC<{ cue: StorytimeCue; speaking: boolean }> = ({ cue, speaking }) => {
  const frame = useCurrentFrame();
  const entrance = interpolate(frame, [0, 10], [90, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <PaperScene>
      <div style={{ position: "absolute", left: 170, top: 190, width: 720, height: 560, borderRadius: "48% 52% 42% 58%", background: cue.variation % 2 ? "#E7DFFF" : "#FFE1B6", transform: "rotate(-4deg)" }} />
      <div style={{ position: "absolute", left: 380, bottom: 92, transform: `translateY(${entrance}px)` }}>
        <Character mood={cue.mood} action={cue.action} color={palette.purple} scale={1.55} talking={speaking} />
      </div>
      <SpeechBubble left={990} top={252} rotate={2}>
        {shortAccent(cue.accentText, 8)}
      </SpeechBubble>
      <div style={{ position: "absolute", right: 220, bottom: 210 }}><WiggleLine width={440} color={palette.orange} rotate={3} /></div>
    </PaperScene>
  );
};

const DialogueTwoShot: React.FC<{ segment: TimelineSegmentProps; cue: StorytimeCue; speaking: boolean }> = ({ segment, cue, speaking }) => {
  const lines = quotedLines(segment.scriptText);
  return (
    <PaperScene>
      <div style={{ position: "absolute", left: 220, bottom: 92 }}>
        <Character mood={cue.mood} action="talk" color={palette.purple} scale={1.42} mirror talking={speaking} />
      </div>
      <div style={{ position: "absolute", right: 220, bottom: 92 }}>
        <Character mood="neutral" action="talk" color={palette.orange} scale={1.42} talking={false} />
      </div>
      <SpeechBubble left={455} top={130} rotate={-2}>{shortAccent(lines[0] ?? cue.accentText, 9)}</SpeechBubble>
      {lines[1] ? <SpeechBubble left={1050} top={352} rotate={2}>{shortAccent(lines[1], 9)}</SpeechBubble> : null}
      <div style={{ position: "absolute", left: 844, bottom: 152, width: 180, borderTop: `8px dashed ${palette.ink}`, opacity: 0.22 }} />
    </PaperScene>
  );
};

const ImaginationBurst: React.FC<{ cue: StorytimeCue; speaking: boolean }> = ({ cue, speaking }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pulse = 1 + Math.sin((frame / fps) * Math.PI * 2) * 0.035;
  return (
    <PaperScene>
      <div style={{ position: "absolute", inset: 78, borderRadius: "46% 54% 42% 58% / 52% 46% 54% 48%", background: "linear-gradient(135deg, #E8DFFF, #FFD9A5)", border: `10px solid ${palette.ink}`, transform: `scale(${pulse}) rotate(-1deg)` }} />
      {[0, 1, 2, 3, 4].map((item) => (
        <div key={item} style={{ position: "absolute", left: 250 + item * 320, top: 140 + (item % 2) * 150, width: 48, height: 48, background: item % 2 ? palette.coral : palette.orange, clipPath: "polygon(50% 0,61% 35%,100% 50%,61% 65%,50% 100%,39% 65%,0 50%,39% 35%)", transform: `rotate(${item * 19}deg)` }} />
      ))}
      <div style={{ position: "absolute", left: 310, bottom: 92 }}><Character mood={cue.mood} action="celebrate" color={palette.purple} scale={1.45} talking={speaking} /></div>
      <div style={{ position: "absolute", right: 200, top: 280, width: 820, fontFamily: "AntonLocal, Impact, sans-serif", fontSize: 104, lineHeight: 0.94, textAlign: "center", textTransform: "uppercase" }}>{shortAccent(cue.accentText, 7)}</div>
    </PaperScene>
  );
};

const MemoryCutaway: React.FC<{ segment: TimelineSegmentProps; cue: StorytimeCue }> = ({ segment, cue }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const progress = Math.max(0, Math.min(1, frame / Math.max(1, segment.duration * fps)));
  const visual = segment.visual;
  return (
    <PaperScene>
      <div style={{ position: "absolute", left: 170, right: 170, top: 105, bottom: 120, padding: 28, border: `9px solid ${palette.ink}`, borderRadius: 26, background: "#fff", transform: `rotate(${cue.variation % 2 ? 1.2 : -1.1}deg)`, boxShadow: "18px 20px 0 rgba(41,34,52,.12)", overflow: "hidden" }}>
        <div style={{ position: "relative", width: "100%", height: "100%", borderRadius: 12, overflow: "hidden", background: palette.paperDeep }}>
          {visual ? <VisualMediaLayer visual={visual} progress={progress} muted={segment.audio?.mode !== "source" && segment.audio?.mode !== "mixed"} volume={segment.audio?.sourceVolume ?? 0} /> : null}
        </div>
      </div>
      <div style={{ position: "absolute", left: 300, top: 78, width: 190, height: 54, background: "rgba(255,184,92,.82)", transform: "rotate(-7deg)" }} />
      <div style={{ position: "absolute", right: 292, bottom: 94, padding: "14px 22px", borderRadius: 14, background: palette.paper, border: `5px solid ${palette.ink}`, fontFamily: "Inter, system-ui, sans-serif", fontWeight: 850, fontSize: 26 }}>
        {visual?.sourceLabel || "MEMORY REFERENCE"}
      </div>
    </PaperScene>
  );
};

const MotionMontage: React.FC<{ cue: StorytimeCue; speaking: boolean }> = ({ cue, speaking }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const active = Math.floor((frame / fps) * 1.7) % 3;
  const actions = [cue.action, "run", "freeze"];
  const colors = [palette.purple, palette.orange, palette.mint];
  return (
    <PaperScene>
      <div style={{ position: "absolute", inset: "132px 90px 100px", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 34 }}>
        {[0, 1, 2].map((item) => (
          <div key={item} style={{ position: "relative", border: `8px solid ${palette.ink}`, borderRadius: 26, background: item === active ? "#FFF1CF" : "#F2EBDD", overflow: "hidden", transform: `translateY(${item === active ? -16 : 0}px) rotate(${item - 1}deg)`, boxShadow: item === active ? "12px 16px 0 rgba(124,92,252,.2)" : "none" }}>
            <div style={{ position: "absolute", left: 75, bottom: 26 }}><Character mood={item === 2 ? cue.mood : "neutral"} action={actions[item]} color={colors[item]} scale={1.02} talking={speaking && item === active} /></div>
            <div style={{ position: "absolute", left: 24, top: 20, width: 52, height: 52, borderRadius: 99, display: "grid", placeItems: "center", color: palette.paper, background: palette.ink, fontFamily: "AntonLocal, Impact, sans-serif", fontSize: 28 }}>{item + 1}</div>
          </div>
        ))}
      </div>
    </PaperScene>
  );
};

const PunchlineButton: React.FC<{ cue: StorytimeCue; speaking: boolean }> = ({ cue, speaking }) => (
  <PaperScene>
    <div style={{ position: "absolute", left: 185, top: 210, width: 760, fontFamily: "AntonLocal, Impact, sans-serif", fontSize: 108, lineHeight: 0.94, textTransform: "uppercase" }}>
      {shortAccent(cue.accentText, 7)}
      <div style={{ marginTop: 28 }}><WiggleLine width={430} color={palette.purple} rotate={-2} /></div>
    </div>
    <div style={{ position: "absolute", right: 290, bottom: 82 }}><Character mood={cue.mood} action="freeze" color={palette.purple} scale={1.58} talking={speaking} /></div>
    <div style={{ position: "absolute", right: 160, top: 150, fontSize: 140, fontFamily: "AntonLocal, Impact, sans-serif", color: palette.coral, transform: "rotate(8deg)" }}>!</div>
  </PaperScene>
);

const StorytimeSegment: React.FC<{ segment: TimelineSegmentProps; story: StoryProps }> = ({ segment, story }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cue = cueFor(segment);
  const template = segment.template.templateId;
  const speaking = frame / fps < cue.speechEndOffset;
  const narrationEnabled = Boolean(story.narrationAudio) && segment.audio?.mode !== "source" && segment.audio?.mode !== "silent";
  return (
    <AbsoluteFill>
      {narrationEnabled && story.narrationAudio ? (
        <Audio src={mediaSrc(story.narrationAudio)} startFrom={Math.round((segment.narrationStart ?? segment.start) * fps)} volume={segment.audio?.narrationVolume ?? 1} />
      ) : null}
      {template === "storytime_cold_open" ? <ColdOpen segment={segment} cue={cue} speaking={speaking} /> : null}
      {template === "storytime_establishing_doodle" ? <EstablishingDoodle cue={cue} speaking={speaking} /> : null}
      {template === "storytime_dialogue_two_shot" ? <DialogueTwoShot segment={segment} cue={cue} speaking={speaking} /> : null}
      {template === "storytime_imagination_burst" ? <ImaginationBurst cue={cue} speaking={speaking} /> : null}
      {template === "storytime_memory_cutaway" ? <MemoryCutaway segment={segment} cue={cue} /> : null}
      {template === "storytime_motion_montage" ? <MotionMontage cue={cue} speaking={speaking} /> : null}
      {template === "storytime_punchline_button" ? <PunchlineButton cue={cue} speaking={speaking} /> : null}
      {!template.startsWith("storytime_") || template === "storytime_character_stage" ? <CharacterStage cue={cue} speaking={speaking} /> : null}
    </AbsoluteFill>
  );
};

export const StorytimeStory: React.FC<StoryProps> = (props) => {
  const { fps } = useVideoConfig();
  const segments = props.timelineSegments ?? [];
  return (
    <ChannelBrandFrame story={props}>
      <DesignCanvas background={palette.paper}>
        <AbsoluteFill>
          {props.backgroundMusic ? <Audio src={mediaSrc(props.backgroundMusic)} volume={props.backgroundMusicVolume ?? 0.055} /> : null}
          {(props.soundEffects ?? []).map((effect, index) => (
            <Sequence key={`${effect.media.publicPath}-${index}`} from={Math.round(effect.start * fps)}>
              <Audio src={mediaSrc(effect.media)} volume={effect.volume ?? 0.14} />
            </Sequence>
          ))}
          {segments.length ? segments.map((segment) => {
            const from = Math.round(segment.start * fps);
            const duration = Math.max(1, Math.round(segment.end * fps) - from);
            return (
              <Sequence key={segment.segmentId} from={from} durationInFrames={duration}>
                <StorytimeSegment segment={segment} story={props} />
              </Sequence>
            );
          }) : (
            <ColdOpen
              segment={{} as TimelineSegmentProps}
              cue={{ mood: "awkward", location: "school", action: "freeze", castSize: 1, shot: "medium", accentText: props.headline || "That seemed like a good idea", variation: 1, speechEndOffset: props.durationSeconds }}
              speaking
            />
          )}
        </AbsoluteFill>
      </DesignCanvas>
    </ChannelBrandFrame>
  );
};

export const StorytimeThumbnail: React.FC = () => {
  const { width, height } = useVideoConfig();
  const compact = width / height < 1.5;
  const unit = Math.min(width / 1920, height / 1080);
  const headlineSize = compact ? 136 : 188 * unit;
  const phoneWidth = (compact ? 580 : 520) * unit;
  const phoneHeight = (compact ? 760 : 650) * unit;
  const characterScale = (compact ? 1.55 : 1.42) * unit;
  return (
    <AbsoluteFill
      style={{
        overflow: "hidden",
        background: `radial-gradient(circle at 1px 1px, rgba(41,34,52,.11) 1.4px, transparent 1.5px) 0 0 / ${30 * unit}px ${30 * unit}px, ${palette.paper}`,
        color: palette.ink,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: `${52 * unit}px ${58 * unit}px`,
          border: `${10 * unit}px solid ${palette.ink}`,
          borderRadius: 38 * unit,
          boxShadow: `${18 * unit}px ${20 * unit}px 0 rgba(124,92,252,.22)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 68 * unit,
          left: 0,
          right: 0,
          textAlign: "center",
          fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
          fontSize: compact ? 28 : 34 * unit,
          fontWeight: 950,
          letterSpacing: ".16em",
          color: palette.purpleDark,
        }}
      >
        SIDEQUEST
      </div>
      <div
        style={{
          position: "absolute",
          left: compact ? 88 * unit : 135 * unit,
          top: compact ? 168 * unit : 250 * unit,
          width: compact ? 780 * unit : 960 * unit,
          fontFamily: "AntonLocal, Impact, sans-serif",
          fontSize: headlineSize,
          fontWeight: 900,
          lineHeight: 0.82,
          letterSpacing: "-.02em",
          textAlign: "center",
          textTransform: "uppercase",
          transform: "rotate(-2deg)",
          textShadow: `${7 * unit}px ${8 * unit}px 0 ${palette.orange}`,
          WebkitTextStroke: `${2 * unit}px ${palette.ink}`,
        }}
      >
        Wrong
        <br />
        Group
        <br />
        Chat
      </div>
      <div
        style={{
          position: "absolute",
          right: compact ? 70 * unit : 165 * unit,
          top: compact ? 128 * unit : 165 * unit,
          width: phoneWidth,
          height: phoneHeight,
          border: `${12 * unit}px solid ${palette.ink}`,
          borderRadius: 58 * unit,
          background: "#FFFFFF",
          boxShadow: `${18 * unit}px ${22 * unit}px 0 rgba(41,34,52,.14)`,
          transform: "rotate(4deg)",
        }}
      >
        <div
          style={{
            width: 130 * unit,
            height: 18 * unit,
            borderRadius: 99,
            background: palette.ink,
            margin: `${27 * unit}px auto ${42 * unit}px`,
          }}
        />
        {["SATURDAY OFFSITE", "11 LISTENED", "MANAGER 👍"].map((label, index) => (
          <div
            key={label}
            style={{
              margin: `${18 * unit}px ${28 * unit}px`,
              padding: `${20 * unit}px ${22 * unit}px`,
              border: `${5 * unit}px solid ${palette.ink}`,
              borderRadius: 24 * unit,
              background: index === 1 ? "#FFD7DE" : index === 2 ? "#FFF0C8" : "#E8DFFF",
              fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
              fontSize: compact ? 26 : 30 * unit,
              fontWeight: 950,
              lineHeight: 1,
              textAlign: "center",
            }}
          >
            {label}
          </div>
        ))}
        <div
          style={{
            position: "absolute",
            left: 42 * unit,
            right: 42 * unit,
            bottom: 40 * unit,
            padding: `${20 * unit}px 0`,
            border: `${6 * unit}px solid ${palette.ink}`,
            borderRadius: 99,
            background: palette.coral,
            color: "#FFFFFF",
            fontFamily: "AntonLocal, Impact, sans-serif",
            fontSize: compact ? 40 : 48 * unit,
            letterSpacing: ".04em",
            textAlign: "center",
          }}
        >
          SENT
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          left: compact ? 350 * unit : 600 * unit,
          bottom: compact ? -70 * unit : -126 * unit,
          transform: "rotate(-5deg)",
        }}
      >
        <Character mood="panic" action="freeze" color={palette.purple} scale={characterScale} talking={false} />
      </div>
      <div
        style={{
          position: "absolute",
          right: compact ? 78 * unit : 92 * unit,
          top: compact ? 108 * unit : 84 * unit,
          fontFamily: "AntonLocal, Impact, sans-serif",
          fontSize: compact ? 104 : 150 * unit,
          color: palette.coral,
          transform: "rotate(11deg)",
          WebkitTextStroke: `${3 * unit}px ${palette.ink}`,
        }}
      >
        !
      </div>
    </AbsoluteFill>
  );
};
