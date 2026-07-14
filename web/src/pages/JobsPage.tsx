import React from 'react';
import { api } from '../api/client';
import { useStudio } from '../state/useStudio';
import { InlineJobCard } from '../components/InlineJobCard';
import { EmptyState } from '../components/EmptyState';
import { relativeTime, shortId } from '../lib/formatters';

export const JobsPage: React.FC = () => {
  const studio = useStudio();
  const [typeFilter, setTypeFilter] = React.useState('');
  const [laneFilter, setLaneFilter] = React.useState('');
  const [statusFilter, setStatusFilter] = React.useState('');
  const [scope, setScope] = React.useState<'episode' | 'all'>(
    studio.selectedEpisodeId ? 'episode' : 'all',
  );
  const [openLogId, setOpenLogId] = React.useState('');
  const [logs, setLogs] = React.useState<Record<string, string>>({});

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
    if (
      scope === 'episode' &&
      studio.selectedEpisodeId &&
      j.episode_id !== studio.selectedEpisodeId
    ) return false;
    if (typeFilter && j.job_type !== typeFilter) return false;
    if (laneFilter && j.queue_lane !== laneFilter) return false;
    if (statusFilter && j.status !== statusFilter) return false;
    return true;
  });

  const scopedJobs = studio.jobs.filter(
    (job) =>
      scope === 'all' ||
      !studio.selectedEpisodeId ||
      job.episode_id === studio.selectedEpisodeId,
  );
  const jobTypes = [...new Set(scopedJobs.map((j) => j.job_type))];
  const activeCount = scopedJobs.filter((job) =>
    ['queued', 'paused', 'running'].includes(job.status),
  ).length;

  const toggleLogs = async (jobId: string) => {
    if (openLogId === jobId) {
      setOpenLogId('');
      return;
    }
    setOpenLogId(jobId);
    if (jobId in logs) return;
    try {
      const value = await api.jobLogs(jobId);
      setLogs((current) => ({ ...current, [jobId]: value || 'No log output yet.' }));
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <div>
      <div className="topbar mobile-page-hero jobs-page-hero">
        <div>
          <div className="topbar-kicker">Laptop production queue</div>
          <h1>Jobs</h1>
          <p>{activeCount} active · cancel, retry, and inspect remote work.</p>
        </div>
        <button onClick={() => void studio.refreshJobs()}>Refresh</button>
      </div>

      {/* Filters */}
      <div className="filter-toolbar" style={{ marginBottom: 16 }}>
        <select value={scope} onChange={(e) => setScope(e.target.value as 'episode' | 'all')}>
          <option value="episode" disabled={!studio.selectedEpisodeId}>Current episode</option>
          <option value="all">All projects</option>
        </select>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">All types</option>
          {jobTypes.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select value={laneFilter} onChange={(e) => setLaneFilter(e.target.value)}>
          <option value="">All queues</option>
          <option value="editorial">Editorial</option>
          <option value="media">Media</option>
          <option value="render">Render</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          <option value="queued">Queued</option>
          <option value="paused">Paused</option>
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
                onPause={() => act(() => api.pauseJob(job.job_id))}
                onResume={() => act(() => api.resumeJob(job.job_id))}
              />
              <div className="job-remote-actions">
                <button type="button" onClick={() => void toggleLogs(job.job_id)}>
                  {openLogId === job.job_id ? 'Hide logs' : 'View logs'}
                </button>
              </div>
              {openLogId === job.job_id && (
                <pre className="job-log-viewer">{logs[job.job_id] ?? 'Loading logs…'}</pre>
              )}
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
