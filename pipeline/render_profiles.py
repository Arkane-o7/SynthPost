from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from pipeline import config


@dataclass(frozen=True)
class RenderProfile:
    name: str
    width: int
    height: int
    fps: int
    quality: str
    description: str


PROFILES: dict[str, RenderProfile] = {
    "preview": RenderProfile(
        name="preview",
        width=1280,
        height=720,
        fps=15,
        quality="fast",
        description="Fast low-resolution profile for cheap iteration.",
    ),
    "production": RenderProfile(
        name="production",
        width=1920,
        height=1080,
        fps=24,
        quality="final",
        description="Default 1080p final-quality profile.",
    ),
    "final_master": RenderProfile(
        name="final_master",
        width=3840,
        height=2160,
        fps=30,
        quality="highest",
        description="Optional highest-quality master profile.",
    ),
}


def resolve_profile(name: str | None = None) -> RenderProfile:
    selected = (name or config.get_settings().render.profile).strip().lower()
    if selected not in PROFILES:
        allowed = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown render profile `{selected}`. Expected one of: {allowed}.")
    return PROFILES[selected]


def profile_record(profile: str | RenderProfile | None = None) -> dict[str, Any]:
    resolved = profile if isinstance(profile, RenderProfile) else resolve_profile(profile)
    return asdict(resolved)


def apply_manifest_runtime(
    manifest: dict[str, Any],
    *,
    render_profile: str | RenderProfile | None = None,
    test_mode: bool | None = None,
) -> dict[str, Any]:
    profile = render_profile if isinstance(render_profile, RenderProfile) else resolve_profile(render_profile)
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    runtime = {
        **runtime,
        "render_profile": profile.name,
        "render_profile_settings": profile_record(profile),
    }
    if test_mode is not None:
        runtime["test_mode"] = bool(test_mode)
        runtime["mode"] = "TEST_MODE" if test_mode else "production"
    manifest["runtime"] = runtime
    manifest["render_profile"] = profile.name
    if test_mode is not None:
        manifest["test_mode"] = bool(test_mode)
        if test_mode:
            labels = manifest.get("labels") if isinstance(manifest.get("labels"), list) else []
            if "TEST_MODE" not in labels:
                labels.append("TEST_MODE")
            manifest["labels"] = labels
    return manifest
