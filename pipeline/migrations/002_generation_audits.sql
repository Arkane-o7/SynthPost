CREATE TABLE IF NOT EXISTS generation_audits (
  audit_id TEXT PRIMARY KEY,
  story_id TEXT NOT NULL,
  job_id TEXT,
  stage TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  charter_version TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT,
  status TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_generation_audits_story
  ON generation_audits(story_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_generation_audits_stage
  ON generation_audits(stage, created_at DESC);
