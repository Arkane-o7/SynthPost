import React from "react";
import { useStudio } from "../state/useStudio";
import type { Page } from "./LeftRail";

const MOBILE_NAV: { key: Page; label: string; icon: string }[] = [
  { key: "command", label: "Studio", icon: "◉" },
  { key: "episodes", label: "Episodes", icon: "▤" },
  { key: "inbox", label: "Stories", icon: "◇" },
  { key: "jobs", label: "Jobs", icon: "↯" },
  { key: "sources", label: "Sources", icon: "⌁" },
];

export const MobileChrome: React.FC<{
  page: Page;
  setPage: (page: Page) => void;
  onOpenAttention: () => void;
}> = ({ page, setPage, onOpenAttention }) => {
  const studio = useStudio();
  const episode = studio.episodes.find(
    (item) => item.episode_id === studio.selectedEpisodeId,
  );
  const contextJobs = studio.selectedEpisodeId
    ? studio.jobs.filter((job) => job.episode_id === studio.selectedEpisodeId)
    : studio.jobs;
  const activeJobs = contextJobs.filter((job) =>
    ["queued", "paused", "running"].includes(job.status),
  ).length;
  const failedJobs = contextJobs.filter((job) => job.status === "failed").length;
  const attentionCount = activeJobs + failedJobs;

  return (
    <>
      <header className="mobile-command-header">
        <div className="mobile-command-brand">
          <div className="mobile-logo" aria-label="SynthPost Studio">
            S<span>P</span>
          </div>
          <div className="mobile-machine-state">
            <span className="machine-live-dot" aria-hidden="true" />
            <div>
              <strong>{episode?.title ?? "SynthPost remote"}</strong>
              <span>Laptop online · command link active</span>
            </div>
          </div>
          <button
            type="button"
            className="mobile-icon-button"
            aria-label={`Open attention center${attentionCount ? `, ${attentionCount} items` : ""}`}
            onClick={onOpenAttention}
          >
            <span aria-hidden="true">⌁</span>
            {attentionCount > 0 && <b>{Math.min(attentionCount, 99)}</b>}
          </button>
          <button
            type="button"
            className="mobile-icon-button"
            aria-label="Open settings"
            onClick={() => setPage("settings")}
          >
            <span aria-hidden="true">⚙</span>
          </button>
        </div>

        <div className="mobile-context-switcher">
          <label>
            <span>Project</span>
            <select
              aria-label="Current project"
              value={studio.selectedProjectId}
              onChange={(event) => studio.setSelectedProjectId(event.target.value)}
            >
              <option value="">No project</option>
              {studio.projects.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  {project.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Episode</span>
            <select
              aria-label="Current episode"
              value={studio.selectedEpisodeId}
              onChange={(event) => studio.setSelectedEpisodeId(event.target.value)}
            >
              <option value="">No episode</option>
              {studio.episodes.map((item) => (
                <option key={item.episode_id} value={item.episode_id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      <nav className="mobile-bottom-nav" aria-label="Mobile production navigation">
        {MOBILE_NAV.map((item) => (
          <button
            type="button"
            key={item.key}
            className={page === item.key ? "active" : ""}
            onClick={() => setPage(item.key)}
          >
            <span aria-hidden="true">{item.icon}</span>
            {item.label}
            {item.key === "jobs" && activeJobs > 0 && <b>{activeJobs}</b>}
          </button>
        ))}
      </nav>
    </>
  );
};
