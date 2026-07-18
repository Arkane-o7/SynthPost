"""Typed HTTP adapter for the local Hermes Agent Runs API."""

from __future__ import annotations

import fcntl
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipeline import config
from pipeline.llm.providers import parse_json_object
from pipeline.observability import safe_text
from pipeline.storage import PROJECT_ROOT


class HermesError(RuntimeError):
    """Base error for safe, actionable Hermes integration failures."""


class HermesUnavailableError(HermesError):
    pass


class HermesRunError(HermesError):
    pass


class HermesRunCancelled(HermesRunError):
    pass


class HermesOutputError(ValueError):
    pass


class HermesApprovalRequired(ValueError):
    pass


ProgressCallback = Callable[[str, dict[str, Any]], None]
CancelCheck = Callable[[], None]

NEWSROOM_TOOLSETS = frozenset({"web", "browser", "vision", "video"})


@contextmanager
def _hermes_run_slot(
    max_slots: int,
    *,
    deadline: float,
    cancel_check: CancelCheck | None,
    progress_callback: ProgressCallback | None,
):
    """Limit Hermes work across independent editorial/media worker processes."""

    lock_dir = PROJECT_ROOT / ".synthpost" / "hermes-slots"
    lock_dir.mkdir(parents=True, exist_ok=True)
    announced = False
    while True:
        for slot in range(1, max_slots + 1):
            path = Path(lock_dir) / f"slot-{slot}.lock"
            handle = path.open("a+", encoding="utf-8")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                continue
            try:
                yield slot
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()
            return
        if cancel_check is not None:
            cancel_check()
        if time.monotonic() >= deadline:
            raise HermesRunError("Timed out waiting for an available Hermes run slot")
        if progress_callback is not None and not announced:
            progress_callback("waiting_for_capacity", {"status": "waiting_for_capacity"})
            announced = True
        time.sleep(0.2)


@dataclass
class HermesClient:
    base_url: str = field(
        default_factory=lambda: config.get_settings().hermes.base_url
    )
    api_key: str | None = field(
        default_factory=lambda: config.get_settings().hermes.api_key
    )
    request_timeout_seconds: float = field(
        default_factory=lambda: config.get_settings().hermes.request_timeout_seconds
    )
    run_timeout_seconds: float = field(
        default_factory=lambda: config.get_settings().hermes.run_timeout_seconds
    )
    poll_interval_seconds: float = field(
        default_factory=lambda: config.get_settings().hermes.poll_interval_seconds
    )
    max_concurrent_runs: int = field(
        default_factory=lambda: config.get_settings().hermes.max_concurrent_runs
    )

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.api_key:
            raise HermesUnavailableError(
                "Hermes is not configured; set SYNTHPOST_HERMES_API_KEY"
            )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        body: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code in {401, 403}:
                raise HermesUnavailableError(
                    "Hermes API key is required or invalid"
                ) from exc
            raise HermesRunError(
                safe_text(f"Hermes HTTP {exc.code}: {detail or exc.reason}")
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise HermesUnavailableError(
                safe_text(f"Cannot reach Hermes at {self.base_url}: {exc}")
            ) from exc
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise HermesRunError("Hermes returned a non-JSON API response") from exc
        if not isinstance(value, dict):
            raise HermesRunError("Hermes API response must be a JSON object")
        return value

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def capabilities(self) -> dict[str, Any]:
        return self._request("GET", "/v1/capabilities")

    def toolsets(self) -> dict[str, Any]:
        return self._request("GET", "/v1/toolsets")

    def assert_newsroom_safe(self) -> set[str]:
        """Refuse an API profile that can mutate the machine or external state."""

        response = self.toolsets()
        rows = response.get("data")
        if not isinstance(rows, list):
            raise HermesUnavailableError(
                "Hermes /v1/toolsets did not return a toolset list"
            )
        enabled = {
            str(row.get("name") or "").strip()
            for row in rows
            if isinstance(row, dict) and row.get("enabled")
        }
        unsafe = sorted(enabled - NEWSROOM_TOOLSETS)
        if unsafe:
            raise HermesUnavailableError(
                "Hermes API server exposes tools outside the SynthPost newsroom "
                f"profile: {', '.join(unsafe)}. Restrict the api_server platform "
                "to web, browser, vision, and optional video toolsets."
            )
        if "web" not in enabled:
            raise HermesUnavailableError(
                "Hermes API server must enable the web toolset for newsroom work"
            )
        return enabled

    def submit_run(
        self,
        input_text: str,
        *,
        instructions: str,
        session_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        response = self._request(
            "POST",
            "/v1/runs",
            {
                "input": input_text,
                "instructions": instructions,
                "session_id": session_id or f"synthpost-{uuid.uuid4().hex}",
            },
            idempotency_key=idempotency_key,
        )
        run_id = str(response.get("run_id") or "").strip()
        if not run_id:
            raise HermesRunError("Hermes did not return a run_id")
        return run_id

    def run_status(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/runs/{run_id}")

    def stop_run(self, run_id: str) -> None:
        self._request("POST", f"/v1/runs/{run_id}/stop", {})

    def run_text(
        self,
        input_text: str,
        *,
        instructions: str,
        session_id: str | None = None,
        idempotency_key: str | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> tuple[str, dict[str, Any]]:
        started = time.monotonic()
        deadline = started + self.run_timeout_seconds
        self.assert_newsroom_safe()
        with _hermes_run_slot(
            self.max_concurrent_runs,
            deadline=deadline,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
        ):
            run_id = self.submit_run(
                input_text,
                instructions=instructions,
                session_id=session_id,
                idempotency_key=idempotency_key,
            )
            previous_status = ""
            while True:
                if cancel_check is not None:
                    try:
                        cancel_check()
                    except Exception:
                        try:
                            self.stop_run(run_id)
                        finally:
                            raise
                if time.monotonic() >= deadline:
                    try:
                        self.stop_run(run_id)
                    finally:
                        raise HermesRunError(
                            f"Hermes run {run_id} exceeded {self.run_timeout_seconds:g}s"
                        )
                state = self.run_status(run_id)
                status = str(state.get("status") or "unknown").lower()
                if progress_callback is not None and status != previous_status:
                    progress_callback(status, state)
                previous_status = status
                if status == "completed":
                    output = state.get("output")
                    if isinstance(output, list):
                        output = "\n".join(str(item) for item in output)
                    if not isinstance(output, str) or not output.strip():
                        raise HermesOutputError(
                            f"Hermes run {run_id} completed without textual output"
                        )
                    return output, state
                if status in {"failed", "error"}:
                    message = state.get("error") or state.get("detail") or "run failed"
                    raise HermesRunError(safe_text(f"Hermes run failed: {message}"))
                if status in {"cancelled", "canceled"}:
                    raise HermesRunCancelled(f"Hermes run {run_id} was cancelled")
                if status in {
                    "waiting_for_approval",
                    "requires_approval",
                    "requires_action",
                }:
                    raise HermesApprovalRequired(
                        "Hermes requested interactive approval. Configure the dedicated "
                        "SynthPost Hermes profile with pre-approved research tools."
                    )
                time.sleep(self.poll_interval_seconds)

    def run_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        session_id: str | None = None,
        idempotency_key: str | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        schema_text = json.dumps(schema, ensure_ascii=True, separators=(",", ":"))
        instructions = (
            "You are a bounded SynthPost newsroom agent. Use available research "
            "tools when the task requires them. Return only one JSON object matching "
            "the supplied schema. Do not use markdown fences, commentary, or invented "
            "sources. Every factual claim must be supported by a source encountered "
            "during this run."
        )
        output, state = self.run_text(
            f"{prompt}\n\nOUTPUT JSON SCHEMA:\n{schema_text}",
            instructions=instructions,
            session_id=session_id,
            idempotency_key=idempotency_key,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        try:
            return parse_json_object(output), state
        except (ValueError, json.JSONDecodeError) as exc:
            raise HermesOutputError(
                f"Hermes returned output that is not a valid JSON object: {exc}"
            ) from exc


@dataclass
class HermesProvider:
    """Structured-generation provider backed by a fresh isolated Hermes run."""

    client: HermesClient = field(default_factory=HermesClient)
    name: str = "hermes"
    last_model: str | None = None
    last_run_id: str | None = None

    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        del temperature  # Hermes profile/model policy owns sampling.
        value, state = self.client.run_json(prompt, schema)
        self.last_model = str(state.get("model") or "hermes-agent")
        self.last_run_id = str(state.get("run_id") or "") or None
        return value
