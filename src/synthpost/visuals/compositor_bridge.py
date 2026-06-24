from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import RightsCategory, VisualSkillType
from .planner import project_root_from_story

SUPPORTED_SKILL_TYPES = [item.value for item in VisualSkillType]
UNSAFE_RIGHTS_CATEGORIES = {
    RightsCategory.FAIR_USE_REVIEW_REQUIRED.value,
    RightsCategory.UNKNOWN_OR_REJECTED.value,
}
ATTRIBUTION_RECOMMENDED_RIGHTS = {
    RightsCategory.OFFICIAL_PUBLIC.value,
    RightsCategory.PUBLIC_DOMAIN.value,
    RightsCategory.PERMISSIVE_LICENSE.value,
}
ATTRIBUTION_BLOCKING_RIGHTS = {RightsCategory.PERMISSIVE_LICENSE.value}


def build_compositor_bridge(
    manifest: dict[str, Any],
    story_json_path: str | Path,
    *,
    review_only: bool | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    story_path = Path(story_json_path)
    project_root = project_root_from_story(story_path)
    story_path = story_path if story_path.is_absolute() else project_root / story_path
    review_enabled = _review_only_enabled() if review_only is None else review_only
    visual_plan_payload = _load_visual_plan(manifest, story_path, project_root)
    candidates_payload = _load_json_from_summary(manifest, story_path, project_root, "visual_candidates")
    skills_payload = _load_json_from_summary(manifest, story_path, project_root, "visual_skills")
    candidate_by_id = _candidate_index(manifest, candidates_payload)
    skill_by_section = _skill_index(visual_plan_payload, skills_payload)

    warnings: list[str] = []
    rejected: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    input_source = "legacy_visuals"

    sections = visual_plan_payload.get("sections") if isinstance(visual_plan_payload.get("sections"), list) else []
    if sections:
        input_source = "visual_plan"
        for index, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                continue
            candidate_id = _text(section.get("selected_visual_candidate_id"))
            candidate = candidate_by_id.get(candidate_id, {})
            skill = _skill_for_section(section, skill_by_section)
            record = _record_from_plan_section(section, candidate, skill, index=index)
            _normalize_record_paths(record, project_root)
            record_warnings = _validate_bridge_record(record, strict=True)
            if candidate_id and candidate_id not in candidate_by_id:
                record_warnings.append(f"{candidate_id}: missing_candidate_audit_record")
            record["warnings"] = _dedupe([*record.get("warnings", []), *record_warnings])
            if _blocks_render(record) and not review_enabled:
                rejected.append(
                    {
                        "candidate_id": record.get("candidate_id"),
                        "section_id": record.get("section_id"),
                        "rights_category": record.get("rights_category"),
                        "rejection_reasons": _dedupe([*_blocking_reasons(record), *record_warnings]),
                    }
                )
                continue
            if _blocks_render(record) and review_enabled:
                record["render_safety_status"] = "review_only"
            records.append(_clean(record))
    else:
        legacy_visuals = manifest.get("visuals") if isinstance(manifest.get("visuals"), list) else []
        for index, visual in enumerate(legacy_visuals, start=1):
            if not isinstance(visual, dict):
                continue
            record = _record_from_legacy_visual(visual, index=index)
            _normalize_record_paths(record, project_root)
            record_warnings = _validate_bridge_record(record, strict=False)
            record["warnings"] = _dedupe([*record.get("warnings", []), *record_warnings])
            records.append(_clean(record))

    warnings.extend(warning for record in records for warning in record.get("warnings", []))
    warnings.extend(_planning_warnings(visual_plan_payload))
    summary = _bridge_summary(
        manifest=manifest,
        story_path=story_path,
        project_root=project_root,
        input_source=input_source,
        records=records,
        rejected=rejected,
        warnings=warnings,
        visual_plan_payload=visual_plan_payload,
        candidates_payload=candidates_payload,
        skills_payload=skills_payload,
        review_only=review_enabled,
    )
    return records, summary


def apply_compositor_bridge(
    manifest: dict[str, Any],
    story_json_path: str | Path,
    *,
    review_only: bool | None = None,
) -> dict[str, Any]:
    records, summary = build_compositor_bridge(manifest, story_json_path, review_only=review_only)
    summary = dict(summary)
    summary["compositor_visuals_path"] = _write_compositor_visual_input(story_json_path, records, summary)
    manifest["compositor_visuals"] = records
    manifest["visual_compositor_bridge"] = summary
    return manifest


def bridge_validation_errors(summary: dict[str, Any] | None) -> list[str]:
    if not isinstance(summary, dict):
        return ["visual compositor bridge summary is missing"]
    if summary.get("review_only"):
        return []
    errors: list[str] = []
    if summary.get("validation_status") == "failed":
        errors.append("visual compositor bridge validation failed")
    if summary.get("rejected_visual_count"):
        errors.append(f"{summary.get('rejected_visual_count')} unsafe visual(s) rejected")
    attribution = summary.get("attribution") if isinstance(summary.get("attribution"), dict) else {}
    if attribution.get("blocking_missing_count"):
        errors.append(f"{attribution.get('blocking_missing_count')} visual(s) missing required attribution")
    return errors


def skill_placeholder(skill: dict[str, Any] | None, section: dict[str, Any] | None = None) -> dict[str, Any]:
    section = section or {}
    if not isinstance(skill, dict):
        return {
            "type": "none",
            "render_mode": "media_only",
            "title": _text(section.get("section_title") or section.get("title")),
            "lines": [],
        }
    skill_type = _text(skill.get("skill_type")) or "context_card"
    spec = skill.get("spec") if isinstance(skill.get("spec"), dict) else {}
    title = _placeholder_title(skill_type, spec, section)
    lines = _placeholder_lines(skill_type, spec)
    return _clean(
        {
            "type": skill_type if skill_type in SUPPORTED_SKILL_TYPES else "context_card",
            "render_mode": "placeholder",
            "title": title,
            "subtitle": _first_text(spec.get("subtitle"), spec.get("source_title"), section.get("section_type")),
            "lines": lines[:4],
            "source_notes": skill.get("source_notes") if isinstance(skill.get("source_notes"), list) else [],
            "warnings": skill.get("warnings") if isinstance(skill.get("warnings"), list) else [],
        }
    )


def _record_from_plan_section(
    section: dict[str, Any],
    candidate: dict[str, Any],
    skill: dict[str, Any] | None,
    *,
    index: int,
) -> dict[str, Any]:
    source_label = _first_text(section.get("sourceLabel"), candidate.get("source_name"), section.get("attribution_text"), "SYNTHPOST")
    attribution_text = _first_text(
        section.get("attribution_text"),
        candidate.get("attribution_text"),
        section.get("attribution"),
        candidate.get("attribution"),
    )
    rights_category = _first_text(section.get("rights_category"), candidate.get("rights_category"))
    start = _number(section.get("start"), 0)
    end = _number(section.get("end"), start + 6)
    record = {
        "id": f"cv_{index:03d}",
        "candidate_id": _first_text(section.get("selected_visual_candidate_id"), candidate.get("id"), candidate.get("asset_id")),
        "plan_id": _first_text(section.get("script_section_id"), section.get("section_id")),
        "section_id": _first_text(section.get("script_section_id"), section.get("section_id")),
        "section_type": section.get("section_type"),
        "section_title": section.get("section_title"),
        "visual_role": section.get("visual_role"),
        "path": _first_text(section.get("path"), candidate.get("downloaded_path"), candidate.get("path"), section.get("asset_url")),
        "asset_url": _first_text(section.get("asset_url"), candidate.get("asset_url"), candidate.get("remote_url"), candidate.get("path")),
        "start": start,
        "end": end,
        "display_duration_seconds": _number(section.get("display_duration_seconds"), round(max(0.0, end - start), 2)),
        "fit": section.get("fit") or "cover",
        "sourceLabel": source_label.upper()[:42],
        "source_url": _first_text(section.get("source_url"), candidate.get("source_url")),
        "source_domain": _first_text(section.get("source_domain"), candidate.get("source_domain")),
        "source_name": _first_text(candidate.get("source_name"), source_label),
        "provider": candidate.get("provider"),
        "provider_type": candidate.get("provider_type"),
        "license": candidate.get("license"),
        "usage_note": candidate.get("usage_note"),
        "attribution": _first_text(section.get("attribution"), candidate.get("attribution")),
        "attribution_text": attribution_text,
        "attribution_required": bool(candidate.get("attribution_required")),
        "rights_category": rights_category,
        "rights_tier": candidate.get("rights_tier"),
        "rights_confidence": candidate.get("rights_confidence"),
        "usage_basis": candidate.get("usage_basis"),
        "manual_review_flag": bool(section.get("manual_review_flag") or section.get("needs_manual_review") or candidate.get("needs_manual_review")),
        "needs_manual_review": bool(section.get("needs_manual_review") or candidate.get("needs_manual_review")),
        "manual_review_status": candidate.get("manual_review_status"),
        "fallback_status": section.get("fallback_status"),
        "fallback_reason": section.get("fallback_reason"),
        "media_type": _first_text(section.get("media_type"), candidate.get("media_type")),
        "asset_type": _first_text(section.get("asset_type"), candidate.get("asset_type")),
        "relevance_score": section.get("relevance_score"),
        "relevance_reason": section.get("relevance_reason"),
        "motion": candidate.get("motion"),
        "visual_skill": skill,
        "visual_skill_type": skill.get("skill_type") if isinstance(skill, dict) else None,
        "skill_placeholder": skill_placeholder(skill, section),
        "render_safety_status": "ready",
        "input_source": "visual_plan",
    }
    return record


def _record_from_legacy_visual(visual: dict[str, Any], *, index: int) -> dict[str, Any]:
    source_label = _first_text(visual.get("sourceLabel"), visual.get("source_name"), "SYNTHPOST")
    record = {
        "id": f"legacy_{index:03d}",
        "candidate_id": visual.get("asset_id"),
        "section_id": _first_text(visual.get("segment_id"), f"legacy_{index:03d}"),
        "section_type": "legacy_visual",
        "visual_role": visual.get("visual_role") or "legacy_visual",
        "path": _first_text(visual.get("path"), visual.get("downloaded_path"), visual.get("asset_url")),
        "asset_url": _first_text(visual.get("asset_url"), visual.get("path")),
        "start": _number(visual.get("start"), 0),
        "end": _number(visual.get("end"), _number(visual.get("start"), 0) + 6),
        "fit": visual.get("fit") or "cover",
        "sourceLabel": source_label.upper()[:42],
        "source_url": visual.get("source_url"),
        "source_domain": visual.get("source_domain"),
        "source_name": visual.get("source_name"),
        "provider": visual.get("provider"),
        "provider_type": visual.get("provider_type"),
        "license": visual.get("license"),
        "usage_note": visual.get("usage_note"),
        "attribution": visual.get("attribution"),
        "attribution_text": visual.get("attribution_text"),
        "attribution_required": bool(visual.get("attribution_required")),
        "rights_category": visual.get("rights_category"),
        "rights_tier": visual.get("rights_tier"),
        "rights_confidence": visual.get("rights_confidence"),
        "usage_basis": visual.get("usage_basis"),
        "manual_review_flag": bool(visual.get("manual_review_flag") or visual.get("needs_manual_review")),
        "needs_manual_review": bool(visual.get("needs_manual_review")),
        "manual_review_status": visual.get("manual_review_status"),
        "fallback_status": visual.get("fallback_status"),
        "fallback_reason": visual.get("fallback_reason"),
        "media_type": visual.get("media_type"),
        "asset_type": visual.get("asset_type"),
        "motion": visual.get("motion"),
        "audio": visual.get("audio"),
        "play_audio": visual.get("play_audio"),
        "volume": visual.get("volume"),
        "skill_placeholder": skill_placeholder(None, visual),
        "render_safety_status": "legacy_unverified" if not visual.get("rights_category") else "ready",
        "input_source": "legacy_visuals",
    }
    return record


def _validate_bridge_record(record: dict[str, Any], *, strict: bool) -> list[str]:
    warnings: list[str] = []
    identity = _first_text(record.get("candidate_id"), record.get("id"), "visual")
    if not record.get("path") and not record.get("asset_url"):
        warnings.append(f"{identity}: missing_renderable_path")
    rights_category = _text(record.get("rights_category"))
    if not rights_category:
        warnings.append(f"{identity}: missing_rights_category")
    elif rights_category in UNSAFE_RIGHTS_CATEGORIES:
        warnings.append(f"{identity}: unsafe_rights_category_{rights_category}")
    if record.get("manual_review_flag") or record.get("needs_manual_review"):
        warnings.append(f"{identity}: manual_review_required")
    if record.get("attribution_required") and not record.get("attribution_text"):
        warnings.append(f"{identity}: missing_required_attribution")
    if rights_category in ATTRIBUTION_RECOMMENDED_RIGHTS and not record.get("attribution_text"):
        warnings.append(f"{identity}: missing_attribution_text")
    if rights_category != RightsCategory.FIRST_PARTY_GENERATED.value and strict and not record.get("source_url"):
        warnings.append(f"{identity}: missing_source_url")
    if strict and not record.get("visual_skill"):
        warnings.append(f"{identity}: missing_visual_skill_spec")
    return warnings


def _bridge_summary(
    *,
    manifest: dict[str, Any],
    story_path: Path,
    project_root: Path,
    input_source: str,
    records: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    warnings: list[str],
    visual_plan_payload: dict[str, Any],
    candidates_payload: dict[str, Any],
    skills_payload: dict[str, Any],
    review_only: bool,
) -> dict[str, Any]:
    audit_paths = _audit_paths(manifest, story_path, project_root, visual_plan_payload, candidates_payload, skills_payload)
    rights_categories = sorted({category for category in (_text(record.get("rights_category")) for record in records) if category})
    missing_attribution = [
        _first_text(record.get("candidate_id"), record.get("id"))
        for record in records
        if (
            record.get("attribution_required")
            or record.get("rights_category") in ATTRIBUTION_RECOMMENDED_RIGHTS
        )
        and not record.get("attribution_text")
    ]
    manual_review_records = [
        _first_text(record.get("candidate_id"), record.get("id"))
        for record in records
        if record.get("manual_review_flag") or record.get("needs_manual_review")
    ]
    blocking_missing_attribution = [
        _first_text(record.get("candidate_id"), record.get("id"))
        for record in records
        if _missing_blocking_attribution(record)
    ]
    fallback_count = sum(1 for record in records if record.get("fallback_status") not in (None, "", "none"))
    planning_audit = visual_plan_payload.get("audit") if isinstance(visual_plan_payload.get("audit"), dict) else {}
    missing_coverage = planning_audit.get("missing_visual_coverage_warnings") if isinstance(planning_audit.get("missing_visual_coverage_warnings"), list) else []
    unsafe_visual_ids = _dedupe(
        [
            *[_first_text(item.get("candidate_id"), item.get("section_id")) for item in rejected],
            *[_first_text(record.get("candidate_id"), record.get("id")) for record in records if _blocks_render(record)],
        ]
    )
    validation_failed = bool(rejected or blocking_missing_attribution)
    return _clean(
        {
            "version": 1,
            "story_id": manifest.get("story_id"),
            "episode_id": manifest.get("episode_id"),
            "status": "failed" if validation_failed else ("ready_with_warnings" if warnings else "ready"),
            "validation_status": "failed" if validation_failed else ("passed_with_warnings" if warnings else "passed"),
            "input_source": input_source,
            "review_only": review_only,
            "visual_candidates_path": audit_paths.get("visual_candidates"),
            "visual_plan_path": audit_paths.get("visual_plan"),
            "visual_skills_path": audit_paths.get("visual_skills"),
            "selected_visual_count": len(records),
            "rejected_visual_count": len(rejected),
            "fallback_count": fallback_count,
            "manual_review_warning_count": len(manual_review_records),
            "unsafe_visual_warning_count": len(unsafe_visual_ids),
            "unsafe_visual_ids": unsafe_visual_ids,
            "rights_categories_used": rights_categories,
            "attribution": {
                "complete": not missing_attribution,
                "missing_count": len(missing_attribution),
                "missing_visual_ids": missing_attribution,
                "blocking_missing_count": len(blocking_missing_attribution),
                "blocking_missing_visual_ids": blocking_missing_attribution,
            },
            "supported_skill_types": SUPPORTED_SKILL_TYPES,
            "skill_types_used": sorted({record.get("visual_skill_type") for record in records if record.get("visual_skill_type")}),
            "warnings": _dedupe(warnings),
            "manual_review_warnings": manual_review_records,
            "missing_visual_coverage_warnings": missing_coverage,
            "rejected_visuals": rejected,
        }
    )


def _audit_paths(
    manifest: dict[str, Any],
    story_path: Path,
    project_root: Path,
    visual_plan_payload: dict[str, Any],
    candidates_payload: dict[str, Any],
    skills_payload: dict[str, Any],
) -> dict[str, str]:
    summary = manifest.get("visual_plan") if isinstance(manifest.get("visual_plan"), dict) else {}
    audit_paths = summary.get("audit_paths") if isinstance(summary.get("audit_paths"), dict) else {}
    result = {
        "visual_candidates": _first_text(
            audit_paths.get("visual_candidates"),
            visual_plan_payload.get("visual_candidates_path"),
            skills_payload.get("visual_candidates_path"),
            _relative_if_exists(story_path.parent / "visuals" / "visual_candidates.json", project_root),
        ),
        "visual_plan": _first_text(
            audit_paths.get("visual_plan"),
            candidates_payload.get("visual_plan_path"),
            skills_payload.get("visual_plan_path"),
            _relative_if_exists(story_path.parent / "visuals" / "visual_plan.json", project_root),
        ),
        "visual_skills": _first_text(
            audit_paths.get("visual_skills"),
            visual_plan_payload.get("visual_skills_path"),
            candidates_payload.get("visual_skills_path"),
            _relative_if_exists(story_path.parent / "visuals" / "visual_skills.json", project_root),
        ),
    }
    return {key: value for key, value in result.items() if value}


def _load_visual_plan(manifest: dict[str, Any], story_path: Path, project_root: Path) -> dict[str, Any]:
    return _load_json_from_summary(manifest, story_path, project_root, "visual_plan")


def _load_json_from_summary(
    manifest: dict[str, Any],
    story_path: Path,
    project_root: Path,
    key: str,
) -> dict[str, Any]:
    summary = manifest.get("visual_plan") if isinstance(manifest.get("visual_plan"), dict) else {}
    audit_paths = summary.get("audit_paths") if isinstance(summary.get("audit_paths"), dict) else {}
    candidate_paths = [
        audit_paths.get(key),
        summary.get(f"{key}_path"),
        str(story_path.parent / "visuals" / f"{key}.json"),
    ]
    for value in candidate_paths:
        if not value:
            continue
        path = Path(str(value))
        resolved = path if path.is_absolute() else project_root / path
        if not resolved.exists():
            continue
        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def _write_compositor_visual_input(
    story_json_path: str | Path,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    story_path = Path(story_json_path)
    project_root = project_root_from_story(story_path)
    story_path = story_path if story_path.is_absolute() else project_root / story_path
    output_path = story_path.parent / "visuals" / "compositor_visuals.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "story_id": summary.get("story_id"),
        "episode_id": summary.get("episode_id"),
        "visual_count": len(records),
        "visuals": records,
        "bridge": {key: value for key, value in summary.items() if key != "compositor_visuals_path"},
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return _project_relative(output_path, project_root)


def _candidate_index(manifest: dict[str, Any], candidates_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key in ("candidates", "chosen_visuals", "selected_assets"):
        items = candidates_payload.get(key) if isinstance(candidates_payload.get(key), list) else []
        for item in items:
            if isinstance(item, dict):
                identity = _first_text(item.get("id"), item.get("asset_id"))
                if identity:
                    result[identity] = item
    for item in manifest.get("visual_assets", []) if isinstance(manifest.get("visual_assets"), list) else []:
        if isinstance(item, dict):
            identity = _first_text(item.get("id"), item.get("asset_id"))
            if identity:
                result.setdefault(identity, item)
    return result


def _skill_index(visual_plan_payload: dict[str, Any], skills_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for payload in (visual_plan_payload, skills_payload):
        skills = payload.get("skills") if isinstance(payload.get("skills"), list) else []
        for skill in skills:
            if isinstance(skill, dict):
                section_id = _text(skill.get("script_section_id"))
                if section_id:
                    result[section_id] = skill
    sections = visual_plan_payload.get("sections") if isinstance(visual_plan_payload.get("sections"), list) else []
    for section in sections:
        if isinstance(section, dict) and isinstance(section.get("visual_skill"), dict):
            section_id = _first_text(section.get("script_section_id"), section.get("section_id"))
            if section_id:
                result.setdefault(section_id, section["visual_skill"])
    return result


def _skill_for_section(section: dict[str, Any], skill_by_section: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if isinstance(section.get("visual_skill"), dict):
        return section["visual_skill"]
    section_id = _first_text(section.get("script_section_id"), section.get("section_id"))
    return skill_by_section.get(section_id)


def _planning_warnings(visual_plan_payload: dict[str, Any]) -> list[str]:
    audit = visual_plan_payload.get("audit") if isinstance(visual_plan_payload.get("audit"), dict) else {}
    warnings = list(visual_plan_payload.get("warnings") if isinstance(visual_plan_payload.get("warnings"), list) else [])
    warnings.extend(audit.get("missing_visual_coverage_warnings") if isinstance(audit.get("missing_visual_coverage_warnings"), list) else [])
    warnings.extend(audit.get("reuse_limit_warnings") if isinstance(audit.get("reuse_limit_warnings"), list) else [])
    skill_audit = visual_plan_payload.get("skill_audit") if isinstance(visual_plan_payload.get("skill_audit"), dict) else {}
    warnings.extend(skill_audit.get("warnings") if isinstance(skill_audit.get("warnings"), list) else [])
    return [_text(warning) for warning in warnings if _text(warning)]


def _placeholder_title(skill_type: str, spec: dict[str, Any], section: dict[str, Any]) -> str:
    if skill_type == VisualSkillType.MAP.value:
        locations = spec.get("location_names") if isinstance(spec.get("location_names"), list) else []
        return "Map: " + ", ".join(str(item) for item in locations[:3]) if locations else "Map Context"
    if skill_type == VisualSkillType.CHART.value:
        return _first_text(spec.get("title"), spec.get("metric"), "Chart")
    if skill_type == VisualSkillType.TIMELINE.value:
        return _first_text(spec.get("title"), "Timeline")
    if skill_type == VisualSkillType.DOCUMENT_CALLOUT.value:
        return _first_text(spec.get("source_title"), section.get("section_title"), "Document")
    if skill_type == VisualSkillType.QUOTE_CARD.value:
        return _first_text(spec.get("speaker"), "Quote")
    if skill_type == VisualSkillType.DATA_CALLOUT.value:
        return _first_text(spec.get("label"), "Data Point")
    if skill_type == VisualSkillType.ENTITY_CARD.value:
        return _first_text(spec.get("primary_entity"), spec.get("title"), "Entity")
    if skill_type == VisualSkillType.SOURCE_CARD.value:
        return _first_text(spec.get("title"), "Source")
    if skill_type == VisualSkillType.BROLL_CLIP.value:
        return _first_text(spec.get("clip_title"), section.get("section_title"), "B-roll")
    if skill_type == VisualSkillType.STILL_IMAGE.value:
        return _first_text(spec.get("title"), section.get("section_title"), "Still Image")
    return _first_text(spec.get("title"), section.get("section_title"), "Context")


def _placeholder_lines(skill_type: str, spec: dict[str, Any]) -> list[str]:
    if skill_type == VisualSkillType.MAP.value:
        return [str(item) for item in spec.get("labels", []) if item]
    if skill_type == VisualSkillType.CHART.value:
        values = spec.get("values") if isinstance(spec.get("values"), list) else []
        return [_first_text(value.get("value"), value.get("label")) for value in values if isinstance(value, dict)]
    if skill_type == VisualSkillType.TIMELINE.value:
        events = spec.get("events") if isinstance(spec.get("events"), list) else []
        return [_first_text(event.get("date"), event.get("label")) for event in events if isinstance(event, dict)]
    if skill_type == VisualSkillType.DOCUMENT_CALLOUT.value:
        return [_text(spec.get("excerpt")), _text(spec.get("summary"))]
    if skill_type == VisualSkillType.QUOTE_CARD.value:
        return [_text(spec.get("quote_text")), _text(spec.get("context"))]
    if skill_type == VisualSkillType.DATA_CALLOUT.value:
        return [" ".join(part for part in [_text(spec.get("number")), _text(spec.get("unit")), _text(spec.get("context"))] if part)]
    if skill_type == VisualSkillType.CONTEXT_CARD.value:
        return [str(item) for item in spec.get("bullets", []) if item]
    if skill_type == VisualSkillType.ENTITY_CARD.value:
        return [str(item) for item in spec.get("entities", []) if item]
    return [_first_text(spec.get("summary"), spec.get("source_domain"), spec.get("source_url"))]


def _is_unsafe(record: dict[str, Any]) -> bool:
    rights_category = _text(record.get("rights_category"))
    return not rights_category or rights_category in UNSAFE_RIGHTS_CATEGORIES or bool(record.get("manual_review_flag"))


def _missing_blocking_attribution(record: dict[str, Any]) -> bool:
    return (
        bool(record.get("attribution_required"))
        and _text(record.get("rights_category")) in ATTRIBUTION_BLOCKING_RIGHTS
        and not _text(record.get("attribution_text"))
    )


def _blocks_render(record: dict[str, Any]) -> bool:
    return _is_unsafe(record) or _missing_blocking_attribution(record)


def _blocking_reasons(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if _is_unsafe(record):
        reasons.append("unsafe_rights_category")
    if _missing_blocking_attribution(record):
        reasons.append("missing_required_attribution")
    return reasons


def _review_only_enabled() -> bool:
    return os.environ.get("SYNTHPOST_COMPOSITOR_REVIEW_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_record_paths(record: dict[str, Any], project_root: Path) -> None:
    for key in ("path", "asset_url"):
        value = _text(record.get(key))
        if not value or "://" in value or value.startswith("data:"):
            continue
        path = Path(value)
        if path.is_absolute():
            record[key] = _project_relative(path, project_root)


def _relative_if_exists(path: Path, project_root: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _project_relative(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _number(value: object, fallback: float) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return fallback


def _first_text(*values: object) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _text(value: object) -> str:
    return str(value or "").strip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _clean(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if value not in (None, "", [], {})}
