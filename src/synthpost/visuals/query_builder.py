from __future__ import annotations

import re
import urllib.parse
from typing import Any

from .models import AssetType, StorySegment, VisualQuery

STOPWORDS = {
    "a",
    "about",
    "after",
    "again",
    "against",
    "all",
    "also",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "can",
    "could",
    "for",
    "from",
    "has",
    "have",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "more",
    "new",
    "no",
    "not",
    "of",
    "on",
    "or",
    "other",
    "over",
    "said",
    "says",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "which",
    "with",
    "within",
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "ai": ["artificial intelligence", "data center", "semiconductor", "chip", "server racks", "cloud computing"],
    "technology": [
        "technology",
        "software",
        "app",
        "chip",
        "data center",
        "product demo",
        "screenshot",
        "official announcement",
    ],
    "energy": [
        "electric grid",
        "transmission lines",
        "power plant",
        "substation",
        "data center electricity",
        "regulatory filing",
    ],
    "economy": ["markets", "stock exchange", "factory", "shipping port", "currency", "central bank", "chart"],
    "business": ["company headquarters", "earnings", "CEO", "product launch", "factory", "market chart"],
    "politics": ["government", "parliament", "leader", "official briefing", "capitol", "press conference"],
    "geopolitics": ["map", "leader", "border", "UN", "official briefing", "city skyline"],
    "world": ["map", "city skyline", "leader", "protest", "official briefing"],
    "conflict": ["map", "military", "city damage", "border", "satellite image", "briefing", "battlefield footage"],
    "culture": ["event", "public reaction", "venue", "platform screenshot"],
}

ENTITY_ALIASES: dict[str, list[str]] = {
    "ferc": ["Federal Energy Regulatory Commission", "FERC", "electric grid", "transmission"],
    "ai": ["artificial intelligence", "AI", "data centers", "GPU"],
    "data": ["data center", "server racks", "cloud infrastructure"],
    "grid": ["electric grid", "transmission lines", "power infrastructure"],
}

TYPE_HINTS: dict[str, list[AssetType]] = {
    "map": [AssetType.MAP, AssetType.IMAGE, AssetType.GENERATED],
    "chart": [AssetType.CHART, AssetType.IMAGE, AssetType.GENERATED],
    "document": [AssetType.DOCUMENT, AssetType.SCREENSHOT, AssetType.GENERATED],
    "screenshot": [AssetType.SCREENSHOT, AssetType.IMAGE, AssetType.GENERATED],
    "video": [AssetType.VIDEO, AssetType.IMAGE, AssetType.GENERATED],
    "footage": [AssetType.VIDEO, AssetType.IMAGE, AssetType.GENERATED],
}


def compact_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def tokenize(value: object) -> list[str]:
    text = compact_text(value).lower()
    words = re.findall(r"[a-z0-9][a-z0-9-]{2,}", text)
    return [word for word in words if word not in STOPWORDS]


def split_sentences(value: object) -> list[str]:
    text = compact_text(value)
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [sentence.strip(" \"'") for sentence in sentences if len(sentence.split()) >= 6]


def unique(values: list[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = compact_text(value)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if limit and len(result) >= limit:
            break
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [compact_text(item) for item in value if compact_text(item)]


def visual_handoff_for_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    handoff = raw.get("handoff") if isinstance(raw.get("handoff"), dict) else {}
    visuals = handoff.get("visuals") if isinstance(handoff.get("visuals"), dict) else {}
    source_metadata = visuals.get("source_metadata") if isinstance(visuals.get("source_metadata"), dict) else raw.get("source_metadata", {})
    editorial = raw.get("editorial") if isinstance(raw.get("editorial"), dict) else {}
    return {
        "candidate_id": visuals.get("candidate_id") or editorial.get("candidate_id"),
        "headline": visuals.get("headline") or raw.get("headline_source", ""),
        "category": visuals.get("category") or raw.get("category", ""),
        "visual_opportunities": _string_list(visuals.get("visual_opportunities")) or _string_list(raw.get("visual_opportunities")),
        "entities": _string_list(visuals.get("entities")) or _string_list(raw.get("entities") or raw.get("key_entities")),
        "source_metadata": source_metadata if isinstance(source_metadata, dict) else {},
        "candidate_relevance": visuals.get("candidate_relevance") if isinstance(visuals.get("candidate_relevance"), dict) else {},
        "why_it_matters": visuals.get("why_it_matters") or editorial.get("why_it_matters", ""),
        "synthpost_angle": visuals.get("synthpost_angle") or editorial.get("synthpost_angle") or editorial.get("possible_synthpost_angle", ""),
        "risks_or_reasons_to_avoid": _string_list(visuals.get("risks_or_reasons_to_avoid")) or _string_list(editorial.get("risks_or_reasons_to_avoid")),
    }


def keyword_phrases(text: str, category: str = "") -> list[str]:
    words = tokenize(text)
    phrases: list[str] = []
    phrases.extend(words)
    lowered = text.lower()
    for key, aliases in ENTITY_ALIASES.items():
        if key in words or key in lowered:
            phrases.extend(aliases)
    phrases.extend(CATEGORY_KEYWORDS.get(category.lower(), []))
    return unique(phrases, limit=18)


def _headline_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[Any] = []
    composition = manifest.get("composition")
    if isinstance(composition, dict):
        values.extend(composition.get("headlines") or [])
    values.extend(manifest.get("chyrons") or [])
    values.extend(manifest.get("headlines") or [])

    items: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, str):
            text = compact_text(value)
            if text:
                items.append({"text": text})
        elif isinstance(value, dict):
            text = compact_text(value.get("text") or value.get("headline") or value.get("title"))
            if not text:
                continue
            item = {"text": text}
            for key in ("start", "end"):
                try:
                    number = float(value[key])
                except (KeyError, TypeError, ValueError):
                    continue
                item[key] = number
            items.append(item)
    return items


def _source_host(manifest: dict[str, Any]) -> str:
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    try:
        host = urllib.parse.urlparse(str(raw.get("source_url") or "")).hostname or ""
    except ValueError:
        return ""
    return host.removeprefix("www.")


def _add_item(items: list[dict[str, Any]], seen: set[str], value: object, **extra: Any) -> None:
    text = compact_text(value)
    if not text:
        return
    key = text.lower()
    if key in seen:
        return
    seen.add(key)
    item = {"text": text}
    item.update({key: value for key, value in extra.items() if value is not None})
    items.append(item)


def _duration(manifest: dict[str, Any]) -> float:
    for section_name in ("composition", "direction"):
        section = manifest.get(section_name)
        if isinstance(section, dict):
            for key in ("duration_seconds", "estimated_duration_seconds"):
                try:
                    value = float(section.get(key))
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    return value
    script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
    script_text = compact_text(script.get("text") if isinstance(script, dict) else "")
    return max(30.0, len(script_text.split()) / 145 * 60)


def build_story_segments(manifest: dict[str, Any], *, target_count: int = 5) -> list[StorySegment]:
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
    visual_handoff = visual_handoff_for_manifest(manifest)
    duration = _duration(manifest)
    category = compact_text((script or {}).get("category") or (raw or {}).get("category"))
    claim_texts = [
        compact_text(claim.get("text"))
        for claim in (raw or {}).get("claims", [])
        if isinstance(claim, dict) and compact_text(claim.get("text"))
    ]
    facts = unique(
        [
            *claim_texts,
            *[compact_text(fact) for fact in (raw or {}).get("facts", []) if compact_text(fact)],
        ]
    )
    summary = compact_text((raw or {}).get("summary"))
    script_text = compact_text((script or {}).get("text"))
    planning_context = " ".join(
        [
            *visual_handoff.get("entities", []),
            *visual_handoff.get("visual_opportunities", []),
            compact_text(visual_handoff.get("why_it_matters")),
            compact_text(visual_handoff.get("synthpost_angle")),
        ]
    )
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for headline_item in _headline_items(manifest):
        _add_item(items, seen, headline_item["text"], start=headline_item.get("start"), end=headline_item.get("end"))

    _add_item(items, seen, (script or {}).get("headline") or (raw or {}).get("headline_source") or "SynthPost briefing")
    for fact in facts:
        _add_item(items, seen, fact)
    for sentence in split_sentences(script_text):
        _add_item(items, seen, sentence)
    _add_item(items, seen, summary)

    items = items[: max(1, target_count)]
    count = len(items)
    timed = any("start" in item for item in items)

    segments: list[StorySegment] = []
    for index, item in enumerate(items):
        start = float(item.get("start", index * duration / count))
        if "end" in item:
            end = float(item["end"])
        elif timed and index + 1 < count and "start" in items[index + 1]:
            end = float(items[index + 1]["start"])
        else:
            end = (index + 1) * duration / count
        end = min(duration, max(start + 2.0, end))
        fact = facts[index % len(facts)] if facts else ""
        text = " ".join(part for part in [item["text"], fact, summary, planning_context, script_text[:600]] if part)
        keywords = keyword_phrases(text, category)
        segments.append(
            StorySegment(
                segment_id=f"seg_{index + 1:02d}",
                title=compact_text(item["text"]),
                text=text,
                start=round(start, 2),
                end=round(end, 2),
                keywords=keywords,
            )
        )

    if segments:
        segments.sort(key=lambda segment: segment.start)
        for index, segment in enumerate(segments[:-1]):
            segment.end = round(max(segment.start + 2.0, min(duration, segments[index + 1].start)), 2)
        segments[-1].end = round(duration, 2)
    return segments


def desired_types_for_segment(segment: StorySegment, category: str) -> list[AssetType]:
    desired: list[AssetType] = [AssetType.VIDEO, AssetType.IMAGE]
    haystack = f"{segment.title} {' '.join(segment.keywords)} {category}".lower()
    for key, hints in TYPE_HINTS.items():
        if key in haystack:
            desired.extend(hints)
    if category.lower() in {"conflict", "world", "politics", "geopolitics"}:
        desired.extend([AssetType.MAP, AssetType.SATELLITE, AssetType.SCREENSHOT])
    if category.lower() in {"economy", "business", "energy"}:
        desired.extend([AssetType.CHART, AssetType.MAP, AssetType.DOCUMENT])
    desired.append(AssetType.GENERATED)
    seen: set[AssetType] = set()
    result: list[AssetType] = []
    for item in desired:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_visual_queries(manifest: dict[str, Any], segments: list[StorySegment]) -> list[VisualQuery]:
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
    visual_handoff = visual_handoff_for_manifest(manifest)
    source_metadata = visual_handoff.get("source_metadata") if isinstance(visual_handoff.get("source_metadata"), dict) else {}
    category = compact_text((script or {}).get("category") or (raw or {}).get("category"))
    source_name = compact_text((raw or {}).get("source_name") or source_metadata.get("source_name") or source_metadata.get("source"))
    source_host = _source_host(manifest) or compact_text(source_metadata.get("source_domain"))
    entities = visual_handoff.get("entities", [])
    visual_opportunities = visual_handoff.get("visual_opportunities", [])
    queries: list[VisualQuery] = []
    for segment in segments:
        keywords = unique(segment.keywords, limit=10)
        query_terms = unique(
            [
                segment.title,
                source_name,
                source_host,
                category,
                *entities[:3],
                *visual_opportunities[:2],
                *keywords[:5],
            ],
            limit=9,
        )
        queries.append(
            VisualQuery(
                segment_id=segment.segment_id,
                query=" ".join(query_terms),
                keywords=keywords,
                desired_types=desired_types_for_segment(segment, category),
                start=segment.start,
                end=segment.end,
            )
        )
    return queries
