from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ..content_writing import ollama as writing_contract
from ..storage import read_manifest, write_manifest


SCREEN_FIELDS = (
    "key_points",
    "lower_thirds",
    "chyrons",
    "on_screen_bullets",
    "quote_cards",
    "data_callouts",
)

CHYRON_TYPES_BY_SECTION = {
    "cold_open": "hook",
    "intro": "context",
    "background_context": "context",
    "main_developments": "key_fact",
    "why_it_matters": "explainer",
    "stakes_consequences": "risk_stakes",
    "opposing_views_uncertainty": "uncertainty_caveat",
    "conclusion": "final_takeaway",
    "outro_next_story": "final_takeaway",
}

FIELD_LIMITS = {
    "lower_thirds": {"max_words": 9, "max_chars": 62},
    "chyrons": {"max_words": 9, "max_chars": 64},
    "key_points": {"max_words": 16, "max_chars": 98},
    "on_screen_bullets": {"max_words": 14, "max_chars": 88},
    "quote_cards": {"max_words": 18, "max_chars": 120},
    "data_callouts": {"max_words": 10, "max_chars": 72},
}

CLICKBAIT_PATTERNS = (
    "you won't believe",
    "shocking",
    "insane",
    "secret they don't want",
    "this changes everything",
    "mind-blowing",
)


def compact_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [compact_text(item) for item in value if compact_text(item)]


def _words(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'%-]*", value)


def short_line(text: str, *, max_words: int = 16, max_chars: int = 98, uppercase: bool = False) -> str:
    cleaned = compact_text(text).strip("\"'").rstrip(".")
    words = _words(cleaned)
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words])
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rsplit(" ", 1)[0]
    return cleaned.upper() if uppercase else cleaned


def _claims_by_id(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        compact_text(claim.get("claim_id")): claim
        for claim in _dict_list(raw.get("claims"))
        if compact_text(claim.get("claim_id"))
    }


def _claim_texts(
    section: dict[str, Any],
    claims: dict[str, dict[str, Any]],
    fallback_claim_ids: list[str] | None = None,
) -> list[str]:
    texts: list[str] = []
    section_claim_ids = _string_list(section.get("claim_ids")) or list(fallback_claim_ids or [])
    for claim_id in section_claim_ids:
        claim = claims.get(claim_id)
        if claim and compact_text(claim.get("text")):
            texts.append(compact_text(claim.get("text")))
    if not texts:
        for note in _string_list(section.get("source_notes")):
            text = note.split(":", 1)[1] if ":" in note else note
            if compact_text(text):
                texts.append(compact_text(text))
    if not texts and compact_text(section.get("narration")):
        texts.append(compact_text(section.get("narration")))
    return _dedupe_strings(texts)


def _claim_ids_for_section(section: dict[str, Any], claims: dict[str, dict[str, Any]]) -> list[str]:
    claim_ids = [claim_id for claim_id in _string_list(section.get("claim_ids")) if claim_id in claims]
    if claim_ids:
        return claim_ids
    for claim_id, claim in claims.items():
        claim_text = compact_text(claim.get("text"))
        if claim_text and claim_text.lower() in compact_text(section.get("narration")).lower():
            claim_ids.append(claim_id)
    if claim_ids:
        return claim_ids[:3]
    return list(claims.keys())[:1]


def _section_schedule(sections: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    schedule: dict[str, tuple[float, float]] = {}
    cursor = 0.0
    for section in sections:
        section_id = compact_text(section.get("section_id")) or f"section_{len(schedule) + 1:02d}"
        try:
            duration = max(4.0, float(section.get("estimated_duration_seconds") or 12.0))
        except (TypeError, ValueError):
            duration = 12.0
        schedule[section_id] = (round(cursor, 2), round(cursor + duration, 2))
        cursor += duration
    return schedule


def _data_markers(text: str) -> list[str]:
    markers = re.findall(
        r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?\s?(?:%|percent|million|billion|trillion|days?|weeks?|months?|years?)\b",
        text,
        flags=re.IGNORECASE,
    )
    return _dedupe_strings(markers)


def _primary_quote(claim_ids: list[str], claims: dict[str, dict[str, Any]]) -> str:
    for claim_id in claim_ids:
        claim = claims.get(claim_id, {})
        for evidence_item in _dict_list(claim.get("evidence")):
            quote = compact_text(evidence_item.get("quote"))
            if quote:
                return quote
    return ""


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = compact_text(value)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _build_item(
    *,
    text: str,
    field: str,
    section_id: str,
    claim_ids: list[str],
    start: float,
    end: float,
    item_type: str,
    source_notes: list[str],
) -> dict[str, Any]:
    limits = FIELD_LIMITS[field]
    return {
        "text": short_line(
            text,
            max_words=int(limits["max_words"]),
            max_chars=int(limits["max_chars"]),
            uppercase=field in {"lower_thirds", "chyrons"},
        ),
        "type": item_type,
        "section_id": section_id,
        "claim_ids": claim_ids,
        "source_notes": source_notes,
        "start": round(start, 2),
        "end": round(max(start + 2.0, end), 2),
    }


def _item_source_notes(claim_ids: list[str], claims: dict[str, dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for claim_id in claim_ids:
        claim = claims.get(claim_id)
        if claim:
            notes.append(f"{claim_id}: {compact_text(claim.get('text'))}")
    return notes


def _deterministic_section_items(
    section: dict[str, Any],
    *,
    claims: dict[str, dict[str, Any]],
    start: float,
    end: float,
) -> dict[str, Any]:
    section_id = compact_text(section.get("section_id")) or "section"
    item_type = CHYRON_TYPES_BY_SECTION.get(section_id, "key_fact")
    claim_ids = _claim_ids_for_section(section, claims)
    source_notes = _item_source_notes(claim_ids, claims)
    texts = _claim_texts(section, claims, fallback_claim_ids=claim_ids)
    texts = _prioritized_texts_for_section(section_id, texts)
    primary = texts[0] if texts else compact_text(section.get("narration"))
    secondary = texts[1] if len(texts) > 1 else primary
    midpoint = start + max(2.0, (end - start) * 0.42)
    later = start + max(3.5, (end - start) * 0.68)
    lower = _build_item(
        text=primary,
        field="lower_thirds",
        section_id=section_id,
        claim_ids=claim_ids,
        start=start,
        end=min(end, start + 6.0),
        item_type=item_type,
        source_notes=source_notes,
    )
    key_point = _build_item(
        text=primary,
        field="key_points",
        section_id=section_id,
        claim_ids=claim_ids,
        start=midpoint,
        end=min(end, midpoint + 6.0),
        item_type=item_type,
        source_notes=source_notes,
    )
    bullet = _build_item(
        text=secondary,
        field="on_screen_bullets",
        section_id=section_id,
        claim_ids=claim_ids,
        start=later,
        end=min(end, later + 6.0),
        item_type=item_type,
        source_notes=source_notes,
    )
    chyron = {**lower, "text": lower["text"], "start": start, "end": min(end, start + 8.0)}
    result: dict[str, Any] = {
        "section_id": section_id,
        "key_points": [key_point],
        "lower_thirds": [lower],
        "chyrons": [chyron],
        "on_screen_bullets": [bullet],
        "quote_cards": [],
        "data_callouts": [],
    }
    quote = _primary_quote(claim_ids, claims)
    if quote and section_id in {"main_developments", "opposing_views_uncertainty", "why_it_matters"}:
        result["quote_cards"].append(
            _build_item(
                text=quote,
                field="quote_cards",
                section_id=section_id,
                claim_ids=claim_ids,
                start=min(end, start + 2.0),
                end=min(end, start + 9.0),
                item_type=item_type,
                source_notes=source_notes,
            )
        )
    markers = _data_markers(primary)
    if markers:
        result["data_callouts"].append(
            _build_item(
                text=f"{markers[0]}: {primary}",
                field="data_callouts",
                section_id=section_id,
                claim_ids=claim_ids,
                start=min(end, start + 1.5),
                end=min(end, start + 7.5),
                item_type="key_fact",
                source_notes=source_notes,
            )
        )
    return result


def _prioritized_texts_for_section(section_id: str, texts: list[str]) -> list[str]:
    if len(texts) < 2:
        return texts
    priority = {
        "cold_open": [0, 1, 2],
        "intro": [1, 0, 2],
        "background_context": [2, 0, 1],
        "main_developments": [0, 1, 2],
        "why_it_matters": [1, 2, 0],
        "stakes_consequences": [2, 1, 0],
        "opposing_views_uncertainty": [2, 0, 1],
        "conclusion": [0, 2, 1],
        "outro_next_story": [1, 0, 2],
    }.get(section_id, [0, 1, 2])
    ordered: list[str] = []
    for index in priority:
        if index < len(texts):
            ordered.append(texts[index])
    ordered.extend(text for index, text in enumerate(texts) if index not in priority)
    return _dedupe_strings(ordered)


def _fallback_sections(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    if _dict_list(script.get("sections")):
        return _dict_list(script.get("sections"))
    facts = _string_list(raw.get("facts"))
    claim_ids = _string_list(script.get("claim_ids"))
    text = facts[0] if facts else compact_text(script.get("text") or raw.get("summary") or raw.get("headline_source"))
    return [
        {
            "section_id": "main_developments",
            "title": "Main Developments",
            "narration": text or "Story details are being verified.",
            "estimated_duration_seconds": 30,
            "claim_ids": claim_ids,
            "source_notes": [text] if text else [],
        }
    ]


def _deterministic_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    sections = _fallback_sections(manifest)
    claims = _claims_by_id(raw)
    schedule = _section_schedule(sections)
    section_outputs: list[dict[str, Any]] = []
    for section in sections:
        section_id = compact_text(section.get("section_id")) or "section"
        start, end = schedule.get(section_id, (0.0, 30.0))
        section_outputs.append(_deterministic_section_items(section, claims=claims, start=start, end=end))
    return {
        "provider": "mock",
        "model": "deterministic_chyrons",
        "sections": section_outputs,
    }


def prompt_for(manifest: dict[str, Any]) -> str:
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
    sections = _fallback_sections(manifest)
    claims = _dict_list(raw.get("claims"))
    claim_lines = "\n".join(f"- {claim.get('claim_id')}: {claim.get('text')}" for claim in claims)
    section_lines = "\n".join(
        (
            f"- {section.get('section_id')} | claim_ids={_string_list(section.get('claim_ids'))} | "
            f"duration={section.get('estimated_duration_seconds')} | {compact_text(section.get('narration'))}"
        )
        for section in sections
    )
    return (
        "Return exactly one compact JSON object for SynthPost on-screen news text.\n"
        "Do not write markdown or prose outside JSON.\n"
        "Generate screen text per script section, not from a flattened transcript.\n"
        "Use only the supplied claims, section claim_ids, raw facts, source summary, and selected candidate metadata.\n"
        "Do not invent names, dates, numbers, causes, forecasts, or consequences.\n"
        "Keep lower_thirds and chyrons to 4-9 words. Keep key_points to 8-16 words. No clickbait.\n"
        "Allowed chyron types: hook, context, key_fact, explainer, consequence, risk_stakes, uncertainty_caveat, final_takeaway.\n"
        "Each generated item must include: text, type, section_id, claim_ids, source_notes, start, end.\n"
        "Optional fields per section: key_points, lower_thirds, chyrons, on_screen_bullets, quote_cards, data_callouts.\n\n"
        f"Headline: {script.get('headline') or raw.get('headline_source')}\n"
        f"Category: {script.get('category') or raw.get('category')}\n"
        f"Summary: {raw.get('summary')}\n"
        f"Facts: {_string_list(raw.get('facts'))}\n"
        f"Selected candidate: {raw.get('selected_candidate') if isinstance(raw.get('selected_candidate'), dict) else {}}\n"
        f"Claims:\n{claim_lines}\n"
        f"Sections:\n{section_lines}\n\n"
        "Output shape: "
        '{"sections":[{"section_id":"cold_open","key_points":[{"text":"...","type":"hook",'
        '"section_id":"cold_open","claim_ids":["claim_01"],"source_notes":["claim_01: ..."],'
        '"start":0,"end":6}],"lower_thirds":[],"chyrons":[],"on_screen_bullets":[],'
        '"quote_cards":[],"data_callouts":[]}]}'
    )


def _provider_name() -> str:
    return os.environ.get("SYNTHPOST_NEWS_POINTS_PROVIDER") or os.environ.get("SYNTHPOST_LLM_PROVIDER", "mock")


def _provider_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    provider = _provider_name().lower()
    if provider == "ollama":
        result = writing_contract.call_ollama(prompt_for(manifest))
        result["provider"] = "ollama"
        result["model"] = os.environ.get("SYNTHPOST_OLLAMA_MODEL", "gemma4:26b")
        return result
    return _deterministic_contract(manifest)


def _normalize_item(
    item: object,
    *,
    field: str,
    section_id: str,
    fallback_type: str,
    fallback_claim_ids: list[str],
    fallback_source_notes: list[str],
    start: float,
    end: float,
) -> dict[str, Any] | None:
    if isinstance(item, str):
        raw_item: dict[str, Any] = {"text": item}
    elif isinstance(item, dict):
        raw_item = dict(item)
    else:
        return None
    text = compact_text(raw_item.get("text") or raw_item.get("headline") or raw_item.get("title") or raw_item.get("quote"))
    if not text:
        return None
    limits = FIELD_LIMITS[field]
    item_start = raw_item.get("start")
    item_end = raw_item.get("end")
    try:
        resolved_start = float(item_start) if item_start not in (None, "") else start
    except (TypeError, ValueError):
        resolved_start = start
    try:
        resolved_end = float(item_end) if item_end not in (None, "") else end
    except (TypeError, ValueError):
        resolved_end = end
    return {
        **raw_item,
        "text": short_line(
            text,
            max_words=int(limits["max_words"]),
            max_chars=int(limits["max_chars"]),
            uppercase=field in {"lower_thirds", "chyrons"},
        ),
        "type": compact_text(raw_item.get("type")) or fallback_type,
        "section_id": compact_text(raw_item.get("section_id")) or section_id,
        "claim_ids": _string_list(raw_item.get("claim_ids")) or list(fallback_claim_ids),
        "source_notes": _string_list(raw_item.get("source_notes")) or list(fallback_source_notes),
        "start": round(resolved_start, 2),
        "end": round(max(resolved_start + 2.0, resolved_end), 2),
    }


def normalize_contract(contract: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    base = _deterministic_contract(manifest)
    base_by_id = {section["section_id"]: section for section in _dict_list(base.get("sections"))}
    raw_sections = _dict_list(contract.get("sections"))
    normalized_sections: list[dict[str, Any]] = []
    for base_section in _dict_list(base.get("sections")):
        section_id = compact_text(base_section.get("section_id"))
        provider_section = next(
            (section for section in raw_sections if compact_text(section.get("section_id")) == section_id),
            {},
        )
        section_type = CHYRON_TYPES_BY_SECTION.get(section_id, "key_fact")
        normalized: dict[str, Any] = {"section_id": section_id}
        for field in SCREEN_FIELDS:
            provider_items = provider_section.get(field) if isinstance(provider_section, dict) else None
            fallback_items = base_by_id.get(section_id, {}).get(field, [])
            raw_items = provider_items if isinstance(provider_items, list) and provider_items else fallback_items
            fallback_item = fallback_items[0] if fallback_items and isinstance(fallback_items[0], dict) else {}
            normalized[field] = [
                item
                for item in (
                    _normalize_item(
                        raw_item,
                        field=field,
                        section_id=section_id,
                        fallback_type=section_type,
                        fallback_claim_ids=_string_list(fallback_item.get("claim_ids")),
                        fallback_source_notes=_string_list(fallback_item.get("source_notes")),
                        start=float(base_by_id[section_id][field][0]["start"]) if base_by_id[section_id].get(field) else 0.0,
                        end=float(base_by_id[section_id][field][0]["end"]) if base_by_id[section_id].get(field) else 6.0,
                    )
                    for raw_item in raw_items
                )
                if item
            ]
        normalized_sections.append(normalized)
    normalized_contract = {
        "provider": compact_text(contract.get("provider")) or base.get("provider") or _provider_name(),
        "model": compact_text(contract.get("model")) or base.get("model") or "unknown",
        "sections": normalized_sections,
    }
    points, chyrons = flatten_contract(normalized_contract)
    normalized_contract["points"] = points
    normalized_contract["chyrons"] = chyrons
    normalized_contract["review"] = validate_contract(normalized_contract, manifest)
    return normalized_contract


def _item_grounding_review(item: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    claim_ids = _string_list(item.get("claim_ids"))
    text = compact_text(item.get("text"))
    fake_script = {
        "text": "",
        "claim_ids": claim_ids,
        "sections": [
            {
                "section_id": compact_text(item.get("section_id")) or "main_developments",
                "title": "Screen Text",
                "narration": text,
                "estimated_duration_seconds": 4,
                "claim_ids": claim_ids,
                "source_notes": _string_list(item.get("source_notes")),
            }
        ],
        "major_claims": [],
    }
    return writing_contract.groundedness_review(fake_script, raw)


def validate_contract(contract: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    warnings: list[str] = []
    item_count = 0
    section_count = 0
    for section in _dict_list(contract.get("sections")):
        section_id = compact_text(section.get("section_id"))
        if not section_id:
            warnings.append("section missing section_id")
            continue
        section_count += 1
        if not _dict_list(section.get("key_points")):
            warnings.append(f"{section_id} missing key_points")
        if not _dict_list(section.get("lower_thirds")):
            warnings.append(f"{section_id} missing lower_thirds")
        for field in SCREEN_FIELDS:
            limits = FIELD_LIMITS[field]
            for item in _dict_list(section.get(field)):
                item_count += 1
                text = compact_text(item.get("text"))
                if not text:
                    warnings.append(f"{section_id}/{field} item missing text")
                    continue
                if len(_words(text)) > int(limits["max_words"]):
                    warnings.append(f"{section_id}/{field} item too long")
                if not _string_list(item.get("claim_ids")):
                    warnings.append(f"{section_id}/{field} item missing claim_ids")
                if not _string_list(item.get("source_notes")):
                    warnings.append(f"{section_id}/{field} item missing source_notes")
                lowered = text.lower()
                if any(pattern in lowered for pattern in CLICKBAIT_PATTERNS):
                    warnings.append(f"{section_id}/{field} item uses clickbait phrasing")
                grounding = _item_grounding_review(item, raw)
                if grounding["status"] != "pass":
                    warnings.extend(f"{section_id}/{field}: {warning}" for warning in grounding["warnings"])
    return {
        "status": "pass" if not warnings else "needs_review",
        "section_count": section_count,
        "item_count": item_count,
        "warnings": warnings,
    }


def flatten_contract(contract: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    points: list[dict[str, Any]] = []
    chyrons: list[dict[str, Any]] = []
    seen_points: set[tuple[str, str]] = set()
    seen_chyrons: set[tuple[str, str]] = set()
    for section in _dict_list(contract.get("sections")):
        for item in [*_dict_list(section.get("key_points")), *_dict_list(section.get("on_screen_bullets"))]:
            key = ("point", compact_text(item.get("text")).lower())
            if key in seen_points:
                continue
            seen_points.add(key)
            points.append({key: value for key, value in item.items() if value not in (None, "", [], {})})
        for item in [*_dict_list(section.get("lower_thirds")), *_dict_list(section.get("chyrons"))]:
            key = ("chyron", compact_text(item.get("text")).lower())
            if key in seen_chyrons:
                continue
            seen_chyrons.add(key)
            chyrons.append({key: value for key, value in item.items() if value not in (None, "", [], {})})
    return points, chyrons


def _merge_sections(manifest: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
    existing_sections = _fallback_sections(manifest)
    by_id = {compact_text(section.get("section_id")): section for section in _dict_list(contract.get("sections"))}
    merged: list[dict[str, Any]] = []
    for section in existing_sections:
        section_id = compact_text(section.get("section_id")) or "section"
        enriched = dict(section)
        generated = by_id.get(section_id, {})
        for field in SCREEN_FIELDS:
            if generated.get(field):
                enriched[field] = generated[field]
        merged.append(enriched)
    if not merged and isinstance(script, dict):
        return _dict_list(script.get("sections"))
    return merged


def derive_points(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    contract = normalize_contract(_deterministic_contract(manifest), manifest)
    return contract["points"]


def run(story_json_path: str | Path, *, force: bool = False) -> list[dict[str, Any]]:
    manifest = read_manifest(story_json_path)
    script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
    existing_points = manifest.get("points")
    has_section_chyrons = any(
        any(_dict_list(section.get(field)) for field in SCREEN_FIELDS)
        for section in _dict_list(script.get("sections"))
    )
    if existing_points and has_section_chyrons and not force:
        print("[points] Reusing section-based points/chyrons from manifest.")
        return existing_points
    raw_contract = _provider_contract(manifest)
    contract = normalize_contract(raw_contract, manifest)
    review = contract["review"]
    if review["status"] != "pass":
        raise ValueError(f"News points/chyrons failed groundedness review: {', '.join(review['warnings'])}")
    script["sections"] = _merge_sections(manifest, contract)
    manifest["script"] = script
    manifest["points"] = contract["points"]
    manifest["chyrons"] = contract["chyrons"]
    manifest["news_points_review"] = {
        **review,
        "provider": contract.get("provider"),
        "model": contract.get("model"),
    }
    write_manifest(story_json_path, manifest)
    print(
        f"[points] Wrote {len(contract['points'])} point(s) and "
        f"{len(contract['chyrons'])} chyron cue(s)."
    )
    return contract["points"]
