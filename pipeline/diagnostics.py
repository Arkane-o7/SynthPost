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


def _kokoro(settings) -> DiagnosticCheck:
    configured = settings.avatar.python_path
    engine = resolve_project_path(settings.avatar.engine_path)
    candidate = engine / ".venv" / "bin" / "python"
    interpreter = Path(configured) if configured else candidate
    if not interpreter.is_absolute():
        interpreter = resolve_project_path(interpreter)
    if not interpreter.exists():
        return DiagnosticCheck(
            "kokoro",
            "missing",
            "feature",
            f"configured narration Python not found: {interpreter}",
            "Install Avatar Engine dependencies or set SYNTHPOST_AVATAR_PYTHON.",
        )
    result = subprocess.run(
        [str(interpreter), "-c", "import kokoro; print(kokoro.__version__)"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return DiagnosticCheck(
            "kokoro",
            "missing",
            "feature",
            f"Kokoro import failed in {interpreter}",
            "Install Kokoro in the Avatar Engine environment.",
        )
    version = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "installed"
    return DiagnosticCheck(
        "kokoro",
        "available",
        "feature",
        f"{version} via {interpreter}",
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
    checks.append(_kokoro(settings))
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
