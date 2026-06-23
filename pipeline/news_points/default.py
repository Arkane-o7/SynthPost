from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..storage import read_manifest, write_manifest


def short_line(text: str, max_chars: int = 98) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rsplit(" ", 1)[0] + "."


def derive_points(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("raw", {})
    facts = raw.get("facts", []) if isinstance(raw, dict) else []
    usable = [short_line(str(fact)) for fact in facts if str(fact).strip()]
    if not usable:
        script_text = str(manifest.get("script", {}).get("text", ""))
        usable = [short_line(part) for part in re.split(r"(?<=[.!?])\s+", script_text) if part.strip()]
    usable = usable[:4] or ["Story details are being verified."]
    return [{"text": text, "start": round(4.0 + index * 4.0, 2)} for index, text in enumerate(usable)]


def run(story_json_path: str | Path, *, force: bool = False) -> list[dict[str, Any]]:
    manifest = read_manifest(story_json_path)
    existing = manifest.get("points")
    if existing is not None and not force:
        print("[points] Reusing points from manifest.")
        return existing
    points = derive_points(manifest)
    manifest["points"] = points
    write_manifest(story_json_path, manifest)
    print(f"[points] Wrote {len(points)} point(s).")
    return points
