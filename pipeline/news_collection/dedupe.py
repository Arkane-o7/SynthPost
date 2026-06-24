from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher
from urllib.parse import urlsplit, urlunsplit

from .candidates import CandidateStory, normalize_headline


SOURCE_TIER_STRENGTH = {
    "official": 5,
    "high": 4,
    "trusted": 4,
    "medium": 3,
    "unknown": 2,
    "low": 1,
}


def dedupe_candidates(candidates: list[CandidateStory]) -> list[CandidateStory]:
    kept: list[CandidateStory] = []
    for candidate in candidates:
        match_index = -1
        match_reason = ""
        for index, existing in enumerate(kept):
            reason = duplicate_reason(existing, candidate)
            if reason:
                match_index = index
                match_reason = reason
                break
        if match_index < 0:
            kept.append(candidate)
            continue
        existing = kept[match_index]
        winner, loser = _stronger_candidate(existing, candidate)
        kept[match_index] = _record_merge(winner, loser, match_reason)
    return kept


def duplicate_reason(first: CandidateStory, second: CandidateStory) -> str:
    first_url = canonical_url(first.source_url)
    second_url = canonical_url(second.source_url)
    if first_url and second_url and first_url == second_url:
        return "same_canonical_url"
    if first.normalized_headline and first.normalized_headline == second.normalized_headline:
        return "same_normalized_headline"
    similarity = headline_similarity(first, second)
    overlap = entity_overlap(first, second)
    if similarity >= 0.86:
        return f"similar_headline:{similarity:.2f}"
    if first.source_domain and first.source_domain == second.source_domain and similarity >= 0.72:
        return f"same_domain_similar_headline:{similarity:.2f}"
    if overlap >= 0.5 and similarity >= 0.72:
        return f"entity_overlap:{overlap:.2f};headline_similarity:{similarity:.2f}"
    return ""


def canonical_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url.strip().lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower().removeprefix("www."), path, "", ""))


def headline_similarity(first: CandidateStory, second: CandidateStory) -> float:
    left = normalize_headline(first.headline)
    right = normalize_headline(second.headline)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def entity_overlap(first: CandidateStory, second: CandidateStory) -> float:
    left = {entity.lower() for entity in first.key_entities}
    right = {entity.lower() for entity in second.key_entities}
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, min(len(left), len(right)))


def _stronger_candidate(first: CandidateStory, second: CandidateStory) -> tuple[CandidateStory, CandidateStory]:
    if _candidate_strength(second) > _candidate_strength(first):
        return second, first
    return first, second


def _candidate_strength(candidate: CandidateStory) -> tuple[int, int, int, int, str]:
    tier = SOURCE_TIER_STRENGTH.get(candidate.source_reliability_tier.lower(), 2)
    facts = len(candidate.facts)
    summary_words = len(candidate.summary.split())
    has_date = 1 if candidate.published_at else 0
    return (tier, facts, summary_words, has_date, candidate.source_url)


def _record_merge(winner: CandidateStory, loser: CandidateStory, reason: str) -> CandidateStory:
    merged_ids = _dedupe_strings(
        [
            *winner.dedupe_merged_candidate_ids,
            loser.candidate_id,
            *loser.dedupe_merged_candidate_ids,
        ]
    )
    merged_urls = _dedupe_strings(
        [
            *winner.dedupe_merged_source_urls,
            loser.source_url,
            *loser.dedupe_merged_source_urls,
        ]
    )
    reasons = _dedupe_strings(
        [
            *winner.dedupe_reasons,
            f"{reason}: merged {loser.source_name} / {loser.headline}",
            *loser.dedupe_reasons,
        ]
    )
    return replace(
        winner,
        dedupe_status="merged",
        dedupe_reasons=reasons,
        dedupe_merged_candidate_ids=merged_ids,
        dedupe_merged_source_urls=merged_urls,
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
