import React from "react";
import { useCurrentFrame } from "remotion";
import { genreTheme, typography } from "../styles/brand";

const COPY = "SYNTHPOST   ·   THE SIGNAL. THE STORY.   ·   VERIFIED SOURCE   ·   BROADCASTING LIVE   ·   ";

export const BrandRibbon: React.FC<{
  category?: string;
  compact?: boolean;
}> = ({ category, compact = false }) => {
  const frame = useCurrentFrame();
  const theme = genreTheme(category);
  const height = compact ? 32 : 88;
  const offset = -((frame * (compact ? 1.1 : 0.6)) % 720);

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: compact ? 0 : -10,
        height,
        overflow: "hidden",
        pointerEvents: "none",
        zIndex: 12,
      }}
    >
      <svg width="100%" height="100%" viewBox={`0 0 1920 ${height}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id={`ribbon-${theme.key}`} x1="0" x2="1">
            <stop offset="0" stopColor={theme.accent} />
            <stop offset="1" stopColor={theme.accentEnd} />
          </linearGradient>
          <path
            id={`ribbon-path-${theme.key}-${compact ? "compact" : "field"}`}
            d={compact ? `M -60 16 C 520 4, 1120 29, 1980 13` : `M -80 42 C 430 2, 1130 93, 2000 31`}
          />
        </defs>
        <use
          href={`#ribbon-path-${theme.key}-${compact ? "compact" : "field"}`}
          fill="none"
          stroke={`url(#ribbon-${theme.key})`}
          strokeWidth={compact ? 31 : 42}
          strokeLinecap="round"
        />
        <g transform={`translate(${offset} 0)`}>
          <text fill="#F3EFE7" fontFamily={typography.mono} fontSize={compact ? 13 : 17} fontWeight={700} letterSpacing={3}>
            <textPath href={`#ribbon-path-${theme.key}-${compact ? "compact" : "field"}`} startOffset="0">{COPY.repeat(4)}</textPath>
          </text>
        </g>
      </svg>
    </div>
  );
};
