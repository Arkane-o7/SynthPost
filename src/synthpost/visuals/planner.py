from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from .downloader import download_asset, project_relative
from .manifest import visual_to_manifest
from .models import (
    AssetType,
    ProviderReport,
    SelectionStatus,
    StorySegment,
    VisualAsset,
    VisualPlan,
    VisualPlanEntry,
    VisualProvider,
)
from .policy import (
    OFFICIAL_PROVIDERS,
    OPEN_ARCHIVE_PROVIDERS,
    STOCK_PROVIDERS,
    asset_is_selectable,
    normalize_asset_metadata,
    provider_type_for_provider,
)
from .providers import (
    LocalLibraryProvider,
    ManifestMediaProvider,
    PexelsPixabayProvider,
    ScreenshotProvider,
    SourcePageProvider,
    WebSearchProvider,
    WikimediaProvider,
    YouTubeMetadataProvider,
    free_source_providers,
)
from .query_builder import (
    build_story_segments,
    build_visual_queries,
    compact_text,
    keyword_phrases,
    unique,
    visual_handoff_for_manifest,
)
from .ranker import rank_assets_for_segment
from .validator import renderable_and_safe, validate_asset


def project_root_from_story(story_json_path: Path) -> Path:
    resolved = story_json_path.resolve()
    for parent in [resolved.parent, *resolved.parents]:
        if (parent / "pipeline").exists() and (parent / "compositor").exists():
            return parent
    return Path(__file__).resolve().parents[3]


def default_providers(project_root: Path) -> list[VisualProvider]:
    providers: list[VisualProvider] = [
        ManifestMediaProvider(project_root),
        *free_source_providers(project_root),
        LocalLibraryProvider(project_root),
        SourcePageProvider(project_root),
        WikimediaProvider(project_root),
        PexelsPixabayProvider(project_root),
    ]
    if _context_graphics_enabled():
        providers.insert(-2, ScreenshotProvider(project_root))
    if os.environ.get("SYNTHPOST_INCLUDE_VISUAL_LEADS", "0") == "1":
        providers.extend([WebSearchProvider(project_root), YouTubeMetadataProvider(project_root)])
    return providers


def build_visual_plan(
    manifest: dict[str, Any],
    story_json_path: str | Path,
    *,
    providers: list[VisualProvider] | None = None,
) -> VisualPlan:
    story_path = Path(story_json_path)
    project_root = project_root_from_story(story_path)
    story_path = story_path if story_path.is_absolute() else project_root / story_path
    story_id = str(manifest.get("story_id") or story_path.parent.name)
    episode_id = str(manifest.get("episode_id") or story_path.parents[2].name)
    duration = _duration_seconds(manifest)
    target_count = _target_segment_count(duration)
    segments = _section_segments_from_script(manifest, duration_seconds=duration) or build_story_segments(
        manifest,
        target_count=target_count,
    )
    queries = build_visual_queries(manifest, segments)
    visual_providers = providers or default_providers(project_root)

    candidates: list[VisualAsset] = []
    reports: list[ProviderReport] = []
    for provider in visual_providers:
        try:
            provider_assets, report = provider.search(
                manifest=manifest,
                story_json_path=story_path,
                segments=segments,
                queries=queries,
            )
        except Exception as exc:  # noqa: BLE001 - visual acquisition should degrade cleanly.
            provider_assets = []
            report = ProviderReport(provider=provider.name, query_count=len(queries), warnings=[str(exc)])
        report.provider_type = report.provider_type or provider_type_for_provider(provider.name)
        if report.provider_type == "unknown":
            report.provider_type = provider_type_for_provider(report.provider)
        for asset in provider_assets:
            asset.story_id = asset.story_id or story_id
            normalize_asset_metadata(asset)
        candidates.extend(provider_assets)
        reports.append(report)

    candidates = _dedupe(candidates)
    selected = _select_assets(
        candidates,
        segments=segments,
        queries_by_segment={query.segment_id: query for query in queries},
        project_root=project_root,
    )
    selected = _download_selected(selected, story_path=story_path, project_root=project_root)

    warnings: list[str] = []
    for asset in selected:
        warnings.extend(validate_asset(asset, project_root=project_root))
    selected = [asset for asset in selected if renderable_and_safe(asset, project_root=project_root)]

    if len(selected) < len(segments):
        if _context_graphics_enabled():
            generated = [asset for asset in candidates if asset.provider == "screenshot_provider"]
            selected = _fill_with_generated(selected, generated, segments)
        else:
            selected = _reuse_real_visuals(selected, segments)
    _mark_selection_statuses(selected)

    manifest_visuals = [
        visual_to_manifest(asset, start=segment.start, end=segment.end, fit="cover")
        for segment, asset in zip(segments, selected, strict=False)
    ]
    plan_entries = _build_plan_entries(
        story_id=story_id,
        episode_id=episode_id,
        segments=segments,
        selected=selected,
    )
    planning_audit = _build_planning_audit(
        segments=segments,
        selected=selected,
        entries=plan_entries,
        candidates=candidates,
        queries_by_segment={query.segment_id: query for query in queries},
        project_root=project_root,
    )

    _mark_selected_counts(reports, selected)
    plan = VisualPlan(
        story_id=story_id,
        episode_id=episode_id,
        duration_seconds=duration,
        segments=segments,
        candidates=candidates,
        selected_assets=selected,
        manifest_visuals=manifest_visuals,
        provider_reports=reports,
        warnings=warnings,
        plan_entries=plan_entries,
        planning_audit=planning_audit,
    )
    _write_audit_file(plan, story_path=story_path, queries_by_segment={query.segment_id: query for query in queries})
    return plan


def _duration_seconds(manifest: dict[str, Any]) -> float:
    for section_name in ("composition", "direction", "script"):
        section = manifest.get(section_name)
        if isinstance(section, dict):
            for key in ("duration_seconds", "estimated_duration_seconds", "target_duration_seconds"):
                try:
                    value = float(section.get(key))
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    return round(value, 2)
    script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
    text = str(script.get("text") or "") if isinstance(script, dict) else ""
    word_count = len(text.split())
    if word_count:
        try:
            words_per_minute = float(os.environ.get("SYNTHPOST_WORDS_PER_MINUTE", "145"))
        except ValueError:
            words_per_minute = 145
        return round(max(30.0, word_count / max(80.0, words_per_minute) * 60), 2)
    return 30.0


def _section_segments_from_script(manifest: dict[str, Any], *, duration_seconds: float) -> list[StorySegment]:
    script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    sections = script.get("sections") if isinstance(script.get("sections"), list) else []
    sections = [section for section in sections if isinstance(section, dict) and compact_text(section.get("section_id"))]
    if not sections:
        return []

    category = compact_text(script.get("category") or raw.get("category"))
    visual_handoff = visual_handoff_for_manifest(manifest)
    planning_context = " ".join(
        [
            *visual_handoff.get("entities", []),
            *visual_handoff.get("visual_opportunities", []),
            compact_text(visual_handoff.get("why_it_matters")),
            compact_text(visual_handoff.get("synthpost_angle")),
            compact_text(raw.get("summary")),
        ]
    )
    estimates = [_positive_float(section.get("estimated_duration_seconds")) for section in sections]
    fallback_duration = duration_seconds / max(1, len(sections))
    total_estimated = sum(value or fallback_duration for value in estimates)
    scale = duration_seconds / total_estimated if total_estimated > 0 else 1.0

    result: list[StorySegment] = []
    cursor = 0.0
    seen_ids: dict[str, int] = {}
    for index, section in enumerate(sections):
        base_section_id = compact_text(section.get("section_id")) or f"section_{index + 1:02d}"
        seen_ids[base_section_id] = seen_ids.get(base_section_id, 0) + 1
        section_id = base_section_id if seen_ids[base_section_id] == 1 else f"{base_section_id}_{seen_ids[base_section_id]}"
        title = compact_text(section.get("title")) or base_section_id.replace("_", " ").title()
        estimated = (estimates[index] or fallback_duration) * scale
        start = round(cursor, 2)
        end = round(duration_seconds if index == len(sections) - 1 else min(duration_seconds, cursor + estimated), 2)
        if end <= start:
            end = round(min(duration_seconds, start + 2.0), 2)
        text_parts = [
            title,
            compact_text(section.get("narration")),
            *[compact_text(item) for item in section.get("claim_ids", []) if compact_text(item)],
            *[compact_text(item) for item in section.get("source_notes", []) if compact_text(item)],
            *_section_screen_text(section),
            planning_context,
        ]
        text = " ".join(part for part in text_parts if part)
        result.append(
            StorySegment(
                segment_id=section_id,
                title=title,
                text=text,
                start=start,
                end=end,
                keywords=keyword_phrases(text, category),
            )
        )
        cursor = end
    return result


def _positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _section_screen_text(section: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("key_points", "lower_thirds", "chyrons", "on_screen_bullets", "quote_cards", "data_callouts"):
        items = section.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str):
                values.append(compact_text(item))
            elif isinstance(item, dict):
                values.append(compact_text(item.get("text") or item.get("headline") or item.get("title")))
    return unique([value for value in values if value], limit=16)


def _target_segment_count(duration_seconds: float) -> int:
    configured = os.environ.get("SYNTHPOST_VISUAL_SEGMENTS", "").strip()
    if configured:
        try:
            return max(1, int(configured))
        except ValueError:
            pass
    try:
        seconds_per_visual = float(os.environ.get("SYNTHPOST_VISUAL_SECONDS_PER_BEAT", "7.5"))
    except ValueError:
        seconds_per_visual = 7.5
    try:
        minimum = int(os.environ.get("SYNTHPOST_VISUAL_MIN_SEGMENTS", "4"))
        maximum = int(os.environ.get("SYNTHPOST_VISUAL_MAX_SEGMENTS", "14"))
    except ValueError:
        minimum, maximum = 4, 14
    estimated = int(round(duration_seconds / max(3.0, seconds_per_visual)))
    return max(minimum, min(maximum, estimated))


def _context_graphics_enabled() -> bool:
    value = os.environ.get("SYNTHPOST_ENABLE_CONTEXT_GRAPHICS", "auto").strip().lower()
    return value not in {"0", "false", "no", "off", "disabled"}


def _dedupe(assets: list[VisualAsset]) -> list[VisualAsset]:
    seen: set[str] = set()
    result: list[VisualAsset] = []
    for asset in assets:
        key = asset.identity_key()
        if key in seen:
            continue
        seen.add(key)
        result.append(asset)
    return result


def _select_assets(
    assets: list[VisualAsset],
    *,
    segments,
    queries_by_segment,
    project_root: Path,
) -> list[VisualAsset]:
    selected: list[VisualAsset] = []
    used: set[str] = set()
    stock_providers = STOCK_PROVIDERS
    specific_providers = OFFICIAL_PROVIDERS | OPEN_ARCHIVE_PROVIDERS | {"manifest_media", "local_library"}
    for segment in segments:
        query = queries_by_segment[segment.segment_id]
        ranked = rank_assets_for_segment(assets, segment, query)
        has_specific_candidate = any(
            asset.safe_to_use
            and asset.provider in specific_providers
            and asset.asset_type not in {AssetType.GENERATED, AssetType.PLACEHOLDER}
            and asset.relevance_score >= 50
            for asset in ranked
        )
        chosen: VisualAsset | None = None
        for asset in ranked:
            if asset.asset_type in {AssetType.GENERATED, AssetType.PLACEHOLDER} or asset.provider == "screenshot_provider":
                continue
            if has_specific_candidate and asset.provider in stock_providers:
                continue
            key = asset.identity_key()
            if key in used and asset.provider != "screenshot_provider":
                continue
            if not asset_is_selectable(asset):
                continue
            if asset.rejection_reasons:
                continue
            if asset.path and not renderable_and_safe(asset, project_root=project_root):
                continue
            chosen = asset
            break
        if chosen is None:
            # Text-heavy generated context cards are disabled for the Split Main video panel.
            # Later this hook should be replaced by purpose-built graphics skills:
            # clean maps, charts, document callouts, timelines, source screenshots, etc.
            if _context_graphics_enabled():
                for asset in ranked:
                    if asset.asset_type == AssetType.GENERATED or asset.provider == "screenshot_provider":
                        chosen = asset
                        break
        if chosen:
            chosen.segment_id = segment.segment_id
            used.add(chosen.identity_key())
            selected.append(chosen)
    return selected


def _download_selected(selected: list[VisualAsset], *, story_path: Path, project_root: Path) -> list[VisualAsset]:
    destination_dir = story_path.parent / "visuals" / "downloaded"
    downloaded: list[VisualAsset] = []
    for asset in selected:
        if asset.remote_url and not asset.path:
            asset = download_asset(asset, destination_dir=destination_dir, project_root=project_root)
        downloaded.append(asset)
    return downloaded


def _fill_with_generated(
    selected: list[VisualAsset],
    generated: list[VisualAsset],
    segments,
) -> list[VisualAsset]:
    by_segment = {asset.segment_id: asset for asset in selected}
    generated_by_segment = {asset.segment_id: asset for asset in generated}
    result: list[VisualAsset] = []
    for segment in segments:
        asset = by_segment.get(segment.segment_id)
        if asset is None and segment.segment_id in generated_by_segment:
            asset = replace(
                generated_by_segment[segment.segment_id],
                fallback_reason=generated_by_segment[segment.segment_id].fallback_reason
                or "generated_context_card_no_safe_section_visual",
            )
        if asset:
            asset.segment_id = segment.segment_id
            result.append(asset)
    return result


def _reuse_real_visuals(
    selected: list[VisualAsset],
    segments,
) -> list[VisualAsset]:
    if not selected:
        return []
    by_segment = {asset.segment_id: asset for asset in selected}
    result: list[VisualAsset] = []
    for index, segment in enumerate(segments):
        existing = by_segment.get(segment.segment_id)
        if existing:
            result.append(existing)
            continue
        asset = selected[index % len(selected)]
        result.append(
            replace(
                asset,
                segment_id=segment.segment_id,
                fallback_reason=asset.fallback_reason or "reused_real_visual_no_context_graphic",
            )
        )
    return result


def _build_plan_entries(
    *,
    story_id: str,
    episode_id: str,
    segments: list[StorySegment],
    selected: list[VisualAsset],
) -> list[VisualPlanEntry]:
    entries: list[VisualPlanEntry] = []
    by_segment = {asset.segment_id: asset for asset in selected if asset.segment_id}
    for segment in segments:
        asset = by_segment.get(segment.segment_id)
        if asset is None:
            continue
        fallback_status = _fallback_status(asset)
        entries.append(
            VisualPlanEntry(
                story_id=story_id,
                episode_id=episode_id,
                section_id=segment.segment_id,
                section_title=segment.title,
                section_type=segment.segment_id,
                visual_role=_visual_role(segment, asset, fallback_status=fallback_status),
                selected_visual_candidate_id=asset.asset_id,
                media_type=asset.media_type or asset.asset_type.value,
                asset_type=asset.asset_type.value,
                asset_url=asset.asset_url or asset.remote_url or asset.path,
                path=asset.downloaded_path or asset.path,
                source_url=asset.source_url,
                source_domain=asset.source_domain,
                rights_category=asset.rights_category,
                attribution=asset.attribution,
                attribution_text=asset.attribution_text,
                relevance_score=asset.relevance_score,
                relevance_reason=asset.relevance_reason,
                start=segment.start,
                end=segment.end,
                fallback_status=fallback_status,
                fallback_reason=asset.fallback_reason,
                needs_manual_review=asset.needs_manual_review,
                rejection_reasons=list(asset.rejection_reasons),
                selection_status=asset.selection_status,
            )
        )
    return entries


def _fallback_status(asset: VisualAsset) -> str:
    if asset.provider == "screenshot_provider" or asset.asset_type in {AssetType.GENERATED, AssetType.PLACEHOLDER}:
        return "generated_context_card"
    if asset.fallback_reason:
        if "reused" in asset.fallback_reason:
            return "reused_real_visual"
        return "fallback_visual"
    return "none"


def _visual_role(segment: StorySegment, asset: VisualAsset, *, fallback_status: str) -> str:
    if fallback_status == "generated_context_card":
        return "generated_context_card"
    if fallback_status == "reused_real_visual":
        return "fallback_visual"
    if asset.asset_type == AssetType.DOCUMENT or asset.media_type == "document":
        return "document_visual"
    if asset.asset_type == AssetType.MAP or asset.media_type == "map":
        return "location_visual"
    if asset.asset_type == AssetType.CHART or asset.media_type == "chart":
        return "data_callout"
    title = f"{segment.segment_id} {segment.title} {segment.text}".lower()
    if "quote" in title or "said" in title:
        return "quote_card"
    if segment.segment_id in {"cold_open", "intro"}:
        return "hero_visual"
    if segment.segment_id in {"background_context", "why_it_matters"}:
        return "context_visual"
    if segment.segment_id == "main_developments":
        return "evidence_visual"
    if segment.segment_id in {"stakes_consequences", "opposing_views_uncertainty"}:
        return "data_callout"
    if segment.segment_id in {"conclusion", "outro_next_story"}:
        return "fallback_visual"
    return "context_visual"


def _build_planning_audit(
    *,
    segments: list[StorySegment],
    selected: list[VisualAsset],
    entries: list[VisualPlanEntry],
    candidates: list[VisualAsset],
    queries_by_segment: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    reuse_counts: dict[str, int] = {}
    for asset in selected:
        reuse_counts[asset.asset_id] = reuse_counts.get(asset.asset_id, 0) + 1
    entry_by_section = {entry.section_id: entry for entry in entries}
    missing = [
        f"{segment.segment_id}: no renderable rights-safe visual was assigned"
        for segment in segments
        if segment.segment_id not in entry_by_section
    ]
    manual_review_warnings = [
        {
            "section_id": entry.section_id,
            "candidate_id": entry.selected_visual_candidate_id,
            "rights_category": entry.rights_category,
        }
        for entry in entries
        if entry.needs_manual_review
    ]
    section_rejections: dict[str, list[dict[str, Any]]] = {}
    for segment in segments:
        query = queries_by_segment.get(segment.segment_id)
        if query is None:
            continue
        rejected: list[dict[str, Any]] = []
        for asset in rank_assets_for_segment(candidates, segment, query):
            reasons = list(asset.rejection_reasons)
            if not asset_is_selectable(asset):
                reasons.extend(_rights_rejection_reasons(asset))
            if asset.path and not renderable_and_safe(asset, project_root=project_root):
                reasons.append("not_renderable")
            reasons = _dedupe_reasons(reasons)
            if reasons:
                rejected.append(
                    {
                        "candidate_id": asset.asset_id,
                        "relevance_score": asset.relevance_score,
                        "rights_category": asset.rights_category,
                        "rejection_reasons": reasons,
                    }
                )
            if len(rejected) >= 5:
                break
        if rejected:
            section_rejections[segment.segment_id] = rejected
    return {
        "reuse_counts": reuse_counts,
        "fallback_count": sum(1 for entry in entries if entry.fallback_status != "none"),
        "fallback_sections": [
            {
                "section_id": entry.section_id,
                "candidate_id": entry.selected_visual_candidate_id,
                "fallback_status": entry.fallback_status,
                "fallback_reason": entry.fallback_reason,
            }
            for entry in entries
            if entry.fallback_status != "none"
        ],
        "manual_review_warnings": manual_review_warnings,
        "missing_visual_coverage_warnings": missing,
        "section_rejections": section_rejections,
        "reuse_limit_warnings": [
            f"{asset_id}: reused {count} times"
            for asset_id, count in reuse_counts.items()
            if count > 2
        ],
    }


def _mark_selected_counts(reports: list[ProviderReport], selected: list[VisualAsset]) -> None:
    counts: dict[str, int] = {}
    for asset in selected:
        counts[asset.provider] = counts.get(asset.provider, 0) + 1
    for report in reports:
        if report.provider == "pexels_pixabay_optional":
            report.selected_count = counts.get("pexels", 0) + counts.get("pixabay", 0)
        else:
            report.selected_count = counts.get(report.provider, 0)


def _mark_selection_statuses(selected: list[VisualAsset]) -> None:
    for asset in selected:
        asset.selection_status = SelectionStatus.SELECTED.value
        asset.rejection_reasons = []


def _candidate_audit_records(
    plan: VisualPlan,
    *,
    queries_by_segment: dict[str, Any],
    project_root: Path,
) -> list[dict[str, Any]]:
    selected_keys = {asset.identity_key() for asset in plan.selected_assets}
    records: list[dict[str, Any]] = []
    for asset in plan.candidates:
        best = _best_ranked_candidate(asset, plan=plan, queries_by_segment=queries_by_segment)
        reasons = list(best.rejection_reasons)
        if not asset_is_selectable(best):
            reasons.extend(_rights_rejection_reasons(best))
        if best.path and not renderable_and_safe(best, project_root=project_root):
            reasons.append("not_renderable")
        if best.identity_key() in selected_keys:
            best.selection_status = SelectionStatus.SELECTED.value
            best.rejection_reasons = []
        elif reasons:
            best.selection_status = SelectionStatus.REJECTED.value
            best.rejection_reasons = _dedupe_reasons(reasons)
        else:
            best.selection_status = SelectionStatus.CANDIDATE.value
            best.rejection_reasons = []
        records.append(best.to_record())
    return sorted(
        records,
        key=lambda item: (
            0 if item.get("selection_status") == SelectionStatus.SELECTED.value else 1,
            -float(item.get("relevance_score") or 0),
            str(item.get("id") or ""),
        ),
    )


def _best_ranked_candidate(
    asset: VisualAsset,
    *,
    plan: VisualPlan,
    queries_by_segment: dict[str, Any],
) -> VisualAsset:
    ranked_versions: list[VisualAsset] = []
    for segment in plan.segments:
        query = queries_by_segment.get(segment.segment_id)
        if not query:
            continue
        ranked_versions.extend(rank_assets_for_segment([asset], segment, query))
    if not ranked_versions:
        return asset
    return max(ranked_versions, key=lambda item: item.relevance_score)


def _rights_rejection_reasons(asset: VisualAsset) -> list[str]:
    reasons: list[str] = []
    if not asset.safe_to_use:
        reasons.append("not_marked_safe_to_use")
    if asset.rights_tier == "red":
        reasons.append("rights_tier_red")
    if asset.rights_category == "unknown_or_rejected":
        reasons.append("unknown_or_rejected_rights")
    if asset.needs_manual_review:
        reasons.append("manual_review_required")
    return _dedupe_reasons(reasons)


def _dedupe_reasons(reasons: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for reason in reasons:
        if not reason or reason in seen:
            continue
        seen.add(reason)
        result.append(reason)
    return result


def _write_audit_file(plan: VisualPlan, *, story_path: Path, queries_by_segment: dict[str, Any]) -> None:
    audit_path = story_path.parent / "visuals" / "visuals_audit.json"
    candidate_audit_path = story_path.parent / "visuals" / "visual_candidates.json"
    visual_plan_path = story_path.parent / "visuals" / "visual_plan.json"
    project_root = project_root_from_story(story_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    plan.audit_paths = {
        "visuals_audit": project_relative(audit_path, project_root),
        "visual_candidates": project_relative(candidate_audit_path, project_root),
        "visual_plan": project_relative(visual_plan_path, project_root),
    }
    candidate_records = _candidate_audit_records(
        plan,
        queries_by_segment=queries_by_segment,
        project_root=project_root,
    )
    payload = {
        "story_id": plan.story_id,
        "episode_id": plan.episode_id,
        "summary": plan.summary(),
        "selected_assets": plan.selected_records(),
        "visual_plan": plan.plan_records(),
        "planning_audit": plan.planning_audit,
        "candidates": candidate_records,
        "candidate_audit_path": project_relative(candidate_audit_path, project_root),
        "visual_plan_path": project_relative(visual_plan_path, project_root),
    }
    candidate_payload = {
        "story_id": plan.story_id,
        "episode_id": plan.episode_id,
        "candidate_count": len(candidate_records),
        "selected_count": len(plan.selected_assets),
        "warnings": plan.warnings,
        "provider_reports": [report.to_record() for report in plan.provider_reports],
        "chosen_visuals": plan.selected_records(),
        "visual_plan_path": project_relative(visual_plan_path, project_root),
        "candidates": candidate_records,
        "manual_review_flags": [
            record
            for record in candidate_records
            if record.get("needs_manual_review") or record.get("manual_review_status") in {"required", "rejected"}
        ],
    }
    visual_plan_payload = {
        "story_id": plan.story_id,
        "episode_id": plan.episode_id,
        "duration_seconds": plan.duration_seconds,
        "section_count": len(plan.plan_entries),
        "sections": plan.plan_records(),
        "chosen_visuals": plan.selected_records(),
        "audit": plan.planning_audit,
        "provider_reports": [report.to_record() for report in plan.provider_reports],
        "warnings": plan.warnings,
        "visual_candidates_path": project_relative(candidate_audit_path, project_root),
        "visuals_audit_path": project_relative(audit_path, project_root),
    }
    audit_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    candidate_audit_path.write_text(json.dumps(candidate_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    visual_plan_path.write_text(json.dumps(visual_plan_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
