from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from ..storage import episode_dir


SCORE_FIELDS = (
    "importance_score",
    "viral_potential_score",
    "visual_potential_score",
    "freshness_score",
    "source_reliability_score",
    "synthpost_fit_score",
    "controversy_or_tension_score",
    "explainability_score",
    "final_editorial_score",
)

EDITORIAL_FIELDS = (
    "why_it_matters",
    "why_it_could_perform_well",
    "possible_synthpost_angle",
    "possible_thumbnail_hook",
    "possible_title_ideas",
    "visual_opportunities",
    "risks_or_reasons_to_avoid",
    "selection_reason",
    "rejection_reason",
)


class StorySourceProvider(Protocol):
    name: str

    def collect(self, *, limit: int) -> list["CandidateStory"]:
        ...


def compact_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_headline(value: object) -> str:
    text = compact_text(value).lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
    tokens = [token for token in text.split() if token not in stopwords]
    return " ".join(tokens)


def source_domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").removeprefix("www.")
    except ValueError:
        return ""


def candidate_id_for(*values: object) -> str:
    payload = "|".join(compact_text(value).lower() for value in values if compact_text(value))
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"cand_{digest}"


def cluster_id_for(headline: object, source_url: object = "") -> str:
    normalized = normalize_headline(headline)
    domain = source_domain(compact_text(source_url))
    key = " ".join(normalized.split()[:8]) or compact_text(headline).lower()
    digest = hashlib.sha1(f"{domain}|{key}".encode("utf-8")).hexdigest()[:12]
    return f"cluster_{digest}"


def split_sentences(value: object) -> list[str]:
    text = compact_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if len(part.split()) >= 4]


def normalize_category(value: object, *, source_url: str = "", source_name: str = "") -> str:
    text = compact_text(value).lower()
    haystack = " ".join([text, source_url.lower(), source_name.lower()])
    categories = {
        "ai": ("ai", "artificial intelligence", "openai", "nvidia", "chip"),
        "technology": ("technology", "tech", "software", "semiconductor", "startup"),
        "india": ("india", "delhi", "mumbai", "pib", "hindustan"),
        "economy": ("economy", "market", "inflation", "tariff", "trade", "central bank"),
        "energy": ("energy", "power", "grid", "oil", "gas", "electricity"),
        "geopolitics": ("geopolitics", "china", "russia", "iran", "border", "war"),
        "defense": ("defense", "military", "missile", "army", "navy", "air force"),
        "climate": ("climate", "weather", "flood", "heat", "wildfire", "cyclone"),
        "business": ("business", "earnings", "company", "merger", "ipo"),
        "global": ("world", "global", "international"),
    }
    for category, markers in categories.items():
        if any(marker in haystack for marker in markers):
            return category
    return text or "general"


def normalize_datetime(value: object) -> str:
    text = compact_text(value)
    if not text:
        return ""
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except ValueError:
        return text


def extract_facts(summary: object, headline: object = "") -> list[str]:
    facts = split_sentences(summary)
    if not facts and compact_text(summary):
        facts = [compact_text(summary)]
    if not facts and compact_text(headline):
        facts = [compact_text(headline)]
    seen: set[str] = set()
    result: list[str] = []
    for fact in facts:
        key = fact.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(fact)
    return result[:8]


def extract_entities(*values: object) -> list[str]:
    text = " ".join(compact_text(value) for value in values if compact_text(value))
    acronyms = re.findall(r"\b[A-Z][A-Z0-9&.-]{1,}\b", text)
    phrases = re.findall(r"\b(?:[A-Z][a-zA-Z0-9&.-]+)(?:\s+(?:[A-Z][a-zA-Z0-9&.-]+|of|and|the)){0,4}", text)
    blocked = {"The", "A", "An", "This", "That", "For", "With", "From", "In", "On"}
    entities: list[str] = []
    seen: set[str] = set()
    expanded_phrases: list[str] = []
    for phrase in phrases:
        expanded_phrases.append(phrase)
        expanded_phrases.extend(
            token
            for token in re.split(r"\s+(?:and|of|the)\s+|\s+", phrase)
            if token and token[:1].isupper()
        )
    for value in [*acronyms, *expanded_phrases]:
        entity = compact_text(value).strip(".,:;!?")
        if not entity or entity in blocked or len(entity) < 2:
            continue
        key = entity.lower()
        if key in seen:
            continue
        seen.add(key)
        entities.append(entity)
    return entities[:16]


def default_title_ideas(headline: str) -> list[str]:
    clean = compact_text(headline).rstrip(".")
    return [clean] if clean else []


def default_visual_opportunities(headline: str, entities: list[str], category: str) -> list[str]:
    opportunities = []
    if entities:
        opportunities.append(f"Official visuals or file footage involving {entities[0]}")
    category_prompts = {
        "ai": "Data centers, chips, product demos, company events, or regulatory documents",
        "technology": "Product demos, company footage, app screenshots, or semiconductor visuals",
        "energy": "Grid infrastructure, power plants, maps, charts, and regulatory documents",
        "geopolitics": "Maps, leader footage, official briefings, satellite imagery, or border visuals",
        "defense": "Official defense footage, maps, briefings, or equipment visuals",
        "climate": "Satellite imagery, maps, disaster footage, charts, and local site visuals",
        "economy": "Market charts, ports, factories, central bank footage, and commodity visuals",
        "business": "Company footage, leadership clips, charts, filings, and product visuals",
        "india": "PB-SHABD, PIB, ministry media, maps, and official documents",
    }
    opportunities.append(category_prompts.get(category, "Official footage, source screenshots, maps, and document visuals"))
    if headline:
        opportunities.append(f"Headline/source-page screenshot for: {headline}")
    return opportunities[:5]


@dataclass(frozen=True)
class CandidateStory:
    headline: str
    source_name: str
    source_url: str
    published_at: str = ""
    category: str = "general"
    summary: str = ""
    facts: list[str] = field(default_factory=list)
    key_entities: list[str] = field(default_factory=list)
    candidate_id: str = ""
    cluster_id: str = ""
    normalized_headline: str = ""
    source_reliability_tier: str = "unknown"
    source_ids: list[str] = field(default_factory=lambda: ["source_01"])
    claim_ids: list[str] = field(default_factory=list)
    why_it_matters: str = ""
    why_it_could_perform_well: str = ""
    possible_synthpost_angle: str = ""
    possible_thumbnail_hook: str = ""
    possible_title_ideas: list[str] = field(default_factory=list)
    visual_opportunities: list[str] = field(default_factory=list)
    risks_or_reasons_to_avoid: list[str] = field(default_factory=list)
    selection_reason: str = ""
    rejection_reason: str = ""
    importance_score: float = 0.0
    viral_potential_score: float = 0.0
    visual_potential_score: float = 0.0
    freshness_score: float = 0.0
    source_reliability_score: float = 0.0
    synthpost_fit_score: float = 0.0
    controversy_or_tension_score: float = 0.0
    explainability_score: float = 0.0
    final_editorial_score: float = 0.0

    @property
    def headline_source(self) -> str:
        return self.headline

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "cluster_id": self.cluster_id,
            "headline": self.headline,
            "normalized_headline": self.normalized_headline,
            "source": self.source_name,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "published_at": self.published_at,
            "category": self.category,
            "summary": self.summary,
            "facts": list(self.facts),
            "key_entities": list(self.key_entities),
            "source_reliability_tier": self.source_reliability_tier,
            "source_ids": list(self.source_ids),
            "claim_ids": list(self.claim_ids),
            "why_it_matters": self.why_it_matters,
            "why_it_could_perform_well": self.why_it_could_perform_well,
            "possible_synthpost_angle": self.possible_synthpost_angle,
            "possible_thumbnail_hook": self.possible_thumbnail_hook,
            "possible_title_ideas": list(self.possible_title_ideas),
            "visual_opportunities": list(self.visual_opportunities),
            "risks_or_reasons_to_avoid": list(self.risks_or_reasons_to_avoid),
            "selection_reason": self.selection_reason,
            "rejection_reason": self.rejection_reason,
        }
        for field_name in SCORE_FIELDS:
            record[field_name] = float(getattr(self, field_name))
        return record

    def to_raw(self) -> dict[str, Any]:
        source = {
            "source_id": "source_01",
            "name": self.source_name,
            "url": self.source_url,
            "title": self.headline,
            "published_at": self.published_at,
            "source_type": "rss",
        }
        claims = [
            {
                "claim_id": claim_id,
                "text": fact,
                "source_ids": ["source_01"],
                "evidence": [{"source_id": "source_01", "url": self.source_url, "quote": fact}],
                "confidence": "source_reported",
                "status": "supported",
            }
            for claim_id, fact in zip(self.claim_ids, self.facts, strict=False)
        ]
        return {
            "headline_source": self.headline,
            "summary": self.summary,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "category": self.category,
            "published_at": self.published_at,
            "facts": list(self.facts),
            "key_entities": list(self.key_entities),
            "visual_opportunities": list(self.visual_opportunities),
            "title_ideas": list(self.possible_title_ideas),
            "thumbnail_hooks": [self.possible_thumbnail_hook] if self.possible_thumbnail_hook else [],
            "editorial": {
                "candidate_id": self.candidate_id,
                "cluster_id": self.cluster_id,
                "why_it_matters": self.why_it_matters,
                "why_it_could_perform_well": self.why_it_could_perform_well,
                "possible_synthpost_angle": self.possible_synthpost_angle,
                "risks_or_reasons_to_avoid": list(self.risks_or_reasons_to_avoid),
            },
            "sources": [source],
            "claims": claims,
        }


def build_candidate_story(
    *,
    headline: object,
    source_name: object,
    source_url: object,
    published_at: object = "",
    category: object = "",
    summary: object = "",
    facts: list[str] | None = None,
    key_entities: list[str] | None = None,
) -> CandidateStory:
    clean_headline = compact_text(headline)
    clean_source_name = compact_text(source_name) or source_domain(compact_text(source_url)) or "Unknown source"
    clean_source_url = compact_text(source_url)
    clean_summary = compact_text(summary)
    clean_published = normalize_datetime(published_at)
    clean_category = normalize_category(category, source_url=clean_source_url, source_name=clean_source_name)
    normalized = normalize_headline(clean_headline)
    resolved_facts = [compact_text(fact) for fact in (facts or []) if compact_text(fact)] or extract_facts(
        clean_summary,
        clean_headline,
    )
    entities = key_entities or extract_entities(clean_headline, clean_summary, clean_source_name)
    claim_ids = [f"claim_{index:02d}" for index, _ in enumerate(resolved_facts, start=1)]
    title_ideas = default_title_ideas(clean_headline)
    thumbnail_hook = clean_headline
    visual_opportunities = default_visual_opportunities(clean_headline, entities, clean_category)
    return CandidateStory(
        candidate_id=candidate_id_for(clean_source_url, clean_headline, clean_source_name),
        cluster_id=cluster_id_for(clean_headline, clean_source_url),
        headline=clean_headline,
        normalized_headline=normalized,
        source_name=clean_source_name,
        source_url=clean_source_url,
        published_at=clean_published,
        category=clean_category,
        summary=clean_summary,
        facts=resolved_facts,
        key_entities=entities,
        claim_ids=claim_ids,
        possible_title_ideas=title_ideas,
        possible_thumbnail_hook=thumbnail_hook,
        visual_opportunities=visual_opportunities,
    )


def candidates_payload(episode_id: str, candidates: list[CandidateStory]) -> dict[str, Any]:
    return {
        "episode_id": episode_id,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "candidate_count": len(candidates),
        "candidates": [candidate.to_record() for candidate in candidates],
    }


def write_story_candidates(
    episode_id: str,
    candidates: list[CandidateStory],
    *,
    output_path: str | Path | None = None,
) -> Path:
    path = Path(output_path) if output_path else episode_dir(episode_id) / "story_candidates.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(candidates_payload(episode_id, candidates), handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    return path
