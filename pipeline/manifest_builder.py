from __future__ import annotations

from datetime import datetime
from typing import Any

from pipeline import config
from pipeline.artifacts import (
    materialize_story_artifacts,
    story_manifest_path,
    write_json,
)
from pipeline.models import (
    ArtifactRecord,
    AudioMode,
    ContentRole,
    MediaType,
    ReviewStatus,
    ScriptStatus,
    TimelinePlan,
    TimelineStatus,
)
from pipeline.narration.service import load_narration_artifact
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
        "has_audio": visual.has_audio,
        "attribution_text": visual.attribution_text,
        "content_cleanliness_status": visual.content_cleanliness_status,
        "approval_blockers": visual.approval_blockers,
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


def timeline_narration_text(plan: TimelinePlan) -> str:
    """Return only words assigned to the continuous anchor performance."""

    return "\n\n".join(
        segment.script_text.strip()
        for segment in plan.segments
        if segment.audio.mode != AudioMode.source and segment.script_text.strip()
    )


def hydrate_timeline_visuals(
    plan: TimelinePlan, visuals: list[Any]
) -> TimelinePlan:
    """Refresh mutable asset metadata while preserving approved edit decisions.

    Timeline structure and asset selection remain immutable after approval, but
    an editor may still correct attribution or rights metadata on that selected
    asset. Renderer manifests must use the current asset record rather than the
    stale snapshot embedded when the timeline was first approved.
    """

    hydrated = plan.model_copy(deep=True)
    by_id = {visual.asset_id: visual for visual in visuals}
    source_audio_enabled = config.source_audio_inserts_enabled()

    def use_narration_over_visual(segment) -> None:
        """Treat selected video as B-roll unless an insert edit exists.

        Older approved timelines inferred source audio from the mere presence
        of an audio stream. That muted the continuous avatar render while its
        script clock kept advancing. The current timeline model has no explicit
        insert-edit contract, so hydration safely upgrades those legacy regions
        to narrated B-roll as well.
        """

        segment.visual.audio_mode = "muted"
        segment.anchor.speaking = True
        segment.audio.mode = AudioMode.narration
        segment.audio.narration_volume = 1.0
        segment.audio.source_volume = 0.0
        segment.audio.ducking = False

    def use_fallback(segment) -> None:
        playback_mode = str(segment.overlays.data.get("playback_mode") or "")
        source_clip = segment.overlays.data.get("source_clip")
        if playback_mode in {
            "source_clip",
            "source_clip_muted_broll",
        } and isinstance(source_clip, dict):
            fallback_narration = str(
                source_clip.get("fallback_narration") or ""
            ).strip()
            if fallback_narration:
                segment.script_text = fallback_narration
            segment.overlays.data["playback_mode"] = "source_clip_fallback"
        segment.visual.asset_id = None
        segment.visual.path = None
        segment.visual.media_type = MediaType.fallback
        segment.visual.content_role = ContentRole.fallback
        segment.visual.source = "SynthPost"
        segment.visual.source_url = None
        segment.visual.attribution_text = ""
        segment.visual.review_status = ReviewStatus.approved
        segment.visual.audio_mode = "muted"
        segment.visual.has_audio = False
        if segment.template.template_id not in {
            "fullscreen_anchor",
            "fallback_anchor",
        }:
            segment.template.template_id = "fallback_anchor"
        segment.anchor.visible = True
        segment.anchor.speaking = True
        segment.audio.mode = AudioMode.narration
        segment.audio.narration_volume = 1.0
        segment.audio.source_volume = 0.0
        segment.overlays.attribution = ""
        segment.overlays.document_source = ""

    for segment in hydrated.segments:
        playback_mode = str(segment.overlays.data.get("playback_mode") or "")
        source_clip = segment.overlays.data.get("source_clip")
        if (
            playback_mode == "source_clip"
            and not source_audio_enabled
            and isinstance(source_clip, dict)
        ):
            fallback_narration = str(
                source_clip.get("fallback_narration") or ""
            ).strip()
            if fallback_narration:
                segment.script_text = fallback_narration
            segment.overlays.data["playback_mode"] = "source_clip_muted_broll"
            segment.overlays.data["source_audio_policy"] = "disabled_unverified"
            use_narration_over_visual(segment)
        asset_id = segment.visual.asset_id
        current = by_id.get(asset_id) if asset_id else None
        if current is None:
            if asset_id:
                use_fallback(segment)
            continue
        if (
            current.content_role == ContentRole.fallback
            or current.media_type == MediaType.fallback
            or current.provider
            in {"generated_visual_card", "synthpost_anchor_fallback"}
        ):
            use_fallback(segment)
            continue
        if (
            current.review_status in {ReviewStatus.rejected, ReviewStatus.blocked}
            or not current.download_path
            or not resolve_project_path(current.download_path).is_file()
        ):
            use_fallback(segment)
            continue
        segment.visual.path = current.download_path
        segment.visual.media_type = current.media_type
        segment.visual.content_role = current.content_role
        segment.visual.source = current.provider
        segment.visual.source_url = current.source_url
        segment.visual.rights_tier = current.rights_tier
        segment.visual.review_status = current.review_status
        segment.visual.trim_start = current.trim_start
        segment.visual.trim_end = current.trim_end
        if current.has_audio is not None:
            segment.visual.has_audio = current.has_audio
        segment.visual.attribution_text = current.attribution_text
        segment.visual.content_cleanliness_status = current.content_cleanliness_status
        segment.visual.approval_blockers = list(current.approval_blockers)
        segment.overlays.attribution = current.attribution_text or ""
        if segment.overlays.document_source:
            segment.overlays.document_source = current.attribution_text or ""
        explicit_source_clip = (
            segment.overlays.data.get("playback_mode") == "source_clip"
        )
        if (
            segment.template.template_id == "fullscreen_news_visual"
            and current.media_type == MediaType.video
            and not explicit_source_clip
            and (
                segment.audio.mode in {AudioMode.source, AudioMode.mixed}
                or segment.visual.audio_mode in {"original", "mixed"}
            )
        ):
            use_narration_over_visual(segment)

    if hydrated.audio_plan:
        segment_by_id = {
            segment.segment_id: segment for segment in hydrated.segments
        }
        for region in hydrated.audio_plan.regions:
            segment = segment_by_id.get(region.segment_id)
            if not segment:
                continue
            region.mode = segment.audio.mode
            region.narration_volume = segment.audio.narration_volume
            region.source_volume = segment.audio.source_volume
            region.source_path = (
                segment.visual.path
                if segment.audio.mode in {AudioMode.source, AudioMode.mixed}
                else None
            )
    return hydrated


def build_story_manifest(
    repository,
    story_id: str,
    *,
    render_profile: str | None = None,
    test_mode: bool = False,
) -> dict[str, Any]:
    episode = repository.episode_for_story(story_id)
    candidate = repository.candidate_for_story(story_id)
    script = repository.latest_script(story_id)
    if not script or script.status != ScriptStatus.approved:
        raise ValueError(
            "The latest script revision must be approved before building the "
            "renderer manifest"
        )
    timeline = repository.latest_timeline(story_id)
    if not timeline or timeline.status != TimelineStatus.approved:
        raise ValueError(
            "The latest timeline revision must be approved before building the "
            "renderer manifest"
        )
    try:
        script_created_at = datetime.fromisoformat(
            script.created_at.replace("Z", "+00:00")
        )
        timeline_created_at = datetime.fromisoformat(
            timeline.created_at.replace("Z", "+00:00")
        )
    except ValueError:
        # Retain compatibility with legacy records whose timestamps were not
        # normalized. Current records always use ISO-8601 UTC timestamps.
        script_created_at = timeline_created_at = None
    if (
        script_created_at is not None
        and timeline_created_at is not None
        and timeline_created_at < script_created_at
    ):
        raise ValueError(
            "The approved timeline was invalidated by a newer production revision; "
            "generate and approve the current timeline before rendering"
        )
    visuals = repository.list_visuals(story_id)
    narration = load_narration_artifact(repository, story_id, require_current=True)
    assert narration is not None
    timeline = hydrate_timeline_visuals(timeline, visuals)
    assert_timeline_valid(timeline, require_approved=True, check_media_exists=True)
    narration_text = timeline_narration_text(timeline)
    if not narration_text:
        raise ValueError("Approved timeline contains no anchor narration")
    canonical_text = " ".join(beat.text.strip() for beat in narration.beats)
    narration_matches = " ".join(narration_text.split()) == " ".join(
        canonical_text.split()
    )
    if not narration_matches and not config.source_audio_inserts_enabled():
        raise ValueError(
            "The approved timeline narration does not match the canonical Kokoro "
            "audio. Regenerate and approve the timeline before rendering."
        )
    artifacts = materialize_story_artifacts(repository, story_id)
    story_path = story_manifest_path(episode.episode_id, story_id)
    output_path = story_path.with_name(
        "composited_TEST_MODE.mp4" if test_mode else "composited.mp4"
    )
    preview_path = story_path.with_name("preview.png")
    selected_asset_ids = {
        segment.visual.asset_id
        for segment in timeline.segments
        if segment.visual.asset_id and segment.visual.path
    }
    renderer_visuals = [
        visual
        for visual in visuals
        if visual.asset_id in selected_asset_ids
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
            "text": narration_text,
            "editorial_text": script.text,
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
                "has_audio": visual.has_audio,
            }
            for visual in renderer_visuals
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
    if narration_matches:
        manifest["narration"] = narration.model_dump(mode="json")
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
