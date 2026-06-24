from __future__ import annotations

import hashlib
import logging
import os
import time
import urllib.request
from pathlib import Path

from ..storage import PROJECT_ROOT


DEFAULT_CACHE_DIR = PROJECT_ROOT / ".cache" / "synthpost" / "news_collection" / "rss"
DEFAULT_TTL_SECONDS = 30 * 60
LOGGER = logging.getLogger(__name__)


def cache_enabled() -> bool:
    return os.environ.get("SYNTHPOST_RSS_CACHE", "1").strip().lower() not in {"0", "false", "no", "off"}


def cache_ttl_seconds() -> int:
    raw = os.environ.get("SYNTHPOST_RSS_CACHE_TTL_SECONDS", "")
    if not raw:
        return DEFAULT_TTL_SECONDS
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_TTL_SECONDS


def cache_path_for(url: str, *, cache_dir: str | Path | None = None) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    root = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    return root / f"{digest}.xml"


def fetch_url(
    url: str,
    *,
    cache_dir: str | Path | None = None,
    ttl_seconds: int | None = None,
    use_cache: bool | None = None,
    timeout: int = 20,
) -> bytes:
    enabled = cache_enabled() if use_cache is None else use_cache
    ttl = cache_ttl_seconds() if ttl_seconds is None else ttl_seconds
    path = cache_path_for(url, cache_dir=cache_dir)
    if enabled:
        cached = _read_cache(path, ttl_seconds=ttl)
        if cached is not None:
            return cached
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = response.read()
    except OSError:
        if enabled:
            stale = _read_cache(path, ttl_seconds=None)
            if stale is not None:
                LOGGER.warning("Using stale RSS cache for %s after fetch failure: %s", url, path)
                return stale
        raise
    if enabled:
        _write_cache(path, data)
    return data


def clear_cache(*, cache_dir: str | Path | None = None) -> None:
    root = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    if not root.exists():
        return
    for path in root.glob("*.xml"):
        path.unlink()


def _read_cache(path: Path, *, ttl_seconds: int | None) -> bytes | None:
    if not path.exists():
        return None
    if ttl_seconds is not None and ttl_seconds > 0:
        age = time.time() - path.stat().st_mtime
        if age > ttl_seconds:
            return None
    return path.read_bytes()


def _write_cache(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(data)
    os.replace(temp_path, path)
