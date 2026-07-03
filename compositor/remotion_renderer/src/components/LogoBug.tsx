import React from "react";
import { brand, typography } from "../styles/brand";

export const LogoBug: React.FC = () => {
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
      <div
        style={{
          fontFamily: typography.serif,
          fontSize: 68,
          lineHeight: 1,
          color: brand.white,
          letterSpacing: -1.4,
          textShadow: "0 8px 30px rgba(0,0,0,0.38)",
        }}
      >
        Synthpost<span style={{ color: brand.signalBlue }}>.</span>
      </div>
    </div>
  );
};
