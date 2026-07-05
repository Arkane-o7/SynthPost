"""CLI entrypoint: python -m avatar_engine.render_avatar

Usage examples
--------------
# TalkingHead renderer (explicit):
python -m avatar_engine.render_avatar --job jobs/talkinghead_ep01.json --renderer talkinghead

# Blender renderer (explicit):
python -m avatar_engine.render_avatar --job jobs/sample_job.json --renderer blender

# Use renderer from job JSON or AVATAR_ENGINE_RENDERER env var:
python -m avatar_engine.render_avatar --job jobs/talkinghead_ep01.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Allow imports from scripts/ and the repo root when run directly
_here = Path(__file__).resolve()
_repo_root = _here.parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from avatar_engine.renderer_base import AvatarJob
from avatar_engine.renderer_factory import (
    allow_renderer_fallback,
    get_renderer,
    resolve_renderer_name,
)

BROWSER_RENDERERS = {"talkinghead", "rocketbox"}


def _load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    try:
        import yaml  # type: ignore

        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001 - config defaults should be best-effort.
        print(
            f"[render_avatar] WARNING: Could not load config {config_path}: {exc}",
            file=sys.stderr,
        )
        return {}


def _merge_missing(base: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base) if isinstance(base, dict) else {}
    for key, value in defaults.items():
        if key not in merged or merged[key] in (None, ""):
            merged[key] = value
    return merged


def apply_config_defaults(
    raw_job: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    """Fill missing browser-render job fields from config/default.yaml.

    Job JSON remains the highest-priority source. This only supplies defaults so
    new jobs do not have to rediscover camera framing, background, or voice
    settings for the CC4/Reallusion browser runtime.
    """
    job = dict(raw_job)
    renderer = (
        str(job.get("renderer") or os.environ.get("AVATAR_ENGINE_RENDERER") or "")
        .strip()
        .lower()
    )
    if renderer and renderer not in BROWSER_RENDERERS:
        return job

    browser_config = (
        config.get("talkinghead") if isinstance(config.get("talkinghead"), dict) else {}
    )
    tts_config = config.get("tts") if isinstance(config.get("tts"), dict) else {}

    if isinstance(tts_config, dict) and tts_config:
        voice_defaults = {
            "engine": tts_config.get("engine"),
            "voice_id": tts_config.get("voice_id") or tts_config.get("voice"),
            "voice": tts_config.get("voice") or tts_config.get("voice_id"),
            "speed": tts_config.get("speed"),
            "sample_rate": tts_config.get("sample_rate"),
            "lang_code": tts_config.get("lang_code"),
        }
        job["voice"] = _merge_missing(
            job.get("voice") if isinstance(job.get("voice"), dict) else {},
            {
                key: value
                for key, value in voice_defaults.items()
                if value not in (None, "")
            },
        )

    avatar_defaults = {
        "asset_path": browser_config.get("default_avatar_asset"),
        "metadata_path": browser_config.get("default_avatar_metadata"),
        "body_form": browser_config.get("default_avatar_body_form"),
    }
    job["avatar"] = _merge_missing(
        job.get("avatar") if isinstance(job.get("avatar"), dict) else {},
        {
            key: value
            for key, value in avatar_defaults.items()
            if value not in (None, "")
        },
    )

    default_camera = (
        browser_config.get("default_camera")
        if isinstance(browser_config.get("default_camera"), dict)
        else {}
    )
    job["camera"] = _merge_missing(
        job.get("camera") if isinstance(job.get("camera"), dict) else {},
        default_camera,
    )

    default_overrides = (
        browser_config.get("default_camera_overrides")
        if isinstance(browser_config.get("default_camera_overrides"), dict)
        else {}
    )
    job["camera_overrides"] = _merge_missing(
        job.get("camera_overrides")
        if isinstance(job.get("camera_overrides"), dict)
        else {},
        default_overrides,
    )

    render_defaults = {"background": browser_config.get("default_render_background")}
    job["render"] = _merge_missing(
        job.get("render") if isinstance(job.get("render"), dict) else {},
        {
            key: value
            for key, value in render_defaults.items()
            if value not in (None, "")
        },
    )

    default_animation = (
        browser_config.get("default_animation")
        if isinstance(browser_config.get("default_animation"), dict)
        else {}
    )
    job["animation"] = _merge_missing(
        job.get("animation") if isinstance(job.get("animation"), dict) else {},
        default_animation,
    )

    default_face = (
        browser_config.get("default_face")
        if isinstance(browser_config.get("default_face"), dict)
        else {}
    )
    job["face"] = _merge_missing(
        job.get("face") if isinstance(job.get("face"), dict) else {},
        default_face,
    )

    return job


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m avatar_engine.render_avatar",
        description="Render a talking-avatar clip using the TalkingHead or Blender renderer.",
    )
    parser.add_argument(
        "--job", required=True, help="Path to the avatar job JSON file."
    )
    parser.add_argument(
        "--renderer",
        choices=["talkinghead", "rocketbox", "blender"],
        default=None,
        help="Override the renderer (default: from job or AVATAR_ENGINE_RENDERER env var).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config YAML (default: config/default.yaml).",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run in test mode (relaxed file checks for CI).",
    )

    args = parser.parse_args(argv)

    job_path = Path(args.job)
    if not job_path.is_absolute():
        job_path = _repo_root / job_path
    if not job_path.exists():
        print(f"[render_avatar] ERROR: Job file not found: {job_path}", file=sys.stderr)
        return 1

    config_path = (
        Path(args.config) if args.config else _repo_root / "config" / "default.yaml"
    )
    if not config_path.is_absolute():
        config_path = _repo_root / config_path

    config = _load_config(config_path)

    with job_path.open("r", encoding="utf-8") as fh:
        raw_job = json.load(fh)

    raw_job = apply_config_defaults(raw_job, config)
    job = AvatarJob(raw=raw_job, job_path=job_path)

    # Determine which renderer to use (may raise ValueError for unknown names)
    try:
        resolved_renderer = resolve_renderer_name(job, override=args.renderer)
    except ValueError as exc:
        print(f"[render_avatar] ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"[render_avatar] Job:      {job_path}")
    print(f"[render_avatar] Renderer: {resolved_renderer}")
    print(f"[render_avatar] Episode:  {job.episode_id}  Story: {job.story_id}")

    renderer = get_renderer(job, override=args.renderer, config_path=config_path)

    result = renderer.render(job)

    # Print summary
    if result.status == "pass":
        print(f"[render_avatar] DONE  — output: {result.output_path}")
        print(
            f"[render_avatar] Wall time: {result.wall_time_seconds:.1f}s  "
            f"Realtime factor: {result.realtime_factor:.2f}x"
        )
        if result.warnings:
            for w in result.warnings:
                print(f"[render_avatar] WARNING: {w}")
        return 0
    else:
        print(f"[render_avatar] FAILED — {result.error}", file=sys.stderr)

        if allow_renderer_fallback() and resolved_renderer != "blender":
            print(
                "[render_avatar] AVATAR_ENGINE_ALLOW_RENDERER_FALLBACK=1 is set; "
                "retrying with blender renderer.",
                file=sys.stderr,
            )
            from avatar_engine.renderer_factory import get_renderer as _get

            blender_renderer = _get(job, override="blender", config_path=config_path)
            fallback_result = blender_renderer.render(job)
            if fallback_result.status == "pass":
                print(
                    f"[render_avatar] Blender fallback succeeded: {fallback_result.output_path}"
                )
                return 0
            print(
                f"[render_avatar] Blender fallback also failed: {fallback_result.error}",
                file=sys.stderr,
            )

        return 1


if __name__ == "__main__":
    sys.exit(main())
