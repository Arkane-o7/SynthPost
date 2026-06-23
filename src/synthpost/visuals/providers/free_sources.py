from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
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
from ..query_builder import compact_text, tokenize, unique

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}


@dataclass(frozen=True, slots=True)
class SourceProfile:
    provider: str
    source_name: str
    usage_basis: str
    source_authority: str
    rights_confidence: str = RightsConfidence.VERIFIED.value
    root_env: str | None = None


SOURCE_PROFILES = [
    SourceProfile("pb_shabd_dropfolder", "PB-SHABD / Prasar Bharati", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_PB_SHABD_MEDIA_DIR"),
    SourceProfile("pib_india", "Press Information Bureau India", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_PIB_MEDIA_DIR"),
    SourceProfile("isro_media", "ISRO", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_ISRO_MEDIA_DIR"),
    SourceProfile("pm_india_media", "PM India / PMO", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_PM_INDIA_MEDIA_DIR"),
    SourceProfile("india_ministry_media", "Government of India Ministry Media", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_INDIA_MINISTRY_MEDIA_DIR"),
    SourceProfile("mea_india_media", "MEA India", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_MEA_INDIA_MEDIA_DIR"),
    SourceProfile("nasa_media", "NASA Image and Video Library", UsageBasis.PUBLIC_DOMAIN.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_NASA_MEDIA_DIR"),
    SourceProfile("dvids", "DVIDS / U.S. Department of Defense", UsageBasis.PUBLIC_DOMAIN.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_DVIDS_MEDIA_DIR"),
    SourceProfile("eu_av", "European Commission Audiovisual Service", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_EU_AV_MEDIA_DIR"),
    SourceProfile("white_house_media", "The White House", UsageBasis.PUBLIC_DOMAIN.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_WHITE_HOUSE_MEDIA_DIR"),
    SourceProfile("us_state_department_flickr", "U.S. Department of State", UsageBasis.PUBLIC_DOMAIN.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_STATE_DEPARTMENT_MEDIA_DIR"),
    SourceProfile("noaa_media", "NOAA", UsageBasis.PUBLIC_DOMAIN.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_NOAA_MEDIA_DIR"),
    SourceProfile("usgs_media", "USGS", UsageBasis.PUBLIC_DOMAIN.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_USGS_MEDIA_DIR"),
    SourceProfile("copernicus_data", "Copernicus Data Space", UsageBasis.PUBLIC_DOMAIN.value, SourceAuthority.OFFICIAL.value, RightsConfidence.INFERRED.value, root_env="SYNTHPOST_COPERNICUS_MEDIA_DIR"),
    SourceProfile("library_of_congress", "Library of Congress", UsageBasis.PUBLIC_DOMAIN.value, SourceAuthority.OPEN_ARCHIVE.value, root_env="SYNTHPOST_LOC_MEDIA_DIR"),
    SourceProfile("nara_archives", "U.S. National Archives", UsageBasis.PUBLIC_DOMAIN.value, SourceAuthority.OPEN_ARCHIVE.value, root_env="SYNTHPOST_NARA_MEDIA_DIR"),
    SourceProfile("internet_archive", "Internet Archive", UsageBasis.CC_BY.value, SourceAuthority.OPEN_ARCHIVE.value, RightsConfidence.INFERRED.value, root_env="SYNTHPOST_INTERNET_ARCHIVE_MEDIA_DIR"),
    SourceProfile("natural_earth_maps", "Natural Earth", UsageBasis.PUBLIC_DOMAIN.value, SourceAuthority.OPEN_ARCHIVE.value, root_env="SYNTHPOST_NATURAL_EARTH_MEDIA_DIR"),
    SourceProfile("official_page_screenshot", "Official Source Screenshot", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_OFFICIAL_SCREENSHOT_DIR"),
    SourceProfile("document_screenshot", "Official Document Screenshot", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, root_env="SYNTHPOST_DOCUMENT_SCREENSHOT_DIR"),
    SourceProfile("court_document_source", "Court Document Source", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, RightsConfidence.INFERRED.value, root_env="SYNTHPOST_COURT_DOCUMENT_DIR"),
    SourceProfile("parliament_or_legislature_source", "Parliament / Legislature Source", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, RightsConfidence.INFERRED.value, root_env="SYNTHPOST_LEGISLATURE_MEDIA_DIR"),
    SourceProfile("company_press_kit", "Company Press Kit", UsageBasis.OFFICIAL_PRESS.value, SourceAuthority.OFFICIAL.value, RightsConfidence.INFERRED.value, root_env="SYNTHPOST_COMPANY_PRESS_KIT_DIR"),
]


class DropfolderSourceProvider(VisualProvider):
    def __init__(self, project_root: Path, profile: SourceProfile) -> None:
        self.project_root = project_root
        self.profile = profile
        self.name = profile.provider

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
        for root in roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.name.startswith("."):
                    continue
                if path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                    continue
                metadata = self._sidecar_metadata(path)
                asset = self._asset_from_path(path, metadata, manifest=manifest)
                if self._matches_any(asset, queries):
                    assets.append(asset)
        report.candidate_count = len(assets)
        if not assets:
            report.skipped_reason = f"No media found in {', '.join(str(root) for root in roots)}"
        return assets, report

    def _roots(self) -> list[Path]:
        roots = [
            self.project_root / "media" / "sources" / self.name,
            self.project_root / "assets" / "visuals" / self.name,
            self.project_root / "compositor" / "remotion_renderer" / "public" / "news" / self.name,
        ]
        if self.profile.root_env:
            for value in os.environ.get(self.profile.root_env, "").replace(",", os.pathsep).split(os.pathsep):
                if value.strip():
                    roots.insert(0, Path(value).expanduser())
        return roots

    def _asset_from_path(self, path: Path, metadata: dict[str, Any], *, manifest: dict[str, Any]) -> VisualAsset:
        relative_path = self._manifest_path(path)
        asset_type = self._infer_type(path, metadata)
        title = compact_text(metadata.get("title") or path.stem.replace("_", " ").replace("-", " ").title())
        source_name = compact_text(metadata.get("source_name") or metadata.get("source") or self.profile.source_name)
        attribution = compact_text(metadata.get("attribution") or metadata.get("credit"))
        usage_basis = compact_text(metadata.get("usage_basis") or self.profile.usage_basis)
        keywords = unique(
            [
                *tokenize(title),
                *tokenize(path.parent.name.replace("_", " ").replace("-", " ")),
                *self._keyword_values(metadata.get("keywords")),
            ],
            limit=24,
        )
        return VisualAsset(
            asset_id=safe_filename(f"{self.name}_{relative_path}"),
            asset_type=asset_type,
            title=title,
            provider=self.name,
            path=relative_path,
            source_url=metadata.get("source_url"),
            source_name=source_name,
            license=metadata.get("license") or usage_basis,
            usage_note=metadata.get("usage_note")
            or f"{source_name} drop-folder asset. Imported from an authenticated/manual source export; verify item-level rights.",
            attribution=attribution,
            downloaded_path=relative_path,
            story_id=str(manifest.get("story_id") or ""),
            keywords=keywords,
            safe_to_use=bool(metadata.get("safe_to_use", True)),
            width=metadata.get("width"),
            height=metadata.get("height"),
            duration_seconds=metadata.get("duration_seconds"),
            rights_tier=str(metadata.get("rights_tier") or RightsTier.GREEN.value),
            rights_confidence=str(metadata.get("rights_confidence") or self.profile.rights_confidence),
            usage_basis=usage_basis,
            attribution_required=bool(metadata.get("attribution_required", True)),
            attribution_text=metadata.get("attribution_text") or self._attribution_text(source_name, attribution),
            source_authority=str(metadata.get("source_authority") or self.profile.source_authority),
            content_role=str(metadata.get("content_role") or self._content_role(asset_type)),
            media_type=str(metadata.get("media_type") or self._media_type(asset_type)),
            risk_level=str(metadata.get("risk_level") or RiskLevel.LOW.value),
            manual_review_status=str(metadata.get("manual_review_status") or ManualReviewStatus.NOT_REQUIRED.value),
            motion=dict(metadata.get("motion") or {}),
            extra={
                "visual_role": metadata.get("visual_role") or self._media_type(asset_type),
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

    def _manifest_path(self, path: Path) -> str:
        public_news = self.project_root / "compositor" / "remotion_renderer" / "public" / "news"
        try:
            return f"news/{path.relative_to(public_news).as_posix()}"
        except ValueError:
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

    def _infer_type(self, path: Path, metadata: dict[str, Any]) -> AssetType:
        configured = compact_text(metadata.get("asset_type") or metadata.get("media_type")).lower()
        aliases = {"photo": "image", "stock": "image"}
        configured = aliases.get(configured, configured)
        if configured:
            try:
                return AssetType(configured)
            except ValueError:
                pass
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            return AssetType.VIDEO
        haystack = f"{path.name} {path.parent.name}".lower()
        if "satellite" in haystack:
            return AssetType.SATELLITE
        if "map" in haystack:
            return AssetType.MAP
        if "chart" in haystack or "graph" in haystack:
            return AssetType.CHART
        if "document" in haystack or "filing" in haystack or "pdf" in haystack:
            return AssetType.DOCUMENT
        if "screenshot" in haystack:
            return AssetType.SCREENSHOT
        return AssetType.IMAGE

    def _matches_any(self, asset: VisualAsset, queries: list[VisualQuery]) -> bool:
        if not queries:
            return True
        asset_words = set(tokenize(" ".join([asset.title, asset.source_name or "", " ".join(asset.keywords)])))
        if not asset_words:
            return True
        for query in queries:
            query_words = set(tokenize(" ".join([query.query, " ".join(query.keywords)])))
            if asset_words & query_words:
                return True
        return False

    def _content_role(self, asset_type: AssetType) -> str:
        if asset_type in {AssetType.MAP, AssetType.CHART, AssetType.DOCUMENT, AssetType.SCREENSHOT, AssetType.SATELLITE}:
            return ContentRole.EXPLANATION.value
        return ContentRole.EVIDENCE.value

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

    def _attribution_text(self, source_name: str, attribution: str) -> str:
        return f"Source: {source_name} / {attribution}" if attribution else f"Source: {source_name}"

    def _keyword_values(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return tokenize(value)
        if isinstance(value, list):
            return [compact_text(item) for item in value if compact_text(item)]
        return []


class OpenverseProvider(VisualProvider):
    name = "openverse"

    def __init__(self, project_root: Path, *, per_query: int = 3) -> None:
        self.project_root = project_root
        self.per_query = per_query

    def search(
        self,
        *,
        manifest: dict[str, Any],
        story_json_path: Path,
        segments: list[StorySegment],
        queries: list[VisualQuery],
    ) -> tuple[list[VisualAsset], ProviderReport]:
        if os.environ.get("SYNTHPOST_DISABLE_WEB_VISUALS", "0") == "1":
            return [], ProviderReport(provider=self.name, skipped_reason="SYNTHPOST_DISABLE_WEB_VISUALS=1")
        report = ProviderReport(provider=self.name, query_count=len(queries))
        assets: list[VisualAsset] = []
        seen: set[str] = set()
        for query in queries:
            try:
                results = self._search(query.query)
            except Exception as exc:  # noqa: BLE001
                report.warnings.append(f"{query.query}: {exc}")
                continue
            for item in results:
                url = str(item.get("url") or "")
                if not url or url in seen:
                    continue
                seen.add(url)
                license_name = compact_text(item.get("license") or "open-license")
                assets.append(
                    VisualAsset(
                        asset_id=safe_filename(f"openverse_{item.get('id') or len(assets) + 1}"),
                        asset_type=AssetType.IMAGE,
                        title=compact_text(item.get("title") or "Openverse image"),
                        provider=self.name,
                        remote_url=url,
                        source_url=item.get("foreign_landing_url") or item.get("url"),
                        source_name=compact_text(item.get("source") or "Openverse"),
                        license=license_name,
                        usage_note="Openverse discovery result. Verify license on original asset page before upload.",
                        attribution=compact_text(item.get("creator")),
                        keywords=query.keywords,
                        safe_to_use=True,
                        width=item.get("width"),
                        height=item.get("height"),
                        rights_tier=RightsTier.GREEN.value,
                        rights_confidence=RightsConfidence.INFERRED.value,
                        usage_basis=self._usage_basis(license_name),
                        attribution_required=license_name.lower() not in {"cc0", "pdm", "publicdomain"},
                        source_authority=SourceAuthority.OPEN_ARCHIVE.value,
                        content_role=ContentRole.CONTEXT.value,
                        media_type=MediaType.PHOTO.value,
                        risk_level=RiskLevel.LOW.value,
                        manual_review_status=ManualReviewStatus.NOT_REQUIRED.value,
                    )
                )
        report.candidate_count = len(assets)
        return assets, report

    def _search(self, query: str) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode({"q": query, "page_size": self.per_query, "license_type": "commercial"})
        request = urllib.request.Request(
            f"https://api.openverse.org/v1/images/?{params}",
            headers={"User-Agent": "SynthPostVisuals/0.1"},
        )
        with urllib.request.urlopen(request, timeout=18) as response:
            data = json.loads(response.read().decode("utf-8"))
        return list(data.get("results") or [])[: self.per_query]

    def _usage_basis(self, license_name: str) -> str:
        lowered = license_name.lower()
        if "cc0" in lowered or lowered == "pdm":
            return UsageBasis.CC0.value
        if "by-sa" in lowered:
            return UsageBasis.CC_BY_SA.value
        return UsageBasis.CC_BY.value


class SocialMediaLeadsProvider(VisualProvider):
    name = "social_media_leads"

    def search(
        self,
        *,
        manifest: dict[str, Any],
        story_json_path: Path,
        segments: list[StorySegment],
        queries: list[VisualQuery],
    ) -> tuple[list[VisualAsset], ProviderReport]:
        raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
        records = _as_records(raw.get("social_posts")) + _as_records(raw.get("social_urls"))
        report = ProviderReport(provider=self.name, query_count=len(queries))
        assets: list[VisualAsset] = []
        for index, record in enumerate(records):
            url = compact_text(record.get("url") or record.get("source_url"))
            if not url:
                continue
            assets.append(
                VisualAsset(
                    asset_id=safe_filename(f"social_lead_{index + 1:02d}"),
                    asset_type=AssetType.PLACEHOLDER,
                    title=compact_text(record.get("title") or record.get("text") or f"Social media lead {index + 1}"),
                    provider=self.name,
                    source_url=url,
                    source_name=compact_text(record.get("platform") or _host(url) or "Social media"),
                    usage_note="Social media discovery lead only. Not renderable until rights/permission/review is recorded.",
                    story_id=str(manifest.get("story_id") or ""),
                    keywords=_keyword_values(record.get("keywords")),
                    safe_to_use=False,
                    fallback_reason="manual_review_required",
                    rights_tier=RightsTier.YELLOW.value,
                    rights_confidence=RightsConfidence.UNKNOWN.value,
                    usage_basis=UsageBasis.EDITORIAL_REVIEW.value,
                    attribution_required=True,
                    attribution_text=compact_text(record.get("attribution_text") or record.get("creator") or record.get("handle")),
                    source_authority=SourceAuthority.PLATFORM.value,
                    content_role=ContentRole.CONTEXT.value,
                    media_type=MediaType.SCREENSHOT.value,
                    risk_level=RiskLevel.MEDIUM.value,
                    manual_review_status=ManualReviewStatus.REQUIRED.value,
                )
            )
        report.candidate_count = len(assets)
        if not assets:
            report.skipped_reason = "No raw.social_posts/raw.social_urls in manifest"
        return assets, report


class SocialReferenceIngestProvider(VisualProvider):
    name = "social_reference_ingest"

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
        records = _as_records(raw.get("social_media_assets")) + _as_records(raw.get("approved_social_media"))
        report = ProviderReport(provider=self.name, query_count=len(queries))
        assets: list[VisualAsset] = []
        for index, record in enumerate(records):
            value = compact_text(record.get("path") or record.get("downloaded_path") or record.get("remote_url") or record.get("url"))
            if not value:
                continue
            is_remote = value.startswith(("http://", "https://"))
            ext = Path(urllib.parse.urlparse(value).path if is_remote else value).suffix.lower()
            if ext and ext not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                continue
            asset_type = AssetType.VIDEO if ext in VIDEO_EXTENSIONS else AssetType.SCREENSHOT
            approved = compact_text(record.get("manual_review_status")) == ManualReviewStatus.APPROVED.value
            assets.append(
                VisualAsset(
                    asset_id=safe_filename(str(record.get("asset_id") or f"social_ref_{index + 1:02d}")),
                    asset_type=asset_type,
                    title=compact_text(record.get("title") or f"Approved social reference {index + 1}"),
                    provider=self.name,
                    path=None if is_remote else value,
                    remote_url=value if is_remote else None,
                    source_url=record.get("source_url") or record.get("post_url") or value,
                    source_name=compact_text(record.get("platform") or _host(str(record.get("source_url") or value)) or "Social media"),
                    license=record.get("license") or UsageBasis.EDITORIAL_REVIEW.value,
                    usage_note=record.get("usage_note") or "Manually reviewed social reference. Keep approval/permission record with story audit.",
                    attribution=compact_text(record.get("creator") or record.get("handle")),
                    downloaded_path=record.get("downloaded_path") or record.get("path"),
                    story_id=str(manifest.get("story_id") or ""),
                    keywords=_keyword_values(record.get("keywords")),
                    safe_to_use=approved,
                    rights_tier=RightsTier.YELLOW.value,
                    rights_confidence=RightsConfidence.VERIFIED.value if approved else RightsConfidence.UNKNOWN.value,
                    usage_basis=UsageBasis.EDITORIAL_REVIEW.value,
                    attribution_required=True,
                    attribution_text=record.get("attribution_text") or compact_text(record.get("creator") or record.get("handle")),
                    source_authority=SourceAuthority.PLATFORM.value,
                    content_role=ContentRole.CONTEXT.value,
                    media_type=MediaType.VIDEO.value if asset_type == AssetType.VIDEO else MediaType.SCREENSHOT.value,
                    risk_level=RiskLevel.MEDIUM.value,
                    manual_review_status=ManualReviewStatus.APPROVED.value if approved else ManualReviewStatus.REQUIRED.value,
                    extra={"muted_by_policy": True, "max_clip_seconds": record.get("max_clip_seconds", 7)},
                )
            )
        report.candidate_count = len(assets)
        if not assets:
            report.skipped_reason = "No raw.social_media_assets/raw.approved_social_media in manifest"
        return assets, report


def free_source_providers(project_root: Path) -> list[VisualProvider]:
    providers: list[VisualProvider] = [DropfolderSourceProvider(project_root, profile) for profile in SOURCE_PROFILES]
    providers.append(OpenverseProvider(project_root))
    providers.extend([SocialMediaLeadsProvider(), SocialReferenceIngestProvider(project_root)])
    return providers


def _as_records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    records: list[dict[str, Any]] = []
    for item in values:
        if isinstance(item, str):
            records.append({"url": item})
        elif isinstance(item, dict):
            records.append(item)
    return records


def _keyword_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return tokenize(value)
    if isinstance(value, list):
        return [compact_text(item) for item in value if compact_text(item)]
    return []


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").removeprefix("www.")
    except ValueError:
        return ""
