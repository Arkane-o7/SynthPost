import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { brand, genreTheme, layout, typography } from "../styles/brand";
import type { HeadlineItem, PublicMedia } from "../types";
import { LogoBug } from "./LogoBug";
import { BrandRibbon } from "./BrandRibbon";

export const LowerThird: React.FC<{
  headline: string;
  headlineItems?: HeadlineItem[];
  sourceLabel: string;
  sourceDate: string;
  logo?: PublicMedia;
  category?: string;
}> = ({ headline, headlineItems, category }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const second = frame / fps;
  const theme = genreTheme(category);
  const sourceItems: HeadlineItem[] =
    headlineItems && headlineItems.length
      ? headlineItems
      : [{ text: headline }];
  const items: HeadlineItem[] = sourceItems
    .map(
      (item): HeadlineItem => ({
        ...item,
        text: String(item.text ?? "")
          .trim()
          .toUpperCase(),
        start: Number.isFinite(item.start) ? Number(item.start) : undefined,
        end: Number.isFinite(item.end) ? Number(item.end) : undefined,
      }),
    )
    .filter((item) => item.text);
  const cues = items.length ? items : [{ text: headline.toUpperCase() }];
  const timedMode = cues.some(
    (item) => item.start !== undefined || item.end !== undefined,
  );
  const slideFrames = Math.max(1, Math.round(fps * 4.2));
  const transitionFrames = Math.max(1, Math.round(fps * 0.5));
  const orderedCues = timedMode
    ? [...cues].sort((a, b) => (a.start ?? 0) - (b.start ?? 0))
    : cues;
  let timedActiveIndex = 0;
  if (timedMode) {
    for (let index = 0; index < orderedCues.length; index += 1) {
      const item = orderedCues[index];
      if (
        second >= (item.start ?? 0) &&
        (item.end === undefined || second < item.end)
      ) {
        timedActiveIndex = index;
      }
    }
  }
  const loopFrame = frame % (slideFrames * orderedCues.length);
  const loopActiveIndex = Math.floor(loopFrame / slideFrames);
  const activeIndex = timedMode ? timedActiveIndex : loopActiveIndex;
  const nextIndex = (activeIndex + 1) % orderedCues.length;
  const previousIndex = Math.max(0, activeIndex - 1);
  const currentHeadline = orderedCues[activeIndex]?.text ?? orderedCues[0].text;
  const nextHeadline = orderedCues[nextIndex]?.text ?? orderedCues[0].text;
  const previousHeadline = orderedCues[previousIndex]?.text ?? currentHeadline;
  const currentHeadlineSize =
    currentHeadline.length > 92 ? 36 : currentHeadline.length > 62 ? 42 : 50;
  const nextHeadlineSize =
    nextHeadline.length > 92 ? 36 : nextHeadline.length > 62 ? 42 : 50;
  const previousHeadlineSize =
    previousHeadline.length > 92 ? 36 : previousHeadline.length > 62 ? 42 : 50;
  const activeCueStartFrame = Math.round(
    (orderedCues[activeIndex]?.start ?? 0) * fps,
  );
  const timedTransitionProgress = frame - activeCueStartFrame;
  const isTimedTransition =
    timedMode &&
    activeIndex > 0 &&
    timedTransitionProgress >= 0 &&
    timedTransitionProgress < transitionFrames;
  const currentOpacity = timedMode
    ? isTimedTransition
      ? interpolate(
          timedTransitionProgress,
          [transitionFrames * 0.36, transitionFrames],
          [0, 1],
          {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          },
        )
      : 1
    : (() => {
        const transitionStart = slideFrames - transitionFrames;
        const slideFrame = loopFrame - loopActiveIndex * slideFrames;
        return orderedCues.length > 1 && slideFrame >= transitionStart
          ? interpolate(
              slideFrame - transitionStart,
              [0, transitionFrames * 0.42],
              [1, 0],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              },
            )
          : 1;
      })();
  const currentY = timedMode
    ? isTimedTransition
      ? interpolate(
          timedTransitionProgress,
          [transitionFrames * 0.36, transitionFrames],
          [24, 0],
          {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          },
        )
      : 0
    : (() => {
        const transitionStart = slideFrames - transitionFrames;
        const slideFrame = loopFrame - loopActiveIndex * slideFrames;
        return orderedCues.length > 1 && slideFrame >= transitionStart
          ? interpolate(
              slideFrame - transitionStart,
              [0, transitionFrames * 0.42],
              [0, -28],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              },
            )
          : 0;
      })();
  const secondaryHeadline = timedMode ? previousHeadline : nextHeadline;
  const secondaryHeadlineSize = timedMode
    ? previousHeadlineSize
    : nextHeadlineSize;
  const secondaryOpacity = timedMode
    ? isTimedTransition
      ? interpolate(
          timedTransitionProgress,
          [0, transitionFrames * 0.42],
          [1, 0],
          {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          },
        )
      : 0
    : (() => {
        const transitionStart = slideFrames - transitionFrames;
        const slideFrame = loopFrame - loopActiveIndex * slideFrames;
        return orderedCues.length > 1 && slideFrame >= transitionStart
          ? interpolate(
              slideFrame - transitionStart,
              [transitionFrames * 0.58, transitionFrames],
              [0, 1],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              },
            )
          : 0;
      })();
  const secondaryY = timedMode
    ? isTimedTransition
      ? interpolate(
          timedTransitionProgress,
          [0, transitionFrames * 0.42],
          [0, -24],
          {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          },
        )
      : -24
    : (() => {
        const transitionStart = slideFrames - transitionFrames;
        const slideFrame = loopFrame - loopActiveIndex * slideFrames;
        return orderedCues.length > 1 && slideFrame >= transitionStart
          ? interpolate(
              slideFrame - transitionStart,
              [transitionFrames * 0.58, transitionFrames],
              [28, 0],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              },
            )
          : 36;
      })();
  const headlineStyle = (
    fontSize: number,
    opacity: number,
    translateY: number,
  ): React.CSSProperties => ({
    position: "absolute",
    left: 0,
    right: 0,
    top: "50%",
    margin: 0,
    color: brand.white,
    fontFamily: typography.serif,
    fontSize,
    fontWeight: 400,
    lineHeight: 1.08,
    letterSpacing: 0,
    textTransform: "uppercase",
    textShadow: "0 10px 34px rgba(0,0,0,0.46)",
    transform: `translateY(calc(-50% + ${translateY}px))`,
    opacity,
  });

  return (
    <div
      style={{
        position: "absolute",
        left: layout.lower.left,
        top: layout.lower.top,
        width: layout.lower.width,
        height: layout.lower.height,
        display: "flex",
        background: "linear-gradient(90deg, rgba(5,5,6,.995), rgba(17,17,19,.98) 56%, rgba(7,7,8,.97))",
        borderTop: "1px solid rgba(245,247,250,0.32)",
        boxShadow: "0 -18px 58px rgba(0,0,0,0.34)",
      }}
    >
      <BrandRibbon category={category} compact />
      <LogoBug category={category} />
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "24px 40px 22px 48px",
        }}
      >
        <div
          style={{
            position: "relative",
            height: 134,
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
          }}
        >
          <h1
            style={headlineStyle(currentHeadlineSize, currentOpacity, currentY)}
          >
            {currentHeadline}
          </h1>
          {orderedCues.length > 1 ? (
            <h1
              style={headlineStyle(
                secondaryHeadlineSize,
                secondaryOpacity,
                secondaryY,
              )}
            >
              {secondaryHeadline}
            </h1>
          ) : null}
        </div>

        <div
          style={{
            width: "100%",
            display: "grid",
            gridTemplateColumns: "1fr 150px",
            gap: 18,
            alignItems: "center",
          }}
        >
          <div
            style={{
              height: 2,
              background: `linear-gradient(90deg, ${theme.accent}, ${theme.accentEnd}, rgba(245,247,250,0.12))`,
            }}
          />
          <div
            style={{
              color: "rgba(245,247,250,0.62)",
              fontFamily: typography.sans,
              fontSize: 16,
              fontWeight: 700,
              letterSpacing: 0,
              textTransform: "uppercase",
              textAlign: "right",
            }}
          >
            {theme.label} · SYNTHPOST
          </div>
        </div>
      </div>
    </div>
  );
};
