import React from "react";
import {
  Img,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type {
  MeridianPresenterCue,
  MeridianPresenterMotion,
  MeridianPresenterPlacement,
  PngPresenter,
} from "../types";
import { mediaSrc } from "./media";

const placementStyle = (
  placement: MeridianPresenterPlacement,
  width: number,
): React.CSSProperties => {
  const common: React.CSSProperties = {
    position: "absolute",
    bottom: -42,
    width,
    height: "auto",
  };
  if (placement === "left") {
    return { ...common, left: 54 };
  }
  if (placement === "right") {
    return { ...common, right: 54 };
  }
  if (placement === "center") {
    return { ...common, left: `calc(50% - ${width / 2}px)` };
  }
  if (placement === "lower_left") {
    return { ...common, left: 94, bottom: -170 };
  }
  if (placement === "lower_right") {
    return { ...common, right: 94, bottom: -170 };
  }
  if (placement === "edge_left") {
    return { ...common, left: -width * 0.34, bottom: -110 };
  }
  return { ...common, right: -width * 0.34, bottom: -110 };
};

const entryOffset = (
  motion: MeridianPresenterMotion,
  placement: MeridianPresenterPlacement,
  amount: number,
): { x: number; y: number; scale: number; rotate: number } => {
  const side = placement.includes("left") ? -1 : 1;
  if (motion === "slide") {
    return { x: side * 290 * amount, y: 0, scale: 1, rotate: side * 2.5 * amount };
  }
  if (motion === "peek") {
    return { x: side * 220 * amount, y: 34 * amount, scale: 1, rotate: side * 5 * amount };
  }
  if (motion === "hop") {
    return { x: 0, y: 120 * amount, scale: 1 - 0.08 * amount, rotate: 0 };
  }
  if (motion === "drift") {
    return { x: side * 90 * amount, y: 24 * amount, scale: 1, rotate: side * 1.5 * amount };
  }
  return { x: 0, y: 42 * amount, scale: 1 - 0.28 * amount, rotate: 0 };
};

export const MeridianNarratorLayer: React.FC<{
  presenter: PngPresenter;
  cue?: MeridianPresenterCue;
  durationInFrames: number;
}> = ({ presenter, cue = {}, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const defaults = presenter.editorialMotion ?? {};
  const poseName = cue.pose || defaults.defaultPose || "neutral";
  const pose =
    presenter.poses[poseName] ??
    presenter.poses.neutral ??
    presenter.neutral;
  const previousPose = cue.previousPose
    ? presenter.poses[cue.previousPose]
    : undefined;
  const placement =
    cue.placement || defaults.defaultPlacement || "lower_right";
  const motion = cue.motion || defaults.defaultMotion || "pop";
  const width = Math.max(260, cue.width || defaults.width || 1320);
  const entrance = spring({
    frame,
    fps,
    config: {
      damping: motion === "pop" || motion === "hop" ? 11 : 18,
      stiffness: motion === "pop" || motion === "hop" ? 155 : 118,
      mass: 0.82,
    },
    durationInFrames: Math.max(6, Math.round(fps * 0.32)),
  });
  const entranceOpacity = interpolate(
    frame,
    [0, Math.max(3, Math.round(fps * 0.2))],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const exit = interpolate(
    frame,
    [
      Math.max(0, durationInFrames - Math.round(fps * 0.38)),
      durationInFrames,
    ],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const offset = entryOffset(motion, placement, 1 - entrance);
  const idlePhase = frame / fps;
  const idleX =
    motion === "drift" ? Math.sin(idlePhase * 1.12) * 5 : 0;
  const idleY = motion === "drift" ? Math.sin(idlePhase * 1.55) * 2 : 0;
  const idleRotate =
    motion === "drift" ? Math.sin(idlePhase * 0.95) * 0.18 : 0;
  const breathScale =
    1 +
    Math.sin(
      (idlePhase / Math.max(2.5, presenter.breathCycleSeconds || 4.8)) *
        Math.PI *
        2,
    ) *
      Math.min(0.012, presenter.breathScale || 0.006);
  const editorialLean = Math.sin(idlePhase * 0.72) * 0.12;
  const userScale = Math.max(0.5, cue.scale ?? 1);
  const userRotate = cue.rotate ?? 0;
  const seconds = frame / fps;
  const poseTransitionDuration = Math.max(
    0.08,
    cue.poseTransitionSeconds ?? 0.2,
  );
  const poseTransitionProgress =
    cue.poseTransition === "cut" || cue.poseChangeAt === undefined
      ? 1
      : interpolate(
          seconds,
          [cue.poseChangeAt, cue.poseChangeAt + poseTransitionDuration],
          [0, 1],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
        );
  const poseTransitionActive = Boolean(
    previousPose &&
      cue.poseChangeAt !== undefined &&
      seconds < cue.poseChangeAt + poseTransitionDuration,
  );
  const direction = placement.includes("left") ? -1 : 1;
  const whipDistance = cue.poseTransition === "whip" ? 68 : 24;
  const shadow = "drop-shadow(0 30px 28px rgba(9, 12, 14, 0.30))";
  const commonStyle: React.CSSProperties = {
    ...placementStyle(placement, width),
    zIndex: 30,
    transformOrigin: "50% 100%",
    willChange: "transform, opacity, filter",
  };
  const baseTranslateX = offset.x + idleX + (cue.x ?? 0);
  const baseTranslateY = offset.y + idleY + (cue.y ?? 0);
  const baseScale = offset.scale * userScale * breathScale;
  const baseRotate = offset.rotate + idleRotate + editorialLean + userRotate;
  const entryBlur = (1 - entrance) * (motion === "slide" ? 11 : 7);
  const currentTransitionBlur = poseTransitionActive
    ? (1 - poseTransitionProgress) * 12
    : 0;
  const currentTransitionX = poseTransitionActive
    ? direction * whipDistance * (1 - poseTransitionProgress)
    : 0;

  return (
    <>
      {poseTransitionActive && previousPose ? (
        <Img
          src={mediaSrc(previousPose)}
          style={{
            ...commonStyle,
            zIndex: 29,
            opacity:
              entranceOpacity * exit * (1 - poseTransitionProgress),
            transform: `translate3d(${baseTranslateX - direction * whipDistance * poseTransitionProgress}px, ${baseTranslateY}px, 0) scale(${baseScale * (1 - poseTransitionProgress * 0.012)}) rotate(${baseRotate - direction * poseTransitionProgress * 0.8}deg)`,
            filter: `${defaults.shadow === false ? "" : shadow} blur(${poseTransitionProgress * 12}px)`,
          }}
        />
      ) : null}
      <Img
        src={mediaSrc(pose)}
        style={{
          ...commonStyle,
          opacity:
            entranceOpacity *
            exit *
            (poseTransitionActive ? poseTransitionProgress : 1),
          transform: `translate3d(${baseTranslateX + currentTransitionX}px, ${baseTranslateY}px, 0) scale(${baseScale * (poseTransitionActive ? 0.982 + poseTransitionProgress * 0.018 : 1)}) rotate(${baseRotate + direction * (1 - poseTransitionProgress) * 0.8}deg)`,
          filter: `${defaults.shadow === false ? "" : shadow} blur(${entryBlur + currentTransitionBlur}px)`,
        }}
      />
    </>
  );
};
