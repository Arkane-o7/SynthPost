import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { PngPresenter } from "../types";
import { brand, layout as studioLayout, typography } from "../styles/brand";
import { mediaSrc } from "./media";

const isSpeakingAt = (
  presenter: PngPresenter,
  narrationSecond: number,
): boolean =>
  presenter.speechWindows.some(
    (window) =>
      narrationSecond >= window.start && narrationSecond < window.speechEnd,
  );

export const MeridianPngNarrator: React.FC<{
  presenter: PngPresenter;
  narrationStart: number;
  variant: "split" | "fullscreen";
}> = ({ presenter, narrationStart, variant }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localSecond = frame / fps;
  const narrationSecond = narrationStart + localSecond;
  const speaking = isSpeakingAt(presenter, narrationSecond);
  const mouthOpen =
    speaking &&
    Math.floor(narrationSecond * Math.max(1, presenter.talkCadenceFps)) % 2 ===
      0;
  const entrance = interpolate(
    localSecond,
    [0, Math.max(0.1, presenter.entrySeconds)],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const breathing =
    1 +
    Math.sin(
      (narrationSecond / Math.max(1, presenter.breathCycleSeconds)) *
        Math.PI *
        2,
    ) *
      presenter.breathScale;
  const configured = presenter.layout[variant] ?? {};
  const panelWidth =
    variant === "split" ? studioLayout.anchor.width : studioLayout.width;
  const panelHeight =
    variant === "split" ? studioLayout.anchor.height : studioLayout.height;
  const imageWidth = configured.width ?? (variant === "split" ? 760 : 1120);
  const scale = (configured.scale ?? 1) * breathing;
  const x = configured.x ?? 0;
  const y = configured.y ?? 0;
  const poseStyle: React.CSSProperties = {
    position: "absolute",
    width: imageWidth,
    height: "auto",
    left: `calc(50% - ${imageWidth / 2}px + ${x}px)`,
    bottom: -18 + y,
    transform: `translateY(${(1 - entrance) * 26}px) scale(${scale})`,
    transformOrigin: "50% 100%",
    opacity: entrance,
    filter: "drop-shadow(0 30px 34px rgba(0, 0, 0, 0.42))",
  };

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        width: panelWidth,
        height: panelHeight,
        overflow: "hidden",
        background:
          variant === "split"
            ? `radial-gradient(circle at 48% 40%, rgba(213,169,78,0.13), transparent 44%), linear-gradient(150deg, ${brand.deepBlue}, ${brand.ink} 72%)`
            : `radial-gradient(circle at 69% 34%, rgba(213,169,78,0.15), transparent 38%), linear-gradient(115deg, ${brand.ink}, ${brand.deepBlue} 58%, ${brand.navy})`,
        borderRight:
          variant === "split"
            ? "1px solid rgba(245, 247, 250, 0.24)"
            : undefined,
      }}
    >
      <AbsoluteFill
        style={{
          opacity: 0.2,
          background:
            "repeating-linear-gradient(90deg, rgba(245,247,250,.08) 0 1px, transparent 1px 86px), repeating-linear-gradient(0deg, rgba(245,247,250,.04) 0 1px, transparent 1px 86px)",
        }}
      />
      {variant === "fullscreen" ? (
        <div
          style={{
            position: "absolute",
            left: 120,
            top: 166,
            width: 650,
            color: brand.white,
          }}
        >
          <div
            style={{
              fontFamily: typography.sans,
              fontSize: 18,
              fontWeight: 700,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: brand.signalBlue,
            }}
          >
            Meridian analysis
          </div>
          <div
            style={{
              width: 84,
              height: 3,
              marginTop: 22,
              background: brand.signalBlue,
            }}
          />
        </div>
      ) : null}
      <Img
        src={mediaSrc(presenter.neutral)}
        style={{ ...poseStyle, opacity: mouthOpen ? 0 : entrance }}
      />
      <Img
        src={mediaSrc(presenter.speaking)}
        style={{ ...poseStyle, opacity: mouthOpen ? entrance : 0 }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: variant === "split" ? 110 : 160,
          background:
            "linear-gradient(180deg, transparent, rgba(2, 8, 16, 0.82))",
        }}
      />
    </div>
  );
};
