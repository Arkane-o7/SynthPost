import React from "react";
import { api, artifactUrl } from "../api/client";
import { useStudio } from "../state/useStudio";
import { InlineJobCard } from "../components/InlineJobCard";

export const RenderPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [busy, setBusy] = React.useState(false);

  const storyJobs = studio.jobs.filter(
    (j) =>
      j.story_id === storyId &&
      ["render_avatar", "render_story"].includes(j.job_type),
  );
  const story = studio.candidates.find(
    (candidate) => candidate.story_id === storyId,
  );
  const episodeId = story?.episode_id ?? studio.selectedEpisodeId;
  const storyOutputPath = episodeId
    ? `episodes/${episodeId}/stories/${storyId}/composited.mp4`
    : null;
  const testStoryOutputPath = episodeId
    ? `episodes/${episodeId}/stories/${storyId}/composited_TEST_MODE.mp4`
    : null;
  const hasProductionStoryOutput = storyJobs.some(
    (job) =>
      job.job_type === "render_story" &&
      job.status === "completed" &&
      job.render_profile === "production",
  );
  const hasTestStoryOutput = storyJobs.some(
    (job) =>
      job.job_type === "render_story" &&
      job.status === "completed" &&
      job.render_profile === "preview",
  );

  const activeJob = (jobType: string, profile: string) =>
    storyJobs.find(
      (job) =>
        job.job_type === jobType &&
        job.render_profile === profile &&
        ["queued", "running"].includes(job.status),
    );

  const activeAvatarProduction = activeJob("render_avatar", "production");
  const activeStoryProduction = activeJob("render_story", "production");

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
              disabled={busy || Boolean(activeAvatarProduction)}
              onClick={() =>
                act(() => api.renderAvatar(storyId, "production", false))
              }
            >
              {activeAvatarProduction
                ? "Avatar Production Running…"
                : "Render Avatar (production)"}
            </button>
            <button
              className="btn-primary"
              disabled={busy || Boolean(activeStoryProduction)}
              onClick={() =>
                act(() => api.renderStory(storyId, "production", false))
              }
            >
              {activeStoryProduction
                ? "Story Production Running…"
                : "Render Story (production)"}
            </button>
          </div>
          <p className="text-muted" style={{ fontSize: 12, marginTop: 8 }}>
            Server-side validation still blocks unsafe production renders when
            scripts, timeline, or visual rights are not approved.
          </p>
        </div>

        {hasProductionStoryOutput && storyOutputPath && (
          <div className="card stack">
            <h2>Production Story Output</h2>
            <div className="font-mono text-muted" style={{ fontSize: 12 }}>
              {storyOutputPath}
            </div>
            <video
              controls
              src={artifactUrl(storyOutputPath)}
              style={{ width: "100%", borderRadius: "var(--radius-md)" }}
            />
          </div>
        )}


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
