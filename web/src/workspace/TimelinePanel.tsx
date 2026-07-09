import React from "react";
import { api } from "../api/client";
import { useStudio } from "../state/useStudio";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { formatDuration } from "../lib/formatters";
import type { TimelinePlan, TimelineSegment } from "../contracts";

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

export const TimelinePanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [timeline, setTimeline] = React.useState<TimelinePlan | null>(null);
  const [dragIndex, setDragIndex] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(
    () =>
      api
        .readTimeline(storyId)
        .then(setTimeline)
        .catch(() => setTimeline(null)),
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
    setTimeline({ ...timeline, segments: fixed });
  };

  const totalDuration = timeline
    ? timeline.segments.reduce((sum, s) => sum + s.duration, 0)
    : 0;

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
            disabled={busy}
            onClick={() =>
              act(async () => {
                setTimeline(await api.generateTimeline(storyId));
              })
            }
          >
            {busy ? "Generating…" : "Generate Timeline"}
          </button>
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
        <div className="row">
          <button
            className="btn-primary"
            disabled={busy}
            onClick={() =>
              act(async () => {
                setTimeline(await api.generateTimeline(storyId));
              })
            }
          >
            Regenerate
          </button>
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
            disabled={busy}
            onClick={() =>
              act(async () => {
                await api.approveTimeline(storyId);
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
              draggable
              onDragStart={() => setDragIndex(idx)}
              onDragEnd={() => setDragIndex(null)}
            >
              ≡
            </div>
            <div className="stack">
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
                            ? {
                                ...s,
                                template: {
                                  ...s.template,
                                  template_id: e.target.value,
                                },
                              }
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
