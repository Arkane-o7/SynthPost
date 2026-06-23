from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_lipsync import wav_duration_seconds
from utils import load_json, resolve_tool


STALE_DURATION_TOLERANCE_SECONDS = 0.75


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def mouth_duration(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        data = load_json(path)
        duration = data.get("metadata", {}).get("duration")
        return float(duration) if duration is not None else None
    except Exception:
        return None


def frame_files(render_dir: Path) -> list[Path]:
    return sorted(render_dir.glob("frame_*.png"))


def frame_count_for_duration(duration: float | None, fps: int) -> int | None:
    if duration is None:
        return None
    return max(1, int(duration * fps))


def newest_mtime(paths: list[Path]) -> float | None:
    existing = [path.stat().st_mtime for path in paths if path.exists()]
    return max(existing) if existing else None


def oldest_mtime(paths: list[Path]) -> float | None:
    existing = [path.stat().st_mtime for path in paths if path.exists()]
    return min(existing) if existing else None


def output_duration(path: Path, ffmpeg_name: str | None = None) -> float | None:
    if not path.exists() or not path.is_file():
        return None
    ffprobe = resolve_tool("ffprobe")
    if ffprobe is None and ffmpeg_name:
        ffmpeg_path = resolve_tool(ffmpeg_name)
        if ffmpeg_path is not None:
            candidate = ffmpeg_path.with_name("ffprobe")
            if candidate.exists():
                ffprobe = candidate
    if ffprobe is None:
        return None
    try:
        result = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip())
    except Exception:
        return None


def job_export_mode(job: dict[str, Any]) -> str:
    return str(job.get("export_mode", "combined")).strip().lower()


def expected_native_segment_count(job: dict[str, Any]) -> int:
    cuts = job.get("camera_cuts", [])
    return len(cuts) if isinstance(cuts, list) and cuts else 1


def native_edit_manifest_path(output_path: Path) -> Path:
    return output_path / "edit_manifest.json"


def output_artifact_paths(job: dict[str, Any], output_path: Path) -> list[Path]:
    if job_export_mode(job) == "native_segments":
        if not output_path.exists() or not output_path.is_dir():
            return []
        return sorted(output_path.glob("*.mp4")) + [native_edit_manifest_path(output_path)]
    return [output_path] if output_path.exists() and output_path.is_file() else []


def output_artifacts_duration(paths: list[Path], ffmpeg_name: str | None = None) -> float | None:
    durations: list[float] = []
    videos = [path for path in paths if path.suffix.lower() == ".mp4"]
    if not videos:
        return None
    for path in videos:
        duration = output_duration(path, ffmpeg_name)
        if duration is None:
            return None
        durations.append(duration)
    return sum(durations)


def analyze_outputs(
    *,
    job: dict[str, Any],
    job_path: Path,
    config_path: Path,
    manifest_path: Path,
    audio_path: Path,
    mouth_path: Path,
    render_dir: Path,
    output_path: Path,
    template_path: Path,
    config: dict[str, Any],
    probe_output: bool = False,
    include_manifest_changes: bool = True,
) -> dict[str, Any]:
    fps = int(job.get("fps", config.get("render", {}).get("fps", 30)))
    script_hash = sha256_text(str(job.get("script", "")))
    job_hash = sha256_file(job_path)
    config_hash = sha256_file(config_path)
    previous = load_manifest(manifest_path)
    export_mode = job_export_mode(job)

    audio_duration = wav_duration_seconds(audio_path) if audio_path.exists() else None
    cue_duration = mouth_duration(mouth_path)
    expected_frames = frame_count_for_duration(cue_duration or audio_duration, fps)
    frames = frame_files(render_dir)
    output_artifacts = output_artifact_paths(job, output_path)
    output_video_duration = None
    if probe_output:
        ffmpeg_name = str(config.get("tools", {}).get("ffmpeg", "ffmpeg"))
        if export_mode == "native_segments":
            output_video_duration = output_artifacts_duration(output_artifacts, ffmpeg_name)
        else:
            output_video_duration = output_duration(output_path, ffmpeg_name)
    elif previous.get("output_video_path") == str(output_path) and output_path.exists():
        try:
            output_video_duration = float(previous["output_video_duration"])
        except Exception:
            output_video_duration = None

    reasons: dict[str, list[str]] = {
        "tts": [],
        "lipsync": [],
        "render": [],
        "export": [],
    }

    changed_inputs: list[str] = []
    if include_manifest_changes:
        if previous:
            if previous.get("job_file_hash") and previous.get("job_file_hash") != job_hash:
                changed_inputs.append("job file changed")
            if previous.get("config_file_hash") and previous.get("config_file_hash") != config_hash:
                changed_inputs.append("config file changed")
            if previous.get("script_text_hash") and previous.get("script_text_hash") != script_hash:
                changed_inputs.append("script text changed")
        else:
            changed_inputs.append("no previous run manifest")

    if not audio_path.exists():
        reasons["tts"].append("audio missing")
    reasons["tts"].extend(changed_inputs)

    if not mouth_path.exists():
        reasons["lipsync"].append("mouth cues missing")
    if audio_path.exists() and mouth_path.exists() and audio_path.stat().st_mtime > mouth_path.stat().st_mtime:
        reasons["lipsync"].append("audio newer than mouth cues")
    reasons["lipsync"].extend(changed_inputs)

    if not frames:
        reasons["render"].append("rendered frames missing")
    if mouth_path.exists() and frames:
        first_frame_time = oldest_mtime(frames)
        if first_frame_time is not None and mouth_path.stat().st_mtime > first_frame_time:
            reasons["render"].append("mouth cues newer than rendered frames")
    if expected_frames is not None and frames and len(frames) != expected_frames:
        reasons["render"].append(f"rendered frame count {len(frames)} != expected {expected_frames}")
    reasons["render"].extend(changed_inputs)

    if export_mode == "native_segments":
        edit_manifest = native_edit_manifest_path(output_path)
        segment_videos = [path for path in output_artifacts if path.suffix.lower() == ".mp4"]
        if not output_path.exists():
            reasons["export"].append("native segment output folder missing")
        elif not output_path.is_dir():
            reasons["export"].append("native segment output path is not a folder")
        if output_path.exists() and output_path.is_dir() and not edit_manifest.exists():
            reasons["export"].append("native segment edit manifest missing")
        if output_path.exists() and output_path.is_dir() and not segment_videos:
            reasons["export"].append("native segment MP4s missing")
        expected_segments = expected_native_segment_count(job)
        if segment_videos and len(segment_videos) != expected_segments:
            reasons["export"].append(f"native segment count {len(segment_videos)} != expected {expected_segments}")
    elif not output_path.exists():
        reasons["export"].append("output video missing")
    frame_newest = newest_mtime(frames)
    output_newest = newest_mtime(output_artifacts)
    if frame_newest is not None and output_newest is not None and frame_newest > output_newest:
        if export_mode == "native_segments":
            reasons["export"].append("native segment outputs older than rendered frames")
        else:
            reasons["export"].append("output video older than rendered frames")
    if output_video_duration is not None and audio_duration is not None:
        if math.fabs(output_video_duration - audio_duration) > STALE_DURATION_TOLERANCE_SECONDS:
            reasons["export"].append(
                f"output duration {output_video_duration:.2f}s differs from audio {audio_duration:.2f}s"
            )
    reasons["export"].extend(changed_inputs)

    statuses = {
        stage: "missing" if any("missing" in reason for reason in stage_reasons) else (
            "stale" if stage_reasons else "fresh"
        )
        for stage, stage_reasons in reasons.items()
    }

    return {
        "job_hash": job_hash,
        "config_hash": config_hash,
        "script_hash": script_hash,
        "previous_manifest": previous,
        "input_changes": changed_inputs,
        "reasons": reasons,
        "statuses": statuses,
        "fps": fps,
        "audio_duration": audio_duration,
        "mouth_duration": cue_duration,
        "expected_frame_count": expected_frames,
        "frames": frames,
        "actual_frame_count": len(frames),
        "first_frame": frames[0] if frames else None,
        "last_frame": frames[-1] if frames else None,
        "export_mode": export_mode,
        "output_artifacts": output_artifacts,
        "edit_manifest": native_edit_manifest_path(output_path) if export_mode == "native_segments" else None,
        "output_duration": output_video_duration,
        "template_mtime": template_path.stat().st_mtime if template_path.exists() else None,
    }


def manifest_data(
    *,
    job: dict[str, Any],
    job_path: Path,
    config_path: Path,
    manifest_path: Path,
    audio_path: Path,
    mouth_path: Path,
    render_dir: Path,
    output_path: Path,
    template_path: Path,
    config: dict[str, Any],
    flags: dict[str, bool],
    tts_engine_used: str,
) -> dict[str, Any]:
    analysis = analyze_outputs(
        job=job,
        job_path=job_path,
        config_path=config_path,
        manifest_path=manifest_path,
        audio_path=audio_path,
        mouth_path=mouth_path,
        render_dir=render_dir,
        output_path=output_path,
        template_path=template_path,
        config=config,
        probe_output=True,
        include_manifest_changes=False,
    )

    return {
        "job_id": str(job.get("job_id", "")),
        "job_file_path": str(job_path),
        "job_file_hash": analysis["job_hash"],
        "config_file_hash": analysis["config_hash"],
        "script_text_hash": analysis["script_hash"],
        "tts_engine_used": tts_engine_used,
        "audio_path": str(audio_path),
        "audio_file_hash": sha256_file(audio_path),
        "audio_duration": analysis["audio_duration"],
        "mouth_cue_path": str(mouth_path),
        "mouth_cue_file_hash": sha256_file(mouth_path),
        "mouth_cue_duration": analysis["mouth_duration"],
        "render_profile": job.get("render_profile"),
        "render_fps": analysis["fps"],
        "expected_frame_count": analysis["expected_frame_count"],
        "actual_rendered_frame_count": analysis["actual_frame_count"],
        "first_rendered_frame_path": str(analysis["first_frame"]) if analysis["first_frame"] else None,
        "last_rendered_frame_path": str(analysis["last_frame"]) if analysis["last_frame"] else None,
        "render_folder_path": str(render_dir),
        "export_mode": analysis["export_mode"],
        "output_video_path": str(output_path),
        "output_video_duration": analysis["output_duration"],
        "output_artifacts": [str(path) for path in analysis["output_artifacts"]],
        "edit_manifest_path": str(analysis["edit_manifest"]) if analysis["edit_manifest"] else None,
        "blender_template_path": str(template_path),
        "blender_template_mtime": analysis["template_mtime"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "flags": flags,
        "stale_status": analysis["statuses"],
        "stale_reasons": analysis["reasons"],
    }


def write_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def print_status_report(analysis: dict[str, Any], flags: dict[str, bool], job_path: Path | None = None) -> None:
    labels = (
        ("tts", "TTS"),
        ("lipsync", "Lipsync"),
        ("render", "Render frames"),
        ("export", "Export"),
    )
    print("[status] Dependency status")
    for key, label in labels:
        status = analysis["statuses"][key]
        reasons = analysis["reasons"][key]
        detail = "; ".join(reasons) if reasons else "ready to reuse"
        action = "regenerate"
        if flags.get(f"skip_{key}", False):
            action = "reuse requested"
        if key == "lipsync" and flags.get("skip_lipsync", False):
            action = "reuse requested"
        if key == "tts" and flags.get("skip_tts", False):
            action = "reuse requested"
        if key == "render" and flags.get("skip_render", False):
            action = "reuse requested"
        if key == "export" and flags.get("skip_export", False):
            action = "skip requested"
        print(f"[status] {label}: {status} ({detail}); planned: {action}")

    command_job = str(job_path) if job_path is not None else "jobs/sample_job.json"
    if any(status != "fresh" for status in analysis["statuses"].values()):
        print(f"[status] Recommended command: python scripts/run_job.py {command_job} --force-all")
    else:
        print(f"[status] Recommended command: python scripts/run_job.py {command_job}")
