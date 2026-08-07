"""Production current-CC-model renderer using an isolated Blender EEVEE scene."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from avatar_engine.avatar_validator import load_avatar_metadata, validate_material_profile
from avatar_engine.blender_render_profiles import resolve_blender_render_settings
from avatar_engine.motion_library import load_motion_library
from avatar_engine.quality_gate import quality_gate_diagnostics, validate_quality_gate_job
from avatar_engine.renderer_base import AvatarJob, AvatarRenderer, AvatarRenderResult
from avatar_engine.viseme_mapping import convert_rhubarb_json_to_talkinghead, viseme_mapping_for_avatar


def mux_sparse_windows(
    *,
    ffmpeg: str,
    output_mp4: Path,
    audio_path: Path,
    frames_dir: Path,
    frame_extension: str,
    fps: int,
    windows: list[dict[str, Any]],
    temp_dir: Path,
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
    """Mux rendered source-time windows into one compact presenter clip."""

    segment_paths: list[Path] = []
    resolved_windows: list[dict[str, Any]] = []
    clip_cursor = 0.0
    for window in windows:
        index = int(window["index"])
        frame_count = int(window["frame_count"])
        duration = frame_count / float(fps)
        segment_path = temp_dir / f"window_{index:03d}.mp4"
        pattern = frames_dir / f"window_{index:03d}" / f"frame_%04d.{frame_extension}"
        segment_mux = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-framerate",
                str(fps),
                "-start_number",
                str(window["start_frame"]),
                "-i",
                str(pattern),
                "-ss",
                str(window["source_start"]),
                "-t",
                f"{duration:.6f}",
                "-i",
                str(audio_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-crf",
                "20",
                "-preset",
                "fast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(segment_path),
            ],
            capture_output=True,
            text=True,
        )
        if segment_mux.returncode != 0:
            return segment_mux, resolved_windows
        segment_paths.append(segment_path)
        resolved_windows.append(
            {
                **window,
                "clip_start": round(clip_cursor, 6),
                "clip_end": round(clip_cursor + duration, 6),
            }
        )
        clip_cursor += duration

    if len(segment_paths) == 1:
        shutil.copy2(segment_paths[0], output_mp4)
        return subprocess.CompletedProcess([], 0, "", ""), resolved_windows

    concat_path = temp_dir / "windows.ffconcat"
    concat_path.write_text(
        "ffconcat version 1.0\n"
        + "".join(f"file '{path.as_posix()}'\n" for path in segment_paths),
        encoding="utf-8",
    )
    concat = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            str(output_mp4),
        ],
        capture_output=True,
        text=True,
    )
    return concat, resolved_windows


def build_blender_driver_job(
    *,
    root: Path,
    job: AvatarJob,
    metadata_path: Path,
    metadata: dict[str, Any],
    output_dir: Path,
    scene_path: Path,
    diagnostics_path: Path,
    visemes: list[str],
    vtimes: list[float],
    vdurations: list[float],
    motion_library: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert a modern avatar job into the isolated Blender driver contract."""
    return {
        "asset_path": str(root / job.avatar_asset_path),
        "avatar_root": str(metadata_path.parent),
        "material_profile": metadata["material_profile"],
        "camera": job.camera,
        "duration_seconds": job.camera_duration,
        "distance_multiplier": (job.raw.get("camera_overrides") or {}).get(
            "distance_multiplier", 3.5
        ),
        "output_dir": str(output_dir),
        "scene_path": str(scene_path),
        "diagnostics_path": str(diagnostics_path),
        "animation": job.raw.get("animation") or {},
        "performance": job.raw.get("performance") or {},
        "motion_library": motion_library,
        "render_settings": resolve_blender_render_settings(
            job.render, quality_gate="quality_gate" in job.raw
        ),
        "precomputed_visemes": {
            "visemes": visemes,
            "vtimes": vtimes,
            "vdurations": vdurations,
        },
    }


class BlenderCCAvatarRenderer(AvatarRenderer):
    name = "blender_cc"

    def __init__(self, config_path: Path | None = None) -> None:
        self._root = Path(__file__).resolve().parents[1]
        self._config_path = config_path or self._root / "config" / "default.yaml"

    def validate_job(self, job: AvatarJob) -> None:
        required = [job.avatar_asset_path, job.avatar_metadata_path, job.audio_path, job.viseme_path, job.output_path]
        if not all(required):
            raise ValueError("blender_cc requires avatar, audio, viseme, and output paths")
        for relative in required[:4]:
            if not (self._root / relative).is_file():
                raise FileNotFoundError(f"blender_cc input not found: {relative}")

    def _blender_path(self) -> Path | None:
        configured = "blender"
        if self._config_path.exists():
            try:
                import yaml

                data = yaml.safe_load(self._config_path.read_text(encoding="utf-8")) or {}
                configured = str((data.get("tools") or {}).get("blender") or configured)
            except Exception:
                pass
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return candidate
        found = shutil.which(configured)
        return Path(found) if found else None

    def render(self, job: AvatarJob) -> AvatarRenderResult:
        started = time.monotonic()
        try:
            self.validate_job(job)
        except (ValueError, FileNotFoundError) as exc:
            return AvatarRenderResult(renderer=self.name, status="fail", error=str(exc))
        if "quality_gate" in job.raw:
            quality_errors = validate_quality_gate_job(job.raw)
            if quality_errors:
                return AvatarRenderResult(renderer=self.name, status="fail", error="Invalid quality gate: " + "; ".join(quality_errors))
        blender = self._blender_path()
        if blender is None:
            return AvatarRenderResult(renderer=self.name, status="fail", error="Blender executable not found")

        metadata_path = self._root / job.avatar_metadata_path
        metadata = load_avatar_metadata(metadata_path)
        material_validation = validate_material_profile(metadata, metadata_path.parent)
        if material_validation["status"] != "pass":
            return AvatarRenderResult(renderer=self.name, status="fail", error=f"blender_cc requires a valid material profile: {material_validation}")
        viseme_raw = json.loads((self._root / job.viseme_path).read_text(encoding="utf-8"))
        visemes, vtimes, vdurations = convert_rhubarb_json_to_talkinghead(viseme_raw, viseme_mapping_for_avatar(metadata))
        try:
            motion_library = load_motion_library(self._root, metadata)
            render_settings = resolve_blender_render_settings(
                job.render, quality_gate="quality_gate" in job.raw
            )
        except (ValueError, json.JSONDecodeError) as exc:
            return AvatarRenderResult(renderer=self.name, status="fail", error=str(exc))
        require_motion_library = bool(
            (job.raw.get("animation") or {}).get("require_motion_library", False)
        )
        if require_motion_library and not (motion_library or {}).get(
            "blender_library_available", False
        ):
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error="A Blender motion library is required but no generated CC Action library is available.",
            )

        output_mp4 = self._root / job.output_path
        output_dir = output_mp4.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        diagnostics_path = output_dir / "blender_diagnostics.json"
        scene_path = output_dir / "synthpost_anchor_v2.blend"
        temp_dir = self._root / "assets" / "temp" / f"blender_cc_{uuid.uuid4().hex}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        driver_job_path = temp_dir / "driver_job.json"
        driver_job = build_blender_driver_job(
            root=self._root,
            job=job,
            metadata_path=metadata_path,
            metadata=metadata,
            output_dir=output_dir,
            scene_path=scene_path,
            diagnostics_path=diagnostics_path,
            visemes=visemes,
            vtimes=vtimes,
            vdurations=vdurations,
            motion_library=motion_library,
        )
        driver_job_path.write_text(json.dumps(driver_job, indent=2) + "\n", encoding="utf-8")
        command = [
            str(blender), "--background", "--factory-startup", "--python",
            str(self._root / "blender" / "cc_anchor_driver.py"), "--", "--job", str(driver_job_path),
        ]
        completed = subprocess.run(command, cwd=self._root, capture_output=True, text=True)
        (output_dir / "blender_stdout.log").write_text(completed.stdout, encoding="utf-8")
        (output_dir / "blender_stderr.log").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0 or not diagnostics_path.is_file():
            tail = completed.stderr[-1200:].strip()
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error=(
                    f"Blender driver failed (process exit {completed.returncode}); "
                    f"see {output_dir / 'blender_stderr.log'}"
                    + (f": {tail}" if tail else "")
                ),
            )

        frame_extension = str(render_settings["frame_extension"])
        frame_dir = output_dir / "frames"
        frame_pattern = frame_dir / f"frame_%04d.{frame_extension}"
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return AvatarRenderResult(renderer=self.name, status="fail", error="ffmpeg not found")
        blender_diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        rendered_windows = list(blender_diagnostics.get("render_windows") or [])
        if rendered_windows:
            mux, rendered_windows = mux_sparse_windows(
                ffmpeg=ffmpeg,
                output_mp4=output_mp4,
                audio_path=self._root / job.audio_path,
                frames_dir=frame_dir,
                frame_extension=frame_extension,
                fps=job.camera_fps,
                windows=rendered_windows,
                temp_dir=temp_dir,
            )
        else:
            mux = subprocess.run(
                [
                    ffmpeg, "-y", "-framerate", str(job.camera_fps), "-start_number", "1", "-i", str(frame_pattern),
                    "-i", str(self._root / job.audio_path), "-map", "0:v:0", "-map", "1:a:0", "-r", str(job.camera_fps),
                    "-c:v", "libx264", "-crf", "20", "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output_mp4),
                ],
                capture_output=True,
                text=True,
            )
        if mux.returncode != 0:
            return AvatarRenderResult(renderer=self.name, status="fail", error=f"FFmpeg mux failed: {mux.stderr[-2000:]}")
        frame_count = int(blender_diagnostics.get("frame_count") or 0)
        clip_duration = frame_count / float(job.camera_fps)
        preview = self._root / job.preview_png_path
        preview.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [ffmpeg, "-y", "-ss", str(max(0.0, clip_duration / 2)), "-i", str(output_mp4), "-frames:v", "1", str(preview)],
            capture_output=True,
        )

        frame_paths = list(frame_dir.rglob(f"*.{frame_extension}"))
        frame_bytes = sum(path.stat().st_size for path in frame_paths)
        retained_frames = bool(render_settings["retain_frames"])
        if not retained_frames:
            shutil.rmtree(frame_dir, ignore_errors=True)
        wall = time.monotonic() - started
        process_overhead = max(
            0.0,
            wall - float(blender_diagnostics.get("setup_seconds", 0)) - float(blender_diagnostics.get("render_seconds", 0)),
        )
        manifest = {
            "renderer": self.name,
            "episode_id": job.episode_id,
            "story_id": job.story_id,
            "camera": job.camera,
            "face_mode": job.face_mode,
            "wall_time_seconds": round(wall, 3),
            "realtime_factor": round(clip_duration / wall, 3),
            "source_realtime_factor": round(job.camera_duration / wall, 3),
            "startup_and_mux_seconds": round(process_overhead, 3),
            "clip_duration_seconds": round(clip_duration, 6),
            "source_duration_seconds": job.camera_duration,
            "rendered_duration_seconds": round(clip_duration, 6),
            "skipped_duration_seconds": round(
                max(0.0, job.camera_duration - clip_duration), 6
            ),
            "render_windows": rendered_windows,
            "fps": job.camera_fps,
            "frame_count": frame_count,
            "resolution": blender_diagnostics.get(
                "output_resolution", f"{job.camera_width}x{job.camera_height}"
            ),
            "output_path": str(output_mp4),
            "preview_png_path": str(preview),
            "output_size_bytes": output_mp4.stat().st_size,
            "frame_sequence_bytes": frame_bytes,
            "frame_format": render_settings["frame_format"],
            "frames_retained": retained_frames,
            "render_profile": render_settings["profile"],
            "quality_gate": quality_gate_diagnostics(job.raw, self._root),
            "material_validation": material_validation,
            "renderer_diagnostics": blender_diagnostics,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path = output_dir / "avatar_render_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        stats_path = output_dir / "render_stats.json"
        stats_path.write_text(
            json.dumps(
                {key: manifest[key] for key in ("renderer", "wall_time_seconds", "realtime_factor", "fps", "frame_count", "resolution", "output_size_bytes")},
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        shutil.rmtree(temp_dir, ignore_errors=True)
        return AvatarRenderResult(
            renderer=self.name,
            status="pass",
            output_path=str(output_mp4),
            preview_png_path=str(preview),
            manifest_path=str(manifest_path),
            stats_path=str(stats_path),
            wall_time_seconds=round(wall, 3),
            realtime_factor=round(clip_duration / wall, 3),
            fps=job.camera_fps,
            resolution=str(manifest["resolution"]),
            frame_count=frame_count,
            face_mode=job.face_mode,
            metadata={"blender": blender_diagnostics},
        )
