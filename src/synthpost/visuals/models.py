from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AssetType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    SCREENSHOT = "screenshot"
    CHART = "chart"
    MAP = "map"
    DOCUMENT = "document"
    SATELLITE = "satellite"
    GENERATED = "generated"
    PLACEHOLDER = "placeholder"


class RightsTier(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class RightsConfidence(str, Enum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class UsageBasis(str, Enum):
    PUBLIC_DOMAIN = "public_domain"
    CC0 = "cc0"
    CC_BY = "cc_by"
    CC_BY_SA = "cc_by_sa"
    OFFICIAL_PRESS = "official_press"
    USER_PROVIDED = "user_provided"
    FIRST_PARTY_GENERATED = "first_party_generated"
    EDITORIAL_REVIEW = "editorial_review"
    STOCK_FALLBACK = "stock_fallback"


class SourceAuthority(str, Enum):
    OFFICIAL = "official"
    WIRE = "wire"
    OPEN_ARCHIVE = "open_archive"
    CREATOR = "creator"
    PLATFORM = "platform"
    STOCK = "stock"
    UNKNOWN = "unknown"


class ContentRole(str, Enum):
    EVIDENCE = "evidence"
    CONTEXT = "context"
    EXPLANATION = "explanation"
    ATMOSPHERE = "atmosphere"


class MediaType(str, Enum):
    VIDEO = "video"
    PHOTO = "photo"
    SCREENSHOT = "screenshot"
    DOCUMENT = "document"
    MAP = "map"
    CHART = "chart"
    SATELLITE = "satellite"
    STOCK = "stock"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ManualReviewStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProviderType(str, Enum):
    OFFICIAL = "official"
    OPEN_ARCHIVE = "open_archive"
    LOCAL_LIBRARY = "local_library"
    GENERATED = "generated"
    STOCK = "stock"
    SOCIAL = "social"
    WEB_LEAD = "web_lead"
    UNKNOWN = "unknown"


class RightsCategory(str, Enum):
    OFFICIAL_PUBLIC = "official_public"
    PUBLIC_DOMAIN = "public_domain"
    PERMISSIVE_LICENSE = "permissive_license"
    FIRST_PARTY_GENERATED = "first_party_generated"
    FAIR_USE_REVIEW_REQUIRED = "fair_use_review_required"
    UNKNOWN_OR_REJECTED = "unknown_or_rejected"


class SelectionStatus(str, Enum):
    CANDIDATE = "candidate"
    SELECTED = "selected"
    REJECTED = "rejected"


class VisualSkillType(str, Enum):
    MAP = "map"
    CHART = "chart"
    TIMELINE = "timeline"
    DOCUMENT_CALLOUT = "document_callout"
    QUOTE_CARD = "quote_card"
    DATA_CALLOUT = "data_callout"
    CONTEXT_CARD = "context_card"
    ENTITY_CARD = "entity_card"
    SOURCE_CARD = "source_card"
    BROLL_CLIP = "broll_clip"
    STILL_IMAGE = "still_image"


@dataclass(slots=True)
class StorySegment:
    segment_id: str
    title: str
    text: str
    start: float
    end: float
    keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VisualQuery:
    segment_id: str
    query: str
    keywords: list[str]
    desired_types: list[AssetType]
    start: float
    end: float


@dataclass(slots=True)
class VisualAsset:
    asset_id: str
    asset_type: AssetType
    title: str
    provider: str
    path: str | None = None
    remote_url: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    license: str | None = None
    usage_note: str | None = None
    attribution: str | None = None
    downloaded_path: str | None = None
    story_id: str | None = None
    segment_id: str | None = None
    keywords: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    safe_to_use: bool = False
    fallback_reason: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    rights_tier: str = RightsTier.RED.value
    rights_confidence: str = RightsConfidence.UNKNOWN.value
    usage_basis: str | None = None
    attribution_required: bool = False
    attribution_text: str | None = None
    source_authority: str = SourceAuthority.UNKNOWN.value
    content_role: str = ContentRole.CONTEXT.value
    media_type: str | None = None
    risk_level: str = RiskLevel.HIGH.value
    manual_review_status: str = ManualReviewStatus.REQUIRED.value
    motion: dict[str, Any] = field(default_factory=dict)
    provider_type: str = ProviderType.UNKNOWN.value
    source_domain: str | None = None
    asset_url: str | None = None
    caption: str | None = None
    alt_text: str | None = None
    entities: list[str] = field(default_factory=list)
    matched_story_entities: list[str] = field(default_factory=list)
    relevance_reason: str | None = None
    rights_category: str = RightsCategory.UNKNOWN_OR_REJECTED.value
    needs_manual_review: bool = True
    selection_status: str = SelectionStatus.CANDIDATE.value
    rejection_reasons: list[str] = field(default_factory=list)
    created_at: str | None = None
    fetched_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def identity_key(self) -> str:
        return self.path or self.remote_url or self.source_url or self.asset_id

    def with_score(self, score: float, *, segment_id: str | None = None) -> "VisualAsset":
        self.relevance_score = round(score, 2)
        if segment_id:
            self.segment_id = segment_id
        return self

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": self.asset_id,
            "asset_id": self.asset_id,
            "asset_type": self.asset_type.value,
            "title": self.title,
            "provider": self.provider,
            "provider_type": self.provider_type,
            "path": self.path,
            "remote_url": self.remote_url,
            "asset_url": self.asset_url,
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "source_name": self.source_name,
            "license": self.license,
            "usage_note": self.usage_note,
            "attribution": self.attribution,
            "downloaded_path": self.downloaded_path,
            "story_id": self.story_id,
            "segment_id": self.segment_id,
            "keywords": self.keywords,
            "relevance_score": self.relevance_score,
            "safe_to_use": self.safe_to_use,
            "fallback_reason": self.fallback_reason,
            "width": self.width,
            "height": self.height,
            "duration_seconds": self.duration_seconds,
            "rights_tier": self.rights_tier,
            "rights_confidence": self.rights_confidence,
            "usage_basis": self.usage_basis,
            "attribution_required": self.attribution_required,
            "attribution_text": self.attribution_text,
            "source_authority": self.source_authority,
            "content_role": self.content_role,
            "media_type": self.media_type,
            "risk_level": self.risk_level,
            "manual_review_status": self.manual_review_status,
            "motion": self.motion,
            "caption": self.caption,
            "alt_text": self.alt_text,
            "entities": self.entities,
            "matched_story_entities": self.matched_story_entities,
            "relevance_reason": self.relevance_reason,
            "rights_category": self.rights_category,
            "needs_manual_review": self.needs_manual_review,
            "selection_status": self.selection_status,
            "rejection_reasons": self.rejection_reasons,
            "created_at": self.created_at,
            "fetched_at": self.fetched_at,
        }
        record.update({key: value for key, value in self.extra.items() if value not in (None, [], {})})
        return {key: value for key, value in record.items() if value not in (None, [], {})}


@dataclass(slots=True)
class ProviderReport:
    provider: str
    provider_type: str = ProviderType.UNKNOWN.value
    query_count: int = 0
    candidate_count: int = 0
    selected_count: int = 0
    skipped_reason: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "provider": self.provider,
            "provider_type": self.provider_type,
            "query_count": self.query_count,
            "candidate_count": self.candidate_count,
            "selected_count": self.selected_count,
            "skipped_reason": self.skipped_reason,
            "warnings": self.warnings,
        }
        return {key: value for key, value in record.items() if value not in (None, [], {})}


@dataclass(slots=True)
class VisualPlanEntry:
    story_id: str
    episode_id: str
    section_id: str
    section_title: str
    section_type: str
    visual_role: str
    selected_visual_candidate_id: str
    media_type: str
    asset_type: str
    start: float
    end: float
    asset_url: str | None = None
    path: str | None = None
    source_url: str | None = None
    source_domain: str | None = None
    rights_category: str | None = None
    attribution: str | None = None
    attribution_text: str | None = None
    relevance_score: float = 0.0
    relevance_reason: str | None = None
    fallback_status: str = "none"
    fallback_reason: str | None = None
    needs_manual_review: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    selection_status: str = SelectionStatus.SELECTED.value

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "story_id": self.story_id,
            "episode_id": self.episode_id,
            "script_section_id": self.section_id,
            "section_title": self.section_title,
            "section_type": self.section_type,
            "visual_role": self.visual_role,
            "selected_visual_candidate_id": self.selected_visual_candidate_id,
            "media_type": self.media_type,
            "asset_type": self.asset_type,
            "asset_url": self.asset_url,
            "path": self.path,
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "rights_category": self.rights_category,
            "attribution": self.attribution,
            "attribution_text": self.attribution_text,
            "relevance_score": self.relevance_score,
            "relevance_reason": self.relevance_reason,
            "start": self.start,
            "end": self.end,
            "display_duration_seconds": round(max(0.0, self.end - self.start), 2),
            "fallback_status": self.fallback_status,
            "fallback_reason": self.fallback_reason,
            "needs_manual_review": self.needs_manual_review,
            "manual_review_flag": self.needs_manual_review,
            "rejection_reasons": self.rejection_reasons,
            "selection_status": self.selection_status,
        }
        return {key: value for key, value in record.items() if value not in (None, [], {})}


@dataclass(slots=True)
class VisualSkillSpec:
    skill_id: str
    story_id: str
    episode_id: str
    section_id: str
    selected_visual_candidate_id: str
    skill_type: str
    skill_reason: str
    spec: dict[str, Any]
    evidence_claim_ids: list[str] = field(default_factory=list)
    source_notes: list[str] = field(default_factory=list)
    source_url: str | None = None
    source_domain: str | None = None
    rights_category: str | None = None
    attribution_text: str | None = None
    needs_manual_review: bool = False
    fallback_reason: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        spec_key = f"{self.skill_type}_spec"
        record: dict[str, Any] = {
            "skill_id": self.skill_id,
            "story_id": self.story_id,
            "episode_id": self.episode_id,
            "script_section_id": self.section_id,
            "selected_visual_candidate_id": self.selected_visual_candidate_id,
            "skill_type": self.skill_type,
            "skill_reason": self.skill_reason,
            "spec": self.spec,
            spec_key: self.spec,
            "evidence_claim_ids": self.evidence_claim_ids,
            "source_notes": self.source_notes,
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "rights_category": self.rights_category,
            "attribution_text": self.attribution_text,
            "needs_manual_review": self.needs_manual_review,
            "manual_review_flag": self.needs_manual_review,
            "fallback_reason": self.fallback_reason,
            "warnings": self.warnings,
            "render_ready": True,
            "groundedness": {
                "status": "grounded_with_available_evidence" if not self.warnings else "grounded_with_warnings",
                "evidence_claim_ids": self.evidence_claim_ids,
            },
        }
        return {key: value for key, value in record.items() if value not in (None, [], {})}


@dataclass(slots=True)
class VisualPlan:
    story_id: str
    episode_id: str
    duration_seconds: float
    segments: list[StorySegment]
    candidates: list[VisualAsset]
    selected_assets: list[VisualAsset]
    manifest_visuals: list[dict[str, Any]]
    provider_reports: list[ProviderReport]
    warnings: list[str] = field(default_factory=list)
    plan_entries: list[VisualPlanEntry] = field(default_factory=list)
    planning_audit: dict[str, Any] = field(default_factory=dict)
    skill_specs: list[VisualSkillSpec] = field(default_factory=list)
    skill_audit: dict[str, Any] = field(default_factory=dict)
    audit_paths: dict[str, str] = field(default_factory=dict)

    def selected_records(self) -> list[dict[str, Any]]:
        return [asset.to_record() for asset in self.selected_assets]

    def plan_records(self) -> list[dict[str, Any]]:
        return [entry.to_record() for entry in self.plan_entries]

    def skill_records(self) -> list[dict[str, Any]]:
        return [spec.to_record() for spec in self.skill_specs]

    def summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "duration_seconds": self.duration_seconds,
            "segment_count": len(self.segments),
            "section_count": len(self.plan_entries),
            "candidate_count": len(self.candidates),
            "selected_count": len(self.selected_assets),
            "skill_count": len(self.skill_specs),
            "segments": [
                {
                    "segment_id": segment.segment_id,
                    "title": segment.title,
                    "start": segment.start,
                    "end": segment.end,
                    "keywords": segment.keywords,
                }
                for segment in self.segments
            ],
            "providers": [report.to_record() for report in self.provider_reports],
            "warnings": self.warnings,
        }
        if self.audit_paths:
            summary["audit_paths"] = self.audit_paths
            if self.audit_paths.get("visual_plan"):
                summary["visual_plan_path"] = self.audit_paths["visual_plan"]
        if self.planning_audit:
            summary["reuse_counts"] = self.planning_audit.get("reuse_counts", {})
            summary["fallback_count"] = self.planning_audit.get("fallback_count", 0)
            summary["manual_review_warning_count"] = len(self.planning_audit.get("manual_review_warnings", []))
            summary["coverage_warnings"] = self.planning_audit.get("missing_visual_coverage_warnings", [])
        if self.skill_audit:
            summary["skill_types"] = self.skill_audit.get("skill_types", {})
            summary["skill_warning_count"] = len(self.skill_audit.get("warnings", []))
        return summary


class VisualProvider:
    name = "provider"

    def search(
        self,
        *,
        manifest: dict[str, Any],
        story_json_path: Path,
        segments: list[StorySegment],
        queries: list[VisualQuery],
    ) -> tuple[list[VisualAsset], ProviderReport]:
        raise NotImplementedError
