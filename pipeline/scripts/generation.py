from __future__ import annotations

import json
import re
from typing import Any

from pipeline import config
from pipeline.llm.providers import (
    configured_provider,
    structured_generate,
)
from pipeline.models import (
    ApprovalStatus,
    ScriptDocument,
    ScriptSection,
    ScriptStatus,
    StoryWorkflowState,
    new_id,
    now_iso,
    normalize_section_headline_cues,
    section_overlay_text,
)

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
                    "url",
                    "title",
                    "publisher",
                    "published_at",
                    "discovery_method",
                    "research_query",
                    "relevance_score",
                    "extraction_status",
                    "warnings",
                )
            }
            for document in pack.get("documents", [])
        ],
        "claims": [
            {
                key: claim.get(key)
                for key in (
                    "claim_id",
                    "claim_text",
                    "claim_type",
                    "confidence",
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
                "excerpt": str(evidence.get("excerpt") or "")[:280],
            }
            for evidence in pack.get("evidence", [])
        ],
        "organizations": pack.get("organizations", [])[:20],
        "locations": pack.get("locations", [])[:20],
        "numbers": pack.get("numbers", [])[:30],
        "dates": pack.get("dates", [])[:20],
        "uncertainties": pack.get("uncertainties", []),
    }


def estimate_duration(text: str) -> float:
    words = len(text.split())
    return round(max(3.0, words / config.words_per_minute() * 60.0), 2)


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
                    ],
                    "properties": {
                        "section_type": {"type": "string"},
                        "text": {"type": "string"},
                        "claim_ids": {"type": "array", "items": {"type": "string"}},
                        "lower_third": {"type": "string", "maxLength": 80},
                        "chyron": {"type": "string", "maxLength": 64},
                        "headline_cues": {
                            "type": "array",
                            "items": {"type": "string", "maxLength": 80},
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
        sections.append(
            ScriptSection(
                section_id=section_id(section_type, index),
                section_type=section_type,  # type: ignore[arg-type]
                text=text,
                estimated_duration_seconds=estimate_duration(text),
                claim_ids=used_claim_ids,
                suggested_visual_types=[
                    str(value)
                    for value in item.get("suggested_visual_types", ["context"])
                ],
                suggested_search_queries=[
                    str(value)
                    for value in item.get(
                        "suggested_search_queries", [raw.get("headline", "")]
                    )
                ],
                suggested_template_ids=[
                    str(value)
                    for value in item.get(
                        "suggested_template_ids", ["split_anchor_visual"]
                    )
                ],
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
                editorial_notes=[],
                approval_status=ApprovalStatus.review,
            )
        )
    if not sections:
        raise ValueError("LLM returned no script sections")
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
    pack: dict[str, Any], *, target_duration_seconds: int = 600
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
    return f"""
You are SynthPost Studio's local newsroom writer. Create a grounded section-based news script.
Use only the supplied research pack. Do not fabricate quotes, statistics, names, dates, or attribution.
Return only JSON matching the provided response schema.

Target duration: {target_duration_seconds} seconds.
Estimated narration target: about {words} spoken words.
Accepted duration window: {min_seconds}-{max_seconds} seconds, approximately {min_words}-{max_words} words.
Do not return a short default script. Match the requested runtime by expanding or tightening the section text while staying grounded in the research pack.
Write full paragraph narration, not bullet summaries. For long runtimes, add sourced background, careful chronology, implications, caveats, and transitions.
Approximate section word targets:
{section_target_text}
Required tone: clear spoken delivery, no clickbait, separate facts from uncertainty.
Required section types to use when appropriate: {", ".join(SECTION_ORDER)}.
Every factual section must include claim_ids from the pack.
For every section, write a distinct lower_third of at most 80 characters and a
distinct chyron of at most 64 characters. Both must summarize that section's
specific content in concise broadcast language; do not repeat the episode
headline or reuse the same overlay across sections.
Also return headline_cues in spoken order: one concise headline for every
sentence or major clause in the section narration. Each cue must describe the
specific beat being spoken, not the template, visual, or overall episode.
For every section, return exactly two suggested_search_queries grounded in its linked claims:
1. A still-image, diagram, or map query using concrete people, places, objects, and events.
2. A primary-source video query using the exact event/person/location plus "official video", "raw footage", "B-roll", or "press footage". Do not request finished news coverage or broadcaster packages.
Keep each query between 4 and 10 words. Avoid abstract searches such as "benefits", "future plans", "advancements", or "latest updates" unless paired with a concrete subject and location.

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
        ],
        "properties": {
            "text": {"type": "string"},
            "claim_ids": {"type": "array", "items": {"type": "string"}},
            "lower_third": {"type": "string", "maxLength": 80},
            "chyron": {"type": "string", "maxLength": 64},
            "headline_cues": {
                "type": "array",
                "items": {"type": "string", "maxLength": 80},
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
    word_count = len(text.split())
    lower = max(45, round(target_words * 0.72))
    upper = round(target_words * 1.35)
    if word_count < lower or word_count > upper:
        raise ValueError(
            f"{section_type} must contain {lower}-{upper} words; got {word_count}"
        )
    claim_ids = [
        str(value)
        for value in raw.get("claim_ids", [])
        if str(value) in valid_claim_ids
    ]
    if not claim_ids and section_type != "outro":
        raise ValueError(f"{section_type} must link at least one valid claim_id")
    queries = [
        " ".join(str(value).split())
        for value in raw.get("suggested_search_queries", [])
        if str(value).strip()
    ]
    if len(queries) != 2:
        raise ValueError(f"{section_type} must return exactly two search queries")
    return ScriptSection(
        section_id=section_id(section_type, index),
        section_type=section_type,  # type: ignore[arg-type]
        text=text,
        estimated_duration_seconds=estimate_duration(text),
        claim_ids=list(dict.fromkeys(claim_ids)),
        suggested_visual_types=[
            str(value)
            for value in raw.get("suggested_visual_types", ["context"])
        ],
        suggested_search_queries=queries,
        suggested_template_ids=[
            str(value)
            for value in raw.get(
                "suggested_template_ids", ["split_anchor_visual"]
            )
        ],
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
        approval_status=ApprovalStatus.review,
    )


def expand_long_form_script(
    provider,
    outline: ScriptDocument,
    pack: dict[str, Any],
    *,
    target_duration_seconds: int,
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
    for index, (section_type, target_words) in enumerate(targets.items(), start=1):
        base = _long_form_base_section(outline, section_type)
        payload = {
            "headline": outline.headline,
            "section_type": section_type,
            "target_words": target_words,
            "base_outline_text": base.text,
            "base_claim_ids": base.claim_ids,
            "research": compact_pack,
        }
        prompt = f"""
You are performing a long-form section expansion for SynthPost Studio.
Write only this one section of a grounded spoken-news script.

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

Return only JSON matching this schema:
{json.dumps(_long_form_section_schema())}

INPUT JSON:
{json.dumps(payload, ensure_ascii=True)}
""".strip()
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
) -> ScriptDocument:
    pack = repository.latest_research_pack(story_id)
    if not pack:
        raise ValueError(f"No research pack exists for story: {story_id}")
    provider = configured_provider() if provider_name is None else configured_provider()
    if provider_name == "mock":
        from pipeline.llm.providers import MockProvider

        provider = MockProvider()

    candidate = repository.candidate_for_story(story_id)
    if candidate.workflow_state in {
        StoryWorkflowState.research_ready,
        StoryWorkflowState.script_review,
    }:
        repository.transition_story(story_id, StoryWorkflowState.script_generating)
    value, attempts, selected_provider, fallback_errors = _generate_with_provider(
        provider,
        generation_prompt(pack, target_duration_seconds=target_duration_seconds),
        script_schema(),
        lambda raw: script_from_llm_json(story_id, raw, pack),
        max_retries=2,
    )
    expansion_attempts = 0
    tolerance = duration_tolerance_seconds(target_duration_seconds)
    if (
        target_duration_seconds >= 240
        and value.estimated_duration_seconds < target_duration_seconds - tolerance
    ):
        value, expansion_attempts = expand_long_form_script(
            selected_provider,
            value,
            pack,
            target_duration_seconds=target_duration_seconds,
        )
    value = enforce_target_duration(value, target_duration_seconds)
    generation_warnings = [
        f"llm_provider={selected_provider.name}",
        f"structured_attempts={len(attempts)}",
    ]
    if expansion_attempts:
        generation_warnings.extend(
            [
                "long_form_chunked_expansion=true",
                f"long_form_expansion_attempts={expansion_attempts}",
            ]
        )
    model = getattr(selected_provider, "last_model", None)
    if model:
        generation_warnings.append(f"llm_model={model}")
    value.warnings.extend(generation_warnings)
    script = repository.save_script(value)
    try:
        repository.transition_story(story_id, StoryWorkflowState.script_review)
    except Exception:
        pass
    return script


def save_manual_script(
    repository, story_id: str, headline: str, text: str, *, category: str = "manual"
) -> ScriptDocument:
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
        for edited, original in zip(script.sections, previous.sections):
            edited.section_id = original.section_id
            edited.section_type = original.section_type
            edited.claim_ids = list(original.claim_ids)
            edited.suggested_visual_types = list(original.suggested_visual_types)
            edited.suggested_search_queries = list(original.suggested_search_queries)
            edited.suggested_template_ids = list(original.suggested_template_ids)
            edited.editorial_notes = list(original.editorial_notes)
    saved = repository.save_script(script)
    candidate = repository.candidate_for_story(story_id)
    if candidate.workflow_state in {
        StoryWorkflowState.selected,
        StoryWorkflowState.research_ready,
        StoryWorkflowState.script_generating,
    }:
        try:
            if candidate.workflow_state == StoryWorkflowState.selected:
                repository.transition_story(story_id, StoryWorkflowState.researching)
                repository.transition_story(story_id, StoryWorkflowState.research_ready)
            if (
                repository.candidate_for_story(story_id).workflow_state
                == StoryWorkflowState.research_ready
            ):
                repository.transition_story(story_id, StoryWorkflowState.script_review)
        except Exception:
            pass
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
    for section in script.sections:
        if section.approval_status not in {
            ApprovalStatus.approved,
            ApprovalStatus.locked,
        }:
            section.approval_status = ApprovalStatus.approved
    updated = repository.update_script_status(script.script_id, ScriptStatus.approved)
    try:
        repository.transition_story(story_id, StoryWorkflowState.script_approved)
    except Exception:
        pass
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
    pack_numbers = set(str(value) for value in pack.get("numbers", []))
    script_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", script.text))
    if script_numbers and not any(
        number in " ".join(pack_numbers) for number in script_numbers
    ):
        warnings.append(
            "script contains numbers that were not observed in the research pack"
        )
    if '"' in script.text or "“" in script.text or "”" in script.text:
        warnings.append("direct quotation marks require explicit evidence review")
    return warnings
