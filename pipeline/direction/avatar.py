from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .. import config
from ..observability import safe_text
from ..provenance import artifact_record, record_story_artifact
from ..render_profiles import resolve_profile
from ..storage import (
    ensure_parent,
    output_is_fresh,
    project_relative,
    read_manifest,
    resolve_project_path,
    story_dir,
    write_manifest,
)

GESTURE_PATTERN = [
    ("seated_idle", "calm"),
    ("explain_small", "focused"),
    ("nod_yes", "focused"),
    ("point_camera", "serious"),
]

BROWSER_GESTURE_MAP = {
    "explain_small": "explain_small",
    "nod_yes": "nod",
    "point_camera": "emphasis_right",
}

FULL_SCREEN_ANCHOR_TEMPLATES = {
    "full_screen_anchor",
    "fullscreen_anchor",
    "news_full_screen_anchor",
    "opening_anchor",
    "closing_anchor",
}

VISUAL_ONLY_TEMPLATES = {
    "full_screen_news_visuals",
    "fullscreen_news_visuals",
    "fullscreennewsvisuals",
    "news_visuals_full_screen",
    "source_clip_full_screen",
}

BROWSER_RENDERERS = {"rocketbox", "talkinghead"}
MODERN_CC_RENDERERS = BROWSER_RENDERERS | {"blender_cc"}
SUPPORTED_RENDERERS = MODERN_CC_RENDERERS | {"blender"}
DEFAULT_BROWSER_RENDERER = "rocketbox"
DEFAULT_AVATAR_ASSET_PATH = "assets/avatars/synthpost_anchor_v1/anchor.glb"
DEFAULT_AVATAR_METADATA_PATH = "assets/avatars/synthpost_anchor_v1/avatar.json"
DEFAULT_AVATAR_STYLE = "professional_news_anchor"
DEFAULT_AVATAR_BODY_FORM = "F"
DEFAULT_AVATAR_BACKGROUND = "charcoal"


def avatar_python() -> str:
    configured = config.get_settings().avatar.python_path
    if configured:
        return str(configured)
    candidate = config.avatar_engine_dir() / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def manifest_presenter(manifest: dict[str, Any] | None) -> dict[str, Any]:
    channel = as_dict((manifest or {}).get("channel"))
    production = as_dict(channel.get("production"))
    return production


def avatar_renderer(
    manifest: dict[str, Any] | None = None,
    render_profile: str | None = None,
) -> str:
    presenter = manifest_presenter(manifest)
    provider = str(presenter.get("presenter_provider") or "avatar_engine")
    if provider != "avatar_engine":
        raise ValueError(
            f"Presenter provider {provider!r} is not rendered by Avatar Engine"
        )
    profile_renderer = None
    if render_profile:
        profile = resolve_profile(render_profile)
        key = (
            "presenter_preview_renderer"
            if profile.name == "preview"
            else "presenter_final_renderer"
        )
        profile_renderer = presenter.get(key)
        # Stored SynthPost manifests created before the split only contain the
        # legacy `presenter_renderer=rocketbox` field. Migrate them at read time
        # so existing approved stories also receive the EEVEE final path.
        if (
            not profile_renderer
            and str((manifest or {}).get("channel_id") or "").lower()
            == "synthpost"
            and str(presenter.get("presenter_renderer") or "").lower()
            == "rocketbox"
        ):
            profile_renderer = (
                "rocketbox" if profile.name == "preview" else "blender_cc"
            )
    renderer = (
        profile_renderer
        or presenter.get("presenter_renderer")
        or
        config.get_settings().avatar.renderer
        or config.env("AVATAR_ENGINE_RENDERER")
        or DEFAULT_BROWSER_RENDERER
    )
    renderer = renderer.strip().lower()
    if renderer not in SUPPORTED_RENDERERS:
        expected = ", ".join(sorted(SUPPORTED_RENDERERS))
        raise ValueError(
            f"Unsupported Avatar-Engine renderer `{renderer}`. Expected one of: {expected}."
        )
    return renderer


def is_browser_renderer(renderer: str | None) -> bool:
    return str(renderer or "").strip().lower() in BROWSER_RENDERERS


def is_modern_cc_renderer(renderer: str | None) -> bool:
    return str(renderer or "").strip().lower() in MODERN_CC_RENDERERS


def avatar_runtime(renderer: str | None) -> str:
    normalized = str(renderer or "").strip().lower()
    if normalized == "rocketbox":
        return "custom_threejs_cc4"
    if normalized == "talkinghead":
        return "talkinghead_browser"
    if normalized == "blender_cc":
        return "blender_eevee_cc"
    return "legacy_blender"


def avatar_asset_path(manifest: dict[str, Any] | None = None) -> str:
    presenter = manifest_presenter(manifest)
    configured = str(presenter.get("presenter_asset_path") or "").strip()
    if configured:
        return configured
    return config.get_settings().avatar.asset_path.strip() or DEFAULT_AVATAR_ASSET_PATH


def avatar_metadata_path(manifest: dict[str, Any] | None = None) -> str:
    presenter = manifest_presenter(manifest)
    configured = str(presenter.get("presenter_metadata_path") or "").strip()
    if configured:
        return configured
    return (
        config.get_settings().avatar.metadata_path.strip()
        or DEFAULT_AVATAR_METADATA_PATH
    )


def avatar_render_background(manifest: dict[str, Any] | None = None) -> str:
    presenter = manifest_presenter(manifest)
    configured = str(presenter.get("presenter_background") or "").strip()
    if configured:
        return configured
    return (
        (config.env("SYNTHPOST_AVATAR_RENDER_BACKGROUND", DEFAULT_AVATAR_BACKGROUND) or "").strip()
        or DEFAULT_AVATAR_BACKGROUND
    )


def avatar_body_form(manifest: dict[str, Any] | None = None) -> str:
    presenter = manifest_presenter(manifest)
    configured = str(presenter.get("presenter_body_form") or "").strip()
    if configured:
        return configured
    return (
        (config.env("SYNTHPOST_AVATAR_BODY_FORM", DEFAULT_AVATAR_BODY_FORM) or "").strip()
        or DEFAULT_AVATAR_BODY_FORM
    )


def avatar_asset_id(job: dict[str, Any]) -> str:
    avatar = as_dict(job.get("avatar"))
    explicit = avatar.get("asset_id") or avatar.get("id")
    if explicit:
        return str(explicit)
    asset_path = str(avatar.get("asset_path") or avatar_asset_path())
    return Path(asset_path).parent.name or Path(asset_path).stem or "unknown_avatar"


def estimate_duration_seconds(script: str) -> float:
    words = max(1, len(script.split()))
    return max(6.0, words / config.words_per_minute() * 60.0)


def normalized_template_name(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def camera_for_template(template_name: Any) -> str:
    return (
        "landscape_intro"
        if normalized_template_name(template_name) in FULL_SCREEN_ANCHOR_TEMPLATES
        else "front_close"
    )


def template_requires_avatar(template_name: Any) -> bool:
    return normalized_template_name(template_name) not in VISUAL_ONLY_TEMPLATES


def camera_cuts_for(duration: float, template_name: Any = None) -> list[dict[str, Any]]:
    return [{"start": 0.0, "camera": camera_for_template(template_name)}]


def performance_beats_for(script: str, duration: float) -> list[dict[str, Any]]:
    sentence_count = max(1, script.count(".") + script.count("?") + script.count("!"))
    beat_count = min(max(2, sentence_count), len(GESTURE_PATTERN))
    beat_length = duration / beat_count
    beats: list[dict[str, Any]] = []
    for index in range(beat_count):
        gesture, expression = GESTURE_PATTERN[index % len(GESTURE_PATTERN)]
        beats.append(
            {
                "start": round(index * beat_length, 2),
                "end": round(
                    duration if index == beat_count - 1 else (index + 1) * beat_length,
                    2,
                ),
                "gesture": gesture,
                "expression": expression,
            }
        )
    return beats


def exact_performance_beats(
    narration: dict[str, Any], script: str, duration: float
) -> list[dict[str, Any]]:
    raw_beats = narration.get("beats")
    if not isinstance(raw_beats, list) or not raw_beats:
        return performance_beats_for(script, duration)
    beats: list[dict[str, Any]] = []
    for index, timing in enumerate(raw_beats):
        if not isinstance(timing, dict):
            continue
        gesture, expression = GESTURE_PATTERN[index % len(GESTURE_PATTERN)]
        beats.append(
            {
                "beat_id": timing.get("beat_id"),
                "start": float(timing.get("start_time") or 0.0),
                "end": float(timing.get("end_time") or 0.0),
                "gesture": gesture,
                "expression": expression,
                "timing_source": "tts_exact_samples",
            }
        )
    return beats or performance_beats_for(script, duration)


def gesture_events_for(
    script: str, duration: float, narration: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for beat in exact_performance_beats(narration or {}, script, duration):
        event_type = BROWSER_GESTURE_MAP.get(str(beat.get("gesture", "")))
        if not event_type:
            continue
        start = float(beat.get("start") or 0.0)
        end = float(beat.get("end") or start + 0.9)
        events.append(
            {
                "time": round(start, 2),
                "type": event_type,
                "duration": round(max(0.6, min(1.4, end - start)), 2),
            }
        )
    return events


def performance_v2_for(
    *,
    episode_id: str,
    story_id: str,
    script: str,
    duration: float,
    narration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one deterministic performance timeline shared by WebGL and Blender."""
    seed_material = f"{episode_id}\0{story_id}\0{script}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:4], "big")
    rng = random.Random(seed)

    blink_events: list[dict[str, Any]] = []
    blink_time = rng.uniform(2.8, 4.8)
    while blink_time < max(0.0, duration - 0.35):
        blink_events.append(
            {
                "time": round(blink_time, 2),
                "duration": round(rng.uniform(0.12, 0.17), 3),
                "strength": round(rng.uniform(0.88, 1.0), 2),
            }
        )
        blink_time += rng.uniform(3.2, 5.6)

    body_events = [
        {
            **event,
            "weight": 0.6,
            "blend_in": 0.15,
            "blend_out": 0.2,
        }
        for event in gesture_events_for(script, duration, narration)
        if float(event.get("time") or 0.0) > 0.15
    ]
    if duration >= 1.5:
        body_events.append(
            {
                "time": round(max(0.0, duration - 0.75), 2),
                "type": "conclusion_settle",
                "duration": 0.65,
                "weight": 0.8,
                "blend_in": 0.12,
                "blend_out": 0.18,
            }
        )

    return {
        "version": "performance_v2",
        "seed": seed,
        "visemes": [],
        "speech_envelope": [],
        "blink_events": blink_events,
        "gaze_events": [
            {"start": 0.0, "end": round(duration, 3), "target": "camera"}
        ],
        "expression_events": [
            {
                "start": 0.0,
                "end": round(duration, 3),
                "preset": "attentive",
                "weight": 0.18,
            }
        ],
        "body_events": body_events,
    }


def blender_profile_for(render_profile: str) -> str:
    return {
        "preview": "review",
        "production": "production",
        "final_master": "master",
    }[resolve_profile(render_profile).name]


def anchor_render_windows(
    manifest: dict[str, Any], narration_duration: float
) -> list[dict[str, Any]]:
    """Return coalesced narration-clock windows where the 3D anchor is visible."""

    timeline = as_dict(manifest.get("approved_timeline")) or as_dict(
        manifest.get("timeline_plan")
    )
    raw_segments = timeline.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        return []

    windows: list[dict[str, Any]] = []
    narration_cursor = 0.0
    for raw_segment in sorted(
        (item for item in raw_segments if isinstance(item, dict)),
        key=lambda item: float(item.get("start_time") or 0.0),
    ):
        timeline_start = float(raw_segment.get("start_time") or 0.0)
        timeline_end = float(raw_segment.get("end_time") or timeline_start)
        duration = max(0.0, timeline_end - timeline_start)
        audio = as_dict(raw_segment.get("audio"))
        audio_mode = str(audio.get("mode") or "narration").lower()
        source_start = narration_cursor
        if audio_mode != "source":
            narration_cursor += duration
        source_end = narration_cursor
        anchor = as_dict(raw_segment.get("anchor"))
        visible = bool(anchor.get("visible", True))
        if (
            not visible
            or audio_mode in {"source", "silent"}
            or source_end <= source_start
        ):
            continue
        source_end = min(source_end, max(0.0, narration_duration))
        if source_end <= source_start:
            continue
        camera = str(anchor.get("camera") or "front_close")
        segment_id = str(raw_segment.get("segment_id") or "")
        if (
            windows
            and abs(float(windows[-1]["timeline_end"]) - timeline_start) <= 0.05
            and abs(float(windows[-1]["source_end"]) - source_start) <= 0.05
            and windows[-1]["camera"] == camera
        ):
            windows[-1]["timeline_end"] = round(timeline_end, 3)
            windows[-1]["source_end"] = round(source_end, 3)
            if segment_id:
                windows[-1]["segment_ids"].append(segment_id)
            continue
        windows.append(
            {
                "timeline_start": round(timeline_start, 3),
                "timeline_end": round(timeline_end, 3),
                "source_start": round(source_start, 3),
                "source_end": round(source_end, 3),
                "camera": camera,
                "segment_ids": [segment_id] if segment_id else [],
            }
        )

    clip_cursor = 0.0
    for window in windows:
        duration = float(window["source_end"]) - float(window["source_start"])
        window["clip_start"] = round(clip_cursor, 3)
        clip_cursor += duration
        window["clip_end"] = round(clip_cursor, 3)
    return windows


def timeline_has_visible_anchor(manifest: dict[str, Any]) -> bool | None:
    """Return timeline anchor visibility, or None when no timeline is present."""

    timeline = as_dict(manifest.get("approved_timeline")) or as_dict(
        manifest.get("timeline_plan")
    )
    raw_segments = timeline.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        return None
    return any(
        bool(as_dict(segment.get("anchor")).get("visible", True))
        for segment in raw_segments
        if isinstance(segment, dict)
    )


def voice_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    narration = config.get_settings().narration
    settings: dict[str, Any] = {
        "engine": "dots_tts",
        "model": narration.model_name,
        "voice_id": narration.voice_id,
        "speed": narration.voice_speed,
        "sample_rate": 48000,
        "lang_code": narration.language_code,
    }
    if overrides:
        settings.update(
            {key: value for key, value in overrides.items() if value not in (None, "")}
        )
    if "voice" not in settings and settings.get("voice_id"):
        settings["voice"] = settings["voice_id"]
    return settings


def safe_path_component(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return cleaned.strip("._") or "item"


def browser_avatar_media_paths(episode_id: str, story_id: str) -> tuple[str, str]:
    base = (
        Path("assets")
        / "temp"
        / "synthpost"
        / safe_path_component(episode_id)
        / safe_path_component(story_id)
    )
    return (base / "voice.wav").as_posix(), (base / "rhubarb.json").as_posix()


def resolve_engine_path(value: str | Path, engine_dir: Path | None = None) -> Path:
    root = engine_dir or config.avatar_engine_dir()
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def engine_relative(path: str | Path, engine_dir: Path | None = None) -> str:
    root = (engine_dir or config.avatar_engine_dir()).resolve()
    resolved = resolve_engine_path(path, root).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def path_is_fresh(output: Path, inputs: Sequence[str | Path]) -> bool:
    if not output.exists():
        return False
    output_mtime = output.stat().st_mtime
    for value in inputs:
        input_path = Path(value)
        if input_path.exists() and input_path.stat().st_mtime > output_mtime:
            return False
    return True


def json_payload(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True) + "\n"


def write_json_if_changed(path: Path, data: dict[str, Any]) -> bool:
    ensure_parent(path)
    payload = json_payload(data)
    if path.exists() and path.read_text(encoding="utf-8") == payload:
        return False
    path.write_text(payload, encoding="utf-8")
    return True


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def read_avatar_job(job_path: Path) -> dict[str, Any]:
    with job_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected Avatar-Engine job object: {job_path}")
    return data


def avatar_job_output_path(job: dict[str, Any]) -> str:
    render = as_dict(job.get("render"))
    return str(render.get("output_path") or job.get("output_path") or "")


def avatar_job_preview_path(job: dict[str, Any]) -> str:
    render = as_dict(job.get("render"))
    return str(render.get("preview_png_path") or "")


def default_preview_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}_preview.png")


def browser_camera_overrides(direction: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "distance_multiplier": config.env_float(
            "SYNTHPOST_AVATAR_DISTANCE_MULTIPLIER", 2.3
        ),
        "target_height_factor": config.env_float(
            "SYNTHPOST_AVATAR_TARGET_HEIGHT_FACTOR", 0.84
        ),
        "height_factor": config.env_float("SYNTHPOST_AVATAR_HEIGHT_FACTOR", 0.86),
    }
    configured = direction.get("camera_overrides")
    if isinstance(configured, dict):
        defaults.update(
            {key: value for key, value in configured.items() if value not in (None, "")}
        )
    return defaults


def browser_avatar_job_from_manifest(
    manifest: dict[str, Any],
    duration: float,
    *,
    render_profile: str,
    renderer: str,
) -> dict[str, Any]:
    story_id = str(manifest["story_id"])
    episode_id = str(manifest["episode_id"])
    script = (
        manifest.get("script", {}) if isinstance(manifest.get("script"), dict) else {}
    )
    script_text = str(script.get("text", ""))
    direction = as_dict(manifest.get("direction"))
    composition = (
        manifest.get("composition", {})
        if isinstance(manifest.get("composition"), dict)
        else {}
    )
    profile = resolve_profile(render_profile)
    voice = voice_config(as_dict(direction.get("voice")) or None)
    anchor_output_path = direction.get(
        "anchor_output_path",
        f"episodes/{episode_id}/stories/{story_id}/anchor.mp4",
    )
    output_path = resolve_project_path(anchor_output_path)
    preview_path = resolve_project_path(
        direction.get(
            "avatar_preview_path", default_preview_path(output_path).as_posix()
        )
    )
    generated_audio_path, viseme_path = browser_avatar_media_paths(episode_id, story_id)
    narration = as_dict(manifest.get("narration"))
    canonical_audio = str(narration.get("audio_path") or "").strip()
    if canonical_audio:
        canonical_source = resolve_project_path(canonical_audio)
        if not canonical_source.exists():
            raise FileNotFoundError(
                f"Canonical dots.tts narration is missing: {canonical_source}"
            )
        engine_audio = resolve_engine_path(generated_audio_path)
        engine_audio.parent.mkdir(parents=True, exist_ok=True)
        if (
            not engine_audio.exists()
            or engine_audio.stat().st_size != canonical_source.stat().st_size
            or engine_audio.stat().st_mtime_ns != canonical_source.stat().st_mtime_ns
        ):
            shutil.copy2(canonical_source, engine_audio)
    audio_path = generated_audio_path
    camera_name = str(
        direction.get("avatar_camera")
        or camera_for_template(composition.get("template"))
    )
    render_config: dict[str, Any] = {
        "background": avatar_render_background(manifest),
        "output_path": output_path.as_posix(),
        "preview_png_path": preview_path.as_posix(),
        "blender_profile": blender_profile_for(profile.name),
    }
    if renderer == "blender_cc":
        windows = anchor_render_windows(manifest, duration)
        visible_duration = sum(
            float(window["source_end"]) - float(window["source_start"])
            for window in windows
        )
        if windows and visible_duration < duration - 0.05:
            render_config["render_windows"] = windows
            render_config["sparse_timeline"] = True

    return {
        "job_id": story_id,
        "channel_id": manifest.get("channel_id", "synthpost"),
        "channel_profile_version": manifest.get("channel_profile_version"),
        "renderer": renderer,
        "episode_id": episode_id,
        "story_id": story_id,
        # scripts/generate_tts.py still reads the legacy `script` key; render_avatar reads `script_text`.
        "script": script_text,
        "script_text": script_text,
        "voice": voice,
        "audio_path": audio_path,
        "canonical_audio_path": canonical_audio or None,
        "audio_source": (
            "canonical_narration" if canonical_audio else "avatar_engine_tts"
        ),
        "viseme_path": viseme_path,
        "avatar": {
            "asset_path": avatar_asset_path(manifest),
            "metadata_path": avatar_metadata_path(manifest),
            "asset_id": Path(avatar_asset_path(manifest)).parent.name or "unknown_anchor",
            "style": str(
                manifest_presenter(manifest).get("presenter_style")
                or config.env("SYNTHPOST_AVATAR_STYLE", DEFAULT_AVATAR_STYLE)
            ),
            "face_type": "3d",
            "body_form": avatar_body_form(manifest),
            "requires_3d_lips": True,
            "profile": manifest_presenter(manifest).get("presenter_style"),
        },
        "camera": {
            "name": camera_name,
            "width": profile.width,
            "height": profile.height,
            "fps": profile.fps,
            "duration_seconds": round(duration, 3),
        },
        "avatar_transform": {
            "rotation_y_degrees": config.env_float(
                "SYNTHPOST_AVATAR_ROTATION_Y_DEGREES", -3.0
            ),
        },
        "camera_overrides": browser_camera_overrides(direction),
        "render": render_config,
        "animation": {
            "idle_loop": "procedural_anchor",
            "gesture_events": gesture_events_for(
                script_text, duration, narration
            ),
        },
        "performance": performance_v2_for(
            episode_id=episode_id,
            story_id=story_id,
            script=script_text,
            duration=duration,
            narration=narration,
        ),
        "face": {
            "mode": "3d_viseme",
            "viseme_source": "rhubarb",
            "blendshape_profile": "reallusion_viseme",
            "fallback_mode": "legacy_2d",
            "allow_fallback": False,
        },
    }


def legacy_blender_job_from_manifest(
    manifest: dict[str, Any], duration: float, *, render_profile: str
) -> dict[str, Any]:
    story_id = str(manifest["story_id"])
    episode_id = str(manifest["episode_id"])
    script = (
        manifest.get("script", {}) if isinstance(manifest.get("script"), dict) else {}
    )
    direction = as_dict(manifest.get("direction"))
    composition = (
        manifest.get("composition", {})
        if isinstance(manifest.get("composition"), dict)
        else {}
    )
    profile = resolve_profile(render_profile)
    anchor_output_path = direction.get(
        "anchor_output_path",
        f"episodes/{episode_id}/stories/{story_id}/anchor.mp4",
    )

    narration = as_dict(manifest.get("narration"))
    return {
        "job_id": story_id,
        "renderer": "blender",
        "script": str(script.get("text", "")),
        "character": "avatar_01",
        "face_mode": "2d",
        "fps": profile.fps,
        "resolution": [profile.width, profile.height],
        "render_profile": profile.name,
        "voice": voice_config(as_dict(direction.get("voice")) or None),
        "camera_cuts": camera_cuts_for(duration, composition.get("template")),
        "performance_beats": exact_performance_beats(
            narration, str(script.get("text", "")), duration
        ),
        "output_path": resolve_project_path(anchor_output_path).as_posix(),
        "canonical_audio_path": narration.get("audio_path"),
        "audio_source": (
            "canonical_narration"
            if narration.get("audio_path")
            else "avatar_engine_tts"
        ),
    }


def avatar_job_from_manifest(
    manifest: dict[str, Any],
    duration: float,
    *,
    render_profile: str = "production",
    renderer: str | None = None,
) -> dict[str, Any]:
    selected_renderer = (
        renderer or avatar_renderer(manifest, render_profile)
    ).strip().lower()
    if selected_renderer not in SUPPORTED_RENDERERS:
        expected = ", ".join(sorted(SUPPORTED_RENDERERS))
        raise ValueError(
            f"Unsupported Avatar-Engine renderer `{selected_renderer}`. Expected one of: {expected}."
        )
    if is_modern_cc_renderer(selected_renderer):
        return browser_avatar_job_from_manifest(
            manifest,
            duration,
            render_profile=render_profile,
            renderer=selected_renderer,
        )
    return legacy_blender_job_from_manifest(
        manifest, duration, render_profile=render_profile
    )


def write_avatar_job(story_json_path: str | Path, job: dict[str, Any]) -> Path:
    manifest = read_manifest(story_json_path)
    path = (
        story_dir(str(manifest["episode_id"]), str(manifest["story_id"]))
        / "avatar_job.json"
    )
    write_json_if_changed(path, job)
    return path


def native_segment_export(output_path: str | Path) -> dict[str, Any] | None:
    expected_output = resolve_project_path(output_path)
    export_dir = expected_output.with_suffix("")
    manifest_path = export_dir / "edit_manifest.json"
    if manifest_path.exists():
        try:
            with manifest_path.open("r", encoding="utf-8") as handle:
                edit_manifest = json.load(handle)
        except (OSError, json.JSONDecodeError):
            edit_manifest = {}
        segments = (
            edit_manifest.get("segments") if isinstance(edit_manifest, dict) else None
        )
        if isinstance(segments, list):
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                segment_path = segment.get("path")
                if not segment_path:
                    continue
                resolved_segment = resolve_project_path(segment_path)
                if resolved_segment.exists():
                    return {
                        "path": resolved_segment,
                        "edit_manifest_path": manifest_path,
                        "segment": segment,
                        "export_mode": edit_manifest.get("export_mode"),
                    }
    if export_dir.is_dir():
        candidates = sorted(export_dir.glob("*.mp4"))
        if candidates:
            return {
                "path": candidates[0],
                "edit_manifest_path": manifest_path if manifest_path.exists() else None,
                "segment": {},
                "export_mode": "native_segments",
            }
    return None


def adopt_anchor_output_path(
    story_json_path: str | Path,
    actual_output_path: str | Path,
    native_export: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = read_manifest(story_json_path)
    direction = as_dict(manifest.get("direction"))
    direction["anchor_output_path"] = project_relative(actual_output_path)
    if native_export:
        edit_manifest_path = native_export.get("edit_manifest_path")
        direction["avatar_export_mode"] = (
            native_export.get("export_mode") or "native_segments"
        )
        if edit_manifest_path:
            direction["avatar_edit_manifest_path"] = project_relative(
                edit_manifest_path
            )
        segment = native_export.get("segment")
        if isinstance(segment, dict):
            direction["avatar_segment"] = {
                key: value
                for key, value in segment.items()
                if key
                in {
                    "index",
                    "camera",
                    "start",
                    "end",
                    "duration",
                    "start_frame",
                    "end_frame",
                    "frame_count",
                    "resolution",
                }
            }
    manifest["direction"] = direction
    write_manifest(story_json_path, manifest)
    return direction


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        frames = handle.getnframes()
        rate = handle.getframerate()
    return frames / float(rate or 1)


def probe_tts_duration(job_path: Path, test_mode: bool) -> float | None:
    engine_dir = config.avatar_engine_dir()
    script = engine_dir / "scripts" / "generate_tts.py"
    if not script.exists():
        return None
    probe_wav = job_path.parent / "tts_probe.wav"
    command = [
        avatar_python(),
        str(script),
        str(job_path),
        str(probe_wav),
        "--config",
        str(engine_dir / "config" / "default.yaml"),
    ]
    if test_mode:
        command.append("--test-mode")
    subprocess.run(
        command,
        cwd=engine_dir,
        env=avatar_subprocess_env(avatar_renderer()),
        check=True,
    )
    return wav_duration(probe_wav)


def existing_browser_audio_duration(
    episode_id: str, story_id: str
) -> tuple[float | None, str | None]:
    audio_rel, _ = browser_avatar_media_paths(episode_id, story_id)
    audio_path = resolve_engine_path(audio_rel)
    if not audio_path.exists():
        return None, None
    try:
        return wav_duration(audio_path), project_relative(audio_path)
    except (OSError, wave.Error):
        return None, None


def build_direction(
    story_json_path: str | Path,
    *,
    test_mode: bool = False,
    render_profile: str = "production",
) -> dict[str, Any]:
    manifest = read_manifest(story_json_path)
    profile = resolve_profile(render_profile)
    renderer = avatar_renderer(manifest, profile.name)
    script_text = str(manifest.get("script", {}).get("text", "")).strip()
    if not script_text:
        raise ValueError("Cannot build direction because script.text is empty.")

    narration = as_dict(manifest.get("narration"))
    narration_duration = float(narration.get("duration_seconds") or 0.0)
    estimated_duration = narration_duration or estimate_duration_seconds(script_text)
    duration_source = (
        "tts_exact_samples" if narration_duration else "words_per_minute"
    )
    if is_modern_cc_renderer(renderer) and not narration_duration:
        audio_duration, audio_path = existing_browser_audio_duration(
            str(manifest["episode_id"]), str(manifest["story_id"])
        )
        if audio_duration:
            estimated_duration = audio_duration
            duration_source = "avatar_audio"

    job = avatar_job_from_manifest(
        manifest, estimated_duration, render_profile=profile.name, renderer=renderer
    )
    job_path = write_avatar_job(story_json_path, job)

    if config.env_bool("SYNTHPOST_AVATAR_TTS_PROBE", False) and not is_modern_cc_renderer(
        renderer
    ):
        probed_duration = probe_tts_duration(job_path, test_mode=test_mode)
        if probed_duration:
            estimated_duration = probed_duration
            duration_source = "avatar_tts_probe"
            job = avatar_job_from_manifest(
                manifest,
                estimated_duration,
                render_profile=profile.name,
                renderer=renderer,
            )
            job_path = write_avatar_job(story_json_path, job)

    output_path = avatar_job_output_path(job)
    job_camera = as_dict(job.get("camera"))
    direction = {
        "job_id": str(manifest["story_id"]),
        "voice": job.get("voice", {}),
        "fps": int(job.get("fps") or job_camera.get("fps") or profile.fps),
        "resolution": job.get("resolution")
        or [
            int(job_camera.get("width") or profile.width),
            int(job_camera.get("height") or profile.height),
        ],
        "render_profile": profile.name,
        "test_mode": bool(test_mode),
        "avatar_renderer": renderer,
        "avatar_runtime": avatar_runtime(renderer),
        "camera_cuts": job.get("camera_cuts")
        or camera_cuts_for(
            estimated_duration, manifest.get("composition", {}).get("template")
        ),
        "performance_beats": job.get("performance_beats")
        or exact_performance_beats(narration, script_text, estimated_duration),
        "anchor_output_path": project_relative(output_path),
        "avatar_job_path": project_relative(job_path),
        "estimated_duration_seconds": round(estimated_duration, 2),
        "duration_source": duration_source,
    }

    if is_modern_cc_renderer(renderer):
        audio_abs = resolve_engine_path(str(job.get("audio_path", "")))
        viseme_abs = resolve_engine_path(str(job.get("viseme_path", "")))
        preview_path = avatar_job_preview_path(job)
        avatar = as_dict(job.get("avatar"))
        face = as_dict(job.get("face"))
        render = as_dict(job.get("render"))
        direction.update(
            {
                "avatar_export_mode": (
                    "eevee_mp4" if renderer == "blender_cc" else "browser_mp4"
                ),
                "avatar_asset_id": avatar_asset_id(job),
                "avatar_asset_path": avatar.get("asset_path"),
                "avatar_metadata_path": avatar.get("metadata_path"),
                "avatar_face_mode": face.get("mode", "3d_viseme"),
                "avatar_render_background": render.get("background"),
                "avatar_audio_path": project_relative(audio_abs),
                "avatar_lipsync_path": project_relative(viseme_abs),
                "avatar_preview_path": project_relative(preview_path)
                if preview_path
                else None,
            }
        )
        render_windows = render.get("render_windows")
        if isinstance(render_windows, list) and render_windows:
            direction["avatar_render_windows"] = render_windows
            direction["avatar_render_mode"] = "visible_timeline_windows"
        if timeline_has_visible_anchor(manifest) is False:
            direction["avatar_render_mode"] = "not_visible"
            direction["skip_avatar_render"] = True

    manifest["direction"] = {
        key: value
        for key, value in direction.items()
        if value not in (None, "", [], {})
    }
    write_manifest(story_json_path, manifest)
    record_story_artifact(
        story_json_path,
        "avatar_job",
        artifact_record(
            path=job_path,
            stage="direction",
            input_paths=[story_json_path],
            provider=as_dict(job.get("voice")).get("engine"),
            model=as_dict(job.get("voice")).get("voice_id"),
            fresh=True,
            test_mode=test_mode,
            render_profile=profile.name,
            metadata={
                "duration_source": duration_source,
                "avatar_renderer": renderer,
                "avatar_runtime": avatar_runtime(renderer),
                "avatar_asset_id": avatar_asset_id(job)
                if is_modern_cc_renderer(renderer)
                else None,
            },
        ),
    )
    return manifest["direction"]


def avatar_subprocess_env(renderer: str) -> dict[str, str]:
    engine_dir = config.avatar_engine_dir()
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(engine_dir)
        if not existing_pythonpath
        else str(engine_dir) + os.pathsep + existing_pythonpath
    )
    env["AVATAR_ENGINE_RENDERER"] = renderer
    return env


def require_browser_avatar_assets(job: dict[str, Any], engine_dir: Path) -> None:
    avatar = as_dict(job.get("avatar"))
    required = {
        "avatar GLB": avatar.get("asset_path"),
        "avatar metadata": avatar.get("metadata_path"),
    }
    missing: list[str] = []
    for label, value in required.items():
        if not value:
            missing.append(f"{label} path is missing from the Avatar-Engine job")
            continue
        resolved = resolve_engine_path(str(value), engine_dir)
        if not resolved.exists():
            missing.append(f"{label} not found: {resolved}")
    if missing:
        details = "\n".join(f"  - {item}" for item in missing)
        raise FileNotFoundError(
            f"{str(job.get('channel_id') or 'channel').title()} presenter assets are missing:\n"
            f"{details}\n"
            "Configure that channel's SYNTHEA_<CHANNEL>_PRESENTER_ASSET_PATH and "
            "SYNTHEA_<CHANNEL>_PRESENTER_META_PATH, select the video_file presenter provider, "
            "or use --skip-avatar-render for a non-production test."
        )


def _trim_process_output(value: str | None, *, limit: int = 6000) -> str:
    if not value:
        return ""
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[-limit:]


def run_avatar_subprocess(
    command: list[str], *, engine_dir: Path, renderer: str
) -> None:
    print(safe_text(f"[direction] Running Avatar-Engine: {' '.join(command)}"))
    result = subprocess.run(
        command,
        cwd=engine_dir,
        env=avatar_subprocess_env(renderer),
        capture_output=True,
        text=True,
    )
    stdout = _trim_process_output(result.stdout)
    stderr = _trim_process_output(result.stderr)
    if stdout:
        print(safe_text(stdout))
    if stderr:
        print(safe_text(stderr))
    if result.returncode != 0:
        details = [
            "Avatar-Engine command failed",
            f"exit_code={result.returncode}",
            f"command={' '.join(command)}",
        ]
        if stdout:
            details.append(f"stdout:\n{stdout}")
        if stderr:
            details.append(f"stderr:\n{stderr}")
        raise RuntimeError("\n".join(details))


def prepare_browser_avatar_inputs(
    job_path: Path,
    *,
    force: bool,
    test_mode: bool,
    renderer: str,
) -> dict[str, Any]:
    engine_dir = config.avatar_engine_dir()
    job = read_avatar_job(job_path)
    config_path = engine_dir / "config" / "default.yaml"
    audio_path = resolve_engine_path(str(job.get("audio_path", "")), engine_dir)
    viseme_path = resolve_engine_path(str(job.get("viseme_path", "")), engine_dir)
    commands: list[list[str]] = []

    canonical_audio = job.get("audio_source") == "canonical_narration"
    tts_inputs = [job_path, config_path]
    if canonical_audio:
        if not audio_path.exists():
            raise FileNotFoundError(
                f"Canonical dots.tts narration is missing: {audio_path}"
            )
        print(safe_text(f"[tts] Using canonical dots.tts narration: {audio_path}"))
    elif force or not path_is_fresh(audio_path, tts_inputs):
        tts_cmd = [
            avatar_python(),
            "scripts/generate_tts.py",
            str(job_path),
            engine_relative(audio_path, engine_dir),
            "--config",
            "config/default.yaml",
        ]
        if test_mode:
            tts_cmd.append("--test-mode")
        run_avatar_subprocess(tts_cmd, engine_dir=engine_dir, renderer=renderer)
        commands.append(tts_cmd)
    else:
        print(safe_text(f"[tts] Reusing fresh Avatar-Engine audio: {audio_path}"))

    lipsync_inputs = [audio_path, config_path]
    if force or not path_is_fresh(viseme_path, lipsync_inputs):
        lipsync_cmd = [
            avatar_python(),
            "scripts/generate_lipsync.py",
            engine_relative(audio_path, engine_dir),
            engine_relative(viseme_path, engine_dir),
            "--config",
            "config/default.yaml",
        ]
        if test_mode:
            lipsync_cmd.append("--test-mode")
        run_avatar_subprocess(lipsync_cmd, engine_dir=engine_dir, renderer=renderer)
        commands.append(lipsync_cmd)
    else:
        print(safe_text(f"[lipsync] Reusing fresh Avatar-Engine mouth cues: {viseme_path}"))

    duration = wav_duration(audio_path)
    job = read_avatar_job(job_path)
    camera = as_dict(job.get("camera"))
    current_duration = float(camera.get("duration_seconds") or 0.0)
    if abs(current_duration - duration) > 0.05:
        camera["duration_seconds"] = round(duration, 3)
        job["camera"] = camera
        write_json_if_changed(job_path, job)

    return {
        "audio_path": audio_path,
        "viseme_path": viseme_path,
        "duration_seconds": duration,
        "commands": commands,
    }


def avatar_engine_commit(engine_dir: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=engine_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    value = result.stdout.strip()
    return value or None


def browser_render_sidecars(output_path: Path) -> tuple[Path, Path]:
    return (
        output_path.parent / "avatar_render_manifest.json",
        output_path.parent / "render_stats.json",
    )


def update_browser_direction_after_prepare(
    story_json_path: str | Path,
    job: dict[str, Any],
    prepared: dict[str, Any],
) -> dict[str, Any]:
    manifest = read_manifest(story_json_path)
    direction = as_dict(manifest.get("direction"))
    audio_path = prepared["audio_path"]
    viseme_path = prepared["viseme_path"]
    duration = float(prepared["duration_seconds"])
    direction.update(
        {
            "avatar_audio_path": project_relative(audio_path),
            "avatar_lipsync_path": project_relative(viseme_path),
            "audio_duration_seconds": round(duration, 3),
            "estimated_duration_seconds": round(duration, 2),
            "duration_source": "avatar_audio",
            "avatar_renderer": job.get("renderer"),
            "avatar_runtime": avatar_runtime(str(job.get("renderer", ""))),
            "avatar_export_mode": (
                "eevee_mp4"
                if str(job.get("renderer")) == "blender_cc"
                else "browser_mp4"
            ),
        }
    )
    manifest["direction"] = {
        key: value
        for key, value in direction.items()
        if value not in (None, "", [], {})
    }
    write_manifest(story_json_path, manifest)
    return manifest["direction"]


def update_browser_direction_after_render(
    story_json_path: str | Path,
    job: dict[str, Any],
    output_path: Path,
    prepared: dict[str, Any] | None = None,
) -> dict[str, Any]:
    render_manifest_path, stats_path = browser_render_sidecars(output_path)
    render_manifest = read_json_if_exists(render_manifest_path)
    manifest = read_manifest(story_json_path)
    direction = as_dict(manifest.get("direction"))
    preview_path = avatar_job_preview_path(job)
    avatar = as_dict(job.get("avatar"))
    face = as_dict(job.get("face"))
    render = as_dict(job.get("render"))
    direction.update(
        {
            "anchor_output_path": project_relative(output_path),
            "avatar_renderer": job.get("renderer"),
            "avatar_runtime": avatar_runtime(str(job.get("renderer", ""))),
            "avatar_export_mode": (
                "eevee_mp4"
                if str(job.get("renderer")) == "blender_cc"
                else "browser_mp4"
            ),
            "avatar_asset_id": avatar_asset_id(job),
            "avatar_asset_path": avatar.get("asset_path"),
            "avatar_metadata_path": avatar.get("metadata_path"),
            "avatar_face_mode": face.get("mode", "3d_viseme"),
            "avatar_render_background": render.get("background"),
            "avatar_preview_path": project_relative(preview_path)
            if preview_path
            else None,
            "avatar_render_manifest_path": project_relative(render_manifest_path)
            if render_manifest_path.exists()
            else None,
            "avatar_render_stats_path": project_relative(stats_path)
            if stats_path.exists()
            else None,
        }
    )
    if prepared:
        direction.update(
            {
                "avatar_audio_path": project_relative(prepared["audio_path"]),
                "avatar_lipsync_path": project_relative(prepared["viseme_path"]),
                "audio_duration_seconds": round(float(prepared["duration_seconds"]), 3),
                "estimated_duration_seconds": round(
                    float(prepared["duration_seconds"]), 2
                ),
                "duration_source": "avatar_audio",
            }
        )
    if render_manifest:
        direction["render_wall_time_seconds"] = render_manifest.get("wall_time_seconds")
        direction["realtime_factor"] = render_manifest.get("realtime_factor")
        render_windows = render_manifest.get("render_windows")
        if isinstance(render_windows, list) and render_windows:
            direction["avatar_render_windows"] = render_windows
            direction["avatar_render_mode"] = "visible_timeline_windows"
            direction["avatar_rendered_duration_seconds"] = render_manifest.get(
                "rendered_duration_seconds"
            )
            direction["avatar_skipped_duration_seconds"] = render_manifest.get(
                "skipped_duration_seconds"
            )
        if render_manifest.get("fps"):
            direction["fps"] = render_manifest.get("fps")
        resolution = str(render_manifest.get("resolution") or "")
        if "x" in resolution:
            try:
                width, height = resolution.lower().split("x", 1)
                direction["resolution"] = [int(width), int(height)]
            except ValueError:
                pass
    manifest["direction"] = {
        key: value
        for key, value in direction.items()
        if value not in (None, "", [], {})
    }
    write_manifest(story_json_path, manifest)
    return manifest["direction"]


def browser_artifact_metadata(
    *,
    engine_dir: Path,
    job: dict[str, Any],
    output_path: Path,
    prepared: dict[str, Any] | None,
) -> dict[str, Any]:
    render_manifest_path, stats_path = browser_render_sidecars(output_path)
    render_manifest = read_json_if_exists(render_manifest_path)
    stats = read_json_if_exists(stats_path)
    voice = as_dict(job.get("voice"))
    avatar = as_dict(job.get("avatar"))
    face = as_dict(job.get("face"))
    preview_path = avatar_job_preview_path(job)
    metadata: dict[str, Any] = {
        "avatar_renderer": job.get("renderer"),
        "avatar_runtime": avatar_runtime(str(job.get("renderer", ""))),
        "avatar_asset_id": avatar_asset_id(job),
        "avatar_asset_path": avatar.get("asset_path"),
        "avatar_face_mode": face.get("mode", "3d_viseme"),
        "avatar_engine_commit": avatar_engine_commit(engine_dir),
        "voice_engine": voice.get("engine"),
        "voice_id": voice.get("voice_id") or voice.get("voice"),
        "voice_speed": voice.get("speed"),
        "output_path": project_relative(output_path),
        "preview_png_path": project_relative(preview_path) if preview_path else None,
        "manifest_path": project_relative(render_manifest_path)
        if render_manifest_path.exists()
        else None,
        "stats_path": project_relative(stats_path) if stats_path.exists() else None,
    }
    if prepared:
        metadata["audio_path"] = project_relative(prepared["audio_path"])
        metadata["rhubarb_path"] = project_relative(prepared["viseme_path"])
        metadata["audio_duration_seconds"] = round(
            float(prepared["duration_seconds"]), 3
        )
    if render_manifest:
        metadata.update(
            {
                "render_wall_time_seconds": render_manifest.get("wall_time_seconds"),
                "realtime_factor": render_manifest.get("realtime_factor"),
                "frame_count": render_manifest.get("frame_count"),
                "render_windows": render_manifest.get("render_windows"),
                "rendered_duration_seconds": render_manifest.get(
                    "rendered_duration_seconds"
                ),
                "skipped_duration_seconds": render_manifest.get(
                    "skipped_duration_seconds"
                ),
                "warnings": render_manifest.get("warnings"),
            }
        )
    elif stats:
        metadata.update(
            {
                "render_wall_time_seconds": stats.get("wall_time_seconds"),
                "realtime_factor": stats.get("realtime_factor"),
            }
        )
    return metadata


def run_browser_avatar_engine(
    story_json_path: str | Path,
    *,
    job_path: Path,
    output_path: Path,
    renderer: str,
    voice: dict[str, Any],
    profile_name: str,
    force: bool,
    test_mode: bool,
) -> Path:
    engine_dir = config.avatar_engine_dir()
    if not job_path.exists():
        raise FileNotFoundError(f"Avatar job file not found: {job_path}")

    job = read_avatar_job(job_path)
    require_browser_avatar_assets(job, engine_dir)
    audio_path = resolve_engine_path(str(job.get("audio_path", "")), engine_dir)
    viseme_path = resolve_engine_path(str(job.get("viseme_path", "")), engine_dir)
    initial_inputs: list[str | Path] = [
        job_path,
        audio_path,
        viseme_path,
    ]
    if (
        audio_path.exists()
        and viseme_path.exists()
        and path_is_fresh(output_path, initial_inputs)
        and not force
    ):
        print(safe_text(f"[direction] Reusing fresh modern avatar render: {output_path}"))
        update_browser_direction_after_render(
            story_json_path,
            job,
            output_path,
            {
                "audio_path": audio_path,
                "viseme_path": viseme_path,
                "duration_seconds": wav_duration(audio_path),
            },
        )
        record_story_artifact(
            story_json_path,
            "avatar_anchor",
            artifact_record(
                path=output_path,
                stage="avatar",
                input_paths=initial_inputs,
                provider=voice.get("engine"),
                model=voice.get("voice_id") or voice.get("voice"),
                fresh=False,
                reused=True,
                test_mode=test_mode,
                render_profile=profile_name,
                flags={"force": force, "avatar_renderer": renderer},
                metadata=browser_artifact_metadata(
                    engine_dir=engine_dir,
                    job=job,
                    output_path=output_path,
                    prepared={
                        "audio_path": audio_path,
                        "viseme_path": viseme_path,
                        "duration_seconds": wav_duration(audio_path),
                    },
                ),
            ),
        )
        return output_path

    prepared = prepare_browser_avatar_inputs(
        job_path, force=force, test_mode=test_mode, renderer=renderer
    )
    job = read_avatar_job(job_path)
    update_browser_direction_after_prepare(story_json_path, job, prepared)
    output_path = resolve_project_path(avatar_job_output_path(job))
    inputs: list[str | Path] = [
        job_path,
        prepared["audio_path"],
        prepared["viseme_path"],
    ]
    if path_is_fresh(output_path, inputs) and not force:
        print(safe_text(f"[direction] Reusing fresh modern avatar render: {output_path}"))
        update_browser_direction_after_render(
            story_json_path, job, output_path, prepared
        )
        record_story_artifact(
            story_json_path,
            "avatar_anchor",
            artifact_record(
                path=output_path,
                stage="avatar",
                input_paths=inputs,
                provider=voice.get("engine"),
                model=voice.get("voice_id") or voice.get("voice"),
                fresh=False,
                reused=True,
                test_mode=test_mode,
                render_profile=profile_name,
                flags={"force": force, "avatar_renderer": renderer},
                metadata=browser_artifact_metadata(
                    engine_dir=engine_dir,
                    job=job,
                    output_path=output_path,
                    prepared=prepared,
                ),
            ),
        )
        return output_path

    if test_mode:
        print(
            "[TEST_MODE] WARNING: Avatar-Engine modern renderer is running with TEST_MODE TTS/lipsync inputs."
        )
    command = [
        avatar_python(),
        "-m",
        "avatar_engine.render_avatar",
        "--job",
        str(job_path),
        "--renderer",
        renderer,
        "--config",
        "config/default.yaml",
    ]
    if test_mode:
        command.append("--test-mode")
    run_avatar_subprocess(command, engine_dir=engine_dir, renderer=renderer)
    if not output_path.exists():
        raise FileNotFoundError(
            f"Avatar-Engine did not create expected anchor clip: {output_path}"
        )

    update_browser_direction_after_render(story_json_path, job, output_path, prepared)
    record_story_artifact(
        story_json_path,
        "avatar_anchor",
        artifact_record(
            path=output_path,
            stage="avatar",
            input_paths=inputs,
            provider=voice.get("engine"),
            model=voice.get("voice_id") or voice.get("voice"),
            fresh=True,
            reused=False,
            test_mode=test_mode,
            render_profile=profile_name,
            command=command,
            flags={"force": force, "avatar_renderer": renderer},
            metadata=browser_artifact_metadata(
                engine_dir=engine_dir,
                job=job,
                output_path=output_path,
                prepared=prepared,
            ),
        ),
    )
    return output_path


def run_legacy_blender_avatar_engine(
    story_json_path: str | Path,
    *,
    job_path: Path,
    output_path: Path,
    voice: dict[str, Any],
    profile_name: str,
    force: bool,
    test_mode: bool,
) -> Path:
    if output_is_fresh(output_path, [story_json_path, job_path]) and not force:
        print(safe_text(f"[direction] Reusing fresh anchor render: {output_path}"))
        record_story_artifact(
            story_json_path,
            "avatar_anchor",
            artifact_record(
                path=output_path,
                stage="avatar",
                input_paths=[story_json_path, job_path],
                provider=voice.get("engine"),
                model=voice.get("voice_id") or voice.get("voice"),
                fresh=False,
                reused=True,
                test_mode=test_mode,
                render_profile=profile_name,
                flags={"force": force, "avatar_renderer": "blender"},
                metadata={
                    "avatar_renderer": "blender",
                    "avatar_runtime": "legacy_blender",
                },
            ),
        )
        return output_path

    native_export = native_segment_export(output_path)
    if (
        native_export
        and output_is_fresh(native_export["path"], [story_json_path, job_path])
        and not force
    ):
        actual_output_path = native_export["path"]
        adopt_anchor_output_path(story_json_path, actual_output_path, native_export)
        print(safe_text(f"[direction] Reusing fresh native anchor segment: {actual_output_path}"))
        record_story_artifact(
            story_json_path,
            "avatar_anchor",
            artifact_record(
                path=actual_output_path,
                stage="avatar",
                input_paths=[story_json_path, job_path],
                provider=voice.get("engine"),
                model=voice.get("voice_id") or voice.get("voice"),
                fresh=False,
                reused=True,
                test_mode=test_mode,
                render_profile=profile_name,
                flags={
                    "force": force,
                    "native_segment_export": True,
                    "avatar_renderer": "blender",
                },
                metadata={
                    "reuse_reason": "fresh Avatar-Engine native segment export already exists",
                    "avatar_renderer": "blender",
                    "avatar_runtime": "legacy_blender",
                },
            ),
        )
        return actual_output_path

    engine_dir = config.avatar_engine_dir()
    run_job = engine_dir / "scripts" / "run_job.py"
    if not run_job.exists():
        raise FileNotFoundError(f"Avatar-Engine runner not found: {run_job}")
    if not job_path.exists():
        raise FileNotFoundError(f"Avatar job file not found: {job_path}")

    command = [
        avatar_python(),
        "scripts/run_job.py",
        str(job_path),
        "--config",
        "config/default.yaml",
    ]
    job = read_avatar_job(job_path)
    canonical_audio = str(job.get("canonical_audio_path") or "").strip()
    if canonical_audio:
        source_audio = resolve_project_path(canonical_audio)
        if not source_audio.exists():
            raise FileNotFoundError(
                f"Canonical dots.tts narration is missing: {source_audio}"
            )
        legacy_audio = engine_dir / "assets" / "temp" / str(job["job_id"]) / "audio.wav"
        legacy_audio.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_audio, legacy_audio)
        command.append("--skip-tts")
        if force:
            command.extend(["--force-lipsync", "--force-render", "--force-export"])
    elif force:
        command.append("--force-all")
    if test_mode:
        command.append("--test-mode")

    if test_mode:
        print("[TEST_MODE] WARNING: Avatar-Engine is rendering in TEST_MODE.")
    run_avatar_subprocess(command, engine_dir=engine_dir, renderer="blender")
    native_export = native_segment_export(output_path)
    actual_output_path = (
        output_path
        if output_path.exists()
        else native_export["path"]
        if native_export
        else None
    )
    if actual_output_path is None or not actual_output_path.exists():
        raise FileNotFoundError(
            f"Avatar-Engine did not create expected anchor clip: {output_path}"
        )
    if actual_output_path != output_path:
        adopt_anchor_output_path(story_json_path, actual_output_path, native_export)
    record_story_artifact(
        story_json_path,
        "avatar_anchor",
        artifact_record(
            path=actual_output_path,
            stage="avatar",
            input_paths=[story_json_path, job_path],
            provider=voice.get("engine"),
            model=voice.get("voice_id") or voice.get("voice"),
            fresh=True,
            reused=False,
            test_mode=test_mode,
            render_profile=profile_name,
            command=command,
            flags={
                "force": force,
                "native_segment_export": actual_output_path != output_path,
                "avatar_renderer": "blender",
            },
            metadata={"avatar_renderer": "blender", "avatar_runtime": "legacy_blender"},
        ),
    )
    return actual_output_path


def run_avatar_engine(
    story_json_path: str | Path,
    *,
    force: bool = False,
    test_mode: bool = False,
    render_profile: str = "production",
) -> Path:
    manifest = read_manifest(story_json_path)
    direction = manifest.get("direction", {})
    job_path = resolve_project_path(direction.get("avatar_job_path", ""))
    output_path = resolve_project_path(direction.get("anchor_output_path", ""))
    profile = resolve_profile(render_profile)
    voice = as_dict(direction.get("voice"))
    renderer = (
        str(
            direction.get("avatar_renderer")
            or avatar_renderer(manifest, profile.name)
        ).strip().lower()
    )

    if is_modern_cc_renderer(renderer):
        return run_browser_avatar_engine(
            story_json_path,
            job_path=job_path,
            output_path=output_path,
            renderer=renderer,
            voice=voice,
            profile_name=profile.name,
            force=force,
            test_mode=test_mode,
        )

    return run_legacy_blender_avatar_engine(
        story_json_path,
        job_path=job_path,
        output_path=output_path,
        voice=voice,
        profile_name=profile.name,
        force=force,
        test_mode=test_mode,
    )


def run(
    story_json_path: str | Path,
    *,
    force: bool = False,
    render: bool = True,
    test_mode: bool = False,
    render_profile: str = "production",
) -> dict[str, Any]:
    profile = resolve_profile(render_profile)
    direction = build_direction(
        story_json_path, test_mode=test_mode, render_profile=profile.name
    )
    skip_invisible_anchor = bool(direction.get("skip_avatar_render"))
    if render and not skip_invisible_anchor:
        run_avatar_engine(
            story_json_path,
            force=force,
            test_mode=test_mode,
            render_profile=profile.name,
        )
    else:
        output_path = resolve_project_path(direction.get("anchor_output_path", ""))
        voice = as_dict(direction.get("voice"))
        renderer = (
            str(
                direction.get("avatar_renderer")
                or avatar_renderer(read_manifest(story_json_path), profile.name)
            ).strip().lower()
        )
        metadata = {
            "avatar_renderer": renderer,
            "avatar_runtime": avatar_runtime(renderer),
            "avatar_asset_id": direction.get("avatar_asset_id"),
            "avatar_face_mode": direction.get("avatar_face_mode"),
            "render_wall_time_seconds": 0,
            "realtime_factor": 0,
            "output_path": project_relative(output_path),
        }
        record_story_artifact(
            story_json_path,
            "avatar_anchor",
            artifact_record(
                path=output_path,
                stage="avatar",
                input_paths=[story_json_path, direction.get("avatar_job_path", "")],
                provider=voice.get("engine"),
                model=voice.get("voice_id") or voice.get("voice"),
                fresh=False,
                reused=output_path.exists(),
                skipped=True,
                test_mode=test_mode,
                render_profile=profile.name,
                flags={
                    "skip_avatar_render": True,
                    "anchor_not_visible": skip_invisible_anchor,
                    "force": force,
                    "avatar_renderer": renderer,
                },
                metadata=metadata,
            ),
        )
        if skip_invisible_anchor:
            print("[direction] Skipping Avatar-Engine because the approved timeline never displays the anchor.")
    return direction
