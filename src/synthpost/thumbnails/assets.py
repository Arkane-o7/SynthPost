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
    matches = [_score_asset(brief, asset) for asset in candidates]
    useful = [match for match in matches if match.score >= 12]
    useful.sort(key=lambda match: (match.score, _asset_priority(match.asset)), reverse=True)
    return useful[:max_assets]


def resolve_brief_assets(brief: ThumbnailBrief, *, library_path: str | Path | None = None) -> tuple[ThumbnailBrief, list[AssetMatch]]:
    has_foreground = any(asset.type in {"hero_composite", "foreground_composite", "person_image", "object"} for asset in brief.assets)
    max_assets = 1 if has_foreground else 2
    matches = select_assets_for_brief(brief, library_path=library_path, max_assets=max_assets)
    if matches:
        brief.assets = [*brief.assets, *(match.asset for match in matches)]
    return brief, matches


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


def _score_asset(brief: ThumbnailBrief, asset: ThumbnailAsset) -> AssetMatch:
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
    query_terms = set(_tokens(" ".join([brief.video_title, brief.episode_headline, brief.story_angle, topic])))
    score = 0
    reasons: list[str] = []

    if topic in haystack:
        score += 8
        reasons.append(f"topic:{topic}")
    for term in subject_terms:
        if term and term in haystack:
            score += 10
            reasons.append(f"subject:{term}")
    for token in query_terms:
        if len(token) > 2 and token in haystack:
            score += 2
            if len(reasons) < 5:
                reasons.append(f"keyword:{token}")
    if asset.type in {"hero_composite", "foreground_composite"}:
        score += 5
        reasons.append("foreground_composite")
    if asset.usage_status == "approved":
        score += 3
    if not _asset_exists(asset):
        score -= 20
        reasons.append("missing_file")
    return AssetMatch(asset=asset, score=score, reasons=reasons)


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
