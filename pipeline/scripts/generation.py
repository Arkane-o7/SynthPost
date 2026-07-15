from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from typing import Any, Callable

from pipeline import config
from pipeline.llm.providers import (
    StructuredGenerationError,
    configured_provider,
    structured_generate,
)
from pipeline.editorial.charter import (
    CHARTER_VERSION,
    charter_prompt_context,
    load_editorial_charter,
    normalize_narration_mode,
    show_format_for,
)
from pipeline.models import (
    ApprovalStatus,
    GenerationAudit,
    NarrativeArcItem,
    NarrativeBeat,
    NarrativeBrief,
    NarrativeDraft,
    NarrativeSegmentPlan,
    NarrativeSegmentation,
    NarrationMode,
    ScriptDocument,
    ScriptSection,
    ScriptStatus,
    SourceClipCue,
    StoryWorkflowState,
    new_id,
    now_iso,
    normalize_section_headline_cues,
    narration_beats,
    section_overlay_text,
)
from pipeline.workflow import can_transition

SECTION_ORDER = [
    "cold_open",
    "intro",
    "context",
    "key_developments",
    "why_it_matters",
    "stakes",
    "uncertainty",
    "conclusion",
    "outro",
]


def _assert_story_can_enter_script_review(repository, story_id: str) -> None:
    current = repository.candidate_for_story(story_id).workflow_state
    if current == StoryWorkflowState.script_review:
        return
    if not can_transition(current, StoryWorkflowState.script_review):
        raise ValueError(
            f"Story cannot enter script review from workflow state {current.value}"
        )


def _move_story_to_script_review(repository, story_id: str) -> None:
    """Invalidate downstream workflow state after a new script revision exists."""

    _assert_story_can_enter_script_review(repository, story_id)
    current = repository.candidate_for_story(story_id).workflow_state
    if current == StoryWorkflowState.script_review:
        return
    repository.transition_story(story_id, StoryWorkflowState.script_review)


SCRIPT_PROMPT_VERSION = "synthpost.script.v5"
LONG_FORM_PROMPT_VERSION = "synthpost.long-form-section.v4"
HEADLINE_PROMPT_VERSION = "synthpost.headline-editor.v2"
NARRATIVE_BRIEF_PROMPT_VERSION = "synthpost.narrative-brief.v3"
NARRATIVE_DRAFT_PROMPT_VERSION = "synthpost.narrative-draft.v3"
NARRATIVE_REPAIR_PROMPT_VERSION = "synthpost.narrative-repair.v3"
NARRATIVE_SEGMENT_PROMPT_VERSION = "synthpost.narrative-segmentation.v1"


def target_word_count(duration_seconds: int) -> int:
    return round(duration_seconds * config.words_per_minute() / 60.0)


def duration_tolerance_seconds(duration_seconds: int) -> float:
    # Long-form narration estimates are approximate: TTS voice, punctuation, and
    # model phrasing can move runtime substantially. Keep this strict enough to
    # reject short default drafts, but flexible enough for local TTS/rendering.
    return max(8.0, duration_seconds * 0.20)


def section_word_targets(duration_seconds: int) -> dict[str, int]:
    total = target_word_count(duration_seconds)
    if total < 350:
        # Short broadcast pieces need fewer, stronger sections. Applying the
        # long-form minimum to all nine section types produced impossible or
        # even negative targets for 60-90 second scripts.
        weights = {
            "cold_open": 0.08,
            "context": 0.18,
            "key_developments": 0.28,
            "why_it_matters": 0.20,
            "uncertainty": 0.12,
            "conclusion": 0.14,
        }
        minimum = 12
    else:
        weights = {
            "cold_open": 0.06,
            "intro": 0.08,
            "context": 0.16,
            "key_developments": 0.18,
            "why_it_matters": 0.13,
            "stakes": 0.13,
            "uncertainty": 0.11,
            "conclusion": 0.10,
            "outro": 0.05,
        }
        minimum = 20
    targets = {
        section: max(minimum, round(total * weight))
        for section, weight in weights.items()
    }
    delta = total - sum(targets.values())
    targets["key_developments"] += delta
    return targets


def compact_research_pack_for_prompt(pack: dict[str, Any]) -> dict[str, Any]:
    """Keep grounded evidence while excluding bulky scraped page boilerplate."""

    return {
        "story_id": pack.get("story_id"),
        "research_summary": pack.get("research_summary", ""),
        "research_queries": pack.get("research_queries", []),
        "documents": [
            {
                key: document.get(key)
                for key in (
                    "document_id",
                    "title",
                    "publisher",
                    "published_at",
                    "discovery_method",
                    "relevance_score",
                    "extraction_status",
                )
            }
            for document in pack.get("documents", [])[:12]
        ],
        # Keep the grounding fields the writer actually consumes. Notes repeat
        # claim text and can push Groq free/on-demand requests over their TPM cap.
        "claims": [
            {
                key: claim.get(key)
                for key in (
                    "claim_id",
                    "claim_text",
                    "evidence_ids",
                    "supported",
                )
            }
            for claim in pack.get("claims", [])
        ],
        "evidence": [
            {
                "evidence_id": evidence.get("evidence_id"),
                "document_id": evidence.get("document_id"),
                "excerpt": str(evidence.get("excerpt") or "")[:180],
            }
            for evidence in pack.get("evidence", [])[:30]
        ],
        "organizations": pack.get("organizations", [])[:20],
        "locations": pack.get("locations", [])[:20],
        "numbers": pack.get("numbers", [])[:30],
        "dates": pack.get("dates", [])[:20],
        "uncertainties": pack.get("uncertainties", [])[:8],
        "systems": pack.get("systems", [])[:12],
        "stakeholders": pack.get("stakeholders", [])[:12],
        "trade_offs": pack.get("trade_offs", [])[:8],
        "execution_gaps": pack.get("execution_gaps", [])[:8],
        "editorial_questions": pack.get("editorial_questions", [])[:8],
        "charter_version": pack.get("charter_version", CHARTER_VERSION),
    }


def section_research_context(
    compact_pack: dict[str, Any], claim_ids: list[str], *, max_claims: int = 8
) -> dict[str, Any]:
    """Build a small evidence slice for one expansion request.

    Sending the complete research pack for every section repeatedly exhausts
    hosted-provider token windows. Linked claims come first, followed by a few
    additional claims so the writer can make transitions without losing grounding.
    """

    requested = {str(value) for value in claim_ids}
    all_claims = list(compact_pack.get("claims", []))
    selected_claims = [
        claim for claim in all_claims if str(claim.get("claim_id")) in requested
    ]
    for claim in all_claims:
        if len(selected_claims) >= max_claims:
            break
        if claim not in selected_claims:
            selected_claims.append(claim)
    evidence_ids = {
        str(evidence_id)
        for claim in selected_claims
        for evidence_id in (claim.get("evidence_ids") or [])
    }
    selected_evidence = [
        evidence
        for evidence in compact_pack.get("evidence", [])
        if str(evidence.get("evidence_id")) in evidence_ids
    ][:max_claims]
    document_ids = {
        str(evidence.get("document_id")) for evidence in selected_evidence
    }
    return {
        "story_id": compact_pack.get("story_id"),
        "research_summary": str(compact_pack.get("research_summary") or "")[:500],
        "documents": [
            document
            for document in compact_pack.get("documents", [])
            if str(document.get("document_id")) in document_ids
        ],
        "claims": selected_claims,
        "evidence": selected_evidence,
        "numbers": compact_pack.get("numbers", [])[:10],
        "dates": compact_pack.get("dates", [])[:8],
        "uncertainties": compact_pack.get("uncertainties", [])[:4],
        "systems": compact_pack.get("systems", [])[:6],
        "stakeholders": compact_pack.get("stakeholders", [])[:6],
        "trade_offs": compact_pack.get("trade_offs", [])[:4],
        "execution_gaps": compact_pack.get("execution_gaps", [])[:4],
    }


def estimate_duration(text: str) -> float:
    words = len(text.split())
    return round(max(3.0, words / config.words_per_minute() * 60.0), 2)


def source_clip_schema() -> dict[str, Any]:
    return {
        "anyOf": [
            {
                "type": "object",
                "required": [
                    "duration_seconds",
                    "search_query",
                    "description",
                    "fallback_narration",
                    "speaker",
                    "quote",
                ],
                "properties": {
                    "duration_seconds": {
                        "type": "number",
                        "minimum": 3,
                        "maximum": 30,
                    },
                    "search_query": {"type": "string"},
                    "description": {"type": "string"},
                    "fallback_narration": {"type": "string"},
                    "speaker": {"type": "string"},
                    "quote": {"type": "string"},
                },
            },
            {"type": "null"},
        ]
    }


def source_clip_from_raw(value: Any) -> SourceClipCue | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("source_clip must be an object or null")
    return SourceClipCue.model_validate(value)


def section_total_duration(text: str, source_clip: SourceClipCue | None) -> float:
    return round(
        estimate_duration(text)
        + (source_clip.duration_seconds if source_clip is not None else 0.0),
        2,
    )


def section_id(section_type: str, index: int) -> str:
    return f"sec_{index:03d}_{section_type}"


def split_manual_script(
    story_id: str, headline: str, text: str, *, category: str = "manual"
) -> ScriptDocument:
    paragraphs = [
        part.strip() for part in re.split(r"\n\s*\n", text.strip()) if part.strip()
    ]
    if not paragraphs:
        paragraphs = [text.strip() or headline]
    sections: list[ScriptSection] = []
    for index, paragraph in enumerate(paragraphs, start=1):
        section_type = SECTION_ORDER[min(index - 1, len(SECTION_ORDER) - 1)]
        sections.append(
            ScriptSection(
                section_id=section_id(section_type, index),
                section_type=section_type,  # type: ignore[arg-type]
                text=paragraph,
                estimated_duration_seconds=estimate_duration(paragraph),
                claim_ids=[],
                suggested_visual_types=["context", "fallback"],
                suggested_search_queries=[headline],
                suggested_template_ids=[
                    "split_anchor_visual" if index > 1 else "fullscreen_anchor"
                ],
                lower_third=section_overlay_text(
                    paragraph, section_type, max_chars=80
                ),
                chyron=section_overlay_text(paragraph, section_type, max_chars=64),
                headline_cues=normalize_section_headline_cues(
                    paragraph, section_type
                ),
                approval_status=ApprovalStatus.review,
            )
        )
    script = ScriptDocument(
        story_id=story_id,
        headline=headline,
        dek=paragraphs[0][:180],
        category=category,
        estimated_duration_seconds=round(
            sum(section.estimated_duration_seconds for section in sections), 2
        ),
        status=ScriptStatus.review,
        sections=sections,
    )
    return script


def narrative_brief_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "headline",
            "dek",
            "category",
            "thesis",
            "opening_strategy",
            "closing_strategy",
            "arc",
        ],
        "properties": {
            "headline": {"type": "string"},
            "dek": {"type": "string"},
            "category": {"type": "string"},
            "thesis": {"type": "string"},
            "opening_strategy": {"type": "string"},
            "closing_strategy": {"type": "string"},
            "arc": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "section_type",
                        "purpose",
                        "claim_ids",
                        "must_not_repeat",
                    ],
                    "properties": {
                        "section_type": {"type": "string"},
                        "purpose": {"type": "string"},
                        "claim_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "must_not_repeat": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def narrative_draft_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["headline", "dek", "category", "beats"],
        "properties": {
            "headline": {"type": "string"},
            "dek": {"type": "string"},
            "category": {"type": "string"},
            "beats": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["beat_id", "text", "claim_ids"],
                    "properties": {
                        "beat_id": {"type": "string"},
                        "text": {"type": "string"},
                        "claim_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def narrative_segmentation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["sections"],
        "properties": {
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "section_type",
                        "beat_ids",
                        "suggested_visual_types",
                        "suggested_search_queries",
                        "suggested_template_ids",
                        "lower_third",
                        "chyron",
                        "source_clip",
                    ],
                    "properties": {
                        "section_type": {"type": "string"},
                        "beat_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "suggested_visual_types": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "suggested_search_queries": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "suggested_template_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "lower_third": {"type": "string"},
                        "chyron": {"type": "string"},
                        "source_clip": source_clip_schema(),
                    },
                },
            },
        },
    }


def _valid_claim_ids(pack: dict[str, Any]) -> set[str]:
    return {
        str(claim.get("claim_id"))
        for claim in pack.get("claims", [])
        if claim.get("claim_id")
    }


def _validate_narrative_brief(
    raw: dict[str, Any], pack: dict[str, Any]
) -> NarrativeBrief:
    valid_claims = _valid_claim_ids(narrative_research_pack_for_prompt(pack))
    if not valid_claims:
        raise ValueError("narrative generation requires at least one supported claim")
    raw_arc = raw.get("arc")
    if not isinstance(raw_arc, list) or not 3 <= len(raw_arc) <= len(SECTION_ORDER):
        raise ValueError("narrative brief must contain 3-9 ordered arc items")
    arc: list[NarrativeArcItem] = []
    seen_types: set[str] = set()
    previous_order = -1
    for item in raw_arc:
        if not isinstance(item, dict):
            raise ValueError("narrative arc items must be objects")
        section_type = str(item.get("section_type") or "").strip()
        if section_type not in SECTION_ORDER or section_type in seen_types:
            raise ValueError(f"invalid or duplicate narrative section: {section_type}")
        order = SECTION_ORDER.index(section_type)
        if order <= previous_order:
            raise ValueError("narrative arc section types must follow editorial order")
        claim_ids = [str(value) for value in item.get("claim_ids", [])]
        unknown = sorted(set(claim_ids) - valid_claims)
        if unknown:
            raise ValueError(
                f"narrative arc {section_type} references unknown claims: {unknown}"
            )
        arc.append(
            NarrativeArcItem(
                section_type=section_type,  # type: ignore[arg-type]
                purpose=" ".join(str(item.get("purpose") or "").split()),
                claim_ids=list(dict.fromkeys(claim_ids)),
                must_not_repeat=[
                    " ".join(str(value).split())
                    for value in item.get("must_not_repeat", [])
                    if str(value).strip()
                ],
            )
        )
        seen_types.add(section_type)
        previous_order = order
    if arc[0].section_type != "cold_open":
        raise ValueError("narrative arc must begin with cold_open")
    if arc[-1].section_type not in {"conclusion", "outro"}:
        raise ValueError("narrative arc must end with conclusion or outro")
    return NarrativeBrief(
        headline=" ".join(str(raw.get("headline") or "SynthPost Briefing").split()),
        dek=" ".join(str(raw.get("dek") or "").split()),
        category=" ".join(str(raw.get("category") or "news").split()),
        thesis=" ".join(str(raw.get("thesis") or "").split()),
        opening_strategy=" ".join(
            str(raw.get("opening_strategy") or "").split()
        ),
        closing_strategy=" ".join(
            str(raw.get("closing_strategy") or "").split()
        ),
        arc=arc,
    )


def _validate_narrative_draft(
    raw: dict[str, Any],
    pack: dict[str, Any],
    *,
    target_duration_seconds: int,
) -> NarrativeDraft:
    raw_beats = raw.get("beats")
    if not isinstance(raw_beats, list) or len(raw_beats) < 3:
        raise ValueError("narrative draft must contain at least three ordered beats")
    valid_claims = _valid_claim_ids(narrative_research_pack_for_prompt(pack))
    if not valid_claims:
        raise ValueError("narrative generation requires at least one supported claim")
    minimum_beats = max(
        3, math.ceil(target_word_count(target_duration_seconds) / 55)
    )
    if len(raw_beats) < minimum_beats:
        raise ValueError(
            "narrative draft must use sentence-level beats; "
            f"expected at least {minimum_beats}, got {len(raw_beats)}"
        )
    beats: list[NarrativeBeat] = []
    for index, item in enumerate(raw_beats, start=1):
        if not isinstance(item, dict):
            raise ValueError("narrative beats must be objects")
        text = " ".join(str(item.get("text") or "").split()).strip()
        if len(text.split()) < 3:
            raise ValueError(f"narrative beat {index} is too short")
        if len(text.split()) > 65:
            raise ValueError(
                f"narrative beat {index} must be a sentence or major clause; "
                f"got {len(text.split())} words"
            )
        if text[-1:] not in {".", "?", "!", "\"", "”", "'", "’"}:
            raise ValueError(f"narrative beat {index} must end with punctuation")
        if re.search(r"\b(?:claim|evidence)_[a-z0-9_-]+\b", text, re.IGNORECASE):
            raise ValueError(
                f"narrative beat {index} speaks an internal claim/evidence ID aloud"
            )
        claim_ids = [str(value) for value in item.get("claim_ids", [])]
        if not claim_ids:
            raise ValueError(
                f"narrative beat {index} must link at least one supported claim"
            )
        unknown = sorted(set(claim_ids) - valid_claims)
        if unknown:
            raise ValueError(f"narrative beat {index} references unknown claims: {unknown}")
        beats.append(
            NarrativeBeat(
                beat_id=f"beat_{index:03d}",
                text=text,
                claim_ids=list(dict.fromkeys(claim_ids)),
            )
        )
    draft = NarrativeDraft(
        headline=" ".join(str(raw.get("headline") or "SynthPost Briefing").split()),
        dek=" ".join(str(raw.get("dek") or "").split()),
        category=" ".join(str(raw.get("category") or "news").split()),
        beats=beats,
    )
    tolerance = duration_tolerance_seconds(target_duration_seconds)
    lower_words = target_word_count(max(1, round(target_duration_seconds - tolerance)))
    upper_words = target_word_count(round(target_duration_seconds + tolerance))
    actual_words = len(draft.text.split())
    if not lower_words <= actual_words <= upper_words:
        raise ValueError(
            f"complete narration must contain {lower_words}-{upper_words} words; "
            f"got {actual_words}"
        )
    return draft


_QUALITY_STOP_WORDS = {
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
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "through",
    "to",
    "was",
    "were",
    "with",
    "without",
}


def _quality_tokens(text: str) -> list[str]:
    normalized = text.casefold().replace("bangalore", "bengaluru")
    return re.findall(r"[a-z0-9]+", normalized)


def _content_token_set(text: str, *, limit: int | None = None) -> set[str]:
    tokens = _quality_tokens(text)
    if limit is not None:
        tokens = tokens[:limit]
    return {token for token in tokens if token not in _QUALITY_STOP_WORDS}


_GENERIC_TOPIC_TERMS = {
    "company",
    "development",
    "global",
    "india",
    "indian",
    "latest",
    "news",
    "report",
    "reviewed",
    "source",
    "technology",
}


def narrative_research_pack_for_prompt(pack: dict[str, Any]) -> dict[str, Any]:
    """Exclude search-neighbor claims that do not belong to the lead story.

    Research deliberately collects adjacent coverage, so a pack can contain a
    relevant lead article alongside unrelated search results. Narrative writing
    uses the lead headline/claim as a lexical anchor and retains only claims
    whose claim/evidence/document context overlaps that topic. The canonical
    research pack is not mutated; this is a generation-boundary projection.
    """

    compact = compact_research_pack_for_prompt(pack)
    claims = list(compact.get("claims", []))
    if not claims:
        return compact
    summary = str(compact.get("research_summary") or "").split("Reviewed", 1)[0]
    lead_text = " ".join(
        [summary, str(claims[0].get("claim_text") or "")]
    )
    anchors = _content_token_set(lead_text) - _GENERIC_TOPIC_TERMS
    if len(anchors) < 2:
        return compact

    evidence_by_id = {
        str(item.get("evidence_id")): item
        for item in compact.get("evidence", [])
        if item.get("evidence_id")
    }
    documents_by_id = {
        str(item.get("document_id")): item
        for item in compact.get("documents", [])
        if item.get("document_id")
    }
    relevant_claims: list[dict[str, Any]] = []
    relevant_evidence_ids: set[str] = set()
    relevant_document_ids: set[str] = set()
    relevant_context: list[str] = []
    for index, claim in enumerate(claims):
        evidence_ids = [str(value) for value in claim.get("evidence_ids", [])]
        context_parts = [str(claim.get("claim_text") or "")]
        for evidence_id in evidence_ids:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                continue
            context_parts.append(str(evidence.get("excerpt") or ""))
            document_id = str(evidence.get("document_id") or "")
            document = documents_by_id.get(document_id)
            if document is not None:
                context_parts.append(str(document.get("title") or ""))
        context = " ".join(context_parts)
        overlap = anchors & _content_token_set(context)
        if index == 0 or len(overlap) >= 2:
            relevant_claims.append(claim)
            relevant_context.append(context)
            relevant_evidence_ids.update(evidence_ids)
            for evidence_id in evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence and evidence.get("document_id"):
                    relevant_document_ids.add(str(evidence["document_id"]))

    if not relevant_claims:
        relevant_claims = claims[:1]
    projected = dict(compact)
    projected["claims"] = relevant_claims
    projected["evidence"] = [
        item
        for item in compact.get("evidence", [])
        if str(item.get("evidence_id")) in relevant_evidence_ids
    ]
    projected["documents"] = [
        item
        for item in compact.get("documents", [])
        if str(item.get("document_id")) in relevant_document_ids
    ]
    context_tokens = _quality_tokens(" ".join(relevant_context))

    def context_contains(value: Any) -> bool:
        row_tokens = _quality_tokens(str(value))
        if not row_tokens or len(row_tokens) > len(context_tokens):
            return False
        width = len(row_tokens)
        return any(
            context_tokens[index : index + width] == row_tokens
            for index in range(len(context_tokens) - width + 1)
        )

    def claim_backed_rows(name: str) -> list[Any]:
        rows = compact.get(name, [])
        return [value for value in rows if context_contains(value)]

    for name in (
        "numbers",
        "dates",
        "uncertainties",
        "trade_offs",
        "execution_gaps",
    ):
        projected[name] = claim_backed_rows(name)
    for name in (
        "systems",
        "stakeholders",
        "editorial_questions",
    ):
        projected[name] = [
            value
            for value in compact.get(name, [])
            if context_contains(value)
            or bool(anchors & _content_token_set(str(value)))
        ]
    return projected


def narrative_quality_issues(draft: NarrativeDraft) -> list[str]:
    """Return deterministic story-level failures before section boundaries exist."""

    issues: list[str] = []
    texts = [beat.text for beat in draft.beats]
    lowercase_starts = []
    for beat in draft.beats:
        if re.search(r"[.!?]\s+[a-z]", beat.text):
            lowercase_starts.append(beat.beat_id)
    if lowercase_starts:
        issues.append(
            "sentence begins with lowercase text in " + ", ".join(lowercase_starts)
        )

    opening_sets = [_content_token_set(text, limit=14) for text in texts]
    related_openings: dict[int, set[int]] = defaultdict(set)
    for left in range(len(opening_sets)):
        for right in range(left + 1, len(opening_sets)):
            common = opening_sets[left] & opening_sets[right]
            union = opening_sets[left] | opening_sets[right]
            similarity = len(common) / max(1, len(union))
            if len(common) >= 4 and similarity >= 0.38:
                related_openings[left].add(right)
                related_openings[right].add(left)
    clusters = [
        sorted({index, *neighbors})
        for index, neighbors in related_openings.items()
        if len(neighbors) >= 2
    ]
    if clusters:
        cluster = max(clusters, key=len)
        beat_ids = [draft.beats[index].beat_id for index in cluster]
        issues.append(
            "multiple beats restart with substantially the same scene or framing: "
            + ", ".join(beat_ids)
        )

    full_sets = [_content_token_set(text) for text in texts]
    duplicate_pairs: list[str] = []
    for left in range(len(full_sets)):
        for right in range(left + 1, len(full_sets)):
            common = full_sets[left] & full_sets[right]
            union = full_sets[left] | full_sets[right]
            similarity = len(common) / max(1, len(union))
            if len(common) >= 8 and similarity >= 0.68:
                duplicate_pairs.append(
                    f"{draft.beats[left].beat_id}/{draft.beats[right].beat_id}"
                )
    if duplicate_pairs:
        issues.append(
            "near-duplicate narrative beats detected: "
            + ", ".join(duplicate_pairs[:6])
        )

    ngram_beats: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for beat in draft.beats:
        tokens = _quality_tokens(beat.text)
        for index in range(max(0, len(tokens) - 3)):
            gram = tuple(tokens[index : index + 4])
            if len(set(gram) - _QUALITY_STOP_WORDS) >= 3:
                ngram_beats[gram].add(beat.beat_id)
    repeated = [
        (gram, beat_ids)
        for gram, beat_ids in ngram_beats.items()
        if len(beat_ids) >= 3
    ]
    if repeated:
        gram, beat_ids = max(repeated, key=lambda item: len(item[1]))
        issues.append(
            f"phrase {' '.join(gram)!r} is repeated across "
            + ", ".join(sorted(beat_ids))
        )
    return issues


def narrative_brief_prompt(
    pack: dict[str, Any],
    *,
    target_duration_seconds: int,
    primary_topic: str,
    narration_mode: NarrationMode | str,
) -> str:
    prompt_pack = narrative_research_pack_for_prompt(pack)
    return f"""
You are SynthPost Studio's narrative brief architect. Plan one coherent spoken
news story before any prose is drafted.

{charter_prompt_context(show_format=normalize_narration_mode(narration_mode, target_duration_seconds=target_duration_seconds, primary_topic=primary_topic))}

Build a single thesis and a progressive arc. Allocate claims to the first place
they need full explanation; later arc items may build on an established fact but
must not independently restart or re-explain it. Use only section types from
{json.dumps(SECTION_ORDER)} in that order. Use only the sections the story needs,
but always begin with cold_open and end with conclusion or outro. For every arc
item, list specific ideas or scenes it must not repeat from earlier items.

Target duration: {target_duration_seconds} seconds.
Return only JSON matching the response schema.

INPUT JSON:
{json.dumps(prompt_pack, ensure_ascii=True)}
""".strip()


def narrative_draft_prompt(
    brief: NarrativeBrief,
    pack: dict[str, Any],
    *,
    target_duration_seconds: int,
    primary_topic: str,
    narration_mode: NarrationMode | str,
) -> str:
    prompt_pack = narrative_research_pack_for_prompt(pack)
    target_words = target_word_count(target_duration_seconds)
    minimum_beats = max(3, math.ceil(target_words / 55))
    return f"""
You are SynthPost Studio's senior narrative writer. Write one uninterrupted,
coherent spoken-news narration from the brief and research below.

{charter_prompt_context(show_format=normalize_narration_mode(narration_mode, target_duration_seconds=target_duration_seconds, primary_topic=primary_topic))}

The beats are stable sentence or major-clause boundaries inside one continuous
narrative. They are not sections and must not read like separate article
openings. Write the full story in one pass so each beat advances from the last.
Establish a scene only once. Do not restart with the location, protagonist, or
basic mechanism. Allocate new evidence progressively, use natural transitions,
state company claims as claims, and distinguish patents from proof of commercial
performance. Do not add section headings, stage directions, or visual language.
Use at least {minimum_beats} beats, with each beat containing no more than 65
spoken words. Every beat must attach the supported claim_ids it develops or
synthesizes. Do not state a factual detail unless one of those claims supports it. Claim
IDs and evidence IDs are internal metadata: never include them, parentheses
containing them, citations, or source labels in the spoken text.

Target duration: {target_duration_seconds} seconds, about {target_words} spoken words.
Return only JSON matching the response schema.

INPUT JSON:
{json.dumps({'brief': brief.model_dump(mode='json'), 'research': prompt_pack}, ensure_ascii=True)}
""".strip()


def narrative_repair_prompt(
    draft: NarrativeDraft,
    brief: NarrativeBrief,
    pack: dict[str, Any],
    issues: list[str],
    *,
    target_duration_seconds: int,
    primary_topic: str,
    narration_mode: NarrationMode | str,
) -> str:
    return f"""
You are SynthPost Studio's narrative continuity editor. Rewrite the complete
narration as one coherent spoken story and fix every reported quality failure.

{charter_prompt_context(show_format=normalize_narration_mode(narration_mode, target_duration_seconds=target_duration_seconds, primary_topic=primary_topic))}

Do not merely paraphrase repeated passages. Consolidate duplicated setup, make
each beat introduce or develop a distinct point, repair grammar, preserve only
supported claims, and keep approximately {target_word_count(target_duration_seconds)}
spoken words. Use at least {max(3, math.ceil(target_word_count(target_duration_seconds) / 55))}
beats; every beat must link a supported claim and contain no more than 65 spoken
words. Beats are sentence or major-clause boundaries, not sections.
Return the complete corrected narration, not a patch.

QUALITY FAILURES:
{json.dumps(issues)}

INPUT JSON:
{json.dumps({'brief': brief.model_dump(mode='json'), 'draft': draft.model_dump(mode='json'), 'research': narrative_research_pack_for_prompt(pack)}, ensure_ascii=True)}
""".strip()


def narrative_segmentation_prompt(
    draft: NarrativeDraft,
    brief: NarrativeBrief,
    *,
    source_audio_enabled: bool,
) -> str:
    audio_rule = (
        "Use source_clip only for a verified primary-source audio interruption."
        if source_audio_enabled
        else "Return source_clip as null for every section."
    )
    return f"""
You are SynthPost Studio's narrative segmentation editor. Organize an already
final narration for presentation and visual planning.

Reference every beat_id exactly once, in its existing order, using contiguous
groups. Never return narration text and never rewrite, duplicate, omit, or
reorder a beat. Follow the brief's editorial arc, but use fewer sections when a
separate section would not perform a distinct job. Section types must be unique
and follow this order: {json.dumps(SECTION_ORDER)}.

For every section, return two grounded search queries: a concrete still, map, or
diagram query and an official primary-source video or raw-footage query. Return
specific lower-third and chyron text plus appropriate visual and template hints.
{audio_rule}

Return only JSON matching the response schema.

INPUT JSON:
{json.dumps({'brief': brief.model_dump(mode='json'), 'draft': draft.model_dump(mode='json')}, ensure_ascii=True)}
""".strip()


def _validate_narrative_segmentation(
    raw: dict[str, Any], draft: NarrativeDraft
) -> NarrativeSegmentation:
    raw_sections = raw.get("sections")
    if not isinstance(raw_sections, list) or not 3 <= len(raw_sections) <= len(SECTION_ORDER):
        raise ValueError("narrative segmentation must contain 3-9 sections")
    expected_ids = [beat.beat_id for beat in draft.beats]
    expected_set = set(expected_ids)
    sections: list[NarrativeSegmentPlan] = []
    flattened: list[str] = []
    previous_order = -1
    seen_types: set[str] = set()
    for item in raw_sections:
        if not isinstance(item, dict):
            raise ValueError("narrative segmentation sections must be objects")
        section_type = str(item.get("section_type") or "").strip()
        if section_type not in SECTION_ORDER or section_type in seen_types:
            raise ValueError(f"invalid or duplicate segmented section: {section_type}")
        order = SECTION_ORDER.index(section_type)
        if order <= previous_order:
            raise ValueError("segmented section types must follow editorial order")
        beat_ids = [str(value) for value in item.get("beat_ids", [])]
        if not beat_ids or any(beat_id not in expected_set for beat_id in beat_ids):
            raise ValueError(f"{section_type} contains missing or unknown beat IDs")
        source_clip = (
            source_clip_from_raw(item.get("source_clip"))
            if config.source_audio_inserts_enabled()
            else None
        )
        queries = [
            " ".join(str(value).split())
            for value in item.get("suggested_search_queries", [])
            if str(value).strip()
        ][:2]
        if len(queries) != 2:
            raise ValueError(f"{section_type} must contain exactly two visual queries")
        sections.append(
            NarrativeSegmentPlan(
                section_type=section_type,  # type: ignore[arg-type]
                beat_ids=beat_ids,
                suggested_visual_types=[
                    str(value)
                    for value in item.get("suggested_visual_types", [])
                    if str(value).strip()
                ],
                suggested_search_queries=queries,
                suggested_template_ids=[
                    str(value)
                    for value in item.get("suggested_template_ids", [])
                    if str(value).strip()
                ],
                lower_third=" ".join(str(item.get("lower_third") or "").split())[:80],
                chyron=" ".join(str(item.get("chyron") or "").split())[:64],
                source_clip=source_clip,
            )
        )
        flattened.extend(beat_ids)
        seen_types.add(section_type)
        previous_order = order
    if flattened != expected_ids:
        raise ValueError(
            "segmentation must reference every narration beat exactly once in order"
        )
    if sections[0].section_type != "cold_open":
        raise ValueError("segmentation must begin with cold_open")
    if sections[-1].section_type not in {"conclusion", "outro"}:
        raise ValueError("segmentation must end with conclusion or outro")
    return NarrativeSegmentation(sections=sections)


def script_from_narrative(
    story_id: str,
    draft: NarrativeDraft,
    segmentation: NarrativeSegmentation,
    pack: dict[str, Any],
) -> ScriptDocument:
    beats = {beat.beat_id: beat for beat in draft.beats}
    sections: list[ScriptSection] = []
    for index, plan in enumerate(segmentation.sections, start=1):
        selected = [beats[beat_id] for beat_id in plan.beat_ids]
        text = " ".join(beat.text for beat in selected)
        claim_ids = list(
            dict.fromkeys(
                claim_id for beat in selected for claim_id in beat.claim_ids
            )
        )
        visual_types = plan.suggested_visual_types or ["context"]
        template_ids = plan.suggested_template_ids or ["split_anchor_visual"]
        if plan.source_clip is not None:
            visual_types = list(
                dict.fromkeys(["video", "primary_footage", "source_audio"] + visual_types)
            )
            template_ids = list(
                dict.fromkeys(template_ids + ["fullscreen_news_visual"])
            )
        sections.append(
            ScriptSection(
                section_id=section_id(plan.section_type, index),
                section_type=plan.section_type,
                text=text,
                estimated_duration_seconds=section_total_duration(
                    text, plan.source_clip
                ),
                claim_ids=claim_ids,
                suggested_visual_types=visual_types,
                suggested_search_queries=plan.suggested_search_queries,
                suggested_template_ids=template_ids,
                lower_third=(
                    plan.lower_third
                    or section_overlay_text(text, plan.section_type, max_chars=80)
                ),
                chyron=(
                    plan.chyron
                    or section_overlay_text(text, plan.section_type, max_chars=64)
                ),
                headline_cues=normalize_section_headline_cues(
                    text, plan.section_type
                ),
                source_clip=plan.source_clip,
                approval_status=ApprovalStatus.review,
            )
        )
    if sum(section.source_clip is not None for section in sections) > 4:
        raise ValueError("script may contain at most four source_clip inserts")
    script = ScriptDocument(
        story_id=story_id,
        headline=draft.headline,
        dek=draft.dek,
        category=draft.category,
        estimated_duration_seconds=round(
            sum(section.estimated_duration_seconds for section in sections), 2
        ),
        status=ScriptStatus.review,
        sections=sections,
        source_ids=[
            document.get("document_id")
            for document in pack.get("documents", [])
            if document.get("document_id")
        ],
    )
    script.warnings.extend(validate_grounding(script, pack))
    return script


def script_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["headline", "dek", "category", "sections"],
        "properties": {
            "headline": {"type": "string"},
            "dek": {"type": "string"},
            "category": {"type": "string"},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "section_type",
                        "text",
                        "claim_ids",
                        "lower_third",
                        "chyron",
                        "headline_cues",
                        "source_clip",
                    ],
                    "properties": {
                        "section_type": {"type": "string"},
                        "text": {"type": "string"},
                        "claim_ids": {"type": "array", "items": {"type": "string"}},
                        "lower_third": {"type": "string"},
                        "chyron": {"type": "string"},
                        "headline_cues": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "source_clip": source_clip_schema(),
                        "suggested_visual_types": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "suggested_search_queries": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "suggested_template_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def script_from_llm_json(
    story_id: str, raw: dict[str, Any], pack: dict[str, Any]
) -> ScriptDocument:
    claim_ids = {
        claim.get("claim_id")
        for claim in pack.get("claims", [])
        if claim.get("claim_id")
    }
    sections: list[ScriptSection] = []
    for index, item in enumerate(raw.get("sections", []), start=1):
        section_type = str(
            item.get("section_type")
            or SECTION_ORDER[min(index - 1, len(SECTION_ORDER) - 1)]
        ).strip()
        if section_type not in SECTION_ORDER:
            section_type = SECTION_ORDER[min(index - 1, len(SECTION_ORDER) - 1)]
        text = str(item.get("text") or "").strip()
        lower_third = str(item.get("lower_third") or "").strip()
        chyron = str(item.get("chyron") or "").strip()
        headline_cues = [
            str(value)
            for value in item.get("headline_cues", [])
            if str(value).strip()
        ]
        used_claim_ids = [
            claim_id for claim_id in item.get("claim_ids", []) if claim_id in claim_ids
        ]
        source_clip = (
            source_clip_from_raw(item.get("source_clip"))
            if config.source_audio_inserts_enabled()
            else None
        )
        if source_clip is not None and not used_claim_ids:
            raise ValueError("source_clip sections require at least one valid claim_id")
        suggested_visual_types = [
            str(value)
            for value in item.get("suggested_visual_types", ["context"])
        ]
        suggested_search_queries = [
            str(value)
            for value in item.get(
                "suggested_search_queries", [raw.get("headline", "")]
            )
        ]
        suggested_template_ids = [
            str(value)
            for value in item.get(
                "suggested_template_ids", ["split_anchor_visual"]
            )
        ]
        if source_clip is not None:
            suggested_visual_types = list(
                dict.fromkeys(
                    ["video", "primary_footage", "source_audio"]
                    + suggested_visual_types
                )
            )
            suggested_search_queries = list(
                dict.fromkeys(suggested_search_queries[:1] + [source_clip.search_query])
            )
            suggested_template_ids = list(
                dict.fromkeys(
                    suggested_template_ids + ["fullscreen_news_visual"]
                )
            )
        sections.append(
            ScriptSection(
                section_id=section_id(section_type, index),
                section_type=section_type,  # type: ignore[arg-type]
                text=text,
                estimated_duration_seconds=section_total_duration(text, source_clip),
                claim_ids=used_claim_ids,
                suggested_visual_types=suggested_visual_types,
                suggested_search_queries=suggested_search_queries,
                suggested_template_ids=suggested_template_ids,
                lower_third=(
                    lower_third[:80]
                    or section_overlay_text(text, section_type, max_chars=80)
                ),
                chyron=(
                    chyron[:64]
                    or section_overlay_text(text, section_type, max_chars=64)
                ),
                headline_cues=normalize_section_headline_cues(
                    text, section_type, headline_cues
                ),
                source_clip=source_clip,
                editorial_notes=[],
                approval_status=ApprovalStatus.review,
            )
        )
    if not sections:
        raise ValueError("LLM returned no script sections")
    if sum(section.source_clip is not None for section in sections) > 4:
        raise ValueError("script may contain at most four source_clip inserts")
    script = ScriptDocument(
        story_id=story_id,
        headline=str(raw.get("headline") or "SynthPost Briefing"),
        dek=str(raw.get("dek") or ""),
        category=str(raw.get("category") or "news"),
        estimated_duration_seconds=round(
            sum(section.estimated_duration_seconds for section in sections), 2
        ),
        status=ScriptStatus.review,
        sections=sections,
        source_ids=[
            doc.get("document_id")
            for doc in pack.get("documents", [])
            if doc.get("document_id")
        ],
    )
    warnings = validate_grounding(script, pack)
    script.warnings.extend(warnings)
    return script


def generation_prompt(
    pack: dict[str, Any], *, target_duration_seconds: int = 600,
    primary_topic: str = "general",
    narration_mode: NarrationMode | str = NarrationMode.explained,
) -> str:
    words = target_word_count(target_duration_seconds)
    tolerance = duration_tolerance_seconds(target_duration_seconds)
    min_seconds = round(target_duration_seconds - tolerance)
    max_seconds = round(target_duration_seconds + tolerance)
    min_words = target_word_count(min_seconds)
    max_words = target_word_count(max_seconds)
    section_targets = section_word_targets(target_duration_seconds)
    section_target_text = "\n".join(
        f"- {section}: about {count} words"
        for section, count in section_targets.items()
    )
    prompt_pack = compact_research_pack_for_prompt(pack)
    show_format = normalize_narration_mode(
        narration_mode,
        target_duration_seconds=target_duration_seconds,
        primary_topic=primary_topic,
    )
    editorial_context = charter_prompt_context(show_format=show_format)
    source_clip_instructions = (
        """
For each section return source_clip as either null or a structured primary-source
audio insert. Use a source_clip only when hearing the real person, exchange,
demonstration, announcement, or event audio materially improves the explanation
and the supplied evidence supports that exact moment. It is not ordinary B-roll.
When used:
- the section text must naturally set up the clip before it plays;
- duration_seconds must be 3-15 seconds in most cases, never more than 30;
- search_query must identify the exact person/event/location and seek the
  original official video, speech, hearing, press conference, demo, or raw feed;
- description must state what viewers need to see and hear;
- quote must contain only a verified expected excerpt, or be an empty string;
- speaker must name the verified speaker, or be an empty string;
- fallback_narration must communicate the same supported point naturally if no
  usable audible clip is found. Do not write "as you can see" or promise a clip.
Use these inserts sparingly: normally zero to two in a short explainer and no
more than four in a long programme. Reduce spoken narration to keep insert time
inside the requested total runtime.
""".strip()
        if config.source_audio_inserts_enabled()
        else """
Source-audio inserts are disabled for production. Return source_clip as null for
every section. External videos are muted B-roll and the anchor narration must
remain continuous; never write a sentence that promises an upcoming audible clip.
""".strip()
    )
    return f"""
You are SynthPost Studio's senior newsroom writer. Create a grounded, visual-first section-based news script.

{editorial_context}

Use only the supplied research pack. Do not fabricate quotes, statistics, names, dates, or attribution.
Return only JSON matching the provided response schema.

Target duration: {target_duration_seconds} seconds.
Estimated narration target: about {words} spoken words.
Accepted duration window: {min_seconds}-{max_seconds} seconds, approximately {min_words}-{max_words} words.
Do not return a short default script. Match the requested runtime by expanding or tightening the section text while staying grounded in the research pack.
Write full paragraph narration, not bullet summaries. For long runtimes, add sourced background, careful chronology, implications, caveats, and transitions.
Approximate section word targets:
{section_target_text}
Required presenter voice: confident and curious; India-rooted;
analytical but non-partisan; intelligent without sounding academic. State uncertainty
plainly and never manufacture certainty, conflict, urgency, or emotion.
Required section types to use when appropriate: {", ".join(SECTION_ORDER)}.
Every factual section must include claim_ids from the pack.
Each section must perform a distinct editorial job. Explain the system, identify
stakeholders, connect evidence to consequences, surface trade-offs and execution
gaps, and tell viewers what verifiable development to watch next. Do not repeat
the same background or conclusion in multiple sections.
For every section, write a distinct lower_third of at most 80 characters and a
distinct chyron of at most 64 characters. Both must summarize that section's
specific content in concise broadcast language; do not repeat the episode
headline or reuse the same overlay across sections.
Also return headline_cues in spoken order: one concise headline for every
sentence or major clause in the section narration. Each cue must describe the
specific beat being spoken, not the template, visual, or overall episode.
{source_clip_instructions}
For every section, return exactly two suggested_search_queries grounded in its linked claims:
1. A still-image, diagram, or map query using concrete people, places, objects, and events.
2. A primary-source video query using the exact event/person/location plus "official video", "raw footage", "B-roll", or "press footage". Do not request finished news coverage or broadcaster packages.
Keep each query between 4 and 10 words. Avoid abstract searches such as "benefits", "future plans", "advancements", or "latest updates" unless paired with a concrete subject and location.
Favor maps, diagrams, sourced data, infrastructure, primary documents, authentic
official footage, real product demonstrations and interfaces. Avoid generic stock,
decorative executives, broadcaster packages and visuals that merely repeat the narration.

Research pack JSON:
{json.dumps(prompt_pack, ensure_ascii=True)}
""".strip()


def enforce_target_duration(
    script: ScriptDocument, target_duration_seconds: int
) -> ScriptDocument:
    actual = float(script.estimated_duration_seconds)
    tolerance = duration_tolerance_seconds(target_duration_seconds)
    lower = target_duration_seconds - tolerance
    upper = target_duration_seconds + tolerance
    if lower <= actual <= upper:
        return script
    delta_seconds = target_duration_seconds - actual
    delta_words = round(abs(delta_seconds) * config.words_per_minute() / 60.0)
    direction = "short" if actual < lower else "long"
    adjustment = "add" if actual < lower else "remove"
    msg = (
        f"Generated script is too {direction}: estimated {round(actual)}s, "
        f"target {target_duration_seconds}s, accepted window "
        f"{round(lower)}-{round(upper)}s. {adjustment.capitalize()} about "
        f"{delta_words} spoken words while preserving grounded claim_ids."
    )
    if not config.env_bool("SYNTHPOST_STRICT_DURATION", True):
        script.warnings.append(msg)
        return script
    raise ValueError(msg)


def _long_form_section_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "text",
            "claim_ids",
            "lower_third",
            "chyron",
            "headline_cues",
            "suggested_visual_types",
            "suggested_search_queries",
            "suggested_template_ids",
            "source_clip",
        ],
        "properties": {
            "text": {"type": "string"},
            "claim_ids": {"type": "array", "items": {"type": "string"}},
            "lower_third": {"type": "string"},
            "chyron": {"type": "string"},
            "headline_cues": {
                "type": "array",
                "items": {"type": "string"},
            },
            "suggested_visual_types": {
                "type": "array",
                "items": {"type": "string"},
            },
            "suggested_search_queries": {
                "type": "array",
                "items": {"type": "string"},
            },
            "suggested_template_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "source_clip": source_clip_schema(),
        },
    }


def _long_form_base_section(
    outline: ScriptDocument, section_type: str
) -> ScriptSection:
    by_type = {section.section_type: section for section in outline.sections}
    if section_type in by_type:
        return by_type[section_type]
    fallback_types = {
        "intro": ["cold_open", "context"],
        "stakes": ["why_it_matters", "key_developments"],
        "outro": ["conclusion"],
    }
    for fallback_type in fallback_types.get(section_type, []):
        if fallback_type in by_type:
            return by_type[fallback_type]
    return outline.sections[min(len(outline.sections) - 1, 0)]


def _validate_long_form_section(
    raw: dict[str, Any],
    *,
    section_type: str,
    index: int,
    target_words: int,
    valid_claim_ids: set[str],
) -> ScriptSection:
    text = " ".join(str(raw.get("text") or "").split()).strip()
    source_clip = (
        source_clip_from_raw(raw.get("source_clip"))
        if config.source_audio_inserts_enabled()
        else None
    )
    word_count = len(text.split())
    clip_words = (
        round(source_clip.duration_seconds * config.words_per_minute() / 60.0)
        if source_clip is not None
        else 0
    )
    narration_target_words = max(16, target_words - clip_words)
    lower = max(
        16,
        min(narration_target_words, round(narration_target_words * 0.55)),
    )
    upper = round(narration_target_words * 1.55)
    if word_count < lower or word_count > upper:
        raise ValueError(
            f"{section_type} must contain {lower}-{upper} words; got {word_count}"
        )
    claim_ids = [
        str(value)
        for value in raw.get("claim_ids", [])
        if str(value) in valid_claim_ids
    ]
    if not claim_ids and section_type != "outro" and valid_claim_ids:
        claim_ids = [sorted(valid_claim_ids)[0]]
    queries = [
        " ".join(str(value).split())
        for value in raw.get("suggested_search_queries", [])
        if str(value).strip()
    ]
    queries = queries[:2]
    if not queries:
        queries = [
            f"{section_type.replace('_', ' ')} editorial photo",
            f"{section_type.replace('_', ' ')} official video",
        ]
    elif len(queries) == 1:
        queries.append(f"{queries[0]} official video")
    suggested_visual_types = [
        str(value) for value in raw.get("suggested_visual_types", ["context"])
    ]
    suggested_template_ids = [
        str(value)
        for value in raw.get("suggested_template_ids", ["split_anchor_visual"])
    ]
    if source_clip is not None:
        suggested_visual_types = list(
            dict.fromkeys(
                ["video", "primary_footage", "source_audio"]
                + suggested_visual_types
            )
        )
        queries = list(dict.fromkeys(queries[:1] + [source_clip.search_query]))
        suggested_template_ids = list(
            dict.fromkeys(suggested_template_ids + ["fullscreen_news_visual"])
        )
    return ScriptSection(
        section_id=section_id(section_type, index),
        section_type=section_type,  # type: ignore[arg-type]
        text=text,
        estimated_duration_seconds=section_total_duration(text, source_clip),
        claim_ids=list(dict.fromkeys(claim_ids)),
        suggested_visual_types=suggested_visual_types,
        suggested_search_queries=queries,
        suggested_template_ids=suggested_template_ids,
        lower_third=(
            str(raw.get("lower_third") or "").strip()[:80]
            or section_overlay_text(text, section_type, max_chars=80)
        ),
        chyron=(
            str(raw.get("chyron") or "").strip()[:64]
            or section_overlay_text(text, section_type, max_chars=64)
        ),
        headline_cues=normalize_section_headline_cues(
            text,
            section_type,
            [
                str(value)
                for value in raw.get("headline_cues", [])
                if str(value).strip()
            ],
        ),
        source_clip=source_clip,
        approval_status=ApprovalStatus.review,
    )


def expand_long_form_script(
    provider,
    outline: ScriptDocument,
    pack: dict[str, Any],
    *,
    target_duration_seconds: int,
    narration_mode: NarrationMode | str = NarrationMode.explained,
    audit_callback: Callable[[str, str, list[dict[str, Any]], list[dict[str, Any]]], None] | None = None,
    reusable_audits: dict[str, GenerationAudit] | None = None,
) -> tuple[ScriptDocument, int]:
    targets = section_word_targets(target_duration_seconds)
    compact_pack = compact_research_pack_for_prompt(pack)
    valid_claim_ids = {
        str(claim.get("claim_id"))
        for claim in compact_pack.get("claims", [])
        if claim.get("claim_id")
    }
    sections: list[ScriptSection] = []
    attempt_count = 0
    source_clip_instruction = (
        """Return source_clip as null unless the evidence supports a specific
original audio moment that deserves to interrupt narration. When present, the
section text must set it up; provide its exact source-oriented search query,
intended speaker/verified quote when known, 3-30 second duration, editorial
description, and natural fallback_narration. The source clip duration is part
of this section's time budget, so reduce spoken words accordingly."""
        if config.source_audio_inserts_enabled()
        else """Source-audio inserts are disabled for production. Return
source_clip as null. Treat every external video as muted B-roll and write
continuous anchor narration without promising an audible clip."""
    )
    for index, (section_type, target_words) in enumerate(targets.items(), start=1):
        base = _long_form_base_section(outline, section_type)
        payload = {
            "headline": outline.headline,
            "section_type": section_type,
            "target_words": target_words,
            "base_outline_text": base.text,
            "base_claim_ids": base.claim_ids,
            "research": section_research_context(compact_pack, base.claim_ids),
        }
        prompt = f"""
You are performing a long-form section expansion for SynthPost Studio.
Write only this one section of a grounded spoken-news script.

{charter_prompt_context(show_format=normalize_narration_mode(narration_mode, target_duration_seconds=target_duration_seconds))}

Section type: {section_type}
Exact target: approximately {target_words} words.
Use only facts supported by the supplied claims/evidence. Do not invent or
generalize beyond them. Develop chronology, explanation, practical implications,
caveats, and transitions appropriate to this section without repeating the base
draft sentence-by-sentence. Use natural paragraphs, not bullets.

Return exactly two grounded visual queries: first a concrete still/map/diagram;
second an official primary-source video/raw-footage/B-roll query. Never request a
finished broadcaster news package.

Return a lower_third of at most 80 characters and a chyron of at most 64
characters that specifically summarize this section rather than the episode.
Return headline_cues in spoken order, with one concise headline for each
sentence or major clause in the narration.
{source_clip_instruction}

Return only JSON matching this schema:
{json.dumps(_long_form_section_schema())}

INPUT JSON:
{json.dumps(payload, ensure_ascii=True)}
""".strip()
        stage = f"long_form:{section_type}"
        reusable = (reusable_audits or {}).get(stage)
        reused = False
        if (
            reusable is not None
            and reusable.prompt_text == prompt
            and isinstance(reusable.response, dict)
        ):
            try:
                section = _validate_long_form_section(
                    reusable.response,
                    section_type=section_type,
                    index=index,
                    target_words=target_words,
                    valid_claim_ids=valid_claim_ids,
                )
                attempts = [
                    {
                        "attempt": 0,
                        "ok": True,
                        "prompt": prompt,
                        "raw": reusable.response,
                        "provider": reusable.provider,
                        "model": reusable.model,
                        "elapsed_seconds": 0.0,
                        "reused_checkpoint": True,
                    }
                ]
                reused = True
            except Exception:
                reusable = None
        if reusable is None:
            try:
                section, attempts = structured_generate(
                    provider,
                    prompt,
                    _long_form_section_schema(),
                    lambda raw, st=section_type, idx=index, tw=target_words: (
                        _validate_long_form_section(
                            raw,
                            section_type=st,
                            index=idx,
                            target_words=tw,
                            valid_claim_ids=valid_claim_ids,
                        )
                    ),
                    max_retries=2,
                )
            except StructuredGenerationError as exc:
                if audit_callback:
                    audit_callback(stage, prompt, exc.attempts, [])
                raise
        if audit_callback and not reused:
            audit_callback(
                stage,
                prompt,
                attempts,
                [
                    {
                        "kind": "section_validation",
                        "section_type": section_type,
                        "target_words": target_words,
                        "actual_words": len(section.text.split()),
                        "accepted": True,
                    }
                ],
            )
        sections.append(section)
        attempt_count += len(attempts)
    expanded = outline.model_copy(deep=True)
    expanded.script_id = new_id("script")
    expanded.sections = sections
    expanded.estimated_duration_seconds = round(
        sum(section.estimated_duration_seconds for section in sections), 2
    )
    expanded.status = ScriptStatus.review
    expanded.created_at = now_iso()
    expanded.updated_at = expanded.created_at
    expanded = ScriptDocument.model_validate(expanded.model_dump(mode="json"))
    return expanded, attempt_count


def _headline_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["headline", "dek", "sections"],
        "properties": {
            "headline": {"type": "string"},
            "dek": {"type": "string"},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["section_id", "lower_third", "chyron", "cues"],
                    "properties": {
                        "section_id": {"type": "string"},
                        "lower_third": {"type": "string"},
                        "chyron": {"type": "string"},
                        "cues": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["beat_id", "text"],
                                "properties": {
                                    "beat_id": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def headline_editor_prompt(script: ScriptDocument, pack: dict[str, Any]) -> tuple[str, dict[str, list[str]]]:
    charter = load_editorial_charter()
    claim_by_id = {
        str(claim.get("claim_id")): str(claim.get("claim_text") or "")
        for claim in pack.get("claims", [])
        if claim.get("claim_id")
    }
    expected: dict[str, list[str]] = {}
    sections: list[dict[str, Any]] = []
    for section in script.sections:
        beats = narration_beats(section.text)
        beat_rows = []
        expected[section.section_id] = []
        for index, beat in enumerate(beats or [section.text], start=1):
            beat_id = f"{section.section_id}_beat_{index:02d}"
            expected[section.section_id].append(beat_id)
            beat_rows.append({"beat_id": beat_id, "narration": beat})
        sections.append(
            {
                "section_id": section.section_id,
                "section_type": section.section_type,
                "beats": beat_rows,
                "linked_claims": [
                    claim_by_id[claim_id]
                    for claim_id in section.claim_ids
                    if claim_id in claim_by_id
                ],
            }
        )
    payload = {
        "working_headline": script.headline,
        "research_summary": pack.get("research_summary", ""),
        "systems": pack.get("systems", []),
        "stakeholders": pack.get("stakeholders", []),
        "trade_offs": pack.get("trade_offs", []),
        "execution_gaps": pack.get("execution_gaps", []),
        "sections": sections,
    }
    rules = charter["headline_rules"]
    prompt = f"""
You are SynthPost's senior headline editor. The narration is final. Write the
episode headline, dek, section lower thirds, chyrons and timed beat headlines.

{charter_prompt_context(show_format=script.narration_mode.value)}

Editorial rules:
- Episode headline: {rules['episode_words'][0]}-{rules['episode_words'][1]} words, maximum {rules['episode_max_chars']} characters.
- Beat headline: usually {rules['cue_words'][0]}-{rules['cue_words'][1]} words.
- Use sentence case, active voice, named actors, concrete developments and supported consequences.
- Every headline must stand alone and remain faithful to its narration beat and linked claims.
- Do not copy narration word-for-word. Do not end on an incomplete phrase.
- Do not reuse a headline for different beats or use sensational language.
- Avoid: {'; '.join(rules['avoid'])}.
- Return exactly one cue for every beat_id and preserve every supplied section_id and beat_id.
- Never mention templates, visuals, production instructions or the source publication.

Return only JSON matching this schema:
{json.dumps(_headline_schema())}

INPUT JSON:
{json.dumps(payload, ensure_ascii=True)}
""".strip()
    return prompt, expected


def _validate_headline_response(
    raw: dict[str, Any], expected: dict[str, list[str]]
) -> dict[str, Any]:
    headline = " ".join(str(raw.get("headline") or "").split())
    if not headline:
        raise ValueError("headline must be present")
    rows = raw.get("sections")
    if not isinstance(rows, list):
        raise ValueError("headline response must contain a sections array")
    by_section = {str(row.get("section_id")): row for row in rows if isinstance(row, dict)}
    if set(by_section) != set(expected):
        raise ValueError("headline response must preserve every section_id exactly")
    for section_id, beat_ids in expected.items():
        row = by_section[section_id]
        lower = " ".join(str(row.get("lower_third") or "").split())
        chyron = " ".join(str(row.get("chyron") or "").split())
        if not lower:
            raise ValueError(f"{section_id} lower_third must be present")
        if not chyron:
            raise ValueError(f"{section_id} chyron must be present")
        cues = row.get("cues")
        if not isinstance(cues, list):
            raise ValueError(f"{section_id} cues must be an array")
        cue_map = {str(cue.get("beat_id")): cue for cue in cues if isinstance(cue, dict)}
        if list(cue_map) != beat_ids:
            raise ValueError(f"{section_id} must preserve beat IDs in spoken order")
        for beat_id, cue in cue_map.items():
            text = " ".join(str(cue.get("text") or "").split())
            if not text:
                raise ValueError(f"{beat_id} headline must be present")
    return raw


def apply_headline_response(
    script: ScriptDocument, raw: dict[str, Any]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    previous_headline = script.headline
    script.headline = " ".join(str(raw["headline"]).split())[:110]
    script.dek = " ".join(str(raw.get("dek") or script.dek).split())[:180]
    events.append(
        {
            "kind": "episode_headline_replaced",
            "before": previous_headline,
            "after": script.headline,
            "reason": "dedicated charter headline pass",
        }
    )
    rows = {str(row["section_id"]): row for row in raw["sections"]}
    for section in script.sections:
        row = rows[section.section_id]
        previous = {
            "lower_third": section.lower_third,
            "chyron": section.chyron,
            "headline_cues": list(section.headline_cues),
        }
        section.lower_third = " ".join(str(row["lower_third"]).split())[:80]
        section.chyron = " ".join(str(row["chyron"]).split())[:64]
        section.headline_cues = [
            " ".join(str(cue["text"]).split())[:80] for cue in row["cues"]
        ]
        events.append(
            {
                "kind": "section_overlays_replaced",
                "section_id": section.section_id,
                "before": previous,
                "after": {
                    "lower_third": section.lower_third,
                    "chyron": section.chyron,
                    "headline_cues": list(section.headline_cues),
                },
                "reason": "headlines aligned to final narration beats",
            }
        )
    script.lower_thirds = [section.lower_third for section in script.sections]
    script.chyrons = [section.chyron for section in script.sections]
    return events


def _save_generation_audit(
    repository,
    *,
    story_id: str,
    stage: str,
    prompt_version: str,
    prompt: str,
    attempts: list[dict[str, Any]],
    normalization_events: list[dict[str, Any]] | None = None,
) -> None:
    latest = attempts[-1] if attempts else {}
    validation_events = [
        {
            "attempt": attempt.get("attempt"),
            "ok": attempt.get("ok", False),
            "error": attempt.get("error"),
        }
        for attempt in attempts
    ]
    repository.save_generation_audit(
        GenerationAudit(
            story_id=story_id,
            stage=stage,
            prompt_version=prompt_version,
            charter_version=CHARTER_VERSION,
            provider=str(latest.get("provider") or "unknown"),
            model=latest.get("model"),
            prompt_text=prompt,
            response=latest.get("raw") if isinstance(latest.get("raw"), dict) else None,
            attempts=attempts,
            validation_events=validation_events,
            normalization_events=normalization_events or [],
            status="completed" if latest.get("ok") else "failed",
        )
    )


def _run_audited_stage(
    repository,
    *,
    story_id: str,
    stage: str,
    prompt_version: str,
    prompt: str,
    schema: dict[str, Any],
    validator,
    provider,
    max_retries: int = 2,
    normalization_events: list[dict[str, Any]] | None = None,
):
    try:
        value, attempts = structured_generate(
            provider,
            prompt,
            schema,
            validator,
            max_retries=max_retries,
        )
    except StructuredGenerationError as exc:
        attempts = list(exc.attempts)
        fallback = getattr(provider, "fallback", None)
        fallback_name = getattr(fallback, "name", None)
        last_provider = str(attempts[-1].get("provider") or "") if attempts else ""
        if fallback is not None and fallback_name and last_provider != fallback_name:
            try:
                value, fallback_attempts = structured_generate(
                    fallback,
                    prompt,
                    schema,
                    validator,
                    max_retries=max_retries,
                )
                for offset, attempt in enumerate(fallback_attempts, start=len(attempts) + 1):
                    attempt["attempt"] = offset
                attempts.extend(fallback_attempts)
                if hasattr(provider, "last_provider"):
                    provider.last_provider = fallback_name
                if hasattr(provider, "last_model"):
                    provider.last_model = getattr(fallback, "last_model", None)
            except StructuredGenerationError as fallback_exc:
                for offset, attempt in enumerate(
                    fallback_exc.attempts, start=len(attempts) + 1
                ):
                    attempt["attempt"] = offset
                attempts.extend(fallback_exc.attempts)
                _save_generation_audit(
                    repository,
                    story_id=story_id,
                    stage=stage,
                    prompt_version=prompt_version,
                    prompt=prompt,
                    attempts=attempts,
                )
                raise StructuredGenerationError(
                    f"Structured generation failed across hosted providers: "
                    f"{attempts[-1].get('error')}",
                    attempts,
                ) from fallback_exc
        else:
            _save_generation_audit(
                repository,
                story_id=story_id,
                stage=stage,
                prompt_version=prompt_version,
                prompt=prompt,
                attempts=attempts,
            )
            raise
    _save_generation_audit(
        repository,
        story_id=story_id,
        stage=stage,
        prompt_version=prompt_version,
        prompt=prompt,
        attempts=attempts,
        normalization_events=normalization_events,
    )
    return value, attempts


def _run_or_reuse_audited_stage(
    repository,
    *,
    story_id: str,
    stage: str,
    prompt_version: str,
    prompt: str,
    schema: dict[str, Any],
    validator,
    provider,
    max_retries: int = 2,
    normalization_events: list[dict[str, Any]] | None = None,
):
    stage_normalization_events = list(normalization_events or [])
    checkpoint = next(
        (
            audit
            for audit in repository.list_generation_audits(story_id, limit=100)
            if audit.stage == stage
            and audit.prompt_version == prompt_version
            and audit.status == "completed"
            and audit.prompt_text == prompt
            and isinstance(audit.response, dict)
        ),
        None,
    )
    if checkpoint is not None:
        try:
            value = validator(checkpoint.response)
            return value, [
                {
                    "attempt": 0,
                    "ok": True,
                    "prompt": prompt,
                    "raw": checkpoint.response,
                    "provider": checkpoint.provider,
                    "model": checkpoint.model,
                    "elapsed_seconds": 0.0,
                    "reused_checkpoint": True,
                }
            ]
        except Exception as exc:
            stage_normalization_events.append(
                {
                    "event": "checkpoint_invalidated",
                    "reason": str(exc)[:500],
                }
            )
    return _run_audited_stage(
        repository,
        story_id=story_id,
        stage=stage,
        prompt_version=prompt_version,
        prompt=prompt,
        schema=schema,
        validator=validator,
        provider=provider,
        max_retries=max_retries,
        normalization_events=stage_normalization_events,
    )


def _script_normalization_events(
    raw: dict[str, Any], script: ScriptDocument
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    raw_sections = raw.get("sections", []) if isinstance(raw, dict) else []
    for index, section in enumerate(script.sections):
        source = raw_sections[index] if index < len(raw_sections) and isinstance(raw_sections[index], dict) else {}
        before_claims = [str(value) for value in source.get("claim_ids", [])]
        if before_claims != section.claim_ids:
            events.append(
                {
                    "kind": "claim_ids_filtered",
                    "section_id": section.section_id,
                    "before": before_claims,
                    "after": list(section.claim_ids),
                    "reason": "removed claim IDs absent from the research pack",
                }
            )
        before_cues = [str(value) for value in source.get("headline_cues", [])]
        if before_cues != section.headline_cues:
            events.append(
                {
                    "kind": "headline_cues_normalized",
                    "section_id": section.section_id,
                    "before": before_cues,
                    "after": list(section.headline_cues),
                    "reason": "aligned cue count to deterministic narration beats",
                }
            )
        for field in ("lower_third", "chyron"):
            before = str(source.get(field) or "")
            after = str(getattr(section, field))
            if before != after:
                events.append(
                    {
                        "kind": f"{field}_normalized",
                        "section_id": section.section_id,
                        "before": before,
                        "after": after,
                        "reason": "filled, shortened or deduplicated against the final section narration",
                    }
                )
    return events


def _generate_with_provider(
    provider,
    prompt: str,
    schema: dict[str, Any],
    validator,
    *,
    max_retries: int = 2,
) -> tuple[ScriptDocument, list[dict[str, Any]], Any, list[str]]:
    value, attempts = structured_generate(
        provider,
        prompt,
        schema,
        validator,
        max_retries=max_retries,
    )
    return value, attempts, provider, []


def generate_script(
    repository,
    story_id: str,
    *,
    provider_name: str | None = None,
    target_duration_seconds: int = 600,
    narration_mode: NarrationMode | str = NarrationMode.explained,
    progress_callback: Callable[[float, str], None] | None = None,
) -> ScriptDocument:
    def report(fraction: float, stage: str) -> None:
        if progress_callback is not None:
            progress_callback(max(0.0, min(1.0, fraction)), stage)

    pack = repository.latest_research_pack(story_id)
    if not pack:
        raise ValueError(f"No research pack exists for story: {story_id}")
    _assert_story_can_enter_script_review(repository, story_id)
    provider = configured_provider(provider_name)
    selected_mode = NarrationMode(
        normalize_narration_mode(
            narration_mode,
            target_duration_seconds=target_duration_seconds,
        )
    )

    candidate = repository.candidate_for_story(story_id)
    if candidate.workflow_state in {
        StoryWorkflowState.research_ready,
        StoryWorkflowState.script_review,
    }:
        repository.transition_story(story_id, StoryWorkflowState.script_generating)

    report(0.03, "planning one coherent narrative arc")
    brief_prompt = narrative_brief_prompt(
        pack,
        target_duration_seconds=target_duration_seconds,
        primary_topic=candidate.editorial_fit.primary_topic,
        narration_mode=selected_mode,
    )
    brief, brief_attempts = _run_or_reuse_audited_stage(
        repository,
        story_id=story_id,
        stage="narrative_brief",
        prompt_version=NARRATIVE_BRIEF_PROMPT_VERSION,
        prompt=brief_prompt,
        schema=narrative_brief_schema(),
        validator=lambda raw: _validate_narrative_brief(raw, pack),
        provider=provider,
    )

    report(0.22, "writing uninterrupted narration")
    draft_prompt = narrative_draft_prompt(
        brief,
        pack,
        target_duration_seconds=target_duration_seconds,
        primary_topic=candidate.editorial_fit.primary_topic,
        narration_mode=selected_mode,
    )
    draft, draft_attempts = _run_or_reuse_audited_stage(
        repository,
        story_id=story_id,
        stage="narrative_draft",
        prompt_version=NARRATIVE_DRAFT_PROMPT_VERSION,
        prompt=draft_prompt,
        schema=narrative_draft_schema(),
        validator=lambda raw: _validate_narrative_draft(
            raw, pack, target_duration_seconds=target_duration_seconds
        ),
        provider=provider,
    )

    report(0.55, "checking repetition and narrative continuity")
    quality_issues = narrative_quality_issues(draft)
    repair_attempts: list[dict[str, Any]] = []
    if quality_issues:
        repair_prompt = narrative_repair_prompt(
            draft,
            brief,
            pack,
            quality_issues,
            target_duration_seconds=target_duration_seconds,
            primary_topic=candidate.editorial_fit.primary_topic,
            narration_mode=selected_mode,
        )
        draft, repair_attempts = _run_or_reuse_audited_stage(
            repository,
            story_id=story_id,
            stage="narrative_repair",
            prompt_version=NARRATIVE_REPAIR_PROMPT_VERSION,
            prompt=repair_prompt,
            schema=narrative_draft_schema(),
            validator=lambda raw: _validate_narrative_draft(
                raw, pack, target_duration_seconds=target_duration_seconds
            ),
            provider=provider,
            normalization_events=[
                {
                    "kind": "narrative_quality_repair",
                    "failures": quality_issues,
                }
            ],
        )
        remaining_issues = narrative_quality_issues(draft)
        if remaining_issues:
            raise ValueError(
                "Narrative quality gate failed after repair: "
                + "; ".join(remaining_issues)
            )

    report(0.7, "segmenting accepted narration without rewriting it")
    segment_prompt = narrative_segmentation_prompt(
        draft,
        brief,
        source_audio_enabled=config.source_audio_inserts_enabled(),
    )
    segmentation, segment_attempts = _run_or_reuse_audited_stage(
        repository,
        story_id=story_id,
        stage="narrative_segmentation",
        prompt_version=NARRATIVE_SEGMENT_PROMPT_VERSION,
        prompt=segment_prompt,
        schema=narrative_segmentation_schema(),
        validator=lambda raw: _validate_narrative_segmentation(raw, draft),
        provider=provider,
    )
    value = script_from_narrative(story_id, draft, segmentation, pack)
    value.narration_mode = selected_mode
    value = enforce_target_duration(value, target_duration_seconds)

    report(0.86, "aligning headlines to final narration")
    headline_prompt, expected_beats = headline_editor_prompt(value, pack)
    headline_fallback = False
    try:
        headline_raw, headline_attempts = structured_generate(
            provider,
            headline_prompt,
            _headline_schema(),
            lambda raw: _validate_headline_response(raw, expected_beats),
            max_retries=2,
        )
    except StructuredGenerationError as exc:
        _save_generation_audit(
            repository,
            story_id=story_id,
            stage="headline_editor",
            prompt_version=HEADLINE_PROMPT_VERSION,
            prompt=headline_prompt,
            attempts=exc.attempts,
        )
        # The narration has already passed its grounding, duration, continuity,
        # and segmentation gates. Headline decoration must not discard that
        # accepted work when a provider reorders or omits overlay cue IDs. Keep
        # the narrative's deterministic metadata and surface the fallback in
        # warnings/audits instead.
        headline_attempts = list(exc.attempts)
        headline_fallback = True
    else:
        headline_events = apply_headline_response(value, headline_raw)
        _save_generation_audit(
            repository,
            story_id=story_id,
            stage="headline_editor",
            prompt_version=HEADLINE_PROMPT_VERSION,
            prompt=headline_prompt,
            attempts=headline_attempts,
            normalization_events=headline_events,
        )
    total_attempts = (
        len(brief_attempts)
        + len(draft_attempts)
        + len(repair_attempts)
        + len(segment_attempts)
        + len(headline_attempts)
    )
    generation_warnings = [
        f"llm_provider={provider.name}",
        f"structured_attempts={total_attempts}",
        f"editorial_charter={CHARTER_VERSION}",
        "narrative_first=true",
        f"narrative_brief_prompt={NARRATIVE_BRIEF_PROMPT_VERSION}",
        f"narrative_draft_prompt={NARRATIVE_DRAFT_PROMPT_VERSION}",
        f"narrative_segment_prompt={NARRATIVE_SEGMENT_PROMPT_VERSION}",
        "narrative_quality_gate=passed",
        f"headline_prompt={HEADLINE_PROMPT_VERSION}",
        f"narration_mode={selected_mode.value}",
    ]
    if repair_attempts:
        generation_warnings.append("narrative_repaired=true")
    if headline_fallback:
        generation_warnings.append("headline_editor=fallback_to_narrative_metadata")
    model = getattr(provider, "last_model", None)
    if model:
        generation_warnings.append(f"llm_model={model}")
    value.warnings.extend(generation_warnings)
    script = repository.save_script(value)
    _move_story_to_script_review(repository, story_id)
    report(1.0, "coherent production script ready for review")
    return script


def save_manual_script(
    repository, story_id: str, headline: str, text: str, *, category: str = "manual"
) -> ScriptDocument:
    _assert_story_can_enter_script_review(repository, story_id)
    previous = repository.latest_script(story_id)
    script = split_manual_script(story_id, headline, text, category=category)
    if previous:
        # Editing narration in Studio should not sever the research and visual
        # provenance produced by the structured-generation pass. Paragraphs map
        # one-to-one to sections in the editor, so carry section metadata forward
        # by position while deliberately resetting approval to review.
        if category == "manual":
            script.category = previous.category
        script.source_ids = list(previous.source_ids)
        script.warnings = list(previous.warnings)
        script.narration_mode = previous.narration_mode
        for edited, original in zip(script.sections, previous.sections):
            edited.section_id = original.section_id
            edited.section_type = original.section_type
            edited.claim_ids = list(original.claim_ids)
            edited.suggested_visual_types = list(original.suggested_visual_types)
            edited.suggested_search_queries = list(original.suggested_search_queries)
            edited.suggested_template_ids = list(original.suggested_template_ids)
            edited.source_clip = (
                original.source_clip.model_copy(deep=True)
                if original.source_clip and config.source_audio_inserts_enabled()
                else None
            )
            edited.estimated_duration_seconds = section_total_duration(
                edited.text, edited.source_clip
            )
            edited.editorial_notes = list(original.editorial_notes)
        script.estimated_duration_seconds = round(
            sum(section.estimated_duration_seconds for section in script.sections), 2
        )
    saved = repository.save_script(script)
    candidate = repository.candidate_for_story(story_id)
    if candidate.workflow_state in {
        StoryWorkflowState.selected,
        StoryWorkflowState.research_ready,
        StoryWorkflowState.script_generating,
    }:
        if candidate.workflow_state == StoryWorkflowState.selected:
            repository.transition_story(story_id, StoryWorkflowState.researching)
            repository.transition_story(story_id, StoryWorkflowState.research_ready)
    _move_story_to_script_review(repository, story_id)
    return saved


def approve_script(
    repository, story_id: str, script_id: str | None = None
) -> ScriptDocument:
    script = repository.latest_script(story_id) if script_id is None else None
    if script_id is not None:
        raise NotImplementedError(
            "approving arbitrary script_id is handled by repository.update_script_status"
        )
    if not script:
        raise ValueError(f"No script exists for story: {story_id}")
    _move_story_to_script_review(repository, story_id)
    updated = repository.update_script_status(script.script_id, ScriptStatus.approved)
    repository.transition_story(story_id, StoryWorkflowState.script_approved)
    return updated


def validate_grounding(script: ScriptDocument, pack: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    claim_ids = {
        claim.get("claim_id")
        for claim in pack.get("claims", [])
        if claim.get("claim_id")
    }
    evidence_ids = {
        ev.get("evidence_id")
        for ev in pack.get("evidence", [])
        if ev.get("evidence_id")
    }
    supported_claims = {
        claim.get("claim_id")
        for claim in pack.get("claims", [])
        if claim.get("supported") and set(claim.get("evidence_ids", [])) <= evidence_ids
    }
    sections_that_do_not_need_claim_links = {"cold_open", "outro"}
    for section in script.sections:
        if (
            not section.claim_ids
            and section.section_type not in sections_that_do_not_need_claim_links
        ):
            warnings.append(f"{section.section_id}: no linked claim_ids")
        for claim_id in section.claim_ids:
            if claim_id not in claim_ids:
                warnings.append(f"{section.section_id}: unknown claim_id {claim_id}")
            elif claim_id not in supported_claims:
                warnings.append(
                    f"{section.section_id}: claim {claim_id} is not fully supported"
                )
    grounded_number_text = " ".join(
        [
            *(str(value) for value in pack.get("numbers", [])),
            *(str(value) for value in pack.get("dates", [])),
            *(
                str(claim.get("claim_text") or "")
                for claim in pack.get("claims", [])
            ),
            *(
                str(evidence.get("excerpt") or "")
                for evidence in pack.get("evidence", [])
            ),
        ]
    )
    grounded_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", grounded_number_text))
    script_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", script.text))
    unsupported_numbers = sorted(script_numbers - grounded_numbers)
    if unsupported_numbers:
        warnings.append(
            "script contains numbers that were not observed in the research pack: "
            + ", ".join(unsupported_numbers)
        )
    if '"' in script.text or "“" in script.text or "”" in script.text:
        warnings.append("direct quotation marks require explicit evidence review")
    return warnings
