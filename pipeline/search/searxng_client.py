from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pipeline import config


class SearXNGError(RuntimeError):
    """Raised when a configured SearXNG instance cannot serve a search."""


@dataclass(frozen=True)
class SearXNGResult:
    title: str
    url: str
    snippet: str = ""
    engine: str = "searxng"
    category: str = "general"
    source_domain: str | None = None
    published_date: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    iframe_url: str | None = None
    duration: str | None = None
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


def configured() -> bool:
    return bool(config.env("SYNTHPOST_SEARXNG_URL"))


def _endpoint() -> str:
    base = config.env("SYNTHPOST_SEARXNG_URL")
    if not base:
        raise SearXNGError(
            "SearXNG is not configured; set SYNTHPOST_SEARXNG_URL to the instance URL"
        )
    base = base.rstrip("/")
    return base if base.endswith("/search") else f"{base}/search"


def _published_date(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


def _first_string(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_result(item: Any, default_category: str) -> SearXNGResult | None:
    if not isinstance(item, dict):
        return None
    url = _first_string(item, "url")
    title = _first_string(item, "title") or url
    if not url or not title:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    engine_value = item.get("engine") or item.get("engines") or "searxng"
    if isinstance(engine_value, list):
        engine = ",".join(str(value) for value in engine_value if value)
    else:
        engine = str(engine_value)
    try:
        score = float(item.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    return SearXNGResult(
        title=title,
        url=url,
        snippet=_first_string(item, "content", "snippet", "description") or "",
        engine=engine,
        category=str(item.get("category") or default_category),
        source_domain=parsed.hostname,
        published_date=_published_date(
            item.get("publishedDate")
            or item.get("published_date")
            or item.get("published_at")
        ),
        image_url=_first_string(item, "img_src", "image_src", "image_url"),
        thumbnail_url=_first_string(
            item, "thumbnail_src", "thumbnail", "thumbnail_url"
        ),
        iframe_url=_first_string(item, "iframe_src", "iframe_url"),
        duration=_first_string(item, "length", "duration"),
        score=score,
        metadata={
            key: value
            for key, value in item.items()
            if key
            not in {
                "url",
                "title",
                "content",
                "snippet",
                "description",
                "engine",
                "engines",
                "category",
                "publishedDate",
                "published_date",
                "published_at",
                "img_src",
                "image_src",
                "image_url",
                "thumbnail_src",
                "thumbnail",
                "thumbnail_url",
                "iframe_src",
                "iframe_url",
                "length",
                "duration",
                "score",
            }
        },
    )


def search(
    query: str,
    *,
    categories: list[str] | tuple[str, ...] | None = None,
    engines: list[str] | tuple[str, ...] | None = None,
    language: str | None = None,
    time_range: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> list[SearXNGResult]:
    """Query SearXNG's JSON API and normalize its heterogeneous result objects."""

    query = query.strip()
    if not query or limit <= 0:
        return []
    from urllib.parse import urlencode

    category_list = list(categories or ["general"])
    parameters: dict[str, str | int] = {
        "q": query,
        "format": "json",
        "categories": ",".join(category_list),
        "pageno": max(1, page),
        "safesearch": int(config.env("SYNTHPOST_SEARXNG_SAFESEARCH", "1") or "1"),
    }
    effective_language = language or config.env("SYNTHPOST_SEARXNG_LANGUAGE", "en")
    if effective_language:
        parameters["language"] = effective_language
    if engines:
        parameters["engines"] = ",".join(engines)
    if time_range in {"day", "month", "year"}:
        parameters["time_range"] = time_range
    url = f"{_endpoint()}?{urlencode(parameters)}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "SynthPostStudio/2.0 local editorial tool",
    }
    api_key = config.env("SYNTHPOST_SEARXNG_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = config.env_float("SYNTHPOST_SEARXNG_TIMEOUT", 20.0)
    attempts = max(1, int(config.env("SYNTHPOST_SEARXNG_RETRIES", "2") or "2"))
    payload: dict[str, Any] | None = None
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                raw = response.read(5_000_000)
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise SearXNGError("SearXNG returned a non-object JSON response")
            payload = parsed
            break
        except HTTPError as exc:
            if exc.code == 403:
                raise SearXNGError(
                    "SearXNG rejected JSON output (HTTP 403); add json to "
                    "search.formats in settings.yml"
                ) from exc
            last_error = exc
        except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(0.25 * (attempt + 1))
    if payload is None:
        raise SearXNGError(f"SearXNG search failed: {last_error}")

    results: list[SearXNGResult] = []
    seen: set[str] = set()
    for raw_result in payload.get("results", []):
        result = _parse_result(raw_result, category_list[0])
        if not result or result.url in seen:
            continue
        seen.add(result.url)
        results.append(result)
        if len(results) >= limit:
            break
    return results
