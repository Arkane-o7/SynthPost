from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from pipeline import config
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
    timed_section_headline_cues,
)
from pipeline.provenance import ffprobe_summary
from pipeline.storage import resolve_project_path
from pipeline.timeline.validation import validate_timeline
from pipeline.visuals.providers import broadcast_media_fit


@dataclass(frozen=True)
class TemplateDecision:
    template_id: str
    scores: dict[str, float]
    reasons: list[str]


ANCHOR_BEATS = {
    "cold_open",
    "intro",
    "hook",
    "opening",
    "transition",
    "uncertainty",
    "caveat",
    "conclusion",
    "outro",
    "takeaway",
}
VISUAL_BEATS = {
    "key_developments",
    "development",
    "evidence",
    "what_happened",
    "demonstration",
}
SPLIT_BEATS = {
    "context",
    "explanation",
    "analysis",
    "why_it_matters",
    "impact",
}


def _is_fallback_visual(visual: VisualCandidate | None) -> bool:
    return bool(
        visual
        and (
            visual.content_role == ContentRole.fallback
            or visual.media_type == MediaType.fallback
            or visual.provider
            in {"generated_visual_card", "synthpost_anchor_fallback"}
        )
    )


def visual_has_audio(visual: VisualCandidate | None) -> bool:
    if visual is None or visual.media_type != MediaType.video:
        return False
    if visual.has_audio is not None:
        return visual.has_audio
    if visual.download_path:
        return bool(ffprobe_summary(visual.download_path).get("audio_codec"))
    return False


def choose_audio_mode(
    template_id: str,
    visual: VisualCandidate | None,
    *,
    authored_source_clip: bool = False,
) -> AudioMode:
    """Use source audio only for a script-authored insert.

    Ordinary searched videos remain muted B-roll. A full-screen clip may replace
    narration only when the script explicitly reserved the beat and the selected
    local video really contains an audio stream.
    """

    if (
        config.source_audio_inserts_enabled()
        and
        authored_source_clip
        and template_id == "fullscreen_news_visual"
        and visual is not None
        and visual.media_type == MediaType.video
        and visual_has_audio(visual)
    ):
        return AudioMode.source
    return AudioMode.narration


def select_template(
    section_type: str,
    visual: VisualCandidate | None,
    index: int,
    *,
    total_sections: int | None = None,
    previous_templates: list[str] | tuple[str, ...] = (),
    script_text: str = "",
) -> TemplateDecision:
    """Score production-safe layouts using editorial purpose and shot rhythm."""

    section = section_type.strip().lower()
    previous = list(previous_templates)
    last = previous[-1] if previous else None
    anchor_like = {"fullscreen_anchor", "fallback_anchor"}

    if visual is None or _is_fallback_visual(visual):
        intentional_anchor = section in ANCHOR_BEATS or index == 0
        selected = "fullscreen_anchor" if intentional_anchor else "fallback_anchor"
        reason = (
            "editorial direct-address beat"
            if intentional_anchor
            else "no approved source visual; safe presenter fallback"
        )
        return TemplateDecision(selected, {selected: 100.0}, [reason])

    scores = {
        "split_anchor_visual": 60.0,
        "fullscreen_news_visual": 48.0,
        "fullscreen_anchor": 18.0,
    }
    reasons: dict[str, list[str]] = {template: [] for template in scores}

    def boost(template: str, amount: float, reason: str) -> None:
        scores[template] += amount
        reasons[template].append(reason)

    if section in ANCHOR_BEATS:
        boost("fullscreen_anchor", 46, "section is a direct-address editorial beat")
        boost("split_anchor_visual", -10, "anchor beat should not default to split")
    if section in VISUAL_BEATS:
        boost("fullscreen_news_visual", 36, "section advances the visual evidence")
        boost("split_anchor_visual", 8, "supporting explanation remains useful")
    if section in SPLIT_BEATS:
        boost("split_anchor_visual", 36, "section benefits from presenter explanation")
        boost("fullscreen_news_visual", 6, "approved media can still carry context")

    if visual.media_type == MediaType.video:
        boost("fullscreen_news_visual", 38, "approved motion footage deserves the frame")
    if visual.content_role in {
        ContentRole.primary_footage,
        ContentRole.evidence,
        ContentRole.atmosphere,
    }:
        boost("fullscreen_news_visual", 30, "visual role is strong enough to lead")
    if visual.content_role in {
        ContentRole.explanation,
        ContentRole.location,
        ContentRole.person,
        ContentRole.document,
        ContentRole.data,
    }:
        boost("split_anchor_visual", 20, "visual role benefits from presenter context")

    quality = visual.relevance_score + visual.visual_quality_score
    if quality >= 1.15:
        boost("fullscreen_news_visual", 20, "visual quality and relevance clear hero threshold")
    elif quality < 0.75:
        boost("fullscreen_news_visual", -22, "visual is not strong enough for fullscreen")
        boost("split_anchor_visual", 10, "weaker media is safer as supporting material")

    if visual.width and visual.height:
        aspect_ratio = visual.width / max(1, visual.height)
        if aspect_ratio >= 1.45:
            boost("fullscreen_news_visual", 16, "landscape framing suits fullscreen")
        elif aspect_ratio < 1.05:
            boost("fullscreen_news_visual", -28, "portrait framing should not fill 16:9")
            boost("split_anchor_visual", 18, "portrait framing is safer in the split panel")

    word_count = len(script_text.split())
    if word_count >= 45:
        boost("split_anchor_visual", 12, "dense narration benefits from anchor presence")
    elif 0 < word_count <= 28:
        boost("fullscreen_news_visual", 10, "concise narration leaves room for a hero visual")

    if index == 0:
        boost("fullscreen_anchor", 32, "opening establishes presenter and programme identity")
        boost("split_anchor_visual", -8, "avoid beginning with the default split layout")
    if total_sections and index == total_sections - 1:
        boost("fullscreen_anchor", 18, "closing direct address provides resolution")
        boost("fullscreen_news_visual", 14, "strong closing image can provide visual punctuation")

    if last == "split_anchor_visual":
        boost("fullscreen_news_visual", 14, "change scale after a split shot")
        boost("fullscreen_anchor", 8, "change composition after a split shot")
    elif last == "fullscreen_news_visual":
        boost("split_anchor_visual", 18, "return presenter after fullscreen evidence")
    elif last in anchor_like:
        boost("split_anchor_visual", 14, "move away from consecutive anchor-only shots")
        boost("fullscreen_news_visual", 18, "move from direct address to visual evidence")
        boost("fullscreen_anchor", -34, "avoid consecutive anchor-only shots")

    for template in scores:
        if last == template:
            boost(template, -24, "avoid repeating the previous layout")
        if len(previous) >= 2 and previous[-2:] == [template, template]:
            boost(template, -100, "never use one layout more than twice consecutively")

    selected = max(scores, key=lambda template: scores[template])
    selected_reasons = reasons[selected] or ["highest balanced editorial score"]
    return TemplateDecision(selected, scores, selected_reasons)


def _is_approved_visual(visual: VisualCandidate) -> bool:
    """Return True when an editor explicitly pinned a renderable visual."""
    if visual.review_status not in {
        ReviewStatus.approved,
        ReviewStatus.manual_approved,
    }:
        return False
    return _is_renderable_visual(visual)


def _is_renderable_visual(visual: VisualCandidate) -> bool:
    """Check technical usability without requiring an editorial approval click."""

    if visual.review_status in {ReviewStatus.rejected, ReviewStatus.blocked}:
        return False
    if _is_fallback_visual(visual):
        return True
    if not visual.download_path:
        return False
    if not resolve_project_path(visual.download_path).is_file():
        return False
    if (
        visual.media_type in {MediaType.image, MediaType.video}
        and config.get_settings().visuals.enforce_broadcast_fit
    ):
        eligible, _reason, _score = broadcast_media_fit(
            visual.width, visual.height, visual.media_type
        )
        if not eligible and not visual.broadcast_fit_override:
            return False
    return True


def _review_recency(visual: VisualCandidate) -> float:
    if not visual.reviewed_at:
        return 0.0
    try:
        reviewed = datetime.fromisoformat(
            visual.reviewed_at.replace("Z", "+00:00")
        )
        if reviewed.tzinfo is None:
            reviewed = reviewed.replace(tzinfo=timezone.utc)
        return reviewed.timestamp()
    except ValueError:
        return 0.0


def _visual_selection_key(visual: VisualCandidate) -> tuple:
    explicitly_approved = visual.review_status in {
        ReviewStatus.approved,
        ReviewStatus.manual_approved,
    }
    return (
        _is_fallback_visual(visual),
        0 if explicitly_approved else 1,
        -_review_recency(visual) if explicitly_approved else 0.0,
        -visual.relevance_score,
        -visual.visual_quality_score,
        -visual.source_authority,
    )


def approved_visuals_by_section(
    visuals: list[VisualCandidate],
) -> dict[str, VisualCandidate]:
    """Select one visual per section.

    Explicit approval pins a real visual. With no pinned choice, the highest
    relevance/quality renderable suggestion wins. Synthetic/presenter fallback
    is considered only after every real candidate has been excluded.
    """

    result: dict[str, VisualCandidate] = {}
    ranked = sorted(visuals, key=_visual_selection_key)
    for visual in ranked:
        if not _is_renderable_visual(visual):
            continue
        for section_id in visual.section_ids:
            result.setdefault(section_id, visual)
    return result


def source_audio_visuals_by_section(
    visuals: list[VisualCandidate],
) -> dict[str, VisualCandidate]:
    """Choose an audible local video for each authored source-clip cue."""

    result: dict[str, VisualCandidate] = {}
    ranked = sorted(visuals, key=_visual_selection_key)
    for visual in ranked:
        if (
            visual.media_type != MediaType.video
            or not _is_renderable_visual(visual)
            or not visual_has_audio(visual)
        ):
            continue
        for section_id in visual.section_ids:
            result.setdefault(section_id, visual)
    return result


def distribute_unassigned_visuals(
    visuals: list[VisualCandidate],
    section_ids: list[str],
    already_assigned: dict[str, VisualCandidate],
) -> dict[str, VisualCandidate]:
    """Distribute renderable unassigned visuals across unserved sections.

    When visuals are uploaded or staged via the UI/drop-folder without explicit
    section_id bindings, they end up with ``section_ids == []``.  Without this
    distribution step the timeline planner sees ``visual=None`` for every segment
    and falls back to ``fallback_anchor``.

    Visuals are distributed round-robin (by relevance score, descending) to
    sections that don't already have a visual from explicit assignment.
    """
    result = dict(already_assigned)
    unassigned = [
        visual
        for visual in visuals
        if _is_renderable_visual(visual)
        and not _is_fallback_visual(visual)
        and not visual.section_ids
    ]
    if not unassigned:
        return result
    # Prefer higher-quality / more-relevant visuals first
    unassigned.sort(
        key=lambda v: (
            v.review_status in {ReviewStatus.approved, ReviewStatus.manual_approved},
            v.relevance_score,
            v.visual_quality_score,
            v.source_authority,
        ),
        reverse=True,
    )
    open_sections = [sid for sid in section_ids if sid not in result]
    if not open_sections:
        return result
    for idx, section_id in enumerate(open_sections):
        visual = unassigned[idx % len(unassigned)]
        result[section_id] = visual
    return result


def choose_template(
    section_type: str,
    visual: VisualCandidate | None,
    index: int,
    *,
    total_sections: int | None = None,
    previous_templates: list[str] | tuple[str, ...] = (),
    script_text: str = "",
) -> str:
    return select_template(
        section_type,
        visual,
        index,
        total_sections=total_sections,
        previous_templates=previous_templates,
        script_text=script_text,
    ).template_id


def segment_visual_from_candidate(visual: VisualCandidate | None) -> SegmentVisual:
    if (
        not visual
        or visual.content_role == ContentRole.fallback
        or visual.media_type == MediaType.fallback
        or visual.provider
        in {"generated_visual_card", "synthpost_anchor_fallback"}
    ):
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
        has_audio=visual_has_audio(visual),
        attribution_text=visual.attribution_text,
        content_cleanliness_status=visual.content_cleanliness_status,
        approval_blockers=list(visual.approval_blockers),
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
        warnings=(
            [
                "Experimental source-audio inserts are enabled; the avatar clock pauses during authored inserts."
            ]
            if config.source_audio_inserts_enabled()
            else [
                "Production-safe audio policy: all external visuals are muted B-roll under continuous anchor narration."
            ]
        ),
    )


def _source_clip_window(
    visual: VisualCandidate, requested_duration: float
) -> tuple[float, float, float]:
    trim_start = max(0.0, float(visual.trim_start or 0.0))
    available_end = visual.trim_end
    if available_end is None and visual.duration_seconds is not None:
        available_end = float(visual.duration_seconds)
    available = (
        max(0.0, float(available_end) - trim_start)
        if available_end is not None
        else requested_duration
    )
    duration = min(requested_duration, available) if available > 0 else 0.0
    return trim_start, trim_start + duration, duration


def _estimated_narration_duration(text: str) -> float:
    words = len(text.split())
    return round(max(3.0, words / config.words_per_minute() * 60.0), 2)


def generate_timeline(repository, story_id: str) -> TimelinePlan:
    script = repository.latest_script(
        story_id, approved=True
    ) or repository.latest_script(story_id)
    if not script:
        raise ValueError(f"No script exists for story: {story_id}")
    visuals = repository.list_visuals(story_id)
    by_section = approved_visuals_by_section(visuals)
    source_audio_by_section = source_audio_visuals_by_section(visuals)
    # Auto-distribute renderable visuals that were staged without explicit
    # section_id bindings (common for UI uploads and drop-folder scans).
    all_section_ids = [section.section_id for section in script.sections]
    by_section = distribute_unassigned_visuals(visuals, all_section_ids, by_section)
    start = 0.0
    segments: list[TimelineSegment] = []
    source_audio_enabled = config.source_audio_inserts_enabled()
    for index, section in enumerate(script.sections):
        authored_source_clip = section.source_clip
        source_clip = authored_source_clip if source_audio_enabled else None
        narration_text = section.text
        if authored_source_clip is not None and not source_audio_enabled:
            narration_text = " ".join(
                value.strip()
                for value in (
                    section.text,
                    authored_source_clip.fallback_narration,
                )
                if value.strip()
            )
        source_visual = (
            source_audio_by_section.get(section.section_id) if source_clip else None
        )
        duration = (
            _estimated_narration_duration(narration_text)
            if authored_source_clip is not None and not source_audio_enabled
            else max(
                4.0,
                (section.estimated_duration_seconds or 5.0)
                - (source_clip.duration_seconds if source_clip else 0.0),
            )
        )
        visual = by_section.get(section.section_id)
        if (
            source_visual is not None
            and visual is not None
            and visual.asset_id == source_visual.asset_id
        ):
            # Let the anchor set up an authored insert instead of showing the
            # same clip muted and then immediately replaying it with sound.
            visual = None
        decision = select_template(
            section.section_type,
            visual,
            index,
            total_sections=len(script.sections),
            previous_templates=[item.template.template_id for item in segments],
            script_text=narration_text,
        )
        template_id = decision.template_id
        render_visual = (
            visual
            if template_id in {"split_anchor_visual", "fullscreen_news_visual"}
            else None
        )
        audio_mode = choose_audio_mode(template_id, render_visual)
        anchor = SegmentAnchor(
            visible=template_id != "fullscreen_news_visual",
            # Narration can continue while the anchor is off screen. Only an
            # audible fullscreen source clip replaces the anchor voice.
            speaking=audio_mode != AudioMode.source,
            camera="front_close"
            if template_id != "fullscreen_anchor"
            else "landscape_intro",
        )
        source_volume = 1.0 if audio_mode == AudioMode.source else 0.0
        segment_visual = segment_visual_from_candidate(render_visual)
        if audio_mode == AudioMode.source:
            segment_visual.audio_mode = "original"
        elif audio_mode == AudioMode.mixed:
            segment_visual.audio_mode = "mixed"
        segment = TimelineSegment(
            segment_id=f"seg_{len(segments) + 1:03d}",
            section_id=section.section_id,
            start_time=round(start, 3),
            end_time=round(start + duration, 3),
            duration=round(duration, 3),
            script_text=narration_text,
            claim_ids=section.claim_ids,
            anchor=anchor,
            visual=segment_visual,
            template=SegmentTemplate(template_id=template_id),
            audio=SegmentAudio(
                mode=audio_mode,
                narration_volume=1.0 if audio_mode != AudioMode.source else 0.0,
                source_volume=source_volume,
                ducking=False,
            ),
            overlays=SegmentOverlays(
                lower_third=section.lower_third,
                chyron=section.chyron,
                attribution=render_visual.attribution_text if render_visual else "",
                quote_text="",
                document_source=render_visual.attribution_text
                if render_visual
                and render_visual.content_role == ContentRole.document
                else "",
                data={
                    "playback_mode": "narration",
                    "title": section.section_type.replace("_", " ").title(),
                    "headline_cues": timed_section_headline_cues(
                        narration_text,
                        section.section_type,
                        section.headline_cues,
                        duration,
                    ),
                    "bullets": [narration_text[:120]],
                    "values": [],
                    "locations": [],
                    "events": [],
                    "template_selection": {
                        "policy": "editorial_v1",
                        "selected": template_id,
                        "scores": decision.scores,
                        "reasons": decision.reasons,
                    },
                },
            ),
            status=ApprovalStatus.review,
        )
        segments.append(segment)
        start += duration

        if source_clip is None:
            continue

        source_duration = 0.0
        trim_start = 0.0
        trim_end = 0.0
        if source_visual is not None:
            trim_start, trim_end, source_duration = _source_clip_window(
                source_visual, source_clip.duration_seconds
            )

        if source_visual is not None and source_duration >= 3.0:
            source_segment_visual = segment_visual_from_candidate(source_visual)
            source_segment_visual.audio_mode = "original"
            source_segment_visual.trim_start = trim_start
            source_segment_visual.trim_end = trim_end
            source_segment = TimelineSegment(
                segment_id=f"seg_{len(segments) + 1:03d}",
                section_id=section.section_id,
                start_time=round(start, 3),
                end_time=round(start + source_duration, 3),
                duration=round(source_duration, 3),
                script_text="",
                claim_ids=section.claim_ids,
                anchor=SegmentAnchor(
                    visible=False,
                    speaking=False,
                    camera="front_close",
                ),
                visual=source_segment_visual,
                template=SegmentTemplate(template_id="fullscreen_news_visual"),
                audio=SegmentAudio(
                    mode=AudioMode.source,
                    narration_volume=0.0,
                    source_volume=1.0,
                    ducking=False,
                ),
                overlays=SegmentOverlays(
                    lower_third=section.lower_third,
                    chyron=section.chyron,
                    attribution=source_visual.attribution_text or "",
                    quote_text=source_clip.quote,
                    data={
                        "playback_mode": "source_clip",
                        "source_clip": source_clip.model_dump(mode="json"),
                        "headline_cues": [
                            {
                                "text": source_clip.quote
                                or source_clip.description,
                                "start": 0.0,
                                "end": round(source_duration, 3),
                            }
                        ],
                        "template_selection": {
                            "policy": "authored_source_clip",
                            "selected": "fullscreen_news_visual",
                            "reasons": [
                                "script explicitly reserved primary-source audio"
                            ],
                        },
                    },
                ),
                status=ApprovalStatus.review,
            )
        else:
            fallback_duration = _estimated_narration_duration(
                source_clip.fallback_narration
            )
            source_segment = TimelineSegment(
                segment_id=f"seg_{len(segments) + 1:03d}",
                section_id=section.section_id,
                start_time=round(start, 3),
                end_time=round(start + fallback_duration, 3),
                duration=round(fallback_duration, 3),
                script_text=source_clip.fallback_narration,
                claim_ids=section.claim_ids,
                anchor=SegmentAnchor(
                    visible=True,
                    speaking=True,
                    camera="front_close",
                ),
                visual=segment_visual_from_candidate(None),
                template=SegmentTemplate(template_id="fallback_anchor"),
                audio=SegmentAudio(
                    mode=AudioMode.narration,
                    narration_volume=1.0,
                    source_volume=0.0,
                    ducking=False,
                ),
                overlays=SegmentOverlays(
                    lower_third=section.lower_third,
                    chyron=section.chyron,
                    data={
                        "playback_mode": "source_clip_fallback",
                        "source_clip": source_clip.model_dump(mode="json"),
                        "headline_cues": timed_section_headline_cues(
                            source_clip.fallback_narration,
                            section.section_type,
                            [],
                            fallback_duration,
                        ),
                        "template_selection": {
                            "policy": "authored_source_clip_fallback",
                            "selected": "fallback_anchor",
                            "reasons": [
                                "no usable local video with source audio was available"
                            ],
                        },
                    },
                ),
                status=ApprovalStatus.review,
            )
        segments.append(source_segment)
        start += source_segment.duration
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
        if candidate.workflow_state == StoryWorkflowState.script_approved:
            repository.transition_story(
                story_id, StoryWorkflowState.visuals_searching
            )
            repository.transition_story(story_id, StoryWorkflowState.visuals_review)
        repository.transition_story(story_id, StoryWorkflowState.timeline_draft)
        repository.transition_story(story_id, StoryWorkflowState.timeline_review)
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
    current = repository.candidate_for_story(story_id).workflow_state
    if current == StoryWorkflowState.timeline_review:
        repository.transition_story(story_id, StoryWorkflowState.timeline_approved)
    elif current == StoryWorkflowState.timeline_draft:
        repository.transition_story(story_id, StoryWorkflowState.timeline_review)
        repository.transition_story(story_id, StoryWorkflowState.timeline_approved)
    return saved
