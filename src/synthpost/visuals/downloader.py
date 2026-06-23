from __future__ import annotations

import mimetypes
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .models import VisualAsset

USER_AGENT = "SynthPostVisuals/0.1 (+local-first news pipeline)"
DEFAULT_MAX_BYTES = 100 * 1024 * 1024


def project_relative(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def safe_filename(value: str, fallback: str = "visual") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return cleaned[:90] or fallback


def extension_from_url(url: str, content_type: str | None = None) -> str:
    parsed = urllib.parse.urlparse(url)
    ext = Path(parsed.path).suffix.lower()
    if ext:
        return ext
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return guessed
    return ".jpg"


def download_asset(
    asset: VisualAsset,
    *,
    destination_dir: Path,
    project_root: Path,
    timeout_seconds: int = 25,
    max_bytes: int | None = None,
) -> VisualAsset:
    if asset.path or not asset.remote_url:
        return asset

    byte_limit = max_bytes or int(os.environ.get("SYNTHPOST_VISUAL_DOWNLOAD_MAX_BYTES", DEFAULT_MAX_BYTES))
    destination_dir.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(asset.remote_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get("Content-Type")
            ext = extension_from_url(asset.remote_url, content_type)
            filename = safe_filename(f"{asset.provider}_{asset.asset_id}") + ext
            destination = destination_dir / filename
            total = 0
            with destination.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > byte_limit:
                        raise ValueError(f"Visual download exceeded {byte_limit} bytes: {asset.remote_url}")
                    handle.write(chunk)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        asset.safe_to_use = False
        asset.fallback_reason = f"download_failed: {exc}"
        return asset

    relative = project_relative(destination, project_root)
    asset.path = relative
    asset.downloaded_path = relative
    return asset

