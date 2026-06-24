from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from datetime import datetime, timezone

from .candidates import CandidateStory, SCORE_FIELDS, compact_text


DEFAULT_SCORE_WEIGHTS: dict[str, float] = {
    "importance_score": 0.20,
    "viral_potential_score": 0.18,
    "synthpost_fit_score": 0.14,
    "visual_potential_score": 0.12,
    "explainability_score": 0.12,
    "source_reliability_score": 0.10,
    "freshness_score": 0.08,
    "controversy_or_tension_score": 0.06,
}

SYNTHPOST_CATEGORIES = {
    "ai",
    "technology",
    "india",
    "economy",
    "energy",
    "geopolitics",
    "defense",
    "climate",
    "business",
    "global",
}

LOW_FIT_CATEGORIES = {"celebrity", "entertainment", "sports", "lifestyle"}

PUBLIC_INTEREST_TERMS = {
    "ai",
    "algorithm",
    "antitrust",
    "bankruptcy",
    "border",
    "central bank",
    "chip",
    "climate",
    "congress",
    "court",
    "data",
    "defense",
    "economy",
    "election",
    "energy",
    "fraud",
    "government",
    "inflation",
    "market",
    "ministry",
    "military",
    "money",
    "national security",
    "policy",
    "regulator",
    "security",
    "supply chain",
    "tariff",
    "technology",
    "war",
}

IMPORTANCE_TERMS = {
    "ai",
    "army",
    "ban",
    "bank",
    "border",
    "central bank",
    "chip",
    "china",
    "climate",
    "conflict",
    "congress",
    "court",
    "crisis",
    "defense",
    "economy",
    "energy",
    "export controls",
    "federal",
    "government",
    "grid",
    "india",
    "inflation",
    "market",
    "military",
    "ministry",
    "missile",
    "nasa",
    "nvidia",
    "openai",
    "parliament",
    "policy",
    "regulator",
    "russia",
    "sanction",
    "security",
    "semiconductor",
    "tariff",
    "trade",
    "war",
}

VIRAL_TERMS = {
    "ban",
    "battle",
    "clash",
    "collapse",
    "crackdown",
    "crisis",
    "deadline",
    "first",
    "historic",
    "major",
    "record",
    "race",
    "shock",
    "shortage",
    "surge",
    "threat",
    "warns",
}

VISUAL_TERMS = {
    "briefing",
    "chart",
    "document",
    "drone",
    "factory",
    "footage",
    "image",
    "map",
    "photo",
    "port",
    "satellite",
    "screenshot",
    "ship",
    "video",
    "visual",
}

TENSION_TERMS = {
    "accused",
    "attack",
    "border",
    "clash",
    "conflict",
    "crisis",
    "deadline",
    "dispute",
    "pressure",
    "risk",
    "sanction",
    "scrutiny",
    "tension",
    "threat",
    "war",
    "warning",
}

KNOWN_RELIABLE_DOMAINS = {
    "apnews.com",
    "bbc.com",
    "bloomberg.com",
    "cnbc.com",
    "dw.com",
    "firstpost.com",
    "ft.com",
    "nasa.gov",
    "pib.gov.in",
    "reuters.com",
    "theverge.com",
    "whitehouse.gov",
    "wionews.com",
}


def configured_score_weights() -> dict[str, float]:
    raw = os.environ.get("SYNTHPOST_EDITORIAL_SCORE_WEIGHTS", "")
    if not raw:
        return dict(DEFAULT_SCORE_WEIGHTS)
    try:
        incoming = json.loads(raw)
    except json.JSONDecodeError:
        return dict(DEFAULT_SCORE_WEIGHTS)
    if not isinstance(incoming, dict):
        return dict(DEFAULT_SCORE_WEIGHTS)
    weights = dict(DEFAULT_SCORE_WEIGHTS)
    for key, value in incoming.items():
        if key in weights:
            try:
                weights[key] = float(value)
            except (TypeError, ValueError):
                continue
    total = sum(weight for weight in weights.values() if weight > 0)
    if total <= 0:
        return dict(DEFAULT_SCORE_WEIGHTS)
    return {key: max(value, 0.0) / total for key, value in weights.items()}


def rank_candidates(
    candidates: list[CandidateStory],
    *,
    select_count: int = 1,
    now: datetime | None = None,
    weights: dict[str, float] | None = None,
) -> list[CandidateStory]:
    scored = [score_candidate(candidate, now=now, weights=weights) for candidate in candidates]
    ranked = sorted(scored, key=lambda candidate: candidate.final_editorial_score, reverse=True)
    selected_left = max(select_count, 0)
    output: list[CandidateStory] = []
    for candidate in ranked:
        if candidate.rejection_reasons:
            output.append(
                replace(
                    candidate,
                    selection_status="rejected",
                    selection_reason="",
                    rejection_reason="; ".join(candidate.rejection_reasons),
                )
            )
            continue
        if selected_left > 0:
            selected_left -= 1
            output.append(
                replace(
                    candidate,
                    selection_status="selected",
                    selection_reason=(
                        f"Selected as the highest-ranked acceptable story "
                        f"(final editorial score {candidate.final_editorial_score:.1f})."
                    ),
                )
            )
        else:
            output.append(replace(candidate, selection_status="candidate", selection_reason=""))
    return output


def selected_candidates(candidates: list[CandidateStory]) -> list[CandidateStory]:
    return [candidate for candidate in candidates if candidate.selection_status == "selected"]


def score_candidate(
    candidate: CandidateStory,
    *,
    now: datetime | None = None,
    weights: dict[str, float] | None = None,
) -> CandidateStory:
    now = now or datetime.now(timezone.utc)
    weights = weights or configured_score_weights()
    text = _candidate_text(candidate)
    importance, importance_reason = _importance_score(candidate, text)
    viral, viral_reason = _viral_score(candidate, text)
    visual, visual_reason = _visual_score(candidate, text)
    freshness, freshness_reason = _freshness_score(candidate, now)
    reliability, reliability_reason = _source_reliability_score(candidate)
    fit, fit_reason = _synthpost_fit_score(candidate, text)
    tension, tension_reason = _tension_score(candidate, text)
    explainability, explainability_reason = _explainability_score(candidate, text)

    score_values = {
        "importance_score": importance,
        "viral_potential_score": viral,
        "visual_potential_score": visual,
        "freshness_score": freshness,
        "source_reliability_score": reliability,
        "synthpost_fit_score": fit,
        "controversy_or_tension_score": tension,
        "explainability_score": explainability,
    }
    final = round(sum(score_values[key] * weights.get(key, 0.0) for key in score_values), 2)
    rejection_reasons = _rejection_reasons(
        candidate,
        score_values=score_values,
        final_score=final,
        text=text,
    )
    status = "rejected" if rejection_reasons else "candidate"
    score_reasons = {
        "importance_score": importance_reason,
        "viral_potential_score": viral_reason,
        "visual_potential_score": visual_reason,
        "freshness_score": freshness_reason,
        "source_reliability_score": reliability_reason,
        "synthpost_fit_score": fit_reason,
        "controversy_or_tension_score": tension_reason,
        "explainability_score": explainability_reason,
        "final_editorial_score": _final_reason(score_values, weights, final),
    }
    return replace(
        candidate,
        selection_status=status,
        selection_reason="",
        rejection_reason="; ".join(rejection_reasons),
        rejection_reasons=rejection_reasons,
        score_reasons=score_reasons,
        importance_score=importance,
        viral_potential_score=viral,
        visual_potential_score=visual,
        freshness_score=freshness,
        source_reliability_score=reliability,
        synthpost_fit_score=fit,
        controversy_or_tension_score=tension,
        explainability_score=explainability,
        final_editorial_score=final,
    )


def _candidate_text(candidate: CandidateStory) -> str:
    return " ".join(
        compact_text(value)
        for value in [
            candidate.headline,
            candidate.category,
            candidate.summary,
            " ".join(candidate.facts),
            " ".join(candidate.key_entities),
            " ".join(candidate.visual_opportunities),
            candidate.why_it_matters,
            candidate.why_it_could_perform_well,
        ]
        if compact_text(value)
    ).lower()


def _keyword_hits(text: str, terms: set[str]) -> list[str]:
    return sorted(term for term in terms if re.search(rf"\b{re.escape(term)}\b", text))


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _importance_score(candidate: CandidateStory, text: str) -> tuple[float, str]:
    hits = _keyword_hits(text, IMPORTANCE_TERMS)
    base = 42 if candidate.category in SYNTHPOST_CATEGORIES else 28
    score = base + len(hits) * 5 + min(len(candidate.key_entities), 6) * 2.5 + min(len(candidate.facts), 5) * 2
    if _celebrity_without_public_interest(candidate, text):
        score -= 32
    score = _clamp(score)
    reason = f"{candidate.category} story with {len(hits)} importance signals"
    if hits:
        reason += f" ({', '.join(hits[:5])})"
    if _celebrity_without_public_interest(candidate, text):
        reason += "; reduced because it reads as celebrity/entertainment filler"
    return score, reason


def _viral_score(candidate: CandidateStory, text: str) -> tuple[float, str]:
    hits = _keyword_hits(text, VIRAL_TERMS)
    score = 34 + len(hits) * 7 + min(len(candidate.key_entities), 5) * 2
    if candidate.category in {"ai", "geopolitics", "economy", "energy", "defense"}:
        score += 8
    if _celebrity_without_public_interest(candidate, text):
        score -= 25
    score = _clamp(score)
    reason = f"{len(hits)} audience-hook signals"
    if hits:
        reason += f" ({', '.join(hits[:5])})"
    return score, reason


def _visual_score(candidate: CandidateStory, text: str) -> tuple[float, str]:
    opportunities_text = " ".join(candidate.visual_opportunities).lower()
    hits = _keyword_hits(text, VISUAL_TERMS)
    strong_opportunities = [
        item
        for item in candidate.visual_opportunities
        if not re.search(r"\b(source[- ]page screenshot|logo only|source logo)\b", item.lower())
    ]
    score = 24 + min(len(strong_opportunities), 4) * 7 + len(hits) * 5
    if candidate.category in {"climate", "defense", "geopolitics", "energy", "ai", "technology"}:
        score += 8
    if "logo" in opportunities_text and len(strong_opportunities) == 0:
        score -= 26
    score = _clamp(score)
    reason = f"{len(strong_opportunities)} usable visual opportunities and {len(hits)} visual signals"
    if hits:
        reason += f" ({', '.join(hits[:5])})"
    return score, reason


def _freshness_score(candidate: CandidateStory, now: datetime) -> tuple[float, str]:
    if not candidate.published_at:
        return 35.0, "Missing publication date; treated as low-medium freshness."
    try:
        published = datetime.fromisoformat(candidate.published_at.replace("Z", "+00:00"))
    except ValueError:
        return 35.0, "Unparseable publication date; treated as low-medium freshness."
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    age_hours = max((now.astimezone(timezone.utc) - published.astimezone(timezone.utc)).total_seconds() / 3600, 0)
    if age_hours <= 12:
        score = 96
    elif age_hours <= 24:
        score = 88
    elif age_hours <= 72:
        score = 78
    elif age_hours <= 168:
        score = 62
    elif age_hours <= 720:
        score = 45
    else:
        score = 24
    return float(score), f"Published about {age_hours:.1f} hours before scoring."


def _source_reliability_score(candidate: CandidateStory) -> tuple[float, str]:
    tier = candidate.source_reliability_tier.lower()
    if not candidate.source_url:
        return 18.0, "Missing source URL."
    tier_scores = {
        "official": 92.0,
        "high": 84.0,
        "trusted": 80.0,
        "medium": 64.0,
        "low": 24.0,
        "unknown": 54.0,
    }
    score = tier_scores.get(tier, 54.0)
    domain = candidate.source_domain.lower()
    if domain.endswith((".gov", ".mil", ".int")) or domain in KNOWN_RELIABLE_DOMAINS:
        score = max(score, 78.0)
    if domain.endswith(".gov.in") or domain.endswith(".europa.eu"):
        score = max(score, 86.0)
    if "unknown" in candidate.source_name.lower():
        score = min(score, 35.0)
    return _clamp(score), f"Reliability tier '{tier}' with domain '{domain or 'unknown'}'."


def _synthpost_fit_score(candidate: CandidateStory, text: str) -> tuple[float, str]:
    public_hits = _keyword_hits(text, PUBLIC_INTEREST_TERMS)
    if candidate.category in SYNTHPOST_CATEGORIES:
        score = 68 + len(public_hits) * 3
    elif candidate.category in LOW_FIT_CATEGORIES:
        score = 22 + len(public_hits) * 5
    else:
        score = 42 + len(public_hits) * 3
    if _celebrity_without_public_interest(candidate, text):
        score -= 22
    score = _clamp(score)
    reason = f"Category '{candidate.category}' with {len(public_hits)} SynthPost-fit/public-interest signals"
    if public_hits:
        reason += f" ({', '.join(public_hits[:5])})"
    return score, reason


def _tension_score(candidate: CandidateStory, text: str) -> tuple[float, str]:
    hits = _keyword_hits(text, TENSION_TERMS)
    score = 28 + len(hits) * 8
    if candidate.category in {"geopolitics", "defense", "economy", "energy"}:
        score += 8
    score = _clamp(score)
    reason = f"{len(hits)} tension/conflict signals"
    if hits:
        reason += f" ({', '.join(hits[:5])})"
    return score, reason


def _explainability_score(candidate: CandidateStory, text: str) -> tuple[float, str]:
    summary_words = len(candidate.summary.split())
    fact_bonus = min(len(candidate.facts), 5) * 8
    entity_bonus = min(len(candidate.key_entities), 5) * 3
    context_hits = _keyword_hits(text, {"because", "could", "impact", "means", "why", "rules", "policy", "market"})
    score = 26 + fact_bonus + entity_bonus + min(summary_words, 80) * 0.35 + len(context_hits) * 4
    score = _clamp(score)
    reason = f"{len(candidate.facts)} facts, {len(candidate.key_entities)} entities, {summary_words} summary words"
    if context_hits:
        reason += f", context signals: {', '.join(context_hits[:5])}"
    return score, reason


def _rejection_reasons(
    candidate: CandidateStory,
    *,
    score_values: dict[str, float],
    final_score: float,
    text: str,
) -> list[str]:
    reasons: list[str] = []
    if score_values["source_reliability_score"] < 35:
        reasons.append("low_source_reliability")
    if not candidate.source_url:
        reasons.append("missing_source_url")
    if len(candidate.facts) < 1 or (len(candidate.facts) < 2 and len(candidate.summary.split()) < 18):
        reasons.append("thin_source_material")
    if _celebrity_without_public_interest(candidate, text):
        reasons.append("celebrity_or_entertainment_without_public_interest")
    if score_values["importance_score"] < 35:
        reasons.append("low_importance")
    if score_values["synthpost_fit_score"] < 35:
        reasons.append("weak_synthpost_fit")
    if score_values["explainability_score"] < 40:
        reasons.append("weak_explainability")
    if score_values["visual_potential_score"] < 30:
        reasons.append("weak_visual_potential")
    if _source_logo_only(candidate):
        reasons.append("source_logo_only_visuals")
    if final_score < 45:
        reasons.append("low_editorial_score")
    return _dedupe(reasons)


def _source_logo_only(candidate: CandidateStory) -> bool:
    opportunities = [item.lower() for item in candidate.visual_opportunities]
    return bool(opportunities) and all(("logo" in item or "source-page screenshot" in item) for item in opportunities)


def _celebrity_without_public_interest(candidate: CandidateStory, text: str) -> bool:
    if candidate.category not in LOW_FIT_CATEGORIES:
        return False
    return not _keyword_hits(text, PUBLIC_INTEREST_TERMS)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _final_reason(score_values: dict[str, float], weights: dict[str, float], final: float) -> str:
    top_fields = sorted(SCORE_FIELDS[:-1], key=lambda field: weights.get(field, 0.0), reverse=True)[:3]
    parts = [
        f"{field.replace('_score', '')}={score_values.get(field, 0):.1f}*{weights.get(field, 0):.2f}"
        for field in top_fields
    ]
    return f"Weighted editorial score {final:.1f} from {'; '.join(parts)}."
