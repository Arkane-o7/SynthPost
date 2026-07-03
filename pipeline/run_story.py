from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

from .compositor import render_story
from .direction import avatar
from .render_profiles import apply_manifest_runtime, resolve_profile
from .storage import read_manifest, write_manifest


def _approved_timeline(manifest: dict[str, Any]) -> dict[str, Any] | None:
    timeline = manifest.get("approved_timeline")
    return timeline if isinstance(timeline, dict) else None


def _timeline_has_source_audio(timeline: dict[str, Any]) -> bool:
    segments = (
        timeline.get("segments") if isinstance(timeline.get("segments"), list) else []
    )
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        audio = segment.get("audio") if isinstance(segment.get("audio"), dict) else {}
        visual = (
            segment.get("visual") if isinstance(segment.get("visual"), dict) else {}
        )
        if audio.get("mode") in {"source", "mixed"}:
            return True
        if visual.get("audio_mode") in {"original", "mixed"}:
            return True
    return False


def _float_or_zero(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _avatar_target_duration(manifest: dict[str, Any]) -> float:
    direction = (
        manifest.get("direction") if isinstance(manifest.get("direction"), dict) else {}
    )
    for key in (
        "audio_duration_seconds",
        "anchor_duration_seconds",
        "estimated_duration_seconds",
        "duration_seconds",
    ):
        duration = _float_or_zero(direction.get(key))
        if duration > 0:
            return duration
    return 0.0


def _sync_timeline_to_avatar_duration(manifest: dict[str, Any]) -> bool:
    """Align pure-narration timeline segments to the actual avatar duration.

    Timeline drafts are initially estimated from text length. Real TTS often has
    different pacing and paragraph pauses. If we leave the approved timeline at
    the estimate while Remotion sizes the composition to the real anchor video,
    the last frames become blank and template boundaries feel late/early. For
    pure narration stories we proportionally rescale segment boundaries to the
    Avatar-Engine duration immediately before compositing.
    """

    timeline = _approved_timeline(manifest)
    if not timeline or str(timeline.get("status", "")).strip().lower() != "approved":
        return False
    if _timeline_has_source_audio(timeline):
        timeline["timing_sync_warning"] = (
            "Skipped avatar-duration rescale because source/mixed audio regions are present."
        )
        return False
    segments = (
        timeline.get("segments") if isinstance(timeline.get("segments"), list) else []
    )
    if not segments:
        return False
    target_duration = _avatar_target_duration(manifest)
    if target_duration <= 0:
        return False
    current_end = 0.0
    for segment in segments:
        if isinstance(segment, dict):
            current_end = max(current_end, _float_or_zero(segment.get("end_time")))
    if current_end <= 0 or abs(current_end - target_duration) < 0.08:
        return False
    scale = target_duration / current_end
    cursor = 0.0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        try:
            original_duration = float(segment.get("duration") or 0)
        except (TypeError, ValueError):
            original_duration = 0.0
        if original_duration <= 0:
            original_duration = _float_or_zero(
                segment.get("end_time")
            ) - _float_or_zero(segment.get("start_time"))
        if original_duration <= 0:
            original_duration = 1.0
        duration = max(0.1, original_duration * scale)
        start = cursor
        end = target_duration if index == len(segments) - 1 else cursor + duration
        segment["start_time"] = round(start, 3)
        segment["end_time"] = round(end, 3)
        segment["duration"] = round(max(0.1, end - start), 3)
        cursor = end
    audio_plan = (
        timeline.get("audio_plan")
        if isinstance(timeline.get("audio_plan"), dict)
        else None
    )
    if audio_plan:
        audio_plan["duration_seconds"] = round(target_duration, 3)
        regions = (
            audio_plan.get("regions")
            if isinstance(audio_plan.get("regions"), list)
            else []
        )
        segment_by_id = {
            str(segment.get("segment_id")): segment
            for segment in segments
            if isinstance(segment, dict)
        }
        for region in regions:
            if not isinstance(region, dict):
                continue
            segment = segment_by_id.get(str(region.get("segment_id")))
            if segment:
                region["start_time"] = segment["start_time"]
                region["end_time"] = segment["end_time"]
                region["duration"] = round(
                    _float_or_zero(segment.get("end_time"))
                    - _float_or_zero(segment.get("start_time")),
                    3,
                )
    timeline["duration_seconds"] = round(target_duration, 3)
    timeline["timing_source"] = "avatar_duration_rescaled"
    timeline.setdefault("original_duration_seconds", round(current_end, 3))
    direction = (
        manifest.get("direction") if isinstance(manifest.get("direction"), dict) else {}
    )
    script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
    script_text = str(script.get("text") or "").strip()
    if direction and script_text:
        direction["performance_beats"] = avatar.performance_beats_for(
            script_text, target_duration
        )
        manifest["direction"] = direction
    return True


def run_story(
    story_json_path: str | Path,
    *,
    force_avatar: bool = False,
    force_composite: bool = False,
    skip_avatar_render: bool = False,
    test_mode: bool = False,
    assemble: bool = False,
    render_profile: str = "production",
) -> None:
    """Render a pre-authored story manifest.

    After the pipeline rip-out this entrypoint deliberately does not collect news,
    write scripts, plan visuals, generate thumbnails, or choose templates. The
    manifest must already contain the script, composition/template, visual inputs,
    and optional approved timeline needed by Avatar-Engine and Remotion.
    """

    profile = resolve_profile(render_profile)
    manifest = read_manifest(story_json_path)
    apply_manifest_runtime(manifest, render_profile=profile, test_mode=test_mode)
    write_manifest(story_json_path, manifest)
    if test_mode:
        print(
            "[TEST_MODE] WARNING: Story run is labeled TEST_MODE and must not be treated as production output."
        )

    template_name = (
        manifest.get("composition", {}).get("template")
        if isinstance(manifest.get("composition"), dict)
        else None
    )
    if avatar.template_requires_avatar(template_name):
        avatar.run(
            story_json_path,
            force=force_avatar,
            render=not skip_avatar_render,
            test_mode=test_mode,
            render_profile=profile.name,
        )
        manifest = read_manifest(story_json_path)
        if _sync_timeline_to_avatar_duration(manifest):
            write_manifest(story_json_path, manifest)
            print("[timing] Rescaled approved timeline to Avatar-Engine duration.")
    else:
        print(
            f"[direction] Skipping Avatar-Engine for visual-only template: {template_name}"
        )

    render_story(
        story_json_path,
        force=force_composite,
        test_mode=test_mode,
        render_profile=profile.name,
    )

    if assemble:
        manifest = read_manifest(story_json_path)
        command = [
            "python3",
            "assembly/stitch_episode.py",
            str(manifest["episode_id"]),
            "--render-profile",
            profile.name,
        ]
        if test_mode:
            command.append("--test-mode")
        subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render one pre-authored SynthPost story manifest."
    )
    parser.add_argument("story_json", type=Path)
    parser.add_argument("--force-avatar", action="store_true")
    parser.add_argument("--force-composite", action="store_true")
    parser.add_argument(
        "--skip-avatar-render",
        action="store_true",
        help="Use an existing direction.anchor_output_path.",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Forward Avatar-Engine test mode when rendering.",
    )
    parser.add_argument(
        "--render-profile",
        choices=["preview", "production", "final_master"],
        default="production",
        help="Render quality profile to record and apply where supported.",
    )
    parser.add_argument(
        "--assemble",
        action="store_true",
        help="Run episode assembly after story compositing.",
    )
    args = parser.parse_args()
    run_story(
        args.story_json,
        force_avatar=args.force_avatar,
        force_composite=args.force_composite,
        skip_avatar_render=args.skip_avatar_render,
        test_mode=args.test_mode,
        assemble=args.assemble,
        render_profile=args.render_profile,
    )


if __name__ == "__main__":
    main()
