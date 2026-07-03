import React from "react";
import { AbsoluteFill, useVideoConfig } from "remotion";
import { brand, layout } from "../styles/brand";

export const DesignCanvas: React.FC<{
  children: React.ReactNode;
  background?: React.CSSProperties["background"];
}> = ({ children, background = brand.navy }) => {
  const { width, height } = useVideoConfig();
  const scaleX = width / layout.width;
  const scaleY = height / layout.height;

  return (
    <AbsoluteFill style={{ background, overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: layout.width,
          height: layout.height,
          transform: `scale(${scaleX}, ${scaleY})`,
          transformOrigin: "top left",
        }}
      >
        {children}
      </div>
    </AbsoluteFill>
  );
};
