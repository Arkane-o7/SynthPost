from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def project_relative(path: str | Path) -> str:
    resolved = resolve_project_path(path).resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def read_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = resolve_project_path(path)
    with manifest_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected story manifest object: {manifest_path}")
    return data


def write_manifest(path: str | Path, data: dict[str, Any]) -> None:
    manifest_path = resolve_project_path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    os.replace(temp_path, manifest_path)


def update_section(path: str | Path, section: str, value: Any) -> dict[str, Any]:
    manifest = read_manifest(path)
    manifest[section] = value
    write_manifest(path, manifest)
    return manifest


def episode_dir(episode_id: str) -> Path:
    return PROJECT_ROOT / "episodes" / episode_id


def story_dir(episode_id: str, story_id: str) -> Path:
    return episode_dir(episode_id) / "stories" / story_id


def story_manifest_path(episode_id: str, story_id: str) -> Path:
    return story_dir(episode_id, story_id) / "story.json"


def output_is_fresh(output: str | Path, inputs: list[str | Path]) -> bool:
    output_path = resolve_project_path(output)
    if not output_path.exists():
        return False
    output_mtime = output_path.stat().st_mtime
    for value in inputs:
        input_path = resolve_project_path(value)
        if input_path.exists() and input_path.stat().st_mtime > output_mtime:
            return False
    return True


def require_section(manifest: dict[str, Any], section: str) -> dict[str, Any]:
    value = manifest.get(section)
    if not isinstance(value, dict):
        raise ValueError(f"Story manifest is missing object section '{section}'.")
    return value


def ensure_parent(path: str | Path) -> Path:
    resolved = resolve_project_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved
