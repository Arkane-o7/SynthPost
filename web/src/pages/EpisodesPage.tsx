import React from "react";
import { api, artifactUrl } from "../api/client";
import { useStudio } from "../state/useStudio";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";

export const EpisodesPage: React.FC<{ onOpenStudio: () => void }> = ({
  onOpenStudio,
}) => {
  const studio = useStudio();
  const [title, setTitle] = React.useState("");
  const [profile, setProfile] = React.useState("preview");
  const [editingId, setEditingId] = React.useState("");
  const [editTitle, setEditTitle] = React.useState("");
  const [editProfile, setEditProfile] = React.useState("preview");
  const [busy, setBusy] = React.useState(false);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      setBusy(true);
      studio.setError("");
      await fn();
      await studio.refreshAll();
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  if (!studio.selectedProjectId) {
    return (
      <EmptyState
        icon="▤"
        title="Choose a project first"
        description="Select or create a project in Studio before creating a remote episode."
      />
    );
  }

  return (
    <div className="stack-lg animate-fade-in">
      <div className="mobile-page-hero">
        <div>
          <div className="topbar-kicker">Remote production desk</div>
          <h1>Episodes</h1>
          <p>Create, configure, launch, and collect finished episodes from your phone.</p>
        </div>
        <div className="mobile-hero-stat">
          <strong>{studio.episodes.length}</strong>
          <span>on this project</span>
        </div>
      </div>

      <section className="card mobile-create-episode stack">
        <div>
          <div className="mobile-section-kicker">New assignment</div>
          <h2>Create an episode</h2>
        </div>
        <div className="episode-create-fields">
          <label>
            Episode title
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Morning world briefing"
            />
          </label>
          <label>
            Default render
            <select value={profile} onChange={(event) => setProfile(event.target.value)}>
              <option value="preview">Preview</option>
              <option value="production">Production</option>
            </select>
          </label>
          <button
            type="button"
            className="btn-primary btn-lg"
            disabled={busy || !title.trim()}
            onClick={() =>
              void act(async () => {
                const episode = await api.createEpisode(
                  studio.selectedProjectId,
                  title.trim(),
                  profile,
                );
                studio.setSelectedEpisodeId(episode.episode_id);
                setTitle("");
              })
            }
          >
            <span aria-hidden="true">＋</span> Create episode
          </button>
        </div>
      </section>

      <div className="episode-control-list">
        {studio.episodes.map((episode) => {
          const selected = episode.episode_id === studio.selectedEpisodeId;
          const editing = editingId === episode.episode_id;
          const assemblyJob = studio.jobs.find(
            (job) =>
              job.episode_id === episode.episode_id &&
              job.job_type === "assemble_episode" &&
              ["queued", "paused", "running"].includes(job.status),
          );
          return (
            <article
              key={episode.episode_id}
              className={`episode-control-card ${selected ? "selected" : ""}`}
            >
              <div className="episode-control-accent" />
              <div className="episode-control-main">
                <div className="episode-control-heading">
                  <div>
                    <div className="mobile-section-kicker">
                      {selected ? "Active on phone" : "Episode"}
                    </div>
                    <h2>{episode.title}</h2>
                  </div>
                  <StatusBadge status={episode.status}>{episode.status}</StatusBadge>
                </div>
                <div className="episode-control-metrics">
                  <span><b>{episode.story_ids.length}</b> stories</span>
                  <span><b>{episode.render_profile}</b> profile</span>
                  <span><b>{assemblyJob ? `${Math.round(assemblyJob.progress)}%` : "idle"}</b> renderer</span>
                </div>

                {assemblyJob && (
                  <div className="episode-live-job">
                    <div className="row-between">
                      <strong>{assemblyJob.stage}</strong>
                      <span>{Math.round(assemblyJob.progress)}%</span>
                    </div>
                    <div className="progress-bar">
                      <div className="progress-bar-fill" style={{ width: `${assemblyJob.progress}%` }} />
                    </div>
                  </div>
                )}

                {editing && (
                  <div className="episode-inline-editor">
                    <label>
                      Title
                      <input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} />
                    </label>
                    <label>
                      Render profile
                      <select value={editProfile} onChange={(event) => setEditProfile(event.target.value)}>
                        <option value="preview">Preview</option>
                        <option value="production">Production</option>
                      </select>
                    </label>
                    <div className="row-tight">
                      <button
                        type="button"
                        className="btn-success"
                        disabled={busy || !editTitle.trim()}
                        onClick={() =>
                          void act(async () => {
                            await api.updateEpisode(episode.episode_id, {
                              title: editTitle.trim(),
                              render_profile: editProfile,
                            });
                            setEditingId("");
                          })
                        }
                      >
                        Save changes
                      </button>
                      <button type="button" onClick={() => setEditingId("")}>Cancel</button>
                    </div>
                  </div>
                )}

                {episode.final_output_path && (
                  <div className="episode-output-preview">
                    <video controls preload="metadata" src={artifactUrl(episode.final_output_path)} />
                    <a className="btn btn-download" href={artifactUrl(episode.final_output_path)} download>
                      ↓ Download final video
                    </a>
                  </div>
                )}

                <div className="episode-control-actions">
                  <button
                    type="button"
                    className={selected ? "btn-primary" : ""}
                    onClick={() => {
                      studio.setSelectedEpisodeId(episode.episode_id);
                      onOpenStudio();
                    }}
                  >
                    {selected ? "Open production" : "Select & open"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setEditingId(episode.episode_id);
                      setEditTitle(episode.title);
                      setEditProfile(episode.render_profile);
                    }}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    disabled={busy || Boolean(assemblyJob) || episode.story_ids.length === 0}
                    onClick={() =>
                      void act(() => api.assembleEpisode(episode.episode_id, "production", false))
                    }
                  >
                    {assemblyJob ? "Assembling…" : "Assemble production"}
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
};
