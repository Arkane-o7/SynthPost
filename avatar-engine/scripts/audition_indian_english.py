from __future__ import annotations

import csv
import importlib
import struct
import wave
from pathlib import Path
from typing import Any, Iterable

TEXT = (
    "Good evening. You're watching SynthPost. Today we're tracking inflation, "
    "interest rates, Nvidia, Washington, and a fast-moving update from global "
    "markets. Here's what matters, and why it matters now."
)

# For Indian/Hindi-accented English, keep the text pipeline English ('a') so
# English words stay intelligible, then load Hindi voices or English/Hindi blends.
VOICE_SPECS = [
    ("hf_alpha_english_g2p", "hf_alpha", "a", 0.95),
    ("hf_beta_english_g2p", "hf_beta", "a", 0.95),
    ("hm_omega_english_g2p", "hm_omega", "a", 0.95),
    ("hm_psi_english_g2p", "hm_psi", "a", 0.95),
    ("blend_af_sarah_hf_alpha", "af_sarah,hf_alpha", "a", 0.95),
    ("blend_af_sarah_hf_beta", "af_sarah,hf_beta", "a", 0.95),
    ("blend_af_kore_hf_alpha", "af_kore,hf_alpha", "a", 0.95),
    ("blend_af_nova_hf_beta", "af_nova,hf_beta", "a", 0.95),
    ("blend_bf_emma_hf_alpha", "bf_emma,hf_alpha", "a", 0.95),
    ("blend_bf_lily_hf_beta", "bf_lily,hf_beta", "a", 0.95),
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def main() -> None:
    root = project_root()
    output_dir = root / "assets" / "output" / "tts" / "auditions" / "indian_english"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "audition_text.txt").write_text(TEXT + "\n", encoding="utf-8")

    kokoro = importlib.import_module("kokoro")
    pipeline = kokoro.KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")

    rows: list[dict[str, str]] = []
    playlist: list[str] = []
    sample_rate = 24000

    for index, (label, voice, lang_code, speed) in enumerate(VOICE_SPECS, start=1):
        output_wav = (
            output_dir / f"{index:02d}_{label}_s{int(round(speed * 100)):03d}.wav"
        )
        print(
            f"[indian-english] {index:02d}/{len(VOICE_SPECS)} label={label} voice={voice} lang_code={lang_code} speed={speed}"
        )
        try:
            generator = pipeline(TEXT, voice=voice, speed=speed)
            chunks = [extract_kokoro_audio(result) for result in generator]
            if not chunks:
                raise RuntimeError("Kokoro returned no audio chunks")
            write_float_wav(output_wav, chunks, sample_rate)
            duration = wav_duration_seconds(output_wav)
            status = "ok"
            error = ""
            playlist.append(output_wav.name)
            print(f"[indian-english]   wrote {output_wav} ({duration:.2f}s)")
        except Exception as exc:
            duration = 0.0
            status = "failed"
            error = str(exc)
            print(f"[indian-english]   FAILED: {exc}")

        rows.append(
            {
                "index": str(index),
                "label": label,
                "voice": voice,
                "lang_code": lang_code,
                "speed": str(speed),
                "sample_rate": str(sample_rate),
                "duration_seconds": f"{duration:.3f}",
                "status": status,
                "wav_path": str(output_wav.relative_to(root)),
                "error": error,
            }
        )

    manifest_path = output_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "index",
                "label",
                "voice",
                "lang_code",
                "speed",
                "sample_rate",
                "duration_seconds",
                "status",
                "wav_path",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    playlist_path = output_dir / "playlist.m3u"
    playlist_path.write_text("\n".join(playlist) + "\n", encoding="utf-8")
    print(
        f"[indian-english] Done: {sum(row['status'] == 'ok' for row in rows)}/{len(rows)} generated"
    )
    print(f"[indian-english] Manifest: {manifest_path}")
    print(f"[indian-english] Playlist: {playlist_path}")


if __name__ == "__main__":
    main()
