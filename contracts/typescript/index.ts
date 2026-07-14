// SynthPost V2 TypeScript contracts. Keep field names snake_case to match persisted JSON.

export type Project = {
  project_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  default_category: string;
  default_render_profile: string;
  status: 'active' | 'archived';
};

export type Episode = {
  episode_id: string;
  project_id: string;
  title: string;
  story_ids: string[];
  status: string;
  render_profile: string;
  final_output_path: string | null;
  created_at: string;
  updated_at: string;
};

export type SourceDefinition = {
  source_id: string;
  name: string;
  source_type: 'rss' | 'atom' | 'website' | 'api' | 'custom_url' | 'manual_story';
  category: string;
  homepage_url: string | null;
  feed_url: string | null;
  country: string | null;
  enabled: boolean;
  priority: number;
  reliability_score: number;
  custom: boolean;
  last_checked_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
  last_item_count: number;
};

export type StoryScores = Record<'importance' | 'freshness' | 'public_interest' | 'visual_potential' | 'explainability' | 'source_reliability' | 'format_suitability' | 'originality', number>;

export type EditorialFitAssessment = {
  charter_version: string;
  score: number;
  eligible: boolean;
  primary_topic: string;
  matched_criteria: string[];
  strengths: string[];
  penalties: string[];
  rejection_signals: string[];
  india_relevance: number;
  india_impact: string;
  india_impact_confidence: number;
  reasons: string[];
};

export type StoryCandidate = {
  candidate_id: string;
  title: string;
  canonical_url: string | null;
  source_id: string | null;
  source_name: string;
  published_at: string | null;
  author: string | null;
  category: string;
  summary: string;
  thumbnail_url: string | null;
  language: string;
  discovered_at: string;
  scores: StoryScores;
  editorial_fit: EditorialFitAssessment;
  final_score: number;
  score_reasons: string[];
  selection_status: 'suggested' | 'selected' | 'rejected' | 'duplicate' | 'expired';
  rejection_reasons: string[];
  duplicate_group_id: string | null;
  event_cluster_id: string | null;
  cluster_size: number;
  supporting_sources: string[];
  related_candidate_ids: string[];
  evidence_score: number;
  assignment_lane: 'recommended' | 'global_watch' | 'india_watch' | 'rejected' | 'duplicate' | 'expired' | 'unassessed';
  assignment_summary: string;
  recommended_format: 'signal' | 'explained' | 'deep_dive' | 'india_builds';
  assignment_confidence: number;
  episode_id?: string | null;
  story_id?: string | null;
  workflow_state?: string;
  manual_body?: string | null;
};

export type SourceDocument = {
  document_id: string;
  story_id: string;
  url: string | null;
  title: string;
  publisher: string | null;
  author: string | null;
  published_at: string | null;
  retrieved_at: string;
  content_text: string;
  content_hash: string;
  document_type: string;
  primary_source: boolean;
  discovery_method?: string | null;
  research_query?: string | null;
  relevance_score?: number | null;
  extraction_status: string;
  warnings: string[];
};

export type Claim = {
  claim_id: string;
  claim_text: string;
  evidence_ids: string[];
  confidence: number;
  claim_type: string;
  supported: boolean;
  notes: string;
};

export type EvidenceItem = {
  evidence_id: string;
  document_id: string;
  excerpt: string;
  location: string | null;
  url: string | null;
};

export type ResearchPack = {
  research_pack_id: string;
  story_id: string;
  documents: SourceDocument[];
  research_queries: string[];
  evidence: EvidenceItem[];
  claims: Claim[];
  timeline_events: Record<string, unknown>[];
  people: string[];
  organizations: string[];
  locations: string[];
  numbers: string[];
  dates: string[];
  contradictions: string[];
  uncertainties: string[];
  systems: string[];
  stakeholders: string[];
  trade_offs: string[];
  execution_gaps: string[];
  editorial_questions: string[];
  charter_version: string;
  research_summary: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
};

export type SourceClipCue = {
  duration_seconds: number;
  search_query: string;
  description: string;
  fallback_narration: string;
  speaker: string;
  quote: string;
};

export type ScriptSection = {
  section_id: string;
  section_type: 'cold_open' | 'intro' | 'context' | 'key_developments' | 'why_it_matters' | 'stakes' | 'uncertainty' | 'conclusion' | 'outro';
  text: string;
  estimated_duration_seconds: number;
  claim_ids: string[];
  suggested_visual_types: string[];
  suggested_search_queries: string[];
  suggested_template_ids: string[];
  lower_third: string;
  chyron: string;
  headline_cues: string[];
  source_clip: SourceClipCue | null;
  editorial_notes: string[];
  approval_status: string;
  locked?: boolean;
};

export type NarrationMode = 'signal' | 'explained' | 'deep_dive' | 'india_builds';

export type ScriptDocument = {
  script_id: string;
  story_id: string;
  headline: string;
  dek: string;
  category: string;
  narration_mode: NarrationMode;
  estimated_duration_seconds: number;
  version: number;
  status: string;
  sections: ScriptSection[];
  lower_thirds: string[];
  chyrons: string[];
  source_ids: string[];
  warnings?: string[];
  created_at: string;
  updated_at: string;
};

export type VisualCandidate = {
  asset_id: string;
  story_id: string;
  section_ids: string[];
  provider: string;
  source_url: string | null;
  source_domain: string | null;
  download_path: string | null;
  quarantine_path: string | null;
  thumbnail_path: string | null;
  media_type: 'image' | 'video' | 'document' | 'chart' | 'map' | 'audio' | 'fallback';
  mime_type: string | null;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  has_audio: boolean | null;
  title: string;
  description: string;
  creator: string | null;
  published_at: string | null;
  relevance_score: number;
  visual_quality_score: number;
  source_authority: number;
  content_role: string;
  rights_tier: 'green' | 'yellow' | 'red';
  rights_confidence: number;
  usage_basis: string;
  license: string | null;
  attribution_required: boolean;
  attribution_text: string | null;
  manual_review_flag: boolean;
  review_status: 'suggested' | 'approved' | 'manual_approved' | 'rejected' | 'blocked';
  warnings: string[];
  source_class: string;
  source_identity: string | null;
  source_channel_id: string | null;
  source_channel_name: string | null;
  source_verified: boolean;
  source_metadata: Record<string, unknown>;
  content_cleanliness_status: 'not_scanned' | 'needs_review' | 'passed' | 'rejected';
  contains_third_party_logo: boolean;
  detected_brands: string[];
  contains_lower_third: boolean;
  contains_ticker: boolean;
  contains_presenter: boolean;
  ocr_findings: Array<Record<string, unknown>>;
  scan_timestamps: number[];
  analysis_frame_paths: string[];
  contact_sheet_path: string | null;
  clean_broll_score: number;
  content_analysis_version: string | null;
  content_analysis_provider: string | null;
  content_analysis_evidence: string[];
  approval_blockers: string[];
  trim_start: number | null;
  trim_end: number | null;
  motion: Record<string, unknown>;
  created_at: string;
};

export type TimelineSegment = {
  segment_id: string;
  section_id: string;
  start_time: number;
  end_time: number;
  duration: number;
  script_text: string;
  claim_ids: string[];
  anchor: { visible: boolean; speaking: boolean; camera?: string };
  visual: {
    asset_id?: string | null;
    path?: string | null;
    media_type: string;
    content_role: string;
    source?: string | null;
    source_url?: string | null;
    rights_tier: 'green' | 'yellow' | 'red';
    review_status: 'suggested' | 'approved' | 'manual_approved' | 'rejected' | 'blocked';
    audio_mode: 'muted' | 'original' | 'mixed';
    trim_start?: number | null;
    trim_end?: number | null;
    has_audio?: boolean | null;
    attribution_text?: string | null;
  };
  template: { template_id: string; layout?: string | null };
  audio: { mode: 'narration' | 'source' | 'mixed' | 'silent'; narration_volume: number; source_volume: number; ducking: boolean };
  overlays: { lower_third: string; chyron: string; attribution: string; quote_text: string; document_source: string; data?: Record<string, unknown> };
  status: string;
};

export type TimelinePlan = {
  timeline_id: string;
  story_id: string;
  version: number;
  status: 'draft' | 'review' | 'approved' | 'rejected';
  segments: TimelineSegment[];
  audio_plan?: Record<string, unknown> | null;
  validation_warnings?: string[];
  validation_errors?: string[];
  created_at: string;
  updated_at: string;
};

export type RenderJob = {
  job_id: string;
  episode_id: string | null;
  story_id: string | null;
  job_type: string;
  queue_lane: 'editorial' | 'media' | 'render';
  render_profile: string;
  status: 'queued' | 'paused' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  stage: string;
  started_at: string | null;
  completed_at: string | null;
  output_paths: Record<string, string>;
  log_path: string | null;
  error: string | null;
  traceback?: string | null;
  payload?: Record<string, unknown>;
  attempts: number;
  max_attempts: number;
  available_at: string | null;
  last_attempt_at: string | null;
  last_error: string | null;
  failure_kind: string | null;
  created_at?: string;
  updated_at?: string;
};

export type GenerationAudit = {
  audit_id: string;
  story_id: string;
  job_id: string | null;
  stage: string;
  prompt_version: string;
  charter_version: string;
  provider: string;
  model: string | null;
  prompt_text: string;
  response: Record<string, unknown> | null;
  attempts: Array<Record<string, unknown>>;
  validation_events: Array<Record<string, unknown>>;
  normalization_events: Array<Record<string, unknown>>;
  status: string;
  created_at: string;
};

export type ArtifactRecord = {
  artifact_id: string;
  artifact_type: string;
  path: string;
  content_hash: string | null;
  created_at: string;
  producer: string;
  inputs: string[];
  render_profile: string | null;
  test_mode: boolean;
  metadata: Record<string, unknown>;
};

export const isProject = (value: unknown): value is Project => typeof value === 'object' && value !== null && typeof (value as Project).project_id === 'string';
export const isEpisode = (value: unknown): value is Episode => typeof value === 'object' && value !== null && typeof (value as Episode).episode_id === 'string';
export const isStoryCandidate = (value: unknown): value is StoryCandidate => typeof value === 'object' && value !== null && typeof (value as StoryCandidate).candidate_id === 'string';
export const isTimelinePlan = (value: unknown): value is TimelinePlan => typeof value === 'object' && value !== null && Array.isArray((value as TimelinePlan).segments);
