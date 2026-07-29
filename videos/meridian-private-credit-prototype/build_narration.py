#!/usr/bin/env python3
"""Generate deterministic Meridian narration one beat at a time and assemble it."""

from __future__ import annotations

import argparse
import importlib.util
import json
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EPISODE = Path(__file__).resolve().parent
REQUEST = EPISODE / "narration-request.json"
SEGMENTS = EPISODE / "narration-segments"

WORKER_PATH = ROOT / "pipeline" / "narration" / "dots_worker.py"
WORKER_SPEC = importlib.util.spec_from_file_location("dots_worker", WORKER_PATH)
if WORKER_SPEC is None or WORKER_SPEC.loader is None:
    raise RuntimeError(f"Unable to load {WORKER_PATH}")
WORKER = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(WORKER)
synthesize = WORKER.synthesize


def generate(index: int) -> None:
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    units = request["units"]
    if index < 0 or index >= len(units):
        raise SystemExit(f"unit index must be between 0 and {len(units) - 1}")
    request["units"] = [units[index]]
    # Keep the enrolled Meridian voice and its deterministic delivery identical
    # across independently generated beats.  Varying this seed per unit changes
    # prosody enough to sound like the presenter is being swapped mid-video.
    request["seed"] = int(request.get("seed", 42))
    SEGMENTS.mkdir(parents=True, exist_ok=True)
    beat_id = units[index]["beat_id"]
    result = synthesize(request, SEGMENTS / f"{beat_id}.wav")
    (SEGMENTS / f"{beat_id}.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )


def assemble() -> None:
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    sample_rate = int(request.get("sample_rate", 48_000))
    output = EPISODE / "narration-raw.wav"
    cursor = 0
    timings: list[dict[str, object]] = []
    with wave.open(str(output), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        for unit in request["units"]:
            beat_id = unit["beat_id"]
            path = SEGMENTS / f"{beat_id}.wav"
            with wave.open(str(path), "rb") as source:
                if (
                    source.getnchannels() != 1
                    or source.getsampwidth() != 2
                    or source.getframerate() != sample_rate
                ):
                    raise RuntimeError(f"Unexpected PCM format in {path}")
                frames = source.readframes(source.getnframes())
            start_sample = cursor
            destination.writeframesraw(frames)
            cursor += len(frames) // 2
            timings.append(
                {
                    "beat_id": beat_id,
                    "section_id": unit["section_id"],
                    "text": unit["text"],
                    "kind": unit.get("kind", "narration"),
                    "start_sample": start_sample,
                    "speech_end_sample": cursor,
                    "end_sample": cursor,
                }
            )
    result = {
        "engine": "dots_tts",
        "model": request.get("model_name"),
        "sample_rate": sample_rate,
        "duration_samples": cursor,
        "beats": timings,
    }
    (EPISODE / "narration-timing-raw.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", type=int)
    parser.add_argument("--assemble", action="store_true")
    args = parser.parse_args()
    if args.assemble:
        assemble()
    elif args.unit is not None:
        generate(args.unit)
    else:
        parser.error("provide --unit INDEX or --assemble")


if __name__ == "__main__":
    main()
