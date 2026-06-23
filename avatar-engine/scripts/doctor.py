from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from utils import load_config, load_json, resolve_tool  # noqa: E402
from generate_tts import kokoro_availability, tts_settings  # noqa: E402
from run_manifest import sha256_text  # noqa: E402


REQUIRED_MOUTH_TEXTURES = (
    "mouth_X.png",
    "mouth_A.png",
    "mouth_B.png",
    "mouth_C.png",
    "mouth_D.png",
    "mouth_E.png",
    "mouth_F.png",
    "mouth_G.png",
    "mouth_H.png",
)

REQUIRED_ASSET_FOLDERS = (
    "assets",
    "assets/characters",
    "assets/characters/avatar_01",
    "assets/renders",
    "assets/output",
    "assets/temp",
)


class Doctor:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def ok(self, label: str, detail: str = "") -> None:
        self.passed += 1
        print(f"[OK]   {label}{': ' + detail if detail else ''}")

    def fail(self, label: str, detail: str = "") -> None:
        self.failed += 1
        print(f"[FAIL] {label}{': ' + detail if detail else ''}")

    def warn(self, label: str, detail: str = "") -> None:
        self.warnings += 1
        print(f"[WARN] {label}{': ' + detail if detail else ''}")

    def summary(self) -> int:
        print("")
        print("Health summary")
        print(f"  Pass: {self.passed}")
        print(f"  Warn: {self.warnings}")
        print(f"  Fail: {self.failed}")
        if self.failed:
            print("Result: FAIL")
            return 1
        print("Result: PASS")
        return 0


def run_version(command: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        return False, str(exc)
    output = (result.stdout or result.stderr).strip().splitlines()
    first_line = output[0] if output else f"exit code {result.returncode}"
    return result.returncode == 0, first_line


def check_tool(doctor: Doctor, config: dict[str, Any], key: str, version_args: list[str]) -> Path | None:
    configured = str(config.get("tools", {}).get(key, key))
    resolved = resolve_tool(configured)
    if resolved is None:
        doctor.fail(f"{key} binary", f"not found at '{configured}'")
        return None

    ok, detail = run_version([str(resolved), *version_args])
    if ok:
        doctor.ok(f"{key} binary", f"{resolved} ({detail})")
    else:
        doctor.fail(f"{key} binary", f"{resolved} did not run: {detail}")
    return resolved if ok else None


def check_blender_template(doctor: Doctor, blender_path: Path | None, template_path: Path) -> None:
    if not template_path.exists():
        doctor.fail("Blender template", f"missing: {template_path}")
        return
    doctor.ok("Blender template", str(template_path))

    if blender_path is None:
        doctor.warn("Template object validation", "skipped because Blender is unavailable")
        return

    validator = PROJECT_ROOT / "blender" / "validate_template.py"
    command = [str(blender_path), "-b", str(template_path), "--python", str(validator)]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60)
    except Exception as exc:
        doctor.fail("Template object validation", str(exc))
        return

    output_lines = [line for line in (result.stdout + "\n" + result.stderr).splitlines() if "[template]" in line]
    output = "\n".join(output_lines)
    missing_optional_actions = [
        line.split("WARN missing:", 1)[1].strip()
        for line in output_lines
        if "WARN missing:" in line
    ]
    if result.returncode == 0:
        doctor.ok("Template object validation", "all required objects found")
    else:
        doctor.fail("Template object validation", "missing required objects")
    if missing_optional_actions:
        doctor.warn("Template optional gesture Actions", ", ".join(missing_optional_actions))
    if output:
        for line in output.splitlines():
            print(f"       {line}")


def check_kokoro(doctor: Doctor, config: dict[str, Any], sample_job: Path) -> None:
    job: dict[str, Any] = {}
    if sample_job.exists():
        try:
            job = load_json(sample_job)
        except Exception:
            job = {}

    settings = tts_settings(job, config)
    if settings["engine"] != "kokoro":
        doctor.warn("Kokoro TTS", f"config engine is '{settings['engine']}', fallback audio will be used")
        return

    available, detail = kokoro_availability()
    voice_detail = f"voice={settings['voice']} speed={settings['speed']} sample_rate={settings['sample_rate']}"
    if available:
        doctor.ok("Kokoro TTS", f"{voice_detail}; {detail}")
    else:
        doctor.warn("Kokoro TTS", f"{voice_detail}; {detail}; placeholder fallback will be used")


def main() -> None:
    doctor = Doctor()

    print("desk-avatar-engine doctor")
    print(f"Project root: {PROJECT_ROOT}")
    print("")

    if sys.version_info >= (3, 11):
        doctor.ok("Python version", f"{platform.python_version()}")
    else:
        doctor.warn("Python version", f"{platform.python_version()} (Python 3.11+ recommended)")

    if (PROJECT_ROOT / "scripts" / "run_job.py").exists() and (PROJECT_ROOT / "blender").exists():
        doctor.ok("Project root detection", str(PROJECT_ROOT))
    else:
        doctor.fail("Project root detection", "expected scripts/run_job.py and blender/")

    if sha256_text("manifest-check"):
        doctor.ok("Run manifest helper", "importable")

    config_path = PROJECT_ROOT / "config" / "default.yaml"
    config: dict[str, Any] = {}
    if config_path.exists():
        try:
            config = load_config(config_path)
            doctor.ok("Config loads", str(config_path))
        except Exception as exc:
            doctor.fail("Config loads", str(exc))
    else:
        doctor.fail("Config exists", str(config_path))

    blender_path = check_tool(doctor, config, "blender", ["--version"]) if config else None
    check_tool(doctor, config, "ffmpeg", ["-version"]) if config else None
    check_tool(doctor, config, "rhubarb", ["--version"]) if config else None

    sample_job = PROJECT_ROOT / "jobs" / "sample_job.json"
    if config:
        check_kokoro(doctor, config, sample_job)

    check_blender_template(doctor, blender_path, PROJECT_ROOT / "blender" / "avatar_template.blend")

    if sample_job.exists():
        try:
            load_json(sample_job)
            doctor.ok("Sample job loads", str(sample_job))
        except Exception as exc:
            doctor.fail("Sample job loads", str(exc))
    else:
        doctor.fail("Sample job exists", str(sample_job))

    for folder in REQUIRED_ASSET_FOLDERS:
        path = PROJECT_ROOT / folder
        if path.exists() and path.is_dir():
            doctor.ok("Asset folder", folder)
        else:
            doctor.fail("Asset folder", f"missing: {folder}")

    mouth_dir = PROJECT_ROOT / "assets" / "characters" / "avatar_01" / "mouth_textures"
    if mouth_dir.exists() and mouth_dir.is_dir():
        doctor.ok("Mouth texture folder", str(mouth_dir))
    else:
        doctor.fail("Mouth texture folder", str(mouth_dir))

    for filename in REQUIRED_MOUTH_TEXTURES:
        path = mouth_dir / filename
        if path.exists():
            doctor.ok("Mouth texture", filename)
        else:
            doctor.fail("Mouth texture", f"missing: {filename}")

    raise SystemExit(doctor.summary())


if __name__ == "__main__":
    main()
