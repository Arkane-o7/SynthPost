"""dots.tts-MLX subprocess that emits PCM audio and exact cue offsets.

The worker runs in a dedicated dots.tts environment. It loads the model once,
enrolls or loads one authorized voice profile, then synthesizes every stable
production beat without making SynthPost's main environment depend on MLX.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path
from typing import Any, Iterable


def _pcm16(values: Iterable[float]) -> bytes:
    samples = array("h")
    for value in values:
        normalized = max(-1.0, min(1.0, float(value)))
        samples.append(int(round(normalized * 32767.0)))
    if samples.itemsize != 2:
        raise RuntimeError("This platform does not provide 16-bit signed shorts")
    return samples.tobytes()


def _test_audio(text: str, sample_rate: int) -> bytes:
    word_count = max(1, len(text.split()))
    sample_count = max(sample_rate // 4, round(word_count * sample_rate / 3.2))
    values = (
        0.015 * math.sin(2.0 * math.pi * 180.0 * index / sample_rate)
        for index in range(sample_count)
    )
    return _pcm16(values)


def _atempo_chain(speed: float) -> str:
    factors: list[float] = []
    remaining = speed
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    return ",".join(f"atempo={factor:.6f}" for factor in factors)


def _apply_speed(
    values: Any,
    *,
    sample_rate: int,
    speed: float,
    ffmpeg_binary: str,
) -> Any:
    if abs(speed - 1.0) <= 1e-3:
        return values
    if not shutil.which(ffmpeg_binary) and not Path(ffmpeg_binary).is_file():
        raise RuntimeError(
            f"FFmpeg is required for dots.tts speed={speed}, but "
            f"{ffmpeg_binary!r} was not found"
        )

    import soundfile as sf

    with tempfile.TemporaryDirectory(prefix="dots-speed-") as temp:
        source = Path(temp) / "source.wav"
        output = Path(temp) / "output.wav"
        sf.write(source, values, sample_rate)
        subprocess.run(
            [
                ffmpeg_binary,
                "-y",
                "-v",
                "error",
                "-i",
                str(source),
                "-filter:a",
                _atempo_chain(speed),
                str(output),
            ],
            check=True,
        )
        stretched, stretched_rate = sf.read(output, dtype="float32")
        if int(stretched_rate) != sample_rate:
            raise RuntimeError(
                f"FFmpeg changed dots.tts sample rate to {stretched_rate}"
            )
        return stretched


def _load_runtime(request: dict[str, Any]) -> tuple[Any, Any]:
    model_path = Path(str(request.get("model_path") or ""))
    required_model_files = (
        "config.json",
        "core.safetensors",
        "speaker.safetensors",
        "vocoder.safetensors",
        "tokenizer/tokenizer.json",
    )
    missing_model_files = [
        name for name in required_model_files if not (model_path / name).is_file()
    ]
    if missing_model_files:
        raise RuntimeError(
            f"dots.tts model is incomplete at {model_path}; missing "
            f"{', '.join(missing_model_files)}. "
            "Run `make setup-tts`."
        )

    try:
        import mlx.core as mx
        from dots_tts_mlx.loader import from_pretrained
    except ImportError as exc:
        raise RuntimeError(
            "dots-tts-mlx is unavailable in SYNTHPOST_TTS_PYTHON. "
            "Run `make setup-tts`."
        ) from exc

    model = from_pretrained(str(model_path), dtype=mx.bfloat16).model
    profile_path = request.get("voice_profile_path")
    if profile_path:
        try:
            from dots_tts_mlx.profile import SpeakerProfile
        except ImportError as exc:
            raise RuntimeError("dots.tts SpeakerProfile support is unavailable") from exc
        profile = SpeakerProfile.load(str(profile_path))
        return model, profile

    reference_audio = request.get("reference_audio_path")
    reference_text = str(request.get("reference_text") or "").strip()
    if not reference_audio or not Path(str(reference_audio)).is_file():
        raise RuntimeError(
            "dots.tts needs an authorized reference voice. Set "
            "SYNTHPOST_TTS_VOICE_PROFILE_PATH, or set both "
            "SYNTHPOST_TTS_REFERENCE_AUDIO and SYNTHPOST_TTS_REFERENCE_TEXT."
        )
    if not reference_text:
        raise RuntimeError(
            "SYNTHPOST_TTS_REFERENCE_TEXT must be the exact transcript of "
            "SYNTHPOST_TTS_REFERENCE_AUDIO."
        )
    profile = model.enroll(
        str(reference_audio),
        reference_text,
        speaker_scale=float(request.get("speaker_scale", 1.5)),
    )
    return model, profile


def synthesize(request: dict[str, Any], output_path: Path) -> dict[str, Any]:
    sample_rate = int(request.get("sample_rate", 48_000))
    test_mode = bool(request.get("test_mode", False))
    units = request.get("units")
    if not isinstance(units, list) or not units:
        raise ValueError("Narration request requires at least one unit")

    model = profile = None
    if not test_mode:
        model, profile = _load_runtime(request)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    timings: list[dict[str, Any]] = []
    cursor = 0
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index, unit in enumerate(units):
            text = str(unit["text"]).strip()
            if not text:
                raise ValueError(f"Narration unit {unit.get('beat_id')} is empty")
            start_sample = cursor
            if test_mode:
                chunk = _test_audio(text, sample_rate)
            else:
                assert model is not None and profile is not None
                import mlx.core as mx
                import numpy as np

                kwargs: dict[str, Any] = {
                    "text": text,
                    "profile": profile,
                    "language": str(request.get("language_code") or "EN").upper(),
                    "guidance_scale": float(
                        request.get("guidance_scale", 1.2)
                    ),
                    "seed": int(request.get("seed", 42)) + index,
                    "max_generate_length": int(
                        request.get("max_generate_length", 500)
                    ),
                    "trim_onset": True,
                    "streaming_decode": True,
                }
                if request.get("num_steps") is not None:
                    kwargs["num_steps"] = int(request["num_steps"])
                generated = model.generate(**kwargs)
                actual_rate = int(generated["sample_rate"])
                if actual_rate != sample_rate:
                    raise RuntimeError(
                        f"dots.tts returned {actual_rate} Hz; expected {sample_rate} Hz"
                    )
                values = np.asarray(
                    generated["audio"].astype(mx.float32)
                ).reshape(-1)
                values = _apply_speed(
                    values,
                    sample_rate=sample_rate,
                    speed=float(request.get("voice_speed", 1.0)),
                    ffmpeg_binary=str(request.get("ffmpeg_binary") or "ffmpeg"),
                )
                chunk = _pcm16(values)
            if not chunk:
                raise RuntimeError(
                    f"dots.tts produced no audio for narration unit {unit['beat_id']}"
                )
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
        "engine": "test" if test_mode else "dots_tts",
        "model": request.get("model_name"),
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
