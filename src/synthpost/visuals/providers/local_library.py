from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..downloader import project_relative, safe_filename
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
from ..query_builder import tokenize, unique

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}


class LocalLibraryProvider(VisualProvider):
    name = "local_library"

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
        report = ProviderReport(provider=self.name, query_count=len(queries))
        roots = self._roots()
        assets: list[VisualAsset] = []
        for root, public_prefix in roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.name.startswith("."):
                    continue
                if path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                    continue
                metadata = self._sidecar_metadata(path)
                asset = self._asset_from_path(path, public_prefix, metadata)
                if self._matches_any(asset, queries):
                    assets.append(asset)

        report.candidate_count = len(assets)
        return assets, report

    def _roots(self) -> list[tuple[Path, str | None]]:
        roots: list[tuple[Path, str | None]] = [
            (self.project_root / "compositor" / "remotion_renderer" / "public" / "news", "news"),
            (self.project_root / "assets" / "visuals", None),
            (self.project_root / "media", None),
        ]
        configured = os.environ.get("SYNTHPOST_VISUAL_LIBRARY", "")
        for value in configured.replace(",", os.pathsep).split(os.pathsep):
            if value.strip():
                roots.append((Path(value).expanduser(), None))
        return roots

    def _asset_from_path(self, path: Path, public_prefix: str | None, metadata: dict[str, Any]) -> VisualAsset:
        relative_path = self._manifest_path(path, public_prefix)
        keywords = unique(
            [
                *tokenize(path.stem.replace("_", " ").replace("-", " ")),
                *tokenize(path.parent.name.replace("_", " ").replace("-", " ")),
                *(metadata.get("keywords") or []),
            ],
            limit=24,
        )
        asset_type = self._infer_type(path, keywords, metadata)
        title = str(metadata.get("title") or path.stem.replace("_", " ").replace("-", " ").title())
        safe_to_use = bool(metadata.get("safe_to_use", self._trust_local_library()))
        usage_note = str(
            metadata.get("usage_note")
            or "Local library asset. Assumed user-provided or rights-cleared; add sidecar metadata for public reuse."
        )
        return VisualAsset(
            asset_id=safe_filename(f"local_{relative_path}"),
            asset_type=asset_type,
            title=title,
            provider=self.name,
            path=relative_path,
            source_url=metadata.get("source_url"),
            source_name=metadata.get("source_name") or metadata.get("source") or "Local Library",
            license=metadata.get("license") or metadata.get("license_name") or "local-user-provided",
            usage_note=usage_note,
            attribution=metadata.get("attribution"),
            downloaded_path=relative_path,
            keywords=keywords,
            safe_to_use=safe_to_use,
            fallback_reason=metadata.get("fallback_reason"),
            width=metadata.get("width"),
            height=metadata.get("height"),
            duration_seconds=metadata.get("duration_seconds"),
            rights_tier=str(metadata.get("rights_tier") or RightsTier.GREEN.value),
            rights_confidence=str(metadata.get("rights_confidence") or RightsConfidence.VERIFIED.value),
            usage_basis=str(metadata.get("usage_basis") or UsageBasis.USER_PROVIDED.value),
            attribution_required=bool(metadata.get("attribution_required", bool(metadata.get("attribution")))),
            attribution_text=metadata.get("attribution_text"),
            source_authority=str(metadata.get("source_authority") or SourceAuthority.CREATOR.value),
            content_role=str(metadata.get("content_role") or self._content_role(asset_type)),
            media_type=str(metadata.get("media_type") or self._media_type(asset_type)),
            risk_level=str(metadata.get("risk_level") or RiskLevel.LOW.value),
            manual_review_status=str(metadata.get("manual_review_status") or ManualReviewStatus.NOT_REQUIRED.value),
            motion=dict(metadata.get("motion") or {}),
            extra={
                "rights_tier": metadata.get("rights_tier"),
                "rights_confidence": metadata.get("rights_confidence"),
                "usage_basis": metadata.get("usage_basis"),
                "source_authority": metadata.get("source_authority"),
                "content_role": metadata.get("content_role"),
                "media_type": metadata.get("media_type"),
                "risk_level": metadata.get("risk_level"),
                "manual_review_status": metadata.get("manual_review_status"),
                "motion": metadata.get("motion"),
            },
        )

    def _manifest_path(self, path: Path, public_prefix: str | None) -> str:
        if public_prefix:
            root = self.project_root / "compositor" / "remotion_renderer" / "public" / public_prefix
            return f"{public_prefix}/{path.relative_to(root).as_posix()}"
        return project_relative(path, self.project_root)

    def _sidecar_metadata(self, path: Path) -> dict[str, Any]:
        for candidate in (path.with_suffix(path.suffix + ".json"), path.with_suffix(".json")):
            if not candidate.exists():
                continue
            try:
                with candidate.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                return data if isinstance(data, dict) else {}
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _infer_type(self, path: Path, keywords: list[str], metadata: dict[str, Any]) -> AssetType:
        configured = str(metadata.get("asset_type") or "").lower()
        if configured:
            try:
                return AssetType(configured)
            except ValueError:
                pass
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            return AssetType.VIDEO
        haystack = " ".join([path.name, path.parent.name, *keywords]).lower()
        if "satellite" in haystack:
            return AssetType.SATELLITE
        if "map" in haystack:
            return AssetType.MAP
        if "chart" in haystack or "graph" in haystack:
            return AssetType.CHART
        if "screenshot" in haystack:
            return AssetType.SCREENSHOT
        if "document" in haystack or "filing" in haystack or "order" in haystack:
            return AssetType.DOCUMENT
        return AssetType.IMAGE

    def _content_role(self, asset_type: AssetType) -> str:
        if asset_type in {AssetType.MAP, AssetType.CHART, AssetType.DOCUMENT, AssetType.SCREENSHOT, AssetType.SATELLITE}:
            return ContentRole.EXPLANATION.value
        return ContentRole.CONTEXT.value

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
        if not queries:
            return True
        asset_text = " ".join([asset.title, " ".join(asset.keywords)]).lower()
        asset_words = set(tokenize(asset_text))
        for query in queries:
            query_text = " ".join([query.query, " ".join(query.keywords)]).lower()
            query_words = set(tokenize(query_text))
            if asset_words & query_words:
                return True
            if "datacenter" in asset_text and ("data center" in query_text or "data centers" in query_text):
                return True
            if "transmission" in asset_text and "grid" in query_text:
                return True
        return False

    def _trust_local_library(self) -> bool:
        return os.environ.get("SYNTHPOST_TRUST_LOCAL_VISUAL_LIBRARY", "1") != "0"
