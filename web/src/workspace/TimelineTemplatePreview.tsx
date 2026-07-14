import React from "react";
import { artifactUrl } from "../api/client";
import type { TimelineSegment, VisualCandidate } from "../contracts";

const TEMPLATE_NAMES: Record<string, string> = {
  split_anchor_visual: "Split anchor + visual",
  fullscreen_news_visual: "Full-screen visual",
  fullscreen_anchor: "Full-screen anchor",
  fallback_anchor: "Fallback anchor",
  quote_card: "Quote card",
};

const readableLabel = (value: string) =>
  value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");

const compactLabel = (value: string, maxLength = 96) =>
  value.length > maxLength ? `${value.slice(0, maxLength - 1).trimEnd()}…` : value;

const AnchorSilhouette = () => (
  <div className="timeline-preview-anchor" aria-hidden="true">
    <span className="timeline-preview-anchor-head" />
    <span className="timeline-preview-anchor-body" />
  </div>
);

const PreviewMedia: React.FC<{
  segment: TimelineSegment;
  visual?: VisualCandidate;
}> = ({ segment, visual }) => {
  const mediaType = segment.visual.media_type;
  const thumbnailPath = visual?.thumbnail_path;
  const localPath = visual?.download_path ?? segment.visual.path;
  const imagePath = thumbnailPath ?? (mediaType === "image" ? localPath : null);
  const videoPath = mediaType === "video" && !imagePath ? localPath : null;
  const mediaKey = imagePath ?? videoPath ?? "missing";
  const [failedKey, setFailedKey] = React.useState<string | null>(null);
  const failed = failedKey === mediaKey;

  if (imagePath && !failed) {
    return (
      <img
        className="timeline-preview-media"
        src={artifactUrl(imagePath)}
        alt=""
        onError={() => setFailedKey(mediaKey)}
      />
    );
  }

  if (videoPath && !failed) {
    return (
      <video
        className="timeline-preview-media"
        src={artifactUrl(videoPath)}
        aria-hidden="true"
        muted
        playsInline
        preload="metadata"
        onLoadedMetadata={(event) => {
          const video = event.currentTarget;
          const requestedTime = segment.visual.trim_start ?? 0.1;
          if (Number.isFinite(video.duration) && video.duration > 0) {
            video.currentTime = Math.min(requestedTime, Math.max(0, video.duration - 0.1));
          }
        }}
        onError={() => setFailedKey(mediaKey)}
      />
    );
  }

  return (
    <div className="timeline-preview-media-missing" aria-hidden="true">
      <span>{mediaType === "fallback" ? "SP" : mediaType === "video" ? "▶" : "▣"}</span>
      <small>{mediaType === "fallback" ? "Anchor" : readableLabel(mediaType)}</small>
    </div>
  );
};

export const TimelineTemplatePreview: React.FC<{
  segment: TimelineSegment;
  visual?: VisualCandidate;
}> = ({ segment, visual }) => {
  const templateId = segment.template.template_id;
  const templateName = TEMPLATE_NAMES[templateId] ?? readableLabel(templateId);
  const visualName = compactLabel(
    visual?.title ||
      segment.visual.attribution_text ||
      readableLabel(segment.visual.content_role),
  );
  const lowerThird = segment.overlays.lower_third || segment.overlays.chyron;
  const media = <PreviewMedia segment={segment} visual={visual} />;

  return (
    <aside
      className="timeline-template-preview"
      aria-label={`${templateName} preview with ${visualName}`}
      title={`${templateName} · ${visualName}`}
    >
      <div className="timeline-preview-heading">
        <span>Layout preview</span>
        <span>{segment.visual.media_type}</span>
      </div>
      <div className={`timeline-preview-canvas template-${templateId}`}>
        <div className="timeline-preview-brand" aria-hidden="true">
          SYNTH<span>POST</span>
        </div>

        {templateId === "split_anchor_visual" ? (
          <>
            <div className="timeline-preview-anchor-pane">
              <AnchorSilhouette />
            </div>
            <div className="timeline-preview-visual-pane">{media}</div>
          </>
        ) : templateId === "fullscreen_news_visual" ? (
          <div className="timeline-preview-fullscreen-media">{media}</div>
        ) : templateId === "quote_card" ? (
          <>
            <div className="timeline-preview-quote-backdrop">{media}</div>
            <div className="timeline-preview-quote">
              <span>“</span>
              <strong>{segment.overlays.quote_text || segment.script_text}</strong>
            </div>
          </>
        ) : (
          <div className="timeline-preview-anchor-stage">
            <AnchorSilhouette />
          </div>
        )}

        {lowerThird && templateId !== "quote_card" ? (
          <div className="timeline-preview-lower-third">
            <span />
            <strong>{lowerThird}</strong>
          </div>
        ) : null}
        {segment.overlays.attribution && templateId === "fullscreen_news_visual" ? (
          <div className="timeline-preview-attribution">SOURCE</div>
        ) : null}
      </div>
      <div className="timeline-preview-caption">
        <strong>{templateName}</strong>
        <span>{visualName}</span>
      </div>
    </aside>
  );
};
