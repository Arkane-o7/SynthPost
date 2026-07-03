from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProjectStatus(str, Enum):
    active = "active"
    archived = "archived"


class EpisodeStatus(str, Enum):
    draft = "draft"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    archived = "archived"


class SourceType(str, Enum):
    rss = "rss"
    atom = "atom"
    website = "website"
    api = "api"
    custom_url = "custom_url"
    manual_story = "manual_story"


class StorySelectionStatus(str, Enum):
    suggested = "suggested"
    selected = "selected"
    rejected = "rejected"
    duplicate = "duplicate"


class StoryWorkflowState(str, Enum):
    draft = "draft"
    discovered = "discovered"
    selected = "selected"
    researching = "researching"
    research_ready = "research_ready"
    script_generating = "script_generating"
    script_review = "script_review"
    script_approved = "script_approved"
    visuals_searching = "visuals_searching"
    visuals_review = "visuals_review"
    timeline_draft = "timeline_draft"
    timeline_review = "timeline_review"
    timeline_approved = "timeline_approved"
    rendering_avatar = "rendering_avatar"
    rendering_composition = "rendering_composition"
    assembling = "assembling"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ScriptStatus(str, Enum):
    draft = "draft"
    review = "review"
    approved = "approved"
    rejected = "rejected"


class ApprovalStatus(str, Enum):
    draft = "draft"
    review = "review"
    approved = "approved"
    rejected = "rejected"
    locked = "locked"


class RightsTier(str, Enum):
    green = "green"
    yellow = "yellow"
    red = "red"


class ReviewStatus(str, Enum):
    suggested = "suggested"
    approved = "approved"
    manual_approved = "manual_approved"
    rejected = "rejected"
    blocked = "blocked"


class MediaType(str, Enum):
    image = "image"
    video = "video"
    document = "document"
    chart = "chart"
    map = "map"
    audio = "audio"
    fallback = "fallback"


class ContentRole(str, Enum):
    evidence = "evidence"
    primary_footage = "primary_footage"
    context = "context"
    explanation = "explanation"
    location = "location"
    person = "person"
    document = "document"
    data = "data"
    atmosphere = "atmosphere"
    fallback = "fallback"


class TimelineStatus(str, Enum):
    draft = "draft"
    review = "review"
    approved = "approved"
    rejected = "rejected"


class AudioMode(str, Enum):
    narration = "narration"
    source = "source"
    mixed = "mixed"
    silent = "silent"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class Project(StrictModel):
    project_id: str = Field(default_factory=lambda: new_id("proj"))
    title: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    default_category: str = "general"
    default_render_profile: str = "preview"
    status: ProjectStatus = ProjectStatus.active


class Episode(StrictModel):
    episode_id: str = Field(default_factory=lambda: new_id("ep"))
    project_id: str
    title: str
    story_ids: list[str] = Field(default_factory=list)
    status: EpisodeStatus = EpisodeStatus.draft
    render_profile: str = "preview"
    final_output_path: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class SourceDefinition(StrictModel):
    source_id: str = Field(default_factory=lambda: new_id("src"))
    name: str
    source_type: SourceType
    category: str = "general"
    homepage_url: str | None = None
    feed_url: str | None = None
    country: str | None = None
    enabled: bool = True
    priority: int = 50
    reliability_score: float = 0.7
    custom: bool = False
    last_checked_at: str | None = None

    @model_validator(mode="after")
    def require_source_locator(self) -> "SourceDefinition":
        if self.source_type in {SourceType.rss, SourceType.atom} and not self.feed_url:
            raise ValueError("RSS/Atom sources require feed_url")
        if self.source_type == SourceType.website and not self.homepage_url:
            raise ValueError("Website sources require homepage_url")
        return self


class StoryScores(StrictModel):
    importance: float = 0.0
    freshness: float = 0.0
    public_interest: float = 0.0
    visual_potential: float = 0.0
    explainability: float = 0.0
    source_reliability: float = 0.0
    format_suitability: float = 0.0
    originality: float = 0.0


class StoryCandidate(StrictModel):
    candidate_id: str = Field(default_factory=lambda: new_id("cand"))
    title: str
    canonical_url: str | None = None
    source_id: str | None = None
    source_name: str
    published_at: str | None = None
    author: str | None = None
    category: str = "general"
    summary: str = ""
    thumbnail_url: str | None = None
    language: str = "unknown"
    discovered_at: str = Field(default_factory=now_iso)
    scores: StoryScores = Field(default_factory=StoryScores)
    final_score: float = 0.0
    score_reasons: list[str] = Field(default_factory=list)
    selection_status: StorySelectionStatus = StorySelectionStatus.suggested
    rejection_reasons: list[str] = Field(default_factory=list)
    duplicate_group_id: str | None = None
    episode_id: str | None = None
    story_id: str | None = None
    workflow_state: StoryWorkflowState = StoryWorkflowState.discovered
    manual_body: str | None = None


class SourceDocument(StrictModel):
    document_id: str = Field(default_factory=lambda: new_id("doc"))
    story_id: str
    url: str | None = None
    title: str
    publisher: str | None = None
    author: str | None = None
    published_at: str | None = None
    retrieved_at: str = Field(default_factory=now_iso)
    content_text: str
    content_hash: str
    document_type: str = "article"
    primary_source: bool = False
    extraction_status: str = "extracted"
    warnings: list[str] = Field(default_factory=list)


class EvidenceItem(StrictModel):
    evidence_id: str = Field(default_factory=lambda: new_id("ev"))
    document_id: str
    excerpt: str
    location: str | None = None
    url: str | None = None


class Claim(StrictModel):
    claim_id: str = Field(default_factory=lambda: new_id("claim"))
    claim_text: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    claim_type: str = "fact"
    supported: bool = False
    notes: str = ""


class ResearchPack(StrictModel):
    research_pack_id: str = Field(default_factory=lambda: new_id("research"))
    story_id: str
    documents: list[SourceDocument] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    timeline_events: list[dict[str, Any]] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    numbers: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    research_summary: str = ""
    status: ApprovalStatus = ApprovalStatus.review
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


SectionType = Literal[
    "cold_open",
    "intro",
    "context",
    "key_developments",
    "why_it_matters",
    "stakes",
    "uncertainty",
    "conclusion",
    "outro",
]


class ScriptSection(StrictModel):
    section_id: str
    section_type: SectionType
    text: str
    estimated_duration_seconds: float = 0.0
    claim_ids: list[str] = Field(default_factory=list)
    suggested_visual_types: list[str] = Field(default_factory=list)
    suggested_search_queries: list[str] = Field(default_factory=list)
    suggested_template_ids: list[str] = Field(default_factory=list)
    editorial_notes: list[str] = Field(default_factory=list)
    approval_status: ApprovalStatus = ApprovalStatus.review
    locked: bool = False


class ScriptDocument(StrictModel):
    script_id: str = Field(default_factory=lambda: new_id("script"))
    story_id: str
    headline: str
    dek: str = ""
    category: str = "general"
    estimated_duration_seconds: float = 0.0
    version: int = 1
    status: ScriptStatus = ScriptStatus.review
    sections: list[ScriptSection]
    lower_thirds: list[str] = Field(default_factory=list)
    chyrons: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @property
    def text(self) -> str:
        return "\n\n".join(
            section.text.strip() for section in self.sections if section.text.strip()
        )


class VisualCandidate(StrictModel):
    asset_id: str = Field(default_factory=lambda: new_id("visual"))
    story_id: str
    section_ids: list[str] = Field(default_factory=list)
    provider: str
    source_url: str | None = None
    source_domain: str | None = None
    download_path: str | None = None
    thumbnail_path: str | None = None
    media_type: MediaType
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    title: str = ""
    description: str = ""
    creator: str | None = None
    published_at: str | None = None
    relevance_score: float = 0.0
    visual_quality_score: float = 0.0
    source_authority: float = 0.0
    content_role: ContentRole = ContentRole.context
    rights_tier: RightsTier = RightsTier.yellow
    rights_confidence: float = 0.0
    usage_basis: str = "manual_review_required"
    license: str | None = None
    attribution_required: bool = True
    attribution_text: str | None = None
    manual_review_flag: bool = True
    review_status: ReviewStatus = ReviewStatus.suggested
    warnings: list[str] = Field(default_factory=list)
    trim_start: float | None = None
    trim_end: float | None = None
    motion: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def enforce_rights_state(self) -> "VisualCandidate":
        if self.rights_tier == RightsTier.red and self.review_status in {
            ReviewStatus.approved,
            ReviewStatus.manual_approved,
        }:
            raise ValueError("red-tier visual assets cannot be approved")
        if (
            self.rights_tier == RightsTier.yellow
            and self.review_status == ReviewStatus.approved
        ):
            raise ValueError("yellow-tier visual assets require manual_approved")
        return self


class SegmentAnchor(StrictModel):
    visible: bool = True
    speaking: bool = True
    camera: str = "front_close"


class SegmentVisual(StrictModel):
    asset_id: str | None = None
    path: str | None = None
    media_type: MediaType = MediaType.fallback
    content_role: ContentRole = ContentRole.fallback
    source: str | None = None
    source_url: str | None = None
    rights_tier: RightsTier = RightsTier.green
    review_status: ReviewStatus = ReviewStatus.approved
    audio_mode: Literal["muted", "original", "mixed"] = "muted"
    trim_start: float | None = None
    trim_end: float | None = None
    attribution_text: str | None = None


class SegmentTemplate(StrictModel):
    template_id: str
    layout: str | None = None


class SegmentAudio(StrictModel):
    mode: AudioMode = AudioMode.narration
    narration_volume: float = 1.0
    source_volume: float = 0.0
    ducking: bool = False


class SegmentOverlays(StrictModel):
    lower_third: str = ""
    chyron: str = ""
    attribution: str = ""
    quote_text: str = ""
    document_source: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class TimelineSegment(StrictModel):
    segment_id: str
    section_id: str
    start_time: float
    end_time: float
    duration: float
    script_text: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    anchor: SegmentAnchor = Field(default_factory=SegmentAnchor)
    visual: SegmentVisual = Field(default_factory=SegmentVisual)
    template: SegmentTemplate
    audio: SegmentAudio = Field(default_factory=SegmentAudio)
    overlays: SegmentOverlays = Field(default_factory=SegmentOverlays)
    status: ApprovalStatus = ApprovalStatus.review

    @model_validator(mode="after")
    def validate_timing(self) -> "TimelineSegment":
        if self.start_time < 0 or self.end_time <= self.start_time:
            raise ValueError("segment timing must be positive and ordered")
        expected = round(self.end_time - self.start_time, 3)
        if abs(expected - self.duration) > 0.05:
            raise ValueError("segment duration must match end_time - start_time")
        return self


class AudioRegion(StrictModel):
    region_id: str = Field(default_factory=lambda: new_id("aud"))
    segment_id: str
    start_time: float
    end_time: float
    mode: AudioMode
    narration_path: str | None = None
    source_path: str | None = None
    narration_volume: float = 1.0
    source_volume: float = 0.0


class AudioPlan(StrictModel):
    story_id: str
    duration_seconds: float
    regions: list[AudioRegion] = Field(default_factory=list)
    strategy: Literal["timeline_aligned_avatar", "segment_clips"] = (
        "timeline_aligned_avatar"
    )
    warnings: list[str] = Field(default_factory=list)


class TimelinePlan(StrictModel):
    timeline_id: str = Field(default_factory=lambda: new_id("timeline"))
    story_id: str
    version: int = 1
    status: TimelineStatus = TimelineStatus.draft
    segments: list[TimelineSegment]
    audio_plan: AudioPlan | None = None
    validation_warnings: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class RenderJob(StrictModel):
    job_id: str = Field(default_factory=lambda: new_id("job"))
    episode_id: str | None = None
    story_id: str | None = None
    job_type: str
    render_profile: str = "preview"
    status: JobStatus = JobStatus.queued
    progress: float = 0.0
    stage: str = "queued"
    started_at: str | None = None
    completed_at: str | None = None
    output_paths: dict[str, str] = Field(default_factory=dict)
    log_path: str | None = None
    error: str | None = None
    traceback: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    attempts: int = 0
    max_attempts: int = 2
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class ArtifactRecord(StrictModel):
    artifact_id: str = Field(default_factory=lambda: new_id("art"))
    artifact_type: str
    path: str
    content_hash: str | None = None
    created_at: str = Field(default_factory=now_iso)
    producer: str
    inputs: list[str] = Field(default_factory=list)
    render_profile: str | None = None
    test_mode: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContractEnvelope(StrictModel):
    contract_version: str = "synthpost.v2"
    payload: dict[str, Any]
