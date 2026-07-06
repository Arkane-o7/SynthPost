from __future__ import annotations

from pipeline.models import (
    ApprovalStatus,
    AudioMode,
    AudioPlan,
    AudioRegion,
    ContentRole,
    MediaType,
    ReviewStatus,
    RightsTier,
    SegmentAnchor,
    SegmentAudio,
    SegmentOverlays,
    SegmentTemplate,
    SegmentVisual,
    StoryWorkflowState,
    TimelinePlan,
    TimelineSegment,
    TimelineStatus,
    VisualCandidate,
)
from pipeline.timeline.validation import validate_timeline


def approved_visuals_by_section(
    visuals: list[VisualCandidate],
) -> dict[str, VisualCandidate]:
    result: dict[str, VisualCandidate] = {}
    for visual in visuals:
        if visual.review_status not in {
            ReviewStatus.approved,
            ReviewStatus.manual_approved,
        }:
            continue
        if visual.rights_tier == RightsTier.red:
            continue
        if (
            visual.rights_tier == RightsTier.yellow
            and visual.review_status != ReviewStatus.manual_approved
        ):
            continue
        for section_id in visual.section_ids:
            result.setdefault(section_id, visual)
    return result


def choose_template(
    section_type: str, visual: VisualCandidate | None, index: int
) -> str:
    if index == 0 and visual is None:
        return "fullscreen_anchor"
    if visual:
        if (
            visual.content_role == ContentRole.primary_footage
            and visual.media_type == MediaType.video
        ):
            return "fullscreen_news_visual"
        # Non-quote explainer/card templates are currently blacklisted for
        # production. Keep approved documents, charts, maps, and context media in
        # the retained split broadcast shell until those cards are redesigned.
        return "split_anchor_visual"
    # Default to the retained broadcast anchor look. The newer card/explainer
    # templates should be explicit choices, not automatic replacements for the
    # original SynthPost template language.
    return "fallback_anchor" if index else "fullscreen_anchor"


def segment_visual_from_candidate(visual: VisualCandidate | None) -> SegmentVisual:
    if not visual:
        return SegmentVisual(
            media_type=MediaType.fallback,
            content_role=ContentRole.fallback,
            rights_tier=RightsTier.green,
            review_status=ReviewStatus.approved,
            source="SynthPost",
            attribution_text="",
        )
    return SegmentVisual(
        asset_id=visual.asset_id,
        path=visual.download_path,
        media_type=visual.media_type,
        content_role=visual.content_role,
        source=visual.provider,
        source_url=visual.source_url,
        rights_tier=visual.rights_tier,
        review_status=visual.review_status,
        audio_mode="muted",
        trim_start=visual.trim_start,
        trim_end=visual.trim_end,
        attribution_text=visual.attribution_text,
    )


def build_audio_plan(story_id: str, segments: list[TimelineSegment]) -> AudioPlan:
    regions: list[AudioRegion] = []
    for segment in segments:
        source_path = (
            segment.visual.path
            if segment.audio.mode in {AudioMode.source, AudioMode.mixed}
            else None
        )
        regions.append(
            AudioRegion(
                segment_id=segment.segment_id,
                start_time=segment.start_time,
                end_time=segment.end_time,
                mode=segment.audio.mode,
                narration_path=None,
                source_path=source_path,
                narration_volume=segment.audio.narration_volume,
                source_volume=segment.audio.source_volume,
            )
        )
    duration = max((segment.end_time for segment in segments), default=0.0)
    return AudioPlan(
        story_id=story_id,
        duration_seconds=round(duration, 3),
        regions=regions,
        strategy="timeline_aligned_avatar",
        warnings=[
            "MVP uses a single timeline-aligned avatar render; full source-audio pause synthesis is planned in the audio hardening phase."
        ],
    )


def generate_timeline(repository, story_id: str) -> TimelinePlan:
    script = repository.latest_script(
        story_id, approved=True
    ) or repository.latest_script(story_id)
    if not script:
        raise ValueError(f"No script exists for story: {story_id}")
    visuals = repository.list_visuals(story_id)
    by_section = approved_visuals_by_section(visuals)
    start = 0.0
    segments: list[TimelineSegment] = []
    for index, section in enumerate(script.sections):
        duration = max(4.0, section.estimated_duration_seconds or 5.0)
        visual = by_section.get(section.section_id)
        template_id = choose_template(section.section_type, visual, index)
        audio_mode = (
            AudioMode.source
            if template_id == "fullscreen_news_visual"
            and visual
            and visual.media_type == MediaType.video
            and visual.duration_seconds
            and not section.text.strip()
            else AudioMode.narration
        )
        anchor = SegmentAnchor(
            visible=template_id
            in {
                "split_anchor_visual",
                "fullscreen_anchor",
                "fallback_anchor",
            },
            speaking=audio_mode != AudioMode.source,
            camera="front_close"
            if template_id != "fullscreen_anchor"
            else "landscape_intro",
        )
        source_volume = 1.0 if audio_mode == AudioMode.source else 0.0
        segment = TimelineSegment(
            segment_id=f"seg_{index + 1:03d}",
            section_id=section.section_id,
            start_time=round(start, 3),
            end_time=round(start + duration, 3),
            duration=round(duration, 3),
            script_text=section.text,
            claim_ids=section.claim_ids,
            anchor=anchor,
            visual=segment_visual_from_candidate(visual),
            template=SegmentTemplate(template_id=template_id),
            audio=SegmentAudio(
                mode=audio_mode,
                narration_volume=1.0 if audio_mode != AudioMode.source else 0.0,
                source_volume=source_volume,
                ducking=False,
            ),
            overlays=SegmentOverlays(
                lower_third=script.lower_thirds[0]
                if script.lower_thirds
                else script.headline,
                chyron=script.chyrons[0]
                if script.chyrons
                else section.section_type.replace("_", " "),
                attribution=visual.attribution_text if visual else "",
                quote_text="",
                document_source=visual.attribution_text
                if visual and visual.content_role == ContentRole.document
                else "",
                data={
                    "title": section.section_type.replace("_", " ").title(),
                    "bullets": [section.text[:120]],
                    "values": [],
                    "locations": [],
                    "events": [],
                },
            ),
            status=ApprovalStatus.review,
        )
        segments.append(segment)
        start += duration
    plan = TimelinePlan(
        story_id=story_id, status=TimelineStatus.review, segments=segments
    )
    plan.audio_plan = build_audio_plan(story_id, segments)
    errors, warnings = validate_timeline(plan, check_media_exists=True)
    plan.validation_errors = errors
    plan.validation_warnings = warnings
    saved = repository.save_timeline(plan)
    candidate = repository.candidate_for_story(story_id)
    if candidate.workflow_state in {
        StoryWorkflowState.visuals_review,
        StoryWorkflowState.script_approved,
    }:
        try:
            if candidate.workflow_state == StoryWorkflowState.script_approved:
                repository.transition_story(
                    story_id, StoryWorkflowState.visuals_searching
                )
                repository.transition_story(story_id, StoryWorkflowState.visuals_review)
            repository.transition_story(story_id, StoryWorkflowState.timeline_draft)
            repository.transition_story(story_id, StoryWorkflowState.timeline_review)
        except Exception:
            pass
    return saved


def approve_timeline(repository, story_id: str) -> TimelinePlan:
    plan = repository.latest_timeline(story_id)
    if not plan:
        raise ValueError(f"No timeline exists for story: {story_id}")
    errors, warnings = validate_timeline(plan, check_media_exists=True)
    plan.validation_errors = errors
    plan.validation_warnings = warnings
    if errors:
        repository.save_timeline(plan)
        raise ValueError("Timeline validation failed: " + "; ".join(errors))
    for segment in plan.segments:
        segment.status = ApprovalStatus.approved
    plan.status = TimelineStatus.approved
    plan.audio_plan = build_audio_plan(story_id, plan.segments)
    saved = repository.save_timeline(plan)
    try:
        current = repository.candidate_for_story(story_id).workflow_state
        if current == StoryWorkflowState.timeline_review:
            repository.transition_story(story_id, StoryWorkflowState.timeline_approved)
        elif current == StoryWorkflowState.timeline_draft:
            repository.transition_story(story_id, StoryWorkflowState.timeline_review)
            repository.transition_story(story_id, StoryWorkflowState.timeline_approved)
    except Exception:
        pass
    return saved
