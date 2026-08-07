"""Validation and deterministic diagnostics for avatar renderer bake-offs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


QUALITY_GATE_VERSION = "avatar_quality_gate_v1"
PERFORMANCE_VERSION = "performance_v2"
REQUIRED_REVIEW_FEATURES = {
    "neutral_rest",
    "direct_gaze",
    "bilabial_closure",
    "dental_sounds",
    "wide_vowels",
    "rounded_vowels",
    "blink",
    "pause",
    "emphasis_gesture",
    "conclusion_settle",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_job_sha256(raw_job: dict[str, Any]) -> str:
    payload = json.dumps(raw_job, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_quality_gate_job(raw_job: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    gate = raw_job.get("quality_gate")
    performance = raw_job.get("performance")
    camera = raw_job.get("camera") or {}

    if not isinstance(gate, dict) or gate.get("version") != QUALITY_GATE_VERSION:
        errors.append(f"quality_gate.version must be {QUALITY_GATE_VERSION!r}")
        return errors
    if not isinstance(performance, dict) or performance.get("version") != PERFORMANCE_VERSION:
        errors.append(f"performance.version must be {PERFORMANCE_VERSION!r}")
    if not isinstance(gate.get("seed"), int):
        errors.append("quality_gate.seed must be an integer")
    if gate.get("allow_live_tts") is not False:
        errors.append("quality_gate.allow_live_tts must be false")
    duration = float(camera.get("duration_seconds") or 0)
    if duration < 8.0 or duration > 12.0:
        errors.append("camera.duration_seconds must be between 8 and 12 seconds")
    for field in ("fps", "width", "height"):
        if int(camera.get(field) or 0) <= 0:
            errors.append(f"camera.{field} must be a positive integer")
    features = {str(value) for value in gate.get("review_features") or []}
    missing = sorted(REQUIRED_REVIEW_FEATURES - features)
    if missing:
        errors.append(f"quality_gate.review_features missing: {', '.join(missing)}")
    if len((performance or {}).get("blink_events") or []) != 1:
        errors.append("performance.blink_events must contain exactly one event")
    if len((performance or {}).get("body_events") or []) < 2:
        errors.append("performance.body_events must include emphasis and settle events")
    for path_field in ("audio_path", "viseme_path"):
        if not str(raw_job.get(path_field) or "").strip():
            errors.append(f"{path_field} is required")
    return errors


def quality_gate_diagnostics(raw_job: dict[str, Any], root: Path) -> dict[str, Any]:
    asset_path = root / str((raw_job.get("avatar") or {}).get("asset_path") or "")
    audio_path = root / str(raw_job.get("audio_path") or "")
    viseme_path = root / str(raw_job.get("viseme_path") or "")
    return {
        "quality_gate_version": (raw_job.get("quality_gate") or {}).get("version"),
        "performance_version": (raw_job.get("performance") or {}).get("version"),
        "seed": (raw_job.get("quality_gate") or {}).get("seed"),
        "job_sha256": canonical_job_sha256(raw_job),
        "source_job_sha256": (raw_job.get("quality_gate") or {}).get(
            "source_job_sha256", canonical_job_sha256(raw_job)
        ),
        "candidate": (raw_job.get("quality_gate") or {}).get("candidate"),
        "run_id": (raw_job.get("quality_gate") or {}).get("run_id"),
        "asset_sha256": sha256_file(asset_path),
        "audio_sha256": sha256_file(audio_path),
        "viseme_sha256": sha256_file(viseme_path),
    }
