"""Load and schedule reusable Character Creator Actions through Blender NLA."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _resolve_clip(library: dict[str, Any], requested: str) -> tuple[str, dict[str, Any] | None]:
    aliases = library.get("aliases") or {}
    clip_id = str(aliases.get(requested, requested))
    return clip_id, (library.get("clips") or {}).get(clip_id)


def _load_actions(bpy_module: Any, path: Path, action_names: set[str]) -> list[str]:
    if not path.is_file() or not action_names:
        return []
    with bpy_module.data.libraries.load(str(path), link=False) as (source, target):
        target.actions = [name for name in source.actions if name in action_names]
    return sorted(action.name for action in target.actions if action is not None)


def _new_strip(
    track: Any,
    *,
    name: str,
    action: Any,
    start: int,
    end: int | None,
    influence: float,
    blend_in: int,
    blend_out: int,
    repeat_to: int | None,
    blend_type: str,
) -> Any:
    strip = track.strips.new(name=name, start=start, action=action)
    action_start, action_end = action.frame_range
    strip.action_frame_start = float(action_start)
    strip.action_frame_end = float(action_end)
    strip.frame_start = start
    if repeat_to is not None:
        strip.frame_end = max(start + 1, repeat_to)
        action_length = max(1.0, float(action_end) - float(action_start))
        strip.repeat = max(1.0, (repeat_to - start) / action_length)
    elif end is not None:
        strip.frame_end = max(start + 1, end)
    strip.influence = max(0.0, min(1.0, influence))
    strip.blend_in = max(0, blend_in)
    strip.blend_out = max(0, blend_out)
    strip.blend_type = blend_type
    strip.extrapolation = "NOTHING"
    return strip


def apply_motion_library(
    bpy_module: Any,
    *,
    armature: Any | None,
    scene: Any,
    job: dict[str, Any],
) -> dict[str, Any]:
    library = job.get("motion_library")
    result: dict[str, Any] = {
        "status": "unavailable",
        "library_path": None,
        "loaded_actions": [],
        "idle": None,
        "applied_events": [],
        "missing_clips": [],
    }
    if armature is None or not isinstance(library, dict):
        return result

    library_path = Path(str(library.get("blender_library_path") or ""))
    result["library_path"] = str(library_path) if str(library_path) else None
    if not library_path.is_file():
        result["status"] = "missing_library"
        return result

    animation = job.get("animation") or {}
    performance = job.get("performance") or {}
    idle_requested = str(
        animation.get("idle_loop") or library.get("default_idle") or ""
    ).strip()
    if idle_requested.lower() in {"", "none", "procedural_anchor"}:
        idle_requested = str(library.get("default_idle") or "").strip()

    events = list(performance.get("body_events") or [])
    if not events:
        events = list(animation.get("gesture_events") or [])

    requested: list[tuple[str, dict[str, Any] | None]] = []
    if idle_requested:
        requested.append(_resolve_clip(library, idle_requested))
    for event in events:
        requested_name = str(event.get("clip") or event.get("type") or "").strip()
        if requested_name:
            requested.append(_resolve_clip(library, requested_name))

    action_names = {
        str(clip.get("action") or clip_id)
        for clip_id, clip in requested
        if isinstance(clip, dict)
    }
    result["loaded_actions"] = _load_actions(bpy_module, library_path, action_names)
    animation_data = armature.animation_data_create()

    if idle_requested:
        idle_id, idle_clip = _resolve_clip(library, idle_requested)
        if isinstance(idle_clip, dict):
            action_name = str(idle_clip.get("action") or idle_id)
            action = bpy_module.data.actions.get(action_name)
            if action is not None:
                track = animation_data.nla_tracks.new()
                track.name = "synthpost_base_idle"
                _new_strip(
                    track,
                    name=idle_id,
                    action=action,
                    start=scene.frame_start,
                    end=None,
                    influence=float(idle_clip.get("weight", 1.0)),
                    blend_in=0,
                    blend_out=0,
                    repeat_to=scene.frame_end + 1,
                    blend_type="REPLACE",
                )
                result["idle"] = idle_id
            else:
                result["missing_clips"].append(idle_id)
        else:
            result["missing_clips"].append(idle_id)

    if events:
        gesture_track = animation_data.nla_tracks.new()
        gesture_track.name = "synthpost_presenter_gestures"
        for index, event in enumerate(events):
            requested_name = str(event.get("clip") or event.get("type") or "").strip()
            if not requested_name:
                continue
            clip_id, clip = _resolve_clip(library, requested_name)
            if not isinstance(clip, dict):
                result["missing_clips"].append(clip_id)
                continue
            action_name = str(clip.get("action") or clip_id)
            action = bpy_module.data.actions.get(action_name)
            if action is None:
                result["missing_clips"].append(clip_id)
                continue
            start_seconds = float(event.get("start", event.get("time", 0.0)))
            start = scene.frame_start + int(round(start_seconds * scene.render.fps))
            duration = event.get("duration")
            end = None
            if duration is not None:
                end = start + max(1, int(round(float(duration) * scene.render.fps)))
            blend_in = int(round(float(event.get("blend_in", 0.15)) * scene.render.fps))
            blend_out = int(round(float(event.get("blend_out", 0.2)) * scene.render.fps))
            weight = float(event.get("weight", event.get("strength", 1.0)))
            _new_strip(
                gesture_track,
                name=f"{clip_id}_{index + 1}",
                action=action,
                start=start,
                end=end,
                influence=weight,
                blend_in=blend_in,
                blend_out=blend_out,
                repeat_to=None,
                blend_type=str(clip.get("blend_type") or "COMBINE").upper(),
            )
            result["applied_events"].append(
                {"clip": clip_id, "frame": start, "weight": weight}
            )

    result["missing_clips"] = sorted(set(result["missing_clips"]))
    result["status"] = "pass" if not result["missing_clips"] else "partial"
    return result
