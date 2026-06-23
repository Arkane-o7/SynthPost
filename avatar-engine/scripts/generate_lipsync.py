from __future__ import annotations

import argparse
import subprocess
import wave
from pathlib import Path

from utils import load_config, resolve_tool, write_json


def wav_duration_seconds(audio_wav: Path) -> float:
    with wave.open(str(audio_wav), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
    return frames / float(rate or 1)


def generate_fake_mouth_cues(audio_wav: Path, output_json: Path) -> Path:
    duration = wav_duration_seconds(audio_wav)
    values = ["X", "A", "B", "C", "D", "E", "F", "G", "H"]
    cue_length = 0.16
    cues = []
    start = 0.0
    index = 0
    while start < duration:
        end = min(duration, start + cue_length)
        cues.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "value": values[index % len(values)],
            }
        )
        start = end
        index += 1

    write_json(
        output_json,
        {
            "metadata": {
                "soundFile": str(audio_wav),
                "duration": round(duration, 3),
                "generator": "desk-avatar-engine fake rhubarb",
            },
            "mouthCues": cues,
        },
    )
    return output_json


def generate_lipsync(audio_wav: Path, output_json: Path, config_path: Path, test_mode: bool = False) -> Path:
    if not audio_wav.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_wav}")

    config = load_config(config_path)
    rhubarb_name = str(config.get("tools", {}).get("rhubarb", "rhubarb"))
    rhubarb_path = resolve_tool(rhubarb_name)

    if rhubarb_path and not test_mode:
        print(f"[lipsync] Running Rhubarb: {rhubarb_path}")
        output_json.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [str(rhubarb_path), "-f", "json", "-o", str(output_json), str(audio_wav)],
            check=True,
        )
        print(f"[lipsync] Wrote mouth cues: {output_json}")
        return output_json

    reason = "test mode enabled" if test_mode else f"Rhubarb not found at '{rhubarb_name}'"
    print(f"[lipsync] WARNING: {reason}; generating fake Rhubarb-style mouth cues.")
    generate_fake_mouth_cues(audio_wav, output_json)
    print(f"[lipsync] Wrote fake mouth cues: {output_json}")
    return output_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Rhubarb-style mouth cues.")
    parser.add_argument("audio_wav", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/default.yaml"))
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    generate_lipsync(args.audio_wav, args.output_json, args.config, args.test_mode)


if __name__ == "__main__":
    main()
