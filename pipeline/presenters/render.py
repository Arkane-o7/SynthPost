from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.observability import safe_text
from pipeline.provenance import artifact_record, ffprobe_summary, record_story_artifact
from pipeline.storage import (
    project_relative,
    read_manifest,
    resolve_project_path,
    write_manifest,
)


def _production(manifest: dict[str, Any]) -> dict[str, Any]:
    channel = manifest.get("channel")
    if not isinstance(channel, dict):
        return {}
    production = channel.get("production")
    return production if isinstance(production, dict) else {}


def _use_video_presenter(
    story_json_path: str | Path,
    manifest: dict[str, Any],
    *,
    test_mode: bool,
    render_profile: str,
) -> dict[str, Any]:
    production = _production(manifest)
    configured = str(production.get("presenter_asset_path") or "").strip()
    if not configured:
        raise ValueError("video_file presenter requires presenter_asset_path")
    video_path = resolve_project_path(configured)
    if not video_path.is_file():
        raise FileNotFoundError(f"Configured presenter video is missing: {video_path}")
    probe = ffprobe_summary(video_path)
    if not probe.get("video_codec"):
        raise ValueError(f"Configured presenter is not a readable video: {video_path}")
    if not probe.get("audio_codec"):
        raise ValueError(
            "video_file presenter must include its synchronized narration audio; "
            f"no audio stream was found in {video_path}"
        )
    narration = manifest.get("narration") if isinstance(manifest.get("narration"), dict) else {}
    expected = float(narration.get("duration_seconds") or 0.0)
    actual = float(probe.get("duration_seconds") or 0.0)
    if expected and actual and abs(expected - actual) > 0.35:
        raise ValueError(
            "Presenter video duration does not match canonical narration: "
            f"presenter={actual:.3f}s narration={expected:.3f}s"
        )
    direction = {
        "job_id": str(manifest["story_id"]),
        "presenter_provider": "video_file",
        "presenter_profile": production.get("presenter_style"),
        "anchor_output_path": project_relative(video_path),
        "estimated_duration_seconds": actual or expected,
        "duration_source": "presenter_video_probe",
        "avatar_render_background": production.get("presenter_background"),
        "render_profile": render_profile,
        "test_mode": bool(test_mode),
    }
    manifest["direction"] = {key: value for key, value in direction.items() if value not in (None, "")}
    write_manifest(story_json_path, manifest)
    record_story_artifact(
        story_json_path,
        "presenter_video",
        artifact_record(
            path=video_path,
            stage="presenter",
            input_paths=[story_json_path, video_path],
            provider="video_file",
            model=str(production.get("presenter_style") or "external_presenter"),
            fresh=True,
            reused=True,
            test_mode=test_mode,
            render_profile=render_profile,
            metadata={"channel_id": manifest.get("channel_id"), **probe},
        ),
    )
    print(safe_text(f"[presenter] Using external presenter video: {video_path}"))
    return manifest["direction"]


def _prepare_png_puppet(
    story_json_path: str | Path,
    manifest: dict[str, Any],
    *,
    test_mode: bool,
    render_profile: str,
) -> dict[str, Any]:
    """Pin a deterministic PNG character pack to the canonical narration clock."""

    production = _production(manifest)
    configured = str(production.get("presenter_asset_path") or "").strip()
    if not configured:
        raise ValueError("png_puppet presenter requires presenter_asset_path")
    character_path = resolve_project_path(configured)
    if not character_path.is_file():
        raise FileNotFoundError(
            f"Configured PNG presenter pack is missing: {character_path}"
        )
    try:
        character = json.loads(character_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"PNG presenter pack is not valid JSON: {character_path}") from exc
    if character.get("contract_version") != "synthea.presenter.png_puppet.v1":
        raise ValueError(
            "PNG presenter pack must use contract_version "
            "'synthea.presenter.png_puppet.v1'"
        )

    poses = character.get("poses")
    if not isinstance(poses, dict):
        raise ValueError("PNG presenter pack requires a poses object")
    pose_paths: dict[str, str] = {}
    for raw_name, raw_path in poses.items():
        name = str(raw_name).strip()
        configured_pose = str(raw_path or "").strip()
        if not name or not configured_pose:
            continue
        pose_path = resolve_project_path(configured_pose)
        if not pose_path.is_file() or pose_path.suffix.lower() != ".png":
            raise FileNotFoundError(
                f"PNG presenter pose {name!r} is missing or not a PNG: {pose_path}"
            )
        pose_paths[name] = project_relative(pose_path)
    if "neutral" not in pose_paths:
        raise ValueError("PNG presenter pack requires poses.neutral")
    pose_paths.setdefault("speaking", pose_paths["neutral"])

    narration = (
        manifest.get("narration")
        if isinstance(manifest.get("narration"), dict)
        else {}
    )
    narration_configured = str(narration.get("audio_path") or "").strip()
    if not narration_configured:
        raise ValueError("png_puppet presenter requires canonical narration.audio_path")
    narration_path = resolve_project_path(narration_configured)
    if not narration_path.is_file():
        raise FileNotFoundError(
            f"Canonical narration audio is missing: {narration_path}"
        )
    narration_probe = ffprobe_summary(narration_path)
    if not narration_probe.get("audio_codec"):
        raise ValueError(
            f"Canonical narration is not readable audio: {narration_path}"
        )
    beats = narration.get("beats")
    if not isinstance(beats, list) or not beats:
        raise ValueError("png_puppet presenter requires exact narration.beats timing")

    expected = float(narration.get("duration_seconds") or 0.0)
    actual = float(narration_probe.get("duration_seconds") or 0.0)
    duration = expected or actual
    if duration <= 0:
        raise ValueError("PNG presenter narration duration must be positive")
    if expected and actual and abs(expected - actual) > 0.35:
        raise ValueError(
            "Canonical narration duration does not match its audio probe: "
            f"manifest={expected:.3f}s audio={actual:.3f}s"
        )

    direction = {
        "job_id": str(manifest["story_id"]),
        "presenter_provider": "png_puppet",
        "presenter_renderer": "remotion",
        "presenter_profile": production.get("presenter_style"),
        "presenter_manifest_path": project_relative(character_path),
        "presenter_neutral_path": pose_paths["neutral"],
        "presenter_speaking_path": pose_paths["speaking"],
        "presenter_pose_paths": pose_paths,
        "narration_audio_path": project_relative(narration_path),
        "estimated_duration_seconds": duration,
        "duration_source": "canonical_narration",
        "avatar_render_background": production.get("presenter_background"),
        "render_profile": render_profile,
        "test_mode": bool(test_mode),
    }
    manifest["direction"] = {
        key: value for key, value in direction.items() if value not in (None, "")
    }
    write_manifest(story_json_path, manifest)
    record_story_artifact(
        story_json_path,
        "presenter_character",
        artifact_record(
            path=character_path,
            stage="presenter",
            input_paths=[
                story_json_path,
                character_path,
                *[resolve_project_path(value) for value in pose_paths.values()],
                narration_path,
            ],
            provider="png_puppet",
            model=str(character.get("character_id") or "png_character"),
            fresh=True,
            reused=True,
            test_mode=test_mode,
            render_profile=render_profile,
            metadata={
                "channel_id": manifest.get("channel_id"),
                "poses": pose_paths,
                "timing_source": narration.get("timing_source"),
                **narration_probe,
            },
        ),
    )
    print(
        safe_text(
            f"[presenter] Prepared PNG narrator {character.get('name') or character_path.name} "
            f"against {len(beats)} exact narration beats"
        )
    )
    return manifest["direction"]


def render_presenter(
    story_json_path: str | Path,
    *,
    force: bool = False,
    render: bool = True,
    test_mode: bool = False,
    render_profile: str = "production",
) -> dict[str, Any]:
    """Render the episode-pinned presenter through a replaceable provider."""

    manifest = read_manifest(story_json_path)
    production = _production(manifest)
    provider = str(production.get("presenter_provider") or "avatar_engine").strip()
    if provider == "avatar_engine":
        from pipeline.direction import avatar

        return avatar.run(
            story_json_path,
            force=force,
            render=render,
            test_mode=test_mode,
            render_profile=render_profile,
        )
    if provider == "video_file":
        return _use_video_presenter(
            story_json_path,
            manifest,
            test_mode=test_mode,
            render_profile=render_profile,
        )
    if provider == "png_puppet":
        return _prepare_png_puppet(
            story_json_path,
            manifest,
            test_mode=test_mode,
            render_profile=render_profile,
        )
    raise ValueError(
        f"Unsupported presenter provider {provider!r}; expected avatar_engine, "
        "video_file, or png_puppet"
    )
