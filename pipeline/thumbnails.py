from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from .provenance import artifact_record, record_story_artifact
from .render_profiles import resolve_profile
from .storage import PROJECT_ROOT, episode_dir, project_relative, read_manifest, write_manifest

SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.as_posix() not in sys.path:
    sys.path.insert(0, SRC_DIR.as_posix())

from synthpost.thumbnails.assets import (
    brief_asset_groups,
    library_asset_candidate_records,
    resolve_brief_assets,
    write_resolved_brief_record,
)
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
    "science": "science",
    "earth": "science",
    "environment": "science",
    "climate": "science",
    "water": "science",
    "flood": "science",
    "rains": "science",
    "rain": "science",
    "lake": "science",
    "hyperwall": "science",
    "nasa": "science",
    "conference": "education",
}

SCIENCE_TERMS = {
    "climate",
    "earth",
    "environment",
    "flood",
    "lake",
    "rain",
    "rains",
    "river",
    "satellite",
    "science",
    "swamp",
    "water",
    "waters",
}

LOGO_TERMS = {"logo", "wordmark", "favicon", "brandmark", "brand_mark"}
GENERIC_SPACE_TERMS = {"star", "stars", "skywatching", "solar-system", "solar_system", "galaxy", "nebula"}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [re.sub(r"\s+", " ", str(item or "")).strip() for item in value if str(item or "").strip()]


def _source_metadata_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    metadata = raw.get("source_metadata") if isinstance(raw.get("source_metadata"), dict) else {}
    fallback = {
        "source": raw.get("source_name"),
        "source_name": raw.get("source_name"),
        "source_url": raw.get("source_url"),
        "source_domain": raw.get("source_domain"),
        "source_provider": raw.get("source_provider"),
        "source_type": raw.get("source_type"),
        "source_category": raw.get("source_category"),
        "published_at": raw.get("published_at"),
    }
    return {
        key: metadata.get(key) or value
        for key, value in fallback.items()
        if metadata.get(key) or value
    }


def thumbnail_handoff_for_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("raw", {}) if isinstance(manifest.get("raw"), dict) else {}
    handoff = raw.get("handoff") if isinstance(raw.get("handoff"), dict) else {}
    thumbnail = handoff.get("thumbnail") if isinstance(handoff.get("thumbnail"), dict) else {}
    editorial = raw.get("editorial") if isinstance(raw.get("editorial"), dict) else {}
    selected = raw.get("selected_candidate") if isinstance(raw.get("selected_candidate"), dict) else {}
    source_metadata = thumbnail.get("source_metadata") if isinstance(thumbnail.get("source_metadata"), dict) else {}
    source_metadata = {**_source_metadata_from_raw(raw), **source_metadata}
    raw_thumbnail_hooks = _string_list(raw.get("thumbnail_hooks"))
    return {
        "candidate_id": thumbnail.get("candidate_id") or selected.get("candidate_id") or editorial.get("candidate_id"),
        "headline": thumbnail.get("headline") or raw.get("headline_source", ""),
        "thumbnail_hook": thumbnail.get("thumbnail_hook") or (raw_thumbnail_hooks[0] if raw_thumbnail_hooks else ""),
        "title_ideas": _string_list(thumbnail.get("title_ideas")) or _string_list(raw.get("title_ideas")),
        "visual_opportunities": _string_list(thumbnail.get("visual_opportunities")) or _string_list(raw.get("visual_opportunities")),
        "entities": _string_list(thumbnail.get("entities")) or _string_list(raw.get("entities") or raw.get("key_entities")),
        "source_metadata": source_metadata,
        "source_url": source_metadata.get("source_url"),
        "source_domain": source_metadata.get("source_domain"),
        "source_name": source_metadata.get("source_name") or source_metadata.get("source"),
        "final_editorial_score": thumbnail.get("final_editorial_score") or selected.get("final_editorial_score"),
        "synthpost_angle": thumbnail.get("synthpost_angle") or editorial.get("synthpost_angle") or editorial.get("possible_synthpost_angle", ""),
        "audience_curiosity_angle": thumbnail.get("audience_curiosity_angle") or editorial.get("audience_curiosity_angle", ""),
    }


def run(
    story_json_path: str | Path,
    *,
    count: int = 5,
    min_score: int = 72,
    force: bool = False,
    auto_assets: bool = True,
    manual_review: bool = True,
    test_mode: bool = False,
    render_profile: str = "production",
) -> dict[str, Any]:
    story_path = Path(story_json_path)
    manifest = read_manifest(story_path)
    profile = resolve_profile(render_profile)
    output_dir = episode_dir(str(manifest["episode_id"])) / "thumbnail"
    best_path = output_dir / "thumbnail_best.png"
    candidates_path = output_dir / "thumbnail_candidates.json"
    if not force and (best_path.exists() or (manual_review and candidates_path.exists())):
        result = _write_thumbnail_manifest(
            manifest,
            story_path,
            output_dir,
            reused=True,
            selection_required=not best_path.exists(),
        )
        if best_path.exists():
            record_story_artifact(
                story_path,
                "thumbnail_best",
                artifact_record(
                    path=best_path,
                    stage="thumbnail",
                    input_paths=[story_path, candidates_path],
                    provider="remotion",
                    fresh=False,
                    reused=True,
                    test_mode=test_mode,
                    render_profile=profile.name,
                    metadata={"thumbnail_relevance_score": result.get("thumbnail_relevance_score")},
                ),
            )
        return result

    brief = build_brief(manifest)
    selected_assets = []
    if auto_assets:
        brief, selected_assets = resolve_brief_assets(brief)
    visual_asset_candidates = thumbnail_visual_candidate_report(
        manifest,
        brief=brief,
        selected_library_assets=selected_assets,
    )

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
        visual_asset_candidates=visual_asset_candidates,
    )

    accepted_visual_assets = [
        {
            "asset_id": candidate["asset_id"],
            "source": candidate.get("source"),
            "relevance_score": candidate.get("relevance_score"),
            "reasons": candidate.get("reasons", []),
        }
        for candidate in visual_asset_candidates.get("candidates", [])
        if candidate.get("accepted")
    ]
    selected_assets_payload = [
        *accepted_visual_assets,
        *[
            {
                "asset_id": match.asset.id,
                "score": match.score,
                "relevance_score": match.relevance_score,
                "reasons": match.reasons,
            }
            for match in selected_assets
        ],
    ]
    result = _write_thumbnail_manifest(
        manifest,
        story_path,
        output_dir,
        reused=False,
        selected_assets=selected_assets_payload,
        thumbnail_relevance_score=visual_asset_candidates.get("selected_relevance_score"),
        candidates_path=candidates_path,
        recommended_concept_id=recommended.concept_id,
        recommended_score=recommended.score,
        selection_required=manual_review,
    )
    manifest["thumbnail"] = result
    write_manifest(story_path, manifest)
    if best_path.exists():
        record_story_artifact(
            story_path,
            "thumbnail_best",
            artifact_record(
                path=best_path,
                stage="thumbnail",
                input_paths=[story_path, candidates_path],
                provider="remotion",
                fresh=True,
                reused=False,
                test_mode=test_mode,
                render_profile=profile.name,
                command=["npm", "run", "render:thumbnail"],
                flags={"manual_review": manual_review, "auto_assets": auto_assets},
                metadata={"thumbnail_relevance_score": result.get("thumbnail_relevance_score")},
            ),
        )
    record_story_artifact(
        story_path,
        "thumbnail_candidates",
        artifact_record(
            path=candidates_path,
            stage="thumbnail",
            input_paths=[story_path],
            provider="thumbnail_planner",
            fresh=True,
            reused=False,
            test_mode=test_mode,
            render_profile=profile.name,
            flags={"manual_review": manual_review, "auto_assets": auto_assets},
        ),
    )
    return result


def build_brief(manifest: dict[str, Any]) -> ThumbnailBrief:
    raw = manifest.get("raw", {}) if isinstance(manifest.get("raw"), dict) else {}
    script = manifest.get("script", {}) if isinstance(manifest.get("script"), dict) else {}
    thumbnail_handoff = thumbnail_handoff_for_manifest(manifest)
    title_ideas = thumbnail_handoff.get("title_ideas") if isinstance(thumbnail_handoff.get("title_ideas"), list) else []
    thumbnail_hook = str(thumbnail_handoff.get("thumbnail_hook") or "")
    video_title = str(script.get("headline") or (title_ideas[0] if title_ideas else "") or raw.get("headline_source") or "SynthPost Briefing")
    episode_headline = str(thumbnail_hook or raw.get("summary") or video_title)
    story_text = _story_text(raw, script)
    topic = _topic_from_manifest(raw, script)
    emotion = _emotion_for_topic(topic, " ".join([video_title, episode_headline]))
    subjects = _subjects_for_story(topic, story_text)
    approved_text = _approved_text(topic, video_title, episode_headline)
    assets = _visual_assets(manifest, topic=topic, subjects=subjects)
    stakes = _supporting_thumbnail_text(
        raw,
        topic=topic,
        subjects=subjects,
        video_title=video_title,
        episode_headline=episode_headline,
    )
    story_angle = str(
        thumbnail_handoff.get("synthpost_angle")
        or thumbnail_handoff.get("audience_curiosity_angle")
        or raw.get("summary")
        or episode_headline
    )
    curiosity_gap = str(thumbnail_handoff.get("audience_curiosity_angle") or thumbnail_hook or _curiosity_gap(topic))
    return ThumbnailBrief(
        brief_id=f"{manifest.get('episode_id', 'episode')}_{manifest.get('story_id', 'story')}",
        video_title=video_title,
        episode_headline=episode_headline,
        topic=topic,
        main_subjects=subjects,
        story_angle=story_angle,
        emotion=emotion,
        stakes=stakes,
        curiosity_gap=curiosity_gap,
        approved_thumbnail_text=approved_text,
        assets=assets,
        render_preferences={
            "candidate_count": 5,
            "preferred_templates": _templates_for_topic(topic),
            "avoid_templates": _avoid_templates_for_topic(topic),
            "brand_intensity": "standard",
            "allow_symbolic_generated_background": True,
            "allow_real_person_generation": False,
        },
    )


def brief_record_for_story(manifest: dict[str, Any]) -> dict[str, Any]:
    brief = build_brief(manifest)
    handoff = thumbnail_handoff_for_manifest(manifest)
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
        "handoff": handoff,
    }


def _write_thumbnail_manifest(
    story_manifest: dict[str, Any],
    story_path: Path,
    output_dir: Path,
    *,
    reused: bool,
    selected_assets: list[dict[str, Any]] | None = None,
    thumbnail_relevance_score: float | None = None,
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
        "thumbnail_relevance_score": thumbnail_relevance_score,
        "reused": reused,
    }
    result = {key: value for key, value in result.items() if value not in (None, "", [], {})}
    manifest_path = output_dir / "thumbnail_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    return result


def thumbnail_visual_candidate_report(
    manifest: dict[str, Any],
    *,
    brief: ThumbnailBrief | None = None,
    selected_library_assets: list[Any] | None = None,
) -> dict[str, Any]:
    raw = manifest.get("raw", {}) if isinstance(manifest.get("raw"), dict) else {}
    script = manifest.get("script", {}) if isinstance(manifest.get("script"), dict) else {}
    if brief is None:
        story_text = _story_text(raw, script)
        topic = _topic_from_manifest(raw, script)
        subjects = _subjects_for_story(topic, story_text)
    else:
        topic = brief.topic
        subjects = brief.main_subjects
    _, story_candidates = _rank_story_visuals(manifest, topic=topic, subjects=subjects)
    accepted_story = [candidate for candidate in story_candidates if candidate["accepted"]]
    library_candidates = library_asset_candidate_records(
        brief,
        selected=selected_library_assets,
    ) if brief else []
    selected_relevance_score = max(
        [candidate["relevance_score"] for candidate in accepted_story]
        + [candidate.get("relevance_score", 0) for candidate in library_candidates if candidate.get("accepted")]
        + [0],
    )
    return {
        "story": {
            "headline": raw.get("headline_source") or (script.get("headline") if isinstance(script, dict) else None),
            "topic": topic,
            "entities": [subject.name for subject in subjects],
            "source_name": raw.get("source_name"),
            "source_url": raw.get("source_url"),
            "source_domain": raw.get("source_domain"),
        },
        "selection_policy": [
            "current story official/source image",
            "current story extracted media",
            "related verified public-domain media",
            "generated editorial fallback",
            "generic fallback only if nothing else exists",
        ],
        "selected": [candidate["asset_id"] for candidate in accepted_story],
        "selected_relevance_score": selected_relevance_score,
        "candidates": [_reportable_candidate(candidate) for candidate in story_candidates],
        "library_candidates": library_candidates,
    }


def _topic_from_manifest(raw: dict[str, Any], script: dict[str, Any]) -> str:
    category_values = [str(raw.get("category", "")), str(script.get("category", ""))]
    for value in category_values:
        normalized = value.lower().strip()
        if normalized in TOPIC_MAP and normalized not in {"general", "news"}:
            return TOPIC_MAP[normalized]

    haystack = _story_text(raw, script)
    lowered = haystack.lower()
    tokens = set(_tokens(lowered))
    if "artificial intelligence" in lowered or "generative ai" in lowered or "ai" in tokens:
        return "AI"
    if tokens & SCIENCE_TERMS:
        return "science"
    for needle, topic in TOPIC_MAP.items():
        if " " in needle and needle in lowered:
            return topic
        if needle in tokens:
            return topic
    return "technology"


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
    lake_match = re.search(r"\bLake\s+([A-Z][A-Za-z0-9-]+(?:\s+(?:of\s+)?[A-Z][A-Za-z0-9-]+)?)", text)
    if lake_match:
        _append_subject(subjects, ThumbnailSubject(type="place", name=f"Lake {lake_match.group(1)}", importance="primary", visual_priority=5))
    if re.search(r"\bKenya\b", text):
        _append_subject(subjects, ThumbnailSubject(type="country", name="Kenya", importance="secondary", visual_priority=4))
    if any(phrase in lowered for phrase in ["rising waters", "flood", "flooding", "swamp", "relentless rains"]):
        _append_subject(subjects, ThumbnailSubject(type="event", name="rising waters", importance="secondary", visual_priority=4))
    if "hyperwall" in lowered:
        _append_subject(subjects, ThumbnailSubject(type="object", name="NASA Hyperwall", importance="primary", visual_priority=5))
    if "american library association" in lowered or "ala" in lowered:
        _append_subject(subjects, ThumbnailSubject(type="event", name="ALA Annual Conference", importance="secondary", visual_priority=4))
    if "nvidia" in lowered:
        _append_subject(subjects, ThumbnailSubject(type="company", name="Nvidia", importance="primary", visual_priority=5))
    if "data center" in lowered or "datacenter" in lowered:
        _append_subject(subjects, ThumbnailSubject(type="object", name="data center", importance="primary", visual_priority=5))
    if "grid" in lowered or "power" in lowered:
        _append_subject(subjects, ThumbnailSubject(type="object", name="power grid", importance="secondary", visual_priority=4))
    if "china" in lowered:
        _append_subject(subjects, ThumbnailSubject(type="country", name="China", importance="primary", visual_priority=5))
    if "chip" in lowered or "semiconductor" in lowered:
        _append_subject(subjects, ThumbnailSubject(type="object", name="AI chip", importance="primary", visual_priority=5))
    if not subjects:
        fallback = {
            "AI": "AI model",
            "energy": "power grid",
            "geopolitics": "global map",
            "finance": "market chart",
            "business": "company strategy",
            "science": "source image",
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
    if topic == "science":
        lowered = f"{video_title} {episode_headline}".lower()
        if any(term in lowered for term in ["water", "flood", "lake", "rains", "kenya"]):
            return [fitted, "water warning", "kenya flood watch"]
        if "schedule" in lowered or "conference" in lowered:
            return [fitted, "nasa schedule", "hyperwall at ala"]
        return [fitted, "science update", "why it matters"]
    if topic == "AI":
        return [fitted, "ai shift accelerates", "tech race heats up"]
    if topic == "technology":
        return [fitted, "tech shift", "what changes next"]
    return [fitted, "what changes next", "why it matters"]


def _visual_assets(manifest: dict[str, Any], *, topic: str, subjects: list[ThumbnailSubject]) -> list[Any]:
    assets, _ = _rank_story_visuals(manifest, topic=topic, subjects=subjects)
    return assets


def _supporting_thumbnail_text(
    raw: dict[str, Any],
    *,
    topic: str,
    subjects: list[ThumbnailSubject],
    video_title: str,
    episode_headline: str,
) -> str | None:
    text = _story_text(raw, {})
    lowered = " ".join([text, video_title, episode_headline]).lower()
    lake = next((subject.name for subject in subjects if subject.type == "place" and subject.name.lower().startswith("lake ")), None)
    if topic == "science" and "hyperwall" in lowered and ("ala" in lowered or "american library association" in lowered):
        return "NASA Hyperwall schedule at ALA 2026."
    if topic == "science" and lake and any(term in lowered for term in ["water", "flood", "rains", "swamp"]):
        return f"{lake} rising water seen from orbit."

    facts = raw.get("facts", [])
    if isinstance(facts, list) and facts:
        source = str(facts[0])
    else:
        source = str(raw.get("summary") or episode_headline or video_title)
    return _clip_supporting_text(source)


def _clip_supporting_text(value: str, *, max_words: int = 11, max_chars: int = 78) -> str | None:
    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        return None
    words = text.split()
    clipped = " ".join(words[:max_words])
    if len(clipped) > max_chars:
        clipped = clipped[:max_chars].rsplit(" ", 1)[0]
    clipped = clipped.strip(" ,.;:-")
    if not clipped:
        return None
    if clipped != text.strip(" ,.;:-"):
        clipped = f"{clipped}..."
    return clipped


def _rank_story_visuals(
    manifest: dict[str, Any],
    *,
    topic: str,
    subjects: list[ThumbnailSubject],
) -> tuple[list[Any], list[dict[str, Any]]]:
    from synthpost.thumbnails.models import ThumbnailAsset

    raw = manifest.get("raw", {}) if isinstance(manifest.get("raw"), dict) else {}
    script = manifest.get("script", {}) if isinstance(manifest.get("script"), dict) else {}
    story_terms = _story_terms(raw, script, subjects)
    records = _story_visual_records(manifest)
    candidates = [
        _score_story_visual_candidate(record, index=index, topic=topic, story_terms=story_terms, subjects=subjects, source_url=str(raw.get("source_url") or ""))
        for index, record in enumerate(records, start=1)
    ]
    accepted = [candidate for candidate in candidates if candidate["accepted"]]
    accepted.sort(key=lambda candidate: (candidate["raw_score"], -candidate["order"]), reverse=True)
    assets = [
        ThumbnailAsset.from_record(candidate["_asset_record"])
        for candidate in accepted[:2]
    ]
    return assets, candidates


def _story_visual_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    detailed_assets: dict[str, dict[str, Any]] = {}
    for asset in manifest.get("visual_assets", []) or []:
        if isinstance(asset, dict):
            asset_id = str(asset.get("asset_id") or "")
            if asset_id:
                detailed_assets[asset_id] = asset

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for visual in manifest.get("visuals", []) or []:
        if not isinstance(visual, dict):
            continue
        asset_id = str(visual.get("asset_id") or visual.get("id") or "")
        merged = {**detailed_assets.get(asset_id, {}), **visual}
        key = str(merged.get("asset_id") or merged.get("path") or merged.get("downloaded_path") or merged.get("remote_url") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        records.append(merged)

    for asset_id, asset in detailed_assets.items():
        key = str(asset.get("asset_id") or asset.get("path") or asset.get("downloaded_path") or asset.get("remote_url") or asset_id)
        if key in seen:
            continue
        seen.add(key)
        records.append(asset)
    return records


def _score_story_visual_candidate(
    record: dict[str, Any],
    *,
    index: int,
    topic: str,
    story_terms: set[str],
    subjects: list[ThumbnailSubject],
    source_url: str,
) -> dict[str, Any]:
    path = str(record.get("path") or record.get("downloaded_path") or record.get("remote_url") or "")
    remote_url = str(record.get("remote_url") or "")
    asset_id = str(record.get("asset_id") or f"story_visual_{index:02d}")
    title = str(record.get("title") or record.get("caption") or record.get("alt") or record.get("sourceLabel") or "Story visual")
    source = str(record.get("source_page_role") or record.get("visual_role") or record.get("provider") or "story_visual")
    haystack = " ".join(
        str(value)
        for value in [
            asset_id,
            path,
            remote_url,
            title,
            record.get("provider"),
            record.get("source_name"),
            record.get("source_page_role"),
            record.get("visual_role"),
            " ".join(str(item) for item in record.get("keywords", []) if item),
        ]
        if value
    ).lower()
    candidate_tokens = set(_tokens(haystack))
    score = 0
    reasons: list[str] = []
    reject_reason: str | None = None

    if record.get("safe_to_use", False):
        score += 6
        reasons.append("usage:approved")
    else:
        reject_reason = "usage rights need review"

    if record.get("provider") in {"official_source_media", "manifest_media"} or record.get("source_authority") == "official":
        score += 35
        reasons.append("source:official")
    if record.get("source_page_role") in {"og:image", "lead_image", "article_lead_image"}:
        score += 25
        reasons.append("article_lead_image")
    if source_url and str(record.get("source_url") or "").rstrip("/") == source_url.rstrip("/"):
        score += 12
        reasons.append("source_url:current_story")

    matched_terms = sorted(token for token in story_terms if len(token) > 2 and token in candidate_tokens)
    if matched_terms:
        score += min(40, len(matched_terms) * 5)
        reasons.extend(f"entity:{token}" for token in matched_terms[:5])
    for subject in subjects:
        subject_name = subject.name.lower()
        subject_tokens = set(_tokens(subject_name))
        if subject_name and subject_name in haystack:
            score += 20
            reasons.append(f"subject:{subject.name}")
        elif subject_tokens and subject_tokens.issubset(candidate_tokens):
            score += 14
            reasons.append(f"subject_tokens:{subject.name}")

    image_size = _image_size(path)
    if image_size:
        width, height = image_size
        if width >= 900 and height >= 500:
            score += 8
            reasons.append("dimensions:thumbnail_safe")
        elif width < 640 or height < 360:
            score -= 18
            reasons.append("dimensions:low_resolution")

    if _is_generated_context_candidate(record, haystack):
        score -= 40
        reject_reason = "generated context graphic reserved for video body, not thumbnail background"
    elif _is_logo_candidate(haystack):
        score -= 80
        reject_reason = "publisher logo, not story visual"
    elif _is_generic_space_candidate(haystack) and not _story_terms_are_space_related(story_terms):
        score -= 70
        reject_reason = "generic space image unrelated to story entities"
    elif not path:
        score -= 30
        reject_reason = "missing image path"
    elif not reject_reason and score < 35:
        reject_reason = "low match to current story headline, topic, and entities"

    accepted = reject_reason is None
    relevance_score = round(max(0.0, min(score / 100.0, 1.0)), 2)
    asset_record = {
        "id": f"story_visual_{index:02d}",
        "path_or_url": path,
        "type": "background_image",
        "subject_name": title[:120],
        "source_url": record.get("source_url"),
        "license": str(record.get("license") or record.get("usage_basis") or "story visual"),
        "usage_status": "approved" if accepted else "needs_review",
        "label": str(record.get("source_name") or record.get("sourceLabel") or title)[:80],
        "attribution": record.get("attribution_text") or record.get("attribution"),
        "notes": f"thumbnail_relevance_score={relevance_score}; source={source}",
    }
    return {
        "order": index,
        "asset_id": asset_id,
        "source": source,
        "path_or_url": path,
        "remote_url": remote_url or None,
        "caption": title,
        "width": image_size[0] if image_size else None,
        "height": image_size[1] if image_size else None,
        "raw_score": score,
        "relevance_score": relevance_score,
        "accepted": accepted,
        "reject_reason": reject_reason,
        "reasons": reasons,
        "_asset_record": asset_record,
    }


def _story_terms(raw: dict[str, Any], script: dict[str, Any], subjects: list[ThumbnailSubject]) -> set[str]:
    text = " ".join([_story_text(raw, script), " ".join(subject.name for subject in subjects)])
    generic_source_terms = {"nasa", "science", "gov", "source", "official", "general", "story"}
    return {token for token in _tokens(text) if token not in generic_source_terms}


def _story_text(raw: dict[str, Any], script: dict[str, Any]) -> str:
    facts = raw.get("facts", [])
    fact_text = " ".join(str(item) for item in facts if item) if isinstance(facts, list) else str(facts or "")
    entities = raw.get("entities") or raw.get("key_entities") or []
    entity_text = " ".join(str(item) for item in entities if item) if isinstance(entities, list) else str(entities or "")
    opportunities = raw.get("visual_opportunities", [])
    opportunity_text = " ".join(str(item) for item in opportunities if item) if isinstance(opportunities, list) else str(opportunities or "")
    editorial = raw.get("editorial") if isinstance(raw.get("editorial"), dict) else {}
    return ". ".join(
        str(value)
        for value in [
            raw.get("headline_source"),
            raw.get("summary"),
            fact_text,
            entity_text,
            opportunity_text,
            editorial.get("possible_synthpost_angle") if isinstance(editorial, dict) else "",
            editorial.get("audience_curiosity_angle") if isinstance(editorial, dict) else "",
            script.get("headline") if isinstance(script, dict) else "",
            script.get("text") if isinstance(script, dict) else "",
            raw.get("category"),
            script.get("category") if isinstance(script, dict) else "",
        ]
        if value
    )


def _append_subject(subjects: list[ThumbnailSubject], subject: ThumbnailSubject) -> None:
    if subject.name.lower() not in {item.name.lower() for item in subjects}:
        subjects.append(subject)


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _is_logo_candidate(haystack: str) -> bool:
    return any(term in haystack for term in LOGO_TERMS)


def _is_generic_space_candidate(haystack: str) -> bool:
    return any(term in haystack for term in GENERIC_SPACE_TERMS)


def _is_generated_context_candidate(record: dict[str, Any], haystack: str) -> bool:
    return (
        record.get("provider") == "screenshot_provider"
        or record.get("visual_role") == "context_graphic"
        or record.get("asset_type") == "generated"
        or "source_context.svg" in haystack
    )


def _story_terms_are_space_related(story_terms: set[str]) -> bool:
    return bool(story_terms & {"space", "orbit", "orbital", "moon", "mars", "asteroid", "telescope", "galaxy", "stars"})


def _image_size(path_or_url: str) -> tuple[int, int] | None:
    if not path_or_url or path_or_url.startswith(("http://", "https://", "generated://", "symbolic://")):
        return None
    try:
        from PIL import Image

        path = Path(path_or_url)
        resolved = path if path.is_absolute() else PROJECT_ROOT / path
        if not resolved.exists():
            return None
        with Image.open(resolved) as image:
            return image.size
    except Exception:
        return None


def _reportable_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in candidate.items()
        if not key.startswith("_") and value not in (None, "", [], {})
    }


def _templates_for_topic(topic: str) -> list[str]:
    if topic in {"energy", "finance", "technology"}:
        return ["clean_market_surge", "money_deal_bomb", "logo_collision"]
    if topic in {"geopolitics", "conflict"}:
        return ["clean_market_surge", "logo_collision", "authority_warning"]
    if topic in {"policy", "AI"}:
        return ["clean_market_surge", "authority_warning", "logo_collision"]
    if topic == "science":
        return ["authority_warning", "money_deal_bomb", "logo_collision"]
    return ["clean_market_surge", "authority_warning", "money_deal_bomb"]


def _avoid_templates_for_topic(topic: str) -> list[str]:
    if topic == "science":
        return ["logo_collision"]
    return []


def _curiosity_gap(topic: str) -> str:
    if topic == "energy":
        return "Can infrastructure keep up with AI demand?"
    if topic == "geopolitics":
        return "Who controls the next layer of AI power?"
    if topic == "finance":
        return "How much of the rally is real?"
    if topic == "science":
        return "What changes as the water keeps rising?"
    return "What changes next?"
