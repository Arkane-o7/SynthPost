import React from "react";
import { AbsoluteFill } from "remotion";
import { AnchorPanel } from "../components/AnchorPanel";
import { DesignCanvas } from "../components/DesignCanvas";
import { LowerThird } from "../components/LowerThird";
import { NewsVisualPanel } from "../components/NewsVisualPanel";
import { brand } from "../styles/brand";
import type { StoryProps } from "../types";

export const SplitMain: React.FC<StoryProps> = (props) => {
  return (
    <DesignCanvas>
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
        <AnchorPanel anchor={props.anchor} chromaKey={props.anchorChromaKey} />
        <NewsVisualPanel
          visuals={props.visuals}
          sourceLabel={props.sourceLabel}
          sourceDate={props.sourceDate}
        />
        <LowerThird
          headline={props.headline}
          headlineItems={props.headlineItems}
          sourceLabel={props.sourceLabel}
          sourceDate={props.sourceDate}
          logo={props.logo}
        />
      </AbsoluteFill>
    </DesignCanvas>
  );
};
