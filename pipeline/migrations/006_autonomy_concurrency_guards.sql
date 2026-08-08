-- Enforce one editor-facing unattended result per episode and keep stopping
-- handlers serialized until their worker acknowledges cancellation.

CREATE UNIQUE INDEX IF NOT EXISTS idx_autonomy_runs_episode_unreviewed
  ON autonomy_runs(episode_id)
  WHERE status IN ('queued', 'running', 'needs_attention', 'ready_for_review');

DROP INDEX IF EXISTS idx_jobs_autonomy_active_stage;
CREATE UNIQUE INDEX idx_jobs_autonomy_active_stage
  ON render_jobs(autonomy_run_id, job_type)
  WHERE autonomy_run_id IS NOT NULL
    AND status IN ('queued', 'paused', 'running', 'cancel_requested');

CREATE TRIGGER IF NOT EXISTS prevent_active_job_update_for_terminal_autonomy_run
BEFORE UPDATE OF status, autonomy_run_id ON render_jobs
WHEN NEW.autonomy_run_id IS NOT NULL
  AND NEW.status IN ('queued', 'paused', 'running')
  AND OLD.status NOT IN ('queued', 'paused', 'running', 'cancel_requested')
  AND EXISTS (
    SELECT 1
    FROM autonomy_runs
    WHERE run_id = NEW.autonomy_run_id
      AND status IN ('accepted', 'rejected', 'cancelled')
  )
BEGIN
  SELECT RAISE(ABORT, 'autonomy run is terminal');
END;
