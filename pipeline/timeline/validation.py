from __future__ import annotations

from pathlib import Path

from pipeline.models import ReviewStatus, RightsTier, TimelinePlan, TimelineStatus
from pipeline.storage import resolve_project_path
from pipeline.timeline.templates import (
    TEMPLATE_REGISTRY,
    get_template,
    template_compatible,
)


class TimelineValidationError(ValueError):
    pass


def validate_timeline(
    plan: TimelinePlan,
    *,
    require_approved: bool = False,
    check_media_exists: bool = True,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if require_approved and plan.status != TimelineStatus.approved:
        errors.append("timeline status must be approved before rendering")
    seen: set[str] = set()
    previous_end = 0.0
    for index, segment in enumerate(plan.segments):
        prefix = f"segment {segment.segment_id or index}"
        if segment.segment_id in seen:
            errors.append(f"{prefix}: duplicate segment_id")
        seen.add(segment.segment_id)
        if segment.start_time < previous_end - 0.03:
            errors.append(f"{prefix}: overlaps previous segment")
        if segment.start_time > previous_end + 0.5:
            warnings.append(
                f"{prefix}: unexplained gap of {segment.start_time - previous_end:.2f}s"
            )
        previous_end = max(previous_end, segment.end_time)
        if segment.duration <= 0:
            errors.append(f"{prefix}: nonpositive duration")
        if segment.template.template_id not in TEMPLATE_REGISTRY:
            errors.append(f"{prefix}: unknown template {segment.template.template_id}")
            continue
        template = get_template(segment.template.template_id)
        if not template.production_enabled:
            reason = template.blacklist_reason or "template is not production enabled"
            errors.append(
                f"{prefix}: template {segment.template.template_id} is blacklisted for production: {reason}"
            )
        if (
            template.anchor_visible is not None
            and segment.anchor.visible != template.anchor_visible
        ):
            warnings.append(f"{prefix}: anchor.visible differs from template default")
        if (
            template.anchor_speaking is not None
            and segment.anchor.speaking != template.anchor_speaking
        ):
            warnings.append(f"{prefix}: anchor.speaking differs from template default")
        visual = segment.visual
        if visual.asset_id:
            if visual.rights_tier == RightsTier.red:
                errors.append(f"{prefix}: red-tier asset cannot render")
            if (
                visual.rights_tier == RightsTier.yellow
                and visual.review_status != ReviewStatus.manual_approved
            ):
                errors.append(f"{prefix}: yellow-tier asset requires manual approval")
            if visual.review_status not in {
                ReviewStatus.approved,
                ReviewStatus.manual_approved,
            }:
                errors.append(f"{prefix}: visual is not approved")
            if visual.attribution_text in (None, ""):
                warnings.append(f"{prefix}: approved visual has no attribution text")
        if not template_compatible(
            segment.template.template_id,
            visual.media_type.value,
            visual.content_role.value,
        ):
            errors.append(
                f"{prefix}: template {segment.template.template_id} is incompatible with {visual.media_type.value}/{visual.content_role.value}"
            )
        if check_media_exists and visual.path:
            resolved = resolve_project_path(visual.path)
            if not resolved.exists():
                errors.append(f"{prefix}: media path does not exist: {visual.path}")
        if visual.trim_start is not None and visual.trim_start < 0:
            errors.append(f"{prefix}: trim_start cannot be negative")
        if (
            visual.trim_end is not None
            and visual.trim_start is not None
            and visual.trim_end <= visual.trim_start
        ):
            errors.append(f"{prefix}: trim_end must be greater than trim_start")
        if segment.audio.mode == "source" and segment.anchor.speaking:
            errors.append(f"{prefix}: source audio mode requires anchor.speaking=false")
        if segment.audio.mode == "narration" and segment.visual.audio_mode in {
            "original",
            "mixed",
        }:
            warnings.append(
                f"{prefix}: visual source audio is enabled during narration mode"
            )
        if (
            "attribution" in template.required_fields
            and not segment.overlays.attribution
        ):
            errors.append(f"{prefix}: attribution overlay is required")
        if segment.template.template_id == "quote_card" and not segment.claim_ids:
            errors.append(f"{prefix}: quote card requires a linked claim")
        if (
            segment.template.template_id == "quote_card"
            and not segment.overlays.quote_text
        ):
            errors.append(f"{prefix}: quote card requires quote_text")
    if not plan.segments:
        errors.append("timeline has no segments")
    if previous_end <= 0:
        errors.append("timeline total duration must be positive")
    return errors, warnings


def assert_timeline_valid(
    plan: TimelinePlan,
    *,
    require_approved: bool = False,
    check_media_exists: bool = True,
) -> None:
    errors, warnings = validate_timeline(
        plan, require_approved=require_approved, check_media_exists=check_media_exists
    )
    if errors:
        raise TimelineValidationError("; ".join(errors))
