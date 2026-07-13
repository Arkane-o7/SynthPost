from __future__ import annotations

import hashlib
import html
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import feedparser

from pipeline.models import (
    SourceDefinition,
    SourceType,
    StoryCandidate,
    StorySelectionStatus,
    StoryScores,
    now_iso,
)
from pipeline.editorial.charter import CHARTER_VERSION, assess_editorial_fit
from pipeline.storage import PROJECT_ROOT

CACHE_DIR = PROJECT_ROOT / ".synthpost" / "cache" / "feeds"
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return url.strip()
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), "")
    )


def normalize_title(title: str) -> str:
    value = html.unescape(title or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^\w\s-]", "", value)
    return value


def duplicate_group(title: str, url: str | None) -> str:
    basis = canonicalize_url(url) or normalize_title(title)
    return "dup_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def detect_language(text: str) -> str:
    if not text:
        return "unknown"
    ascii_ratio = sum(1 for char in text if ord(char) < 128) / max(1, len(text))
    return "en" if ascii_ratio > 0.88 else "unknown"


def parse_date(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return (
                    parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                )
            except Exception:
                return None
    return None


def freshness_score(published_at: str | None) -> float:
    if not published_at:
        return 0.45
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        age_hours = max(
            0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600
        )
    except Exception:
        return 0.45
    if age_hours <= 6:
        return 1.0
    if age_hours <= 24:
        return 0.85
    if age_hours <= 72:
        return 0.62
    if age_hours <= 168:
        return 0.35
    return 0.15


def visual_potential(title: str, summary: str) -> float:
    text = f"{title} {summary}".lower()
    keywords = [
        "video",
        "photo",
        "map",
        "satellite",
        "chart",
        "data",
        "fire",
        "protest",
        "launch",
        "speech",
        "court",
        "storm",
        "ai",
        "chip",
        "factory",
        "war",
        "climate",
        "energy",
        "market",
    ]
    hits = sum(1 for key in keywords if key in text)
    return min(1.0, 0.35 + hits * 0.09)


def explainability(title: str, summary: str) -> float:
    text = f"{title} {summary}".lower()
    why_words = [
        "why",
        "how",
        "could",
        "means",
        "impact",
        "explained",
        "after",
        "because",
        "data",
        "policy",
        "deal",
        "ruling",
    ]
    return min(1.0, 0.42 + sum(1 for key in why_words if key in text) * 0.07)


def score_candidate(
    source: SourceDefinition,
    title: str,
    summary: str,
    published_at: str | None,
    duplicate_seen: bool = False,
) -> tuple[StoryScores, float, list[str]]:
    text = f"{title} {summary}".lower()
    importance_terms = [
        "major",
        "first",
        "historic",
        "billion",
        "trillion",
        "climate",
        "energy",
        "ai",
        "chip",
        "semiconductor",
        "cybersecurity",
        "data center",
        "export controls",
        "sanctions",
        "supply chain",
        "regulation",
        "global",
        "market",
        "economy",
        "security",
    ]
    importance = min(
        1.0, 0.35 + sum(1 for term in importance_terms if term in text) * 0.075
    )
    freshness = freshness_score(published_at)
    public_interest = min(1.0, 0.35 + len(title.split()) / 22)
    visual = visual_potential(title, summary)
    explain = explainability(title, summary)
    reliability = max(0.0, min(1.0, source.reliability_score))
    format_suitability = min(1.0, (visual + explain + public_interest) / 3)
    originality = 0.25 if duplicate_seen else 0.9
    scores = StoryScores(
        importance=round(importance, 3),
        freshness=round(freshness, 3),
        public_interest=round(public_interest, 3),
        visual_potential=round(visual, 3),
        explainability=round(explain, 3),
        source_reliability=round(reliability, 3),
        format_suitability=round(format_suitability, 3),
        originality=round(originality, 3),
    )
    weights = {
        "importance": 0.2,
        "freshness": 0.16,
        "public_interest": 0.14,
        "visual_potential": 0.15,
        "explainability": 0.14,
        "source_reliability": 0.11,
        "format_suitability": 0.07,
        "originality": 0.03,
    }
    signal_score = sum(
        getattr(scores, key) * weight for key, weight in weights.items()
    )
    editorial_fit = assess_editorial_fit(source, title, summary)
    final = signal_score * 0.32 + editorial_fit.score * 0.68
    if not editorial_fit.eligible:
        final = min(final, 0.39 if not editorial_fit.rejection_signals else 0.18)
    reasons = [
        f"importance={scores.importance:.2f}",
        f"freshness={scores.freshness:.2f}",
        f"visual_potential={scores.visual_potential:.2f}",
        f"explainability={scores.explainability:.2f}",
        f"source_reliability={scores.source_reliability:.2f}",
        *editorial_fit.reasons,
    ]
    if duplicate_seen:
        reasons.append("near duplicate of an earlier candidate")
    return scores, round(final, 3), reasons


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def fetch_feed(url: str, *, timeout: float = 12.0, max_age_seconds: int = 900) -> bytes:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = cache_key(url)
    cache_path = CACHE_DIR / f"{key}.xml"
    meta_path = CACHE_DIR / f"{key}.etag"
    if (
        cache_path.exists()
        and time.time() - cache_path.stat().st_mtime < max_age_seconds
    ):
        return cache_path.read_bytes()
    headers = {"User-Agent": "SynthPostStudio/2.0 local editorial tool"}
    if meta_path.exists():
        for line in meta_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("ETag: "):
                headers["If-None-Match"] = line.removeprefix("ETag: ")
            if line.startswith("Last-Modified: "):
                headers["If-Modified-Since"] = line.removeprefix("Last-Modified: ")
    try:
        curl = shutil.which("curl")
        if curl:
            command = [
                curl,
                "--location",
                "--silent",
                "--show-error",
                "--fail",
                "--compressed",
                "--connect-timeout",
                str(max(1, min(5, int(timeout)))),
                "--max-time",
                str(max(1, int(timeout))),
                "--user-agent",
                headers["User-Agent"],
            ]
            for name, value in headers.items():
                if name != "User-Agent":
                    command.extend(["--header", f"{name}: {value}"])
            command.append(url)
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=timeout + 3,
            )
            body = result.stdout
        else:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
                etag = response.headers.get("ETag") or ""
                last_modified = response.headers.get("Last-Modified") or ""
                meta_path.write_text(
                    f"ETag: {etag}\nLast-Modified: {last_modified}\n",
                    encoding="utf-8",
                )
        if not body:
            raise ValueError(f"Feed returned an empty response: {url}")
        cache_path.write_bytes(body)
        return body
    except Exception:
        if cache_path.exists():
            return cache_path.read_bytes()
        raise


def candidate_from_feed_entry(
    source: SourceDefinition, entry: Any, *, seen_groups: set[str]
) -> StoryCandidate | None:
    title = html.unescape(str(getattr(entry, "title", "") or "")).strip()
    if not title:
        return None
    link = canonicalize_url(str(getattr(entry, "link", "") or ""))
    summary = html.unescape(
        re.sub(r"<[^>]+>", " ", str(getattr(entry, "summary", "") or ""))
    ).strip()
    summary = re.sub(r"\s+", " ", summary)[:900]
    published_at = parse_date(
        getattr(entry, "published", None) or getattr(entry, "updated", None)
    )
    group = duplicate_group(title, link)
    duplicate_seen = group in seen_groups
    seen_groups.add(group)
    scores, final_score, reasons = score_candidate(
        source, title, summary, published_at, duplicate_seen
    )
    editorial_fit = assess_editorial_fit(source, title, summary)
    thumbnail_url = None
    media_thumbnail = getattr(entry, "media_thumbnail", None)
    if media_thumbnail and isinstance(media_thumbnail, list) and media_thumbnail:
        thumbnail_url = media_thumbnail[0].get("url")
    return StoryCandidate(
        candidate_id="cand_"
        + hashlib.sha1(
            f"{source.source_id}:{link or title}".encode("utf-8")
        ).hexdigest()[:12],
        title=title,
        canonical_url=link,
        source_id=source.source_id,
        source_name=source.name,
        published_at=published_at,
        author=str(getattr(entry, "author", "") or "") or None,
        category=source.category,
        summary=summary,
        thumbnail_url=thumbnail_url,
        language=detect_language(title + " " + summary),
        scores=scores,
        editorial_fit=editorial_fit,
        final_score=final_score,
        score_reasons=reasons,
        duplicate_group_id=group,
    )


def discover_from_source(
    source: SourceDefinition, *, seen_groups: set[str] | None = None
) -> list[StoryCandidate]:
    if (
        source.source_type not in {SourceType.rss, SourceType.atom}
        or not source.feed_url
    ):
        return []
    groups = seen_groups if seen_groups is not None else set()
    body = fetch_feed(source.feed_url)
    parsed = feedparser.parse(body)
    candidates: list[StoryCandidate] = []
    for entry in parsed.entries[:40]:
        candidate = candidate_from_feed_entry(source, entry, seen_groups=groups)
        if candidate:
            candidates.append(candidate)
    return candidates


def discover(
    repository,
    *,
    episode_id: str | None = None,
    category: str | None = None,
    limit_per_source: int = 20,
) -> list[StoryCandidate]:
    seen_groups: set[str] = set()
    candidates: list[StoryCandidate] = []
    sources = repository.list_sources(enabled=True, category=category)
    if category and not sources:
        sources = repository.list_sources(enabled=True)
    for source in sources:
        try:
            found = discover_from_source(source, seen_groups=seen_groups)[
                :limit_per_source
            ]
        except Exception as exc:
            found = []
        for candidate in found:
            candidate.episode_id = episode_id
            repository.upsert_candidate(candidate)
            candidates.append(candidate)
        source.last_checked_at = now_iso()
        repository.upsert_source(source)
    return sorted(candidates, key=lambda item: item.final_score, reverse=True)


def rescore_existing_candidates(repository) -> int:
    """Apply the current charter to legacy inbox rows after a code upgrade."""

    count = 0
    for candidate in repository.list_candidates(limit=5000):
        if (
            candidate.editorial_fit.charter_version == CHARTER_VERSION
            and candidate.editorial_fit.reasons
        ):
            continue
        try:
            source = repository.get_source(candidate.source_id) if candidate.source_id else None
        except Exception:
            source = None
        if source is None:
            source = SourceDefinition(
                source_id=candidate.source_id or "src_legacy",
                name=candidate.source_name,
                source_type=SourceType.manual_story,
                category=candidate.category,
                reliability_score=candidate.scores.source_reliability or 0.6,
                custom=True,
            )
        scores, final, reasons = score_candidate(
            source,
            candidate.title,
            candidate.summary,
            candidate.published_at,
            candidate.selection_status == StorySelectionStatus.duplicate,
        )
        candidate.scores = scores
        candidate.editorial_fit = assess_editorial_fit(
            source, candidate.title, candidate.summary
        )
        candidate.final_score = final
        candidate.score_reasons = reasons
        repository.upsert_candidate(candidate)
        count += 1
    return count


def add_custom_topic(
    repository,
    *,
    title: str,
    summary: str = "",
    category: str = "custom",
    episode_id: str | None = None,
) -> StoryCandidate:
    source = SourceDefinition(
        source_id="src_manual_topic",
        name="Manual Topic",
        source_type=SourceType.manual_story,
        category=category,
        enabled=True,
        priority=100,
        reliability_score=0.5,
        custom=True,
    )
    scores, final, reasons = score_candidate(source, title, summary, None)
    editorial_fit = assess_editorial_fit(source, title, summary)
    candidate = StoryCandidate(
        candidate_id="cand_"
        + hashlib.sha1(
            f"topic:{episode_id or 'global'}:{title}:{summary}".encode("utf-8")
        ).hexdigest()[:12],
        title=title,
        canonical_url=None,
        source_id=source.source_id,
        source_name=source.name,
        category=category,
        summary=summary,
        language=detect_language(title + " " + summary),
        scores=scores,
        editorial_fit=editorial_fit,
        final_score=final,
        score_reasons=[*reasons, "manual topic entered by editor"],
        duplicate_group_id=duplicate_group(title, None),
        episode_id=episode_id,
        manual_body=summary,
    )
    repository.upsert_candidate(candidate)
    return candidate


def add_custom_url(
    repository,
    *,
    url: str,
    title: str | None = None,
    summary: str = "",
    category: str = "custom",
    episode_id: str | None = None,
) -> StoryCandidate:
    canonical = canonicalize_url(url)
    display_title = title or canonical or url
    source = SourceDefinition(
        source_id="src_custom_url",
        name="Custom URL",
        source_type=SourceType.custom_url,
        category=category,
        enabled=True,
        priority=100,
        reliability_score=0.55,
        custom=True,
    )
    scores, final, reasons = score_candidate(source, display_title, summary, None)
    editorial_fit = assess_editorial_fit(source, display_title, summary)
    candidate = StoryCandidate(
        candidate_id="cand_"
        + hashlib.sha1(
            f"url:{episode_id or 'global'}:{canonical}".encode("utf-8")
        ).hexdigest()[:12],
        title=display_title,
        canonical_url=canonical,
        source_id=source.source_id,
        source_name=source.name,
        category=category,
        summary=summary,
        language=detect_language(display_title + " " + summary),
        scores=scores,
        editorial_fit=editorial_fit,
        final_score=final,
        score_reasons=[*reasons, "custom URL entered by editor"],
        duplicate_group_id=duplicate_group(display_title, canonical),
        episode_id=episode_id,
    )
    repository.upsert_candidate(candidate)
    return candidate


def add_manual_story(
    repository,
    *,
    title: str,
    body: str,
    category: str = "manual",
    episode_id: str | None = None,
) -> StoryCandidate:
    summary = re.sub(r"\s+", " ", body).strip()[:900]
    source = SourceDefinition(
        source_id="src_manual_story",
        name="Manual Story",
        source_type=SourceType.manual_story,
        category=category,
        enabled=True,
        priority=100,
        reliability_score=0.6,
        custom=True,
    )
    scores, final, reasons = score_candidate(source, title, summary, None)
    editorial_fit = assess_editorial_fit(source, title, summary)
    candidate = StoryCandidate(
        candidate_id="cand_"
        + hashlib.sha1(
            f"manual:{episode_id or 'global'}:{title}:{body}".encode("utf-8")
        ).hexdigest()[:12],
        title=title,
        source_id=source.source_id,
        source_name=source.name,
        category=category,
        summary=summary,
        language=detect_language(title + " " + body),
        scores=scores,
        editorial_fit=editorial_fit,
        final_score=final,
        score_reasons=[*reasons, "manual story pasted by editor"],
        duplicate_group_id=duplicate_group(title, None),
        episode_id=episode_id,
        manual_body=body,
    )
    repository.upsert_candidate(candidate)
    return candidate
