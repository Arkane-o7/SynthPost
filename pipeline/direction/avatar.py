from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any

from .. import config
from ..provenance import artifact_record, record_story_artifact
from ..render_profiles import resolve_profile
from ..storage import (
    PROJECT_ROOT,
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


def avatar_python() -> str:
    configured = os.environ.get("SYNTHPOST_AVATAR_PYTHON")
    if configured:
        return configured
    candidate = config.avatar_engine_dir() / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def estimate_duration_seconds(script: str) -> float:
    words = max(1, len(script.split()))
    return max(6.0, words / config.words_per_minute() * 60.0)


def normalized_template_name(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def camera_for_template(template_name: Any) -> str:
    return "landscape_intro" if normalized_template_name(template_name) in FULL_SCREEN_ANCHOR_TEMPLATES else "portrait_main"


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
                "end": round(duration if index == beat_count - 1 else (index + 1) * beat_length, 2),
                "gesture": gesture,
                "expression": expression,
            }
        )
    return beats


def voice_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "engine": "kokoro",
        "voice_id": os.environ.get("SYNTHPOST_AVATAR_VOICE_ID", "af_heart"),
        "speed": float(os.environ.get("SYNTHPOST_AVATAR_VOICE_SPEED", "1.0")),
        "sample_rate": 24000,
    }
    if overrides:
        settings.update({key: value for key, value in overrides.items() if value not in (None, "")})
    return settings


def avatar_job_from_manifest(manifest: dict[str, Any], duration: float, *, render_profile: str = "production") -> dict[str, Any]:
    story_id = str(manifest["story_id"])
    episode_id = str(manifest["episode_id"])
    script = manifest.get("script", {})
    direction = manifest.get("direction", {}) if isinstance(manifest.get("direction"), dict) else {}
    composition = manifest.get("composition", {}) if isinstance(manifest.get("composition"), dict) else {}
    profile = resolve_profile(render_profile)
    anchor_output_path = direction.get(
        "anchor_output_path",
        f"episodes/{episode_id}/stories/{story_id}/anchor.mp4",
    )

    return {
        "job_id": story_id,
        "script": str(script.get("text", "")),
        "character": "avatar_01",
        "face_mode": "2d",
        "fps": profile.fps,
        "resolution": [profile.width, profile.height],
        "render_profile": profile.name,
        "voice": voice_config(direction.get("voice") if isinstance(direction.get("voice"), dict) else None),
        "camera_cuts": camera_cuts_for(duration, composition.get("template")),
        "performance_beats": performance_beats_for(str(script.get("text", "")), duration),
        "output_path": resolve_project_path(anchor_output_path).as_posix(),
    }


def write_avatar_job(story_json_path: str | Path, job: dict[str, Any]) -> Path:
    manifest = read_manifest(story_json_path)
    path = story_dir(str(manifest["episode_id"]), str(manifest["story_id"])) / "avatar_job.json"
    ensure_parent(path)
    import json

    with path.open("w", encoding="utf-8") as handle:
        json.dump(job, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
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
        segments = edit_manifest.get("segments") if isinstance(edit_manifest, dict) else None
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


def adopt_anchor_output_path(story_json_path: str | Path, actual_output_path: str | Path, native_export: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = read_manifest(story_json_path)
    direction = manifest.get("direction") if isinstance(manifest.get("direction"), dict) else {}
    direction["anchor_output_path"] = project_relative(actual_output_path)
    if native_export:
        edit_manifest_path = native_export.get("edit_manifest_path")
        direction["avatar_export_mode"] = native_export.get("export_mode") or "native_segments"
        if edit_manifest_path:
            direction["avatar_edit_manifest_path"] = project_relative(edit_manifest_path)
        segment = native_export.get("segment")
        if isinstance(segment, dict):
            direction["avatar_segment"] = {
                key: value
                for key, value in segment.items()
                if key in {"index", "camera", "start", "end", "duration", "start_frame", "end_frame", "frame_count", "resolution"}
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
    command = [avatar_python(), str(script), str(job_path), str(probe_wav), "--config", str(engine_dir / "config" / "default.yaml")]
    if test_mode:
        command.append("--test-mode")
    subprocess.run(command, cwd=engine_dir, check=True)
    return wav_duration(probe_wav)


def build_direction(
    story_json_path: str | Path,
    *,
    test_mode: bool = False,
    render_profile: str = "production",
) -> dict[str, Any]:
    manifest = read_manifest(story_json_path)
    profile = resolve_profile(render_profile)
    script_text = str(manifest.get("script", {}).get("text", "")).strip()
    if not script_text:
        raise ValueError("Cannot build direction because script.text is empty.")

    estimated_duration = estimate_duration_seconds(script_text)
    duration_source = "words_per_minute"
    job = avatar_job_from_manifest(manifest, estimated_duration, render_profile=profile.name)
    job_path = write_avatar_job(story_json_path, job)

    if config.env_bool("SYNTHPOST_AVATAR_TTS_PROBE", False):
        probed_duration = probe_tts_duration(job_path, test_mode=test_mode)
        if probed_duration:
            estimated_duration = probed_duration
            duration_source = "avatar_tts_probe"
            job = avatar_job_from_manifest(manifest, estimated_duration, render_profile=profile.name)
            job_path = write_avatar_job(story_json_path, job)

    direction = {
        "job_id": str(manifest["story_id"]),
        "voice": job["voice"],
        "fps": profile.fps,
        "resolution": [profile.width, profile.height],
        "render_profile": profile.name,
        "test_mode": bool(test_mode),
        "camera_cuts": job["camera_cuts"],
        "performance_beats": job["performance_beats"],
        "anchor_output_path": project_relative(job["output_path"]),
        "avatar_job_path": project_relative(job_path),
        "estimated_duration_seconds": round(estimated_duration, 2),
        "duration_source": duration_source,
    }
    manifest["direction"] = direction
    write_manifest(story_json_path, manifest)
    record_story_artifact(
        story_json_path,
        "avatar_job",
        artifact_record(
            path=job_path,
            stage="direction",
            input_paths=[story_json_path],
            provider=job["voice"].get("engine"),
            model=job["voice"].get("voice_id"),
            fresh=True,
            test_mode=test_mode,
            render_profile=profile.name,
            metadata={"duration_source": duration_source},
        ),
    )
    return direction


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
    voice = direction.get("voice") if isinstance(direction.get("voice"), dict) else {}

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
                model=voice.get("voice_id"),
                fresh=False,
                reused=True,
                test_mode=test_mode,
                render_profile=profile.name,
                flags={"force": force},
            ),
        )
        return output_path

    native_export = native_segment_export(output_path)
    if native_export and output_is_fresh(native_export["path"], [story_json_path, job_path]) and not force:
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
                model=voice.get("voice_id"),
                fresh=False,
                reused=True,
                test_mode=test_mode,
                render_profile=profile.name,
                flags={"force": force, "native_segment_export": True},
                metadata={"reuse_reason": "fresh Avatar-Engine native segment export already exists"},
            ),
        )
        return actual_output_path

    engine_dir = config.avatar_engine_dir()
    run_job = engine_dir / "scripts" / "run_job.py"
    if not run_job.exists():
        raise FileNotFoundError(f"Avatar-Engine runner not found: {run_job}")
    if not job_path.exists():
        raise FileNotFoundError(f"Avatar job file not found: {job_path}")

    command = [avatar_python(), "scripts/run_job.py", str(job_path), "--config", "config/default.yaml"]
    if force:
        command.append("--force-all")
    if test_mode:
        command.append("--test-mode")

    if test_mode:
        print("[TEST_MODE] WARNING: Avatar-Engine is rendering in TEST_MODE.")
    print(f"[direction] Running Avatar-Engine: {' '.join(command)}")
    subprocess.run(command, cwd=engine_dir, check=True)
    native_export = native_segment_export(output_path)
    actual_output_path = output_path if output_path.exists() else native_export["path"] if native_export else None
    if actual_output_path is None or not actual_output_path.exists():
        raise FileNotFoundError(f"Avatar-Engine did not create expected anchor clip: {output_path}")
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
            model=voice.get("voice_id"),
            fresh=True,
            reused=False,
            test_mode=test_mode,
            render_profile=profile.name,
            command=command,
            flags={"force": force, "native_segment_export": actual_output_path != output_path},
        ),
    )
    return actual_output_path


def run(
    story_json_path: str | Path,
    *,
    force: bool = False,
    render: bool = True,
    test_mode: bool = False,
    render_profile: str = "production",
) -> dict[str, Any]:
    profile = resolve_profile(render_profile)
    direction = build_direction(story_json_path, test_mode=test_mode, render_profile=profile.name)
    if render:
        run_avatar_engine(story_json_path, force=force, test_mode=test_mode, render_profile=profile.name)
    else:
        output_path = resolve_project_path(direction.get("anchor_output_path", ""))
        voice = direction.get("voice") if isinstance(direction.get("voice"), dict) else {}
        record_story_artifact(
            story_json_path,
            "avatar_anchor",
            artifact_record(
                path=output_path,
                stage="avatar",
                input_paths=[story_json_path, direction.get("avatar_job_path", "")],
                provider=voice.get("engine"),
                model=voice.get("voice_id"),
                fresh=False,
                reused=output_path.exists(),
                skipped=True,
                test_mode=test_mode,
                render_profile=profile.name,
                flags={"skip_avatar_render": True, "force": force},
            ),
        )
    return direction
