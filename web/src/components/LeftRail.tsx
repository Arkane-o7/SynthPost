import React from 'react';
import { useStudio } from '../state/useStudio';

export type Page = 'command' | 'sources' | 'inbox' | 'jobs' | 'settings';

const NAV_ITEMS: { key: Page; label: string; icon: string }[] = [
  { key: 'command', label: 'Command Center', icon: '◉' },
  { key: 'sources', label: 'Sources', icon: '📡' },
  { key: 'inbox', label: 'Story Inbox', icon: '📨' },
  { key: 'jobs', label: 'Jobs', icon: '⚡' },
  { key: 'settings', label: 'Settings', icon: '⚙' },
];

export const LeftRail: React.FC<{
  page: Page;
  setPage: (page: Page) => void;
}> = ({ page, setPage }) => {
  const studio = useStudio();

  const activeJobCount = studio.jobs.filter((j) =>
    ['queued', 'running'].includes(j.status),
  ).length;

  const suggestedCount = studio.candidates.filter(
    (c) => c.selection_status === 'suggested',
  ).length;

  return (
    <aside className="left-rail">
      {/* Logo */}
      <div className="logo-mark">
        Synth<span>Post</span>
        <br />
        Studio
      </div>
      <div className="logo-sub">local newsroom editor</div>

      {/* Navigation */}
      <nav className="nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.key}
            className={`nav-btn ${page === item.key ? 'active' : ''}`}
            onClick={() => setPage(item.key)}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
            {item.key === 'jobs' && activeJobCount > 0 && (
              <span className="nav-badge">{activeJobCount}</span>
            )}
            {item.key === 'inbox' && suggestedCount > 0 && (
              <span className="nav-badge">{suggestedCount}</span>
            )}
          </button>
        ))}
      </nav>

      {/* Context switchers */}
      <div className="context-switchers">
        <label className="context-label">
          Project
          <select
            value={studio.selectedProjectId}
            onChange={(e) => studio.setSelectedProjectId(e.target.value)}
          >
            <option value="">No project</option>
            {studio.projects.map((p) => (
              <option key={p.project_id} value={p.project_id}>
                {p.title}
              </option>
            ))}
          </select>
        </label>
        <label className="context-label">
          Episode
          <select
            value={studio.selectedEpisodeId}
            onChange={(e) => studio.setSelectedEpisodeId(e.target.value)}
          >
            <option value="">No episode</option>
            {studio.episodes.map((ep) => (
              <option key={ep.episode_id} value={ep.episode_id}>
                {ep.title}
              </option>
            ))}
          </select>
        </label>
      </div>
    </aside>
  );
};
