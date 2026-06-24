from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import VisualAsset, VisualPlanEntry, VisualSkillSpec, VisualSkillType
from .query_builder import compact_text, split_sentences, unique, visual_handoff_for_manifest

DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?"
    r"|\b\d{4}-\d{2}-\d{2}\b|\b(?:19|20)\d{2}\b",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(
    r"\b\d+(?:,\d{3})*(?:\.\d+)?(?:\s?[-–]\s?[A-Za-z]+|\s?(?:%|percent|million|billion|trillion|"
    r"gigawatts?|gw|megawatts?|mw|kilometers?|km|days?|hours?|dollars?|usd|rupees?|people|jobs|deaths?))?\b",
    re.IGNORECASE,
)
QUOTE_RE = re.compile(r"[\"“]([^\"”]{12,220})[\"”]")

LOCATION_TERMS = {
    "africa",
    "beijing",
    "china",
    "delhi",
    "europe",
    "european union",
    "india",
    "israel",
    "kenya",
    "lake naivasha",
    "middle east",
    "moscow",
    "new york",
    "russia",
    "silicon valley",
    "taiwan",
    "ukraine",
    "united kingdom",
    "united states",
    "us",
    "u.s.",
    "washington",
}


@dataclass(slots=True)
class SectionEvidence:
    section: dict[str, Any]
    section_text: str
    claim_ids: list[str]
    source_notes: list[str]
    evidence_texts: list[str]
    facts: list[str]
    claims: list[dict[str, Any]]
    entities: list[str]
    source_metadata: dict[str, Any]
    visual_opportunities: list[str]

    @property
    def evidence_blob(self) -> str:
        return " ".join(unique([self.section_text, *self.evidence_texts, *self.facts], limit=40))


def build_visual_skill_specs(
    manifest: dict[str, Any],
    *,
    entries: list[VisualPlanEntry],
    selected_assets: list[VisualAsset],
) -> tuple[list[VisualSkillSpec], dict[str, Any]]:
    assets_by_id = {asset.asset_id: asset for asset in selected_assets}
    specs: list[VisualSkillSpec] = []
    warnings: list[str] = []
    for index, entry in enumerate(entries, start=1):
        asset = assets_by_id.get(entry.selected_visual_candidate_id)
        evidence = _section_evidence(manifest, entry)
        skill_type, reason, spec, skill_warnings = _assign_skill(entry, asset, evidence)
        warnings.extend(f"{entry.section_id}: {warning}" for warning in skill_warnings)
        specs.append(
            VisualSkillSpec(
                skill_id=f"{entry.section_id}_{skill_type}",
                story_id=entry.story_id,
                episode_id=entry.episode_id,
                section_id=entry.section_id,
                selected_visual_candidate_id=entry.selected_visual_candidate_id,
                skill_type=skill_type,
                skill_reason=reason,
                spec=spec,
                evidence_claim_ids=evidence.claim_ids,
                source_notes=evidence.source_notes,
                source_url=entry.source_url or evidence.source_metadata.get("source_url"),
                source_domain=entry.source_domain or evidence.source_metadata.get("source_domain"),
                rights_category=entry.rights_category,
                attribution_text=entry.attribution_text,
                needs_manual_review=entry.needs_manual_review,
                fallback_reason=entry.fallback_reason,
                warnings=skill_warnings,
            )
        )
    skill_types: dict[str, int] = {}
    for spec in specs:
        skill_types[spec.skill_type] = skill_types.get(spec.skill_type, 0) + 1
    return specs, {
        "skill_count": len(specs),
        "skill_types": skill_types,
        "warnings": warnings,
        "manual_review_warnings": [
            {
                "section_id": spec.section_id,
                "skill_type": spec.skill_type,
                "candidate_id": spec.selected_visual_candidate_id,
            }
            for spec in specs
            if spec.needs_manual_review
        ],
        "unsupported_skill_warnings": [warning for warning in warnings if "unsupported" in warning],
    }


def _assign_skill(
    entry: VisualPlanEntry,
    asset: VisualAsset | None,
    evidence: SectionEvidence,
) -> tuple[str, str, dict[str, Any], list[str]]:
    numbers = _number_records(evidence)
    dates = _date_records(evidence)
    quotes = _quote_records(evidence)
    locations = _location_names(evidence)
    warnings: list[str] = []

    if entry.fallback_status == "generated_context_card" or entry.rights_category == "first_party_generated":
        return (
            VisualSkillType.CONTEXT_CARD.value,
            "generated first-party fallback/context card",
            _context_card_spec(entry, evidence),
            warnings,
        )
    if entry.visual_role == "document_visual" or entry.media_type in {"document", "screenshot"}:
        return (
            VisualSkillType.DOCUMENT_CALLOUT.value,
            "document or screenshot visual selected for this section",
            _document_callout_spec(entry, evidence),
            warnings,
        )
    if entry.visual_role == "quote_card":
        if quotes:
            return (
                VisualSkillType.QUOTE_CARD.value,
                "grounded quote found in source evidence",
                _quote_card_spec(entry, evidence, quotes[0]),
                warnings,
            )
        warnings.append("quote_card_unsupported_no_grounded_quote")
        return (
            VisualSkillType.CONTEXT_CARD.value,
            "quote requested but no grounded quote was available",
            _context_card_spec(entry, evidence),
            warnings,
        )
    if _wants_map(entry, evidence):
        if locations:
            return (
                VisualSkillType.MAP.value,
                "location or geopolitical section with grounded location evidence",
                _map_spec(entry, evidence, locations),
                warnings,
            )
        warnings.append("map_unsupported_no_grounded_location")
    if _wants_timeline(entry, evidence):
        if len(dates) >= 2:
            return (
                VisualSkillType.TIMELINE.value,
                "multiple grounded dates found in section evidence",
                _timeline_spec(entry, evidence, dates),
                warnings,
            )
        warnings.append("timeline_unsupported_not_enough_grounded_dates")
    if _wants_numeric(entry, evidence):
        if len(numbers) >= 2:
            return (
                VisualSkillType.CHART.value,
                "multiple grounded numeric values found in section evidence",
                _chart_spec(entry, evidence, numbers),
                warnings,
            )
        if numbers:
            return (
                VisualSkillType.DATA_CALLOUT.value,
                "grounded numeric value found in section evidence",
                _data_callout_spec(entry, evidence, numbers[0]),
                warnings,
            )
        warnings.append("data_callout_unsupported_no_grounded_number")
    if entry.visual_role == "entity_visual" or (asset and asset.entities):
        return (
            VisualSkillType.ENTITY_CARD.value,
            "entity-matched visual selected for this section",
            _entity_card_spec(entry, evidence, asset),
            warnings,
        )
    if entry.visual_role == "fallback_visual" and evidence.source_metadata:
        return (
            VisualSkillType.SOURCE_CARD.value,
            "fallback/conclusion section anchored to source metadata",
            _source_card_spec(entry, evidence),
            warnings,
        )
    if entry.media_type == "video" or entry.asset_type == "video":
        return (
            VisualSkillType.BROLL_CLIP.value,
            "video visual selected for this section",
            _broll_clip_spec(entry, evidence),
            warnings,
        )
    if entry.media_type in {"photo", "image"} or entry.asset_type == "image":
        return (
            VisualSkillType.STILL_IMAGE.value,
            "still visual selected for this section",
            _still_image_spec(entry, evidence),
            warnings,
        )
    return (
        VisualSkillType.CONTEXT_CARD.value,
        "default grounded context card",
        _context_card_spec(entry, evidence),
        warnings,
    )


def _section_evidence(manifest: dict[str, Any], entry: VisualPlanEntry) -> SectionEvidence:
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
    section = _section_for_id(script, entry.section_id)
    section_text = " ".join(
        unique(
            [
                entry.section_title,
                compact_text(section.get("narration")),
                *_screen_text_items(section),
            ],
            limit=20,
        )
    )
    all_claims = [claim for claim in raw.get("claims", []) if isinstance(claim, dict)]
    claim_ids = _string_list(section.get("claim_ids"))
    matched_claims = [
        claim
        for claim in all_claims
        if compact_text(claim.get("claim_id")) in claim_ids
    ] or all_claims[:3]
    claim_texts = unique(
        [
            text
            for claim in matched_claims
            for text in [
                compact_text(claim.get("text")),
                compact_text(claim.get("evidence_quote")),
                compact_text(claim.get("summary")),
            ]
            if text
        ],
        limit=16,
    )
    facts = _string_list(raw.get("facts"))[:6]
    handoff = visual_handoff_for_manifest(manifest)
    entities = unique(
        [
            *_string_list(raw.get("entities") or raw.get("key_entities")),
            *_string_list(handoff.get("entities")),
            *([entry.section_title] if entry.visual_role == "entity_visual" else []),
        ],
        limit=12,
    )
    source_metadata = dict(handoff.get("source_metadata") if isinstance(handoff.get("source_metadata"), dict) else {})
    source_metadata.setdefault("source_category", raw.get("category"))
    source_metadata.setdefault("source_url", raw.get("source_url"))
    source_metadata.setdefault("source_name", raw.get("source_name"))
    source_notes = unique(
        [
            *_string_list(section.get("source_notes")),
            compact_text(raw.get("source_name")),
            compact_text(source_metadata.get("source_name") or source_metadata.get("source")),
        ],
        limit=8,
    )
    evidence_texts = unique(
        [
            section_text,
            *claim_texts,
            *facts,
            compact_text(raw.get("summary")),
            compact_text(raw.get("headline_source")),
            *handoff.get("visual_opportunities", []),
            *entities,
        ],
        limit=32,
    )
    return SectionEvidence(
        section=section,
        section_text=section_text,
        claim_ids=claim_ids or [compact_text(claim.get("claim_id")) for claim in matched_claims if compact_text(claim.get("claim_id"))],
        source_notes=source_notes,
        evidence_texts=evidence_texts,
        facts=facts,
        claims=matched_claims,
        entities=entities,
        source_metadata=source_metadata,
        visual_opportunities=handoff.get("visual_opportunities", []),
    )


def _section_for_id(script: dict[str, Any], section_id: str) -> dict[str, Any]:
    sections = script.get("sections") if isinstance(script.get("sections"), list) else []
    for section in sections:
        if isinstance(section, dict) and compact_text(section.get("section_id")) == section_id:
            return section
    return {}


def _screen_text_items(section: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("key_points", "lower_thirds", "chyrons", "on_screen_bullets", "quote_cards", "data_callouts"):
        items = section.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str):
                values.append(compact_text(item))
            elif isinstance(item, dict):
                values.append(compact_text(item.get("text") or item.get("title") or item.get("headline")))
    return [value for value in values if value]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [compact_text(item) for item in value if compact_text(item)]


def _wants_map(entry: VisualPlanEntry, evidence: SectionEvidence) -> bool:
    text = f"{entry.visual_role} {entry.section_type} {entry.section_title}".lower()
    category = compact_text(evidence.source_metadata.get("source_category")).lower()
    if entry.visual_role == "entity_visual" and entry.section_type != "background_context":
        return False
    section_has_location = bool(_location_names_from_text(evidence.section_text))
    return (
        entry.visual_role == "location_visual"
        or "map" in text
        or "satellite" in text
        or (category in {"world", "geopolitics", "conflict", "climate"} and section_has_location)
    )


def _wants_timeline(entry: VisualPlanEntry, evidence: SectionEvidence) -> bool:
    text = f"{entry.section_type} {entry.section_title} {' '.join(evidence.visual_opportunities)}".lower()
    return (
        entry.section_type in {"background_context", "main_developments", "stakes_consequences", "opposing_views_uncertainty"}
        or "timeline" in text
        or "deadline" in text
        or "sequence" in text
        or "schedule" in text
    )


def _wants_numeric(entry: VisualPlanEntry, evidence: SectionEvidence) -> bool:
    text = f"{entry.visual_role} {entry.section_type} {entry.section_title} {' '.join(evidence.visual_opportunities)}".lower()
    return (
        entry.visual_role == "data_callout"
        or entry.media_type == "chart"
        or entry.asset_type == "chart"
        or "chart" in text
        or "data" in text
        or "number" in text
        or "tariff" in text
    )


def _number_records(evidence: SectionEvidence) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for text in evidence.evidence_texts:
        for match in NUMBER_RE.finditer(text):
            value = match.group(0).strip()
            records.append(
                {
                    "value": value,
                    "label": _sentence_containing(text, value) or evidence.section_text or value,
                    "source_claim_ids": evidence.claim_ids,
                }
            )
    return _unique_records(records, "value", limit=6)


def _date_records(evidence: SectionEvidence) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for text in evidence.evidence_texts:
        for match in DATE_RE.finditer(text):
            value = match.group(0).strip()
            records.append(
                {
                    "date": value,
                    "label": _sentence_containing(text, value) or evidence.section_text or value,
                    "source_claim_ids": evidence.claim_ids,
                }
            )
    return _unique_records(records, "date", limit=8)


def _quote_records(evidence: SectionEvidence) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for text in evidence.evidence_texts:
        for match in QUOTE_RE.finditer(text):
            quote = compact_text(match.group(1))
            records.append(
                {
                    "quote_text": quote,
                    "speaker": evidence.source_notes[0] if evidence.source_notes else evidence.source_metadata.get("source_name", "Source"),
                    "source_claim_ids": evidence.claim_ids,
                }
            )
    return _unique_records(records, "quote_text", limit=4)


def _location_names(evidence: SectionEvidence) -> list[str]:
    found = _location_names_from_text(evidence.evidence_blob)
    for entity in evidence.entities:
        entity_text = compact_text(entity)
        if entity_text.lower() in LOCATION_TERMS:
            found.append(entity_text)
    return unique(found, limit=6)


def _location_names_from_text(value: str) -> list[str]:
    text = compact_text(value).lower()
    found: list[str] = []
    for term in sorted(LOCATION_TERMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(term)}\b", text):
            found.append(term.title() if term not in {"us", "u.s."} else "United States")
    return found


def _map_spec(entry: VisualPlanEntry, evidence: SectionEvidence, locations: list[str]) -> dict[str, Any]:
    return {
        "location_names": locations,
        "region": locations[0] if locations else "",
        "labels": unique([entry.section_title, *locations], limit=5),
        "source_claim_ids": evidence.claim_ids,
        "source_notes": evidence.source_notes,
    }


def _chart_spec(entry: VisualPlanEntry, evidence: SectionEvidence, numbers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": entry.section_title,
        "metric": _metric_label(entry, evidence),
        "values": numbers[:5],
        "units": _units_from_numbers(numbers),
        "source_claim_ids": evidence.claim_ids,
    }


def _timeline_spec(entry: VisualPlanEntry, evidence: SectionEvidence, dates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": entry.section_title,
        "events": dates[:6],
        "source_claim_ids": evidence.claim_ids,
    }


def _document_callout_spec(entry: VisualPlanEntry, evidence: SectionEvidence) -> dict[str, Any]:
    excerpt = _first_non_empty([*evidence.evidence_texts, evidence.section_text])
    source_title = evidence.source_metadata.get("source_name") or (
        evidence.source_notes[0] if evidence.source_notes else entry.section_title
    )
    return {
        "source_title": source_title,
        "excerpt": excerpt[:260],
        "summary": _first_non_empty(evidence.facts) or evidence.section_text,
        "highlight_labels": unique([entry.section_title, *evidence.entities, *_number_values(evidence)], limit=5),
        "source_url": entry.source_url or evidence.source_metadata.get("source_url"),
        "source_claim_ids": evidence.claim_ids,
    }


def _quote_card_spec(entry: VisualPlanEntry, evidence: SectionEvidence, quote: dict[str, Any]) -> dict[str, Any]:
    return {
        "quote_text": quote["quote_text"],
        "speaker": quote.get("speaker") or (evidence.source_notes[0] if evidence.source_notes else "Source"),
        "context": entry.section_title,
        "source_claim_ids": evidence.claim_ids,
    }


def _data_callout_spec(entry: VisualPlanEntry, evidence: SectionEvidence, number: dict[str, Any]) -> dict[str, Any]:
    value, unit = _split_number_unit(number["value"])
    return {
        "number": value,
        "unit": unit,
        "label": entry.section_title,
        "context": number.get("label") or evidence.section_text,
        "source_claim_ids": evidence.claim_ids,
    }


def _context_card_spec(entry: VisualPlanEntry, evidence: SectionEvidence) -> dict[str, Any]:
    return {
        "title": entry.section_title,
        "subtitle": evidence.source_metadata.get("source_name") or (evidence.source_notes[0] if evidence.source_notes else ""),
        "bullets": unique([*evidence.facts, *_screen_text_items(evidence.section)], limit=4),
        "entities": evidence.entities,
        "source_notes": evidence.source_notes,
        "source_claim_ids": evidence.claim_ids,
        "rights_category": entry.rights_category,
    }


def _entity_card_spec(entry: VisualPlanEntry, evidence: SectionEvidence, asset: VisualAsset | None) -> dict[str, Any]:
    entities = unique([*(asset.entities if asset else []), *evidence.entities], limit=8)
    return {
        "title": entry.section_title,
        "entities": entities,
        "primary_entity": entities[0] if entities else entry.section_title,
        "relationship": _first_non_empty(evidence.facts) or evidence.section_text,
        "source_claim_ids": evidence.claim_ids,
    }


def _source_card_spec(entry: VisualPlanEntry, evidence: SectionEvidence) -> dict[str, Any]:
    return {
        "title": evidence.source_metadata.get("source_name") or (evidence.source_notes[0] if evidence.source_notes else entry.section_title),
        "source_url": entry.source_url or evidence.source_metadata.get("source_url"),
        "source_domain": entry.source_domain or evidence.source_metadata.get("source_domain"),
        "summary": _first_non_empty(evidence.facts) or evidence.section_text,
        "source_claim_ids": evidence.claim_ids,
    }


def _broll_clip_spec(entry: VisualPlanEntry, evidence: SectionEvidence) -> dict[str, Any]:
    return {
        "clip_title": entry.section_title,
        "source_url": entry.source_url,
        "source_domain": entry.source_domain,
        "audio_policy": "preserve_if_template_allows",
        "source_claim_ids": evidence.claim_ids,
    }


def _still_image_spec(entry: VisualPlanEntry, evidence: SectionEvidence) -> dict[str, Any]:
    return {
        "title": entry.section_title,
        "motion_preset": "push_in",
        "source_url": entry.source_url,
        "source_domain": entry.source_domain,
        "source_claim_ids": evidence.claim_ids,
    }


def _sentence_containing(text: str, value: str) -> str:
    for sentence in split_sentences(text):
        if value in sentence:
            return sentence
    return compact_text(text)


def _unique_records(records: list[dict[str, Any]], key: str, *, limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for record in records:
        value = compact_text(record.get(key)).lower()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(record)
        if len(result) >= limit:
            break
    return result


def _metric_label(entry: VisualPlanEntry, evidence: SectionEvidence) -> str:
    for value in [entry.section_title, evidence.section_text, *evidence.facts]:
        text = compact_text(value)
        if text:
            return text[:80]
    return "Reported value"


def _units_from_numbers(numbers: list[dict[str, Any]]) -> list[str]:
    units = [_split_number_unit(number["value"])[1] for number in numbers]
    return unique([unit for unit in units if unit], limit=5)


def _split_number_unit(value: str) -> tuple[str, str]:
    cleaned = compact_text(value)
    match = re.match(r"^(\d+(?:,\d{3})*(?:\.\d+)?)(.*)$", cleaned)
    if not match:
        return cleaned, ""
    return match.group(1), match.group(2).strip(" -–")


def _number_values(evidence: SectionEvidence) -> list[str]:
    return [record["value"] for record in _number_records(evidence)]


def _first_non_empty(values: list[str]) -> str:
    for value in values:
        text = compact_text(value)
        if text:
            return text
    return ""
