from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from .storage import PROJECT_ROOT, episode_dir, project_relative, read_manifest, write_manifest

SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.as_posix() not in sys.path:
    sys.path.insert(0, SRC_DIR.as_posix())

from synthpost.thumbnails.assets import brief_asset_groups, resolve_brief_assets, write_resolved_brief_record
from synthpost.thumbnails.headlines import fit_headline
from synthpost.thumbnails.models import ThumbnailBrief, ThumbnailSubject
from synthpost.thumbnails.planner import plan_concepts
from synthpost.thumbnails.render import render_concept, write_candidates, write_concept
from synthpost.thumbnails.scoring import score_concept


TOPIC_MAP = {
    "ai": "AI",
    "artificial intelligence": "AI",
    "technology": "technology",
    "tech": "technology",
    "energy": "energy",
    "power": "energy",
    "grid": "energy",
    "business": "business",
    "finance": "finance",
    "markets": "finance",
    "economy": "economy",
    "geopolitics": "geopolitics",
    "policy": "policy",
    "culture": "culture",
    "conflict": "conflict",
    "infrastructure": "infrastructure",
}


def run(
    story_json_path: str | Path,
    *,
    count: int = 5,
    min_score: int = 72,
    force: bool = False,
    auto_assets: bool = True,
    manual_review: bool = True,
) -> dict[str, Any]:
    story_path = Path(story_json_path)
    manifest = read_manifest(story_path)
    output_dir = episode_dir(str(manifest["episode_id"])) / "thumbnail"
    best_path = output_dir / "thumbnail_best.png"
    candidates_path = output_dir / "thumbnail_candidates.json"
    if not force and (best_path.exists() or (manual_review and candidates_path.exists())):
        return _write_thumbnail_manifest(
            manifest,
            story_path,
            output_dir,
            reused=True,
            selection_required=not best_path.exists(),
        )

    brief = build_brief(manifest)
    selected_assets = []
    if auto_assets:
        brief, selected_assets = resolve_brief_assets(brief)

    brief_path = output_dir / "thumbnail_brief.json"
    write_resolved_brief_record(brief, brief_path, selected=selected_assets)

    concepts = plan_concepts(brief, count=count)
    for concept in concepts:
        rendered = render_concept(concept, output_dir)
        score_concept(concept, rendered)
        write_concept(concept, output_dir / "concepts" / f"{concept.concept_id}.json")
    viable = [concept for concept in concepts if (concept.score or 0) >= min_score]
    recommended = max(viable or concepts, key=lambda concept: concept.score or 0)
    candidates_path = write_candidates(
        concepts,
        output_dir,
        recommended=recommended,
        min_score=min_score,
        auto_select=not manual_review,
    )

    result = _write_thumbnail_manifest(
        manifest,
        story_path,
        output_dir,
        reused=False,
        selected_assets=[
            {"asset_id": match.asset.id, "score": match.score, "reasons": match.reasons}
            for match in selected_assets
        ],
        candidates_path=candidates_path,
        recommended_concept_id=recommended.concept_id,
        recommended_score=recommended.score,
        selection_required=manual_review,
    )
    manifest["thumbnail"] = result
    write_manifest(story_path, manifest)
    return result


def build_brief(manifest: dict[str, Any]) -> ThumbnailBrief:
    raw = manifest.get("raw", {}) if isinstance(manifest.get("raw"), dict) else {}
    script = manifest.get("script", {}) if isinstance(manifest.get("script"), dict) else {}
    video_title = str(script.get("headline") or raw.get("headline_source") or "SynthPost Briefing")
    episode_headline = str(raw.get("summary") or video_title)
    topic = _topic_from_manifest(raw, script)
    emotion = _emotion_for_topic(topic, " ".join([video_title, episode_headline]))
    subjects = _subjects_for_story(topic, " ".join([video_title, episode_headline, str(raw.get("facts", ""))]))
    approved_text = _approved_text(topic, video_title, episode_headline)
    assets = _visual_assets(manifest)
    return ThumbnailBrief(
        brief_id=f"{manifest.get('episode_id', 'episode')}_{manifest.get('story_id', 'story')}",
        video_title=video_title,
        episode_headline=episode_headline,
        topic=topic,
        main_subjects=subjects,
        story_angle=str(raw.get("summary") or episode_headline),
        emotion=emotion,
        stakes=str(raw.get("facts", [""])[0]) if isinstance(raw.get("facts"), list) and raw.get("facts") else None,
        curiosity_gap=_curiosity_gap(topic),
        approved_thumbnail_text=approved_text,
        assets=assets,
        render_preferences={
            "candidate_count": 5,
            "preferred_templates": _templates_for_topic(topic),
            "brand_intensity": "standard",
            "allow_symbolic_generated_background": True,
            "allow_real_person_generation": False,
        },
    )


def brief_record_for_story(manifest: dict[str, Any]) -> dict[str, Any]:
    brief = build_brief(manifest)
    return {
        "brief_id": brief.brief_id,
        "video_title": brief.video_title,
        "episode_headline": brief.episode_headline,
        "topic": brief.topic,
        "main_subjects": [subject.to_record() for subject in brief.main_subjects],
        "story_angle": brief.story_angle,
        "emotion": brief.emotion,
        "stakes": brief.stakes,
        "curiosity_gap": brief.curiosity_gap,
        "approved_thumbnail_text": brief.approved_thumbnail_text,
        "forbidden_thumbnail_text": brief.forbidden_thumbnail_text,
        "assets": brief_asset_groups(brief.assets),
        "render_preferences": brief.render_preferences,
    }


def _write_thumbnail_manifest(
    story_manifest: dict[str, Any],
    story_path: Path,
    output_dir: Path,
    *,
    reused: bool,
    selected_assets: list[dict[str, Any]] | None = None,
    candidates_path: Path | None = None,
    recommended_concept_id: str | None = None,
    recommended_score: int | None = None,
    selection_required: bool = True,
) -> dict[str, Any]:
    best_path = output_dir / "thumbnail_best.png"
    result = {
        "episode_id": story_manifest.get("episode_id"),
        "story_id": story_manifest.get("story_id"),
        "brief_path": project_relative(output_dir / "thumbnail_brief.json"),
        "best_path": project_relative(best_path) if best_path.exists() else None,
        "candidates_path": project_relative(candidates_path or output_dir / "thumbnail_candidates.json"),
        "contact_sheet": project_relative(output_dir / "thumbnail_contact_sheet.jpg"),
        "recommended_concept_id": recommended_concept_id,
        "recommended_score": recommended_score,
        "selection_required": selection_required,
        "selected_assets": selected_assets or [],
        "reused": reused,
    }
    result = {key: value for key, value in result.items() if value not in (None, "", [], {})}
    manifest_path = output_dir / "thumbnail_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    return result


def _topic_from_manifest(raw: dict[str, Any], script: dict[str, Any]) -> str:
    category_values = [str(raw.get("category", "")), str(script.get("category", ""))]
    for value in category_values:
        normalized = value.lower().strip()
        if normalized in TOPIC_MAP:
            return TOPIC_MAP[normalized]
    haystack = " ".join([*category_values, str(raw.get("headline_source", ""))]).lower()
    for needle, topic in TOPIC_MAP.items():
        if needle in haystack:
            return topic
    return "AI" if "ai" in haystack else "technology"


def _emotion_for_topic(topic: str, text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ["war", "ban", "crisis", "risk", "warning", "pressure"]):
        return "urgent"
    if topic in {"geopolitics", "conflict", "energy"}:
        return "urgent"
    if topic in {"finance", "business"}:
        return "serious"
    return "analytical"


def _subjects_for_story(topic: str, text: str) -> list[ThumbnailSubject]:
    lowered = text.lower()
    subjects: list[ThumbnailSubject] = []
    if "nvidia" in lowered:
        subjects.append(ThumbnailSubject(type="company", name="Nvidia", importance="primary", visual_priority=5))
    if "data center" in lowered or "datacenter" in lowered:
        subjects.append(ThumbnailSubject(type="object", name="data center", importance="primary", visual_priority=5))
    if "grid" in lowered or "power" in lowered:
        subjects.append(ThumbnailSubject(type="object", name="power grid", importance="secondary", visual_priority=4))
    if "china" in lowered:
        subjects.append(ThumbnailSubject(type="country", name="China", importance="primary", visual_priority=5))
    if "chip" in lowered or "semiconductor" in lowered:
        subjects.append(ThumbnailSubject(type="object", name="AI chip", importance="primary", visual_priority=5))
    if not subjects:
        fallback = {
            "AI": "AI model",
            "energy": "power grid",
            "geopolitics": "global map",
            "finance": "market chart",
            "business": "company strategy",
        }.get(topic, "technology shift")
        subjects.append(ThumbnailSubject(type="object", name=fallback, importance="primary", visual_priority=4))
    return subjects[:4]


def _approved_text(topic: str, video_title: str, episode_headline: str) -> list[str]:
    fitted = fit_headline(video_title or episode_headline, max_words=4).lower()
    if topic == "energy":
        return ["ai needs power", "grid under pressure", fitted]
    if topic == "geopolitics":
        return ["chip war escalates", "ai race heats up", fitted]
    if topic == "finance":
        return ["stock surges", "market shock", fitted]
    if topic == "policy":
        return ["ai rules arrive", "policy shock", fitted]
    return [fitted, "ai shift accelerates", "tech race heats up"]


def _visual_assets(manifest: dict[str, Any]) -> list[Any]:
    assets = []
    for index, visual in enumerate(manifest.get("visuals", []) or []):
        if not isinstance(visual, dict) or not visual.get("path"):
            continue
        path = str(visual["path"])
        assets.append(
            {
                "id": f"story_visual_{index + 1:02d}",
                "path_or_url": path,
                "type": "background_image",
                "subject_name": str(visual.get("title") or visual.get("sourceLabel") or "Story visual"),
                "source_url": visual.get("source_url"),
                "license": str(visual.get("license") or visual.get("usage_basis") or "story visual"),
                "usage_status": "approved" if visual.get("safe_to_use", False) else "needs_review",
                "label": str(visual.get("sourceLabel") or visual.get("title") or "Story visual"),
            }
        )
    from synthpost.thumbnails.models import ThumbnailAsset

    return [ThumbnailAsset.from_record(asset) for asset in assets[:2]]


def _templates_for_topic(topic: str) -> list[str]:
    if topic in {"energy", "finance", "technology"}:
        return ["clean_market_surge", "money_deal_bomb", "logo_collision"]
    if topic in {"geopolitics", "conflict"}:
        return ["clean_market_surge", "logo_collision", "authority_warning"]
    if topic in {"policy", "AI"}:
        return ["clean_market_surge", "authority_warning", "logo_collision"]
    return ["clean_market_surge", "authority_warning", "money_deal_bomb"]


def _curiosity_gap(topic: str) -> str:
    if topic == "energy":
        return "Can infrastructure keep up with AI demand?"
    if topic == "geopolitics":
        return "Who controls the next layer of AI power?"
    if topic == "finance":
        return "How much of the rally is real?"
    return "What changes next?"
