"""Contextual logging primitives shared by CLIs, workers, and the API."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from pipeline import config
from pipeline.models import now_iso
from pipeline.storage import PROJECT_ROOT

_SENSITIVE_KEY = re.compile(r"(api[_-]?key|authorization|token|secret|password)", re.I)
_INLINE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|authorization|token|secret|password)\b(\s*[:=]\s*)([^\s,;]+)"
)


def safe_text(value: object) -> str:
    """Redact repository/home paths and inline secret assignments."""

    text = str(value)
    text = text.replace(str(PROJECT_ROOT.resolve()), "<project_root>")
    text = text.replace(str(Path.home()), "~")
    return _INLINE_SECRET.sub(r"\1\2[REDACTED]", text)


def safe_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Remove secret-shaped values before they reach a log line."""

    clean: dict[str, Any] = {}
    for key, value in fields.items():
        if value in (None, "", [], {}):
            continue
        clean[key] = (
            "[REDACTED]"
            if _SENSITIVE_KEY.search(key)
            else safe_text(value)
            if isinstance(value, (str, Path))
            else value
        )
    return clean


@dataclass(frozen=True)
class LogContext:
    project_id: str | None = None
    episode_id: str | None = None
    story_id: str | None = None
    job_id: str | None = None
    stage: str | None = None
    provider: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def fields(self) -> dict[str, Any]:
        return safe_fields(
            {
                "project_id": self.project_id,
                "episode_id": self.episode_id,
                "story_id": self.story_id,
                "job_id": self.job_id,
                "stage": self.stage,
                "provider": self.provider,
                **self.extra,
            }
        )


def format_event(
    event: str,
    message: str,
    *,
    level: str = "INFO",
    context: LogContext | None = None,
    fields: dict[str, Any] | None = None,
    log_format: str | None = None,
) -> str:
    payload = {
        "timestamp": now_iso(),
        "level": level.upper(),
        "event": event,
        "message": safe_text(message),
        **(context.fields() if context else {}),
        **safe_fields(fields or {}),
    }
    effective_format = log_format or config.get_settings().server.log_format
    if effective_format == "json":
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)
    labels = " ".join(
        f"{key}={value}"
        for key, value in payload.items()
        if key
        in {"project_id", "episode_id", "story_id", "job_id", "stage", "provider"}
    )
    suffix = f" [{labels}]" if labels else ""
    return f"[{payload['timestamp']}] {payload['level']} {payload['message']}{suffix}"


def write_event(
    stream: TextIO,
    event: str,
    message: str,
    *,
    level: str = "INFO",
    context: LogContext | None = None,
    fields: dict[str, Any] | None = None,
    log_format: str | None = None,
) -> str:
    line = format_event(
        event,
        message,
        level=level,
        context=context,
        fields=fields,
        log_format=log_format,
    )
    stream.write(line + "\n")
    stream.flush()
    return line
