from __future__ import annotations

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
    raise ValueError(
        f"Unsupported presenter provider {provider!r}; expected avatar_engine or video_file"
    )
