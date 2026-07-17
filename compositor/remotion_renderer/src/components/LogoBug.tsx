import React from "react";
import { brand, genreTheme, typography } from "../styles/brand";

export const LogoBug: React.FC<{ category?: string }> = ({ category }) => {
  const theme = genreTheme(category);
  return (
    <div
      style={{
        width: 405,
        height: "100%",
        display: "flex",
        alignItems: "center",
        paddingLeft: 28,
        borderRight: "1px solid rgba(245,247,250,0.34)",
      }}
    >
      <div
        style={{
          width: 72,
          height: 72,
          borderRadius: 999,
          background: brand.ink,
          color: brand.paper,
          display: "grid",
          placeItems: "center",
          fontFamily: typography.serif,
          fontSize: 61,
          fontWeight: 700,
          lineHeight: 1,
          marginRight: 18,
          boxShadow: "inset 0 0 0 1px rgba(245,247,250,.16)",
        }}
      >
        S
      </div>
      <div
        style={{
          fontFamily: typography.serif,
          fontSize: 54,
          lineHeight: 1,
          color: brand.white,
          letterSpacing: -1.4,
          textShadow: "0 8px 30px rgba(0,0,0,0.38)",
        }}
      >
        SynthPost<span style={{ color: theme.accent }}>.</span>
      </div>
    </div>
  );
};
