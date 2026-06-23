from __future__ import annotations

import json
import shutil
import struct
import zlib
from pathlib import Path
from typing import Any


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        import yaml  # type: ignore
    except ImportError:
        return _load_simple_yaml(path)

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML object in {path}")
    return data


def _load_simple_yaml(path: Path) -> dict[str, Any]:
    """Tiny fallback parser for this repo's simple default.yaml shape."""
    result: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, result)]

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, _, raw_value = line.strip().partition(":")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if raw_value.strip() == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_scalar(raw_value.strip())
    return result


def parse_scalar(value: str) -> Any:
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.startswith("[") and value.endswith("]"):
        items = [item.strip() for item in value[1:-1].split(",") if item.strip()]
        return [parse_scalar(item) for item in items]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value.strip("'\"")


def resolve_tool(binary: str | None) -> Path | None:
    if not binary:
        return None
    candidate = Path(binary).expanduser()
    if candidate.is_absolute() or candidate.parent != Path("."):
        return candidate if candidate.exists() else None
    found = shutil.which(binary)
    return Path(found) if found else None


def resolve_project_path(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def seconds_to_frames(seconds: float, fps: int) -> int:
    return max(1, int(round(seconds * fps)) + 1)


def write_placeholder_png(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_rows = []
    row = bytes(rgb) * width
    for _ in range(height):
        raw_rows.append(b"\x00" + row)
    raw = b"".join(raw_rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def create_placeholder_frames(render_dir: Path, frame_count: int, resolution: list[int]) -> None:
    width = max(64, min(int(resolution[0]), 640))
    height = max(64, min(int(resolution[1]), 360))
    render_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(1, frame_count + 1):
        shade = int(35 + (frame / max(frame_count, 1)) * 90)
        accent = int(90 + (frame % 30) * 3)
        write_placeholder_png(render_dir / f"frame_{frame:05d}.png", width, height, (shade, accent, 150))
