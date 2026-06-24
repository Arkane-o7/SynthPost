from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ..provenance import artifact_record, record_story_artifact
from ..storage import read_manifest, write_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from synthpost.visuals import build_visual_plan  # noqa: E402
from synthpost.visuals.compositor_bridge import apply_compositor_bridge  # noqa: E402

REQUIRED_VISUAL_METADATA = {
    "asset_type",
    "source_name",
    "license",
    "usage_note",
    "downloaded_path",
    "relevance_score",
    "safe_to_use",
    "rights_tier",
    "rights_confidence",
    "usage_basis",
    "source_authority",
    "content_role",
    "media_type",
    "risk_level",
    "manual_review_status",
    "provider_type",
    "source_domain",
    "asset_url",
    "rights_category",
    "needs_manual_review",
    "selection_status",
}


def _has_visual_metadata(visuals: Any) -> bool:
    if not isinstance(visuals, list) or not visuals:
        return False
    return all(isinstance(visual, dict) and REQUIRED_VISUAL_METADATA.issubset(visual.keys()) for visual in visuals)


def run(
    story_json_path: str | Path,
    *,
    force: bool = False,
    test_mode: bool = False,
    render_profile: str = "production",
) -> list[dict[str, Any]]:
    manifest = read_manifest(story_json_path)
    existing = manifest.get("visuals")
    if existing and not force and _has_visual_metadata(existing):
        print("[visuals] Reusing planned visuals from manifest.")
        manifest = apply_compositor_bridge(manifest, story_json_path)
        write_manifest(story_json_path, manifest)
        for index, visual in enumerate(existing, start=1):
            if isinstance(visual, dict) and visual.get("path"):
                record_story_artifact(
                    story_json_path,
                    f"visual_{index:03d}",
                    artifact_record(
                        path=visual["path"],
                        stage="visuals",
                        input_paths=[story_json_path],
                        provider=visual.get("provider"),
                        fresh=False,
                        reused=True,
                        test_mode=test_mode,
                        render_profile=render_profile,
                        metadata={
                            "candidate_id": visual.get("asset_id") or visual.get("candidate_id"),
                            "rights_category": visual.get("rights_category"),
                            "attribution_text": visual.get("attribution_text"),
                            "source_url": visual.get("source_url"),
                            "source_domain": visual.get("source_domain"),
                        },
                    ),
                )
        return existing

    plan = build_visual_plan(manifest, story_json_path)
    manifest["visuals"] = plan.manifest_visuals
    manifest["visual_assets"] = plan.selected_records()
    manifest["visual_plan"] = plan.summary()
    manifest = apply_compositor_bridge(manifest, story_json_path)
    write_manifest(story_json_path, manifest)

    provider_counts = ", ".join(
        f"{report.provider}:{report.selected_count}/{report.candidate_count}" for report in plan.provider_reports
    )
    print(f"[visuals] Planned {len(plan.manifest_visuals)} timed visuals ({provider_counts}).")
    for index, visual in enumerate(plan.manifest_visuals, start=1):
        if isinstance(visual, dict) and visual.get("path"):
            record_story_artifact(
                story_json_path,
                f"visual_{index:03d}",
                artifact_record(
                    path=visual["path"],
                    stage="visuals",
                    input_paths=[story_json_path],
                    provider=visual.get("provider"),
                    fresh=True,
                    reused=False,
                    test_mode=test_mode,
                    render_profile=render_profile,
                    metadata={
                        "asset_type": visual.get("asset_type"),
                        "candidate_id": visual.get("asset_id") or visual.get("candidate_id"),
                        "rights_category": visual.get("rights_category"),
                        "attribution_text": visual.get("attribution_text"),
                        "source_url": visual.get("source_url"),
                        "source_domain": visual.get("source_domain"),
                    },
                ),
            )
    return plan.manifest_visuals
