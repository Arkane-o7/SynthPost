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
    duration = _duration(manifest)
    category = compact_text((script or {}).get("category") or (raw or {}).get("category"))
    facts = [compact_text(fact) for fact in (raw or {}).get("facts", []) if compact_text(fact)]
    summary = compact_text((raw or {}).get("summary"))
    script_text = compact_text((script or {}).get("text"))
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
        text = " ".join(part for part in [item["text"], fact, summary, script_text[:600]] if part)
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
    category = compact_text((script or {}).get("category") or (raw or {}).get("category"))
    source_name = compact_text((raw or {}).get("source_name"))
    source_host = _source_host(manifest)
    queries: list[VisualQuery] = []
    for segment in segments:
        keywords = unique(segment.keywords, limit=10)
        query_terms = unique([segment.title, source_name, source_host, category, *keywords[:5]], limit=9)
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
