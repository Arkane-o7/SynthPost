import React from 'react';
import type { RenderJob } from '../contracts';
import { StatusBadge } from './StatusBadge';
import { shortId } from '../lib/formatters';

/**
 * Compact job card for the right rail and inline usage.
 */
export const InlineJobCard: React.FC<{
  job: RenderJob;
  onRetry?: () => void;
  onCancel?: () => void;
  onPause?: () => void;
  onResume?: () => void;
}> = ({ job, onRetry, onCancel, onPause, onResume }) => {
  const progressClass =
    job.status === 'completed'
      ? 'progress-complete'
      : job.status === 'failed'
        ? 'progress-failed'
        : '';

  return (
    <div className="job-card">
      <div className="job-header">
        <span className="job-type">{job.job_type}</span>
        <StatusBadge status={job.status}>{job.status}</StatusBadge>
      </div>
      {job.story_id && (
        <div className="job-meta font-mono">{shortId(job.story_id)}</div>
      )}
      <div className="progress-bar">
        <div
          className={`progress-bar-fill ${progressClass}`}
          style={{ width: `${job.progress}%` }}
        />
      </div>
      <div className="job-meta">
        {job.stage}
        {job.error ? ` · ${job.error}` : ''}
      </div>
      {(onRetry || onCancel || onPause || onResume) && (
        <div className="row-tight" style={{ marginTop: 8 }}>
          {onRetry && job.status === 'failed' && (
            <button className="btn-ghost" onClick={onRetry}>
              Retry
            </button>
          )}
          {onCancel && ['queued', 'running'].includes(job.status) && (
            <button className="btn-ghost" onClick={onCancel}>
              Cancel
            </button>
          )}
          {onPause && job.status === 'queued' && (
            <button className="btn-ghost" onClick={onPause}>
              Pause queue
            </button>
          )}
          {onResume && job.status === 'paused' && (
            <button className="btn-ghost" onClick={onResume}>
              Resume
            </button>
          )}
        </div>
      )}
    </div>
  );
};

/**
 * Even more compact job card for the right rail.
 */
export const MiniJobCard: React.FC<{ job: RenderJob }> = ({ job }) => {
  const progressClass =
    job.status === 'completed'
      ? 'progress-complete'
      : job.status === 'failed'
        ? 'progress-failed'
        : '';

  return (
    <div className="job-card job-card-compact">
      <div className="row-between">
        <span style={{ fontWeight: 600, fontSize: 12 }}>{job.job_type}</span>
        <StatusBadge status={job.status}>{job.status}</StatusBadge>
      </div>
      <div className="progress-bar" style={{ marginTop: 4, marginBottom: 2 }}>
        <div
          className={`progress-bar-fill ${progressClass}`}
          style={{ width: `${job.progress}%` }}
        />
      </div>
      <div className="text-muted" style={{ fontSize: 11 }}>
        {job.stage}
      </div>
    </div>
  );
};
