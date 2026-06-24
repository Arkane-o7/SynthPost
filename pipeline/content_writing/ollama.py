from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

from .. import evidence
from ..provenance import artifact_record, record_story_artifact
from ..storage import read_manifest, write_manifest


SCRIPT_VERSION = "synthpost_script_v2"

DURATION_PROFILES: dict[str, dict[str, Any]] = {
    "short": {
        "min_seconds": 60,
        "max_seconds": 90,
        "default_seconds": 75,
        "section_ids": ["cold_open", "main_developments", "why_it_matters", "conclusion"],
    },
    "standard": {
        "min_seconds": 180,
        "max_seconds": 300,
        "default_seconds": 240,
        "section_ids": [
            "cold_open",
            "intro",
            "background_context",
            "main_developments",
            "why_it_matters",
            "stakes_consequences",
            "conclusion",
            "outro_next_story",
        ],
    },
    "longform": {
        "min_seconds": 300,
        "max_seconds": 900,
        "default_seconds": 600,
        "section_ids": [
            "cold_open",
            "intro",
            "background_context",
            "main_developments",
            "why_it_matters",
            "stakes_consequences",
            "opposing_views_uncertainty",
            "conclusion",
            "outro_next_story",
        ],
    },
}

SECTION_TITLES = {
    "cold_open": "Cold Open",
    "intro": "Intro",
    "background_context": "Background And Context",
    "main_developments": "Main Developments",
    "why_it_matters": "Why It Matters",
    "stakes_consequences": "Stakes And Consequences",
    "opposing_views_uncertainty": "Opposing Views Or Uncertainty",
    "conclusion": "Conclusion",
    "outro_next_story": "Outro And Next Story Transition",
}

SECTION_WEIGHTS = {
    "cold_open": 0.08,
    "intro": 0.08,
    "background_context": 0.15,
    "main_developments": 0.26,
    "why_it_matters": 0.15,
    "stakes_consequences": 0.12,
    "opposing_views_uncertainty": 0.07,
    "conclusion": 0.06,
    "outro_next_story": 0.03,
}


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def compact_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _duration_mode_from_env(default: str = "short") -> str:
    mode = os.environ.get("SYNTHPOST_SCRIPT_DURATION_MODE") or os.environ.get("SYNTHPOST_SCRIPT_MODE") or default
    mode = mode.strip().lower()
    return mode if mode in DURATION_PROFILES else default


def _clamp_seconds(value: float, *, minimum: float, maximum: float) -> int:
    return int(round(max(minimum, min(maximum, value))))


def writing_options_for(manifest: dict[str, Any]) -> dict[str, Any]:
    writing_config = manifest.get("content_writing") if isinstance(manifest.get("content_writing"), dict) else {}
    mode = str(
        os.environ.get("SYNTHPOST_SCRIPT_DURATION_MODE")
        or os.environ.get("SYNTHPOST_SCRIPT_MODE")
        or writing_config.get("duration_mode")
        or "short"
    ).strip().lower()
    if mode not in DURATION_PROFILES:
        mode = "short"
    profile = DURATION_PROFILES[mode]
    raw_target = os.environ.get("SYNTHPOST_SCRIPT_TARGET_SECONDS") or writing_config.get("target_duration_seconds")
    try:
        target = float(raw_target) if raw_target not in (None, "") else float(profile["default_seconds"])
    except (TypeError, ValueError):
        target = float(profile["default_seconds"])
    target_seconds = _clamp_seconds(
        target,
        minimum=float(profile["min_seconds"]),
        maximum=float(profile["max_seconds"]),
    )
    return {
        "duration_mode": mode,
        "target_duration_seconds": target_seconds,
        "min_duration_seconds": profile["min_seconds"],
        "max_duration_seconds": profile["max_seconds"],
        "required_section_ids": list(profile["section_ids"]),
    }


def _source_metadata_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    metadata = raw.get("source_metadata") if isinstance(raw.get("source_metadata"), dict) else {}
    fallback = {
        "source": raw.get("source_name"),
        "source_name": raw.get("source_name"),
        "source_url": raw.get("source_url"),
        "source_domain": raw.get("source_domain"),
        "source_provider": raw.get("source_provider"),
        "source_type": raw.get("source_type"),
        "source_category": raw.get("source_category"),
        "published_at": raw.get("published_at"),
    }
    return {
        key: metadata.get(key) or value
        for key, value in fallback.items()
        if metadata.get(key) or value
    }


def writing_input_for(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("raw", {}) if isinstance(manifest.get("raw"), dict) else {}
    handoff = raw.get("handoff") if isinstance(raw.get("handoff"), dict) else {}
    writing = handoff.get("writing") if isinstance(handoff.get("writing"), dict) else {}
    editorial = raw.get("editorial") if isinstance(raw.get("editorial"), dict) else {}
    selected = raw.get("selected_candidate") if isinstance(raw.get("selected_candidate"), dict) else {}
    source_metadata = writing.get("source_metadata") if isinstance(writing.get("source_metadata"), dict) else {}
    source_metadata = {**_source_metadata_from_raw(raw), **source_metadata}
    return {
        "candidate_id": writing.get("candidate_id") or selected.get("candidate_id") or editorial.get("candidate_id"),
        "headline": writing.get("headline") or raw.get("headline_source", ""),
        "category": writing.get("category") or raw.get("category", ""),
        "summary": writing.get("summary") or raw.get("summary", ""),
        "facts": _string_list(writing.get("facts")) or _string_list(raw.get("facts")),
        "claims": _dict_list(writing.get("claims")) or _dict_list(raw.get("claims")),
        "claim_ids": _string_list(writing.get("claim_ids")) or [
            str(claim.get("claim_id"))
            for claim in _dict_list(raw.get("claims"))
            if claim.get("claim_id")
        ],
        "entities": _string_list(writing.get("entities")) or _string_list(raw.get("entities") or raw.get("key_entities")),
        "sources": _dict_list(writing.get("sources")) or _dict_list(raw.get("sources")),
        "source_metadata": source_metadata,
        "why_it_matters": writing.get("why_it_matters") or editorial.get("why_it_matters", ""),
        "synthpost_angle": writing.get("synthpost_angle") or editorial.get("synthpost_angle") or editorial.get("possible_synthpost_angle", ""),
        "audience_curiosity_angle": writing.get("audience_curiosity_angle") or editorial.get("audience_curiosity_angle", ""),
        "explainability_notes": writing.get("explainability_notes") or editorial.get("explainability_notes", ""),
        "score_reasons": writing.get("score_reasons") if isinstance(writing.get("score_reasons"), dict) else editorial.get("score_reasons", {}),
        "scores": writing.get("scores") if isinstance(writing.get("scores"), dict) else editorial.get("scores", {}),
        "selection_reason": writing.get("selection_reason") or editorial.get("selection_reason", ""),
    }


def prompt_for(manifest: dict[str, Any]) -> str:
    writing_input = writing_input_for(manifest)
    options = writing_options_for(manifest)
    sources = writing_input["sources"]
    claims = writing_input["claims"]
    source_lines = "\n".join(
        f"- {source.get('source_id')}: {source.get('name')} ({source.get('url', 'no url')})"
        for source in sources
        if isinstance(source, dict)
    )
    claim_lines = "\n".join(
        f"- {claim.get('claim_id')}: {claim.get('text')}"
        for claim in claims
        if isinstance(claim, dict)
    )
    fact_lines = "\n".join(f"- {fact}" for fact in writing_input["facts"])
    entity_line = ", ".join(writing_input["entities"])
    score_reason_lines = "\n".join(
        f"- {key}: {value}"
        for key, value in (writing_input.get("score_reasons") or {}).items()
        if value
    )
    return (
        "Return exactly one valid compact JSON object for a grounded YouTube news script.\n"
        "Do not write markdown, comments, prose outside JSON, or duplicate JSON keys.\n"
        "Required keys exactly once: text, headline, category, claim_ids, source_ids, caveats, sections.\n"
        "Use only the supplied source summary and claim ledger. Do not fabricate claims.\n"
        "Every factual assertion in text must be supported by one of the supplied claim_ids.\n"
        "Do not infer consequences, causes, risks, impacts, or forecasts beyond the claim text.\n"
        "Do not invent numbers, dates, names, locations, causes, or forecasts not present in the source material.\n"
        "If the ledger is small, structure the analysis around what is known and what remains uncertain.\n"
        f"Duration mode: {options['duration_mode']}\n"
        f"Target duration seconds: {options['target_duration_seconds']}\n"
        f"Required section_ids in order: {', '.join(options['required_section_ids'])}\n"
        "Each section must include: section_id, title, narration, estimated_duration_seconds, claim_ids, source_notes.\n\n"
        f"Candidate ID: {writing_input.get('candidate_id') or ''}\n"
        f"Headline: {writing_input.get('headline', '')}\n"
        f"Category: {writing_input.get('category', '')}\n"
        f"Summary: {writing_input.get('summary', '')}\n"
        f"Entities: {entity_line}\n"
        f"Why it matters: {writing_input.get('why_it_matters') or ''}\n"
        f"SynthPost angle: {writing_input.get('synthpost_angle') or ''}\n"
        f"Audience curiosity angle: {writing_input.get('audience_curiosity_angle') or ''}\n"
        f"Explainability notes: {writing_input.get('explainability_notes') or ''}\n"
        f"Selection reason: {writing_input.get('selection_reason') or ''}\n"
        f"Facts:\n{fact_lines}\n"
        f"Sources:\n{source_lines}\n"
        f"Score reasons:\n{score_reason_lines}\n"
        f"Claims:\n{claim_lines}\n\n"
        "Output shape: "
        '{"text":"...","headline":"...","category":"...","duration_mode":"longform",'
        '"target_duration_seconds":600,"estimated_duration_seconds":600,'
        '"sections":[{"section_id":"cold_open","title":"Cold Open","narration":"...",'
        '"estimated_duration_seconds":45,"claim_ids":["claim_01"],"source_notes":["..."]}],'
        '"claim_ids":["claim_01"],"source_ids":["source_01"],"major_claims":[{"text":"...",'
        '"claim_ids":["claim_01"]}],"caveats":[]}'
    )


def call_ollama(prompt: str) -> dict[str, Any]:
    model = os.environ.get("SYNTHPOST_OLLAMA_MODEL", "gemma4:26b")
    timeout = float(os.environ.get("SYNTHPOST_OLLAMA_TIMEOUT", "120"))
    use_chat = os.environ.get("SYNTHPOST_OLLAMA_API", "chat").lower() == "chat"
    url = _ollama_url(use_chat=use_chat)
    if use_chat:
        payload_data: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Output only one valid compact JSON object. No duplicate keys. No markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
            "options": _ollama_options(),
        }
        if _bool_env("SYNTHPOST_OLLAMA_THINK", default=False) is False:
            payload_data["think"] = False
    else:
        payload_data = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": _ollama_options(),
        }
        if _bool_env("SYNTHPOST_OLLAMA_THINK", default=False) is False:
            payload_data["think"] = False
    payload = json.dumps(payload_data).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "Ollama content writing failed. Start Ollama or set "
            "SYNTHPOST_OLLAMA_URL/SYNTHPOST_OLLAMA_MODEL/SYNTHPOST_OLLAMA_TIMEOUT."
        ) from exc
    response_text = _ollama_response_text(data, use_chat=use_chat)
    return _parse_json_response(response_text)


def _ollama_url(*, use_chat: bool) -> str:
    configured = os.environ.get("SYNTHPOST_OLLAMA_URL")
    if configured:
        if use_chat and configured.endswith("/api/generate"):
            return configured.removesuffix("/api/generate") + "/api/chat"
        if not use_chat and configured.endswith("/api/chat"):
            return configured.removesuffix("/api/chat") + "/api/generate"
        return configured
    return "http://localhost:11434/api/chat" if use_chat else "http://localhost:11434/api/generate"


def _ollama_response_text(data: dict[str, Any], *, use_chat: bool) -> str:
    if use_chat:
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        content = str(message.get("content") or "")
        if not content and message.get("thinking"):
            raise RuntimeError(
                "Ollama returned no message content because the model spent its output budget on thinking. "
                "Keep SYNTHPOST_OLLAMA_THINK unset/false or raise SYNTHPOST_OLLAMA_NUM_PREDICT."
            )
        return content
    return str(data.get("response", "{}"))


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _ollama_options() -> dict[str, Any]:
    mode = _duration_mode_from_env()
    default_predict = {"short": 600, "standard": 1800, "longform": 5000}[mode]
    default_ctx = {"short": 4096, "standard": 8192, "longform": 12288}[mode]
    return {
        "temperature": float(os.environ.get("SYNTHPOST_OLLAMA_TEMPERATURE", "0")),
        "top_p": float(os.environ.get("SYNTHPOST_OLLAMA_TOP_P", "0.7")),
        "repeat_penalty": float(os.environ.get("SYNTHPOST_OLLAMA_REPEAT_PENALTY", "1.25")),
        "num_predict": int(os.environ.get("SYNTHPOST_OLLAMA_NUM_PREDICT", str(default_predict))),
        "num_ctx": int(os.environ.get("SYNTHPOST_OLLAMA_NUM_CTX", str(default_ctx))),
    }


def _parse_json_response(response_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(response_text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise _non_json_response_error(response_text) from exc
        else:
            raise _non_json_response_error(response_text)
    if not isinstance(parsed, dict):
        raise RuntimeError("Ollama returned JSON, but the script stage expected a JSON object.")
    return parsed


def _non_json_response_error(response_text: str) -> RuntimeError:
    compact = " ".join(response_text.split())
    excerpt = compact[:500]
    return RuntimeError(f"Ollama returned non-JSON content for the script stage. Response excerpt: {excerpt}")


def deterministic_script(manifest: dict[str, Any]) -> dict[str, Any]:
    writing_input = writing_input_for(manifest)
    options = writing_options_for(manifest)
    raw = manifest.get("raw", {}) if isinstance(manifest.get("raw"), dict) else {}
    headline = str(writing_input.get("headline") or raw.get("headline_source") or "SYNTHPOST BRIEFING").upper()
    category = str(writing_input.get("category") or raw.get("category") or "NEWS").upper()
    claims = _dict_list(writing_input.get("claims"))
    if not claims:
        claims = [
            {"claim_id": f"claim_{index:02d}", "text": fact, "source_ids": ["source_01"]}
            for index, fact in enumerate(writing_input.get("facts", []), start=1)
        ]
    sections = build_script_sections(writing_input, options, claims=claims)
    text = "\n\n".join(section["narration"] for section in sections if section.get("narration")).strip()
    claim_ids = _known_claim_ids(claims)
    source_ids = sorted(
        {
            str(source_id)
            for claim in claims
            for source_id in (claim.get("source_ids") or [])
            if source_id
        }
    )
    estimated_duration = sum(float(section.get("estimated_duration_seconds") or 0) for section in sections)
    return {
        "script_version": SCRIPT_VERSION,
        "text": text,
        "headline": headline,
        "title": headline,
        "category": category,
        "duration_mode": options["duration_mode"],
        "target_duration_seconds": options["target_duration_seconds"],
        "estimated_duration_seconds": round(estimated_duration, 2),
        "sections": sections,
        "claim_ids": claim_ids,
        "source_ids": source_ids,
        "major_claims": [{"text": str(claim.get("text", "")), "claim_ids": [str(claim.get("claim_id"))]} for claim in claims if claim.get("claim_id")],
        "caveats": ["Details may change as more verified reporting becomes available."],
    }


def _known_claim_ids(claims: list[dict[str, Any]]) -> list[str]:
    return [str(claim.get("claim_id")) for claim in claims if claim.get("claim_id")]


def _claim_texts(claims: list[dict[str, Any]]) -> list[str]:
    return [compact_text(claim.get("text")) for claim in claims if compact_text(claim.get("text"))]


def _claim_ids_for_section(section_id: str, claims: list[dict[str, Any]]) -> list[str]:
    claim_ids = _known_claim_ids(claims)
    if section_id in {"cold_open", "intro"}:
        return claim_ids[:1]
    if section_id in {"background_context", "main_developments"}:
        return claim_ids[: max(1, min(3, len(claim_ids)))]
    if section_id in {"why_it_matters", "stakes_consequences", "conclusion"}:
        return claim_ids[:]
    return []


def _source_notes_for_section(section_id: str, claim_ids: list[str], claims: list[dict[str, Any]]) -> list[str]:
    if not claim_ids:
        return ["No additional sourced claim supplied for this section; keep narration limited to uncertainty and transitions."]
    claim_by_id = {str(claim.get("claim_id")): claim for claim in claims}
    notes: list[str] = []
    for claim_id in claim_ids:
        claim = claim_by_id.get(claim_id)
        if claim:
            notes.append(f"{claim_id}: {compact_text(claim.get('text'))}")
    return notes


def _section_durations(section_ids: list[str], target_seconds: int) -> dict[str, int]:
    total_weight = sum(SECTION_WEIGHTS.get(section_id, 0.1) for section_id in section_ids) or 1.0
    durations = {
        section_id: max(8, int(round(target_seconds * SECTION_WEIGHTS.get(section_id, 0.1) / total_weight)))
        for section_id in section_ids
    }
    delta = target_seconds - sum(durations.values())
    if section_ids:
        durations[section_ids[-1]] += delta
    return durations


def build_script_sections(
    writing_input: dict[str, Any],
    options: dict[str, Any],
    *,
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    section_ids = list(options["required_section_ids"])
    durations = _section_durations(section_ids, int(options["target_duration_seconds"]))
    headline = compact_text(writing_input.get("headline")) or "this story"
    summary = compact_text(writing_input.get("summary"))
    facts = _claim_texts(claims) or _string_list(writing_input.get("facts"))
    first_fact = facts[0] if facts else summary
    fact_sentence = " ".join(f"{fact.rstrip('.')}." for fact in facts[:3] if fact)
    entities = ", ".join(_string_list(writing_input.get("entities"))[:5])
    angle = compact_text(writing_input.get("synthpost_angle"))
    why = compact_text(writing_input.get("why_it_matters"))
    curiosity = compact_text(writing_input.get("audience_curiosity_angle"))
    explainability = compact_text(writing_input.get("explainability_notes"))
    section_text = {
        "cold_open": f"Here is the signal: {headline}. {first_fact}",
        "intro": f"This is SynthPost. We are tracking {headline}. The confirmed source material says: {first_fact}",
        "background_context": f"The context starts with the source summary: {summary or first_fact} Key entities in this story include {entities}." if entities else f"The context starts with the source summary: {summary or first_fact}",
        "main_developments": f"The main verified developments are these. {fact_sentence}",
        "why_it_matters": f"Why it matters: {why or angle or first_fact}",
        "stakes_consequences": f"The stakes, based on the selected editorial angle, are this: {angle or curiosity or first_fact}",
        "opposing_views_uncertainty": (
            "The supplied source material does not fully resolve opposing views or every uncertainty. "
            "That means the responsible read is to separate confirmed facts from what still needs verification."
        ),
        "conclusion": f"The bottom line: {fact_sentence or first_fact} We will keep this grounded in the verified source ledger.",
        "outro_next_story": "That is the SynthPost read for now. Next, we will keep following the signals that change the wider story.",
    }
    if explainability and "opposing_views_uncertainty" in section_text:
        section_text["opposing_views_uncertainty"] += f" Explainability note: {explainability}"
    sections: list[dict[str, Any]] = []
    for section_id in section_ids:
        claim_ids = _claim_ids_for_section(section_id, claims)
        sections.append(
            {
                "section_id": section_id,
                "title": SECTION_TITLES.get(section_id, section_id.replace("_", " ").title()),
                "narration": compact_text(section_text.get(section_id, first_fact)),
                "estimated_duration_seconds": durations[section_id],
                "claim_ids": claim_ids,
                "source_notes": _source_notes_for_section(section_id, claim_ids, claims),
            }
        )
    return sections


def _sections_from_script(script: dict[str, Any]) -> list[dict[str, Any]]:
    sections = script.get("sections")
    if not isinstance(sections, list):
        return []
    return [section for section in sections if isinstance(section, dict)]


def normalize_script_contract(script: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    options = writing_options_for(manifest)
    raw = manifest.get("raw", {}) if isinstance(manifest.get("raw"), dict) else {}
    writing_input = writing_input_for(manifest)
    normalized = dict(script)
    normalized.setdefault("script_version", SCRIPT_VERSION)
    normalized.setdefault("duration_mode", options["duration_mode"])
    normalized.setdefault("target_duration_seconds", options["target_duration_seconds"])
    normalized.setdefault("headline", normalized.get("title") or writing_input.get("headline") or raw.get("headline_source") or "SYNTHPOST BRIEFING")
    normalized.setdefault("title", normalized.get("headline"))
    normalized.setdefault("category", writing_input.get("category") or raw.get("category") or "NEWS")
    claims = _dict_list(writing_input.get("claims")) or _dict_list(raw.get("claims"))
    if not normalized.get("claim_ids"):
        normalized["claim_ids"] = _known_claim_ids(claims)
    if not normalized.get("source_ids"):
        normalized["source_ids"] = sorted(
            {
                str(source_id)
                for claim in claims
                for source_id in (claim.get("source_ids") or [])
                if source_id
            }
        )
    if not _sections_from_script(normalized):
        normalized["sections"] = build_script_sections(writing_input, options, claims=claims)
    else:
        normalized["sections"] = normalize_sections(normalized["sections"], options, claims=claims)
    if not compact_text(normalized.get("text")):
        normalized["text"] = "\n\n".join(section.get("narration", "") for section in _sections_from_script(normalized))
    if not normalized.get("major_claims"):
        normalized["major_claims"] = [
            {"text": compact_text(claim.get("text")), "claim_ids": [str(claim.get("claim_id"))]}
            for claim in claims
            if claim.get("claim_id") and compact_text(claim.get("text"))
        ]
    normalized.setdefault("caveats", [])
    normalized["estimated_duration_seconds"] = round(
        sum(float(section.get("estimated_duration_seconds") or 0) for section in _sections_from_script(normalized)),
        2,
    )
    normalized["word_count"] = len(compact_text(normalized.get("text")).split())
    return normalized


def normalize_sections(
    sections: list[dict[str, Any]],
    options: dict[str, Any],
    *,
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    required = list(options["required_section_ids"])
    by_id = {compact_text(section.get("section_id")): dict(section) for section in sections if compact_text(section.get("section_id"))}
    fallback_sections = {
        section["section_id"]: section
        for section in build_script_sections(
            {"headline": "", "summary": "", "facts": _claim_texts(claims)},
            options,
            claims=claims,
        )
    }
    output: list[dict[str, Any]] = []
    for section_id in required:
        section = by_id.get(section_id, fallback_sections[section_id])
        claim_ids = _string_list(section.get("claim_ids"))
        section["section_id"] = section_id
        section["title"] = compact_text(section.get("title")) or SECTION_TITLES.get(section_id, section_id)
        section["narration"] = compact_text(section.get("narration") or section.get("text"))
        try:
            section["estimated_duration_seconds"] = int(round(float(section.get("estimated_duration_seconds"))))
        except (TypeError, ValueError):
            section["estimated_duration_seconds"] = fallback_sections[section_id]["estimated_duration_seconds"]
        section["claim_ids"] = claim_ids
        source_notes = section.get("source_notes")
        section["source_notes"] = _string_list(source_notes) or _source_notes_for_section(section_id, claim_ids, claims)
        output.append(section)
    return output


def groundedness_review(script: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    claims = raw.get("claims") if isinstance(raw.get("claims"), list) else []
    known_claim_ids = {compact_text(claim.get("claim_id")) for claim in claims if isinstance(claim, dict)}
    script_claim_ids = set(evidence.normalize_script_claim_ids(script))
    unknown_claim_ids = sorted(claim_id for claim_id in script_claim_ids if claim_id not in known_claim_ids)
    unsupported_major_claims: list[str] = []
    for index, claim in enumerate(_dict_list(script.get("major_claims")), start=1):
        supporting_ids = _string_list(claim.get("claim_ids") or claim.get("supporting_claim_ids"))
        if not supporting_ids or any(claim_id not in known_claim_ids for claim_id in supporting_ids):
            unsupported_major_claims.append(compact_text(claim.get("text")) or f"major_claim_{index:02d}")
    section_warnings: list[str] = []
    for section in _sections_from_script(script):
        section_id = compact_text(section.get("section_id"))
        narration = compact_text(section.get("narration"))
        claim_ids = _string_list(section.get("claim_ids"))
        if section_id not in {"cold_open", "intro", "opposing_views_uncertainty", "outro_next_story"} and narration and not claim_ids:
            section_warnings.append(f"{section_id} has narration but no claim_ids")
        if any(claim_id not in known_claim_ids for claim_id in claim_ids):
            section_warnings.append(f"{section_id} cites unknown claim_id")
    evidence_text = _evidence_text(raw)
    script_text = _script_fact_text(script)
    unsupported_markers = [
        marker
        for marker in _factual_markers(script_text)
        if marker.lower() not in evidence_text
    ]
    warnings = [
        *[f"unknown claim_id: {claim_id}" for claim_id in unknown_claim_ids],
        *[f"unsupported major claim: {claim}" for claim in unsupported_major_claims],
        *section_warnings,
        *[f"unsupported factual marker: {marker}" for marker in unsupported_markers],
    ]
    return {
        "status": "pass" if not warnings else "needs_review",
        "unknown_claim_ids": unknown_claim_ids,
        "unsupported_major_claims": unsupported_major_claims,
        "unsupported_factual_markers": unsupported_markers,
        "warnings": warnings,
    }


def _validation_options_from_script(script: dict[str, Any]) -> dict[str, Any]:
    mode = compact_text(script.get("duration_mode")).lower()
    if mode not in DURATION_PROFILES:
        mode = "short"
    profile = DURATION_PROFILES[mode]
    target = script.get("target_duration_seconds")
    try:
        target_seconds = float(target) if target not in (None, "") else float(profile["default_seconds"])
    except (TypeError, ValueError):
        target_seconds = float(profile["default_seconds"])
    return {
        "duration_mode": mode,
        "target_duration_seconds": _clamp_seconds(
            target_seconds,
            minimum=float(profile["min_seconds"]),
            maximum=float(profile["max_seconds"]),
        ),
        "min_duration_seconds": profile["min_seconds"],
        "max_duration_seconds": profile["max_seconds"],
        "required_section_ids": list(profile["section_ids"]),
    }


def validate_script_contract(script: dict[str, Any], raw: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or _validation_options_from_script(script)
    warnings: list[str] = []
    for key in ("text", "headline", "category", "claim_ids", "sections"):
        if key not in script or script.get(key) in (None, "", []):
            warnings.append(f"script missing {key}")
    sections = _sections_from_script(script)
    section_ids = [compact_text(section.get("section_id")) for section in sections]
    required_ids = list(options.get("required_section_ids") or [])
    for section_id in required_ids:
        if section_id not in section_ids:
            warnings.append(f"missing required section: {section_id}")
    for section in sections:
        for key in ("section_id", "title", "narration", "estimated_duration_seconds", "source_notes"):
            if section.get(key) in (None, "", []):
                warnings.append(f"section {section.get('section_id') or 'unknown'} missing {key}")
    try:
        target_seconds = float(script.get("target_duration_seconds"))
        estimated_seconds = float(script.get("estimated_duration_seconds"))
    except (TypeError, ValueError):
        warnings.append("script duration metadata is invalid")
        target_seconds = estimated_seconds = 0.0
    if target_seconds:
        tolerance = max(5.0, target_seconds * 0.08)
        if abs(estimated_seconds - target_seconds) > tolerance:
            warnings.append("estimated duration does not match target duration structurally")
    if options:
        minimum = float(options.get("min_duration_seconds", 0))
        maximum = float(options.get("max_duration_seconds", 10_000))
        if target_seconds and not (minimum <= target_seconds <= maximum):
            warnings.append("target duration is outside selected duration mode")
    grounded = groundedness_review(script, raw)
    warnings.extend(grounded["warnings"])
    return {
        "status": "pass" if not warnings else "needs_review",
        "script_version": script.get("script_version"),
        "duration_mode": script.get("duration_mode"),
        "target_duration_seconds": script.get("target_duration_seconds"),
        "estimated_duration_seconds": script.get("estimated_duration_seconds"),
        "section_ids": section_ids,
        "required_section_ids": required_ids,
        "warnings": warnings,
        "groundedness": grounded,
    }


def _evidence_text(raw: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("headline_source", "summary", "source_name", "category", "published_at"):
        values.append(compact_text(raw.get(key)))
    for field in ("facts", "entities", "key_entities"):
        values.extend(_string_list(raw.get(field)))
    for claim in _dict_list(raw.get("claims")):
        values.append(compact_text(claim.get("text")))
        for evidence_item in _dict_list(claim.get("evidence")):
            values.append(compact_text(evidence_item.get("quote")))
    for container_name in ("selected_candidate", "editorial", "source_metadata"):
        container = raw.get(container_name)
        if isinstance(container, dict):
            values.extend(_flatten_strings(container))
    return " ".join(values).lower()


def _flatten_strings(value: object) -> list[str]:
    if isinstance(value, dict):
        output: list[str] = []
        for item in value.values():
            output.extend(_flatten_strings(item))
        return output
    if isinstance(value, list):
        output = []
        for item in value:
            output.extend(_flatten_strings(item))
        return output
    text = compact_text(value)
    return [text] if text else []


def _script_fact_text(script: dict[str, Any]) -> str:
    values = [compact_text(script.get("text"))]
    for section in _sections_from_script(script):
        values.append(compact_text(section.get("narration")))
    for claim in _dict_list(script.get("major_claims")):
        values.append(compact_text(claim.get("text")))
    return " ".join(values)


def _factual_markers(text: str) -> list[str]:
    markers = re.findall(
        r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?\s?(?:%|percent|million|billion|trillion|days?|weeks?|months?|years?)\b",
        text,
        flags=re.IGNORECASE,
    )
    seen: set[str] = set()
    output: list[str] = []
    for marker in markers:
        key = marker.lower()
        if key not in seen:
            seen.add(key)
            output.append(marker)
    return output


def run(story_json_path: str | Path, *, force: bool = False) -> dict[str, Any]:
    manifest = evidence.normalize_manifest(read_manifest(story_json_path))
    provider = os.environ.get("SYNTHPOST_LLM_PROVIDER", "mock").lower()
    script = manifest.get("script")
    if isinstance(script, dict) and script.get("text") and not force:
        if "SYNTHPOST_LLM_PROVIDER" in os.environ:
            for key, value in _provider_metadata(provider).items():
                script.setdefault(key, value)
        script = normalize_script_contract(script, manifest)
        contract_review = validate_script_contract(script, manifest["raw"], writing_options_for(manifest))
        if contract_review["status"] != "pass":
            raise ValueError(f"Script failed content contract review: {', '.join(contract_review['warnings'])}")
        script = evidence.attach_script_evidence(script, manifest["raw"])
        script["contract_review"] = contract_review
        script["groundedness_review"] = contract_review["groundedness"]
        manifest["script"] = script
        manifest["editorial_review"] = evidence.validate_script(script, manifest["raw"])
        write_manifest(story_json_path, manifest)
        record_story_artifact(
            story_json_path,
            "story_manifest_script",
            artifact_record(
                path=story_json_path,
                stage="content_writing",
                input_paths=[story_json_path],
                provider=script.get("llm_provider"),
                model=script.get("llm_model"),
                fresh=False,
                reused=True,
                test_mode=bool(manifest.get("test_mode") or manifest.get("runtime", {}).get("test_mode")),
                render_profile=manifest.get("render_profile") or manifest.get("runtime", {}).get("render_profile") or "production",
            ),
        )
        print("[writing] Reusing script from manifest.")
        return script

    if provider == "ollama":
        script = call_ollama(prompt_for(manifest))
    else:
        script = deterministic_script(manifest)
    script = {**script, **_provider_metadata(provider)}
    script = normalize_script_contract(script, manifest)

    required = {"text", "headline", "category", "claim_ids", "sections"}
    missing = required - set(script)
    if missing:
        raise ValueError(f"Script provider result missing key(s): {', '.join(sorted(missing))}")
    contract_review = validate_script_contract(script, manifest["raw"], writing_options_for(manifest))
    if contract_review["status"] != "pass":
        raise ValueError(f"Script failed content contract review: {', '.join(contract_review['warnings'])}")
    review = evidence.validate_script(script, manifest["raw"])
    if review["status"] != "pass":
        raise ValueError(f"Script failed evidence review: {', '.join(review['warnings'])}")
    script = evidence.attach_script_evidence(script, manifest["raw"])
    script["contract_review"] = contract_review
    script["groundedness_review"] = contract_review["groundedness"]
    manifest["script"] = script
    manifest["editorial_review"] = review
    write_manifest(story_json_path, manifest)
    record_story_artifact(
        story_json_path,
        "story_manifest_script",
        artifact_record(
            path=story_json_path,
            stage="content_writing",
            input_paths=[story_json_path],
            provider=script.get("llm_provider"),
            model=script.get("llm_model"),
            fresh=True,
            reused=False,
            test_mode=bool(manifest.get("test_mode") or manifest.get("runtime", {}).get("test_mode")),
            render_profile=manifest.get("render_profile") or manifest.get("runtime", {}).get("render_profile") or "production",
        ),
    )
    print("[writing] Wrote script section.")
    return script


def _provider_metadata(provider: str) -> dict[str, str]:
    if provider == "ollama":
        return {
            "llm_provider": "ollama",
            "llm_model": os.environ.get("SYNTHPOST_OLLAMA_MODEL", "gemma4:26b"),
            "llm_api": os.environ.get("SYNTHPOST_OLLAMA_API", "chat").lower(),
        }
    return {
        "llm_provider": "mock",
        "llm_model": "deterministic_script",
        "llm_api": "local",
    }
