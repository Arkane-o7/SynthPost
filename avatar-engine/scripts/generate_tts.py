from __future__ import annotations

import argparse
import importlib
import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from utils import load_config, load_json


DEFAULT_TTS_SETTINGS = {
    "engine": "kokoro",
    "voice": "af_heart",
    "speed": 1.0,
    "sample_rate": 24000,
    "lang_code": "a",
}


@dataclass(frozen=True)
class TTSResult:
    path: Path
    engine_used: str


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def kokoro_availability() -> tuple[bool, str]:
    try:
        module = importlib.import_module("kokoro")
    except Exception as exc:
        return False, f"not importable: {exc}"

    if not hasattr(module, "KPipeline"):
        location = getattr(module, "__file__", "<unknown>")
        return False, f"imported from {location}, but KPipeline is missing"
    return True, f"imported from {getattr(module, '__file__', '<unknown>')}"


def load_default_config(config_path: Path | None) -> dict[str, Any]:
    path = config_path or (project_root() / "config" / "default.yaml")
    if not path.exists():
        return {}
    try:
        return load_config(path)
    except Exception as exc:
        print(f"[tts] WARNING: Could not load config {path}: {exc}")
        return {}


def tts_settings(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    settings = dict(DEFAULT_TTS_SETTINGS)
    config_tts = config.get("tts", {})
    if isinstance(config_tts, dict):
        settings.update(config_tts)

    job_voice = job.get("voice", {})
    if isinstance(job_voice, dict):
        settings.update(job_voice)

    if "voice_id" in settings and "voice" not in job_voice:
        settings["voice"] = settings["voice_id"]
    elif isinstance(job_voice, dict) and "voice_id" in job_voice:
        settings["voice"] = job_voice["voice_id"]

    settings["engine"] = str(settings.get("engine", "kokoro")).lower()
    settings["voice"] = str(settings.get("voice", "af_heart"))
    settings["speed"] = float(settings.get("speed", 1.0))
    settings["sample_rate"] = int(settings.get("sample_rate", 24000))
    settings["lang_code"] = str(settings.get("lang_code") or infer_kokoro_lang_code(settings["voice"]))
    return settings


def infer_kokoro_lang_code(voice: str) -> str:
    first = voice[:1].lower()
    return first if first in {"a", "b", "e", "f", "h", "i", "j", "p", "z"} else "a"


def flatten_audio(audio: Any) -> Iterable[float]:
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

    for value in audio:
        if isinstance(value, (list, tuple)):
            for inner in value:
                yield float(inner)
        else:
            yield float(value)


def write_float_wav(output_wav: Path, chunks: list[Any], sample_rate: int) -> None:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_wav), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for chunk in chunks:
            for value in flatten_audio(chunk):
                sample = int(max(-1.0, min(1.0, value)) * 32767)
                wav.writeframesraw(struct.pack("<h", sample))


def extract_kokoro_audio(result: Any) -> Any:
    if hasattr(result, "audio"):
        return result.audio
    if hasattr(result, "output") and hasattr(result.output, "audio"):
        return result.output.audio
    if isinstance(result, tuple) and len(result) >= 3:
        return result[2]
    return result


def generate_with_kokoro(job: dict[str, Any], settings: dict[str, Any], output_wav: Path) -> bool:
    if settings["engine"] != "kokoro":
        print(f"[tts] WARNING: Unsupported TTS engine '{settings['engine']}'; using placeholder WAV.")
        return False

    available, detail = kokoro_availability()
    if not available:
        print(f"[tts] WARNING: Kokoro unavailable ({detail}).")
        return False

    script = str(job.get("script", "")).strip()
    if not script:
        print("[tts] WARNING: Job script is empty; using placeholder WAV.")
        return False

    try:
        kokoro = importlib.import_module("kokoro")
        pipeline = kokoro.KPipeline(lang_code=settings["lang_code"])
        print(
            "[tts] Using local Kokoro "
            f"voice={settings['voice']} speed={settings['speed']} lang_code={settings['lang_code']}"
        )
        generator = pipeline(script, voice=settings["voice"], speed=settings["speed"])
        audio_chunks = []
        for result in generator:
            audio_chunks.append(extract_kokoro_audio(result))
        if not audio_chunks:
            print("[tts] WARNING: Kokoro returned no audio; using placeholder WAV.")
            return False
        write_float_wav(output_wav, audio_chunks, settings["sample_rate"])
    except Exception as exc:
        print(f"[tts] WARNING: Kokoro failed during synthesis: {exc}")
        return False

    return True


def estimate_duration_seconds(script: str) -> float:
    words = max(1, len(script.split()))
    return max(2.0, min(30.0, words / 2.6))


def generate_placeholder_wav(output_wav: Path, duration_seconds: float, sample_rate: int) -> None:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    amplitude = 1200
    beep_frequency = 440.0
    total_samples = int(duration_seconds * sample_rate)

    with wave.open(str(output_wav), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(total_samples):
            second = index / sample_rate
            in_beep = int(second * 2) % 2 == 0 and second < duration_seconds - 0.25
            sample = 0
            if in_beep:
                sample = int(amplitude * math.sin(2 * math.pi * beep_frequency * second))
            wav.writeframesraw(struct.pack("<h", sample))


def default_output_path(job: dict[str, Any]) -> Path:
    job_id = str(job.get("job_id", "tts_test"))
    return project_root() / "assets" / "temp" / job_id / "audio.wav"


def generate_tts(
    job_json_path: Path,
    output_wav: Path | None = None,
    config_path: Path | None = None,
    test_mode: bool = False,
) -> Path:
    return generate_tts_result(job_json_path, output_wav, config_path, test_mode).path


def generate_tts_result(
    job_json_path: Path,
    output_wav: Path | None = None,
    config_path: Path | None = None,
    test_mode: bool = False,
) -> TTSResult:
    job = load_json(job_json_path)
    config = load_default_config(config_path)
    settings = tts_settings(job, config)
    output_wav = output_wav or default_output_path(job)
    sample_rate = int(settings["sample_rate"])
    script = str(job.get("script", ""))

    print(f"[tts] Generating audio for job: {job.get('job_id', '<unknown>')}")
    if not test_mode and generate_with_kokoro(job, settings, output_wav):
        print(f"[tts] Wrote Kokoro audio: {output_wav}")
        return TTSResult(output_wav, "kokoro")

    if test_mode:
        print("[tts] Test mode enabled; using placeholder beep WAV.")
        engine_used = "placeholder_test"
    else:
        print("[tts] WARNING: Kokoro is unavailable or not configured; using placeholder WAV.")
        engine_used = "placeholder_fallback"

    generate_placeholder_wav(output_wav, estimate_duration_seconds(script), sample_rate)
    print(f"[tts] Wrote placeholder audio: {output_wav}")
    return TTSResult(output_wav, engine_used)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate local TTS audio for a desk-avatar job.")
    parser.add_argument("job_json", type=Path)
    parser.add_argument("output_wav", nargs="?", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/default.yaml"))
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    generate_tts(args.job_json, args.output_wav, config_path=args.config, test_mode=args.test_mode)


if __name__ == "__main__":
    main()
