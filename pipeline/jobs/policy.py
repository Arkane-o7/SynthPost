from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError

from pipeline import config


EDITORIAL_JOB_TYPES = frozenset(
    {"discovery", "research", "script_generate", "narration_generate"}
)
MEDIA_JOB_TYPES = frozenset({"visual_search", "timeline_generate"})
RENDER_JOB_TYPES = frozenset({"render_avatar", "render_story", "assemble_episode"})


def queue_lane_for_job_type(job_type: str) -> str:
    if job_type in MEDIA_JOB_TYPES:
        return "media"
    if job_type in RENDER_JOB_TYPES:
        return "render"
    return "editorial"


def default_max_attempts(job_type: str) -> int:
    lane = queue_lane_for_job_type(job_type)
    env_name = f"SYNTHPOST_{lane.upper()}_JOB_MAX_ATTEMPTS"
    default = 2 if lane == "render" else 3
    return max(1, int(config.env(env_name, str(default)) or str(default)))


def retry_time(seconds: float) -> str:
    value = datetime.now(timezone.utc) + timedelta(seconds=max(0.0, seconds))
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RetryDecision:
    kind: str
    retryable: bool
    delay_seconds: float
    reason: str


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _retry_after_hint(exc: BaseException) -> float | None:
    hints: list[float] = []
    for item in _exception_chain(exc):
        raw_hint = getattr(item, "retry_after_seconds", None)
        if isinstance(raw_hint, (int, float)):
            hints.append(float(raw_hint))
        attempts = getattr(item, "attempts", None)
        if isinstance(attempts, list):
            for attempt in attempts:
                if not isinstance(attempt, dict):
                    continue
                value = attempt.get("retry_after_seconds")
                if isinstance(value, (int, float)):
                    hints.append(float(value))
    text = str(exc)
    for pattern in (
        r"retry(?:Delay|[_ -]?after)?[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*s",
        r"retry in\s+([0-9]+(?:\.[0-9]+)?)\s*seconds?",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            hints.append(float(match.group(1)))
    return max(hints) if hints else None


def _backoff_seconds(attempts: int, *, hint: float | None = None) -> float:
    base = max(1.0, config.env_float("SYNTHPOST_JOB_RETRY_BASE_SECONDS", 15.0))
    maximum = max(base, config.env_float("SYNTHPOST_JOB_RETRY_MAX_SECONDS", 900.0))
    delay = base * (2 ** max(0, attempts - 1))
    if hint is not None:
        delay = max(delay, hint)
    return min(maximum, delay)


def classify_failure(job_type: str, attempts: int, exc: BaseException) -> RetryDecision:
    """Classify a worker error without retrying deterministic editor/config failures."""

    chain = _exception_chain(exc)
    message = " | ".join(str(item) for item in chain).casefold()
    hint = _retry_after_hint(exc)
    delay = _backoff_seconds(attempts, hint=hint)

    rate_limit_terms = (
        "429",
        "resource_exhausted",
        "rate limit",
        "rate-limit",
        "quota exceeded",
        "too many requests",
    )
    if any(term in message for term in rate_limit_terms):
        return RetryDecision("rate_limited", True, delay, "provider rate limit")

    timeout_types = (TimeoutError, subprocess.TimeoutExpired)
    if any(isinstance(item, timeout_types) for item in chain) or any(
        term in message for term in ("timed out", "timeout", "deadline exceeded")
    ):
        return RetryDecision("timeout", True, delay, "temporary timeout")

    retryable_http = any(
        isinstance(item, HTTPError) and item.code in {408, 425, 429, 500, 502, 503, 504}
        for item in chain
    )
    network_terms = (
        "connection refused",
        "connection reset",
        "connection aborted",
        "remote end closed",
        "temporary failure",
        "temporarily unavailable",
        "name or service not known",
        "network is unreachable",
        "server disconnected",
        "service unavailable",
        "bad gateway",
    )
    if retryable_http or any(isinstance(item, (URLError, ConnectionError)) for item in chain) or any(
        term in message for term in network_terms
    ):
        return RetryDecision("network", True, delay, "temporary network or service failure")

    permanent_terms = (
        "required to use",
        "api key is required",
        "not configured",
        "no handler registered",
        "requires story_id",
        "requires episode_id",
        "no story manifests found",
        "timeline is not approved",
        "incompatible with",
        "validation error",
        "outside the project",
        "unsupported",
    )
    if isinstance(exc, FileNotFoundError) or any(term in message for term in permanent_terms):
        return RetryDecision("configuration", False, 0.0, "configuration or input requires intervention")

    if any(isinstance(item, subprocess.CalledProcessError) for item in chain):
        return RetryDecision(
            "subprocess",
            True,
            delay,
            "renderer or media subprocess exited unexpectedly",
        )

    if isinstance(exc, (ValueError, TypeError, AssertionError)):
        return RetryDecision("validation", False, 0.0, "deterministic validation failure")

    # Unknown operational failures receive a bounded retry. The attempt budget
    # prevents persistent programming errors from looping forever.
    return RetryDecision("unknown", True, delay, "unclassified operational failure")
