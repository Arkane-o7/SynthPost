from __future__ import annotations

import argparse
import re
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils import load_config, resolve_tool, write_json


def frame_pattern(render_dir: Path) -> str:
    return str(render_dir / "frame_%05d.png")


def frame_path(render_dir: Path, frame_number: int) -> Path:
    return render_dir / f"frame_{frame_number:05d}.png"


def seconds_to_frame_number(seconds: float, fps: int) -> int:
    return max(1, int(round(seconds * fps)) + 1)


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    return slug or "camera"


def png_size(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
        if len(header) < 24 or not header.startswith(b"\x89PNG\r\n\x1a\n"):
            return None
        width, height = struct.unpack(">II", header[16:24])
        return int(width), int(height)
    except Exception:
        return None


def sorted_camera_cuts(job: dict[str, Any]) -> list[dict[str, Any]]:
    cuts = job.get("camera_cuts", [])
    if not isinstance(cuts, list) or not cuts:
        return [{"start": 0.0, "camera": "portrait_main"}]
    return sorted(cuts, key=lambda cut: float(cut.get("start", 0.0)))


def build_native_segments(
    job: dict[str, Any],
    render_dir: Path,
    fps: int,
) -> list[dict[str, Any]]:
    frames = sorted(render_dir.glob("frame_*.png"))
    total_frames = len(frames)
    if total_frames <= 0:
        return []

    cuts = sorted_camera_cuts(job)
    cut_frames = [
        {
            "camera": str(cut.get("camera", "portrait_main")),
            "start": float(cut.get("start", 0.0)),
            "start_frame": seconds_to_frame_number(float(cut.get("start", 0.0)), fps),
        }
        for cut in cuts
    ]

    segments: list[dict[str, Any]] = []
    for index, cut in enumerate(cut_frames, start=1):
        start_frame = int(cut["start_frame"])
        if start_frame > total_frames:
            continue
        next_start_frame = (
            int(cut_frames[index]["start_frame"])
            if index < len(cut_frames)
            else total_frames + 1
        )
        end_frame = min(total_frames, next_start_frame - 1)
        frame_count = end_frame - start_frame + 1
        if frame_count <= 0:
            continue
        first_frame = frame_path(render_dir, start_frame)
        size = png_size(first_frame)
        segments.append(
            {
                "index": len(segments) + 1,
                "camera": cut["camera"],
                "start": (start_frame - 1) / fps,
                "end": end_frame / fps,
                "duration": frame_count / fps,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "frame_count": frame_count,
                "resolution": list(size) if size else None,
            }
        )
    return segments


def export_video(
    render_dir: Path,
    audio_wav: Path,
    output_mp4: Path,
    fps: int,
    config_path: Path,
    test_mode: bool = False,
    output_resolution: list[int] | tuple[int, int] | None = None,
) -> Path | None:
    frames = sorted(render_dir.glob("frame_*.png"))
    if not frames:
        message = f"No rendered frames found in {render_dir}"
        if test_mode:
            print(f"[export] WARNING: {message}; skipping video export.")
            return None
        raise FileNotFoundError(message)
    if not audio_wav.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_wav}")

    config = load_config(config_path)
    ffmpeg_name = str(config.get("tools", {}).get("ffmpeg", "ffmpeg"))
    ffmpeg_path = resolve_tool(ffmpeg_name)
    if not ffmpeg_path:
        message = f"FFmpeg not found at '{ffmpeg_name}'"
        if test_mode:
            print(f"[export] WARNING: {message}; skipping MP4 export in test mode.")
            return None
        raise FileNotFoundError(message)

    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg_path),
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        frame_pattern(render_dir),
        "-i",
        str(audio_wav),
    ]
    if output_resolution is not None:
        width, height = [int(value) for value in output_resolution]
        video_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:eval=frame,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black:eval=frame,"
            "setsar=1"
        )
        command.extend(["-vf", video_filter])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(output_mp4),
        ]
    )
    print(f"[export] Running FFmpeg export: {output_mp4}")
    subprocess.run(command, check=True)
    print(f"[export] Final video: {output_mp4}")
    return output_mp4


def export_native_segments(
    *,
    render_dir: Path,
    audio_wav: Path,
    output_dir: Path,
    fps: int,
    config_path: Path,
    job: dict[str, Any],
    test_mode: bool = False,
) -> Path | None:
    frames = sorted(render_dir.glob("frame_*.png"))
    if not frames:
        message = f"No rendered frames found in {render_dir}"
        if test_mode:
            print(f"[export] WARNING: {message}; skipping native segment export.")
            return None
        raise FileNotFoundError(message)
    if not audio_wav.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_wav}")

    config = load_config(config_path)
    ffmpeg_name = str(config.get("tools", {}).get("ffmpeg", "ffmpeg"))
    ffmpeg_path = resolve_tool(ffmpeg_name)
    if not ffmpeg_path:
        message = f"FFmpeg not found at '{ffmpeg_name}'"
        if test_mode:
            print(f"[export] WARNING: {message}; skipping native segment export in test mode.")
            return None
        raise FileNotFoundError(message)

    output_dir.mkdir(parents=True, exist_ok=True)
    for old_clip in output_dir.glob("*.mp4"):
        old_clip.unlink()

    segments = build_native_segments(job, render_dir, fps)
    if not segments:
        message = "No camera segments could be built from rendered frames."
        if test_mode:
            print(f"[export] WARNING: {message}; skipping native segment export.")
            return None
        raise ValueError(message)

    print(f"[export] Running native segment export: {output_dir}")
    for segment in segments:
        clip_name = f"{segment['index']:03d}_{safe_slug(str(segment['camera']))}.mp4"
        clip_path = output_dir / clip_name
        segment["path"] = str(clip_path)
        command = [
            str(ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-framerate",
            str(fps),
            "-start_number",
            str(segment["start_frame"]),
            "-i",
            frame_pattern(render_dir),
            "-ss",
            f"{float(segment['start']):.6f}",
            "-t",
            f"{float(segment['duration']):.6f}",
            "-i",
            str(audio_wav),
            "-frames:v",
            str(segment["frame_count"]),
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(clip_path),
        ]
        subprocess.run(command, check=True)
        print(
            "[export] Segment "
            f"{segment['index']:03d}: {segment['camera']} "
            f"frames {segment['start_frame']}-{segment['end_frame']} -> {clip_path}"
        )

    edit_manifest = {
        "job_id": str(job.get("job_id", "")),
        "export_mode": "native_segments",
        "fps": fps,
        "audio_path": str(audio_wav),
        "render_dir": str(render_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "segments": segments,
    }
    edit_manifest_path = output_dir / "edit_manifest.json"
    write_json(edit_manifest_path, edit_manifest)
    print(f"[export] Native segment manifest: {edit_manifest_path}")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine rendered frames and audio into an MP4.")
    parser.add_argument("render_dir", type=Path)
    parser.add_argument("audio_wav", type=Path)
    parser.add_argument("output_mp4", type=Path)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--config", type=Path, default=Path("config/default.yaml"))
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--native-segments", action="store_true", help="Export one native-aspect MP4 per camera cut.")
    parser.add_argument("--job", type=Path, help="Job JSON path, required for --native-segments.")
    args = parser.parse_args()
    if args.native_segments:
        if args.job is None:
            raise SystemExit("--job is required with --native-segments")
        from utils import load_json

        job = load_json(args.job)
        export_native_segments(
            render_dir=args.render_dir,
            audio_wav=args.audio_wav,
            output_dir=args.output_mp4,
            fps=args.fps,
            config_path=args.config,
            job=job,
            test_mode=args.test_mode,
        )
    else:
        export_video(args.render_dir, args.audio_wav, args.output_mp4, args.fps, args.config, args.test_mode)


if __name__ == "__main__":
    main()
