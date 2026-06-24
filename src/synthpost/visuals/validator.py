from __future__ import annotations

from pathlib import Path

from .models import VisualAsset

RENDERABLE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".svg", ".mp4", ".mov", ".webm", ".mkv"}


def path_exists(path: str, project_root: Path) -> bool:
    if not path:
        return False
    value = Path(path)
    candidates = [
        value if value.is_absolute() else project_root / value,
        project_root / "compositor" / "remotion_renderer" / "public" / path,
    ]
    return any(candidate.exists() for candidate in candidates)


def validate_asset(asset: VisualAsset, *, project_root: Path) -> list[str]:
    warnings: list[str] = []
    if not asset.safe_to_use:
        warnings.append(f"{asset.asset_id}: not marked safe_to_use")
    if not asset.path and not asset.remote_url:
        warnings.append(f"{asset.asset_id}: no local path or remote URL")
    if asset.path and not path_exists(asset.path, project_root):
        warnings.append(f"{asset.asset_id}: path does not exist: {asset.path}")
    if asset.path and Path(asset.path).suffix.lower() not in RENDERABLE_EXTENSIONS:
        warnings.append(f"{asset.asset_id}: path is not directly renderable by Remotion: {asset.path}")
    if not asset.license and not asset.usage_note:
        warnings.append(f"{asset.asset_id}: missing license or usage note")
    if asset.attribution_required and not asset.attribution_text:
        warnings.append(f"{asset.asset_id}: attribution is required but attribution_text is missing")
    if asset.rights_tier not in {"green", "yellow", "red"}:
        warnings.append(f"{asset.asset_id}: invalid rights_tier: {asset.rights_tier}")
    if asset.rights_category == "unknown_or_rejected":
        warnings.append(f"{asset.asset_id}: unknown or rejected rights category")
    if asset.needs_manual_review and asset.manual_review_status not in {"approved", "not_required"}:
        warnings.append(f"{asset.asset_id}: manual review is required before rendering")
    if asset.media_type is None:
        warnings.append(f"{asset.asset_id}: missing media_type")
    if not asset.source_url and asset.provider not in {"screenshot_provider", "local_library"}:
        warnings.append(f"{asset.asset_id}: missing source URL")
    return warnings


def renderable_and_safe(asset: VisualAsset, *, project_root: Path) -> bool:
    if not asset.safe_to_use:
        return False
    if asset.path:
        return path_exists(asset.path, project_root) and Path(asset.path).suffix.lower() in RENDERABLE_EXTENSIONS
    return bool(asset.remote_url)
