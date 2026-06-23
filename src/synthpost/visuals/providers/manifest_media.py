from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from typing import Any

from ..downloader import safe_filename
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
from ..query_builder import compact_text, tokenize, unique

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
OPEN_LICENSE_HINTS = ("public domain", "cc0", "cc-by", "cc by", "creative commons", "open license", "government work")


class ManifestMediaProvider(VisualProvider):
    name = "manifest_media"

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
        records = self._records(manifest)
        report = ProviderReport(provider=self.name, query_count=len(queries))
        assets: list[VisualAsset] = []
        for index, record in enumerate(records):
            asset = self._asset(record, index=index, manifest=manifest, story_json_path=story_json_path)
            if not asset:
                continue
            if self._matches_any(asset, queries):
                assets.append(asset)
        report.candidate_count = len(assets)
        if not records:
            report.skipped_reason = "No manifest-provided media in raw.visual_assets/raw.official_media/etc."
        return assets, report

    def _records(self, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
        sources: list[Any] = []
        for key in ("visual_assets", "media_assets", "official_media", "visuals"):
            sources.extend(self._as_list(raw.get(key)))
        for key, asset_type in (
            ("image_urls", AssetType.IMAGE.value),
            ("official_image_urls", AssetType.IMAGE.value),
            ("video_urls", AssetType.VIDEO.value),
            ("official_video_urls", AssetType.VIDEO.value),
        ):
            for value in self._as_list(raw.get(key)):
                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("asset_type", asset_type)
                    sources.append(item)
                elif value:
                    sources.append({"url": value, "asset_type": asset_type, "source_url": value})

        records: list[dict[str, Any]] = []
        for item in sources:
            if isinstance(item, str):
                records.append({"url": item})
            elif isinstance(item, dict):
                records.append(item)
        return records

    def _asset(
        self,
        record: dict[str, Any],
        *,
        index: int,
        manifest: dict[str, Any],
        story_json_path: Path,
    ) -> VisualAsset | None:
        raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
        value = compact_text(record.get("path") or record.get("downloaded_path") or record.get("remote_url") or record.get("url"))
        if not value:
            return None

        is_remote = value.startswith(("http://", "https://"))
        ext = Path(urllib.parse.urlparse(value).path if is_remote else value).suffix.lower()
        if ext and ext not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            return None

        asset_type = self._asset_type(record, ext)
        title = compact_text(record.get("title") or record.get("headline") or Path(urllib.parse.urlparse(value).path).stem)
        if not title:
            title = f"Manifest media {index + 1}"
        license_name = compact_text(record.get("license") or record.get("license_name"))
        usage_note = compact_text(record.get("usage_note") or record.get("rights_note"))
        source_url = compact_text(record.get("source_url") or record.get("page_url") or raw.get("source_url") or value)
        source_name = compact_text(record.get("source_name") or record.get("source") or raw.get("source_name") or "Manifest Media")
        keywords = unique(
            [
                *tokenize(title),
                *tokenize(record.get("description")),
                *tokenize(source_name),
                *self._keyword_values(record.get("keywords")),
            ],
            limit=24,
        )
        rights_tier = compact_text(record.get("rights_tier"))
        source_authority = compact_text(record.get("source_authority"))
        usage_basis = compact_text(record.get("usage_basis"))

        return VisualAsset(
            asset_id=safe_filename(str(record.get("asset_id") or f"manifest_{story_json_path.parent.name}_{index + 1:02d}")),
            asset_type=asset_type,
            title=title,
            provider=self.name,
            path=None if is_remote else value,
            remote_url=value if is_remote else None,
            source_url=source_url or value,
            source_name=source_name,
            license=license_name or "manifest-provided",
            usage_note=usage_note
            or "Manifest-provided media. Treat as rights-cleared only when source metadata says so.",
            attribution=compact_text(record.get("attribution") or record.get("credit")),
            downloaded_path=compact_text(record.get("downloaded_path") or record.get("path")),
            story_id=str(manifest.get("story_id") or story_json_path.parent.name),
            segment_id=compact_text(record.get("segment_id")) or None,
            keywords=keywords,
            safe_to_use=self._safe_to_use(record, license_name, usage_note, is_remote=is_remote),
            fallback_reason=compact_text(record.get("fallback_reason")) or None,
            width=record.get("width"),
            height=record.get("height"),
            duration_seconds=record.get("duration_seconds"),
            rights_tier=rights_tier or (RightsTier.GREEN.value if self._safe_to_use(record, license_name, usage_note, is_remote=is_remote) else RightsTier.RED.value),
            rights_confidence=compact_text(record.get("rights_confidence")) or RightsConfidence.VERIFIED.value,
            usage_basis=usage_basis or self._usage_basis(record, license_name, usage_note, is_remote=is_remote),
            attribution_required=bool(record.get("attribution_required", bool(record.get("attribution") or record.get("credit")))),
            attribution_text=compact_text(record.get("attribution_text")),
            source_authority=source_authority or self._source_authority(record, is_remote=is_remote),
            content_role=compact_text(record.get("content_role")) or self._content_role(asset_type),
            media_type=compact_text(record.get("media_type")) or self._media_type(asset_type),
            risk_level=compact_text(record.get("risk_level")) or RiskLevel.LOW.value,
            manual_review_status=compact_text(record.get("manual_review_status")) or ManualReviewStatus.NOT_REQUIRED.value,
            motion=dict(record.get("motion") or {}),
            extra={
                "visual_role": record.get("visual_role") or record.get("role") or "manifest_media",
                "rights_tier": record.get("rights_tier"),
                "rights_confidence": record.get("rights_confidence"),
                "usage_basis": record.get("usage_basis"),
                "source_authority": record.get("source_authority"),
                "content_role": record.get("content_role"),
                "media_type": record.get("media_type"),
                "risk_level": record.get("risk_level"),
                "manual_review_status": record.get("manual_review_status"),
                "motion": record.get("motion"),
            },
        )

    def _asset_type(self, record: dict[str, Any], ext: str) -> AssetType:
        configured = compact_text(record.get("asset_type")).lower()
        if configured:
            try:
                return AssetType(configured)
            except ValueError:
                pass
        if ext in VIDEO_EXTENSIONS:
            return AssetType.VIDEO
        return AssetType.IMAGE

    def _safe_to_use(self, record: dict[str, Any], license_name: str, usage_note: str, *, is_remote: bool) -> bool:
        if "safe_to_use" in record:
            return bool(record.get("safe_to_use"))
        if os.environ.get("SYNTHPOST_TRUST_MANIFEST_MEDIA", "1") != "0" and not is_remote:
            return True
        rights_text = f"{license_name} {usage_note}".lower()
        return any(hint in rights_text for hint in OPEN_LICENSE_HINTS)

    def _usage_basis(self, record: dict[str, Any], license_name: str, usage_note: str, *, is_remote: bool) -> str:
        rights_text = f"{license_name} {usage_note}".lower()
        if "cc0" in rights_text:
            return UsageBasis.CC0.value
        if "cc-by-sa" in rights_text or "cc by-sa" in rights_text or "cc by sa" in rights_text:
            return UsageBasis.CC_BY_SA.value
        if "cc-by" in rights_text or "cc by" in rights_text or "creative commons" in rights_text:
            return UsageBasis.CC_BY.value
        if "public domain" in rights_text or "government work" in rights_text:
            return UsageBasis.PUBLIC_DOMAIN.value
        if compact_text(record.get("official")) or "official" in compact_text(record.get("source_name")).lower():
            return UsageBasis.OFFICIAL_PRESS.value
        return UsageBasis.USER_PROVIDED.value if not is_remote else UsageBasis.EDITORIAL_REVIEW.value

    def _source_authority(self, record: dict[str, Any], *, is_remote: bool) -> str:
        source = compact_text(record.get("source_name") or record.get("source")).lower()
        if compact_text(record.get("official")) or any(term in source for term in ("government", "ministry", "nasa", "dvids", "pib", "pb-shabd", "official")):
            return SourceAuthority.OFFICIAL.value
        return SourceAuthority.CREATOR.value if not is_remote else SourceAuthority.UNKNOWN.value

    def _content_role(self, asset_type: AssetType) -> str:
        if asset_type in {AssetType.MAP, AssetType.CHART, AssetType.DOCUMENT, AssetType.SCREENSHOT, AssetType.SATELLITE}:
            return ContentRole.EXPLANATION.value
        return ContentRole.EVIDENCE.value if asset_type == AssetType.VIDEO else ContentRole.CONTEXT.value

    def _media_type(self, asset_type: AssetType) -> str:
        return {
            AssetType.VIDEO: MediaType.VIDEO.value,
            AssetType.IMAGE: MediaType.PHOTO.value,
            AssetType.SCREENSHOT: MediaType.SCREENSHOT.value,
            AssetType.DOCUMENT: MediaType.DOCUMENT.value,
            AssetType.MAP: MediaType.MAP.value,
            AssetType.CHART: MediaType.CHART.value,
            AssetType.SATELLITE: MediaType.SATELLITE.value,
        }.get(asset_type, MediaType.PHOTO.value)

    def _matches_any(self, asset: VisualAsset, queries: list[VisualQuery]) -> bool:
        if not queries or asset.segment_id:
            return True
        asset_words = set(tokenize(" ".join([asset.title, asset.source_name or "", " ".join(asset.keywords)])))
        if not asset_words:
            return True
        for query in queries:
            query_words = set(tokenize(" ".join([query.query, " ".join(query.keywords)])))
            if asset_words & query_words:
                return True
        return False

    def _as_list(self, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _keyword_values(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return tokenize(value)
        if isinstance(value, list):
            return [compact_text(item) for item in value if compact_text(item)]
        return []
