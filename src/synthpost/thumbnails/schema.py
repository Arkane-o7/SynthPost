from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .models import PROJECT_ROOT, ThumbnailBrief


SCHEMA_PATH = PROJECT_ROOT / "thumbnail_brief.schema.json"


def read_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved
    with resolved.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {resolved}")
    return data


def validate_brief_record(record: dict[str, Any]) -> None:
    schema = read_json(SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(record), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path) or "<root>"
        raise ValueError(f"Thumbnail brief is invalid at {path}: {first.message}")


def load_brief(path: str | Path) -> ThumbnailBrief:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved
    record = read_json(resolved)
    validate_brief_record(record)
    return ThumbnailBrief.from_record(record, fallback_id=resolved.stem)
