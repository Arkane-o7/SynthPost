from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from export_video import export_native_segments, export_video
from generate_lipsync import generate_lipsync, wav_duration_seconds
from generate_tts import generate_tts_result
from run_manifest import analyze_outputs, manifest_data, print_status_report, write_manifest
from utils import create_placeholder_frames, load_config, load_json, resolve_project_path, resolve_tool, write_json


REQUIRED_JOB_FIELDS = {
    "job_id",
    "script",
    "character",
    "face_mode",
    "fps",
    "resolution",
    "voice",
    "camera_cuts",
    "performance_beats",
    "output_path",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def validate_job(job: dict[str, Any], job_path: Path, root: Path) -> None:
    missing = sorted(REQUIRED_JOB_FIELDS - set(job))
    if missing:
        raise ValueError(f"Job file {job_path} is missing required field(s): {', '.join(missing)}")
    if not isinstance(job["resolution"], list) or len(job["resolution"]) != 2:
        raise ValueError("Job field 'resolution' must be a two-item list like [1920, 1080].")
    character_dir = root / "assets" / "characters" / str(job["character"])
    if not character_dir.exists():
        raise FileNotFoundError(f"Character folder not found: {character_dir}")


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def apply_render_profile(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    profile_name = str(job.get("render_profile", "")).strip()
    if not profile_name:
        return dict(job)

    profiles = config.get("render_profiles", {})
    if not isinstance(profiles, dict):
        raise ValueError("Config field 'render_profiles' must be a mapping.")
    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        available = ", ".join(sorted(str(name) for name in profiles)) or "<none>"
        raise ValueError(f"Unknown render_profile '{profile_name}'. Available profiles: {available}")

    merged = merge_dicts(profile, job)
    merged["render_profile"] = profile_name
    return merged


def create_job_folders(root: Path, job_id: str) -> tuple[Path, Path, Path]:
    temp_dir = root / "assets" / "temp" / job_id
    render_dir = root / "assets" / "renders" / job_id
    output_dir = root / "assets" / "output"
    for folder in (temp_dir, render_dir, output_dir):
        folder.mkdir(parents=True, exist_ok=True)
    return temp_dir, render_dir, output_dir


def ensure_inside(path: Path, allowed_parent: Path) -> None:
    resolved_path = path.resolve()
    resolved_parent = allowed_parent.resolve()
    if resolved_path != resolved_parent and resolved_parent not in resolved_path.parents:
        raise ValueError(f"Refusing to clean path outside generated folder: {path}")


def export_mode(job: dict[str, Any]) -> str:
    return str(job.get("export_mode", "combined")).strip().lower()


def resolve_export_target_path(root: Path, job: dict[str, Any], output_path: Path) -> Path:
    mode = export_mode(job)
    if mode == "combined":
        return output_path
    if mode == "native_segments":
        configured_dir = job.get("segment_output_dir")
        if configured_dir:
            return resolve_project_path(root, str(configured_dir))
        return output_path.with_suffix("") if output_path.suffix else output_path
    raise ValueError("Job field 'export_mode' must be 'combined' or 'native_segments'.")


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def clean_generated_outputs(root: Path, temp_dir: Path, render_dir: Path, output_paths: list[Path]) -> None:
    generated_roots = {
        "temp": root / "assets" / "temp",
        "renders": root / "assets" / "renders",
        "output": root / "assets" / "output",
    }

    for folder, allowed_parent in ((temp_dir, generated_roots["temp"]), (render_dir, generated_roots["renders"])):
        ensure_inside(folder, allowed_parent)
        if folder.exists():
            print(f"[clean] Removing generated folder: {folder}")
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)

    for output_path in unique_paths(output_paths):
        ensure_inside(output_path, generated_roots["output"])
        if output_path.is_dir():
            print(f"[clean] Removing generated output folder: {output_path}")
            shutil.rmtree(output_path)
        elif output_path.exists():
            print(f"[clean] Removing generated output file: {output_path}")
            output_path.unlink()


def clear_render_frames(root: Path, render_dir: Path) -> None:
    ensure_inside(render_dir, root / "assets" / "renders")
    if not render_dir.exists():
        render_dir.mkdir(parents=True, exist_ok=True)
        return
    deleted = 0
    for frame in render_dir.glob("frame_*.png"):
        if frame.is_file():
            frame.unlink()
            deleted += 1
    if deleted:
        print(f"[blender] Cleared {deleted} existing rendered frame(s): {render_dir}")


def warn_if_reusing_stale_frames(render_dir: Path, mouth_path: Path) -> None:
    frames = sorted(render_dir.glob("frame_*.png"))
    if not frames:
        print(f"[blender] WARNING: --skip-render requested but no frames exist in: {render_dir}")
        return

    print(f"[blender] Skipping render; using {len(frames)} existing frame(s): {render_dir}")
    if mouth_path.exists():
        oldest_frame_mtime = min(frame.stat().st_mtime for frame in frames)
        if oldest_frame_mtime < mouth_path.stat().st_mtime:
            print(
                "[blender] WARNING: Existing frames are older than the current mouth cues. "
                "The exported audio and mouth animation may not match. Run without --skip-render "
                "after changing TTS or lip sync."
            )


def warn_stage(stage: str, reasons: list[str]) -> None:
    for reason in reasons:
        print(f"[stale:{stage}] WARNING: {reason}")


def previous_tts_engine(manifest: dict[str, Any]) -> str:
    engine = manifest.get("tts_engine_used")
    return str(engine) if engine else "existing"


def run_blender(
    root: Path,
    job_path: Path,
    job: dict[str, Any],
    config: dict[str, Any],
    render_dir: Path,
    mouth_path: Path,
    test_mode: bool,
) -> None:
    blender_name = str(config.get("tools", {}).get("blender", "blender"))
    blender_path = resolve_tool(blender_name)
    template_path = root / "blender" / "avatar_template.blend"

    if not blender_path:
        message = f"Blender not found at '{blender_name}'"
        if test_mode:
            print(f"[blender] WARNING: {message}; creating placeholder PNG frames.")
            make_placeholder_render(job, render_dir, config, mouth_path)
            return
        raise FileNotFoundError(message)

    if not template_path.exists():
        message = f"Template blend file not found: {template_path}"
        if test_mode:
            print(f"[blender] WARNING: {message}; creating placeholder PNG frames.")
            make_placeholder_render(job, render_dir, config, mouth_path)
            return
        raise FileNotFoundError(message)

    driver_path = root / "blender" / "blender_driver.py"
    command = [
        str(blender_path),
        "-b",
        str(template_path),
        "--python",
        str(driver_path),
        "--",
        str(job_path),
    ]
    clear_render_frames(root, render_dir)
    print(f"[blender] Running Blender in background mode: {blender_path}")
    subprocess.run(command, check=True)


def make_placeholder_render(job: dict[str, Any], render_dir: Path, config: dict[str, Any], mouth_path: Path) -> None:
    render_config = config.get("render", {})
    fps = int(job.get("fps", render_config.get("fps", 30)))
    resolution = [int(value) for value in job.get("resolution", render_config.get("resolution", [1920, 1080]))]
    frame_count = int(render_config.get("placeholder_frame_count", fps * 3))
    if mouth_path.exists():
        mouth_data = load_json(mouth_path)
        duration = float(mouth_data.get("metadata", {}).get("duration", 0.0))
        if duration > 0:
            frame_count = max(frame_count, int(duration * fps))
    create_placeholder_frames(render_dir, frame_count, resolution)
    print(f"[blender] Wrote {frame_count} placeholder frames to: {render_dir}")


def run_pipeline(
    job_path: Path,
    config_path: Path,
    test_mode: bool = False,
    skip_tts: bool = False,
    skip_lipsync: bool = False,
    skip_render: bool = False,
    skip_export: bool = False,
    keep_temp: bool = False,
    clean: bool = False,
    force_tts: bool = False,
    force_lipsync: bool = False,
    force_render: bool = False,
    force_export: bool = False,
    force_all: bool = False,
    status: bool = False,
) -> Path | None:
    root = project_root()
    job_path = job_path if job_path.is_absolute() else root / job_path
    config_path = config_path if config_path.is_absolute() else root / config_path

    print(f"[job] Loading config: {config_path}")
    config = load_config(config_path)
    test_mode = test_mode or bool(config.get("test_mode", False))

    print(f"[job] Loading job: {job_path}")
    source_job = load_json(job_path)
    job = apply_render_profile(source_job, config)
    validate_job(job, job_path, root)

    job_id = str(job["job_id"])
    temp_dir = root / "assets" / "temp" / job_id
    render_dir = root / "assets" / "renders" / job_id
    output_path = resolve_project_path(root, str(job["output_path"]))
    output_target_path = resolve_export_target_path(root, job, output_path)
    effective_job_path = temp_dir / "effective_job.json"
    audio_path = temp_dir / "audio.wav"
    mouth_path = temp_dir / "mouth_cues.json"
    manifest_path = temp_dir / "run_manifest.json"
    template_path = root / "blender" / "avatar_template.blend"

    if force_all:
        force_tts = force_lipsync = force_render = force_export = True
    if force_tts:
        skip_tts = False
    if force_lipsync:
        skip_lipsync = False
    if force_render:
        skip_render = False
    if force_export:
        skip_export = False

    flags = {
        "test_mode": test_mode,
        "skip_tts": skip_tts,
        "skip_lipsync": skip_lipsync,
        "skip_render": skip_render,
        "skip_export": skip_export,
        "keep_temp": keep_temp,
        "clean": clean,
        "force_tts": force_tts,
        "force_lipsync": force_lipsync,
        "force_render": force_render,
        "force_export": force_export,
        "force_all": force_all,
        "status": status,
    }

    initial_analysis = analyze_outputs(
        job=job,
        job_path=job_path,
        config_path=config_path,
        manifest_path=manifest_path,
        audio_path=audio_path,
        mouth_path=mouth_path,
        render_dir=render_dir,
        output_path=output_target_path,
        template_path=template_path,
        config=config,
        probe_output=False,
    )

    if status:
        print_status_report(initial_analysis, flags, job_path)
        return None

    create_job_folders(root, job_id)

    if clean:
        clean_generated_outputs(root, temp_dir, render_dir, [output_path, output_target_path])

    write_json(effective_job_path, job)

    print(f"[job] Starting '{job_id}'")
    print(f"[job] Test mode: {'on' if test_mode else 'off'}")
    print(
        "[job] Skips: "
        f"tts={'on' if skip_tts else 'off'}, "
        f"lipsync={'on' if skip_lipsync else 'off'}, "
        f"render={'on' if skip_render else 'off'}, "
        f"export={'on' if skip_export else 'off'}"
    )
    print(
        "[job] Force: "
        f"tts={'on' if force_tts else 'off'}, "
        f"lipsync={'on' if force_lipsync else 'off'}, "
        f"render={'on' if force_render else 'off'}, "
        f"export={'on' if force_export else 'off'}"
    )
    if keep_temp:
        print("[job] Keep temp: on")
    print(f"[job] Temp: {temp_dir}")
    print(f"[job] Renders: {render_dir}")
    if job.get("render_profile"):
        print(f"[job] Render profile: {job['render_profile']}")
    print(f"[job] Export mode: {export_mode(job)}")
    print(f"[job] Output: {output_target_path}")

    tts_engine_used = previous_tts_engine(initial_analysis.get("previous_manifest", {}))
    if skip_tts:
        warn_stage("tts", initial_analysis["reasons"]["tts"])
        if not audio_path.exists():
            print(f"[tts] WARNING: --skip-tts requested but audio file is missing: {audio_path}")
            raise FileNotFoundError(f"--skip-tts requested but audio file is missing: {audio_path}")
        print(f"[tts] Skipping TTS; using existing audio: {audio_path}")
    else:
        tts_result = generate_tts_result(effective_job_path, audio_path, config_path=config_path, test_mode=test_mode)
        tts_engine_used = tts_result.engine_used

    after_tts_analysis = analyze_outputs(
        job=job,
        job_path=job_path,
        config_path=config_path,
        manifest_path=manifest_path,
        audio_path=audio_path,
        mouth_path=mouth_path,
        render_dir=render_dir,
        output_path=output_target_path,
        template_path=template_path,
        config=config,
        probe_output=False,
    )
    if skip_lipsync:
        warn_stage("lipsync", after_tts_analysis["reasons"]["lipsync"])
        if not mouth_path.exists():
            print(f"[lipsync] WARNING: --skip-lipsync requested but mouth cue file is missing: {mouth_path}")
            raise FileNotFoundError(f"--skip-lipsync requested but mouth cue file is missing: {mouth_path}")
        print(f"[lipsync] Skipping lip sync; using existing cues: {mouth_path}")
    else:
        generate_lipsync(audio_path, mouth_path, config_path=config_path, test_mode=test_mode)

    after_lipsync_analysis = analyze_outputs(
        job=job,
        job_path=job_path,
        config_path=config_path,
        manifest_path=manifest_path,
        audio_path=audio_path,
        mouth_path=mouth_path,
        render_dir=render_dir,
        output_path=output_target_path,
        template_path=template_path,
        config=config,
        probe_output=False,
    )
    if skip_render:
        warn_stage("render", after_lipsync_analysis["reasons"]["render"])
        warn_if_reusing_stale_frames(render_dir, mouth_path)
    else:
        run_blender(root, effective_job_path, job, config, render_dir, mouth_path, test_mode=test_mode)

    fps = int(job.get("fps", 30))
    try:
        duration = wav_duration_seconds(audio_path)
        print(f"[job] Audio duration: {duration:.2f}s at {fps} fps")
    except Exception as exc:
        print(f"[job] WARNING: Could not read audio duration: {exc}")

    after_render_analysis = analyze_outputs(
        job=job,
        job_path=job_path,
        config_path=config_path,
        manifest_path=manifest_path,
        audio_path=audio_path,
        mouth_path=mouth_path,
        render_dir=render_dir,
        output_path=output_target_path,
        template_path=template_path,
        config=config,
        probe_output=False,
    )
    if skip_export:
        warn_stage("export", after_render_analysis["reasons"]["export"])
        print("[export] Skipping MP4 export.")
        print("[job] Done: export skipped by request.")
        write_manifest(
            manifest_path,
            manifest_data(
                job=job,
                job_path=job_path,
                config_path=config_path,
                manifest_path=manifest_path,
                audio_path=audio_path,
                mouth_path=mouth_path,
                render_dir=render_dir,
                output_path=output_target_path,
                template_path=template_path,
                config=config,
                flags=flags,
                tts_engine_used=tts_engine_used,
            ),
        )
        print(f"[manifest] Wrote run manifest: {manifest_path}")
        return None

    if export_mode(job) == "native_segments":
        exported = export_native_segments(
            render_dir=render_dir,
            audio_wav=audio_path,
            output_dir=output_target_path,
            fps=fps,
            config_path=config_path,
            job=job,
            test_mode=test_mode,
        )
    else:
        exported = export_video(
            render_dir=render_dir,
            audio_wav=audio_path,
            output_mp4=output_path,
            fps=fps,
            config_path=config_path,
            test_mode=test_mode,
            output_resolution=job.get("resolution", config.get("render", {}).get("resolution", [1920, 1080])),
        )
    if exported:
        print(f"[job] Done: {exported}")
    else:
        print("[job] Done with warnings: MP4 export was skipped.")
    write_manifest(
        manifest_path,
        manifest_data(
            job=job,
            job_path=job_path,
            config_path=config_path,
            manifest_path=manifest_path,
            audio_path=audio_path,
            mouth_path=mouth_path,
            render_dir=render_dir,
            output_path=output_target_path,
            template_path=template_path,
            config=config,
            flags=flags,
            tts_engine_used=tts_engine_used,
        ),
    )
    print(f"[manifest] Wrote run manifest: {manifest_path}")
    return exported


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a desk-avatar video generation job.")
    parser.add_argument("job_json", nargs="?", type=Path, default=Path("jobs/sample_job.json"))
    parser.add_argument("--config", type=Path, default=Path("config/default.yaml"))
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--skip-tts", action="store_true", help="Reuse assets/temp/<job_id>/audio.wav.")
    parser.add_argument("--skip-lipsync", action="store_true", help="Reuse assets/temp/<job_id>/mouth_cues.json.")
    parser.add_argument("--skip-render", action="store_true", help="Reuse existing assets/renders/<job_id>/frame_*.png.")
    parser.add_argument("--skip-export", action="store_true", help="Run generation steps but do not create an MP4.")
    parser.add_argument("--keep-temp", action="store_true", help="Explicitly keep generated temp files. This is the default.")
    parser.add_argument("--clean", action="store_true", help="Clean only this job's temp, render frames, and MP4 before running.")
    parser.add_argument("--force-tts", action="store_true", help="Regenerate TTS audio even when a skip flag was provided.")
    parser.add_argument("--force-lipsync", action="store_true", help="Regenerate mouth cues even when a skip flag was provided.")
    parser.add_argument("--force-render", action="store_true", help="Regenerate rendered frames even when a skip flag was provided.")
    parser.add_argument("--force-export", action="store_true", help="Regenerate the output MP4 even when a skip flag was provided.")
    parser.add_argument("--force-all", action="store_true", help="Regenerate audio, mouth cues, rendered frames, and MP4.")
    parser.add_argument("--status", action="store_true", help="Print stale/fresh status without running generation tools.")
    args = parser.parse_args()

    try:
        run_pipeline(
            args.job_json,
            args.config,
            test_mode=args.test_mode,
            skip_tts=args.skip_tts,
            skip_lipsync=args.skip_lipsync,
            skip_render=args.skip_render,
            skip_export=args.skip_export,
            keep_temp=args.keep_temp,
            clean=args.clean,
            force_tts=args.force_tts,
            force_lipsync=args.force_lipsync,
            force_render=args.force_render,
            force_export=args.force_export,
            force_all=args.force_all,
            status=args.status,
        )
    except subprocess.CalledProcessError as exc:
        print(f"[error] External command failed with exit code {exc.returncode}: {exc.cmd}", file=sys.stderr)
        raise SystemExit(exc.returncode)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
