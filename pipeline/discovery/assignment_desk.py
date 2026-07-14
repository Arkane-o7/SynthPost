from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from pipeline import config
from pipeline.llm.providers import configured_provider, structured_generate
from pipeline.models import StoryCandidate, StorySelectionStatus


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "have", "how", "in", "into", "is", "it", "its", "new", "of",
    "on", "or", "says", "that", "the", "their", "this", "to", "will",
    "with", "why", "after", "over", "amid", "could", "may",
}
DEVELOPMENT_TERMS = {
    "approves", "approved", "bans", "blocked", "builds", "cuts", "deploys",
    "expands", "files", "invests", "launches", "limits", "passes", "raises",
    "releases", "restricts", "shuts", "signs", "sues", "unveils", "updates",
    "acquires", "merges", "opens", "closes", "strikes", "orders", "rules",
}
WEAK_EVENT_PATTERNS = (
    "not sexy", "ideal second car", "best ", "showcase", "gathered at",
    "anniversary", "opinion:", "review:", "what exactly is", "futurist is leaving",
    "head of safety is leaving", "named head", "commercial imagines",
)


@dataclass
class EventCluster:
    cluster_id: str
    members: list[StoryCandidate]
    leader: StoryCandidate


def _tokens(value: str) -> set[str]:
    # Google News titles commonly end in " - Publisher". That syndication
    # suffix is not part of the event and otherwise causes every article from
    # one outlet to collapse into the same cluster.
    value = re.sub(r"\s+[-–—]\s+[^-–—]{2,80}$", "", value.strip())
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9+-]{1,}", value.casefold())
        if token not in STOPWORDS and not token.isdigit()
    }


def _published(candidate: StoryCandidate) -> datetime:
    value = candidate.published_at or candidate.discovered_at
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def age_hours(candidate: StoryCandidate) -> float:
    return max(
        0.0,
        (datetime.now(timezone.utc) - _published(candidate)).total_seconds() / 3600,
    )


def event_similarity(left: StoryCandidate, right: StoryCandidate) -> float:
    left_tokens = _tokens(left.title)
    right_tokens = _tokens(right.title)
    shared = left_tokens & right_tokens
    union = left_tokens | right_tokens
    jaccard = len(shared) / max(1, len(union))
    sequence = SequenceMatcher(
        None, normalize_event_title(left.title), normalize_event_title(right.title)
    ).ratio()
    # One generic shared token such as "AI" must never merge two events.
    if len(shared) < 2:
        return 0.0
    return max(jaccard, sequence * 0.88)


def normalize_event_title(title: str) -> str:
    return " ".join(sorted(_tokens(title)))


def cluster_candidates(
    candidates: list[StoryCandidate],
    *,
    source_priorities: dict[str, int] | None = None,
) -> list[EventCluster]:
    priorities = source_priorities or {}
    groups: list[list[StoryCandidate]] = []
    for candidate in sorted(candidates, key=_published, reverse=True):
        matched: list[StoryCandidate] | None = None
        for group in groups:
            if abs((_published(candidate) - _published(group[0])).total_seconds()) > 8 * 86400:
                continue
            if max(event_similarity(candidate, member) for member in group[:5]) >= 0.48:
                matched = group
                break
        if matched is None:
            groups.append([candidate])
        else:
            matched.append(candidate)

    clusters: list[EventCluster] = []
    for members in groups:
        leader = max(
            members,
            key=lambda item: (
                priorities.get(item.source_id or "", 50),
                item.scores.source_reliability,
                item.scores.freshness,
                item.final_score,
            ),
        )
        fingerprint = "|".join(sorted(normalize_event_title(item.title) for item in members))
        cluster_id = "event_" + hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:12]
        clusters.append(EventCluster(cluster_id, members, leader))
    return clusters


def development_score(candidate: StoryCandidate) -> float:
    text = f"{candidate.title} {candidate.summary}".casefold()
    verb_hits = sum(1 for term in DEVELOPMENT_TERMS if re.search(rf"\b{re.escape(term)}\b", text))
    weak = sum(1 for pattern in WEAK_EVENT_PATTERNS if pattern in text)
    consequence = len(candidate.editorial_fit.matched_criteria)
    return max(0.0, min(1.0, 0.16 + verb_hits * 0.18 + consequence * 0.07 - weak * 0.34))


def india_impact_hypothesis(candidate: StoryCandidate) -> tuple[str, float]:
    fit = candidate.editorial_fit
    text = f"{candidate.title} {candidate.summary}".casefold()
    if any(term in text for term in ("india", "indian", "rbi", "isro", "upi", "meity", "sebi")):
        return "The development directly names an Indian institution, market, company or affected group.", 0.82
    mapping = {
        "artificial_intelligence": "Potential effects on Indian compute access, cloud pricing, developers and domestic AI investment require verification.",
        "technology": "Potential effects on Indian users, developers, platform regulation or technology supply chains require verification.",
        "infrastructure": "Potential effects on Indian manufacturing capacity, logistics and infrastructure investment require verification.",
        "energy": "Potential effects on Indian import costs, electricity systems, inflation and industrial competitiveness require verification.",
        "business": "Potential effects on Indian capital, trade, jobs or supply-chain exposure require verification.",
        "science": "Potential implications for Indian research capability, public investment or technology access require verification.",
        "geopolitics_and_power": "Potential effects on Indian trade, strategic autonomy, energy security or supply chains require verification.",
        "policy": "Potential precedent for Indian regulation, standards or market access requires verification.",
    }
    impact = mapping.get(fit.primary_topic, "")
    if impact and "system_change" in fit.matched_criteria:
        return impact, 0.38
    return "", 0.0


def _recommended_format(candidate: StoryCandidate) -> str:
    age = age_hours(candidate)
    if candidate.editorial_fit.primary_topic in {"infrastructure", "energy"} and candidate.cluster_size >= 3:
        return "india_builds"
    if age <= 48 and candidate.cluster_size >= 2:
        return "signal"
    if candidate.evidence_score >= 0.75 and candidate.cluster_size >= 3:
        return "deep_dive"
    return "explained"


def _assessment_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["assessments"],
        "properties": {
            "assessments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "candidate_id", "verdict", "consequence_score",
                        "india_score", "evidence_score", "confidence",
                        "reason", "india_impact", "recommended_format",
                    ],
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "verdict": {"type": "string", "enum": ["recommended", "global_watch", "reject"]},
                        "consequence_score": {"type": "number"},
                        "india_score": {"type": "number"},
                        "evidence_score": {"type": "number"},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                        "india_impact": {"type": "string"},
                        "recommended_format": {"type": "string", "enum": ["signal", "explained", "deep_dive", "india_builds"]},
                    },
                },
            }
        },
    }


def _validate_assessments(raw: dict[str, Any], allowed: set[str]) -> dict[str, dict[str, Any]]:
    rows = raw.get("assessments")
    if not isinstance(rows, list):
        raise ValueError("assignment desk response needs an assessments array")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id not in allowed or candidate_id in result:
            raise ValueError(f"unknown or duplicate candidate_id: {candidate_id}")
        result[candidate_id] = row
    if set(result) != allowed:
        missing = sorted(allowed - set(result))
        raise ValueError(f"assignment desk omitted candidate_ids: {missing}")
    return result


def _ai_assess(leaders: list[StoryCandidate]) -> dict[str, dict[str, Any]]:
    if not leaders or not config.env_bool("SYNTHPOST_AI_ASSIGNMENT_DESK", True):
        return {}
    ai_limit = max(
        1,
        min(24, int(config.env_float("SYNTHPOST_ASSIGNMENT_DESK_AI_LIMIT", 12))),
    )
    limited = leaders[:ai_limit]
    payload = [
        {
            "candidate_id": item.candidate_id,
            "title": item.title,
            "summary": item.summary[:500],
            "published_at": item.published_at,
            "topic": item.editorial_fit.primary_topic,
            "sources": item.supporting_sources,
            "deterministic_india_hypothesis": item.editorial_fit.india_impact,
            "charter_signals": item.editorial_fit.matched_criteria,
            "rejection_signals": item.editorial_fit.rejection_signals,
        }
        for item in limited
    ]
    prompt = f"""
You are SynthPost's senior assignment editor. Rank event clusters, not headlines.
SynthPost covers globally consequential technology, AI, science, infrastructure,
energy, business and power shifts with a concrete, defensible India consequence.

Reject product fluff, celebrity reactions, personnel moves, routine corporate
events, opinion without a new development, PR announcements without consequence,
local crime and ordinary political churn. Do not invent an India connection.
When India is not explicitly named, an India impact may be a clearly labelled,
credible consequence to verify—not a fact. Recommend only when the event changes
a consequential system, has evidence, and can sustain a visual explainer.

Return one assessment for every supplied candidate. Scores are 0-1.
INPUT JSON:
{json.dumps(payload, ensure_ascii=True)}
""".strip()
    provider = configured_provider()
    value, _ = structured_generate(
        provider,
        prompt,
        _assessment_schema(),
        lambda raw: _validate_assessments(
            raw, {candidate.candidate_id for candidate in limited}
        ),
        # The deterministic desk is already complete. AI is an enrichment,
        # so rate limits and malformed responses must fail fast rather than
        # holding the discovery queue open for retry sleeps.
        max_retries=0,
    )
    return value


def apply_assignment_desk(
    repository,
    candidates: list[StoryCandidate],
    *,
    use_ai: bool = True,
) -> list[StoryCandidate]:
    if not candidates:
        return []
    sources = {source.source_id: source for source in repository.list_sources()}
    clusters = cluster_candidates(
        candidates,
        source_priorities={key: value.priority for key, value in sources.items()},
    )
    leaders: list[StoryCandidate] = []
    for cluster in clusters:
        source_names = sorted({member.source_name for member in cluster.members})
        related = [member.candidate_id for member in cluster.members]
        evidence = min(
            1.0,
            0.28 + len(source_names) * 0.2 + max(
                member.scores.source_reliability for member in cluster.members
            ) * 0.22,
        )
        for member in cluster.members:
            member.event_cluster_id = cluster.cluster_id
            member.duplicate_group_id = cluster.cluster_id
            member.cluster_size = len(cluster.members)
            member.supporting_sources = source_names
            member.related_candidate_ids = related
            member.evidence_score = round(evidence, 3)
            if member.candidate_id != cluster.leader.candidate_id:
                member.assignment_lane = "duplicate"
                if member.selection_status in {
                    StorySelectionStatus.suggested,
                    StorySelectionStatus.expired,
                    StorySelectionStatus.duplicate,
                }:
                    member.selection_status = StorySelectionStatus.duplicate

        leader = cluster.leader
        if leader.selection_status in {
            StorySelectionStatus.expired,
            StorySelectionStatus.duplicate,
        }:
            leader.selection_status = StorySelectionStatus.suggested
        impact, impact_confidence = india_impact_hypothesis(leader)
        leader.editorial_fit.india_impact = impact
        leader.editorial_fit.india_impact_confidence = impact_confidence
        leader.editorial_fit.india_relevance = impact_confidence
        development = development_score(leader)
        source = sources.get(leader.source_id or "")
        priority = (source.priority / 100.0) if source else 0.5
        score = (
            leader.scores.importance * 0.18
            + leader.scores.freshness * 0.15
            + development * 0.2
            + impact_confidence * 0.18
            + evidence * 0.13
            + leader.scores.visual_potential * 0.07
            + leader.scores.explainability * 0.06
            + priority * 0.03
        )
        age = age_hours(leader)
        if age > config.env_float("SYNTHPOST_DISCOVERY_MAX_AGE_HOURS", 240.0):
            leader.assignment_lane = "expired"
            if leader.selection_status == StorySelectionStatus.suggested:
                leader.selection_status = StorySelectionStatus.expired
        elif leader.editorial_fit.rejection_signals or development < 0.32:
            leader.assignment_lane = "rejected"
        elif score >= 0.57 and impact_confidence >= 0.3:
            leader.assignment_lane = "recommended"
        elif "system_change" in leader.editorial_fit.matched_criteria:
            leader.assignment_lane = "global_watch"
        else:
            leader.assignment_lane = "rejected"
        leader.final_score = round(score, 3)
        leader.assignment_confidence = round(max(development, evidence) * 0.7 + impact_confidence * 0.3, 3)
        leader.assignment_summary = (
            f"{leader.cluster_size} article(s) from {len(source_names)} source(s); "
            f"development {round(development * 100)}%, evidence {round(evidence * 100)}%."
        )
        leader.recommended_format = _recommended_format(leader)
        leader.editorial_fit.eligible = leader.assignment_lane == "recommended"
        leaders.append(leader)

    assessments: dict[str, dict[str, Any]] = {}
    if use_ai:
        try:
            assessments = _ai_assess(
                sorted(leaders, key=lambda item: item.final_score, reverse=True)
            )
        except Exception as exc:
            # Discovery remains useful when the hosted assignment editor is
            # unavailable; the deterministic desk is deliberately complete.
            for leader in leaders:
                leader.score_reasons.append(f"AI assignment editor unavailable: {exc}")

    for leader in leaders:
        assessment = assessments.get(leader.candidate_id)
        # Hosted judgement can refine borderline stories, but it cannot undo a
        # deterministic hard rejection such as local crime, shopping content,
        # personnel churn, or an expired event.
        hard_rejected = bool(leader.editorial_fit.rejection_signals) or leader.assignment_lane == "expired"
        if assessment and not hard_rejected:
            verdict = str(assessment.get("verdict") or "reject")
            india_score = max(0.0, min(1.0, float(assessment.get("india_score") or 0)))
            consequence = max(0.0, min(1.0, float(assessment.get("consequence_score") or 0)))
            confidence = max(0.0, min(1.0, float(assessment.get("confidence") or 0)))
            if verdict == "recommended" and india_score >= 0.35 and consequence >= 0.5:
                leader.assignment_lane = "recommended"
            elif verdict == "global_watch" and consequence >= 0.45:
                leader.assignment_lane = "global_watch"
            else:
                leader.assignment_lane = "rejected"
            leader.editorial_fit.eligible = leader.assignment_lane == "recommended"
            leader.editorial_fit.india_relevance = india_score
            leader.editorial_fit.india_impact_confidence = india_score
            leader.editorial_fit.india_impact = str(assessment.get("india_impact") or "").strip()
            leader.assignment_summary = str(assessment.get("reason") or "").strip()
            leader.assignment_confidence = confidence
            leader.recommended_format = str(assessment.get("recommended_format") or "explained")
            ai_score = consequence * 0.45 + india_score * 0.3 + float(assessment.get("evidence_score") or 0) * 0.15 + confidence * 0.1
            leader.final_score = round(leader.final_score * 0.45 + ai_score * 0.55, 3)

    for cluster in clusters:
        for member in cluster.members:
            repository.upsert_candidate(member)
    return sorted(leaders, key=lambda item: item.final_score, reverse=True)


def rebuild_assignment_desk(repository, *, use_ai: bool = False) -> list[StoryCandidate]:
    candidates = repository.list_candidates(
        limit=1500,
        include_duplicates=True,
        include_expired=True,
    )
    candidates = [
        candidate
        for candidate in candidates
        if candidate.selection_status
        in {
            StorySelectionStatus.suggested,
            StorySelectionStatus.duplicate,
            StorySelectionStatus.expired,
        }
    ]
    return apply_assignment_desk(repository, candidates, use_ai=use_ai)
