"""Edge neural TTS worker with section-continuous prosody and PCM timing.

The worker synthesizes each script section as one utterance so adjacent beats do
not restart the voice. Native Edge word boundaries are projected onto the final
48 kHz PCM sample clock, and section pauses are then written as exact samples.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import subprocess
import tempfile
import wave
from array import array
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable


TICKS_PER_SECOND = 10_000_000


def _pcm16(values: Iterable[float]) -> bytes:
    samples = array("h")
    for value in values:
        normalized = max(-1.0, min(1.0, float(value)))
        samples.append(int(round(normalized * 32767.0)))
    return samples.tobytes()


def _test_audio(text: str, sample_rate: int) -> bytes:
    word_count = max(1, len(text.split()))
    sample_count = max(sample_rate // 4, round(word_count * sample_rate / 3.25))
    return _pcm16(
        0.015 * math.sin(2.0 * math.pi * 190.0 * index / sample_rate)
        for index in range(sample_count)
    )


def _rate(speed: float) -> str:
    percent = round((speed - 1.0) * 100)
    return f"{percent:+d}%"


def _word_weight(text: str) -> int:
    return max(1, len(re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?", text)))


def _event_sample(event: dict[str, Any], key: str, sample_rate: int) -> int:
    ticks = int(event[key])
    return max(0, round(ticks * sample_rate / TICKS_PER_SECOND))


def _event_ranges(
    units: list[dict[str, Any]],
    events: list[dict[str, Any]],
    section_samples: int,
    sample_rate: int,
) -> list[tuple[int, int, int]]:
    """Return local (start, speech_end, end) samples for each narration beat."""

    if not events:
        weights = [_word_weight(str(unit["text"])) for unit in units]
        total = max(1, sum(weights))
        cursor = 0
        ranges: list[tuple[int, int, int]] = []
        for index, weight in enumerate(weights):
            start = round(section_samples * cursor / total)
            cursor += weight
            end = section_samples if index == len(weights) - 1 else round(
                section_samples * cursor / total
            )
            ranges.append((start, end, end))
        return ranges

    weights = [_word_weight(str(unit["text"])) for unit in units]
    total_weight = max(1, sum(weights))
    event_count = len(events)
    event_edges = [0]
    cumulative = 0
    for index, weight in enumerate(weights[:-1], start=1):
        cumulative += weight
        proposed = round(event_count * cumulative / total_weight)
        minimum = event_edges[-1] + 1
        maximum = event_count - (len(weights) - index)
        event_edges.append(max(minimum, min(maximum, proposed)))
    event_edges.append(event_count)

    ranges = []
    for index in range(len(units)):
        first_event = event_edges[index]
        next_event = event_edges[index + 1]
        start = (
            0
            if index == 0
            else _event_sample(events[first_event], "offset", sample_rate)
        )
        last = events[max(first_event, next_event - 1)]
        speech_end = _event_sample(last, "offset", sample_rate) + _event_sample(
            last, "duration", sample_rate
        )
        end = (
            section_samples
            if index == len(units) - 1
            else _event_sample(events[next_event], "offset", sample_rate)
        )
        start = min(section_samples - 1, max(0, start))
        speech_end = min(section_samples, max(start + 1, speech_end))
        end = min(section_samples, max(speech_end, end))
        ranges.append((start, speech_end, end))
    return ranges


async def _synthesize_section(
    text: str,
    *,
    voice: str,
    speed: float,
    mp3_path: Path,
) -> list[dict[str, Any]]:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=_rate(speed))
    events: list[dict[str, Any]] = []
    with mp3_path.open("wb") as audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                events.append(
                    {
                        "offset": int(chunk["offset"]),
                        "duration": int(chunk["duration"]),
                        "text": str(chunk.get("text") or ""),
                    }
                )
    if not mp3_path.is_file() or not mp3_path.stat().st_size:
        raise RuntimeError("Edge TTS produced no audio")
    return events


def _decode_pcm(mp3_path: Path, wav_path: Path, sample_rate: int, ffmpeg: str) -> bytes:
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(mp3_path),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ],
        check=True,
    )
    with wave.open(str(wav_path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise RuntimeError("Edge TTS PCM decode must be 16-bit mono")
        if wav.getframerate() != sample_rate:
            raise RuntimeError("Edge TTS PCM decode changed the requested sample rate")
        return wav.readframes(wav.getnframes())


def synthesize(request: dict[str, Any], output_path: Path) -> dict[str, Any]:
    units = request.get("units")
    if not isinstance(units, list) or not units:
        raise ValueError("Narration request requires at least one unit")
    sample_rate = int(request.get("sample_rate", 48_000))
    test_mode = bool(request.get("test_mode", False))
    voice = str(request.get("voice_id") or "en-US-AvaMultilingualNeural")
    speed = float(request.get("voice_speed", 1.0))
    ffmpeg = str(request.get("ffmpeg_binary") or "ffmpeg")

    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for unit in units:
        grouped.setdefault(str(unit["section_id"]), []).append(unit)

    timings: list[dict[str, Any]] = []
    cursor = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        with tempfile.TemporaryDirectory(prefix="edge-tts-") as temp:
            temp_dir = Path(temp)
            for section_index, (section_id, section_units) in enumerate(grouped.items()):
                section_text = " ".join(str(unit["text"]).strip() for unit in section_units)
                if test_mode:
                    section_pcm = _test_audio(section_text, sample_rate)
                    events: list[dict[str, Any]] = []
                else:
                    mp3_path = temp_dir / f"section-{section_index:02d}.mp3"
                    wav_path = temp_dir / f"section-{section_index:02d}.wav"
                    events = asyncio.run(
                        _synthesize_section(
                            section_text,
                            voice=voice,
                            speed=speed,
                            mp3_path=mp3_path,
                        )
                    )
                    section_pcm = _decode_pcm(mp3_path, wav_path, sample_rate, ffmpeg)

                section_samples = len(section_pcm) // 2
                output.writeframesraw(section_pcm)
                ranges = _event_ranges(
                    section_units, events, section_samples, sample_rate
                )
                is_last_section = section_index == len(grouped) - 1
                section_pause = (
                    0
                    if is_last_section
                    else max(0, round(float(section_units[-1].get("pause_after_ms", 0)) * sample_rate / 1000))
                )
                for unit_index, (unit, local) in enumerate(zip(section_units, ranges)):
                    start, speech_end, end = local
                    if unit_index == len(section_units) - 1:
                        end += section_pause
                    timings.append(
                        {
                            "beat_id": unit["beat_id"],
                            "section_id": section_id,
                            "text": str(unit["text"]).strip(),
                            "kind": unit.get("kind", "narration"),
                            "start_sample": cursor + start,
                            "speech_end_sample": cursor + speech_end,
                            "end_sample": cursor + end,
                        }
                    )
                cursor += section_samples
                if section_pause:
                    output.writeframesraw(bytes(section_pause * 2))
                    cursor += section_pause

    return {
        "engine": "test" if test_mode else "edge_tts",
        "model": request.get("model_name") or "edge-tts",
        "voice_id": voice,
        "sample_rate": sample_rate,
        "duration_samples": cursor,
        "boundary_source": "proportional_test" if test_mode else "edge_word_boundary",
        "beats": timings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request_json", type=Path)
    parser.add_argument("output_wav", type=Path)
    parser.add_argument("result_json", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request_json.read_text(encoding="utf-8"))
    result = synthesize(request, args.output_wav)
    args.result_json.write_text(
        json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
