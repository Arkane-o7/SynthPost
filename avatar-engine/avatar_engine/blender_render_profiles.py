"""Deterministic EEVEE render profiles for the current CC anchor."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


BLENDER_CC_RENDER_PROFILES: dict[str, dict[str, Any]] = {
    "review": {
        "samples": 8,
        "resolution_scale": 0.75,
        "frame_format": "JPEG",
        "frame_quality": 92,
        "retain_frames": False,
    },
    "production": {
        "samples": 32,
        "resolution_scale": 1.0,
        "frame_format": "JPEG",
        "frame_quality": 95,
        "retain_frames": False,
    },
    "master": {
        "samples": 64,
        "resolution_scale": 1.0,
        "frame_format": "PNG",
        "png_compression": 15,
        "retain_frames": True,
    },
}

_FRAME_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


def resolve_blender_render_settings(
    render: dict[str, Any] | None,
    *,
    quality_gate: bool = False,
) -> dict[str, Any]:
    """Resolve a job render block into a bounded Blender driver contract."""

    render = dict(render or {})
    profile_name = str(
        render.get("blender_profile") or ("master" if quality_gate else "production")
    ).strip().lower()
    if profile_name not in BLENDER_CC_RENDER_PROFILES:
        allowed = ", ".join(sorted(BLENDER_CC_RENDER_PROFILES))
        raise ValueError(f"Unknown Blender CC render profile {profile_name!r}; expected {allowed}")

    settings = deepcopy(BLENDER_CC_RENDER_PROFILES[profile_name])
    settings["profile"] = profile_name
    for source, target in (
        ("blender_samples", "samples"),
        ("blender_resolution_scale", "resolution_scale"),
        ("frame_format", "frame_format"),
        ("frame_quality", "frame_quality"),
        ("png_compression", "png_compression"),
        ("retain_frames", "retain_frames"),
    ):
        if source in render:
            settings[target] = render[source]

    settings["samples"] = max(1, min(256, int(settings["samples"])))
    settings["resolution_scale"] = max(
        0.25, min(1.0, float(settings["resolution_scale"]))
    )
    frame_format = str(settings["frame_format"]).strip().upper()
    if frame_format == "JPG":
        frame_format = "JPEG"
    if frame_format not in _FRAME_EXTENSIONS:
        raise ValueError("frame_format must be JPEG, PNG, or WEBP")
    settings["frame_format"] = frame_format
    settings["frame_extension"] = _FRAME_EXTENSIONS[frame_format]
    settings["frame_quality"] = max(1, min(100, int(settings.get("frame_quality", 95))))
    settings["png_compression"] = max(
        0, min(100, int(settings.get("png_compression", 15)))
    )
    settings["retain_frames"] = bool(settings.get("retain_frames", False))

    presenter_pass = render.get("presenter_pass") or {}
    if not isinstance(presenter_pass, dict):
        raise ValueError("render.presenter_pass must be an object")
    crop = presenter_pass.get("crop")
    if crop is not None:
        if not isinstance(crop, list) or len(crop) != 4:
            raise ValueError("render.presenter_pass.crop must be [min_x, min_y, max_x, max_y]")
        crop = [float(value) for value in crop]
        if not all(0.0 <= value <= 1.0 for value in crop):
            raise ValueError("render.presenter_pass.crop values must be between 0 and 1")
        if crop[0] >= crop[2] or crop[1] >= crop[3]:
            raise ValueError("render.presenter_pass.crop must have positive width and height")
    transparent = bool(presenter_pass.get("transparent", False))
    if transparent:
        settings["frame_format"] = "PNG"
        settings["frame_extension"] = "png"
    settings["presenter_pass"] = {
        "enabled": bool(presenter_pass.get("enabled", bool(crop) or transparent)),
        "transparent": transparent,
        "crop": crop,
    }
    raw_windows = render.get("render_windows") or []
    if not isinstance(raw_windows, list):
        raise ValueError("render.render_windows must be an array")
    windows: list[dict[str, Any]] = []
    previous_end = 0.0
    for index, raw_window in enumerate(raw_windows):
        if not isinstance(raw_window, dict):
            raise ValueError(f"render.render_windows[{index}] must be an object")
        source_start = float(raw_window.get("source_start") or 0.0)
        source_end = float(raw_window.get("source_end") or 0.0)
        if source_start < 0 or source_end <= source_start:
            raise ValueError(
                f"render.render_windows[{index}] must have a positive source range"
            )
        if source_start < previous_end - 0.001:
            raise ValueError("render.render_windows must be ordered and non-overlapping")
        previous_end = source_end
        windows.append(
            {
                **raw_window,
                "source_start": source_start,
                "source_end": source_end,
            }
        )
    settings["render_windows"] = windows
    return settings
