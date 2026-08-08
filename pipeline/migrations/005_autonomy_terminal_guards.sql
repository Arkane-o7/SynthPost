-- A stopped or reviewed run is a hard boundary. Stale reconcilers may still
-- hold an old in-memory copy, so reject any new active job at SQLite itself.

CREATE TRIGGER IF NOT EXISTS prevent_active_job_for_terminal_autonomy_run
BEFORE INSERT ON render_jobs
WHEN NEW.autonomy_run_id IS NOT NULL
  AND NEW.status IN ('queued', 'paused', 'running')
  AND EXISTS (
    SELECT 1
    FROM autonomy_runs
    WHERE run_id = NEW.autonomy_run_id
      AND status IN ('accepted', 'rejected', 'cancelled')
  )
BEGIN
  SELECT RAISE(ABORT, 'autonomy run is terminal');
END;
