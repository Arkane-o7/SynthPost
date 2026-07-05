from __future__ import annotations

import argparse
import csv
import importlib
import struct
import wave
from pathlib import Path
from typing import Any, Iterable

DEFAULT_SCRIPT = (
    "Good evening. You're watching SynthPost. Today we're tracking inflation, "
    "interest rates, Nvidia, Washington, and a fast-moving update from global "
    "markets. Here's what matters, and why it matters now."
)

FALLBACK_KOKORO_VOICES = [
    "af_alloy",
    "af_aoede",
    "af_bella",
    "af_heart",
    "af_jessica",
    "af_kore",
    "af_nicole",
    "af_nova",
    "af_river",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_michael",
    "am_onyx",
    "am_puck",
    "am_santa",
    "bf_alice",
    "bf_emma",
    "bf_isabella",
    "bf_lily",
    "bm_daniel",
    "bm_fable",
    "bm_george",
    "bm_lewis",
    "ef_dora",
    "em_alex",
    "em_santa",
    "ff_siwis",
    "hf_alpha",
    "hf_beta",
    "hm_omega",
    "hm_psi",
    "if_sara",
    "im_nicola",
    "jf_alpha",
    "jf_gongitsune",
    "jf_nezumi",
    "jf_tebukuro",
    "jm_kumo",
    "pf_dora",
    "pm_alex",
    "pm_santa",
    "zf_xiaobei",
    "zf_xiaoni",
    "zf_xiaoxiao",
    "zf_xiaoyi",
    "zm_yunjian",
    "zm_yunxi",
    "zm_yunxia",
    "zm_yunyang",
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def kokoro_voice_names() -> list[str]:
    try:
        from huggingface_hub import list_repo_files

        files = list_repo_files("hexgrad/Kokoro-82M")
        return sorted(
            f[len("voices/") : -3]
            for f in files
            if f.startswith("voices/") and f.endswith(".pt")
        )
    except Exception as exc:
        print(f"[audition] WARNING: Could not query Kokoro repo voice list: {exc}")
        return sorted(FALLBACK_KOKORO_VOICES)


def default_female_english_voices() -> list[str]:
    voices = kokoro_voice_names()
    return [voice for voice in voices if voice[:2] in {"af", "bf"}]


def all_female_voices() -> list[str]:
    voices = kokoro_voice_names()
    return [voice for voice in voices if len(voice) >= 2 and voice[1] == "f"]


def infer_lang_code(voice: str) -> str:
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


def extract_kokoro_audio(result: Any) -> Any:
    if hasattr(result, "audio"):
        return result.audio
    if hasattr(result, "output") and hasattr(result.output, "audio"):
        return result.output.audio
    if isinstance(result, tuple) and len(result) >= 3:
        return result[2]
    return result


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


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
    return frames / float(rate or 1)


def synthesize_voice(
    kokoro: Any,
    pipelines: dict[str, Any],
    voice: str,
    text: str,
    speed: float,
    sample_rate: int,
    output_wav: Path,
) -> float:
    lang_code = infer_lang_code(voice)
    if lang_code not in pipelines:
        pipelines[lang_code] = kokoro.KPipeline(
            lang_code=lang_code,
            repo_id="hexgrad/Kokoro-82M",
        )
    pipeline = pipelines[lang_code]
    generator = pipeline(text, voice=voice, speed=speed)
    audio_chunks = [extract_kokoro_audio(result) for result in generator]
    if not audio_chunks:
        raise RuntimeError("Kokoro returned no audio chunks")
    write_float_wav(output_wav, audio_chunks, sample_rate)
    return wav_duration_seconds(output_wav)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate short Kokoro voice audition WAVs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/output/tts/auditions/female_english"),
    )
    parser.add_argument("--text", default=DEFAULT_SCRIPT)
    parser.add_argument("--speed", type=float, default=0.95)
    parser.add_argument("--sample-rate", type=int, default=24000)
    parser.add_argument(
        "--voices",
        default="",
        help="Comma-separated voice list. Defaults to English female Kokoro voices.",
    )
    parser.add_argument(
        "--all-female",
        action="store_true",
        help="Use every Kokoro voice whose second prefix letter is f, including non-English voices.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = project_root()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.voices.strip():
        voices = [v.strip() for v in args.voices.split(",") if v.strip()]
    elif args.all_female:
        voices = all_female_voices()
    else:
        voices = default_female_english_voices()

    kokoro = importlib.import_module("kokoro")
    if not hasattr(kokoro, "KPipeline"):
        raise RuntimeError("Installed kokoro package does not expose KPipeline")

    speed_tag = f"s{int(round(args.speed * 100)):03d}"
    manifest_path = output_dir / "manifest.csv"
    playlist_path = output_dir / "playlist.m3u"
    text_path = output_dir / "audition_text.txt"
    text_path.write_text(args.text + "\n", encoding="utf-8")

    rows: list[dict[str, str]] = []
    playlist_entries: list[str] = []
    pipelines: dict[str, Any] = {}

    for index, voice in enumerate(voices, start=1):
        output_wav = output_dir / f"{index:02d}_{voice}_{speed_tag}.wav"
        print(f"[audition] {index:02d}/{len(voices)} voice={voice} speed={args.speed}")
        try:
            duration = synthesize_voice(
                kokoro=kokoro,
                pipelines=pipelines,
                voice=voice,
                text=args.text,
                speed=args.speed,
                sample_rate=args.sample_rate,
                output_wav=output_wav,
            )
            status = "ok"
            error = ""
            playlist_entries.append(output_wav.name)
            print(f"[audition]   wrote {output_wav} ({duration:.2f}s)")
        except Exception as exc:
            duration = 0.0
            status = "failed"
            error = str(exc)
            print(f"[audition]   FAILED: {exc}")

        rows.append(
            {
                "index": str(index),
                "voice": voice,
                "speed": str(args.speed),
                "sample_rate": str(args.sample_rate),
                "lang_code": infer_lang_code(voice),
                "duration_seconds": f"{duration:.3f}",
                "status": status,
                "wav_path": str(output_wav.relative_to(root)),
                "error": error,
            }
        )

    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "index",
                "voice",
                "speed",
                "sample_rate",
                "lang_code",
                "duration_seconds",
                "status",
                "wav_path",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    playlist_path.write_text("\n".join(playlist_entries) + "\n", encoding="utf-8")

    ok_count = sum(1 for row in rows if row["status"] == "ok")
    print(f"[audition] Done: {ok_count}/{len(rows)} clips generated")
    print(f"[audition] Manifest: {manifest_path}")
    print(f"[audition] Playlist: {playlist_path}")


if __name__ == "__main__":
    main()
