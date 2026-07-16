import type { TimelineSegment, VisualCandidate } from "../contracts";

const VISUAL_TEMPLATE_IDS = new Set([
  "split_anchor_visual",
  "fullscreen_news_visual",
  "quote_card",
]);

const FULLSCREEN_ROLES = new Set([
  "primary_footage",
  "evidence",
  "context",
  "atmosphere",
]);

const isRenderableCandidate = (
  visual: VisualCandidate,
  templateId: string,
) => {
  if (
    !visual.download_path ||
    visual.review_status === "rejected" ||
    visual.review_status === "blocked" ||
    !["image", "video"].includes(visual.media_type)
  ) {
    return false;
  }
  if (templateId === "fullscreen_news_visual") {
    return FULLSCREEN_ROLES.has(visual.content_role);
  }
  if (templateId === "quote_card") {
    return (
      visual.media_type === "image" &&
      ["evidence", "context"].includes(visual.content_role)
    );
  }
  return true;
};

const reviewTimestamp = (visual: VisualCandidate) => {
  if (!visual.reviewed_at) return 0;
  const value = Date.parse(visual.reviewed_at);
  return Number.isFinite(value) ? value : 0;
};

const candidateRank = (visual: VisualCandidate) => [
  ["approved", "manual_approved"].includes(visual.review_status) ? 1 : 0,
  reviewTimestamp(visual),
  visual.relevance_score,
  visual.visual_quality_score,
  visual.source_authority,
];

const compareCandidates = (left: VisualCandidate, right: VisualCandidate) => {
  const leftRank = candidateRank(left);
  const rightRank = candidateRank(right);
  for (let index = 0; index < leftRank.length; index += 1) {
    if (leftRank[index] !== rightRank[index]) {
      return rightRank[index] - leftRank[index];
    }
  }
  return left.asset_id.localeCompare(right.asset_id);
};

const preferredVisualId = (segment: TimelineSegment) => {
  if (segment.visual.asset_id) return segment.visual.asset_id;
  const stored = segment.overlays.data?.preferred_visual_asset_id;
  return typeof stored === "string" && stored ? stored : null;
};

export const findTimelineVisual = (
  segment: TimelineSegment,
  templateId: string,
  visuals: VisualCandidate[],
) => {
  const preferredId = preferredVisualId(segment);
  if (preferredId) {
    const preferred = visuals.find(
      (visual) =>
        visual.asset_id === preferredId &&
        isRenderableCandidate(visual, templateId),
    );
    if (preferred) return preferred;
  }

  const sectionCandidates = visuals
    .filter(
      (visual) =>
        visual.section_ids.includes(segment.section_id) &&
        isRenderableCandidate(visual, templateId),
    )
    .sort(compareCandidates);
  if (sectionCandidates.length > 0) return sectionCandidates[0];

  return visuals
    .filter(
      (visual) =>
        visual.section_ids.length === 0 &&
        isRenderableCandidate(visual, templateId),
    )
    .sort(compareCandidates)[0];
};

const fallbackVisual = (): TimelineSegment["visual"] => ({
  asset_id: null,
  path: null,
  media_type: "fallback",
  content_role: "fallback",
  source: "SynthPost",
  source_url: null,
  rights_tier: "green",
  review_status: "approved",
  audio_mode: "muted",
  trim_start: null,
  trim_end: null,
  has_audio: false,
  attribution_text: "",
  content_cleanliness_status: "passed",
  approval_blockers: [],
});

const segmentVisual = (
  visual: VisualCandidate,
): TimelineSegment["visual"] => ({
  asset_id: visual.asset_id,
  path: visual.download_path,
  media_type: visual.media_type,
  content_role: visual.content_role,
  source: visual.provider,
  source_url: visual.source_url,
  rights_tier: visual.rights_tier,
  review_status: visual.review_status,
  audio_mode: "muted",
  trim_start: visual.trim_start,
  trim_end: visual.trim_end,
  has_audio: visual.has_audio,
  attribution_text: visual.attribution_text,
  content_cleanliness_status: visual.content_cleanliness_status,
  approval_blockers: visual.approval_blockers,
});

export const applyTimelineTemplate = (
  segment: TimelineSegment,
  templateId: string,
  visuals: VisualCandidate[],
): TimelineSegment => {
  const visualTemplate = VISUAL_TEMPLATE_IDS.has(templateId);
  const selectedVisual = visualTemplate
    ? findTimelineVisual(segment, templateId, visuals)
    : undefined;
  const retainedVisualId =
    selectedVisual?.asset_id ?? preferredVisualId(segment) ?? null;
  const visual = selectedVisual ? segmentVisual(selectedVisual) : fallbackVisual();
  const fullscreenVisual = templateId === "fullscreen_news_visual";

  return {
    ...segment,
    template: { ...segment.template, template_id: templateId },
    anchor: {
      ...segment.anchor,
      visible: !fullscreenVisual,
      speaking: true,
    },
    visual,
    audio: {
      ...segment.audio,
      mode: "narration",
      narration_volume: 1,
      source_volume: 0,
      ducking: false,
    },
    overlays: {
      ...segment.overlays,
      attribution: selectedVisual?.attribution_text ?? "",
      data: {
        ...(segment.overlays.data ?? {}),
        preferred_visual_asset_id: retainedVisualId,
      },
    },
  };
};
