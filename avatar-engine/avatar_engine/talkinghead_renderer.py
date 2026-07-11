"""TalkingHeadAvatarRenderer — browser-based 3D avatar renderer.

Pipeline
--------
1. Validate job schema and avatar metadata.
2. Ensure the web_avatar_runtime is built (runs ``npm ci && npm run build``
   if ``dist/`` is absent).
3. Write a resolved job JSON (with absolute HTTP-routable paths) to the
   temp directory served by the local HTTP server.
4. Start a Python HTTP server at a free port, serving the entire project
   root (read-only) so the browser can reach GLB, audio, and rhubarb files.
5. Launch Chromium via Playwright with:
   - solid green background (chroma key)
   - video recording enabled
   - autoplay policy unlocked
6. Navigate to ``http://localhost:<port>/web_avatar_runtime/dist/``
   with ``?job=<relative-temp-job-path>`` as a query param.
7. The browser runtime loads the avatar, decodes the audio, converts
   Rhubarb cues to Oculus visemes, and calls TalkingHead.speakAudio().
8. Playwright polls for ``window.__renderStatus === "done"``.
9. The page is closed, triggering Playwright to flush the WebM recording.
10. FFmpeg muxes the original audio WAV into the WebM to produce the
    requested H.264 MP4.
11. FFmpeg extracts a mid-clip preview PNG.
12. Manifest and render-stats JSON are written next to the MP4.

Export method
-------------
Option B (Playwright real-time canvas capture) + Option C (green screen).
Alpha WebM and Remotion-native rendering are deferred (see design doc).
"""

from __future__ import annotations

import base64
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from avatar_engine.avatar_validator import (
    AvatarValidationError,
    load_avatar_metadata,
    validate_avatar_for_talkinghead,
)
from avatar_engine.renderer_base import AvatarJob, AvatarRenderer, AvatarRenderResult
from avatar_engine.renderer_factory import allow_2d_face_fallback
from avatar_engine.viseme_mapping import (
    convert_rhubarb_json_to_talkinghead,
    viseme_mapping_for_avatar,
)

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

# Extra time added to clip duration when waiting for the browser (seconds).
# Longform CC4/GLB renders can spend significant time loading and capturing frames,
# so allow callers to raise the timeout without editing code.
BROWSER_TIMEOUT_PADDING_S = int(
    os.environ.get("AVATAR_ENGINE_BROWSER_TIMEOUT_PADDING_S", "3600")
)

# Green-screen background colour used for chroma keying.
CHROMA_GREEN = "0x00ff00"

# Quality settings for H.264 mux.
H264_CRF = 20
H264_PRESET = "fast"

# Canvas capture writes one PNG per frame before muxing. Long-form 1080p jobs
# therefore need substantially more temporary space than the final MP4.
CANVAS_FRAME_ESTIMATED_BYTES = int(
    os.environ.get("AVATAR_ENGINE_ESTIMATED_BYTES_PER_FRAME", "1250000")
)
MIN_RENDER_FREE_BYTES = int(
    os.environ.get("AVATAR_ENGINE_MIN_RENDER_FREE_BYTES", str(5 * 1024**3))
)


# --------------------------------------------------------------------------- #
# Renderer                                                                     #
# --------------------------------------------------------------------------- #


class TalkingHeadAvatarRenderer(AvatarRenderer):
    """Renders a 3D talking avatar using TalkingHead + Playwright capture."""

    name = "talkinghead"

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path
        self._root = _project_root()

    # ---------------------------------------------------------------------- #
    # AvatarRenderer interface                                                 #
    # ---------------------------------------------------------------------- #

    def validate_job(self, job: AvatarJob) -> None:
        _require_talkinghead_fields(job, self._root)

    def render(self, job: AvatarJob) -> AvatarRenderResult:
        t_start = time.monotonic()
        root = self._root

        # ------------------------------------------------------------------ #
        # 1.  Validate job fields and avatar                                  #
        # ------------------------------------------------------------------ #
        try:
            _require_talkinghead_fields(job, root)
        except (ValueError, FileNotFoundError) as exc:
            return AvatarRenderResult(renderer=self.name, status="fail", error=str(exc))

        avatar_meta_path = root / job.avatar_metadata_path
        try:
            avatar_meta = load_avatar_metadata(avatar_meta_path)
        except AvatarValidationError as exc:
            return AvatarRenderResult(renderer=self.name, status="fail", error=str(exc))

        allow_2d = allow_2d_face_fallback()
        validation = validate_avatar_for_talkinghead(
            avatar_meta,
            avatar_id=str(avatar_meta.get("id", job.avatar_metadata_path)),
            allow_2d_fallback=allow_2d,
        )
        if validation["status"] != "pass":
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error=validation.get("error", "Avatar validation failed."),
                metadata={"avatar_validation": validation},
            )
        warnings: list[str] = list(validation.get("warnings", []))

        duration_s = job.camera_duration or _estimate_duration(root / job.audio_path)
        target_fps = job.camera_fps or 24
        estimated_temp_bytes = max(
            MIN_RENDER_FREE_BYTES,
            int(duration_s * target_fps * CANVAS_FRAME_ESTIMATED_BYTES * 1.25),
        )
        free_bytes = shutil.disk_usage(root).free
        if free_bytes < estimated_temp_bytes:
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error=(
                    "Insufficient free disk space for long-form avatar capture: "
                    f"need approximately {estimated_temp_bytes / 1024**3:.1f} GiB, "
                    f"have {free_bytes / 1024**3:.1f} GiB. Clear "
                    "avatar-engine/assets/temp/th_* render caches and retry."
                ),
            )

        # ------------------------------------------------------------------ #
        # 2.  Ensure web_avatar_runtime is built                              #
        # ------------------------------------------------------------------ #
        try:
            _ensure_web_runtime_built(root)
        except RuntimeError as exc:
            return AvatarRenderResult(renderer=self.name, status="fail", error=str(exc))

        dist_dir = root / "web_avatar_runtime" / "dist"

        # ------------------------------------------------------------------ #
        # 3.  Resolve paths and build browser job JSON                        #
        # ------------------------------------------------------------------ #
        temp_id = f"th_{uuid.uuid4().hex[:8]}"
        temp_dir = root / "assets" / "temp" / temp_id
        temp_dir.mkdir(parents=True, exist_ok=True)

        audio_path = root / job.audio_path
        viseme_path = root / job.viseme_path

        # Convert Rhubarb cues to TalkingHead format here so the browser page
        # receives pre-computed arrays and does not need the Python mapping lib.
        custom_map = viseme_mapping_for_avatar(avatar_meta)
        try:
            rhubarb_raw = json.loads(viseme_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error=f"Cannot read Rhubarb JSON at {viseme_path}: {exc}",
            )

        visemes, vtimes, vdurations = convert_rhubarb_json_to_talkinghead(
            rhubarb_raw, custom_map
        )

        # Build the browser-job object.  All asset paths are relative to the
        # project root so the HTTP server can map them to files.
        browser_job: dict[str, Any] = {
            "renderer": self.name,
            "episode_id": job.episode_id,
            "story_id": job.story_id,
            "avatar_url": "/" + job.avatar_asset_path.replace("\\", "/"),
            "audio_url": "/" + job.audio_path.replace("\\", "/"),
            "body_form": job.body_form,
            "camera": {
                "name": job.camera_name,
                "width": job.camera_width,
                "height": job.camera_height,
                "fps": job.camera_fps,
                "duration_seconds": job.camera_duration,
            },
            "face": job.face,
            "animation": job.raw.get("animation", {}),
            "avatar_transform": job.raw.get("avatar_transform", {}),
            "camera_overrides": job.raw.get("camera_overrides", {}),
            "render": {
                "background": job.raw.get("render", {}).get(
                    "background", "chroma_green"
                ),
            },
            "precomputed_visemes": {
                "visemes": visemes,
                "vtimes": vtimes,
                "vdurations": vdurations,
            },
        }

        browser_job_file = temp_dir / "browser_job.json"
        browser_job_file.write_text(json.dumps(browser_job, indent=2), encoding="utf-8")

        # Absolute server path for the HTTP query param.
        # The HTTP server is rooted at the project root, so the job JSON at
        # assets/temp/<id>/browser_job.json is served at /assets/temp/<id>/...
        rel_job_path = "/" + browser_job_file.relative_to(root).as_posix()

        # ------------------------------------------------------------------ #
        # 4.  Start local HTTP server                                         #
        # ------------------------------------------------------------------ #
        port = _find_free_port()
        server = _start_http_server(root, port)
        try:
            result = self._run_browser_capture(
                job=job,
                root=root,
                dist_dir=dist_dir,
                port=port,
                rel_job_path=rel_job_path,
                audio_path=audio_path,
                temp_dir=temp_dir,
                t_start=t_start,
                validation=validation,
                warnings=warnings,
                browser_job=browser_job,
            )
        finally:
            server.shutdown()

        keep_failed_temp = os.environ.get(
            "AVATAR_ENGINE_KEEP_FAILED_TEMP", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
        if result.status == "pass" or not keep_failed_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return result

    # ---------------------------------------------------------------------- #
    # Browser capture                                                          #
    # ---------------------------------------------------------------------- #

    def _run_browser_capture(
        self,
        *,
        job: AvatarJob,
        root: Path,
        dist_dir: Path,
        port: int,
        rel_job_path: str,
        audio_path: Path,
        temp_dir: Path,
        t_start: float,
        validation: dict[str, Any],
        warnings: list[str],
        browser_job: dict[str, Any],
    ) -> AvatarRenderResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error=(
                    "playwright Python package is not installed. "
                    "Run: pip install playwright && playwright install chromium"
                ),
            )

        video_dir = temp_dir / "video"
        video_dir.mkdir(exist_ok=True)
        canvas_frame_dir = temp_dir / "canvas_frames"
        canvas_frame_dir.mkdir(exist_ok=True)
        canvas_frame_count = 0
        frame_sequence_pattern: Path | None = None

        width = job.camera_width
        height = job.camera_height
        duration_s = job.camera_duration or _estimate_duration(audio_path)
        timeout_ms = int((duration_s + BROWSER_TIMEOUT_PADDING_S) * 1000)

        page_url = (
            f"http://localhost:{port}/web_avatar_runtime/dist/?job={rel_job_path}"
        )

        playwright_video_path: Path | None = None

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-web-security",
                    "--enable-webgl",
                    "--use-gl=angle",
                    "--use-angle=metal",
                    "--ignore-gpu-blocklist",
                    "--no-sandbox",
                ],
            )
            ctx = browser.new_context(
                viewport={"width": width, "height": height},
                record_video_dir=str(video_dir),
                record_video_size={"width": width, "height": height},
            )
            page = ctx.new_page()

            # Collect browser console messages for debugging
            console_messages: list[str] = []

            def _on_console(msg: Any) -> None:
                console_messages.append(f"[{msg.type}] {msg.text}")

            def _push_canvas_frame(data_url: str, frame_index: int) -> None:
                nonlocal canvas_frame_count
                try:
                    _, encoded = data_url.split(",", 1)
                    frame_path = canvas_frame_dir / f"frame_{int(frame_index):06d}.png"
                    frame_path.write_bytes(base64.b64decode(encoded))
                    canvas_frame_count = max(canvas_frame_count, int(frame_index) + 1)
                except Exception as exc:
                    raise RuntimeError(
                        f"Cannot write canvas frame {frame_index}: {exc}"
                    ) from exc

            page.on("console", _on_console)
            page.expose_function("__pushCanvasFrame", _push_canvas_frame)

            try:
                page.goto(page_url, wait_until="networkidle", timeout=30_000)
                # Wait for the render-complete signal
                page.wait_for_function(
                    'window.__renderStatus === "done" || window.__renderStatus === "error"',
                    timeout=timeout_ms,
                )
                render_status = page.evaluate("() => window.__renderStatus")
                if render_status == "error":
                    render_error = page.evaluate(
                        "() => window.__renderError || 'Unknown browser error'"
                    )
                    raise RuntimeError(render_error)
            except Exception as exc:
                # Save console for diagnosis
                console_log = temp_dir / "console.log"
                console_log.write_text("\n".join(console_messages), encoding="utf-8")
                browser.close()
                return AvatarRenderResult(
                    renderer=self.name,
                    status="fail",
                    error=f"Browser capture failed: {exc}. See {console_log}",
                )

            # Retrieve any runtime warnings the browser page emitted
            browser_warnings: list[str] = page.evaluate(
                "() => window.__renderWarnings || []"
            )
            warnings.extend(browser_warnings)

            if canvas_frame_count > 0:
                frame_sequence_pattern = canvas_frame_dir / "frame_%06d.png"
                playwright_video_path = None
                warnings.append(
                    f"Using browser canvas PNG frame capture: {canvas_frame_count} frames"
                )
            else:
                canvas_recording_base64: str | None = page.evaluate(
                    "() => window.__canvasRecordingBase64 || null"
                )
                if canvas_recording_base64:
                    canvas_video_path = temp_dir / "canvas_capture.webm"
                    canvas_video_path.write_bytes(
                        base64.b64decode(canvas_recording_base64)
                    )
                    playwright_video_path = canvas_video_path
                    warnings.append(
                        f"Using browser canvas MediaRecorder capture: {canvas_video_path.name}"
                    )
                else:
                    playwright_video_path = Path(page.video.path())

            page.close()
            ctx.close()
            browser.close()

        if frame_sequence_pattern is None and (
            playwright_video_path is None or not playwright_video_path.exists()
        ):
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error="Playwright did not produce a video file or canvas frame sequence.",
            )

        # ------------------------------------------------------------------ #
        # 10. FFmpeg: mux audio into MP4                                       #
        # ------------------------------------------------------------------ #
        output_mp4 = root / job.output_path
        output_mp4.parent.mkdir(parents=True, exist_ok=True)

        ffmpeg = _find_ffmpeg(self._config_path, root)
        if ffmpeg is None:
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error="ffmpeg not found. Set tools.ffmpeg in config/default.yaml or add it to PATH.",
            )

        target_fps = job.camera_fps or 24
        video_input_args = (
            ["-framerate", str(target_fps), "-i", str(frame_sequence_pattern)]
            if frame_sequence_pattern is not None
            else ["-i", str(playwright_video_path)]
        )
        mux_cmd = [
            str(ffmpeg),
            "-y",
            *video_input_args,
            "-i",
            str(audio_path),  # audio WAV
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-r",
            str(target_fps),  # re-encode to target fps
            "-c:v",
            "libx264",
            "-crf",
            str(H264_CRF),
            "-preset",
            H264_PRESET,
            "-c:a",
            "aac",
            "-shortest",
            str(output_mp4),
        ]
        mux_result = subprocess.run(mux_cmd, capture_output=True, text=True)
        if mux_result.returncode != 0:
            return AvatarRenderResult(
                renderer=self.name,
                status="fail",
                error=f"FFmpeg mux failed:\n{mux_result.stderr[-2000:]}",
            )

        # ------------------------------------------------------------------ #
        # 11. FFmpeg: extract preview PNG                                      #
        # ------------------------------------------------------------------ #
        preview_png: Path | None = None
        if job.preview_png_path:
            preview_png = root / job.preview_png_path
            preview_png.parent.mkdir(parents=True, exist_ok=True)
            mid_time = max(1.0, duration_s / 2.0)
            preview_cmd = [
                str(ffmpeg),
                "-y",
                "-ss",
                str(mid_time),
                "-i",
                str(output_mp4),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(preview_png),
            ]
            subprocess.run(preview_cmd, capture_output=True)

        # ------------------------------------------------------------------ #
        # 12. Manifest and stats                                               #
        # ------------------------------------------------------------------ #
        wall_time = time.monotonic() - t_start
        realtime_factor = duration_s / wall_time if wall_time > 0 else 0.0
        fps = job.camera_fps
        frame_count = int(duration_s * fps)

        manifest = {
            "renderer": self.name,
            "episode_id": job.episode_id,
            "story_id": job.story_id,
            "face_mode": job.face_mode,
            "avatar_validation": validation,
            "camera": browser_job["camera"],
            "viseme_mapping_source": "rhubarb",
            "output_path": str(output_mp4),
            "preview_png_path": str(preview_png) if preview_png else None,
            "wall_time_seconds": round(wall_time, 3),
            "realtime_factor": round(realtime_factor, 3),
            "clip_duration_seconds": round(duration_s, 3),
            "fps": fps,
            "frame_count": frame_count,
            "resolution": f"{job.camera_width}x{job.camera_height}",
            "warnings": warnings,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        manifest_path = output_mp4.parent / "avatar_render_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        stats_path = output_mp4.parent / "render_stats.json"
        stats_path.write_text(
            json.dumps(
                {
                    "renderer": self.name,
                    "duration_seconds": round(duration_s, 3),
                    "fps": fps,
                    "resolution": f"{job.camera_width}x{job.camera_height}",
                    "wall_time_seconds": round(wall_time, 3),
                    "realtime_factor": round(realtime_factor, 3),
                    "output_path": str(output_mp4),
                    "status": "pass",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return AvatarRenderResult(
            renderer=self.name,
            status="pass",
            output_path=str(output_mp4),
            preview_png_path=str(preview_png) if preview_png else None,
            manifest_path=str(manifest_path),
            stats_path=str(stats_path),
            wall_time_seconds=round(wall_time, 3),
            realtime_factor=round(realtime_factor, 3),
            fps=fps,
            resolution=f"{job.camera_width}x{job.camera_height}",
            frame_count=frame_count,
            face_mode=job.face_mode,
            warnings=warnings,
            metadata={"avatar_validation": validation},
        )


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _require_talkinghead_fields(job: AvatarJob, root: Path) -> None:
    """Raise ValueError / FileNotFoundError when mandatory fields are absent.

    Phase 1: collect all field-level errors (wrong values, empty strings).
    Phase 2: check file existence only if there are no field errors.
    This ensures callers always see the most actionable error first.
    """
    errors: list[str] = []

    # --- Phase 1: field-level checks ---
    if job.renderer not in {"talkinghead", "rocketbox"}:
        errors.append(
            f"Job renderer must be 'talkinghead' or 'rocketbox', got '{job.renderer}'."
        )

    if not job.audio_path:
        errors.append("'audio_path' is required.")

    if not job.viseme_path:
        errors.append("'viseme_path' is required.")

    if not job.avatar_asset_path:
        errors.append("'avatar.asset_path' is required.")

    if not job.avatar_metadata_path:
        errors.append("'avatar.metadata_path' is required.")

    if not job.output_path:
        errors.append("'render.output_path' is required.")

    if job.face_mode not in ("3d_viseme",):
        errors.append(
            f"'face.mode' must be '3d_viseme' for browser avatar renderers, got '{job.face_mode}'. "
            "Set AVATAR_ENGINE_ALLOW_2D_FACE_FALLBACK=1 to allow legacy_2d as a fallback."
        )

    if errors:
        raise ValueError(
            "TalkingHead job validation failed:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    # --- Phase 2: file existence checks (only reached when fields are valid) ---
    audio = root / job.audio_path
    if not audio.exists():
        raise FileNotFoundError(f"Audio file not found: {audio}")

    viseme = root / job.viseme_path
    if not viseme.exists():
        raise FileNotFoundError(f"Rhubarb/viseme file not found: {viseme}")

    asset = root / job.avatar_asset_path
    if not asset.exists():
        raise FileNotFoundError(f"Avatar GLB/VRM asset not found: {asset}")

    meta = root / job.avatar_metadata_path
    if not meta.exists():
        raise FileNotFoundError(f"Avatar metadata file not found: {meta}")
        raise ValueError(
            "TalkingHead job validation failed:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def _ensure_web_runtime_built(root: Path) -> None:
    """Build web_avatar_runtime/dist if missing or stale."""
    runtime_dir = root / "web_avatar_runtime"
    dist_dir = runtime_dir / "dist"
    pkg_json = runtime_dir / "package.json"

    if not pkg_json.exists():
        raise RuntimeError(
            f"web_avatar_runtime/package.json not found at {pkg_json}. "
            "The web runtime has not been set up in this repository."
        )

    if not dist_dir.exists() or not any(dist_dir.iterdir()):
        print(
            "[talkinghead] web_avatar_runtime/dist/ not found. Running npm ci && npm run build …"
        )
        node_modules = runtime_dir / "node_modules"
        if not node_modules.exists():
            _run_npm(runtime_dir, ["ci"])
        _run_npm(runtime_dir, ["run", "build"])

    if not dist_dir.exists():
        raise RuntimeError(
            "web_avatar_runtime build failed: dist/ directory was not created."
        )


def _run_npm(cwd: Path, args: list[str]) -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError(
            "npm is not available.  Install Node.js >= 18 to build the web avatar runtime."
        )
    subprocess.run([npm] + args, cwd=str(cwd), check=True)


def _find_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _start_http_server(root: Path, port: int) -> http.server.HTTPServer:
    """Start a simple HTTP file server in a daemon thread, serving *root*."""
    handler = _make_handler(root)
    server = http.server.HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)  # brief settle
    return server


def _make_handler(root: Path) -> type[http.server.SimpleHTTPRequestHandler]:
    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass  # suppress per-request log lines

    return _Handler


def _find_ffmpeg(config_path: Path | None, root: Path) -> Path | None:
    # Try config file first
    if config_path and config_path.exists():
        try:
            import yaml  # type: ignore

            with config_path.open() as fh:
                cfg = yaml.safe_load(fh) or {}
        except ImportError:
            cfg = {}
        ffmpeg_cfg = cfg.get("tools", {}).get("ffmpeg", "")
        if ffmpeg_cfg:
            p = Path(ffmpeg_cfg).expanduser()
            if p.exists():
                return p

    # Fall back to PATH
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def _estimate_duration(audio_path: Path) -> float:
    """Estimate audio duration from WAV header (fallback: 60 s)."""
    try:
        import wave

        with wave.open(str(audio_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / rate if rate > 0 else 60.0
    except Exception:
        return 60.0
