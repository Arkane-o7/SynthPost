import React from "react";
import { anchorCrop, brand, layout } from "../styles/brand";
import type { PublicMedia } from "../types";
import { AnchorVideoLayer } from "./AnchorVideoLayer";

export const AnchorPanel: React.FC<{
  anchor?: PublicMedia;
  chromaKey?: boolean;
  muted?: boolean;
  startFrom?: number;
}> = ({ anchor, chromaKey, muted, startFrom }) => {
  return (
    <AnchorVideoLayer
      anchor={anchor}
      chromaKey={chromaKey}
      crop={anchorCrop}
      muted={muted}
      startFrom={startFrom}
      style={{
        left: layout.anchor.left,
        top: layout.anchor.top,
        width: layout.anchor.width,
        height: layout.anchor.height,
        backgroundColor: brand.ink,
        borderRight: "1px solid rgba(245, 247, 250, 0.34)",
      }}
    />
  );
};
