from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .. import config
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
SUPPORTED_RENDERERS = BROWSER_RENDERERS | {"blender"}
DEFAULT_BROWSER_RENDERER = "rocketbox"
DEFAULT_AVATAR_ASSET_PATH = "assets/avatars/synthpost_anchor_v1/anchor.glb"
DEFAULT_AVATAR_METADATA_PATH = "assets/avatars/synthpost_anchor_v1/avatar.json"
DEFAULT_AVATAR_STYLE = "professional_news_anchor"
DEFAULT_AVATAR_BODY_FORM = "F"
DEFAULT_AVATAR_BACKGROUND = "charcoal"


def avatar_python() -> str:
    configured = os.environ.get("SYNTHPOST_AVATAR_PYTHON")
    if configured:
        return configured
    candidate = config.avatar_engine_dir() / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def avatar_renderer() -> str:
    renderer = (
        os.environ.get("SYNTHPOST_AVATAR_RENDERER")
        or os.environ.get("AVATAR_ENGINE_RENDERER")
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


def avatar_runtime(renderer: str | None) -> str:
    normalized = str(renderer or "").strip().lower()
    if normalized == "rocketbox":
        return "custom_threejs_cc4"
    if normalized == "talkinghead":
        return "talkinghead_browser"
    return "legacy_blender"


def avatar_asset_path() -> str:
    return (
        os.environ.get("SYNTHPOST_AVATAR_ASSET_PATH", DEFAULT_AVATAR_ASSET_PATH).strip()
        or DEFAULT_AVATAR_ASSET_PATH
    )


def avatar_metadata_path() -> str:
    return (
        os.environ.get(
            "SYNTHPOST_AVATAR_META_PATH", DEFAULT_AVATAR_METADATA_PATH
        ).strip()
        or DEFAULT_AVATAR_METADATA_PATH
    )


def avatar_render_background() -> str:
    return (
        os.environ.get(
            "SYNTHPOST_AVATAR_RENDER_BACKGROUND", DEFAULT_AVATAR_BACKGROUND
        ).strip()
        or DEFAULT_AVATAR_BACKGROUND
    )


def avatar_body_form() -> str:
    return (
        os.environ.get("SYNTHPOST_AVATAR_BODY_FORM", DEFAULT_AVATAR_BODY_FORM).strip()
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


def gesture_events_for(script: str, duration: float) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for beat in performance_beats_for(script, duration):
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


def voice_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "engine": "kokoro",
        "voice_id": os.environ.get("SYNTHPOST_AVATAR_VOICE_ID") or "af_heart",
        "speed": float(os.environ.get("SYNTHPOST_AVATAR_VOICE_SPEED") or "1.10"),
        "sample_rate": 24000,
        "lang_code": os.environ.get("SYNTHPOST_AVATAR_LANG_CODE") or "a",
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
    audio_path, viseme_path = browser_avatar_media_paths(episode_id, story_id)
    camera_name = str(
        direction.get("avatar_camera")
        or camera_for_template(composition.get("template"))
    )

    return {
        "job_id": story_id,
        "renderer": renderer,
        "episode_id": episode_id,
        "story_id": story_id,
        # scripts/generate_tts.py still reads the legacy `script` key; render_avatar reads `script_text`.
        "script": script_text,
        "script_text": script_text,
        "voice": voice,
        "audio_path": audio_path,
        "viseme_path": viseme_path,
        "avatar": {
            "asset_path": avatar_asset_path(),
            "metadata_path": avatar_metadata_path(),
            "asset_id": Path(avatar_asset_path()).parent.name or "synthpost_anchor_v1",
            "style": os.environ.get("SYNTHPOST_AVATAR_STYLE", DEFAULT_AVATAR_STYLE),
            "face_type": "3d",
            "body_form": avatar_body_form(),
            "requires_3d_lips": True,
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
        "render": {
            "background": avatar_render_background(),
            "output_path": output_path.as_posix(),
            "preview_png_path": preview_path.as_posix(),
        },
        "animation": {
            "idle_loop": "procedural_anchor",
            "gesture_events": gesture_events_for(script_text, duration),
        },
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
        "performance_beats": performance_beats_for(
            str(script.get("text", "")), duration
        ),
        "output_path": resolve_project_path(anchor_output_path).as_posix(),
    }


def avatar_job_from_manifest(
    manifest: dict[str, Any],
    duration: float,
    *,
    render_profile: str = "production",
    renderer: str | None = None,
) -> dict[str, Any]:
    selected_renderer = (renderer or avatar_renderer()).strip().lower()
    if selected_renderer not in SUPPORTED_RENDERERS:
        expected = ", ".join(sorted(SUPPORTED_RENDERERS))
        raise ValueError(
            f"Unsupported Avatar-Engine renderer `{selected_renderer}`. Expected one of: {expected}."
        )
    if is_browser_renderer(selected_renderer):
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
    renderer = avatar_renderer()
    script_text = str(manifest.get("script", {}).get("text", "")).strip()
    if not script_text:
        raise ValueError("Cannot build direction because script.text is empty.")

    estimated_duration = estimate_duration_seconds(script_text)
    duration_source = "words_per_minute"
    if is_browser_renderer(renderer):
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

    if config.env_bool("SYNTHPOST_AVATAR_TTS_PROBE", False) and not is_browser_renderer(
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
        or performance_beats_for(script_text, estimated_duration),
        "anchor_output_path": project_relative(output_path),
        "avatar_job_path": project_relative(job_path),
        "estimated_duration_seconds": round(estimated_duration, 2),
        "duration_source": duration_source,
    }

    if is_browser_renderer(renderer):
        audio_abs = resolve_engine_path(str(job.get("audio_path", "")))
        viseme_abs = resolve_engine_path(str(job.get("viseme_path", "")))
        preview_path = avatar_job_preview_path(job)
        avatar = as_dict(job.get("avatar"))
        face = as_dict(job.get("face"))
        render = as_dict(job.get("render"))
        direction.update(
            {
                "avatar_export_mode": "browser_mp4",
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
                if is_browser_renderer(renderer)
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
            "Avatar-Engine browser renderer prerequisites are missing:\n"
            f"{details}\n"
            "Provide the CC4/Reallusion GLB (normally avatar-engine/assets/avatars/synthpost_anchor_v1/anchor.glb), "
            "or run with SYNTHPOST_AVATAR_RENDERER=blender for the legacy Blender path, or use --skip-avatar-render."
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
    print(f"[direction] Running Avatar-Engine: {' '.join(command)}")
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
        print(stdout)
    if stderr:
        print(stderr)
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

    tts_inputs = [job_path, config_path]
    if force or not path_is_fresh(audio_path, tts_inputs):
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
        print(f"[tts] Reusing fresh Avatar-Engine audio: {audio_path}")

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
        print(f"[lipsync] Reusing fresh Avatar-Engine mouth cues: {viseme_path}")

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
            "avatar_export_mode": "browser_mp4",
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
            "avatar_export_mode": "browser_mp4",
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
        resolve_project_path(story_json_path),
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
        print(f"[direction] Reusing fresh browser avatar render: {output_path}")
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
        resolve_project_path(story_json_path),
        job_path,
        prepared["audio_path"],
        prepared["viseme_path"],
    ]
    if path_is_fresh(output_path, inputs) and not force:
        print(f"[direction] Reusing fresh browser avatar render: {output_path}")
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
            "[TEST_MODE] WARNING: Avatar-Engine browser renderer is running with TEST_MODE TTS/lipsync inputs."
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
        print(f"[direction] Reusing fresh anchor render: {output_path}")
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
        print(f"[direction] Reusing fresh native anchor segment: {actual_output_path}")
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
    if force:
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
        str(direction.get("avatar_renderer") or avatar_renderer()).strip().lower()
    )

    if is_browser_renderer(renderer):
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
    if render:
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
            str(direction.get("avatar_renderer") or avatar_renderer()).strip().lower()
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
                    "force": force,
                    "avatar_renderer": renderer,
                },
                metadata=metadata,
            ),
        )
    return direction
