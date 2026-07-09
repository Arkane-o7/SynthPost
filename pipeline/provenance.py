from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .render_profiles import resolve_profile
from .storage import (
    PROJECT_ROOT,
    project_relative,
    read_manifest,
    resolve_project_path,
    write_manifest,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def file_sha256(path: str | Path) -> str | None:
    resolved = resolve_project_path(path)
    if not resolved.exists() or not resolved.is_file():
        return None
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_hashes(paths: list[str | Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for value in paths:
        resolved = resolve_project_path(value)
        digest = file_sha256(resolved)
        if digest:
            hashes[project_relative(resolved)] = digest
    return hashes


def ffprobe_summary(path: str | Path) -> dict[str, Any]:
    resolved = resolve_project_path(path)
    if not resolved.exists():
        return {}
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate",
                "-of",
                "json",
                str(resolved),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
    except Exception:
        return {}
    summary: dict[str, Any] = {}
    try:
        summary["duration_seconds"] = round(
            float(data.get("format", {}).get("duration")), 3
        )
    except (TypeError, ValueError):
        pass
    if data.get("format", {}).get("size"):
        try:
            summary["size_bytes"] = int(data["format"]["size"])
        except (TypeError, ValueError):
            pass
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            summary["video_codec"] = stream.get("codec_name")
            summary["width"] = stream.get("width")
            summary["height"] = stream.get("height")
            summary["avg_frame_rate"] = stream.get("avg_frame_rate")
        elif stream.get("codec_type") == "audio":
            summary["audio_codec"] = stream.get("codec_name")
    return {
        key: value for key, value in summary.items() if value not in (None, "", [], {})
    }


def artifact_record(
    *,
    path: str | Path,
    stage: str,
    input_paths: list[str | Path] | None = None,
    provider: str | None = None,
    model: str | None = None,
    fresh: bool = True,
    skipped: bool = False,
    reused: bool = False,
    test_mode: bool = False,
    render_profile: str | None = None,
    command: list[str] | str | None = None,
    flags: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = resolve_project_path(path)
    profile = resolve_profile(render_profile)
    record: dict[str, Any] = {
        "path": project_relative(resolved),
        "stage": stage,
        "created_at": now_iso(),
        "fresh": bool(fresh),
        "reused": bool(reused),
        "skipped": bool(skipped),
        "test_mode": bool(test_mode),
        "mode": "TEST_MODE" if test_mode else "production",
        "render_profile": profile.name,
        "input_hashes": input_hashes(input_paths or []),
    }
    if provider:
        record["provider"] = provider
    if model:
        record["model"] = model
    if command:
        record["command"] = (
            shlex.join(command) if isinstance(command, list) else command
        )
    if flags:
        record["flags"] = {
            key: value for key, value in flags.items() if value is not None
        }
    if metadata:
        record.update(
            {
                key: value
                for key, value in metadata.items()
                if value not in (None, "", [], {})
            }
        )
    digest = file_sha256(resolved)
    if digest:
        record["sha256"] = digest
    media = ffprobe_summary(resolved)
    if media:
        record["media"] = media
    return {
        key: value for key, value in record.items() if value not in (None, "", [], {})
    }


def record_story_artifact(
    story_json_path: str | Path, key: str, record: dict[str, Any]
) -> dict[str, Any]:
    manifest = read_manifest(story_json_path)
    raw_provenance = manifest.get("provenance")
    provenance: dict[str, Any] = (
        raw_provenance if isinstance(raw_provenance, dict) else {}
    )
    raw_artifacts = provenance.get("artifacts")
    artifacts: dict[str, Any] = raw_artifacts if isinstance(raw_artifacts, dict) else {}
    artifacts[key] = record
    provenance["artifacts"] = artifacts
    provenance["updated_at"] = now_iso()
    manifest["provenance"] = provenance
    write_manifest(story_json_path, manifest)
    return manifest


def episode_manifest_path(episode_id: str) -> Path:
    return PROJECT_ROOT / "episodes" / episode_id / "episode_manifest.json"


def read_episode_manifest(episode_id: str) -> dict[str, Any]:
    path = episode_manifest_path(episode_id)
    if not path.exists():
        return {"episode_id": episode_id, "provenance": {"artifacts": {}}}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return (
        data
        if isinstance(data, dict)
        else {"episode_id": episode_id, "provenance": {"artifacts": {}}}
    )


def write_episode_manifest(episode_id: str, data: dict[str, Any]) -> Path:
    path = episode_manifest_path(episode_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    temp.replace(path)
    return path


def record_episode_artifact(
    episode_id: str,
    key: str,
    record: dict[str, Any],
    *,
    runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = read_episode_manifest(episode_id)
    manifest["episode_id"] = episode_id
    if runtime:
        manifest["runtime"] = runtime
    raw_provenance = manifest.get("provenance")
    provenance: dict[str, Any] = (
        raw_provenance if isinstance(raw_provenance, dict) else {}
    )
    raw_artifacts = provenance.get("artifacts")
    artifacts: dict[str, Any] = raw_artifacts if isinstance(raw_artifacts, dict) else {}
    artifacts[key] = record
    provenance["artifacts"] = artifacts
    provenance["updated_at"] = now_iso()
    manifest["provenance"] = provenance
    write_episode_manifest(episode_id, manifest)
    return manifest
