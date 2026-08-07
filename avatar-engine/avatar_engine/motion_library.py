"""Shared manifest handling for reusable CC body-motion clips."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MOTION_LIBRARY_VERSION = "cc_motion_library_v1"


def load_motion_library(root: Path, metadata: dict[str, Any]) -> dict[str, Any] | None:
    reference = metadata.get("motion_library")
    if not isinstance(reference, dict):
        return None
    relative = str(reference.get("manifest_path") or "").strip()
    if not relative:
        return None
    path = root / relative
    if not path.is_file():
        return {
            "version": MOTION_LIBRARY_VERSION,
            "manifest_path": str(path),
            "available": False,
            "clips": {},
            "aliases": {},
            "warnings": [f"Motion manifest is missing: {relative}"],
        }
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != MOTION_LIBRARY_VERSION:
        raise ValueError(
            f"Motion manifest {relative} must use version {MOTION_LIBRARY_VERSION!r}"
        )
    clips = raw.get("clips")
    aliases = raw.get("aliases") or {}
    if not isinstance(clips, dict) or not clips:
        raise ValueError(f"Motion manifest {relative} must define at least one clip")
    if not isinstance(aliases, dict):
        raise ValueError(f"Motion manifest {relative} aliases must be an object")

    library_relative = str(raw.get("blender_library") or "").strip()
    library_path = path.parent / library_relative if library_relative else None
    normalized_clips: dict[str, dict[str, Any]] = {}
    for clip_id, value in clips.items():
        if not isinstance(value, dict):
            raise ValueError(f"Motion clip {clip_id!r} must be an object")
        normalized = dict(value)
        normalized["action"] = str(normalized.get("action") or clip_id)
        web_file = str(normalized.get("web_file") or "").strip()
        if web_file:
            absolute_web = path.parent / web_file
            try:
                normalized["web_url"] = "/" + absolute_web.relative_to(root).as_posix()
            except ValueError as exc:
                raise ValueError(f"Motion web_file escapes repository root: {web_file}") from exc
            normalized["web_available"] = absolute_web.is_file()
        normalized_clips[str(clip_id)] = normalized

    return {
        "version": MOTION_LIBRARY_VERSION,
        "manifest_path": str(path),
        "blender_library_path": str(library_path) if library_path else None,
        "blender_library_available": bool(library_path and library_path.is_file()),
        "available": bool(library_path and library_path.is_file()),
        "default_idle": str(raw.get("default_idle") or ""),
        "clips": normalized_clips,
        "aliases": {str(key): str(value) for key, value in aliases.items()},
        "warnings": [],
    }


def resolve_clip_id(library: dict[str, Any] | None, requested: str) -> str:
    if not library:
        return requested
    aliases = library.get("aliases") or {}
    return str(aliases.get(requested, requested))


def browser_motion_library(library: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return only HTTP-safe motion data needed by the Three.js runtime."""

    if not library:
        return None
    clips: dict[str, dict[str, Any]] = {}
    for clip_id, value in (library.get("clips") or {}).items():
        web_url = value.get("web_url")
        clips[clip_id] = {
            "url": web_url,
            "available": bool(web_url and value.get("web_available")),
            "kind": value.get("kind", "gesture"),
            "loop": bool(value.get("loop", False)),
        }
    return {
        "version": library.get("version"),
        "default_idle": library.get("default_idle"),
        "aliases": library.get("aliases") or {},
        "clips": clips,
    }
