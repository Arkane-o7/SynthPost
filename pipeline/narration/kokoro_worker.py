"""Small Kokoro subprocess that emits PCM audio and sample-exact cue offsets.

The worker intentionally has no SynthPost imports. It runs with the avatar
engine Python environment, where Kokoro and its native dependencies live.
"""

from __future__ import annotations

import argparse
import json
import math
import wave
from array import array
from pathlib import Path
from typing import Any, Iterable


def _audio_values(result: Any) -> Iterable[float]:
    audio = getattr(result, "audio", None)
    if audio is None and isinstance(result, (tuple, list)) and len(result) >= 3:
        audio = result[2]
    if audio is None:
        raise RuntimeError("Kokoro returned a chunk without audio")
    if hasattr(audio, "detach"):
        audio = audio.detach()
    if hasattr(audio, "cpu"):
        audio = audio.cpu()
    if hasattr(audio, "numpy"):
        audio = audio.numpy()
    if hasattr(audio, "reshape"):
        audio = audio.reshape(-1)
    if hasattr(audio, "tolist"):
        audio = audio.tolist()
    return audio


def _pcm16(values: Iterable[float]) -> bytes:
    samples = array("h")
    for value in values:
        normalized = max(-1.0, min(1.0, float(value)))
        samples.append(int(round(normalized * 32767.0)))
    if samples.itemsize != 2:
        raise RuntimeError("This platform does not provide 16-bit signed shorts")
    return samples.tobytes()


def _test_audio(text: str, sample_rate: int) -> bytes:
    # Deterministic, quiet speech-shaped audio used only by automated tests.
    word_count = max(1, len(text.split()))
    sample_count = max(sample_rate // 4, round(word_count * sample_rate / 3.2))
    values = (
        0.015 * math.sin(2.0 * math.pi * 180.0 * index / sample_rate)
        for index in range(sample_count)
    )
    return _pcm16(values)


def synthesize(request: dict[str, Any], output_path: Path) -> dict[str, Any]:
    sample_rate = int(request.get("sample_rate", 24000))
    test_mode = bool(request.get("test_mode", False))
    units = request.get("units")
    if not isinstance(units, list) or not units:
        raise ValueError("Narration request requires at least one unit")

    pipeline = None
    if not test_mode:
        try:
            from kokoro import KPipeline
        except ImportError as exc:
            raise RuntimeError(
                "Kokoro is unavailable in the configured avatar Python environment"
            ) from exc
        pipeline = KPipeline(lang_code=str(request["language_code"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    timings: list[dict[str, Any]] = []
    cursor = 0
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for unit in units:
            text = str(unit["text"]).strip()
            if not text:
                raise ValueError(f"Narration unit {unit.get('beat_id')} is empty")
            start_sample = cursor
            if test_mode:
                chunks = [_test_audio(text, sample_rate)]
            else:
                assert pipeline is not None
                chunks = [
                    _pcm16(_audio_values(result))
                    for result in pipeline(
                        text,
                        voice=str(request["voice_id"]),
                        speed=float(request["voice_speed"]),
                    )
                ]
            if not chunks or not any(chunks):
                raise RuntimeError(
                    f"Kokoro produced no audio for narration unit {unit['beat_id']}"
                )
            for chunk in chunks:
                wav.writeframesraw(chunk)
                cursor += len(chunk) // 2
            speech_end_sample = cursor
            pause_samples = max(
                0, round(float(unit.get("pause_after_ms", 0)) * sample_rate / 1000)
            )
            if pause_samples:
                wav.writeframesraw(bytes(pause_samples * 2))
                cursor += pause_samples
            timings.append(
                {
                    "beat_id": unit["beat_id"],
                    "section_id": unit["section_id"],
                    "text": text,
                    "kind": unit.get("kind", "narration"),
                    "start_sample": start_sample,
                    "speech_end_sample": speech_end_sample,
                    "end_sample": cursor,
                }
            )

    return {
        "engine": "test" if test_mode else "kokoro",
        "sample_rate": sample_rate,
        "duration_samples": cursor,
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
