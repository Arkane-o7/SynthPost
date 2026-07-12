from __future__ import annotations

import re
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
    paused = "paused"
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
    lower_third: str = ""
    chyron: str = ""
    headline_cues: list[str] = Field(default_factory=list)
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


def section_overlay_text(
    text: str, section_type: str, *, max_chars: int
) -> str:
    """Create a concise, deterministic overlay for legacy or manual scripts."""

    normalized = " ".join(text.split()).strip(" \t\n\r-–—")
    if not normalized:
        normalized = section_type.replace("_", " ").title()
    first_sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0]
    first_sentence = first_sentence.rstrip(".!?").strip()
    if len(first_sentence) <= max_chars:
        return first_sentence
    shortened = first_sentence[: max_chars + 1].rsplit(" ", 1)[0].rstrip(" ,;:-–—")
    return shortened or first_sentence[:max_chars].rstrip()


def narration_beats(text: str, *, max_words: int = 24) -> list[str]:
    """Split narration into stable sentence/clause beats for timed overlays."""

    normalized = " ".join(text.split()).strip()
    if not normalized:
        return []

    protected: dict[str, str] = {}

    def protect_abbreviation(match: re.Match[str]) -> str:
        token = f"__ABBR_{len(protected)}__"
        protected[token] = match.group(0)
        return token

    sentence_safe = re.sub(r"\b(?:[A-Z]\.){2,}", protect_abbreviation, normalized)
    sentences = re.split(r"(?<=[.!?])\s+", sentence_safe)
    sentences = [
        _restore_abbreviations(sentence, protected).strip()
        for sentence in sentences
        if sentence.strip()
    ]

    beats: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        if len(words) <= max_words:
            beats.append(sentence)
            continue
        clauses = [
            clause.strip()
            for clause in re.split(
                r"(?<=[;:])\s+|\s+[—–]\s+|,\s+(?=(?:and|but|while|which|as)\b)",
                sentence,
                flags=re.IGNORECASE,
            )
            if clause.strip()
        ]
        if len(clauses) == 1:
            clauses = [
                " ".join(words[index : index + max_words])
                for index in range(0, len(words), max_words)
            ]
        beats.extend(clauses)

    merged: list[str] = []
    for beat in beats:
        if merged and len(beat.split()) < 5:
            merged[-1] = f"{merged[-1]} {beat}".strip()
        else:
            merged.append(beat)
    return merged


def _restore_abbreviations(text: str, protected: dict[str, str]) -> str:
    for token, abbreviation in protected.items():
        text = text.replace(token, abbreviation)
    return text


def normalize_section_headline_cues(
    text: str,
    section_type: str,
    provided: list[str] | tuple[str, ...] = (),
) -> list[str]:
    """Return one concise headline per narration beat in spoken order."""

    beats = narration_beats(text)
    if not beats:
        return [section_overlay_text(text, section_type, max_chars=80)]
    cleaned = [
        section_overlay_text(str(value), section_type, max_chars=80)
        for value in provided
        if str(value).strip()
    ]
    if len(cleaned) == len(beats):
        return cleaned
    return [
        section_overlay_text(beat, section_type, max_chars=80) for beat in beats
    ]


def timed_section_headline_cues(
    text: str,
    section_type: str,
    provided: list[str] | tuple[str, ...],
    duration: float,
) -> list[dict[str, float | str]]:
    """Align section headlines to narration using spoken-word proportions."""

    beats = narration_beats(text)
    headlines = normalize_section_headline_cues(text, section_type, provided)
    if not beats:
        beats = [text or section_type.replace("_", " ")]
    weights = [max(1, len(beat.split())) for beat in beats]
    total_weight = max(1, sum(weights))
    cursor = 0
    cues: list[dict[str, float | str]] = []
    for index, (headline, weight) in enumerate(zip(headlines, weights)):
        start = duration * cursor / total_weight
        cursor += weight
        end = duration if index == len(headlines) - 1 else duration * cursor / total_weight
        cues.append(
            {
                "text": headline,
                "start": round(start, 3),
                "end": round(max(start + 0.01, end), 3),
            }
        )
    return cues


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
