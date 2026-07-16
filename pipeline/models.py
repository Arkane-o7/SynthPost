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
from pipeline.scripts.text import (
    narration_beats,
    normalize_section_headline_cues,
    section_overlay_text,
    timed_section_headline_cues,
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
    expired = "expired"


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


class NarrationMode(str, Enum):
    signal = "signal"
    explained = "explained"
    deep_dive = "deep_dive"
    india_builds = "india_builds"


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
    paused = "paused"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobQueueLane(str, Enum):
    editorial = "editorial"
    media = "media"
    render = "render"


def queue_lane_for_job_type(job_type: str) -> JobQueueLane:
    if job_type in {"visual_search", "timeline_generate"}:
        return JobQueueLane.media
    if job_type in {"render_avatar", "render_story", "assemble_episode"}:
        return JobQueueLane.render
    return JobQueueLane.editorial


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
    last_success_at: str | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    last_item_count: int = 0

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


class EditorialFitAssessment(StrictModel):
    charter_version: str = "1.0.0"
    score: float = 0.0
    eligible: bool = False
    primary_topic: str = "general"
    matched_criteria: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)
    rejection_signals: list[str] = Field(default_factory=list)
    india_relevance: float = 0.0
    india_impact: str = ""
    india_impact_confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)


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
    editorial_fit: EditorialFitAssessment = Field(
        default_factory=EditorialFitAssessment
    )
    final_score: float = 0.0
    score_reasons: list[str] = Field(default_factory=list)
    selection_status: StorySelectionStatus = StorySelectionStatus.suggested
    rejection_reasons: list[str] = Field(default_factory=list)
    duplicate_group_id: str | None = None
    event_cluster_id: str | None = None
    cluster_size: int = 1
    supporting_sources: list[str] = Field(default_factory=list)
    related_candidate_ids: list[str] = Field(default_factory=list)
    evidence_score: float = 0.0
    assignment_lane: str = "unassessed"
    assignment_summary: str = ""
    recommended_format: str = "explained"
    assignment_confidence: float = 0.0
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
    discovery_method: str | None = None
    research_query: str | None = None
    relevance_score: float | None = None
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
    research_queries: list[str] = Field(default_factory=list)
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
    systems: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)
    execution_gaps: list[str] = Field(default_factory=list)
    editorial_questions: list[str] = Field(default_factory=list)
    charter_version: str = "1.0.0"
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


class SourceClipCue(StrictModel):
    """An editorially authored pause for primary-source audio.

    The cue is attached to a narrated section and plays immediately after that
    section's setup. ``fallback_narration`` is spoken only when no usable local
    video with audio can satisfy the cue.
    """

    duration_seconds: float = Field(ge=3.0, le=30.0)
    search_query: str = Field(min_length=4, max_length=180)
    description: str = Field(min_length=4, max_length=320)
    fallback_narration: str = Field(min_length=4, max_length=600)
    speaker: str = Field(default="", max_length=120)
    quote: str = Field(default="", max_length=500)


class NarrativeArcItem(StrictModel):
    """One editorial job in a narrative brief, before prose is written."""

    section_type: SectionType
    purpose: str = Field(min_length=4, max_length=320)
    claim_ids: list[str] = Field(default_factory=list)
    must_not_repeat: list[str] = Field(default_factory=list)


class NarrativeBrief(StrictModel):
    """A story-level plan that allocates evidence across one continuous arc."""

    headline: str
    dek: str = ""
    category: str = "news"
    thesis: str = Field(min_length=4, max_length=600)
    opening_strategy: str = Field(min_length=4, max_length=400)
    closing_strategy: str = Field(min_length=4, max_length=400)
    arc: list[NarrativeArcItem]


class NarrativeBeat(StrictModel):
    """A stable sentence or major clause inside uninterrupted narration."""

    beat_id: str
    text: str = Field(min_length=2, max_length=1200)
    claim_ids: list[str] = Field(default_factory=list)


class NarrativeDraft(StrictModel):
    """The authoritative narration before presentation sections are assigned."""

    headline: str
    dek: str = ""
    category: str = "news"
    beats: list[NarrativeBeat]

    @property
    def text(self) -> str:
        return " ".join(beat.text.strip() for beat in self.beats if beat.text.strip())


class NarrativeSegmentPlan(StrictModel):
    """Presentation metadata referencing narration beats without rewriting them."""

    section_type: SectionType
    beat_ids: list[str]
    suggested_visual_types: list[str] = Field(default_factory=list)
    suggested_search_queries: list[str] = Field(default_factory=list)
    suggested_template_ids: list[str] = Field(default_factory=list)
    lower_third: str = ""
    chyron: str = ""
    source_clip: SourceClipCue | None = None


class NarrativeSegmentation(StrictModel):
    sections: list[NarrativeSegmentPlan]


class ScriptBeat(StrictModel):
    """A stable production cue inside one approved script section."""

    beat_id: str
    text: str = Field(min_length=2, max_length=1200)
    claim_ids: list[str] = Field(default_factory=list)


class ScriptSection(StrictModel):
    section_id: str
    section_type: SectionType
    text: str
    estimated_duration_seconds: float = 0.0
    claim_ids: list[str] = Field(default_factory=list)
    suggested_visual_types: list[str] = Field(default_factory=list)
    suggested_search_queries: list[str] = Field(default_factory=list)
    suggested_template_ids: list[str] = Field(default_factory=list)
    lower_third: str = ""
    chyron: str = ""
    headline_cues: list[str] = Field(default_factory=list)
    beats: list[ScriptBeat] = Field(default_factory=list)
    source_clip: SourceClipCue | None = None
    editorial_notes: list[str] = Field(default_factory=list)
    approval_status: ApprovalStatus = ApprovalStatus.review
    locked: bool = False

    @model_validator(mode="after")
    def normalize_production_beats(self) -> "ScriptSection":
        expected_texts = narration_beats(self.text) or [self.text.strip()]
        current_text = " ".join(beat.text.strip() for beat in self.beats)
        expected_text = " ".join(text.strip() for text in expected_texts)
        ids_are_unique = len({beat.beat_id for beat in self.beats}) == len(self.beats)
        if (
            not self.beats
            or not ids_are_unique
            or " ".join(current_text.split()) != " ".join(expected_text.split())
        ):
            self.rebuild_beats()
        return self

    def rebuild_beats(self) -> None:
        """Recreate stable beat IDs after an editor changes section narration."""

        texts = narration_beats(self.text) or [self.text.strip()]
        self.beats = [
            ScriptBeat(
                beat_id=f"{self.section_id}_beat_{index:02d}",
                text=text,
                claim_ids=list(self.claim_ids),
            )
            for index, text in enumerate(texts, start=1)
            if text.strip()
        ]


class ScriptDocument(StrictModel):
    script_id: str = Field(default_factory=lambda: new_id("script"))
    story_id: str
    headline: str
    dek: str = ""
    category: str = "general"
    narration_mode: NarrationMode = NarrationMode.explained
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

    @model_validator(mode="after")
    def normalize_section_overlays(self) -> "ScriptDocument":
        """Backfill section overlays and keep legacy positional arrays in sync.

        Older V2 scripts stored a single episode headline in ``lower_thirds`` and
        ``chyrons``. Treat a one-item list on a multi-section script as that
        legacy format, then derive distinct overlays from each section's actual
        narration. Multi-item lists remain valid positional input for older API
        clients.
        """

        lower_thirds = list(self.lower_thirds)
        chyrons = list(self.chyrons)
        positional_lower_thirds = len(lower_thirds) > 1 or len(self.sections) == 1
        positional_chyrons = len(chyrons) > 1 or len(self.sections) == 1
        seen_lower_thirds: set[str] = set()
        seen_chyrons: set[str] = set()
        episode_lower_third = section_overlay_text(
            self.headline, "intro", max_chars=80
        ).casefold()
        episode_chyron = section_overlay_text(
            self.headline, "intro", max_chars=64
        ).casefold()

        for index, section in enumerate(self.sections):
            lower_third = section.lower_third.strip()
            if not lower_third:
                lower_third = (
                    lower_thirds[index]
                    if positional_lower_thirds and index < len(lower_thirds)
                    else ""
                )
            lower_third = section_overlay_text(
                lower_third or section.text, section.section_type, max_chars=80
            )
            if len(self.sections) > 1 and (
                lower_third.casefold() == episode_lower_third
                or lower_third.casefold() in seen_lower_thirds
            ):
                lower_third = section_overlay_text(
                    section.text, section.section_type, max_chars=80
                )
            if lower_third.casefold() in seen_lower_thirds:
                lower_third = section_overlay_text(
                    f"{section.section_type.replace('_', ' ').title()}: "
                    f"{section.text}",
                    section.section_type,
                    max_chars=80,
                )
            section.lower_third = lower_third
            seen_lower_thirds.add(lower_third.casefold())

            chyron = section.chyron.strip()
            if not chyron:
                chyron = (
                    chyrons[index]
                    if positional_chyrons and index < len(chyrons)
                    else ""
                )
            chyron = section_overlay_text(
                chyron or section.text, section.section_type, max_chars=64
            )
            if len(self.sections) > 1 and (
                chyron.casefold() == episode_chyron
                or chyron.casefold() in seen_chyrons
            ):
                chyron = section_overlay_text(
                    section.text, section.section_type, max_chars=64
                )
            if chyron.casefold() in seen_chyrons:
                chyron = section_overlay_text(
                    f"{section.section_type.replace('_', ' ').title()}: "
                    f"{section.text}",
                    section.section_type,
                    max_chars=64,
                )
            section.chyron = chyron
            seen_chyrons.add(chyron.casefold())

            section.headline_cues = normalize_section_headline_cues(
                section.text,
                section.section_type,
                section.headline_cues,
            )

        self.lower_thirds = [section.lower_third for section in self.sections]
        self.chyrons = [section.chyron for section in self.sections]
        return self

    @property
    def text(self) -> str:
        return "\n\n".join(
            section.text.strip() for section in self.sections if section.text.strip()
        )


class NarrationBeatTiming(StrictModel):
    """Sample-derived timing for one Kokoro production beat."""

    beat_id: str
    section_id: str
    text: str
    kind: Literal["narration", "source_fallback"] = "narration"
    start_time: float = Field(ge=0)
    speech_end_time: float = Field(gt=0)
    end_time: float = Field(gt=0)
    pause_after_seconds: float = Field(default=0.0, ge=0)
    start_sample: int = Field(ge=0)
    speech_end_sample: int = Field(gt=0)
    end_sample: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_order(self) -> "NarrationBeatTiming":
        if not (
            self.start_time < self.speech_end_time <= self.end_time
            and self.start_sample < self.speech_end_sample <= self.end_sample
        ):
            raise ValueError("narration beat timing must be positive and ordered")
        return self


class NarrationSectionTiming(StrictModel):
    """Exact continuous-audio window owned by one script section."""

    section_id: str
    beat_ids: list[str]
    start_time: float = Field(ge=0)
    speech_end_time: float = Field(gt=0)
    end_time: float = Field(gt=0)
    duration_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_order(self) -> "NarrationSectionTiming":
        if not self.beat_ids:
            raise ValueError("narration section timing requires at least one beat")
        if not self.start_time < self.speech_end_time <= self.end_time:
            raise ValueError("narration section timing must be positive and ordered")
        if abs((self.end_time - self.start_time) - self.duration_seconds) > 0.01:
            raise ValueError("narration section duration must match its time window")
        return self


class NarrationArtifact(StrictModel):
    """Canonical local narration audio and its exact beat-level clock."""

    contract_version: Literal["synthpost.narration.v1"] = "synthpost.narration.v1"
    story_id: str
    episode_id: str
    script_id: str
    script_version: int
    input_hash: str
    provider: Literal["kokoro"] = "kokoro"
    model: str = "Kokoro-82M"
    voice_id: str
    voice_speed: float = Field(gt=0)
    language_code: str
    sample_rate: int = Field(gt=0)
    timing_source: Literal["kokoro_exact_samples"] = "kokoro_exact_samples"
    test_mode: bool = False
    audio_path: str
    duration_seconds: float = Field(gt=0)
    beats: list[NarrationBeatTiming]
    sections: list[NarrationSectionTiming]
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def validate_timeline(self) -> "NarrationArtifact":
        if not self.beats or not self.sections:
            raise ValueError("narration artifact requires beats and sections")
        previous_end = 0.0
        for beat in self.beats:
            if beat.start_time < previous_end - 0.002:
                raise ValueError("narration beats must be monotonic")
            previous_end = beat.end_time
        if abs(previous_end - self.duration_seconds) > 0.01:
            raise ValueError("narration duration must match the final beat")
        return self

class VisualCandidate(StrictModel):
    asset_id: str = Field(default_factory=lambda: new_id("visual"))
    story_id: str
    section_ids: list[str] = Field(default_factory=list)
    provider: str
    source_url: str | None = None
    source_domain: str | None = None
    download_path: str | None = None
    quarantine_path: str | None = None
    thumbnail_path: str | None = None
    media_type: MediaType
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    has_audio: bool | None = None
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
    reviewed_at: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_class: str = "unknown"
    source_identity: str | None = None
    source_channel_id: str | None = None
    source_channel_name: str | None = None
    source_verified: bool = False
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    content_cleanliness_status: Literal[
        "not_scanned", "needs_review", "passed", "rejected"
    ] = "not_scanned"
    contains_third_party_logo: bool = False
    detected_brands: list[str] = Field(default_factory=list)
    contains_lower_third: bool = False
    contains_ticker: bool = False
    contains_presenter: bool = False
    ocr_findings: list[dict[str, Any]] = Field(default_factory=list)
    scan_timestamps: list[float] = Field(default_factory=list)
    analysis_frame_paths: list[str] = Field(default_factory=list)
    contact_sheet_path: str | None = None
    clean_broll_score: float = 0.0
    content_analysis_version: str | None = None
    content_analysis_provider: str | None = None
    content_analysis_evidence: list[str] = Field(default_factory=list)
    approval_blockers: list[str] = Field(default_factory=list)
    broadcast_fit_override: bool = False
    trim_start: float | None = None
    trim_end: float | None = None
    motion: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def enforce_rights_state(self) -> "VisualCandidate":
        normalized_warnings: list[str] = []
        obsolete_local_fragments = (
            "download failed",
            "research lead only",
            "requested format is not available",
            "yt-dlp completed without a supported video file",
        )
        for warning in self.warnings:
            if warning.lower().startswith("download rejected for broadcast layout:"):
                warning = "broadcast layout warning:" + warning.split(":", 1)[1]
            if self.download_path and any(
                fragment in warning.lower() for fragment in obsolete_local_fragments
            ):
                continue
            if warning not in normalized_warnings:
                normalized_warnings.append(warning)
        self.warnings = normalized_warnings
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
    has_audio: bool | None = None
    attribution_text: str | None = None
    content_cleanliness_status: Literal[
        "not_scanned", "needs_review", "passed", "rejected"
    ] = "not_scanned"
    approval_blockers: list[str] = Field(default_factory=list)


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
    queue_lane: JobQueueLane | None = None
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
    available_at: str | None = None
    last_attempt_at: str | None = None
    last_error: str | None = None
    failure_kind: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def infer_queue_lane(self):
        if self.queue_lane is None:
            self.queue_lane = queue_lane_for_job_type(self.job_type)
        return self


class GenerationAudit(StrictModel):
    audit_id: str = Field(default_factory=lambda: new_id("audit"))
    story_id: str
    job_id: str | None = None
    stage: str
    prompt_version: str
    charter_version: str
    provider: str
    model: str | None = None
    prompt_text: str
    response: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    validation_events: list[dict[str, Any]] = Field(default_factory=list)
    normalization_events: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "completed"
    created_at: str = Field(default_factory=now_iso)


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
