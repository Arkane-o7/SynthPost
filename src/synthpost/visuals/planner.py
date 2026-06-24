from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from .downloader import download_asset, project_relative
from .manifest import visual_to_manifest
from .models import AssetType, ProviderReport, SelectionStatus, VisualAsset, VisualPlan, VisualProvider
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
from .query_builder import build_story_segments, build_visual_queries
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
    segments = build_story_segments(manifest, target_count=target_count)
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
    )
    _write_audit_file(plan, story_path=story_path, queries_by_segment={query.segment_id: query for query in queries})
    return plan


def _duration_seconds(manifest: dict[str, Any]) -> float:
    for section_name in ("composition", "direction"):
        section = manifest.get(section_name)
        if isinstance(section, dict):
            for key in ("duration_seconds", "estimated_duration_seconds"):
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
        asset = by_segment.get(segment.segment_id) or generated_by_segment.get(segment.segment_id)
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
    project_root = project_root_from_story(story_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
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
        "candidates": candidate_records,
        "candidate_audit_path": project_relative(candidate_audit_path, project_root),
    }
    candidate_payload = {
        "story_id": plan.story_id,
        "episode_id": plan.episode_id,
        "candidate_count": len(candidate_records),
        "selected_count": len(plan.selected_assets),
        "warnings": plan.warnings,
        "provider_reports": [report.to_record() for report in plan.provider_reports],
        "chosen_visuals": plan.selected_records(),
        "candidates": candidate_records,
        "manual_review_flags": [
            record
            for record in candidate_records
            if record.get("needs_manual_review") or record.get("manual_review_status") in {"required", "rejected"}
        ],
    }
    audit_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    candidate_audit_path.write_text(json.dumps(candidate_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
