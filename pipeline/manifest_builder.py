from __future__ import annotations

from typing import Any

from pipeline.artifacts import (
    materialize_story_artifacts,
    story_manifest_path,
    write_json,
)
from pipeline.models import (
    ArtifactRecord,
    ReviewStatus,
    RightsTier,
    TimelinePlan,
    TimelineStatus,
)
from pipeline.provenance import file_sha256, now_iso
from pipeline.storage import project_relative, resolve_project_path
from pipeline.timeline.validation import assert_timeline_valid


def remotion_visual_from_segment(segment) -> dict[str, Any] | None:
    visual = segment.visual
    if not visual.asset_id or not visual.path:
        return None
    return {
        "asset_id": visual.asset_id,
        "path": visual.path,
        "media_type": visual.media_type.value
        if hasattr(visual.media_type, "value")
        else visual.media_type,
        "content_role": visual.content_role.value
        if hasattr(visual.content_role, "value")
        else visual.content_role,
        "source": visual.source,
        "source_url": visual.source_url,
        "rights_tier": visual.rights_tier.value
        if hasattr(visual.rights_tier, "value")
        else visual.rights_tier,
        "review_status": visual.review_status.value
        if hasattr(visual.review_status, "value")
        else visual.review_status,
        "audio_mode": visual.audio_mode,
        "trim_start": visual.trim_start,
        "trim_end": visual.trim_end,
        "attribution_text": visual.attribution_text,
    }


def renderer_timeline(plan: TimelinePlan) -> dict[str, Any]:
    return {
        "timeline_id": plan.timeline_id,
        "version": plan.version,
        "status": plan.status.value if hasattr(plan.status, "value") else plan.status,
        "audio_plan": plan.audio_plan.model_dump(mode="json")
        if plan.audio_plan
        else None,
        "segments": [segment.model_dump(mode="json") for segment in plan.segments],
    }


def build_story_manifest(
    repository,
    story_id: str,
    *,
    render_profile: str | None = None,
    test_mode: bool = False,
) -> dict[str, Any]:
    episode = repository.episode_for_story(story_id)
    candidate = repository.candidate_for_story(story_id)
    script = repository.latest_script(story_id, approved=True)
    if not script:
        raise ValueError(
            "An approved script is required before building the renderer manifest"
        )
    timeline = repository.latest_timeline(story_id, approved=True)
    if not timeline:
        raise ValueError(
            "An approved timeline is required before building the renderer manifest"
        )
    assert_timeline_valid(timeline, require_approved=True, check_media_exists=True)
    artifacts = materialize_story_artifacts(repository, story_id)
    story_path = story_manifest_path(episode.episode_id, story_id)
    output_path = story_path.with_name(
        "composited_TEST_MODE.mp4" if test_mode else "composited.mp4"
    )
    preview_path = story_path.with_name("preview.png")
    approved_visuals = [
        visual
        for visual in repository.list_visuals(story_id)
        if visual.review_status in {ReviewStatus.approved, ReviewStatus.manual_approved}
        and visual.rights_tier != RightsTier.red
    ]
    manifest: dict[str, Any] = {
        "contract_version": "synthpost.v2.renderer_manifest",
        "story_id": story_id,
        "episode_id": episode.episode_id,
        "script": {
            "script_id": script.script_id,
            "headline": script.headline,
            "dek": script.dek,
            "category": script.category,
            "text": script.text,
            "sections": [
                section.model_dump(mode="json") for section in script.sections
            ],
        },
        "raw": {
            "headline_source": candidate.title,
            "category": candidate.category,
            "source_name": candidate.source_name,
            "published_at": candidate.published_at,
            "canonical_url": candidate.canonical_url,
        },
        "composition": {
            "template": "timeline_story",
            "output_path": project_relative(output_path),
            "preview_path": project_relative(preview_path),
        },
        "approved_timeline": renderer_timeline(timeline),
        "compositor_visuals": [
            {
                "asset_id": visual.asset_id,
                "path": visual.download_path,
                "media_type": visual.media_type.value,
                "content_role": visual.content_role.value,
                "source_url": visual.source_url,
                "provider": visual.provider,
                "license": visual.license,
                "attribution_text": visual.attribution_text,
                "rights_category": visual.rights_tier.value,
                "manual_review_flag": visual.manual_review_flag,
                "motion": visual.motion,
            }
            for visual in approved_visuals
            if visual.download_path
        ],
        "points": [
            {"text": section.text[:110], "start": max(0, index * 4)}
            for index, section in enumerate(script.sections[:4])
        ],
        "runtime": {
            "render_profile": render_profile or episode.render_profile,
            "test_mode": test_mode,
            "mode": "TEST_MODE" if test_mode else "production",
        },
        "provenance": {
            "created_at": now_iso(),
            "source_artifacts": artifacts,
        },
    }
    write_json(story_path, manifest)
    repository.record_artifact(
        ArtifactRecord(
            artifact_type="renderer_manifest",
            path=project_relative(story_path),
            content_hash=file_sha256(story_path),
            producer="pipeline.manifest_builder",
            inputs=list(artifacts.values()),
            render_profile=render_profile or episode.render_profile,
            test_mode=test_mode,
            metadata={"story_id": story_id, "episode_id": episode.episode_id},
        ),
        story_id=story_id,
        episode_id=episode.episode_id,
    )
    return manifest
