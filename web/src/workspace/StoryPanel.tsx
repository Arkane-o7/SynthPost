import React from 'react';
import { useStudio } from '../state/useStudio';
import { StatusBadge } from '../components/StatusBadge';
import { scorePercent, relativeTime } from '../lib/formatters';

export const StoryPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const story = studio.candidates.find((c) => c.story_id === storyId);

  if (!story) {
    return <div className="text-muted">Story not found.</div>;
  }

  const pct = scorePercent(story.final_score);

  return (
    <div className="card stack-lg animate-fade-in">
      <h2>Story Source</h2>
      <div className="row-between">
        <div>
          <h2 style={{ fontSize: 22 }}>{story.title}</h2>
          <div className="text-muted" style={{ marginTop: 4 }}>
            {story.source_name} · {story.category} ·{' '}
            {relativeTime(story.published_at)}
          </div>
        </div>
        <div
          className={`score-circle ${
            pct >= 80 ? 'score-high' : pct >= 60 ? 'score-mid' : 'score-low'
          }`}
        >
          {pct}
        </div>
      </div>

      <p style={{ lineHeight: 1.6 }}>
        {story.summary || story.manual_body || 'No summary available.'}
      </p>

      {story.canonical_url && (
        <div
          className="font-mono"
          style={{
            padding: '10px 14px',
            background: 'var(--surface-inset)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 12,
            wordBreak: 'break-all',
          }}
        >
          {story.canonical_url}
        </div>
      )}

      <div className="row-tight">
        <StatusBadge status={story.selection_status}>
          {story.selection_status}
        </StatusBadge>
        <StatusBadge status={story.workflow_state ?? ''}>
          {story.workflow_state ?? 'unknown'}
        </StatusBadge>
      </div>

      {story.score_reasons.length > 0 && (
        <div>
          <h3>Score Reasons</h3>
          <div className="row-tight" style={{ marginTop: 8 }}>
            {story.score_reasons.map((r) => (
              <StatusBadge key={r} tone="blue">
                {r}
              </StatusBadge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
