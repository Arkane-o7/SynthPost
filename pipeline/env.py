from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILES = (PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local")


def _parse_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def load_env_files(*, override: bool = False) -> None:
    """Load simple KEY=VALUE entries from local env files.

    This intentionally supports only the subset we need for local SynthPost
    configuration. Existing process environment variables win by default.
    """
    for path in _ENV_FILES:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export ") :].strip()
            if not key:
                continue
            if not override and os.environ.get(key) not in (None, ""):
                continue
            os.environ[key] = _parse_value(raw_value)


load_env_files()
