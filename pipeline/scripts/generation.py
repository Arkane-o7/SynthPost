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
    targets = {
        section: max(35, round(total * weight)) for section, weight in weights.items()
    }
    delta = total - sum(targets.values())
    targets["key_developments"] += delta
    return targets


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
        lower_thirds=[headline[:80]],
        chyrons=[headline[:64]],
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
                    "required": ["section_type", "text", "claim_ids"],
                    "properties": {
                        "section_type": {"type": "string"},
                        "text": {"type": "string"},
                        "claim_ids": {"type": "array", "items": {"type": "string"}},
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
        lower_thirds=[str(raw.get("headline") or "SynthPost Briefing")[:80]],
        chyrons=[str(raw.get("headline") or "SynthPost Briefing")[:64]],
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
    return f"""
You are SynthPost Studio's local newsroom writer. Create a grounded section-based news script.
Use only the supplied research pack. Do not fabricate quotes, statistics, names, dates, or attribution.
Return only JSON matching this schema: {json.dumps(script_schema())}

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

Research pack JSON:
{json.dumps(pack, ensure_ascii=True)}
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
        lambda raw: enforce_target_duration(
            script_from_llm_json(story_id, raw, pack), target_duration_seconds
        ),
        max_retries=3,
    )
    generation_warnings = [
        f"llm_provider={selected_provider.name}",
        f"structured_attempts={len(attempts)}",
    ]
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
    script = split_manual_script(story_id, headline, text, category=category)
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
