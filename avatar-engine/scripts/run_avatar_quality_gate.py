#!/usr/bin/env python3
"""Render one isolated run of the deterministic avatar quality gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOB = ROOT / "jobs" / "synthpost_anchor_v1_quality_gate.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from avatar_engine.quality_gate import canonical_job_sha256, validate_quality_gate_job


def build_candidate_job(
    source: dict[str, Any],
    *,
    candidate: str,
    run_id: str,
    renderer: str,
    quality_profile: str,
    blender_profile: str | None = None,
    tone_mapping: str = "aces",
) -> dict[str, Any]:
    # JSON round-trip is deliberate: this must not mutate the shared source job.
    job = json.loads(json.dumps(source))
    source_sha256 = canonical_job_sha256(source)
    job["renderer"] = renderer
    job["episode_id"] = f"ep_synthpost_anchor_v1_{candidate}_{run_id}"
    job["story_id"] = f"story_synthpost_anchor_v1_{candidate}_{run_id}"
    output_root = f"assets/output/avatar_bakeoff/{candidate}/{run_id}"
    job.setdefault("render", {})["quality_profile"] = quality_profile
    if blender_profile:
        job["render"]["blender_profile"] = blender_profile
    job["render"]["tone_mapping"] = tone_mapping
    job["render"]["output_path"] = f"{output_root}/video.mp4"
    job["render"]["preview_png_path"] = f"{output_root}/preview.png"
    job.setdefault("quality_gate", {})["source_job_sha256"] = source_sha256
    job["quality_gate"]["candidate"] = candidate
    job["quality_gate"]["run_id"] = run_id
    return job


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, default=DEFAULT_JOB)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--run", dest="run_id", required=True)
    parser.add_argument("--renderer", default="rocketbox")
    parser.add_argument("--quality-profile", default="legacy_control")
    parser.add_argument(
        "--blender-profile",
        choices=["review", "production", "master"],
        default=None,
        help="Override the EEVEE profile when --renderer=blender_cc.",
    )
    parser.add_argument(
        "--tone-mapping", choices=["aces", "agx", "neutral"], default="aces"
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "default.yaml")
    args = parser.parse_args(argv)

    source_path = args.job if args.job.is_absolute() else ROOT / args.job
    source = json.loads(source_path.read_text(encoding="utf-8"))
    errors = validate_quality_gate_job(source)
    if errors:
        print("Invalid source quality-gate job: " + "; ".join(errors), file=sys.stderr)
        return 2

    generated = build_candidate_job(
        source,
        candidate=args.candidate,
        run_id=args.run_id,
        renderer=args.renderer,
        quality_profile=args.quality_profile,
        blender_profile=args.blender_profile,
        tone_mapping=args.tone_mapping,
    )
    generated_dir = ROOT / "assets" / "temp" / "avatar_quality_gate_jobs"
    generated_dir.mkdir(parents=True, exist_ok=True)
    generated_path = generated_dir / f"{args.candidate}_{args.run_id}.json"
    generated_path.write_text(json.dumps(generated, indent=2) + "\n", encoding="utf-8")

    command = [
        sys.executable,
        "-m",
        "avatar_engine.render_avatar",
        "--job",
        str(generated_path),
        "--renderer",
        args.renderer,
        "--config",
        str(args.config),
    ]
    print("[quality-gate] " + " ".join(command))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
