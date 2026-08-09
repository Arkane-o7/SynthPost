#!/usr/bin/env python3
"""Synthesize the Sidequest pilot and build its exact-timed story manifest."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
VIDEO = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPT = VIDEO / "podcast.txt"
SCENE_PLAN = VIDEO / "scene_plan.json"
REQUEST = VIDEO / "narration-request.json"
RAW_TIMING = VIDEO / "narration-timing-raw.json"
AUDIO = VIDEO / "podcast_audio.wav"
TIMING = VIDEO / "timing.json"
SUBTITLES = VIDEO / "podcast_audio.srt"
STORY = VIDEO / "story.json"

SECTION_TYPES = {
    "cold_open": "cold_open",
    "setup": "context",
    "wrong_chat": "key_developments",
    "damage_control": "stakes",
    "next_morning": "why_it_matters",
    "button": "conclusion",
}

SECTION_LABELS = {
    "cold_open": "Eleven listened",
    "setup": "The setup",
    "wrong_chat": "Wrong chat",
    "damage_control": "Damage control",
    "next_morning": "The next morning",
    "button": "Mostly solved",
}


def read_script() -> tuple[list[dict[str, Any]], OrderedDict[str, list[str]]]:
    sections: OrderedDict[str, list[str]] = OrderedDict()
    current: str | None = None
    for raw_line in SCRIPT.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        marker = re.fullmatch(r"\[SECTION:([^\]]+)\]", line)
        if marker:
            current = marker.group(1)
            sections.setdefault(current, [])
            continue
        if current is None:
            raise ValueError("Narration text appeared before its first section marker")
        sections[current].append(line)

    units: list[dict[str, Any]] = []
    for section_id, texts in sections.items():
        for index, text in enumerate(texts, start=1):
            units.append(
                {
                    "beat_id": f"{section_id}_beat_{index:02d}",
                    "section_id": section_id,
                    "text": text,
                    "kind": "narration",
                }
            )
    return units, sections


def narration_request(units: list[dict[str, Any]]) -> dict[str, Any]:
    from pipeline import config
    from pipeline.channels import get_channel_profile, resolved_production
    from pipeline.storage import resolve_project_path

    profile = get_channel_profile("storytime")
    production = resolved_production(profile)
    settings = config.get_settings().narration
    provider = str(production["narrator_provider"])
    configured_profile = production["narrator_voice_profile_path"]
    profile_path = (
        resolve_project_path(Path(str(configured_profile)))
        if configured_profile
        else None
    )
    if provider == "dots_tts" and (
        profile_path is None or not profile_path.is_dir()
    ):
        raise FileNotFoundError(f"Sidequest narrator profile is missing: {profile_path}")

    request_units: list[dict[str, Any]] = []
    for index, unit in enumerate(units):
        next_section = units[index + 1]["section_id"] if index + 1 < len(units) else None
        pause_ms = 0
        if next_section is not None:
            pause_ms = (
                settings.narration_beat_pause_ms
                if next_section == unit["section_id"]
                else settings.narration_section_pause_ms
            )
        request_units.append({**unit, "pause_after_ms": pause_ms})

    return {
        "contract_version": "synthea.narration.request.v2",
        "channel_id": "storytime",
        "channel_profile_version": profile.profile_version,
        "script_id": "script_sidequest_wrong_group_chat_pilot",
        "script_version": 1,
        "provider": provider,
        "model_path": str(resolve_project_path(settings.model_path)),
        "model_name": production["narrator_model_name"] or settings.model_name,
        "voice_id": production["narrator_voice_id"],
        "voice_profile_path": str(profile_path) if profile_path else None,
        "reference_audio_path": None,
        "reference_text": None,
        "voice_speed": float(production["narrator_voice_speed"]),
        "language_code": settings.language_code,
        "num_steps": settings.num_steps,
        "guidance_scale": settings.guidance_scale,
        "speaker_scale": settings.speaker_scale,
        "seed": settings.seed,
        "max_generate_length": settings.max_generate_length,
        "ffmpeg_binary": config.get_settings().render.ffmpeg_binary,
        "sample_rate": 48_000,
        "test_mode": False,
        "units": request_units,
    }


def seconds(sample: int, sample_rate: int) -> float:
    return round(sample / sample_rate, 6)


def srt_time(value: float) -> str:
    total_ms = max(0, round(value * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_value, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_value:02d},{milliseconds:03d}"


def exact_windows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    rate = int(raw["sample_rate"])
    return [
        {
            "beat_id": beat["beat_id"],
            "section_id": beat["section_id"],
            "text": beat["text"],
            "kind": beat.get("kind", "narration"),
            "start_time": seconds(int(beat["start_sample"]), rate),
            "speech_end_time": seconds(int(beat["speech_end_sample"]), rate),
            "end_time": seconds(int(beat["end_sample"]), rate),
        }
        for beat in raw["beats"]
    ]


def write_timing(windows: list[dict[str, Any]], raw: dict[str, Any]) -> None:
    by_section: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for beat in windows:
        by_section.setdefault(beat["section_id"], []).append(beat)
    sections = []
    for section_id, beats in by_section.items():
        start = beats[0]["start_time"]
        end = beats[-1]["end_time"]
        sections.append(
            {
                "section": section_id,
                "label": SECTION_LABELS[section_id],
                "start": start,
                "end": end,
                "duration": round(end - start, 6),
                "beats": beats,
            }
        )
    payload = {
        "version": 1,
        "timing_source": (
            "edge_word_boundaries_pcm_samples"
            if raw.get("engine") == "edge_tts"
            else "exact_pcm_samples"
        ),
        "sample_rate": raw["sample_rate"],
        "total_duration": seconds(int(raw["duration_samples"]), int(raw["sample_rate"])),
        "sections": sections,
        "beats": windows,
    }
    TIMING.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    blocks = []
    for index, beat in enumerate(windows, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{srt_time(beat['start_time'])} --> {srt_time(beat['speech_end_time'])}",
                    beat["text"],
                ]
            )
        )
    SUBTITLES.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def build_story(
    request: dict[str, Any],
    units: list[dict[str, Any]],
    sections: OrderedDict[str, list[str]],
    windows: list[dict[str, Any]],
) -> None:
    from pipeline.channels import get_channel_profile

    scene_plan = json.loads(SCENE_PLAN.read_text(encoding="utf-8"))
    planned = scene_plan["beats"]
    if len(units) != len(windows) or len(units) != len(planned):
        raise ValueError(
            f"Beat mismatch: script={len(units)} timing={len(windows)} plan={len(planned)}"
        )

    segments = []
    for index, (unit, timing, shot) in enumerate(zip(units, windows, planned), start=1):
        start = float(timing["start_time"])
        end = float(timing["end_time"])
        cue = {
            **shot["cue"],
            "speech_end_offset": round(
                float(timing["speech_end_time"]) - start, 6
            ),
        }
        segments.append(
            {
                "segment_id": f"segment_{index:02d}_{unit['beat_id']}",
                "beat_id": unit["beat_id"],
                "scene_id": f"scene_{index:02d}",
                "section_id": unit["section_id"],
                "start_time": start,
                "end_time": end,
                "duration": round(end - start, 6),
                "narrative_function": "land_punchline"
                if shot["template_id"] == "storytime_punchline_button"
                else "advance_story",
                "visual_role": shot["template_id"].removeprefix("storytime_"),
                "transition_in": "paper_cut" if index == 1 else "hard_cut",
                "transition_out": "hard_cut",
                "script_text": unit["text"],
                "anchor": {"visible": False, "speaking": True, "camera": shot["cue"]["shot"]},
                "visual": {"media_type": "fallback", "content_role": "fallback"},
                "template": {"template_id": shot["template_id"]},
                "audio": {
                    "mode": "narration",
                    "narration_volume": 1.0,
                    "source_volume": 0.0,
                    "ducking": False,
                },
                "overlays": {"data": {"storytime": cue}},
                "status": "approved",
            }
        )

    duration = float(windows[-1]["end_time"])
    profile = get_channel_profile("storytime")
    channel = profile.model_dump()
    manifest = {
        "story_id": scene_plan["story_id"],
        "episode_id": "episode_sidequest_wrong_group_chat_pilot",
        "channel_id": "storytime",
        "channel": channel,
        "raw": {
            "headline_source": "I Sent a Private Voice Note to the Entire Office",
            "source_name": "Sidequest",
            "published_at": "2026-08-09T00:00:00+05:30",
            "category": "storytime",
        },
        "script": {
            "script_id": request["script_id"],
            "headline": "I Sent a Private Voice Note to the Entire Office",
            "dek": "One private note. Eleven listeners. Zero useful thoughts.",
            "category": "storytime animation",
            "status": "approved",
            "sections": [
                {
                    "section_id": section_id,
                    "section_type": SECTION_TYPES[section_id],
                    "text": "\n\n".join(texts),
                }
                for section_id, texts in sections.items()
            ],
        },
        "direction": {
            "fps": 24,
            "estimated_duration_seconds": duration,
            "presenter_provider": "procedural_puppet",
            "narration_audio_path": str(AUDIO.relative_to(ROOT)),
        },
        "narration": {
            "audio_path": str(AUDIO.relative_to(ROOT)),
            "subtitles_path": str(SUBTITLES.relative_to(ROOT)),
            "provider": request["provider"],
            "model": request["model_name"],
            "voice_id": request["voice_id"],
            "voice_profile": (
                str(Path(request["voice_profile_path"]).relative_to(ROOT))
                if request.get("voice_profile_path")
                else None
            ),
            "timing_source": (
                "edge_word_boundaries_pcm_samples"
                if request["provider"] == "edge_tts"
                else "exact_pcm_samples"
            ),
            "preview_audio": False,
            "duration_seconds": duration,
            "beats": windows,
        },
        "runtime": {
            "render_profile": "studio_review",
            "render_profile_settings": {"fps": 24, "width": 1920, "height": 1080},
        },
        "approved_timeline": {
            "timeline_id": "timeline_sidequest_wrong_group_chat_pilot",
            "story_id": scene_plan["story_id"],
            "version": 1,
            "status": "approved",
            "segments": segments,
        },
        "composition": {
            "template": "timeline_story_storytime",
            "duration_seconds": duration,
            "output_path": "videos/sidequest-wrong-group-chat-pilot/output.mp4",
            "preview_path": "videos/sidequest-wrong-group-chat-pilot/preview.png",
        },
        "production_notes": {
            "fictional_composite": True,
            "design_read": scene_plan["design_read"],
            "asset_strategy": scene_plan["asset_strategy"],
            "voice_status": "channel-owned neural synthetic voice",
        },
    }
    STORY.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-tts", action="store_true")
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()

    units, sections = read_script()
    request = narration_request(units)
    REQUEST.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")

    if args.manifest_only:
        if not RAW_TIMING.is_file() or not AUDIO.is_file():
            raise FileNotFoundError("Exact narration artifacts do not exist yet")
    elif args.force_tts or not RAW_TIMING.is_file() or not AUDIO.is_file():
        from pipeline.narration.service import _worker_command

        subprocess.run(
            _worker_command(request, REQUEST, AUDIO, RAW_TIMING),
            cwd=ROOT,
            check=True,
        )

    raw = json.loads(RAW_TIMING.read_text(encoding="utf-8"))
    windows = exact_windows(raw)
    write_timing(windows, raw)
    build_story(request, units, sections, windows)
    print(
        json.dumps(
            {
                "audio": str(AUDIO),
                "story": str(STORY),
                "beats": len(windows),
                "duration_seconds": windows[-1]["end_time"],
                "timing_source": (
                    "edge_word_boundaries_pcm_samples"
                    if raw.get("engine") == "edge_tts"
                    else "exact_pcm_samples"
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
