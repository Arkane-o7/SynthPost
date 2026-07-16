"""Generate and load the canonical Kokoro narration artifact for a story."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import config
from ..models import (
    ArtifactRecord,
    NarrationArtifact,
    NarrationBeatTiming,
    NarrationSectionTiming,
    ScriptDocument,
    ScriptStatus,
)
from ..provenance import file_sha256
from ..storage import (
    PROJECT_ROOT,
    project_relative,
    read_manifest,
    resolve_project_path,
    story_dir,
    write_manifest,
)

SAMPLE_RATE = 24_000


class NarrationNotReadyError(ValueError):
    """The latest approved script has no current canonical narration."""


def _kokoro_python() -> str:
    configured = config.get_settings().avatar.python_path
    if configured:
        return str(configured)
    candidate = config.avatar_engine_dir() / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


@dataclass(frozen=True)
class NarrationUnit:
    beat_id: str
    section_id: str
    text: str
    kind: str = "narration"


def _units(script: ScriptDocument) -> list[NarrationUnit]:
    units: list[NarrationUnit] = []
    include_source_fallback = not config.source_audio_inserts_enabled()
    for section in script.sections:
        units.extend(
            NarrationUnit(
                beat_id=beat.beat_id,
                section_id=section.section_id,
                text=beat.text,
            )
            for beat in section.beats
        )
        if include_source_fallback and section.source_clip:
            units.append(
                NarrationUnit(
                    beat_id=f"{section.section_id}_source_fallback",
                    section_id=section.section_id,
                    text=section.source_clip.fallback_narration,
                    kind="source_fallback",
                )
            )
    if not units:
        raise ValueError("Approved script contains no narration beats")
    return units


def _request(script: ScriptDocument, *, test_mode: bool) -> dict[str, Any]:
    settings = config.get_settings().avatar
    units = _units(script)
    request_units: list[dict[str, Any]] = []
    for index, unit in enumerate(units):
        is_last = index == len(units) - 1
        next_section = None if is_last else units[index + 1].section_id
        if is_last:
            pause_ms = 0
        elif next_section == unit.section_id:
            pause_ms = settings.narration_beat_pause_ms
        else:
            pause_ms = settings.narration_section_pause_ms
        request_units.append(
            {
                "beat_id": unit.beat_id,
                "section_id": unit.section_id,
                "text": unit.text,
                "kind": unit.kind,
                "pause_after_ms": pause_ms,
            }
        )
    return {
        "contract_version": "synthpost.narration.request.v1",
        "script_id": script.script_id,
        "script_version": script.version,
        "voice_id": settings.voice_id,
        "voice_speed": settings.voice_speed,
        "language_code": settings.language_code,
        "sample_rate": SAMPLE_RATE,
        "test_mode": test_mode,
        "units": request_units,
    }


def _input_hash(request: dict[str, Any]) -> str:
    encoded = json.dumps(
        request, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def narration_dir(episode_id: str, story_id: str, script_version: int) -> Path:
    return (
        story_dir(episode_id, story_id)
        / "narration"
        / f"script_v{script_version:03d}"
    )


def narration_artifact_path(
    episode_id: str, story_id: str, script_version: int
) -> Path:
    return narration_dir(episode_id, story_id, script_version) / "alignment.json"


def _section_timings(
    script: ScriptDocument, beats: list[NarrationBeatTiming]
) -> list[NarrationSectionTiming]:
    timings: list[NarrationSectionTiming] = []
    by_section = {
        section.section_id: [
            beat for beat in beats if beat.section_id == section.section_id
        ]
        for section in script.sections
    }
    for section in script.sections:
        section_beats = by_section[section.section_id]
        if not section_beats:
            raise ValueError(
                f"Narration has no timing units for section {section.section_id}"
            )
        start = section_beats[0].start_time
        end = section_beats[-1].end_time
        timings.append(
            NarrationSectionTiming(
                section_id=section.section_id,
                beat_ids=[beat.beat_id for beat in section_beats],
                start_time=start,
                speech_end_time=section_beats[-1].speech_end_time,
                end_time=end,
                duration_seconds=round(end - start, 6),
            )
        )
    return timings


def generate_narration(
    repository,
    story_id: str,
    *,
    force: bool = False,
    test_mode: bool = False,
) -> NarrationArtifact:
    script = repository.latest_script(story_id)
    if not script or script.status != ScriptStatus.approved:
        raise NarrationNotReadyError(
            "Approve the latest script before generating its Kokoro narration."
        )
    episode = repository.episode_for_story(story_id)
    request = _request(script, test_mode=test_mode)
    expected_hash = _input_hash(request)
    artifact_path = narration_artifact_path(
        episode.episode_id, story_id, script.version
    )
    if not force and artifact_path.exists():
        artifact = NarrationArtifact.model_validate(read_manifest(artifact_path))
        if (
            artifact.input_hash == expected_hash
            and artifact.test_mode == test_mode
            and resolve_project_path(artifact.audio_path).exists()
        ):
            return artifact

    target_dir = artifact_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    audio_path = target_dir / "narration.wav"
    with tempfile.TemporaryDirectory(prefix=".narration-", dir=target_dir) as temp:
        temp_dir = Path(temp)
        request_path = temp_dir / "request.json"
        result_path = temp_dir / "result.json"
        temp_audio = temp_dir / "narration.wav"
        request_path.write_text(
            json.dumps(request, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(PROJECT_ROOT), env.get("PYTHONPATH", "")) if part
        )
        process = subprocess.run(
            [
                _kokoro_python(),
                "-m",
                "pipeline.narration.kokoro_worker",
                str(request_path),
                str(temp_audio),
                str(result_path),
            ],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30 * 60,
            check=False,
        )
        if process.returncode != 0:
            detail = (process.stderr or process.stdout).strip()
            raise RuntimeError(
                "Kokoro narration generation failed"
                + (f": {detail[-1200:]}" if detail else "")
            )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        sample_rate = int(result["sample_rate"])
        beats = [
            NarrationBeatTiming(
                **raw,
                start_time=round(raw["start_sample"] / sample_rate, 6),
                speech_end_time=round(
                    raw["speech_end_sample"] / sample_rate, 6
                ),
                end_time=round(raw["end_sample"] / sample_rate, 6),
                pause_after_seconds=round(
                    (raw["end_sample"] - raw["speech_end_sample"])
                    / sample_rate,
                    6,
                ),
            )
            for raw in result["beats"]
        ]
        os.replace(temp_audio, audio_path)

    artifact = NarrationArtifact(
        story_id=story_id,
        episode_id=episode.episode_id,
        script_id=script.script_id,
        script_version=script.version,
        input_hash=expected_hash,
        voice_id=request["voice_id"],
        voice_speed=request["voice_speed"],
        language_code=request["language_code"],
        sample_rate=sample_rate,
        test_mode=test_mode,
        audio_path=project_relative(audio_path),
        duration_seconds=round(result["duration_samples"] / sample_rate, 6),
        beats=beats,
        sections=_section_timings(script, beats),
        warnings=(
            ["test_synthesizer=true"]
            if test_mode
            else ["timing_is_sample_exact_not_forced_alignment"]
        ),
    )
    write_manifest(artifact_path, artifact.model_dump(mode="json"))
    for artifact_type, path in (
        ("canonical_narration_audio", audio_path),
        ("canonical_narration_alignment", artifact_path),
    ):
        repository.record_artifact(
            ArtifactRecord(
                artifact_type=artifact_type,
                path=project_relative(path),
                content_hash=file_sha256(path),
                producer="pipeline.narration.service",
                inputs=[f"script:{script.script_id}:v{script.version}"],
                metadata={
                    "story_id": story_id,
                    "episode_id": episode.episode_id,
                    "script_id": script.script_id,
                    "script_version": script.version,
                    "input_hash": expected_hash,
                    "timing_source": artifact.timing_source,
                    "sample_rate": artifact.sample_rate,
                },
            ),
            story_id=story_id,
            episode_id=episode.episode_id,
        )
    return artifact


def load_narration_artifact(
    repository, story_id: str, *, require_current: bool = True
) -> NarrationArtifact | None:
    script = repository.latest_script(story_id)
    if not script:
        if require_current:
            raise NarrationNotReadyError("No script exists for this story.")
        return None
    episode = repository.episode_for_story(story_id)
    path = narration_artifact_path(episode.episode_id, story_id, script.version)
    if not path.exists():
        if require_current:
            raise NarrationNotReadyError(
                "Generate Kokoro narration for the latest approved script first."
            )
        return None
    artifact = NarrationArtifact.model_validate(read_manifest(path))
    expected_hash = _input_hash(_request(script, test_mode=False))
    current = (
        artifact.script_id == script.script_id
        and artifact.script_version == script.version
        and artifact.input_hash == expected_hash
        and not artifact.test_mode
        and resolve_project_path(artifact.audio_path).exists()
    )
    if not current:
        if require_current:
            raise NarrationNotReadyError(
                "The narration is stale because the script or Kokoro settings changed. "
                "Regenerate narration before planning the timeline."
            )
        return None
    return artifact
