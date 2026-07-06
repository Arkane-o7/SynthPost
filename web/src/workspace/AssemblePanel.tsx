import React from "react";
import { api } from "../api/client";
import { useStudio } from "../state/useStudio";
import { StatusBadge } from "../components/StatusBadge";
import { InlineJobCard } from "../components/InlineJobCard";

export const AssemblePanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [busy, setBusy] = React.useState(false);

  const episode = studio.episodes.find(
    (e) => e.episode_id === studio.selectedEpisodeId,
  );

  const episodeJobs = studio.jobs.filter(
    (j) => j.episode_id === studio.selectedEpisodeId,
  );

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
      <div className="card stack-lg">
        <h2>Episode Assembly</h2>

        {episode && (
          <div>
            <h3>Episode</h3>
            <div className="row-tight" style={{ marginTop: 4 }}>
              <span style={{ fontWeight: 600 }}>{episode.title}</span>
              <StatusBadge status={episode.status}>
                {episode.status}
              </StatusBadge>
            </div>
            <div className="text-muted" style={{ fontSize: 13, marginTop: 4 }}>
              {episode.story_ids.length} stor
              {episode.story_ids.length === 1 ? "y" : "ies"} · Profile:{" "}
              {episode.render_profile}
            </div>
          </div>
        )}

        <p className="text-muted" style={{ fontSize: 13 }}>
          Assembly concatenates rendered story segments into a single episode
          video and appends the SynthPost outro. The intro bumper is currently
          disabled until a final intro is designed.
        </p>

        <div className="row">
          <button
            disabled={busy || !studio.selectedEpisodeId}
            onClick={() =>
              act(() =>
                api.assembleEpisode(studio.selectedEpisodeId, "preview", true),
              )
            }
          >
            {busy ? "Assembling…" : "Assemble Test Episode"}
          </button>
          <button
            className="btn-primary btn-lg"
            disabled={busy || !studio.selectedEpisodeId}
            onClick={() =>
              act(() =>
                api.assembleEpisode(
                  studio.selectedEpisodeId,
                  "production",
                  false,
                ),
              )
            }
          >
            {busy ? "Assembling…" : "Assemble Production Episode"}
          </button>
        </div>

        {episode?.final_output_path && (
          <div>
            <h3>Output</h3>
            <div
              className="font-mono"
              style={{
                padding: "10px 14px",
                background: "var(--surface-inset)",
                borderRadius: "var(--radius-sm)",
                fontSize: 12,
                marginTop: 4,
                wordBreak: "break-all",
              }}
            >
              {episode.final_output_path}
            </div>
          </div>
        )}
      </div>

      <div className="card stack">
        <h2>Assembly Jobs</h2>
        {episodeJobs.length === 0 ? (
          <p className="text-muted" style={{ fontSize: 13 }}>
            No assembly jobs yet.
          </p>
        ) : (
          episodeJobs
            .slice(0, 6)
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
