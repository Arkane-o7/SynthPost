-- SynthPost V2 initial local-first newsroom schema.
-- SQLite stores canonical JSON payloads while indexing workflow-critical fields.

CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episodes (
  episode_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  render_profile TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_episodes_project ON episodes(project_id);

CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  category TEXT NOT NULL,
  enabled INTEGER NOT NULL,
  priority INTEGER NOT NULL,
  reliability_score REAL NOT NULL,
  data TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sources_enabled ON sources(enabled, category);

CREATE TABLE IF NOT EXISTS story_candidates (
  candidate_id TEXT PRIMARY KEY,
  episode_id TEXT,
  story_id TEXT,
  title TEXT NOT NULL,
  canonical_url TEXT,
  source_id TEXT,
  source_name TEXT NOT NULL,
  category TEXT NOT NULL,
  published_at TEXT,
  final_score REAL NOT NULL,
  selection_status TEXT NOT NULL,
  workflow_state TEXT NOT NULL,
  duplicate_group_id TEXT,
  data TEXT NOT NULL,
  discovered_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidates_episode ON story_candidates(episode_id, selection_status);
CREATE INDEX IF NOT EXISTS idx_candidates_score ON story_candidates(final_score DESC);
CREATE INDEX IF NOT EXISTS idx_candidates_url ON story_candidates(canonical_url);

CREATE TABLE IF NOT EXISTS source_documents (
  document_id TEXT PRIMARY KEY,
  story_id TEXT NOT NULL,
  url TEXT,
  title TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  extraction_status TEXT NOT NULL,
  data TEXT NOT NULL,
  retrieved_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_story ON source_documents(story_id);

CREATE TABLE IF NOT EXISTS research_packs (
  research_pack_id TEXT PRIMARY KEY,
  story_id TEXT NOT NULL,
  status TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_story ON research_packs(story_id, created_at DESC);

CREATE TABLE IF NOT EXISTS script_revisions (
  script_id TEXT PRIMARY KEY,
  story_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(story_id, version)
);

CREATE INDEX IF NOT EXISTS idx_scripts_story ON script_revisions(story_id, version DESC);

CREATE TABLE IF NOT EXISTS visual_candidates (
  asset_id TEXT PRIMARY KEY,
  story_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  media_type TEXT NOT NULL,
  rights_tier TEXT NOT NULL,
  review_status TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_visuals_story ON visual_candidates(story_id, review_status);

CREATE TABLE IF NOT EXISTS timeline_revisions (
  timeline_id TEXT PRIMARY KEY,
  story_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(story_id, version)
);

CREATE INDEX IF NOT EXISTS idx_timelines_story ON timeline_revisions(story_id, version DESC);

CREATE TABLE IF NOT EXISTS render_jobs (
  job_id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  episode_id TEXT,
  story_id TEXT,
  status TEXT NOT NULL,
  progress REAL NOT NULL,
  stage TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON render_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_story ON render_jobs(story_id, created_at DESC);

CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id TEXT PRIMARY KEY,
  artifact_type TEXT NOT NULL,
  story_id TEXT,
  episode_id TEXT,
  path TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_story ON artifacts(story_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_episode ON artifacts(episode_id, artifact_type);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
