from __future__ import annotations

from dataclasses import replace

from .models import AssetType, ContentRole, RightsTier, SelectionStatus, SourceAuthority, StorySegment, VisualAsset, VisualQuery
from .query_builder import tokenize

LOGO_TERMS = {"logo", "wordmark", "favicon", "brandmark"}
GENERIC_SPACE_TERMS = {"stars", "starfield", "galaxy", "nebula", "skywatching", "solar-system", "solar_system"}
SPACE_STORY_TERMS = {"space", "orbit", "orbital", "moon", "mars", "asteroid", "telescope", "galaxy", "stars", "skywatching", "satellite"}

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


def _asset_text(asset: VisualAsset) -> str:
    return " ".join(
        str(value or "")
        for value in [
            asset.title,
            asset.caption,
            asset.alt_text,
            asset.source_name,
            asset.source_url,
            asset.remote_url,
            asset.path,
            " ".join(asset.keywords or []),
            " ".join(asset.entities or []),
        ]
    ).lower()


def _story_match_keywords(asset: VisualAsset) -> set[str]:
    return _keyword_set(
        [
            asset.title,
            asset.caption or "",
            asset.alt_text or "",
            asset.source_url or "",
            asset.remote_url or "",
            asset.path or "",
            *(asset.keywords or []),
            *(asset.entities or []),
        ]
    )


def hard_rejection_reasons(asset: VisualAsset, segment: StorySegment, query: VisualQuery) -> list[str]:
    text = _asset_text(asset)
    tokens = set(tokenize(text))
    reasons: list[str] = []
    query_text = f"{segment.title} {segment.text} {query.query} {' '.join(query.keywords)}".lower()
    query_tokens = set(tokenize(query_text))
    if tokens & LOGO_TERMS or any(term in text for term in LOGO_TERMS):
        reasons.append("publisher_logo_rejected")
    if (tokens & GENERIC_SPACE_TERMS or any(term in text for term in GENERIC_SPACE_TERMS)) and not (query_tokens & SPACE_STORY_TERMS):
        reasons.append("generic_space_media_rejected_for_non_space_story")
    if (
        asset.asset_type not in {AssetType.GENERATED, AssetType.PLACEHOLDER}
        and asset.provider not in {"pexels", "pixabay"}
        and not (_story_match_keywords(asset) & _keyword_set([segment.title, segment.text, query.query, *query.keywords]))
    ):
        reasons.append("unrelated_to_current_story")
    return reasons


def score_asset(asset: VisualAsset, segment: StorySegment, query: VisualQuery) -> float:
    if hard_rejection_reasons(asset, segment, query):
        return 0.0
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
    asset_keywords = _keyword_set(
        [
            asset.title,
            asset.caption or "",
            asset.alt_text or "",
            asset.source_name or "",
            asset.source_domain or "",
            *(asset.keywords or []),
            *(asset.entities or []),
        ]
    )
    overlap = query_keywords & asset_keywords
    score += min(36, len(overlap) * 6)
    story_entities = _keyword_set(query.keywords)
    matched_entities = story_entities & asset_keywords
    score += min(24, len(matched_entities) * 8)

    title = asset.title.lower()
    for keyword in query.keywords[:8]:
        if keyword.lower() in title:
            score += 4
        if asset.source_name and keyword.lower() in asset.source_name.lower():
            score += 2

    if asset.segment_id == segment.segment_id:
        score += 18

    return max(0.0, round(score, 2))


def relevance_reason(asset: VisualAsset, segment: StorySegment, query: VisualQuery, score: float) -> str:
    if asset.rejection_reasons:
        return "; ".join(asset.rejection_reasons)
    query_keywords = _keyword_set([segment.title, segment.text, query.query, *query.keywords])
    asset_keywords = _keyword_set([asset.title, asset.caption or "", asset.alt_text or "", asset.source_name or "", *(asset.keywords or []), *(asset.entities or [])])
    overlap = sorted(query_keywords & asset_keywords)[:6]
    parts = [
        f"{asset.asset_type.value} from {asset.provider}",
        f"score={score:.2f}",
    ]
    if overlap:
        parts.append(f"matched terms: {', '.join(overlap)}")
    if asset.safe_to_use:
        parts.append("rights-safe")
    else:
        parts.append("not auto-selectable")
    return "; ".join(parts)


def rank_assets_for_segment(
    assets: list[VisualAsset],
    segment: StorySegment,
    query: VisualQuery,
) -> list[VisualAsset]:
    ranked: list[VisualAsset] = []
    for asset in assets:
        asset = replace(
            asset,
            keywords=list(asset.keywords),
            entities=list(asset.entities),
            matched_story_entities=list(asset.matched_story_entities),
            rejection_reasons=list(asset.rejection_reasons),
            extra=dict(asset.extra),
        )
        rejection_reasons = hard_rejection_reasons(asset, segment, query)
        score = score_asset(asset, segment, query)
        asset.rejection_reasons = rejection_reasons
        if rejection_reasons:
            asset.selection_status = SelectionStatus.REJECTED.value
        query_keywords = _keyword_set([*query.keywords, query.query])
        asset_keywords = _keyword_set([asset.title, asset.caption or "", asset.alt_text or "", asset.source_name or "", *(asset.keywords or []), *(asset.entities or [])])
        asset.matched_story_entities = sorted(query_keywords & asset_keywords)[:12]
        asset.relevance_reason = relevance_reason(asset, segment, query, score)
        ranked.append(asset.with_score(score, segment_id=segment.segment_id))
    return sorted(ranked, key=lambda item: item.relevance_score, reverse=True)
