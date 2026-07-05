"""CLI smoke test: python -m avatar_engine.smoke_talkinghead

Renders a short test clip through the TalkingHead renderer and reports
wall-time performance vs. clip duration.

Usage
-----
python -m avatar_engine.smoke_talkinghead \\
    --duration 10 \\
    --avatar assets/avatars/synthpost_anchor_v1/avatar.glb \\
    --audio tests/fixtures/sample.wav \\
    --out .tmp/talkinghead_smoke/

Required inputs
---------------
The smoke test assumes Rhubarb has already been run against the audio.
Alternatively, pass --visemes to specify an existing Rhubarb JSON.
If neither the audio nor the viseme files exist, the smoke creates stub
fixtures in the output directory.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time
import wave
import zlib
from pathlib import Path

_here = Path(__file__).resolve()
_repo_root = _here.parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from avatar_engine.renderer_base import AvatarJob
from avatar_engine.renderer_factory import get_renderer
from avatar_engine.viseme_mapping import SAMPLE_RHUBARB_CUES

# --------------------------------------------------------------------------- #
# Smoke test job template                                                      #
# --------------------------------------------------------------------------- #

_SCRIPT = (
    "This is a quick smoke test of the TalkingHead avatar renderer. "
    "If you can see and hear the avatar speaking this sentence, the renderer is working."
)


def _build_smoke_job(
    duration: float,
    avatar_path: str,
    avatar_meta_path: str,
    audio_path: str,
    viseme_path: str,
    output_mp4: str,
    preview_png: str,
    width: int,
    height: int,
    fps: int,
) -> dict:
    return {
        "renderer": "talkinghead",
        "episode_id": "smoke_test",
        "story_id": "smoke_001",
        "script_text": _SCRIPT,
        "audio_path": audio_path,
        "viseme_path": viseme_path,
        "avatar": {
            "asset_path": avatar_path,
            "metadata_path": avatar_meta_path,
            "style": "professional_stylized_news_anchor",
            "face_type": "3d",
            "requires_3d_lips": True,
        },
        "camera": {
            "name": "front_medium",
            "width": width,
            "height": height,
            "fps": fps,
            "duration_seconds": duration,
        },
        "render": {
            "background": "chroma_green",
            "output_path": output_mp4,
            "preview_png_path": preview_png,
        },
        "animation": {
            "idle_loop": "news_idle",
            "gesture_style": "calm_anchor",
            "gesture_events": [],
        },
        "face": {
            "mode": "3d_viseme",
            "viseme_source": "rhubarb",
            "blendshape_profile": "auto_detect",
            "fallback_mode": "legacy_2d",
            "allow_fallback": False,
        },
    }


# --------------------------------------------------------------------------- #
# Stub fixture generators                                                       #
# --------------------------------------------------------------------------- #


def _write_stub_wav(path: Path, duration_s: float, sample_rate: int = 24000) -> None:
    """Write a minimal silent WAV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = int(duration_s * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_samples)


def _write_stub_rhubarb(path: Path, duration_s: float) -> None:
    """Write a minimal Rhubarb JSON with repeating cue pattern."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cues = []
    t = 0.0
    cue_duration = 0.1
    labels = ["X", "A", "E", "F", "B", "C", "G", "H", "X", "A"]
    idx = 0
    while t < duration_s:
        end = min(t + cue_duration, duration_s)
        cues.append(
            {
                "start": round(t, 3),
                "end": round(end, 3),
                "value": labels[idx % len(labels)],
            }
        )
        t = end
        idx += 1
    data = {
        "metadata": {"soundFile": str(path), "duration": duration_s},
        "mouthCues": cues,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_stub_png(path: Path, width: int = 32, height: int = 32) -> None:
    """Write a tiny solid-green PNG as a placeholder avatar thumbnail."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFF_FFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    path.parent.mkdir(parents=True, exist_ok=True)
    row = bytes([0, 0, 255, 0] * width)  # filter=0 + RGBA green
    raw = b"".join(b"\x00" + bytes([0, 255, 0]) * width for _ in range(height))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def _stub_avatar_metadata(meta_path: Path, asset_path: str) -> None:
    """Write a stub avatar.json if missing."""
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    if not meta_path.exists():
        data = {
            "id": "smoke_test_avatar",
            "name": "Smoke Test Avatar",
            "source_tool": "stub",
            "format": "glb",
            "license": "stub",
            "style": "professional_stylized_news_anchor",
            "face_type": "3d",
            "rig_type": "mixamo_compatible",
            "supports_3d_lips": True,
            "supports_visemes": True,
            "blendshape_profile": "arkit",
            "viseme_shapes": ["aa", "ih", "ou", "ee", "oh"],
            "expression_shapes": ["neutral", "blink", "smile"],
            "legacy_2d_face_supported": False,
            "notes": "Stub metadata for smoke testing only.",
        }
        meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m avatar_engine.smoke_talkinghead",
        description="Smoke-test the TalkingHead renderer end-to-end.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Clip duration in seconds (default: 10).",
    )
    parser.add_argument(
        "--avatar",
        default="assets/avatars/synthpost_anchor_v1/avatar.glb",
        help="Relative path to avatar GLB (default: synthpost_anchor_v1).",
    )
    parser.add_argument(
        "--audio",
        default=None,
        help="Relative path to audio WAV (default: generates a silent stub).",
    )
    parser.add_argument(
        "--visemes",
        default=None,
        help="Relative path to Rhubarb JSON (default: generates a stub).",
    )
    parser.add_argument(
        "--out",
        default=".tmp/talkinghead_smoke",
        help="Output directory (default: .tmp/talkinghead_smoke/).",
    )
    parser.add_argument(
        "--width", type=int, default=1280, help="Frame width (default: 1280)."
    )
    parser.add_argument(
        "--height", type=int, default=720, help="Frame height (default: 720)."
    )
    parser.add_argument(
        "--fps", type=int, default=24, help="Frames per second (default: 24)."
    )
    parser.add_argument("--config", default=None, help="Config YAML path.")

    args = parser.parse_args(argv)

    out_dir = _repo_root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    duration = args.duration

    # ---- Audio ----
    if args.audio:
        audio_path = _repo_root / args.audio
        if not audio_path.exists():
            print(f"[smoke] Audio not found at {audio_path}; generating silent stub.")
            _write_stub_wav(audio_path, duration)
    else:
        audio_path = out_dir / "smoke_audio.wav"
        if not audio_path.exists():
            print("[smoke] Generating silent stub WAV …")
            _write_stub_wav(audio_path, duration)

    # ---- Visemes ----
    if args.visemes:
        viseme_path = _repo_root / args.visemes
        if not viseme_path.exists():
            print(f"[smoke] Rhubarb JSON not found at {viseme_path}; generating stub.")
            _write_stub_rhubarb(viseme_path, duration)
    else:
        viseme_path = out_dir / "smoke_rhubarb.json"
        if not viseme_path.exists():
            print("[smoke] Generating stub Rhubarb cues …")
            _write_stub_rhubarb(viseme_path, duration)

    # ---- Avatar metadata ----
    avatar_path = _repo_root / args.avatar
    avatar_meta_path = avatar_path.parent / "avatar.json"
    _stub_avatar_metadata(avatar_meta_path, str(avatar_path))

    # ---- Build job ----
    output_mp4 = out_dir / "smoke_output.mp4"
    preview_png = out_dir / "smoke_preview.png"

    def _rel(p: Path) -> str:
        return str(p.relative_to(_repo_root)).replace("\\", "/")

    job_dict = _build_smoke_job(
        duration=duration,
        avatar_path=_rel(avatar_path),
        avatar_meta_path=_rel(avatar_meta_path),
        audio_path=_rel(audio_path),
        viseme_path=_rel(viseme_path),
        output_mp4=_rel(output_mp4),
        preview_png=_rel(preview_png),
        width=args.width,
        height=args.height,
        fps=args.fps,
    )

    job_file = out_dir / "smoke_job.json"
    job_file.write_text(json.dumps(job_dict, indent=2), encoding="utf-8")
    print(f"[smoke] Job: {job_file}")

    config_path = (
        Path(args.config) if args.config else _repo_root / "config" / "default.yaml"
    )
    job = AvatarJob(raw=job_dict, job_path=job_file)
    renderer = get_renderer(job, override="talkinghead", config_path=config_path)

    print(
        f"[smoke] Starting TalkingHead render: {duration}s clip at {args.width}x{args.height} {args.fps}fps …"
    )
    t0 = time.monotonic()
    result = renderer.render(job)
    wall_time = time.monotonic() - t0

    if result.status == "pass":
        realtime = duration / wall_time if wall_time > 0 else 0
        report = {
            "renderer": "talkinghead",
            "duration_seconds": duration,
            "fps": args.fps,
            "resolution": f"{args.width}x{args.height}",
            "wall_time_seconds": round(wall_time, 3),
            "realtime_factor": round(realtime, 3),
            "output_path": result.output_path,
            "status": "pass",
        }
        report_path = out_dir / "smoke_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("\n[smoke] ✓ PASS")
        print(f"  Duration:       {duration:.1f}s")
        print(f"  Wall time:      {wall_time:.1f}s")
        print(f"  Realtime factor:{realtime:.2f}x")
        print(f"  Output:         {result.output_path}")
        print(f"  Report:         {report_path}")
        if result.warnings:
            for w in result.warnings:
                print(f"  WARNING: {w}")
        return 0
    else:
        print(f"\n[smoke] ✗ FAIL: {result.error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
