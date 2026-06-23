from __future__ import annotations

import os
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any

from .. import config
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


def avatar_job_from_manifest(manifest: dict[str, Any], duration: float) -> dict[str, Any]:
    story_id = str(manifest["story_id"])
    episode_id = str(manifest["episode_id"])
    script = manifest.get("script", {})
    direction = manifest.get("direction", {}) if isinstance(manifest.get("direction"), dict) else {}
    composition = manifest.get("composition", {}) if isinstance(manifest.get("composition"), dict) else {}
    anchor_output_path = direction.get(
        "anchor_output_path",
        f"episodes/{episode_id}/stories/{story_id}/anchor.mp4",
    )

    return {
        "job_id": story_id,
        "script": str(script.get("text", "")),
        "character": "avatar_01",
        "face_mode": "2d",
        "fps": 24,
        "resolution": [1920, 1080],
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


def build_direction(story_json_path: str | Path, *, test_mode: bool = False) -> dict[str, Any]:
    manifest = read_manifest(story_json_path)
    script_text = str(manifest.get("script", {}).get("text", "")).strip()
    if not script_text:
        raise ValueError("Cannot build direction because script.text is empty.")

    estimated_duration = estimate_duration_seconds(script_text)
    duration_source = "words_per_minute"
    job = avatar_job_from_manifest(manifest, estimated_duration)
    job_path = write_avatar_job(story_json_path, job)

    if config.env_bool("SYNTHPOST_AVATAR_TTS_PROBE", False):
        probed_duration = probe_tts_duration(job_path, test_mode=test_mode)
        if probed_duration:
            estimated_duration = probed_duration
            duration_source = "avatar_tts_probe"
            job = avatar_job_from_manifest(manifest, estimated_duration)
            job_path = write_avatar_job(story_json_path, job)

    direction = {
        "job_id": str(manifest["story_id"]),
        "voice": job["voice"],
        "camera_cuts": job["camera_cuts"],
        "performance_beats": job["performance_beats"],
        "anchor_output_path": project_relative(job["output_path"]),
        "avatar_job_path": project_relative(job_path),
        "estimated_duration_seconds": round(estimated_duration, 2),
        "duration_source": duration_source,
    }
    manifest["direction"] = direction
    write_manifest(story_json_path, manifest)
    return direction


def run_avatar_engine(story_json_path: str | Path, *, force: bool = False, test_mode: bool = False) -> Path:
    manifest = read_manifest(story_json_path)
    direction = manifest.get("direction", {})
    job_path = resolve_project_path(direction.get("avatar_job_path", ""))
    output_path = resolve_project_path(direction.get("anchor_output_path", ""))

    if output_is_fresh(output_path, [story_json_path, job_path]) and not force:
        print(f"[direction] Reusing fresh anchor render: {output_path}")
        return output_path

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

    print(f"[direction] Running Avatar-Engine: {' '.join(command)}")
    subprocess.run(command, cwd=engine_dir, check=True)
    if not output_path.exists():
        raise FileNotFoundError(f"Avatar-Engine did not create expected anchor clip: {output_path}")
    return output_path


def run(story_json_path: str | Path, *, force: bool = False, render: bool = True, test_mode: bool = False) -> dict[str, Any]:
    direction = build_direction(story_json_path, test_mode=test_mode)
    if render:
        run_avatar_engine(story_json_path, force=force, test_mode=test_mode)
    return direction
