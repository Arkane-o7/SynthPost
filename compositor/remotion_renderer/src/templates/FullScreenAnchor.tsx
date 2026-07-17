import React from "react";
import { AbsoluteFill } from "remotion";
import { AnchorVideoLayer } from "../components/AnchorVideoLayer";
import { DesignCanvas } from "../components/DesignCanvas";
import { LowerThird } from "../components/LowerThird";
import { brand, fullAnchorCrop } from "../styles/brand";
import type { StoryProps } from "../types";

export const FullScreenAnchor: React.FC<StoryProps> = (props) => {
  return (
    <DesignCanvas>
      <AbsoluteFill
        style={{
          backgroundColor: brand.navy,
          overflow: "hidden",
          color: brand.white,
        }}
      >
        <AnchorVideoLayer
          anchor={props.anchor}
          chromaKey={props.anchorChromaKey}
          crop={fullAnchorCrop}
          mediaFilter="saturate(0.92) contrast(1.03) brightness(0.88)"
          overlay="linear-gradient(180deg, rgba(2,8,16,0.10) 0%, rgba(2,8,16,0.04) 44%, rgba(2,8,16,0.42) 78%, rgba(2,8,16,0.68) 100%), linear-gradient(90deg, rgba(2,8,16,0.28) 0%, transparent 26%, transparent 74%, rgba(2,8,16,0.30) 100%)"
          style={{
            left: 0,
            top: 0,
            width: "100%",
            height: "100%",
          }}
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
          headline={props.headline}
          headlineItems={props.headlineItems}
          sourceLabel={props.sourceLabel}
          sourceDate={props.sourceDate}
          logo={props.logo}
          category={props.category}
        />
      </AbsoluteFill>
    </DesignCanvas>
  );
};
