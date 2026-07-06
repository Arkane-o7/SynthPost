import React from "react";
import { api } from "../api/client";
import { useStudio } from "../state/useStudio";
import { InlineJobCard } from "../components/InlineJobCard";

export const RenderPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [busy, setBusy] = React.useState(false);

  const storyJobs = studio.jobs.filter((j) => j.story_id === storyId);

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

  return (
    <div
      className="grid grid-2 animate-fade-in"
      style={{ alignItems: "start" }}
    >
      {/* Render controls */}
      <div className="stack-lg">
        {/* Test mode */}
        <div className="render-mode-card">
          <h3>Test Mode</h3>
          <p className="text-muted" style={{ fontSize: 13, marginBottom: 12 }}>
            Test renders use the preview profile and produce artifacts in the
            test directory. Safe to run repeatedly.
          </p>
          <div className="row">
            <button
              disabled={busy}
              onClick={() =>
                act(() => api.renderAvatar(storyId, "preview", true))
              }
            >
              Render Avatar (test)
            </button>
            <button
              disabled={busy}
              onClick={() =>
                act(() => api.renderStory(storyId, "preview", true))
              }
            >
              Render Story (test)
            </button>
          </div>
        </div>

        {/* Production */}
        <div
          className="render-mode-card"
          style={{ borderColor: "var(--status-amber-bd)" }}
        >
          <h3>Production</h3>
          <div
            className="validation-msg validation-warning"
            style={{ marginBottom: 12 }}
          >
            ⚠ Production rendering uses the approved story state and can be
            slow, especially with the real avatar engine.
          </div>
          <div className="row">
            <button
              disabled={busy}
              onClick={() =>
                act(() => api.renderAvatar(storyId, "production", false))
              }
            >
              Render Avatar (production)
            </button>
            <button
              className="btn-primary"
              disabled={busy}
              onClick={() =>
                act(() => api.renderStory(storyId, "production", false))
              }
            >
              Render Story (production)
            </button>
          </div>
          <p className="text-muted" style={{ fontSize: 12, marginTop: 8 }}>
            Server-side validation still blocks unsafe production renders when
            scripts, timeline, or visual rights are not approved.
          </p>
        </div>
      </div>

      {/* Related jobs */}
      <div className="card stack">
        <h2>Related Jobs</h2>
        {storyJobs.length === 0 ? (
          <p className="text-muted" style={{ fontSize: 13 }}>
            No render jobs for this story yet.
          </p>
        ) : (
          storyJobs
            .slice(0, 8)
            .map((job) => (
              <InlineJobCard
                key={job.job_id}
                job={job}
                onRetry={() => act(() => api.retryJob(job.job_id))}
                onCancel={() => act(() => api.cancelJob(job.job_id))}
              />
            ))
        )}
      </div>
    </div>
  );
};
