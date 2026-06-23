from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import PROJECT_ROOT, ThumbnailAsset, ThumbnailBrief


ASSET_LIBRARY_PATH = PROJECT_ROOT / "assets" / "thumbnails" / "asset_library.json"
GENERATED_ASSET_DIR = PROJECT_ROOT / "assets" / "thumbnails" / "generated"

ASSET_GROUPS = {
    "person_image": "person_images",
    "logo": "logos",
    "background_image": "background_images",
    "generated_background": "background_images",
    "map": "maps",
    "screenshot": "screenshots",
    "document": "documents",
    "object": "objects",
    "icon": "objects",
    "hero_composite": "objects",
    "foreground_composite": "objects",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass
class AssetMatch:
    asset: ThumbnailAsset
    score: int
    reasons: list[str]
    relevance_score: float = 0.0
    reject_reason: str | None = None


def brief_asset_groups(assets: list[ThumbnailAsset]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {
        "person_images": [],
        "logos": [],
        "background_images": [],
        "maps": [],
        "screenshots": [],
        "documents": [],
        "objects": [],
    }
    for asset in assets:
        group = ASSET_GROUPS.get(asset.type, "objects")
        groups[group].append(asset.to_record())
    return groups


def load_asset_library(path: str | Path | None = None) -> list[ThumbnailAsset]:
    library_path = Path(path) if path else ASSET_LIBRARY_PATH
    assets: list[ThumbnailAsset] = []
    if library_path.exists():
        with library_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            records = data.get("assets", [])
        elif isinstance(data, list):
            records = data
        else:
            records = []
        for record in records:
            if isinstance(record, dict):
                assets.append(ThumbnailAsset.from_record(record))
    assets.extend(_scan_generated_assets())
    return _dedupe_assets(assets)


def select_assets_for_brief(
    brief: ThumbnailBrief,
    *,
    library_path: str | Path | None = None,
    max_assets: int = 2,
    require_approved: bool = True,
) -> list[AssetMatch]:
    existing_ids = {asset.id for asset in brief.assets}
    candidates = [
        asset
        for asset in load_asset_library(library_path)
        if asset.id not in existing_ids
        and asset.usage_status != "do_not_use"
        and (not require_approved or asset.usage_status == "approved")
    ]
    matches = [score_asset_for_brief(brief, asset) for asset in candidates]
    useful = [match for match in matches if _is_useful_library_match(match)]
    useful.sort(key=lambda match: (match.score, _asset_priority(match.asset)), reverse=True)
    return useful[:max_assets]


def resolve_brief_assets(brief: ThumbnailBrief, *, library_path: str | Path | None = None) -> tuple[ThumbnailBrief, list[AssetMatch]]:
    has_story_image = any(
        asset.id.startswith("story_visual_")
        and asset.type in {"background_image", "generated_background", "map", "screenshot"}
        and asset.usage_status == "approved"
        for asset in brief.assets
    )
    if has_story_image:
        return brief, []
    if _has_only_generic_subjects(brief):
        return brief, []

    has_foreground = any(asset.type in {"hero_composite", "foreground_composite", "person_image", "object"} for asset in brief.assets)
    max_assets = 1 if has_foreground else 2
    matches = select_assets_for_brief(brief, library_path=library_path, max_assets=max_assets)
    if matches:
        brief.assets = [*brief.assets, *(match.asset for match in matches)]
    return brief, matches


def library_asset_candidate_records(
    brief: ThumbnailBrief,
    *,
    library_path: str | Path | None = None,
    selected: list[AssetMatch] | None = None,
    limit: int = 24,
) -> list[dict[str, Any]]:
    selected_ids = {match.asset.id for match in selected or []}
    existing_ids = {asset.id for asset in brief.assets}
    candidates = [
        asset
        for asset in load_asset_library(library_path)
        if asset.id not in existing_ids and asset.usage_status != "do_not_use"
    ]
    matches = [score_asset_for_brief(brief, asset) for asset in candidates]
    matches.sort(key=lambda match: (match.asset.id not in selected_ids, -match.score, match.asset.id))
    records: list[dict[str, Any]] = []
    for match in matches[:limit]:
        accepted = match.asset.id in selected_ids
        reject_reason = None if accepted else match.reject_reason or _library_reject_reason(match)
        records.append(
            {
                key: value
                for key, value in {
                    "asset_id": match.asset.id,
                    "source": "asset_library",
                    "path_or_url": match.asset.path_or_url,
                    "type": match.asset.type,
                    "subject": match.asset.subject_name,
                    "label": match.asset.label,
                    "raw_score": match.score,
                    "relevance_score": match.relevance_score,
                    "accepted": accepted,
                    "reject_reason": reject_reason,
                    "reasons": match.reasons,
                }.items()
                if value not in (None, "", [], {})
            }
        )
    return records


def write_resolved_brief_record(brief: ThumbnailBrief, path: str | Path, *, selected: list[AssetMatch] | None = None) -> Path:
    output_path = Path(path)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "brief_id": brief.brief_id,
        "video_title": brief.video_title,
        "episode_headline": brief.episode_headline,
        "topic": brief.topic,
        "main_subjects": [subject.to_record() for subject in brief.main_subjects],
        "story_angle": brief.story_angle,
        "emotion": brief.emotion,
        "stakes": brief.stakes,
        "curiosity_gap": brief.curiosity_gap,
        "key_numbers": brief.key_numbers,
        "approved_thumbnail_text": brief.approved_thumbnail_text,
        "forbidden_thumbnail_text": brief.forbidden_thumbnail_text,
        "assets": brief_asset_groups(brief.assets),
        "render_preferences": brief.render_preferences,
        "compliance": {
            "must_use_only_approved_assets": False,
            "requires_human_review": True,
            "notes": "Auto-resolved by SynthPost thumbnail asset selector.",
        },
    }
    payload = {key: value for key, value in payload.items() if value not in (None, "", [], {})}
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    return output_path


def _scan_generated_assets() -> list[ThumbnailAsset]:
    if not GENERATED_ASSET_DIR.exists():
        return []
    assets: list[ThumbnailAsset] = []
    for path in GENERATED_ASSET_DIR.rglob("*.png"):
        if path.name.endswith("_chromakey.png"):
            continue
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        stem = path.stem.lower()
        assets.append(
            ThumbnailAsset(
                id=f"generated_{_slug(path.parent.name)}_{_slug(path.stem)}",
                path_or_url=rel,
                type="hero_composite",
                subject_name=stem.replace("_", " "),
                usage_status="approved",
                license="AI-generated project asset",
                label="Auto-discovered generated composite",
            )
        )
    return assets


def score_asset_for_brief(brief: ThumbnailBrief, asset: ThumbnailAsset) -> AssetMatch:
    haystack = " ".join(
        str(value)
        for value in [
            asset.id,
            asset.path_or_url,
            asset.type,
            asset.subject_name,
            asset.label,
        ]
        if value
    ).lower()
    topic = brief.topic.lower()
    subject_terms = [_slug(subject.name).replace("-", " ") for subject in brief.main_subjects]
    haystack_tokens = set(_tokens(haystack))
    query_terms = set(_tokens(" ".join([brief.video_title, brief.episode_headline, brief.story_angle, topic])))
    score = 0
    reasons: list[str] = []

    if topic and topic in haystack_tokens:
        score += 8
        reasons.append(f"topic:{topic}")
    for term in subject_terms:
        term_tokens = set(_tokens(term))
        if term and term in haystack:
            score += 10
            reasons.append(f"subject:{term}")
        elif term_tokens and term_tokens.issubset(haystack_tokens):
            score += 8
            reasons.append(f"subject_tokens:{term}")
    for token in query_terms:
        if len(token) > 2 and token in haystack_tokens:
            score += 2
            if len(reasons) < 5:
                reasons.append(f"keyword:{token}")
    if asset.type in {"hero_composite", "foreground_composite"}:
        score += 5
        reasons.append("foreground_composite")
    if asset.usage_status == "approved":
        score += 3
    if _is_branding_asset(asset):
        score -= 30
        reasons.append("reject:publisher_logo_or_branding")
    if _is_generic_space_asset(asset) and not _story_is_space_related(brief):
        score -= 24
        reasons.append("reject:generic_space_asset")
    if not _asset_exists(asset):
        score -= 20
        reasons.append("missing_file")
    reject_reason = _library_reject_reason(AssetMatch(asset=asset, score=score, reasons=reasons))
    return AssetMatch(
        asset=asset,
        score=score,
        reasons=reasons,
        relevance_score=_normalized_relevance(score),
        reject_reason=reject_reason,
    )


def _is_useful_library_match(match: AssetMatch) -> bool:
    if match.reject_reason:
        return False
    if match.score < 18:
        return False
    strong_reasons = [
        reason
        for reason in match.reasons
        if reason.startswith(("subject:", "subject_tokens:", "topic:", "keyword:"))
    ]
    return len(strong_reasons) >= 2


def _library_reject_reason(match: AssetMatch) -> str | None:
    if any(reason.startswith("reject:publisher_logo") for reason in match.reasons):
        return "publisher logo or source branding, not a story visual"
    if any(reason.startswith("reject:generic_space") for reason in match.reasons):
        return "generic space image unrelated to current story entities"
    if "missing_file" in match.reasons:
        return "asset file is missing"
    if match.score < 18:
        return "low match to current story headline, topic, and entities"
    strong_reasons = [
        reason
        for reason in match.reasons
        if reason.startswith(("subject:", "subject_tokens:", "topic:", "keyword:"))
    ]
    if len(strong_reasons) < 2:
        return "insufficient story-specific match"
    return None


def _asset_exists(asset: ThumbnailAsset) -> bool:
    value = asset.path_or_url
    if value.startswith(("http://", "https://", "generated://", "symbolic://")):
        return True
    path = Path(value)
    return (path if path.is_absolute() else PROJECT_ROOT / path).exists()


def _asset_priority(asset: ThumbnailAsset) -> int:
    if asset.type in {"hero_composite", "foreground_composite"}:
        return 3
    if asset.type in {"person_image", "object"}:
        return 2
    return 1


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.lower()) if token not in STOPWORDS]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "asset"


def _normalized_relevance(score: int) -> float:
    return round(max(0.0, min(score / 40.0, 1.0)), 2)


def _is_branding_asset(asset: ThumbnailAsset) -> bool:
    haystack = " ".join(
        str(value)
        for value in [asset.id, asset.path_or_url, asset.subject_name, asset.label]
        if value
    ).lower()
    return any(token in haystack for token in ["logo", "wordmark", "favicon", "brandmark", "brand_mark"])


def _is_generic_space_asset(asset: ThumbnailAsset) -> bool:
    haystack = " ".join(
        str(value)
        for value in [asset.id, asset.path_or_url, asset.subject_name, asset.label]
        if value
    ).lower()
    return any(token in haystack for token in ["star", "stars", "skywatching", "solar-system", "galaxy", "nebula"])


def _story_is_space_related(brief: ThumbnailBrief) -> bool:
    tokens = set(_tokens(" ".join([brief.video_title, brief.episode_headline, brief.story_angle, brief.topic])))
    return bool(tokens & {"space", "orbit", "orbital", "moon", "mars", "asteroid", "telescope", "galaxy", "stars"})


def _dedupe_assets(assets: list[ThumbnailAsset]) -> list[ThumbnailAsset]:
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    deduped: list[ThumbnailAsset] = []
    for asset in assets:
        normalized_path = asset.path_or_url.lower()
        if asset.id in seen_ids or normalized_path in seen_paths:
            continue
        seen_ids.add(asset.id)
        seen_paths.add(normalized_path)
        deduped.append(asset)
    return deduped


def _has_only_generic_subjects(brief: ThumbnailBrief) -> bool:
    generic_subjects = {
        "ai model",
        "company strategy",
        "global map",
        "market chart",
        "power grid",
        "source image",
        "technology shift",
    }
    names = {subject.name.strip().lower() for subject in brief.main_subjects if subject.name.strip()}
    return bool(names) and names <= generic_subjects
