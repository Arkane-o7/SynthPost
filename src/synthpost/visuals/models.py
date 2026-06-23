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
            "asset_id": self.asset_id,
            "asset_type": self.asset_type.value,
            "title": self.title,
            "provider": self.provider,
            "path": self.path,
            "remote_url": self.remote_url,
            "source_url": self.source_url,
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
        }
        record.update({key: value for key, value in self.extra.items() if value not in (None, [], {})})
        return {key: value for key, value in record.items() if value not in (None, [], {})}


@dataclass(slots=True)
class ProviderReport:
    provider: str
    query_count: int = 0
    candidate_count: int = 0
    selected_count: int = 0
    skipped_reason: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "provider": self.provider,
            "query_count": self.query_count,
            "candidate_count": self.candidate_count,
            "selected_count": self.selected_count,
            "skipped_reason": self.skipped_reason,
            "warnings": self.warnings,
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

    def selected_records(self) -> list[dict[str, Any]]:
        return [asset.to_record() for asset in self.selected_assets]

    def summary(self) -> dict[str, Any]:
        return {
            "duration_seconds": self.duration_seconds,
            "segment_count": len(self.segments),
            "candidate_count": len(self.candidates),
            "selected_count": len(self.selected_assets),
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
