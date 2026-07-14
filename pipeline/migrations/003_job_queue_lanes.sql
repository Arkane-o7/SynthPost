ALTER TABLE render_jobs ADD COLUMN queue_lane TEXT NOT NULL DEFAULT 'editorial';
ALTER TABLE render_jobs ADD COLUMN available_at TEXT;
ALTER TABLE render_jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE render_jobs ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 2;

UPDATE render_jobs
SET queue_lane = CASE
  WHEN job_type IN ('visual_search', 'timeline_generate') THEN 'media'
  WHEN job_type IN ('render_avatar', 'render_story', 'assemble_episode') THEN 'render'
  ELSE 'editorial'
END;

UPDATE render_jobs
SET
  attempts = COALESCE(CAST(json_extract(data, '$.attempts') AS INTEGER), 0),
  max_attempts = COALESCE(CAST(json_extract(data, '$.max_attempts') AS INTEGER), 2),
  available_at = json_extract(data, '$.available_at');

CREATE INDEX IF NOT EXISTS idx_jobs_lane_available
  ON render_jobs(queue_lane, status, available_at, created_at);
