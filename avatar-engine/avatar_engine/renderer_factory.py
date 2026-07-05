"""Renderer selection logic.

Priority order (highest to lowest):
  1. Explicit ``--renderer`` CLI flag (passed via ``override``).
  2. ``renderer`` field in the job JSON.
  3. ``AVATAR_ENGINE_RENDERER`` environment variable.
  4. Default: ``"blender"``.

Fallback to Blender is allowed ONLY when
``AVATAR_ENGINE_ALLOW_RENDERER_FALLBACK=1`` is set in the environment.
"""

from __future__ import annotations

import os
from pathlib import Path

from avatar_engine.renderer_base import AvatarJob, AvatarRenderer

# Registered renderer names → import paths (lazy to avoid hard deps at import time)
_RENDERER_REGISTRY: dict[str, str] = {
    "blender": "avatar_engine.blender_renderer.BlenderAvatarRenderer",
    "talkinghead": "avatar_engine.talkinghead_renderer.TalkingHeadAvatarRenderer",
    "rocketbox": "avatar_engine.rocketbox_renderer.RocketboxAvatarRenderer",
}

VALID_RENDERERS = frozenset(_RENDERER_REGISTRY.keys())


def resolve_renderer_name(job: AvatarJob, override: str | None = None) -> str:
    """Return the canonical renderer name for the given job and environment."""
    if override:
        name = override.strip().lower()
        _require_valid(name)
        return name

    job_renderer = job.renderer
    if job_renderer and job_renderer != "blender":
        # Non-default value in the job itself
        _require_valid(job_renderer)
        return job_renderer

    env_renderer = os.environ.get("AVATAR_ENGINE_RENDERER", "").strip().lower()
    if env_renderer:
        _require_valid(env_renderer)
        return env_renderer

    # job_renderer may already be "blender" (the raw field default)
    if job_renderer in VALID_RENDERERS:
        return job_renderer

    return "blender"


def get_renderer(
    job: AvatarJob,
    override: str | None = None,
    config_path: Path | None = None,
) -> AvatarRenderer:
    """Instantiate and return the appropriate renderer for *job*."""
    name = resolve_renderer_name(job, override)
    class_path = _RENDERER_REGISTRY[name]
    module_name, class_name = class_path.rsplit(".", 1)

    import importlib

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)

    if name == "blender":
        return cls(config_path=config_path)
    if name in {"talkinghead", "rocketbox"}:
        return cls(config_path=config_path)
    return cls()


def allow_renderer_fallback() -> bool:
    return os.environ.get("AVATAR_ENGINE_ALLOW_RENDERER_FALLBACK", "").strip() == "1"


def allow_2d_face_fallback() -> bool:
    return os.environ.get("AVATAR_ENGINE_ALLOW_2D_FACE_FALLBACK", "").strip() == "1"


# --------------------------------------------------------------------------- #


def _require_valid(name: str) -> None:
    if name not in VALID_RENDERERS:
        raise ValueError(
            f"Unknown renderer '{name}'. "
            f"Valid choices: {sorted(VALID_RENDERERS)}. "
            "Set AVATAR_ENGINE_RENDERER or pass --renderer."
        )
