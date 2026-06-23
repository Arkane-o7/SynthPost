from __future__ import annotations

from dataclasses import replace

from .models import AssetType, ContentRole, RightsTier, SourceAuthority, StorySegment, VisualAsset, VisualQuery
from .query_builder import tokenize

TYPE_WEIGHT = {
    AssetType.VIDEO: 42,
    AssetType.IMAGE: 30,
    AssetType.MAP: 28,
    AssetType.CHART: 27,
    AssetType.SATELLITE: 27,
    AssetType.SCREENSHOT: 25,
    AssetType.DOCUMENT: 23,
    AssetType.GENERATED: 17,
    AssetType.PLACEHOLDER: -20,
}

PROVIDER_WEIGHT = {
    "manifest_media": 28,
    "pb_shabd_dropfolder": 27,
    "pib_india": 27,
    "isro_media": 26,
    "pm_india_media": 25,
    "india_ministry_media": 24,
    "mea_india_media": 24,
    "nasa_media": 25,
    "dvids": 25,
    "eu_av": 24,
    "white_house_media": 23,
    "us_state_department_flickr": 22,
    "noaa_media": 22,
    "usgs_media": 22,
    "copernicus_data": 22,
    "official_source_media": 24,
    "local_library": 20,
    "wikimedia": 16,
    "wikimedia_commons": 16,
    "openverse": 14,
    "library_of_congress": 14,
    "nara_archives": 14,
    "internet_archive": 10,
    "natural_earth_maps": 16,
    "official_page_screenshot": 15,
    "document_screenshot": 15,
    "court_document_source": 14,
    "parliament_or_legislature_source": 14,
    "company_press_kit": 13,
    "pexels": 5,
    "pixabay": 5,
    "screenshot_provider": 3,
    "social_reference_ingest": -8,
    "social_media_leads": -25,
    "web_search": -20,
    "youtube_metadata": -20,
}

AUTHORITY_WEIGHT = {
    SourceAuthority.OFFICIAL.value: 18,
    SourceAuthority.OPEN_ARCHIVE.value: 12,
    SourceAuthority.CREATOR.value: 10,
    SourceAuthority.WIRE.value: 8,
    SourceAuthority.PLATFORM.value: -12,
    SourceAuthority.STOCK.value: -18,
    SourceAuthority.UNKNOWN.value: -30,
}


def _keyword_set(values: list[str]) -> set[str]:
    keywords: set[str] = set()
    for value in values:
        keywords.update(tokenize(value))
        keywords.add(value.lower())
    return {value for value in keywords if value}


def score_asset(asset: VisualAsset, segment: StorySegment, query: VisualQuery) -> float:
    score = 0.0
    score += TYPE_WEIGHT.get(asset.asset_type, 0)
    score += PROVIDER_WEIGHT.get(asset.provider, 0)
    score += AUTHORITY_WEIGHT.get(asset.source_authority, 0)
    if asset.rights_tier == RightsTier.GREEN.value:
        score += 28
    elif asset.rights_tier == RightsTier.YELLOW.value:
        score -= 18
    else:
        score -= 100
    if asset.safe_to_use:
        score += 18
    else:
        score -= 45
    if asset.license or asset.usage_note:
        score += 5
    if asset.attribution:
        score += 3
    if asset.fallback_reason:
        score -= 10
    if asset.provider in {"pexels", "pixabay"}:
        score -= 20
    if asset.provider in {"manifest_media", "official_source_media"}:
        score += 8
    if asset.asset_type in query.desired_types:
        score += 9
    if asset.content_role == ContentRole.EVIDENCE.value:
        score += 12
    elif asset.content_role == ContentRole.EXPLANATION.value:
        score += 7
    elif asset.content_role == ContentRole.ATMOSPHERE.value:
        score -= 14

    query_keywords = _keyword_set([segment.title, segment.text, query.query, *query.keywords])
    asset_keywords = _keyword_set([asset.title, asset.source_name or "", *(asset.keywords or [])])
    overlap = query_keywords & asset_keywords
    score += min(36, len(overlap) * 6)

    title = asset.title.lower()
    for keyword in query.keywords[:8]:
        if keyword.lower() in title:
            score += 4
        if asset.source_name and keyword.lower() in asset.source_name.lower():
            score += 2

    if asset.segment_id == segment.segment_id:
        score += 18

    return max(0.0, round(score, 2))


def rank_assets_for_segment(
    assets: list[VisualAsset],
    segment: StorySegment,
    query: VisualQuery,
) -> list[VisualAsset]:
    ranked: list[VisualAsset] = []
    for asset in assets:
        asset = replace(asset, keywords=list(asset.keywords), extra=dict(asset.extra))
        score = score_asset(asset, segment, query)
        ranked.append(asset.with_score(score, segment_id=segment.segment_id))
    return sorted(ranked, key=lambda item: item.relevance_score, reverse=True)
