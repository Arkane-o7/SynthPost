import React from 'react';
import { api } from '../api/client';
import { useStudio } from '../state/useStudio';
import { InlineJobCard } from '../components/InlineJobCard';
import { EmptyState } from '../components/EmptyState';
import { relativeTime, shortId } from '../lib/formatters';

export const JobsPage: React.FC = () => {
  const studio = useStudio();
  const [typeFilter, setTypeFilter] = React.useState('');
  const [statusFilter, setStatusFilter] = React.useState('');

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError('');
      await fn();
      await studio.refreshAll();
    } catch (err) {
      studio.setError(err instanceof Error ? err.message : String(err));
    }
  };

  const jobs = studio.jobs.filter((j) => {
    if (typeFilter && j.job_type !== typeFilter) return false;
    if (statusFilter && j.status !== statusFilter) return false;
    return true;
  });

  const jobTypes = [...new Set(studio.jobs.map((j) => j.job_type))];

  return (
    <div>
      <div className="topbar">
        <div>
          <div className="topbar-kicker">SynthPost Studio</div>
          <h1>Jobs</h1>
        </div>
        <button onClick={() => void studio.refreshJobs()}>Refresh</button>
      </div>

      {/* Filters */}
      <div className="filter-toolbar" style={{ marginBottom: 16 }}>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">All types</option>
          {jobTypes.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          <option value="queued">Queued</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <span className="text-muted" style={{ fontSize: 13 }}>
          {jobs.length} job{jobs.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Job list */}
      {jobs.length === 0 ? (
        <EmptyState
          icon="⚡"
          title="No jobs found"
          description="Jobs are created when you run research, generate scripts, render stories, or assemble episodes."
        />
      ) : (
        <div className="stack">
          {jobs.map((job) => (
            <div key={job.job_id} className="card" style={{ padding: 'var(--sp-4)' }}>
              <InlineJobCard
                job={job}
                onRetry={() => act(() => api.retryJob(job.job_id))}
                onCancel={() => act(() => api.cancelJob(job.job_id))}
              />
              <div
                className="row-between text-muted"
                style={{ fontSize: 11, marginTop: 8 }}
              >
                <span className="font-mono">{shortId(job.job_id)}</span>
                <span>
                  {job.started_at && `Started ${relativeTime(job.started_at)}`}
                  {job.completed_at &&
                    ` · Finished ${relativeTime(job.completed_at)}`}
                </span>
              </div>
              {job.error && (
                <div className="error-banner" style={{ marginTop: 8 }}>
                  {job.error}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
