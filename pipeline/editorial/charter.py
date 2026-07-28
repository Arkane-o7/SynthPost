from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from pipeline.channels import ChannelId, get_channel_profile
from pipeline.models import EditorialFitAssessment, SourceDefinition
from pipeline.storage import PROJECT_ROOT


CHARTER_PATH = PROJECT_ROOT / "editorial" / "charters" / "synthpost.v1.json"


@lru_cache(maxsize=1)
def load_editorial_charter() -> dict[str, Any]:
    return json.loads(CHARTER_PATH.read_text(encoding="utf-8"))


CHARTER_VERSION = str(load_editorial_charter()["version"])


def _contains(text: str, phrase: str) -> bool:
    normalized = phrase.casefold().strip()
    if not normalized:
        return False
    left = r"(?<!\w)" if normalized[0].isalnum() else ""
    right = r"(?!\w)" if normalized[-1].isalnum() else ""
    return bool(re.search(f"{left}{re.escape(normalized)}{right}", text))


def _matched_phrases(text: str, phrases: list[str]) -> list[str]:
    return [phrase for phrase in phrases if _contains(text, phrase)]


def _topic_scores(text: str) -> dict[str, int]:
    charter = load_editorial_charter()
    return {
        topic: len(_matched_phrases(text, phrases))
        for topic, phrases in charter["priority_verticals"].items()
    }


def assess_editorial_fit(
    source: SourceDefinition,
    title: str,
    summary: str,
    channel_id: ChannelId = "synthpost",
) -> EditorialFitAssessment:
    if channel_id != "synthpost":
        return _assess_channel_fit(source, title, summary, channel_id)
    charter = load_editorial_charter()
    text = f"{title} {summary}".casefold()
    padded_text = f" {text} "
    desk = charter["assignment_desk"]
    topic_scores = _topic_scores(text)
    primary_topic = max(topic_scores, key=topic_scores.get) if any(topic_scores.values()) else "general"
    topic_terms = [
        phrase
        for phrases in charter["priority_verticals"].values()
        for phrase in phrases
        if _contains(text, phrase)
    ]
    strategic_terms = _matched_phrases(padded_text, desk["strategic_signals"])
    system_scale_terms = _matched_phrases(text, desk["system_scale_signals"])
    india_terms = _matched_phrases(text, desk["india_impact_signals"])
    global_terms = _matched_phrases(padded_text, desk["global_context_signals"])
    impact_terms = _matched_phrases(
        text,
        [
            "people", "public", "consumer", "worker", "farmer", "student",
            "patient", "household", "community", "citizen", "jobs", "prices",
            "safety", "health", "transport", "electricity", "water",
        ],
    )
    tradeoff_terms = _matched_phrases(
        text,
        [
            "but", "however", "while", "risk", "cost", "challenge", "gap",
            "shortfall", "delay", "versus", "despite", "uncertain", "concern",
            "bottleneck", "trade-off", "tradeoff",
        ],
    )
    visual_terms = _matched_phrases(
        text,
        [
            "map", "data", "chart", "satellite", "launch", "factory", "rail",
            "metro", "port", "road", "grid", "plant", "document", "court",
            "protest", "flood", "fire", "demonstration", "prototype", "facility",
        ],
    )
    consequence_terms = _matched_phrases(
        text,
        [
            "policy", "regulation", "law", "court", "supply chain", "economy",
            "market", "security", "infrastructure", "public", "industry", "trade",
            "energy", "climate", "standards", "ban", "approval", "investment",
        ],
    )
    durable_terms = _matched_phrases(
        text,
        [
            "strategy", "system", "policy", "infrastructure", "research", "plan",
            "mission", "transition", "supply chain", "regulation", "economy",
            "manufacturing", "capacity", "investment",
        ],
    )

    criteria: list[str] = []
    has_strategic_subject = bool(strategic_terms)
    has_system_scale = bool(system_scale_terms)
    india_origin = source.country == "in"
    has_explicit_india_angle = bool(india_terms)
    # Global shifts may enter the desk with a hypothesis to investigate, but
    # they no longer receive a fabricated "India connection" signal. The
    # assignment desk writes the actual hypothesis and its confidence later.
    has_developable_india_angle = has_explicit_india_angle or (
        not india_origin and has_strategic_subject and has_system_scale
    )
    has_global_scope = bool(global_terms) or (
        not india_origin and source.category not in {"general", "india", "local"}
    )

    if has_strategic_subject and has_system_scale:
        criteria.append("system_change")
    if impact_terms and has_system_scale:
        criteria.append("meaningful_impact")
    if has_explicit_india_angle:
        criteria.append("india_connection")
    if tradeoff_terms:
        criteria.append("tradeoff_or_uncertainty")
    if visual_terms or (has_strategic_subject and primary_topic in {"infrastructure", "science", "energy"}):
        criteria.append("visual_explainability")
    if source.reliability_score >= 0.75:
        criteria.append("credible_evidence")
    if consequence_terms and has_system_scale:
        criteria.append("beyond_announcement")
    if durable_terms and has_strategic_subject:
        criteria.append("durable_value")

    rejection_signals: list[str] = []
    for signal, patterns in charter["reject_patterns"].items():
        if _matched_phrases(text, patterns):
            rejection_signals.append(signal)
    for signal, patterns in desk["automatic_rejections"].items():
        if _matched_phrases(text, patterns):
            rejection_signals.append(signal)

    if not has_strategic_subject:
        rejection_signals.append("no_strategic_technology_or_system_subject")
    if not has_system_scale:
        rejection_signals.append("no_system_scale_consequence")
    if india_origin and not (
        has_global_scope or (has_strategic_subject and has_system_scale)
    ):
        rejection_signals.append("local_story_without_global_or_industry_significance")
    if not has_developable_india_angle:
        rejection_signals.append("no_developable_india_angle")
    rejection_signals = list(dict.fromkeys(rejection_signals))

    minimum = int(charter["minimum_eligibility_matches"])
    base = len(criteria) / len(charter["eligibility_criteria"])
    focus_bonus = min(0.18, sum(topic_scores.values()) * 0.025)
    india_bonus = 0.08 if has_explicit_india_angle else 0.0
    penalty = min(0.75, len(rejection_signals) * 0.34)
    score = max(0.0, min(1.0, base + focus_bonus + india_bonus - penalty))
    eligible = (
        len(criteria) >= minimum
        and has_strategic_subject
        and has_system_scale
        and has_developable_india_angle
        and not rejection_signals
    )

    labels = {
        item["id"]: item["label"] for item in charter["eligibility_criteria"]
    }
    strengths = [labels[item] for item in criteria]
    reasons = [
        f"Charter fit {round(score * 100)}% · {len(criteria)}/{len(labels)} signals",
        *strengths,
    ]
    if rejection_signals:
        reasons.extend(
            f"Off-charter signal: {signal.replace('_', ' ')}"
            for signal in rejection_signals
        )
    elif len(criteria) < minimum:
        reasons.append(f"Needs at least {minimum} charter signals")

    return EditorialFitAssessment(
        charter_version=CHARTER_VERSION,
        score=round(score, 3),
        eligible=eligible,
        primary_topic=primary_topic,
        matched_criteria=criteria,
        strengths=strengths,
        penalties=[signal.replace("_", " ") for signal in rejection_signals],
        rejection_signals=rejection_signals,
        india_relevance=round(min(1.0, 0.42 + 0.2 * len(india_terms)), 3)
        if has_explicit_india_angle
        else 0.0,
        reasons=reasons,
    )


_CHANNEL_TOPIC_TERMS: dict[ChannelId, dict[str, tuple[str, ...]]] = {
    "synthpost": {},
    "meridian": {
        "markets": ("market", "stocks", "bonds", "equity", "investor", "trading"),
        "companies": ("company", "business", "earnings", "revenue", "merger", "bankruptcy"),
        "economics": ("economy", "inflation", "interest rate", "central bank", "gdp", "currency"),
        "financial_systems": ("bank", "credit", "debt", "mortgage", "fund", "capital", "finance"),
    },
    "beyond": {
        "geopolitics": ("war", "conflict", "diplomacy", "sanctions", "border", "military"),
        "world_news": ("government", "election", "president", "minister", "parliament", "protest"),
        "global_economy": ("trade", "tariff", "oil", "shipping", "currency", "global economy"),
        "security": ("security", "attack", "ceasefire", "treaty", "nuclear", "defence", "defense"),
    },
}


def _assess_channel_fit(
    source: SourceDefinition,
    title: str,
    summary: str,
    channel_id: ChannelId,
) -> EditorialFitAssessment:
    """Score non-SynthPost desks without inheriting the India-specific charter."""

    profile = get_channel_profile(channel_id)
    text = f"{title} {summary}".casefold()
    topic_hits = {
        topic: [term for term in terms if _contains(text, term)]
        for topic, terms in _CHANNEL_TOPIC_TERMS[channel_id].items()
    }
    primary_topic = max(topic_hits, key=lambda topic: len(topic_hits[topic]))
    matched_topics = [topic for topic, terms in topic_hits.items() if terms]
    consequence_terms = _matched_phrases(
        text,
        [
            "policy", "law", "court", "prices", "jobs", "trade", "security",
            "industry", "market", "economy", "public", "supply chain", "investment",
            "regulation", "election", "conflict", "bank", "debt",
        ],
    )
    development_terms = _matched_phrases(
        text,
        [
            "approves", "bans", "cuts", "raises", "launches", "passes", "rules",
            "signs", "invests", "acquires", "merges", "files", "strikes", "orders",
            "announces", "reports", "falls", "rises",
        ],
    )
    visual_terms = _matched_phrases(
        text,
        ["data", "chart", "map", "document", "speech", "protest", "factory", "port", "market"],
    )
    criteria: list[str] = []
    if matched_topics:
        criteria.append("channel_subject")
    if consequence_terms:
        criteria.append("consequence")
    if development_terms:
        criteria.append("new_development")
    if visual_terms:
        criteria.append("visual_explainability")
    if source.reliability_score >= 0.7:
        criteria.append("credible_evidence")

    rejection_signals: list[str] = []
    if not matched_topics:
        rejection_signals.append("outside_channel_focus")
    if any(term in text for term in ("celebrity gossip", "horoscope", "shopping deal", "coupon")):
        rejection_signals.append("low_consequence_lifestyle_content")

    score = min(
        1.0,
        0.12
        + min(0.42, sum(len(terms) for terms in topic_hits.values()) * 0.07)
        + min(0.24, len(consequence_terms) * 0.06)
        + min(0.14, len(development_terms) * 0.07)
        + (0.08 if source.reliability_score >= 0.7 else 0.0),
    )
    if rejection_signals:
        score = min(score, 0.24)
    eligible = score >= 0.48 and not rejection_signals
    strengths = [item.replace("_", " ") for item in criteria]
    reasons = [
        f"{profile.name} fit {round(score * 100)}%",
        *strengths,
        *(f"Off-channel signal: {item.replace('_', ' ')}" for item in rejection_signals),
    ]
    return EditorialFitAssessment(
        charter_version=f"{channel_id}.{profile.profile_version}",
        score=round(score, 3),
        eligible=eligible,
        primary_topic=primary_topic,
        matched_criteria=criteria,
        strengths=strengths,
        penalties=[item.replace("_", " ") for item in rejection_signals],
        rejection_signals=rejection_signals,
        india_relevance=0.0,
        reasons=reasons,
    )


def show_format_for(target_duration_seconds: int, primary_topic: str = "") -> str:
    if primary_topic in {"infrastructure", "energy", "science"} and 420 <= target_duration_seconds <= 1080:
        return "india_builds"
    if target_duration_seconds <= 300:
        return "signal"
    if target_duration_seconds <= 720:
        return "explained"
    return "deep_dive"


def normalize_narration_mode(
    narration_mode: str | None,
    *,
    target_duration_seconds: int = 600,
    primary_topic: str = "",
) -> str:
    raw_value = getattr(narration_mode, "value", narration_mode)
    value = str(raw_value or "").strip().lower()
    if value in load_editorial_charter()["show_formats"]:
        return value
    return show_format_for(target_duration_seconds, primary_topic)


def charter_prompt_context(*, show_format: str) -> str:
    charter = load_editorial_charter()
    selected_format = normalize_narration_mode(show_format)
    show = charter["show_formats"][selected_format]
    influence = charter["editorial_influence"]
    return "\n".join(
        [
            f"EDITORIAL CHARTER: {charter['charter_id']} v{charter['version']}",
            f"Promise: {charter['editorial_promise']}",
            f"Lens: {charter['lens']}",
            "Voice: " + "; ".join(charter["tone"]),
            f"Format: {show['label']}",
            "Narration profile: " + "; ".join(show["narration"]),
            "Shared narration rules: " + "; ".join(charter["narration_principles"]),
            "Avoid in narration: " + "; ".join(charter["narration_avoid"]),
            "Editorial blend: "
            f"{round(influence['verge_editorial_model'] * 100)}% technology-society editorial lens; "
            f"{round(influence['aim_subject_focus'] * 100)}% India technology subject depth; "
            f"{round(influence['firstpost_video_presentation'] * 100)}% presenter-led broadcast discipline.",
            "Research lens: " + "; ".join(charter["research_lens"]),
            "Preferred visuals: " + "; ".join(charter["visual_preferences"]),
        ]
    )


def narration_prompt_context(*, show_format: str) -> str:
    """Return only the charter rules needed to write spoken narration.

    The broader charter context also contains research and visual-production
    policy. Injecting those unrelated rules into the writer prompt makes the
    core editorial task harder to follow and needlessly consumes context.
    """

    charter = load_editorial_charter()
    selected_format = normalize_narration_mode(show_format)
    show = charter["show_formats"][selected_format]
    return "\n".join(
        [
            f"Editorial promise: {charter['editorial_promise']}",
            "Voice: " + "; ".join(charter["tone"]),
            f"Format: {show['label']}",
            "Format structure: " + " -> ".join(show["structure"]),
            "Narration profile: " + "; ".join(show["narration"]),
            "Shared narration rules: " + "; ".join(charter["narration_principles"]),
            "Avoid in narration: " + "; ".join(charter["narration_avoid"]),
        ]
    )
