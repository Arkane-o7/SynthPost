import React from "react";
import {Img, staticFile} from "remotion";
import { brand, typography } from "../styles/brand";
import type {PublicMedia} from "../types";

export const LogoBug: React.FC<{
  channelName?: string;
  logo?: PublicMedia;
}> = ({channelName = "SynthPost", logo}) => {
  return (
    <div
      style={{
        width: 390,
        height: "100%",
        display: "flex",
        alignItems: "center",
        paddingLeft: 30,
        borderRight: "1px solid rgba(245,247,250,0.34)",
      }}
    >
      {logo ? <Img
        src={logo.remote ? logo.publicPath : staticFile(logo.publicPath)}
        style={{maxWidth: 300, maxHeight: 112, objectFit: "contain", objectPosition: "left center"}}
      /> : <div
        style={{
          fontFamily: typography.serif,
          fontSize: 68,
          lineHeight: 1,
          color: brand.white,
          letterSpacing: -1.4,
          textShadow: "0 8px 30px rgba(0,0,0,0.38)",
        }}
      >
        {channelName}<span style={{ color: brand.signalBlue }}>.</span>
      </div>}
    </div>
  );
};
