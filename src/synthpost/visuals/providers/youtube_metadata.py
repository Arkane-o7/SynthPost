from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import (
    AssetType,
    ContentRole,
    ManualReviewStatus,
    MediaType,
    ProviderReport,
    RightsConfidence,
    RightsTier,
    RiskLevel,
    SourceAuthority,
    StorySegment,
    UsageBasis,
    VisualAsset,
    VisualProvider,
    VisualQuery,
)


class YouTubeMetadataProvider(VisualProvider):
    name = "youtube_metadata"

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def search(
        self,
        *,
        manifest: dict[str, Any],
        story_json_path: Path,
        segments: list[StorySegment],
        queries: list[VisualQuery],
    ) -> tuple[list[VisualAsset], ProviderReport]:
        raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
        urls = raw.get("official_video_urls") or raw.get("video_urls") or []
        if isinstance(urls, str):
            urls = [urls]
        report = ProviderReport(provider=self.name, query_count=len(queries))
        assets: list[VisualAsset] = []
        for index, url in enumerate(urls):
            segment = segments[min(index, len(segments) - 1)] if segments else None
            assets.append(
                VisualAsset(
                    asset_id=f"youtube_lead_{index + 1:02d}",
                    asset_type=AssetType.VIDEO,
                    title=f"Official video lead {index + 1}",
                    provider=self.name,
                    source_url=str(url),
                    source_name="YouTube",
                    usage_note="Metadata lead only. Download/use requires explicit rights, embed permission, or a user-provided local copy.",
                    story_id=str(manifest.get("story_id", "")),
                    segment_id=segment.segment_id if segment else None,
                    keywords=segment.keywords if segment else [],
                    safe_to_use=False,
                    fallback_reason="video_rights_review_required",
                    rights_tier=RightsTier.YELLOW.value,
                    rights_confidence=RightsConfidence.INFERRED.value,
                    usage_basis=UsageBasis.EDITORIAL_REVIEW.value,
                    attribution_required=True,
                    attribution_text=f"Source: YouTube / {url}",
                    source_authority=SourceAuthority.PLATFORM.value,
                    content_role=ContentRole.CONTEXT.value,
                    media_type=MediaType.VIDEO.value,
                    risk_level=RiskLevel.MEDIUM.value,
                    manual_review_status=ManualReviewStatus.REQUIRED.value,
                )
            )
        if not assets:
            report.skipped_reason = "No raw.official_video_urls/raw.video_urls in manifest"
        report.candidate_count = len(assets)
        return assets, report
