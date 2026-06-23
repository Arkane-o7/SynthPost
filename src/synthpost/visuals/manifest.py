from __future__ import annotations

from typing import Any

from .models import VisualAsset


def visual_to_manifest(asset: VisualAsset, *, start: float, end: float, fit: str = "cover") -> dict[str, Any]:
    source_label = asset.source_name or asset.title or "SYNTHPOST"
    if asset.provider == "local_library" and source_label == "Local Library":
        source_label = asset.title
    record = {
        "path": asset.path or asset.remote_url or "",
        "start": round(start, 2),
        "end": round(end, 2),
        "fit": fit,
        "sourceLabel": source_label.upper()[:42],
        "asset_id": asset.asset_id,
        "asset_type": asset.asset_type.value,
        "source_url": asset.source_url,
        "source_name": asset.source_name,
        "license": asset.license,
        "usage_note": asset.usage_note,
        "attribution": asset.attribution,
        "downloaded_path": asset.downloaded_path or asset.path,
        "story_id": asset.story_id,
        "segment_id": asset.segment_id,
        "relevance_score": asset.relevance_score,
        "safe_to_use": asset.safe_to_use,
        "fallback_reason": asset.fallback_reason,
        "provider": asset.provider,
        "title": asset.title,
        "visual_role": asset.extra.get("visual_role"),
        "rights_tier": asset.rights_tier,
        "rights_confidence": asset.rights_confidence,
        "usage_basis": asset.usage_basis,
        "attribution_required": asset.attribution_required,
        "attribution_text": asset.attribution_text,
        "source_authority": asset.source_authority,
        "content_role": asset.content_role,
        "media_type": asset.media_type,
        "risk_level": asset.risk_level,
        "manual_review_status": asset.manual_review_status,
        "motion": asset.motion,
    }
    return {key: value for key, value in record.items() if value not in (None, "", [], {})}
