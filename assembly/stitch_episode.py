from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import config
from pipeline.provenance import artifact_record, record_episode_artifact
from pipeline.render_profiles import profile_record, resolve_profile
from pipeline.storage import (
    PROJECT_ROOT,
    episode_dir,
    read_manifest,
    resolve_project_path,
)

WIDTH = 1920
HEIGHT = 1080
FPS = 24
NORMALIZATION_VERSION = "audio_v3"
FINAL_AUDIO_FILTER = (
    "alimiter=limit=0.65:attack=5:release=50:level=false,aresample=48000"
)


def run(command: list[str]) -> None:
    print("[assembly] " + " ".join(command))
    subprocess.run(command, check=True)


def ffprobe_streams(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def has_audio(path: Path) -> bool:
    data = ffprobe_streams(path)
    return any(
        stream.get("codec_type") == "audio" for stream in data.get("streams", [])
    )


def duration_seconds(path: Path) -> float:
    data = ffprobe_streams(path)
    try:
        return float(data.get("format", {}).get("duration", 1.0))
    except (TypeError, ValueError):
        return 1.0


def ensure_placeholder_clip(
    path: Path,
    label: str,
    duration: float,
    *,
    width: int = WIDTH,
    height: int = HEIGHT,
    fps: int = FPS,
) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = config.ffmpeg_binary()
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=#050A14:s={width}x{height}:d={duration}",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r=48000:cl=stereo:d={duration}",
        "-vf",
        "format=yuv420p",
        "-shortest",
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(path),
    ]
    run(command)


def normalize_clip(
    input_path: Path,
    output_path: Path,
    *,
    width: int = WIDTH,
    height: int = HEIGHT,
    fps: int = FPS,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = config.ffmpeg_binary()
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=#050A14,"
        "setsar=1"
    )
    # AAC encoding can overshoot a one-pass loudnorm true-peak target on highly
    # dynamic brand clips. Keep program loudness at -16 LUFS and add a
    # conservative sample limiter so the encoded master remains below -1.5 dBTP.
    audio_filter = (
        "loudnorm=I=-16:TP=-2.5:LRA=11,"
        "alimiter=limit=0.70:attack=5:release=50:level=false,"
        "aresample=48000"
    )
    try:
        is_short_brand_placeholder = (
            input_path.parent == (PROJECT_ROOT / "assets" / "brand")
            and duration_seconds(input_path) <= 2.5
        )
    except Exception:
        is_short_brand_placeholder = False
    if is_short_brand_placeholder:
        audio_filter = "aresample=48000"

    if has_audio(input_path):
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-vf",
            video_filter,
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-af",
            audio_filter,
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    else:
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(input_path),
            "-f",
            "lavfi",
            "-t",
            f"{duration_seconds(input_path):.3f}",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            video_filter,
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    try:
        run(command)
    except subprocess.CalledProcessError:
        if has_audio(input_path) and "-af" in command:
            fallback = command[:]
            fallback[fallback.index("-af") + 1] = "aresample=48000"
            print(
                "[assembly] Audio loudnorm failed, retrying with resample-only audio filter."
            )
            run(fallback)
            return
        raise


def concat_clips(
    clips: list[Path], output_path: Path, work_dir: Path, *, fps: int = FPS
) -> None:
    list_path = work_dir / "concat.txt"
    with list_path.open("w", encoding="utf-8") as handle:
        for clip in clips:
            safe = str(clip.resolve()).replace("'", "'\\''")
            handle.write(f"file '{safe}'\n")
    command = [
        config.ffmpeg_binary(),
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-af",
        FINAL_AUDIO_FILTER,
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        run(command)
    except subprocess.CalledProcessError:
        print(
            "[assembly] Concat demuxer failed, retrying with safe filter re-encode concat."
        )
        concat_clips_filter(clips, output_path, fps=fps)


def concat_clips_filter(
    clips: list[Path], output_path: Path, *, fps: int = FPS
) -> None:
    command = [
        config.ffmpeg_binary(),
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
    ]
    for clip in clips:
        command.extend(["-i", str(clip)])
    streams = "".join(f"[{index}:v:0][{index}:a:0]" for index in range(len(clips)))
    filter_complex = (
        f"{streams}concat=n={len(clips)}:v=1:a=1[v][concat_a];"
        f"[concat_a]{FINAL_AUDIO_FILTER}[a]"
    )
    command.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    run(command)


def story_manifests(episode_id: str) -> list[Path]:
    episode_root = episode_dir(episode_id)
    episode_path = episode_root / "episode.json"
    if not episode_path.exists():
        return sorted((episode_root / "stories").glob("*/story.json"))

    episode_data = read_manifest(episode_path)
    story_ids = episode_data.get("story_ids", [])
    manifests = [
        episode_root / "stories" / story_id / "story.json" for story_id in story_ids
    ]
    missing = [path.parent.name for path in manifests if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Story manifests missing for episode "
            f"{episode_id}: {', '.join(missing)}"
        )
    return manifests


def stitch_episode(
    episode_id: str,
    *,
    force: bool = False,
    test_mode: bool = False,
    render_profile: str = "production",
) -> Path:
    profile = resolve_profile(render_profile)
    if test_mode:
        print(
            "[TEST_MODE] WARNING: Assembly output will be labeled TEST_MODE and written as final_TEST_MODE.mp4."
        )
    episode = episode_dir(episode_id)
    manifests = story_manifests(episode_id)
    if not manifests:
        raise FileNotFoundError(f"No story manifests found for episode: {episode_id}")

    outro = PROJECT_ROOT / "assets" / "brand" / "outro.mp4"
    ensure_placeholder_clip(
        outro,
        "SYNTHPOST",
        1.2,
        width=profile.width,
        height=profile.height,
        fps=profile.fps,
    )

    source_clips = []
    for manifest_path in manifests:
        # story.json is rebuilt by both preview and production actions, so its
        # composition.output_path may point at TEST_MODE even when production
        # assembly is requested. Pick the canonical clip for the assembly mode
        # first, and only fall back to the manifest path for legacy artifacts.
        canonical_output = manifest_path.with_name(
            "composited_TEST_MODE.mp4" if test_mode else "composited.mp4"
        )
        manifest = read_manifest(manifest_path)
        manifest_output = resolve_project_path(
            manifest.get("composition", {}).get("output_path", "")
        )
        output = canonical_output if canonical_output.exists() else manifest_output
        if not output.exists():
            raise FileNotFoundError(f"Composited story clip missing: {output}")
        source_clips.append(output)
    source_clips.append(outro)

    work_dir = episode / "_assembly"
    work_dir.mkdir(parents=True, exist_ok=True)
    normalized: list[Path] = []
    for index, clip in enumerate(source_clips):
        out = work_dir / (
            f"{index:03d}_{clip.stem}_{profile.name}_"
            f"{NORMALIZATION_VERSION}_normalized.mp4"
        )
        if force or not out.exists() or clip.stat().st_mtime > out.stat().st_mtime:
            normalize_clip(
                clip, out, width=profile.width, height=profile.height, fps=profile.fps
            )
        normalized.append(out)

    final_path = episode / ("final_TEST_MODE.mp4" if test_mode else "final.mp4")
    concat_clips(normalized, final_path, work_dir, fps=profile.fps)
    command = [
        "python3",
        "assembly/stitch_episode.py",
        episode_id,
        "--render-profile",
        profile.name,
    ]
    if force:
        command.append("--force")
    if test_mode:
        command.append("--test-mode")
    story_inputs = [*manifests, *source_clips]
    runtime = {
        "render_profile": profile.name,
        "render_profile_settings": profile_record(profile),
        "test_mode": bool(test_mode),
        "mode": "TEST_MODE" if test_mode else "production",
    }
    record_episode_artifact(
        episode_id,
        "final_video",
        artifact_record(
            path=final_path,
            stage="assembly",
            input_paths=story_inputs,
            provider="ffmpeg",
            fresh=True,
            reused=False,
            test_mode=test_mode,
            render_profile=profile.name,
            command=command,
            flags={"force": force},
        ),
        runtime=runtime,
    )
    print(f"[assembly] Final episode: {final_path}")
    return final_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stitch SynthPost story clips into one episode MP4."
    )
    parser.add_argument("episode_id")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Write TEST_MODE provenance and final_TEST_MODE.mp4.",
    )
    parser.add_argument(
        "--render-profile",
        choices=["preview", "production", "final_master"],
        default="production",
        help="Render quality profile for output normalization.",
    )
    args = parser.parse_args()
    stitch_episode(
        args.episode_id,
        force=args.force,
        test_mode=args.test_mode,
        render_profile=args.render_profile,
    )


if __name__ == "__main__":
    main()
