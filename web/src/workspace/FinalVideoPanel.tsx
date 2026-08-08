import React from "react";
import { api, artifactUrl } from "../api/client";
import { InlineJobCard } from "../components/InlineJobCard";
import { StatusBadge } from "../components/StatusBadge";
import { useStudio } from "../state/useStudio";

export const FinalVideoPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [busy, setBusy] = React.useState(false);
  const story = studio.candidates.find(
    (candidate) => candidate.story_id === storyId,
  );
  const episode = studio.episodes.find(
    (candidate) => candidate.episode_id === studio.selectedEpisodeId,
  );
  const jobs = studio.jobs.filter(
    (job) =>
      (job.story_id === storyId &&
        ["render_avatar", "render_story"].includes(job.job_type)) ||
      (job.episode_id === studio.selectedEpisodeId &&
        job.job_type === "assemble_episode"),
  );
  const activeJob = jobs.find((job) =>
    ["queued", "running", "cancel_requested"].includes(job.status),
  );
  const failedJob = jobs.find((job) => job.status === "failed");
  const isComplete = story?.workflow_state === "completed";

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError("");
      setBusy(true);
      await fn();
      await studio.refreshAll();
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const retryProductionJob = async (job: (typeof jobs)[number]) => {
    if (job.autonomy_run_id) {
      const run = await api.retryAutonomyRun(job.autonomy_run_id);
      studio.mergeAutonomyRun(run);
      return;
    }
    await api.retryJob(job.job_id);
  };

  const cancelProductionJob = async (job: (typeof jobs)[number]) => {
    if (job.autonomy_run_id) {
      const run = await api.cancelAutonomyRun(job.autonomy_run_id);
      studio.mergeAutonomyRun(run);
      return;
    }
    await api.cancelJob(job.job_id);
  };

  const phase =
    activeJob?.job_type === "assemble_episode"
      ? "Adding outro & assembling"
      : activeJob?.job_type === "render_avatar"
        ? "Rendering anchor"
        : activeJob
          ? "Rendering production video"
          : isComplete
            ? "Final video ready"
            : "Ready for production";

  return (
    <div className="final-video-workspace animate-fade-in">
      <section className="final-video-hero">
        <div className="final-video-signal" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div>
          <div className="generation-ledger-kicker">One production output</div>
          <h2>{phase}</h2>
          <p>
            Production render and episode assembly run as one flow. The final
            file includes the approved timeline, anchor, visuals, audio mix, and
            channel outro.
          </p>
        </div>
        <StatusBadge tone={isComplete ? "green" : activeJob ? "blue" : "amber"}>
          {isComplete
            ? "Complete"
            : activeJob
              ? `${Math.round(activeJob.progress)}%`
              : "Awaiting render"}
        </StatusBadge>
      </section>

      {activeJob && (
        <section className="final-video-progress">
          <div className="row-between">
            <strong>{activeJob.stage}</strong>
            <span>{Math.round(activeJob.progress)}%</span>
          </div>
          <div className="progress-bar">
            <div
              className="progress-bar-fill"
              style={{ width: `${activeJob.progress}%` }}
            />
          </div>
          <div className="final-video-phases">
            <span className={activeJob.job_type !== "assemble_episode" ? "active" : "done"}>
              01 Render
            </span>
            <span className={activeJob.job_type === "assemble_episode" ? "active" : ""}>
              02 Assemble + Outro
            </span>
            <span>03 Final File</span>
          </div>
        </section>
      )}

      {episode?.final_output_path && (
        <section className="final-video-output">
          <div className="row-between">
            <div>
              <div className="generation-ledger-kicker">
                {isComplete ? "Latest final" : "Previous final retained"}
              </div>
              <h2>{episode.title}</h2>
            </div>
            <button
              className="btn-finder"
              disabled={busy}
              onClick={() =>
                void act(() => api.revealEpisodeOutput(episode.episode_id))
              }
            >
              ⌖ Show in Finder
            </button>
          </div>
          <video
            controls
            preload="metadata"
            src={artifactUrl(episode.final_output_path, episode.updated_at)}
          />
          <div className="final-video-output-path">{episode.final_output_path}</div>
        </section>
      )}

      {!isComplete && !activeJob && (
        <section className="final-video-action">
          <div>
            <h2>{failedJob ? "Final generation needs attention" : "Generate the final video"}</h2>
            <p>
              {failedJob
                ? failedJob.error || "The previous production job did not complete."
                : "Timeline approval normally starts this automatically. Use this action to resume or retry the production flow."}
            </p>
          </div>
          <button
            className="btn-primary btn-lg"
            disabled={busy}
            onClick={() => void act(() => api.generateFinalVideo(storyId))}
          >
            {busy ? "Starting…" : failedJob ? "Retry Final Video" : "Generate Final Video"}
          </button>
        </section>
      )}

      <details className="final-video-job-history">
        <summary>Production job history ({jobs.length})</summary>
        <div className="stack">
          {jobs.length === 0 ? (
            <p className="text-muted">No production jobs yet.</p>
          ) : (
            jobs.slice(0, 8).map((job) => {
              const autonomyRun = job.autonomy_run_id
                ? studio.autonomyRuns.find(
                    (run) => run.run_id === job.autonomy_run_id,
                  )
                : undefined;
              const canRetryAutonomyRun =
                !job.autonomy_run_id || autonomyRun?.status === "needs_attention";
              const canCancelAutonomyRun =
                !job.autonomy_run_id ||
                Boolean(
                  autonomyRun &&
                    ["queued", "running", "needs_attention"].includes(
                      autonomyRun.status,
                    ),
                );
              return (
                <InlineJobCard
                  key={job.job_id}
                  job={job}
                  retryLabel={job.autonomy_run_id ? "Retry shift" : undefined}
                  cancelLabel={job.autonomy_run_id ? "Stop shift" : undefined}
                  onRetry={
                    canRetryAutonomyRun
                      ? () => void act(() => retryProductionJob(job))
                      : undefined
                  }
                  onCancel={
                    canCancelAutonomyRun
                      ? () => void act(() => cancelProductionJob(job))
                      : undefined
                  }
                />
              );
            })
          )}
        </div>
      </details>
    </div>
  );
};
