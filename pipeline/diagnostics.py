"""Local dependency and configuration diagnostics for SynthPost developers."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from pipeline import config
from pipeline.storage import PROJECT_ROOT, resolve_project_path


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: str
    requirement: str
    detail: str
    remedy: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"available", "configured", "optional_missing"}

    def as_dict(self) -> dict[str, object]:
        return {**asdict(self), "ok": self.ok}


def _binary(
    name: str,
    command: str,
    *,
    requirement: str,
    remedy: str,
) -> DiagnosticCheck:
    path = shutil.which(command)
    if path:
        return DiagnosticCheck(name, "available", requirement, path)
    status = "optional_missing" if requirement == "optional" else "missing"
    return DiagnosticCheck(name, status, requirement, f"{command} not found", remedy)


def _directory(name: str, path: Path, requirement: str) -> DiagnosticCheck:
    if path.is_dir():
        return DiagnosticCheck(name, "available", requirement, str(path))
    status = "optional_missing" if requirement == "optional" else "missing"
    return DiagnosticCheck(
        name,
        status,
        requirement,
        f"directory not found: {path}",
        "Run `make setup` or restore the repository directory.",
    )


def _dots_tts(settings) -> DiagnosticCheck:
    interpreter = resolve_project_path(settings.narration.python_path)
    if not interpreter.exists():
        return DiagnosticCheck(
            "dots_tts",
            "missing",
            "feature",
            f"configured narration Python not found: {interpreter}",
            "Run `make setup-tts` or set SYNTHPOST_TTS_PYTHON.",
        )
    result = subprocess.run(
        [
            str(interpreter),
            "-c",
            (
                "import importlib.metadata; import dots_tts_mlx; "
                "print(importlib.metadata.version('dots-tts-mlx'))"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return DiagnosticCheck(
            "dots_tts",
            "missing",
            "feature",
            f"dots-tts-mlx import failed in {interpreter}",
            "Run `make setup-tts`.",
        )
    version = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "installed"
    model_path = resolve_project_path(settings.narration.model_path)
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
        return DiagnosticCheck(
            "dots_tts",
            "missing",
            "feature",
            f"dots-tts-mlx {version}; incomplete model at {model_path}: "
            f"{', '.join(missing_model_files)}",
            "Run `make setup-tts` to download the configured MLX checkpoint.",
        )
    profile_path = settings.narration.voice_profile_path
    reference_path = settings.narration.reference_audio_path
    has_profile = bool(profile_path and resolve_project_path(profile_path).is_dir())
    has_reference = bool(
        reference_path
        and resolve_project_path(reference_path).is_file()
        and settings.narration.reference_text
    )
    if not has_profile and not has_reference:
        return DiagnosticCheck(
            "dots_tts",
            "misconfigured",
            "feature",
            f"dots-tts-mlx {version}; model={model_path}; no authorized voice configured",
            "Enroll a voice profile or set SYNTHPOST_TTS_REFERENCE_AUDIO and "
            "SYNTHPOST_TTS_REFERENCE_TEXT.",
        )
    return DiagnosticCheck(
        "dots_tts",
        "available",
        "feature",
        f"dots-tts-mlx {version}; model={model_path}; voice={settings.narration.voice_id}",
    )


def _codex(settings) -> DiagnosticCheck:
    binary = settings.llm.codex_binary
    path = shutil.which(binary)
    if not path:
        return DiagnosticCheck(
            "codex",
            "missing",
            "feature",
            f"Codex CLI not found at {binary!r}",
            "Install Codex or set SYNTHPOST_CODEX_BINARY.",
        )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "CODEX_HOME",
            "HOME",
            "LANG",
            "LC_ALL",
            "LOGNAME",
            "PATH",
            "SHELL",
            "TMPDIR",
            "USER",
        }
    }
    try:
        result = subprocess.run(
            [path, "login", "status"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return DiagnosticCheck(
            "codex",
            "misconfigured",
            "feature",
            f"Could not check Codex login: {type(exc).__name__}",
            "Run `codex login`, then retry `make doctor`.",
        )
    status = f"{result.stdout}\n{result.stderr}".strip()
    if result.returncode != 0 or "logged in" not in status.casefold():
        return DiagnosticCheck(
            "codex",
            "misconfigured",
            "feature",
            "Codex CLI is installed but has no usable saved login.",
            "Run `codex login` and choose your ChatGPT account.",
        )
    sandbox = shutil.which(settings.llm.codex_sandbox_binary)
    if not sandbox:
        return DiagnosticCheck(
            "codex_sandbox",
            "missing",
            "feature",
            f"sandbox-exec not found at {settings.llm.codex_sandbox_binary!r}",
            "Set SYNTHPOST_CODEX_SANDBOX_BINARY to /usr/bin/sandbox-exec.",
        )
    mode = "ChatGPT" if "chatgpt" in status.casefold() else "configured account"
    return DiagnosticCheck(
        "codex",
        "available",
        "feature",
        f"{Path(path).name} authenticated with {mode}; model={settings.llm.codex_model}",
    )


def run_diagnostics(*, config_only: bool = False) -> list[DiagnosticCheck]:
    checks: list[DiagnosticCheck] = []
    try:
        settings = config.validate_startup()
        checks.append(
            DiagnosticCheck(
                "configuration",
                "configured",
                "required",
                "Environment values parsed successfully.",
            )
        )
    except config.ConfigurationError as exc:
        return [
            DiagnosticCheck(
                "configuration",
                "misconfigured",
                "required",
                str(exc),
                "Correct the named value in .env and run `make config-check`.",
            )
        ]

    provider_problem = settings.llm.provider_problem()
    checks.append(
        DiagnosticCheck(
            "llm_provider",
            "misconfigured" if provider_problem else "configured",
            "feature",
            provider_problem
            or f"{settings.llm.provider} is ready for configuration checks.",
            "Set the provider API key in .env; use mock only for tests/smoke demos."
            if provider_problem
            else "",
        )
    )
    db_path = resolve_project_path(settings.storage.database_path)
    checks.append(
        DiagnosticCheck(
            "storage",
            "available" if db_path.parent.is_dir() else "configured",
            "required",
            f"database={db_path}; artifact_root={PROJECT_ROOT / 'episodes'}",
        )
    )
    jobs = settings.jobs
    checks.append(
        DiagnosticCheck(
            "worker_pool",
            "configured",
            "required",
            "parallel capacity: "
            f"editorial={jobs.editorial_workers}, "
            f"media={jobs.media_workers}, render={jobs.render_workers}",
        )
    )
    if config_only:
        return checks

    python_status = "available" if sys.version_info >= (3, 11) else "missing"
    checks.append(
        DiagnosticCheck(
            "python",
            python_status,
            "required",
            sys.version.split()[0],
            "Install Python 3.11 or newer." if python_status == "missing" else "",
        )
    )
    checks.extend(
        [
            _directory("python_venv", PROJECT_ROOT / ".venv", "required"),
            _binary(
                "node", "node", requirement="required", remedy="Install Node.js 20+."
            ),
            _binary(
                "npm", "npm", requirement="required", remedy="Install Node.js 20+."
            ),
            _binary(
                "ffmpeg",
                settings.render.ffmpeg_binary,
                requirement="required",
                remedy="Install FFmpeg (for example, `brew install ffmpeg`).",
            ),
            _binary(
                "ffprobe",
                "ffprobe",
                requirement="required",
                remedy="Install FFmpeg, which includes ffprobe.",
            ),
            _directory(
                "remotion", resolve_project_path(settings.render.remotion_path), "required"
            ),
            _directory(
                "avatar_engine",
                resolve_project_path(settings.avatar.engine_path),
                "feature",
            ),
            _binary(
                "blender",
                "blender",
                requirement="optional",
                remedy="Install Blender only for the legacy Blender renderer.",
            ),
            _binary(
                "yt_dlp",
                settings.visuals.yt_dlp_binary,
                requirement="optional",
                remedy="Install yt-dlp to acquire eligible source videos.",
            ),
            _binary(
                "tesseract",
                settings.visuals.tesseract_binary,
                requirement="optional",
                remedy="Install Tesseract for visual cleanliness OCR.",
            ),
        ]
    )
    if settings.llm.provider == "codex":
        checks.append(_codex(settings))
    checks.append(_dots_tts(settings))
    rhubarb = PROJECT_ROOT / "Rhubarb-Lip-Sync-1.14.0-macOS" / "rhubarb"
    checks.append(
        DiagnosticCheck(
            "rhubarb",
            "available" if rhubarb.is_file() else "optional_missing",
            "optional",
            str(rhubarb) if rhubarb.is_file() else "bundled Rhubarb binary not found",
            "Restore the bundled binary when using Rhubarb lip sync.",
        )
    )
    return checks


def exit_code(checks: list[DiagnosticCheck], *, strict_features: bool = False) -> int:
    blocking = {"required"}
    if strict_features:
        blocking.add("feature")
    return int(any(not check.ok and check.requirement in blocking for check in checks))
