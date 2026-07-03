import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { brand, layout } from "../styles/brand";
import type { TimedVisual } from "../types";
import { activeVisual, clampUnit } from "./VisualMediaLayer";
import { VisualSkillRenderer } from "./visualSkills/VisualSkillRenderer";

export const NewsVisualPanel: React.FC<{
  visuals: TimedVisual[];
  sourceLabel: string;
  sourceDate: string;
}> = ({ visuals }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const second = frame / fps;
  const visual = activeVisual(visuals, second);
  const visualDuration = Math.max(0.01, visual.end - visual.start);
  const visualProgress = clampUnit((second - visual.start) / visualDuration);
  const mediaStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: visual.fit ?? "cover",
    objectPosition: "center center",
    filter: "saturate(0.82) contrast(1.05) brightness(0.82)",
  };

  return (
    <div
      style={{
        position: "absolute",
        left: layout.visual.left,
        top: layout.visual.top,
        width: layout.visual.width,
        height: layout.visual.height,
        overflow: "hidden",
        backgroundColor: brand.deepBlue,
      }}
    >
      <VisualSkillRenderer
        visual={visual}
        progress={visualProgress}
        muted
        mediaStyle={mediaStyle}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(90deg, rgba(2,8,16,0.36) 0%, transparent 22%, transparent 74%, rgba(2,8,16,0.40) 100%), linear-gradient(180deg, rgba(2,8,16,0.24) 0%, transparent 45%, rgba(2,8,16,0.42) 100%)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: 1,
          background: "rgba(245,247,250,0.28)",
        }}
      />
    </div>
  );
};
