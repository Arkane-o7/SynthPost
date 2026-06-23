from __future__ import annotations

import os
from typing import Any

from .models import (
    AssetType,
    ContentRole,
    ManualReviewStatus,
    MediaType,
    RightsConfidence,
    RightsTier,
    RiskLevel,
    SourceAuthority,
    UsageBasis,
    VisualAsset,
)

OFFICIAL_PROVIDERS = {
    "pb_shabd_dropfolder",
    "pib_india",
    "isro_media",
    "pm_india_media",
    "india_ministry_media",
    "mea_india_media",
    "nasa_media",
    "dvids",
    "eu_av",
    "white_house_media",
    "us_state_department_flickr",
    "noaa_media",
    "usgs_media",
    "copernicus_data",
    "official_source_media",
    "official_page_screenshot",
    "document_screenshot",
    "court_document_source",
    "parliament_or_legislature_source",
    "company_press_kit",
}

OPEN_ARCHIVE_PROVIDERS = {
    "wikimedia",
    "wikimedia_commons",
    "openverse",
    "library_of_congress",
    "nara_archives",
    "internet_archive",
    "natural_earth_maps",
}

STOCK_PROVIDERS = {"pexels", "pixabay", "pexels_pixabay_optional"}
SOCIAL_PROVIDERS = {"social_media_leads", "social_reference_ingest", "youtube_metadata"}
GENERATED_PROVIDERS = {"screenshot_provider"}
CC_USAGE = {UsageBasis.CC0.value, UsageBasis.CC_BY.value, UsageBasis.CC_BY_SA.value}


def normalize_asset_metadata(asset: VisualAsset) -> VisualAsset:
    asset.media_type = _value(asset.extra.get("media_type"), _media_type(asset), asset.media_type)
    asset.source_authority = _value(
        asset.extra.get("source_authority"),
        asset.source_authority if asset.source_authority != SourceAuthority.UNKNOWN.value else None,
        _source_authority(asset.provider),
        asset.source_authority,
    )
    asset.usage_basis = _value(asset.extra.get("usage_basis"), asset.usage_basis, _usage_basis(asset))
    asset.rights_tier = _value(
        asset.extra.get("rights_tier"),
        asset.rights_tier if asset.rights_tier != RightsTier.RED.value else None,
        _rights_tier(asset),
        asset.rights_tier,
    )
    asset.rights_confidence = _value(
        asset.extra.get("rights_confidence"),
        asset.rights_confidence if asset.rights_confidence != RightsConfidence.UNKNOWN.value else None,
        _rights_confidence(asset),
        asset.rights_confidence,
    )
    asset.content_role = _value(
        asset.extra.get("content_role"),
        asset.content_role if asset.content_role != ContentRole.CONTEXT.value else None,
        _content_role(asset),
    )
    asset.risk_level = _value(
        asset.extra.get("risk_level"),
        asset.risk_level if asset.risk_level != RiskLevel.HIGH.value else None,
        _risk_level(asset),
    )
    asset.manual_review_status = _value(
        asset.extra.get("manual_review_status"),
        asset.manual_review_status if asset.manual_review_status != ManualReviewStatus.REQUIRED.value else None,
        _manual_review_status(asset),
        asset.manual_review_status,
    )
    asset.attribution_required = bool(
        asset.extra.get("attribution_required", asset.attribution_required or _attribution_required(asset))
    )
    asset.attribution_text = _value(asset.attribution_text, asset.extra.get("attribution_text"), _attribution_text(asset))
    if not asset.motion:
        asset.motion = dict(asset.extra.get("motion") or default_motion(asset))
    asset.safe_to_use = asset_is_selectable(asset)
    return asset


def asset_is_selectable(asset: VisualAsset) -> bool:
    if asset.rights_tier == RightsTier.RED.value:
        return False
    if asset.manual_review_status == ManualReviewStatus.REJECTED.value:
        return False
    if asset.rights_tier == RightsTier.YELLOW.value:
        if asset.manual_review_status != ManualReviewStatus.APPROVED.value:
            return False
        if asset.source_authority == SourceAuthority.PLATFORM.value:
            return os.environ.get("SYNTHPOST_ALLOW_RISKY_SOCIAL", "0") == "1"
        return os.environ.get("SYNTHPOST_ALLOW_YELLOW_VISUALS", "0") == "1"
    return asset.rights_tier == RightsTier.GREEN.value


def default_motion(asset: VisualAsset) -> dict[str, Any]:
    if asset.asset_type == AssetType.VIDEO:
        return {}
    presets = {
        MediaType.PHOTO.value: ("push_in", 0.3),
        MediaType.SCREENSHOT.value: ("screenshot_focus", 0.32),
        MediaType.DOCUMENT.value: ("document_scan", 0.42),
        MediaType.MAP.value: ("map_zoom", 0.42),
        MediaType.CHART.value: ("chart_reveal", 0.36),
        MediaType.SATELLITE.value: ("map_zoom", 0.38),
        MediaType.STOCK.value: ("pan_left", 0.22),
    }
    preset, intensity = presets.get(asset.media_type or "", ("push_in", 0.28))
    return {"preset": preset, "intensity": intensity, "focus": [0.5, 0.5]}


def _value(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            if hasattr(value, "value"):
                return value.value
            return value
    return None


def _media_type(asset: VisualAsset) -> str:
    if asset.provider in STOCK_PROVIDERS:
        return MediaType.STOCK.value
    return {
        AssetType.VIDEO: MediaType.VIDEO.value,
        AssetType.IMAGE: MediaType.PHOTO.value,
        AssetType.SCREENSHOT: MediaType.SCREENSHOT.value,
        AssetType.DOCUMENT: MediaType.DOCUMENT.value,
        AssetType.MAP: MediaType.MAP.value,
        AssetType.CHART: MediaType.CHART.value,
        AssetType.SATELLITE: MediaType.SATELLITE.value,
        AssetType.GENERATED: MediaType.SCREENSHOT.value,
    }.get(asset.asset_type, MediaType.PHOTO.value)


def _source_authority(provider: str) -> str:
    if provider in OFFICIAL_PROVIDERS:
        return SourceAuthority.OFFICIAL.value
    if provider in OPEN_ARCHIVE_PROVIDERS:
        return SourceAuthority.OPEN_ARCHIVE.value
    if provider in STOCK_PROVIDERS:
        return SourceAuthority.STOCK.value
    if provider in SOCIAL_PROVIDERS:
        return SourceAuthority.PLATFORM.value
    if provider in GENERATED_PROVIDERS:
        return SourceAuthority.CREATOR.value
    if provider in {"local_library", "manifest_media"}:
        return SourceAuthority.CREATOR.value
    return SourceAuthority.UNKNOWN.value


def _usage_basis(asset: VisualAsset) -> str:
    rights_text = f"{asset.license or ''} {asset.usage_note or ''}".lower()
    if asset.provider in STOCK_PROVIDERS:
        return UsageBasis.STOCK_FALLBACK.value
    if "cc0" in rights_text or "public domain mark" in rights_text:
        return UsageBasis.CC0.value
    if "cc-by-sa" in rights_text or "cc by-sa" in rights_text or "cc by sa" in rights_text:
        return UsageBasis.CC_BY_SA.value
    if "cc-by" in rights_text or "cc by" in rights_text or "creative commons attribution" in rights_text:
        return UsageBasis.CC_BY.value
    if "public domain" in rights_text or "government work" in rights_text:
        return UsageBasis.PUBLIC_DOMAIN.value
    if asset.provider in OFFICIAL_PROVIDERS:
        return UsageBasis.OFFICIAL_PRESS.value
    if asset.provider in GENERATED_PROVIDERS:
        return UsageBasis.USER_PROVIDED.value
    if asset.provider in {"local_library", "manifest_media"}:
        return UsageBasis.USER_PROVIDED.value
    if asset.provider in SOCIAL_PROVIDERS:
        return UsageBasis.EDITORIAL_REVIEW.value
    return UsageBasis.USER_PROVIDED.value if asset.path else None


def _rights_tier(asset: VisualAsset) -> str:
    if asset.provider in SOCIAL_PROVIDERS:
        return RightsTier.YELLOW.value
    if asset.provider in STOCK_PROVIDERS:
        return RightsTier.GREEN.value
    if asset.provider in GENERATED_PROVIDERS:
        return RightsTier.GREEN.value
    if asset.provider in OFFICIAL_PROVIDERS | OPEN_ARCHIVE_PROVIDERS | {"local_library", "manifest_media"}:
        return RightsTier.GREEN.value if asset.safe_to_use else RightsTier.RED.value
    return RightsTier.RED.value


def _rights_confidence(asset: VisualAsset) -> str:
    if asset.provider in {"manifest_media", "local_library"}:
        return RightsConfidence.VERIFIED.value if asset.safe_to_use else RightsConfidence.UNKNOWN.value
    if asset.provider in GENERATED_PROVIDERS:
        return RightsConfidence.VERIFIED.value
    if asset.provider in OFFICIAL_PROVIDERS:
        return RightsConfidence.VERIFIED.value
    if asset.provider in OPEN_ARCHIVE_PROVIDERS | STOCK_PROVIDERS | SOCIAL_PROVIDERS:
        return RightsConfidence.INFERRED.value
    return RightsConfidence.UNKNOWN.value


def _content_role(asset: VisualAsset) -> str:
    if asset.provider in STOCK_PROVIDERS:
        return ContentRole.ATMOSPHERE.value
    if asset.media_type in {MediaType.DOCUMENT.value, MediaType.MAP.value, MediaType.CHART.value, MediaType.SCREENSHOT.value}:
        return ContentRole.EXPLANATION.value
    if asset.provider in OFFICIAL_PROVIDERS or asset.asset_type == AssetType.VIDEO:
        return ContentRole.EVIDENCE.value
    return ContentRole.CONTEXT.value


def _risk_level(asset: VisualAsset) -> str:
    if asset.rights_tier == RightsTier.GREEN.value:
        return RiskLevel.LOW.value
    if asset.rights_tier == RightsTier.YELLOW.value:
        return RiskLevel.MEDIUM.value
    return RiskLevel.HIGH.value


def _manual_review_status(asset: VisualAsset) -> str:
    if asset.rights_tier == RightsTier.YELLOW.value:
        return ManualReviewStatus.REQUIRED.value
    if asset.rights_tier == RightsTier.GREEN.value:
        return ManualReviewStatus.NOT_REQUIRED.value
    return ManualReviewStatus.REJECTED.value


def _attribution_required(asset: VisualAsset) -> bool:
    if asset.attribution:
        return True
    if asset.source_authority in {SourceAuthority.OFFICIAL.value, SourceAuthority.OPEN_ARCHIVE.value}:
        return True
    return asset.usage_basis in CC_USAGE


def _attribution_text(asset: VisualAsset) -> str | None:
    if asset.attribution:
        source = asset.source_name or asset.provider
        return f"Source: {source} / {asset.attribution}"
    if asset.source_name:
        return f"Source: {asset.source_name}"
    return None
