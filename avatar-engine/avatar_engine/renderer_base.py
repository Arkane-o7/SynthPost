"""Abstract base class for all avatar renderers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AvatarJob:
    """Typed wrapper around a raw job dict, with convenience accessors."""

    raw: dict[str, Any]
    job_path: Path | None = None

    # ------------------------------------------------------------------ #
    # Generic access                                                        #
    # ------------------------------------------------------------------ #

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.raw

    # ------------------------------------------------------------------ #
    # Typed accessors                                                       #
    # ------------------------------------------------------------------ #

    @property
    def renderer(self) -> str:
        return str(self.raw.get("renderer", "blender")).strip().lower()

    @property
    def episode_id(self) -> str:
        return str(self.raw.get("episode_id", self.raw.get("job_id", "")))

    @property
    def story_id(self) -> str:
        return str(self.raw.get("story_id", ""))

    @property
    def script_text(self) -> str:
        return str(self.raw.get("script_text", self.raw.get("script", "")))

    # Avatar sub-object
    @property
    def avatar(self) -> dict[str, Any]:
        return dict(self.raw.get("avatar", {}))

    @property
    def avatar_asset_path(self) -> str:
        return str(self.avatar.get("asset_path", ""))

    @property
    def avatar_metadata_path(self) -> str:
        return str(self.avatar.get("metadata_path", ""))

    # Camera sub-object
    @property
    def camera(self) -> dict[str, Any]:
        return dict(self.raw.get("camera", {}))

    @property
    def camera_width(self) -> int:
        return int(self.camera.get("width", 1920))

    @property
    def camera_height(self) -> int:
        return int(self.camera.get("height", 1080))

    @property
    def camera_fps(self) -> int:
        return int(self.camera.get("fps", 24))

    @property
    def camera_name(self) -> str:
        return str(self.camera.get("name", "front_medium"))

    @property
    def camera_duration(self) -> float:
        return float(self.camera.get("duration_seconds", 0.0))

    # Render sub-object
    @property
    def render(self) -> dict[str, Any]:
        return dict(self.raw.get("render", {}))

    @property
    def output_path(self) -> str:
        return str(self.render.get("output_path", self.raw.get("output_path", "")))

    @property
    def preview_png_path(self) -> str:
        return str(self.render.get("preview_png_path", ""))

    # Face sub-object
    @property
    def face(self) -> dict[str, Any]:
        return dict(self.raw.get("face", {}))

    @property
    def face_mode(self) -> str:
        return str(self.face.get("mode", "3d_viseme")).strip().lower()

    @property
    def body_form(self) -> str:
        """Body form for TalkingHead (M/F/N).  Reads from avatar.body_form
        first, then falls back to the top-level key, then defaults to 'M'."""
        return str(
            self.avatar.get("body_form") or self.raw.get("body_form") or "M"
        ).upper()

    # Audio / viseme paths
    @property
    def audio_path(self) -> str:
        return str(self.raw.get("audio_path", ""))

    @property
    def viseme_path(self) -> str:
        return str(self.raw.get("viseme_path", ""))


# --------------------------------------------------------------------------- #


@dataclass
class AvatarRenderResult:
    """Returned by every AvatarRenderer.render() call."""

    renderer: str
    status: str  # "pass" | "fail"
    output_path: str | None = None
    preview_png_path: str | None = None
    manifest_path: str | None = None
    stats_path: str | None = None
    wall_time_seconds: float = 0.0
    realtime_factor: float = 0.0
    fps: int = 24
    resolution: str = "1920x1080"
    frame_count: int = 0
    face_mode: str = "unknown"
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_stats_dict(self) -> dict[str, Any]:
        return {
            "renderer": self.renderer,
            "status": self.status,
            "fps": self.fps,
            "resolution": self.resolution,
            "wall_time_seconds": self.wall_time_seconds,
            "realtime_factor": self.realtime_factor,
            "frame_count": self.frame_count,
            "face_mode": self.face_mode,
            "output_path": self.output_path,
            "preview_png_path": self.preview_png_path,
            "manifest_path": self.manifest_path,
            "warnings": self.warnings,
            "error": self.error,
        }


# --------------------------------------------------------------------------- #


class AvatarRenderer(ABC):
    """Abstract base for all avatar renderers."""

    name: str = "base"

    @abstractmethod
    def render(self, job: AvatarJob) -> AvatarRenderResult:
        """Execute the render job and return a result record."""
        ...

    def validate_job(self, job: AvatarJob) -> None:
        """Pre-render validation.  Raises ValueError on any problem."""
        pass
