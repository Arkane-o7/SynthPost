from __future__ import annotations

import json
import re
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

SCRIPT_PROMPT_VERSION = "synthpost.script.v5"
LONG_FORM_PROMPT_VERSION = "synthpost.long-form-section.v4"
HEADLINE_PROMPT_VERSION = "synthpost.headline-editor.v2"


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
) -> ScriptDocument:
    pack = repository.latest_research_pack(story_id)
    if not pack:
        raise ValueError(f"No research pack exists for story: {story_id}")
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
    main_prompt = generation_prompt(
        pack,
        target_duration_seconds=target_duration_seconds,
        primary_topic=candidate.editorial_fit.primary_topic,
        narration_mode=selected_mode,
    )
    reusable_audit = next(
        (
            audit
            for audit in repository.list_generation_audits(story_id, limit=50)
            if audit.stage == "script_draft"
            and audit.prompt_version == SCRIPT_PROMPT_VERSION
            and audit.status == "completed"
            and audit.prompt_text == main_prompt
            and isinstance(audit.response, dict)
        ),
        None,
    )
    if reusable_audit is not None:
        value = script_from_llm_json(story_id, reusable_audit.response or {}, pack)
        attempts = [
            {
                "attempt": 0,
                "ok": True,
                "prompt": main_prompt,
                "raw": reusable_audit.response,
                "provider": reusable_audit.provider,
                "model": reusable_audit.model,
                "elapsed_seconds": 0.0,
                "reused_checkpoint": True,
            }
        ]
        selected_provider = provider
        fallback_errors = []
    else:
        try:
            value, attempts, selected_provider, fallback_errors = _generate_with_provider(
                provider,
                main_prompt,
                script_schema(),
                lambda raw: script_from_llm_json(story_id, raw, pack),
                max_retries=2,
            )
        except StructuredGenerationError as exc:
            _save_generation_audit(
                repository,
                story_id=story_id,
                stage="script_draft",
                prompt_version=SCRIPT_PROMPT_VERSION,
                prompt=main_prompt,
                attempts=exc.attempts,
            )
            raise
    main_raw = attempts[-1].get("raw") if attempts else {}
    value.narration_mode = selected_mode
    if reusable_audit is None:
        _save_generation_audit(
            repository,
            story_id=story_id,
            stage="script_draft",
            prompt_version=SCRIPT_PROMPT_VERSION,
            prompt=main_prompt,
            attempts=attempts,
            normalization_events=_script_normalization_events(
                main_raw if isinstance(main_raw, dict) else {}, value
            ),
        )
    expansion_attempts = 0
    tolerance = duration_tolerance_seconds(target_duration_seconds)
    if (
        target_duration_seconds >= 240
        and value.estimated_duration_seconds < target_duration_seconds - tolerance
    ):
        reusable_expansions = {
            audit.stage: audit
            for audit in repository.list_generation_audits(story_id, limit=100)
            if audit.stage.startswith("long_form:")
            and audit.prompt_version == LONG_FORM_PROMPT_VERSION
            and audit.status == "completed"
            and isinstance(audit.response, dict)
        }
        value, expansion_attempts = expand_long_form_script(
            selected_provider,
            value,
            pack,
            target_duration_seconds=target_duration_seconds,
            narration_mode=selected_mode,
            audit_callback=lambda stage, prompt, stage_attempts, events: (
                _save_generation_audit(
                    repository,
                    story_id=story_id,
                    stage=stage,
                    prompt_version=LONG_FORM_PROMPT_VERSION,
                    prompt=prompt,
                    attempts=stage_attempts,
                    normalization_events=events,
                )
            ),
            reusable_audits=reusable_expansions,
        )
    value = enforce_target_duration(value, target_duration_seconds)
    headline_prompt, expected_beats = headline_editor_prompt(value, pack)
    try:
        headline_raw, headline_attempts = structured_generate(
            selected_provider,
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
        raise
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
    generation_warnings = [
        f"llm_provider={selected_provider.name}",
        f"structured_attempts={len(attempts)}",
        f"editorial_charter={CHARTER_VERSION}",
        f"script_prompt={SCRIPT_PROMPT_VERSION}",
        f"headline_prompt={HEADLINE_PROMPT_VERSION}",
        f"narration_mode={selected_mode.value}",
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
