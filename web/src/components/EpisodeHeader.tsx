import React from 'react';
import type { StoryCandidate } from '../contracts';
import { useStudio } from '../state/useStudio';
import { StatusBadge } from './StatusBadge';

export const EpisodeHeader: React.FC<{
  story?: StoryCandidate | null;
}> = ({ story }) => {
  const studio = useStudio();
  const project = studio.projects.find(
    (p) => p.project_id === studio.selectedProjectId,
  );
  const episode = studio.episodes.find(
    (e) => e.episode_id === studio.selectedEpisodeId,
  );

  return (
    <div className="episode-header">
      <div className="episode-breadcrumb">
        <span>{project?.title ?? 'No project'}</span>
        <span className="sep">›</span>
        <span>{episode?.title ?? 'No episode'}</span>
        {story && (
          <>
            <span className="sep">›</span>
            <span style={{ color: 'var(--text)' }}>Story</span>
          </>
        )}
      </div>
      {story ? (
        <>
          <div className="episode-story-title">{story.title}</div>
          <div className="episode-meta">
            <StatusBadge status={story.workflow_state ?? 'selected'}>
              {story.workflow_state ?? 'selected'}
            </StatusBadge>
            <span className="text-muted" style={{ fontSize: 13 }}>
              {story.source_name} · {story.category}
            </span>
            {episode?.render_profile && (
              <StatusBadge tone="blue">{episode.render_profile}</StatusBadge>
            )}
          </div>
        </>
      ) : (
        <div className="text-muted" style={{ marginTop: 8 }}>
          No story selected for this episode.
        </div>
      )}
    </div>
  );
};
