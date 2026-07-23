import React from "react";
import { api } from "../api/client";
import { useStudio } from "../state/useStudio";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { formatDuration } from "../lib/formatters";
import { TimelineTemplatePreview } from "./TimelineTemplatePreview";
import { applyTimelineTemplate } from "./timelineVisualSelection";
import type {
  NarrationArtifact,
  NarrationBeatTiming,
  TimelinePlan,
  TimelineSegment,
  VisualCandidate,
} from "../contracts";

const TEMPLATE_IDS = [
  "split_anchor_visual",
  "fullscreen_news_visual",
  "fullscreen_anchor",
  "fallback_anchor",
  "quote_card",
];

function reorder<T>(items: T[], from: number, to: number): T[] {
  const copy = [...items];
  const [item] = copy.splice(from, 1);
  copy.splice(to, 0, item);
  return copy;
}

function narrationBeatsForSegment(
  segment: TimelineSegment,
  narration: NarrationArtifact,
): NarrationBeatTiming[] {
  const beatId = segment.overlays.data?.narration_beat_id;
  if (typeof beatId === "string" && beatId) {
    return narration.beats.filter((beat) => beat.beat_id === beatId);
  }
  return narration.beats.filter(
    (beat) => beat.section_id === segment.section_id,
  );
}

export const TimelinePanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [timeline, setTimeline] = React.useState<TimelinePlan | null>(null);
  const [visuals, setVisuals] = React.useState<VisualCandidate[]>([]);
  const [narration, setNarration] = React.useState<NarrationArtifact | null>(null);
  const [dragIndex, setDragIndex] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(
    () =>
      Promise.all([
        api.readTimeline(storyId),
        api.listVisuals(storyId).catch(() => [] as VisualCandidate[]),
        api.readNarration(storyId).catch(() => null),
      ])
        .then(([nextTimeline, nextVisuals, nextNarration]) => {
          setTimeline(nextTimeline);
          setVisuals(nextVisuals);
          setNarration(nextNarration);
        })
        .catch(() => {
          setTimeline(null);
          setVisuals([]);
          setNarration(null);
        }),
    [storyId, studio.lastJobEventTimestamp],
  );
  React.useEffect(() => {
    void load();
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError("");
      setBusy(true);
      await fn();
      await studio.refreshAll();
    } catch (err) {
      studio.setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const updateSegments = (segments: TimelineSegment[]) => {
    if (!timeline) return;
    let cursor = 0;
    const fixed = segments.map((seg) => {
      const duration = Math.max(1, Number(seg.duration));
      const next = {
        ...seg,
        start_time: Number(cursor.toFixed(3)),
        end_time: Number((cursor + duration).toFixed(3)),
        duration,
      };
      cursor += duration;
      return next;
    });
    setTimeline({ ...timeline, status: "review", segments: fixed });
  };

  const totalDuration = timeline
    ? timeline.segments.reduce((sum, s) => sum + s.duration, 0)
    : 0;
  const visualsById = React.useMemo(
    () => new Map(visuals.map((visual) => [visual.asset_id, visual])),
    [visuals],
  );
  const narrationJob = studio.jobs.find(
    (job) =>
      job.story_id === storyId &&
      job.job_type === "narration_generate" &&
      ["queued", "running"].includes(job.status),
  );
  const story = studio.candidates.find(
    (candidate) => candidate.story_id === storyId,
  );
  const narrationEligible = Boolean(
    story?.workflow_state &&
      ![
        "selected",
        "researching",
        "research_ready",
        "script_generating",
        "script_review",
      ].includes(story.workflow_state),
  );
  const hasExactClock = Boolean(
    narration &&
      timeline?.segments
        .filter((segment) => segment.audio.mode !== "source")
        .every(
          (segment) =>
            segment.overlays.data?.timing_source === "kokoro_exact_samples",
        ),
  );

  if (!timeline) {
    return (
      <div className="animate-fade-in">
        <EmptyState
          icon="🎬"
          title="No timeline yet"
          description="Generate a timeline from the approved script and visuals. You can then reorder segments, change templates, and adjust durations."
        >
          <button
            className="btn-primary btn-lg"
            disabled={busy || Boolean(narrationJob) || !narration}
            onClick={() =>
              act(async () => {
                setTimeline(await api.generateTimeline(storyId));
              })
            }
          >
            {narrationJob
              ? "Generating Kokoro narration…"
              : !narration
                ? "Narration required"
                : busy
                  ? "Generating…"
                  : "Generate Timeline"}
          </button>
          {!narration && !narrationJob && (
            <button
              disabled={busy || !narrationEligible}
              title={
                narrationEligible
                  ? "Generate canonical Kokoro narration"
                  : "Approve the latest script first"
              }
              onClick={() => act(() => api.generateNarration(storyId))}
            >
              {narrationEligible
                ? "Generate narration"
                : "Approve the latest script first"}
            </button>
          )}
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="stack-lg animate-fade-in">
      {/* Toolbar */}
      <div className="card">
        <div className="row-between" style={{ marginBottom: 8 }}>
          <div className="row-tight">
            <h2>Timeline</h2>
            <StatusBadge status={timeline.status}>
              {timeline.status}
            </StatusBadge>
            <span className="text-muted" style={{ fontSize: 13 }}>
              v{timeline.version}
            </span>
          </div>
          <span className="text-muted" style={{ fontSize: 13 }}>
            {timeline.segments.length} segments ·{" "}
            {formatDuration(totalDuration)} ({Math.round(totalDuration)}s)
          </span>
        </div>
        {hasExactClock && narration && (
          <div className="validation-msg validation-success" style={{ marginBottom: 12 }}>
            ✓ Kokoro exact clock · {narration.beats.length} beats · {formatDuration(narration.duration_seconds)} · {narration.sample_rate.toLocaleString()} Hz
          </div>
        )}
        {narration && !hasExactClock && (
          <div className="validation-msg validation-warning" style={{ marginBottom: 12 }}>
            ⚠ This is a legacy estimated timeline. Regenerate it to apply the current Kokoro exact clock.
          </div>
        )}
        <div className="row">
          <button
            className="btn-primary"
            disabled={busy || !narration || Boolean(narrationJob)}
            title={
              narration
                ? "Regenerate from the current exact narration"
                : "Generate the current Kokoro narration first"
            }
            onClick={() =>
              act(async () => {
                setTimeline(await api.generateTimeline(storyId));
              })
            }
          >
            Regenerate
          </button>
          {!narration && (
            <button
              disabled={busy || Boolean(narrationJob) || !narrationEligible}
              onClick={() => act(() => api.generateNarration(storyId))}
            >
              {narrationJob
                ? "Generating narration…"
                : narrationEligible
                  ? "Generate Kokoro narration"
                  : "Approve the latest script first"}
            </button>
          )}
          <button
            disabled={busy || !timeline}
            onClick={() =>
              act(async () => {
                const result = await api.validateTimeline(storyId, timeline);
                setTimeline({
                  ...timeline,
                  validation_errors: result.errors,
                  validation_warnings: result.warnings,
                });
              })
            }
          >
            Validate
          </button>
          <button
            disabled={busy || !timeline}
            onClick={() =>
              act(async () => {
                await api.saveTimeline(storyId, timeline);
                await load();
              })
            }
          >
            Save Draft
          </button>
          <button
            className="btn-success"
            disabled={busy || !hasExactClock}
            title={
              hasExactClock
                ? "Approve this sample-timed timeline"
                : "Regenerate the timeline with current Kokoro narration first"
            }
            onClick={() =>
              act(async () => {
                await api.approveTimeline(storyId, timeline);
                await load();
              })
            }
          >
            ✓ Approve Timeline
          </button>
        </div>
      </div>

      {/* Segments */}
      <div className="timeline-list">
        {timeline.segments.map((seg, idx) => (
          <div
            key={seg.segment_id}
            className={`timeline-segment ${dragIndex === idx ? "dragging" : ""}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => {
              if (dragIndex !== null)
                updateSegments(reorder(timeline.segments, dragIndex, idx));
              setDragIndex(null);
            }}
          >
            <div
              className="drag-handle"
              draggable={!hasExactClock}
              title={
                hasExactClock
                  ? "Order is locked to the approved narration"
                  : "Drag to reorder this legacy timeline"
              }
              onDragStart={() => {
                if (!hasExactClock) setDragIndex(idx);
              }}
              onDragEnd={() => setDragIndex(null)}
            >
              {hasExactClock ? "🔒" : "≡"}
            </div>
            <div className="stack timeline-segment-main">
              <div className="segment-header">
                <div className="row-tight">
                  <span style={{ fontWeight: 700, fontSize: 13 }}>
                    #{idx + 1}
                  </span>
                  <span className="segment-time">
                    {seg.start_time.toFixed(1)}s – {seg.end_time.toFixed(1)}s (
                    {seg.duration.toFixed(1)}s)
                  </span>
                </div>
                <div className="segment-controls">
                  <select
                    value={seg.template.template_id}
                    onChange={(e) =>
                      updateSegments(
                        timeline.segments.map((s, i) =>
                          i === idx
                            ? applyTimelineTemplate(
                                s,
                                e.target.value,
                                visuals,
                              )
                            : s,
                        ),
                      )
                    }
                  >
                    {TEMPLATE_IDS.map((id) => (
                      <option key={id} value={id}>
                        {id}
                      </option>
                    ))}
                  </select>
                  <input
                    type="number"
                    value={seg.duration}
                    disabled={hasExactClock}
                    title={
                      hasExactClock
                        ? "Duration comes from Kokoro's exact audio samples"
                        : "Estimated legacy duration"
                    }
                    onChange={(e) =>
                      updateSegments(
                        timeline.segments.map((s, i) =>
                          i === idx
                            ? { ...s, duration: Number(e.target.value) }
                            : s,
                        ),
                      )
                    }
                  />
                </div>
              </div>
              <div className="segment-script">{seg.script_text}</div>
              {hasExactClock && narration && seg.audio.mode !== "source" && (
                <div className="timeline-beat-clock" aria-label="Exact spoken beat timing">
                  <div className="timeline-beat-clock-title">
                    Spoken beats · exact Kokoro clock
                  </div>
                  {narrationBeatsForSegment(seg, narration).map(
                    (beat, beatIndex, segmentBeats) => (
                      <div className="timeline-beat-clock-row" key={beat.beat_id}>
                        <span>
                          {(
                            seg.start_time +
                            beat.start_time -
                            segmentBeats[0].start_time
                          ).toFixed(2)}–
                          {(
                            seg.start_time +
                            beat.speech_end_time -
                            segmentBeats[0].start_time
                          ).toFixed(2)}s
                        </span>
                        <p>{beat.text}</p>
                      </div>
                    ),
                  )}
                </div>
              )}
              <div className="segment-meta">
                <span>
                  🎥 {seg.visual.content_role}{" "}
                  <StatusBadge
                    tone={
                      seg.visual.rights_tier === "green"
                        ? "green"
                        : seg.visual.rights_tier === "red"
                          ? "red"
                          : "amber"
                    }
                  >
                    {seg.visual.rights_tier}
                  </StatusBadge>
                </span>
                <span>🎙 {seg.audio.mode}</span>
                {seg.overlays.lower_third && (
                  <span>📺 {seg.overlays.lower_third}</span>
                )}
              </div>
            </div>
            <TimelineTemplatePreview
              segment={seg}
              visual={
                seg.visual.asset_id
                  ? visualsById.get(seg.visual.asset_id)
                  : undefined
              }
            />
          </div>
        ))}
      </div>

      {/* Validation results */}
      {timeline.validation_errors && timeline.validation_errors.length > 0 && (
        <div className="stack">
          {timeline.validation_errors.map((e) => (
            <div key={e} className="validation-msg validation-error">
              ✕ {e}
            </div>
          ))}
        </div>
      )}
      {timeline.validation_warnings &&
        timeline.validation_warnings.length > 0 && (
          <div className="stack">
            {timeline.validation_warnings.map((w) => (
              <div key={w} className="validation-msg validation-warning">
                ⚠ {w}
              </div>
            ))}
          </div>
        )}
      {timeline.validation_errors?.length === 0 &&
        timeline.validation_warnings?.length === 0 && (
          <div className="validation-msg validation-success">
            ✓ Timeline validates cleanly
          </div>
        )}
    </div>
  );
};
