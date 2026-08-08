-- Durable unattended-production runs and explicit job correlation.

CREATE TABLE IF NOT EXISTS autonomy_runs (
  run_id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  episode_id TEXT NOT NULL,
  story_id TEXT,
  status TEXT NOT NULL,
  current_stage TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(project_id),
  FOREIGN KEY(episode_id) REFERENCES episodes(episode_id)
);

CREATE INDEX IF NOT EXISTS idx_autonomy_runs_channel_status
  ON autonomy_runs(channel_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_autonomy_runs_episode
  ON autonomy_runs(episode_id, created_at DESC);

ALTER TABLE render_jobs ADD COLUMN autonomy_run_id TEXT;
CREATE INDEX IF NOT EXISTS idx_jobs_autonomy_run
  ON render_jobs(autonomy_run_id, job_type, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_autonomy_active_stage
  ON render_jobs(autonomy_run_id, job_type)
  WHERE autonomy_run_id IS NOT NULL
    AND status IN ('queued', 'paused', 'running');
