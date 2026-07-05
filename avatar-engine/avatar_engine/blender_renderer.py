"""BlenderAvatarRenderer — wraps the existing scripts/run_job.py pipeline.

This renderer is the backward-compatible path.  It delegates to the existing
Blender-based pipeline unchanged and maps the result back to AvatarRenderResult.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from avatar_engine.renderer_base import AvatarJob, AvatarRenderer, AvatarRenderResult


class BlenderAvatarRenderer(AvatarRenderer):
    """Delegates to scripts/run_job.py using the existing Blender pipeline."""

    name = "blender"

    def __init__(
        self, config_path: Path | None = None, extra_flags: list[str] | None = None
    ) -> None:
        self._config_path = config_path
        self._extra_flags: list[str] = extra_flags or []

    # ---------------------------------------------------------------------- #
    # AvatarRenderer interface                                                 #
    # ---------------------------------------------------------------------- #

    def validate_job(self, job: AvatarJob) -> None:
        """Check that the job at least has the fields run_job.py requires."""
        required = {"job_id", "script", "character", "fps", "resolution", "output_path"}
        # TalkingHead-format jobs use different keys; allow either form
        legacy_keys = set(job.raw.keys())
        if not required.issubset(legacy_keys):
            missing = sorted(required - legacy_keys)
            # If the caller has a talkinghead-format job, warn but don't fail here —
            # the Blender path cannot render it anyway, so we give a clear error.
            raise ValueError(
                f"BlenderAvatarRenderer requires legacy job fields: {missing}. "
                "Either fix the job or switch to renderer=talkinghead."
            )

    def render(self, job: AvatarJob) -> AvatarRenderResult:
        root = _project_root()
        run_job_script = root / "scripts" / "run_job.py"
        if not run_job_script.exists():
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error=f"Blender pipeline script not found: {run_job_script}",
            )

        if job.job_path is None:
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error="BlenderAvatarRenderer requires job.job_path to be set (path to the job JSON file).",
            )

        config_path = self._config_path or (root / "config" / "default.yaml")

        cmd = [
            sys.executable,
            str(run_job_script),
            str(job.job_path),
            "--config",
            str(config_path),
        ]
        cmd.extend(self._extra_flags)

        t0 = time.monotonic()
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error=f"Blender pipeline exited with code {exc.returncode}.",
            )

        wall_time = time.monotonic() - t0

        output_path = job.output_path or str(
            root / "assets" / "output" / f"{job.episode_id}.mp4"
        )
        return AvatarRenderResult(
            renderer=self.name,
            status="pass",
            output_path=output_path,
            wall_time_seconds=round(wall_time, 3),
            fps=job.camera_fps or int(job.raw.get("fps", 24)),
            resolution=(
                f"{job.camera_width}x{job.camera_height}"
                if "camera" in job.raw
                else "{}x{}".format(*job.raw.get("resolution", [1920, 1080]))
            ),
            face_mode=str(job.raw.get("face_mode", "legacy_blender")),
        )


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]
