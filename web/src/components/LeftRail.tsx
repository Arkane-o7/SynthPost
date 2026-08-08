import React from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import type { Episode } from "../contracts";
import { useStudio } from "../state/useStudio";
import { ChannelSwitcher } from "./ChannelSwitcher";
import { ThemeToggle } from "./ThemeToggle";
import {
  ChevronDown,
  ChevronRight,
  FolderClosed,
  MonitorPlay,
  Pin,
  Plus,
  Settings2,
  Trash2,
} from "lucide-react";

export type Page = "command" | "review" | "settings";

type RailIconName =
  | "settings"
  | "folder"
  | "review"
  | "pin"
  | "trash";

const RailIcon: React.FC<{ name: RailIconName }> = ({ name }) => {
  switch (name) {
    case "settings":
      return <Settings2 size={18} strokeWidth={1.8} aria-hidden="true" />;
    case "folder":
      return <FolderClosed size={18} strokeWidth={1.8} aria-hidden="true" />;
    case "review":
      return <MonitorPlay size={18} strokeWidth={1.8} aria-hidden="true" />;
    case "pin":
      return <Pin size={17} strokeWidth={1.8} aria-hidden="true" />;
    case "trash":
      return <Trash2 size={17} strokeWidth={1.8} aria-hidden="true" />;
  }
};

type DeleteTarget =
  | { kind: "project"; id: string; title: string }
  | { kind: "episode"; id: string; projectId: string; title: string };

export const LeftRail: React.FC<{
  page: Page;
  setPage: (page: Page) => void;
}> = ({ page, setPage }) => {
  const studio = useStudio();
  const [creatingProject, setCreatingProject] = React.useState(false);
  const [creatingEpisodeFor, setCreatingEpisodeFor] = React.useState("");
  const [openingEpisodeId, setOpeningEpisodeId] = React.useState("");
  const [mutatingItem, setMutatingItem] = React.useState("");
  const [deleteTarget, setDeleteTarget] = React.useState<DeleteTarget | null>(
    null,
  );
  const [expandedProjects, setExpandedProjects] = React.useState<Set<string>>(
    () =>
      new Set(
        studio.selectedProjectId ? [studio.selectedProjectId] : [],
      ),
  );
  const [episodesByProject, setEpisodesByProject] = React.useState<
    Record<string, Episode[]>
  >({});
  const [loadingProjects, setLoadingProjects] = React.useState<Set<string>>(
    new Set(),
  );
  const reviewCount = studio.autonomyRuns.filter((run) =>
    ["ready_for_review", "needs_attention"].includes(run.status),
  ).length;

  React.useEffect(() => {
    setExpandedProjects(new Set());
    setEpisodesByProject({});
    setLoadingProjects(new Set());
    setCreatingEpisodeFor("");
    setOpeningEpisodeId("");
    setMutatingItem("");
    setDeleteTarget(null);
  }, [studio.selectedChannelId]);

  React.useEffect(() => {
    if (!studio.selectedProjectId) return;
    setExpandedProjects((current) =>
      new Set(current).add(studio.selectedProjectId),
    );
  }, [studio.selectedProjectId]);

  React.useEffect(() => {
    if (!studio.selectedProjectId) return;
    setEpisodesByProject((current) => ({
      ...current,
      [studio.selectedProjectId]: studio.episodes,
    }));
  }, [studio.episodes, studio.selectedProjectId]);

  React.useEffect(() => {
    if (!deleteTarget) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !mutatingItem) {
        setDeleteTarget(null);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [deleteTarget, mutatingItem]);

  const loadProjectEpisodes = React.useCallback(
    async (projectId: string) => {
      if (episodesByProject[projectId] || loadingProjects.has(projectId)) {
        return;
      }
      setLoadingProjects((current) => new Set(current).add(projectId));
      try {
        const episodes = await api.listEpisodes(projectId);
        setEpisodesByProject((current) => ({
          ...current,
          [projectId]: episodes,
        }));
      } catch (error) {
        studio.setError(error instanceof Error ? error.message : String(error));
      } finally {
        setLoadingProjects((current) => {
          const next = new Set(current);
          next.delete(projectId);
          return next;
        });
      }
    },
    [episodesByProject, loadingProjects, studio],
  );

  const createProject = async () => {
    try {
      setCreatingProject(true);
      studio.setError("");
      const project = await api.createProject(studio.selectedChannelId);
      await studio.refreshAll();
      setEpisodesByProject((current) => ({
        ...current,
        [project.project_id]: [],
      }));
      setExpandedProjects((current) =>
        new Set(current).add(project.project_id),
      );
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setCreatingProject(false);
    }
  };

  const createEpisode = async (projectId: string) => {
    try {
      setCreatingEpisodeFor(projectId);
      studio.setError("");
      const episode = await api.createEpisode(projectId);
      setEpisodesByProject((current) => ({
        ...current,
        [projectId]: [...(current[projectId] ?? []), episode],
      }));
      await studio.openEpisode(projectId, episode.episode_id);
      setPage("command");
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setCreatingEpisodeFor("");
    }
  };

  const toggleProject = (projectId: string) => {
    const willExpand = !expandedProjects.has(projectId);
    setExpandedProjects((current) => {
      const next = new Set(current);
      if (next.has(projectId)) {
        next.delete(projectId);
      } else {
        next.add(projectId);
      }
      return next;
    });
    if (willExpand) {
      void loadProjectEpisodes(projectId);
    }
  };

  const selectEpisode = async (projectId: string, episodeId: string) => {
    if (
      projectId === studio.selectedProjectId &&
      episodeId === studio.selectedEpisodeId
    ) {
      setPage("command");
      return;
    }
    try {
      setOpeningEpisodeId(episodeId);
      studio.setError("");
      await studio.openEpisode(projectId, episodeId);
      setPage("command");
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setOpeningEpisodeId("");
    }
  };

  const toggleProjectPin = async (projectId: string, pinned: boolean) => {
    try {
      setMutatingItem(`project:${projectId}`);
      studio.setError("");
      await api.updateProject(projectId, { pinned: !pinned });
      await studio.refreshAll();
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setMutatingItem("");
    }
  };

  const toggleEpisodePin = async (
    projectId: string,
    episode: Episode,
  ) => {
    try {
      setMutatingItem(`episode:${episode.episode_id}`);
      studio.setError("");
      const updated = await api.updateEpisode(episode.episode_id, {
        pinned: !episode.pinned,
      });
      setEpisodesByProject((current) => ({
        ...current,
        [projectId]: (current[projectId] ?? [])
          .map((item) =>
            item.episode_id === updated.episode_id ? updated : item,
          )
          .sort(
            (left, right) =>
              Number(right.pinned) - Number(left.pinned) ||
              right.updated_at.localeCompare(left.updated_at),
          ),
      }));
      if (projectId === studio.selectedProjectId) {
        await studio.refreshAll();
      }
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setMutatingItem("");
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    try {
      setMutatingItem(`${target.kind}:${target.id}`);
      studio.setError("");
      if (target.kind === "project") {
        await api.deleteProject(target.id);
        setExpandedProjects((current) => {
          const next = new Set(current);
          next.delete(target.id);
          return next;
        });
        setEpisodesByProject((current) => {
          const next = { ...current };
          delete next[target.id];
          return next;
        });
      } else {
        await api.deleteEpisode(target.id);
        setEpisodesByProject((current) => ({
          ...current,
          [target.projectId]: (current[target.projectId] ?? []).filter(
            (episode) => episode.episode_id !== target.id,
          ),
        }));
      }
      await studio.refreshAll();
      setDeleteTarget(null);
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setMutatingItem("");
    }
  };

  return (
    <aside className="left-rail">
      <div className="rail-studio-identity">
        <div className="rail-brand">
          <div className="rail-brand-wordmark">Synthea</div>
          <span className="rail-brand-mode">Studio</span>
        </div>
        <div className="rail-brand-sub">Production operating system</div>
      </div>
      <ChannelSwitcher onChange={() => setPage("command")} />

      <nav className="rail-primary-nav" aria-label="Production desks">
        <button
          type="button"
          className={`nav-btn ${page === "review" ? "active" : ""}`}
          aria-current={page === "review" ? "page" : undefined}
          onClick={() => setPage("review")}
        >
          <span className="nav-icon"><RailIcon name="review" /></span>
          <span className="nav-label">Review Queue</span>
          {reviewCount > 0 && <b className="rail-nav-count">{Math.min(reviewCount, 99)}</b>}
        </button>
      </nav>

      <section className="rail-library" aria-label="Projects and episodes">
        <div className="rail-section-heading">
          <span>Projects</span>
          <button
            type="button"
            className="rail-icon-button"
            aria-label="Create new project"
            title="New project"
            disabled={creatingProject}
            onClick={() => void createProject()}
          >
            {creatingProject ? <span className="rail-spinner" /> : <Plus size={17} aria-hidden="true" />}
          </button>
        </div>

        <div className="rail-project-list">
          {studio.projects.length === 0 && (
            <button
              type="button"
              className="rail-empty-project"
              disabled={creatingProject}
              onClick={() => void createProject()}
            >
              <Plus size={16} aria-hidden="true" />
              Create your first project
            </button>
          )}

          {studio.projects.map((project) => {
            const isSelected =
              project.project_id === studio.selectedProjectId;
            const isExpanded = expandedProjects.has(project.project_id);
            const isLoading = loadingProjects.has(project.project_id);
            const projectEpisodes =
              episodesByProject[project.project_id] ??
              (isSelected ? studio.episodes : []);

            return (
              <div
                key={project.project_id}
                className={`rail-project-group ${isSelected ? "selected" : ""}`}
              >
                <div className="rail-project-row-shell">
                  <button
                    type="button"
                    className="rail-project-row"
                    aria-expanded={isExpanded}
                    title={project.title}
                    onClick={() => toggleProject(project.project_id)}
                  >
                    <span className="rail-project-icon">
                      <RailIcon name="folder" />
                    </span>
                    <span className="rail-row-label">{project.title}</span>
                    <span className="rail-project-caret" aria-hidden="true">
                      {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                    </span>
                  </button>
                  <div className="rail-row-actions">
                    <button
                      type="button"
                      className={`rail-row-action ${project.pinned ? "pinned" : ""}`}
                      aria-label={`${project.pinned ? "Unpin" : "Pin"} project ${project.title}`}
                      aria-pressed={project.pinned}
                      title={project.pinned ? "Unpin project" : "Pin project"}
                      disabled={Boolean(mutatingItem)}
                      onClick={() =>
                        void toggleProjectPin(
                          project.project_id,
                          project.pinned,
                        )
                      }
                    >
                      {mutatingItem === `project:${project.project_id}` ? (
                        <span className="rail-spinner" />
                      ) : (
                        <RailIcon name="pin" />
                      )}
                    </button>
                    <button
                      type="button"
                      className="rail-row-action danger"
                      aria-label={`Delete project ${project.title}`}
                      title="Delete project"
                      disabled={Boolean(mutatingItem)}
                      onClick={() =>
                        setDeleteTarget({
                          kind: "project",
                          id: project.project_id,
                          title: project.title,
                        })
                      }
                    >
                      <RailIcon name="trash" />
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div className="rail-episode-list">
                    {projectEpisodes.map((episode) => {
                      const isActive =
                        isSelected &&
                        episode.episode_id === studio.selectedEpisodeId;
                      const isOpening =
                        episode.episode_id === openingEpisodeId;
                      return (
                        <div
                          key={episode.episode_id}
                          className="rail-episode-row-shell"
                        >
                          <button
                            type="button"
                            className={`rail-episode-row ${isActive ? "active" : ""}`}
                            aria-current={isActive ? "page" : undefined}
                            title={episode.title}
                            disabled={Boolean(openingEpisodeId)}
                            onClick={() =>
                              void selectEpisode(
                                project.project_id,
                                episode.episode_id,
                              )
                            }
                          >
                            <span className="rail-row-label">
                              {episode.title}
                            </span>
                            {isOpening && (
                              <span
                                className="rail-spinner rail-episode-spinner"
                                aria-label="Opening episode"
                              />
                            )}
                          </button>
                          <div className="rail-row-actions">
                            <button
                              type="button"
                              className={`rail-row-action ${episode.pinned ? "pinned" : ""}`}
                              aria-label={`${episode.pinned ? "Unpin" : "Pin"} episode ${episode.title}`}
                              aria-pressed={episode.pinned}
                              title={
                                episode.pinned
                                  ? "Unpin episode"
                                  : "Pin episode"
                              }
                              disabled={Boolean(mutatingItem)}
                              onClick={() =>
                                void toggleEpisodePin(
                                  project.project_id,
                                  episode,
                                )
                              }
                            >
                              {mutatingItem ===
                              `episode:${episode.episode_id}` ? (
                                <span className="rail-spinner" />
                              ) : (
                                <RailIcon name="pin" />
                              )}
                            </button>
                            <button
                              type="button"
                              className="rail-row-action danger"
                              aria-label={`Delete episode ${episode.title}`}
                              title="Delete episode"
                              disabled={Boolean(mutatingItem)}
                              onClick={() =>
                                setDeleteTarget({
                                  kind: "episode",
                                  id: episode.episode_id,
                                  projectId: project.project_id,
                                  title: episode.title,
                                })
                              }
                            >
                              <RailIcon name="trash" />
                            </button>
                          </div>
                        </div>
                      );
                    })}

                    {isLoading && (
                      <div className="rail-no-episodes rail-loading-episodes">
                        <span className="rail-spinner" />
                        Loading episodes…
                      </div>
                    )}

                    {!isLoading && projectEpisodes.length === 0 && (
                      <div className="rail-no-episodes">No episodes yet</div>
                    )}

                    <button
                      type="button"
                      className="rail-new-episode"
                      disabled={Boolean(creatingEpisodeFor)}
                      onClick={() => void createEpisode(project.project_id)}
                    >
                      {creatingEpisodeFor === project.project_id ? (
                        <>
                          <span className="rail-spinner" />
                          Creating episode…
                        </>
                      ) : (
                        <>
                          <Plus size={14} aria-hidden="true" />
                          New episode
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <div className="rail-footer">
        <ThemeToggle />
        <button
          type="button"
          className={`nav-btn rail-settings ${page === "settings" ? "active" : ""}`}
          aria-current={page === "settings" ? "page" : undefined}
          onClick={() => setPage("settings")}
        >
          <span className="nav-icon">
            <RailIcon name="settings" />
          </span>
          <span className="nav-label">Settings</span>
        </button>
      </div>

      {deleteTarget &&
        createPortal(
        <div
          className="rail-confirm-scrim"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !mutatingItem) {
              setDeleteTarget(null);
            }
          }}
        >
          <div
            className="rail-confirm-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="rail-delete-title"
            aria-describedby="rail-delete-description"
          >
            <div className="rail-confirm-icon">
              <RailIcon name="trash" />
            </div>
            <div>
              <div className="topbar-kicker">Permanent action</div>
              <h2 id="rail-delete-title">
                Delete {deleteTarget.kind}?
              </h2>
            </div>
            <p id="rail-delete-description">
              {deleteTarget.kind === "project"
                ? `“${deleteTarget.title}” and every episode inside it will be permanently removed, including their production files.`
                : `“${deleteTarget.title}” and its story, research, script, visuals, timeline, and production files will be permanently removed.`}
            </p>
            <p className="rail-confirm-note">
              Items with active jobs cannot be deleted.
            </p>
            <div className="rail-confirm-actions">
              <button
                type="button"
                autoFocus
                disabled={Boolean(mutatingItem)}
                onClick={() => setDeleteTarget(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-danger"
                disabled={Boolean(mutatingItem)}
                onClick={() => void confirmDelete()}
              >
                {mutatingItem ? (
                  <>
                    <span className="rail-spinner" />
                    Deleting…
                  </>
                ) : (
                  "Delete permanently"
                )}
              </button>
            </div>
          </div>
        </div>,
          document.body,
        )}
    </aside>
  );
};
