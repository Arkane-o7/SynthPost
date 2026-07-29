import React from "react";

export const meridianPalette = {
  forest: "#488050",
  forestDark: "#305535",
  paper: "#f2ead9",
  paperBright: "#fffaf0",
  ink: "#17221d",
  inkMuted: "#586760",
  brass: "#d2a64a",
  coral: "#d76a57",
  chalk: "#eef2e8",
  blue: "#6ea4a0",
  thread: "#a73f34",
};

export const CorkBoard: React.FC = () => (
  <div
    style={{
      position: "absolute",
      inset: 0,
      overflow: "hidden",
      background:
        "radial-gradient(circle at 14% 21%,rgba(255,238,185,.25) 0 1px,transparent 2px),radial-gradient(circle at 72% 61%,rgba(72,39,19,.22) 0 1px,transparent 2px),radial-gradient(circle at 42% 86%,rgba(255,244,205,.2) 0 1.5px,transparent 2.5px),linear-gradient(135deg,#bd8b56 0%,#a97243 48%,#c0905a 100%)",
      backgroundSize: "17px 19px,23px 29px,31px 27px,100% 100%",
    }}
  >
    <div
      style={{
        position: "absolute",
        inset: 24,
        border: "18px solid transparent",
        borderImage:
          "linear-gradient(135deg,#7d4c28,#c18a53 32%,#6a3e22 68%,#9d6739) 1",
        boxShadow:
          "inset 0 0 0 4px rgba(45,25,14,.55), inset 0 0 70px rgba(56,30,14,.3), 0 0 0 3px rgba(36,20,12,.6)",
      }}
    />
    <div
      style={{
        position: "absolute",
        inset: 44,
        boxShadow: "inset 0 0 64px rgba(55,28,13,.24)",
        pointerEvents: "none",
      }}
    />
  </div>
);

const tornEdge =
  "polygon(.4% 1%,8% .15%,16% .9%,25% .1%,34% .85%,43% .15%,52% .9%,61% .1%,70% .85%,79% .15%,88% .9%,99.6% .15%,99.3% 98.8%,91% 99.55%,82% 98.75%,73% 99.5%,64% 98.8%,55% 99.55%,46% 98.75%,37% 99.5%,28% 98.8%,19% 99.55%,10% 98.75%,.25% 99.35%)";

export const BoardPin: React.FC<{
  x: number | string;
  y?: number;
  color?: "brass" | "coral" | "green";
  size?: number;
  rotate?: number;
}> = ({ x, y = 16, color = "coral", size = 34, rotate = 0 }) => {
  const head =
    color === "brass"
      ? "#d6ad55"
      : color === "green"
        ? "#527e63"
        : "#c85248";
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: size,
        height: size,
        zIndex: 25,
        transform: `translate(-50%, -50%) rotate(${rotate}deg)`,
        transformOrigin: "50% 50%",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: size * 0.13,
          top: size * 0.33,
          width: size * 0.82,
          height: size * 0.58,
          borderRadius: "50%",
          background: "rgba(17,22,18,.34)",
          filter: "blur(3px)",
          transform: "rotate(-8deg)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: size * 0.08,
          top: size * 0.03,
          width: size * 0.84,
          height: size * 0.84,
          borderRadius: "50%",
          background: `radial-gradient(circle at 31% 24%,rgba(255,255,255,.92) 0 7%,rgba(255,255,255,.18) 9%,transparent 15%),radial-gradient(circle at 42% 38%,${head} 0 45%,#813d34 72%,#3c201d 100%)`,
          border: "1.5px solid rgba(38,25,18,.42)",
          boxShadow:
            "0 5px 7px rgba(0,0,0,.36), inset -3px -4px 7px rgba(33,17,12,.34)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: size * 0.43,
          top: size * 0.84,
          width: size * 0.14,
          height: size * 0.22,
          borderRadius: "0 0 50% 50%",
          background: "linear-gradient(90deg,#2d302e,#bbb 48%,#343735)",
          clipPath: "polygon(16% 0,84% 0,50% 100%)",
          opacity: 0.8,
        }}
      />
    </div>
  );
};

export const TornPaper: React.FC<{
  children: React.ReactNode;
  style?: React.CSSProperties;
  innerStyle?: React.CSSProperties;
  pin?: boolean;
  pinColor?: "brass" | "coral" | "green";
  pinX?: number | string;
  pinY?: number;
  pinSize?: number;
  pinRotate?: number;
}> = ({
  children,
  style,
  innerStyle,
  pin = false,
  pinColor = "coral",
  pinX = "50%",
  pinY = 16,
  pinSize = 34,
  pinRotate = -2,
}) => (
  <div
    style={{
      position: "absolute",
      overflow: "visible",
      ...style,
    }}
  >
    <div
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        background: meridianPalette.paperBright,
        clipPath: tornEdge,
        ...innerStyle,
      }}
    >
      {children}
    </div>
    {pin ? (
      <BoardPin
        x={pinX}
        y={pinY}
        color={pinColor}
        size={pinSize}
        rotate={pinRotate}
      />
    ) : null}
  </div>
);

/** A marker treatment that follows the text instead of a fixed pixel box. */
export const MarkerHighlight: React.FC<{
  children: React.ReactNode;
  progress: number;
  color?: string;
  thickness?: number;
}> = ({
  children,
  progress,
  color = "rgba(232,189,66,.58)",
  thickness = 46,
}) => (
  <span
    style={{
      boxDecorationBreak: "clone",
      WebkitBoxDecorationBreak: "clone",
      backgroundImage: `linear-gradient(${color}, ${color})`,
      backgroundPosition: "0 86%",
      backgroundRepeat: "no-repeat",
      backgroundSize: `${Math.max(0, Math.min(1, progress)) * 100}% ${thickness}%`,
      padding: "0 .08em",
      margin: "0 -.08em",
    }}
  >
    {children}
  </span>
);

export const MarkerStroke: React.FC<{
  progress: number;
  color?: string;
  style?: React.CSSProperties;
  thickness?: number;
}> = ({
  progress,
  color = meridianPalette.brass,
  style,
  thickness = 13,
}) => (
  <svg
    viewBox="0 0 1000 48"
    preserveAspectRatio="none"
    style={{
      position: "absolute",
      overflow: "visible",
      ...style,
    }}
  >
    <path
      d="M 8 29 C 190 23, 385 33, 560 25 S 835 31, 992 21"
      fill="none"
      stroke={color}
      strokeWidth={thickness}
      strokeLinecap="round"
      pathLength={1}
      strokeDasharray={1}
      strokeDashoffset={1 - progress}
      opacity={0.92}
    />
    <path
      d="M 12 35 C 240 31, 510 38, 985 29"
      fill="none"
      stroke={color}
      strokeWidth={Math.max(3, thickness * 0.28)}
      strokeLinecap="round"
      pathLength={1}
      strokeDasharray={1}
      strokeDashoffset={1 - progress}
      opacity={0.48}
    />
  </svg>
);

export const ThreadConnector: React.FC<{
  start: { x: number; y: number };
  end: { x: number; y: number };
  progress: number;
  bend?: number;
  color?: string;
  zIndex?: number;
}> = ({
  start,
  end,
  progress,
  bend = 0,
  color = meridianPalette.thread,
  zIndex = 2,
}) => {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const normalLength = Math.max(1, Math.hypot(dx, dy));
  const nx = -dy / normalLength;
  const ny = dx / normalLength;
  const c1 = {
    x: start.x + dx * 0.34 + nx * bend,
    y: start.y + dy * 0.34 + ny * bend,
  };
  const c2 = {
    x: start.x + dx * 0.72 + nx * bend * 0.45,
    y: start.y + dy * 0.72 + ny * bend * 0.45,
  };
  return (
    <svg
      viewBox="0 0 1920 1080"
      style={{ position: "absolute", inset: 0, zIndex, pointerEvents: "none" }}
    >
      <path
        d={`M ${start.x} ${start.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${end.x} ${end.y}`}
        fill="none"
        stroke="rgba(23,34,29,.22)"
        strokeWidth="9"
        strokeLinecap="round"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={1 - progress}
        transform="translate(2 4)"
      />
      <path
        d={`M ${start.x} ${start.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${end.x} ${end.y}`}
        fill="none"
        stroke={color}
        strokeWidth="5.5"
        strokeLinecap="round"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={1 - progress}
      />
    </svg>
  );
};

export const isRightPlacement = (placement?: string): boolean =>
  !placement || placement.includes("right");
