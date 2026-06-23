from __future__ import annotations

import os
from pathlib import Path

from .storage import PROJECT_ROOT, resolve_project_path


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    value = env(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number.") from exc


def avatar_engine_dir() -> Path:
    return resolve_project_path(env("SYNTHPOST_AVATAR_ENGINE_DIR", "avatar-engine") or "avatar-engine")


def remotion_dir() -> Path:
    return resolve_project_path(env("SYNTHPOST_REMOTION_DIR", "compositor/remotion_renderer") or "compositor/remotion_renderer")


def ffmpeg_binary() -> str:
    return env("SYNTHPOST_FFMPEG", "ffmpeg") or "ffmpeg"


def words_per_minute() -> float:
    return env_float("SYNTHPOST_WORDS_PER_MINUTE", 145.0)


def sample_story_path() -> Path:
    return PROJECT_ROOT / "episodes" / "ep_2026-06-20" / "stories" / "story_001" / "story.json"
