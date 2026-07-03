from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request, urlopen


class LLMProvider(Protocol):
    name: str

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]: ...


@dataclass
class OllamaProvider:
    base_url: str = os.environ.get(
        "SYNTHPOST_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
    )
    model: str = os.environ.get("SYNTHPOST_OLLAMA_MODEL", "llama3.1:8b")
    timeout: float = float(os.environ.get("SYNTHPOST_OLLAMA_TIMEOUT", "90"))
    temperature: float = float(os.environ.get("SYNTHPOST_OLLAMA_TEMPERATURE", "0.2"))
    context_size: int | None = (
        int(os.environ["SYNTHPOST_OLLAMA_CONTEXT_SIZE"])
        if os.environ.get("SYNTHPOST_OLLAMA_CONTEXT_SIZE")
        else None
    )
    name: str = "ollama"

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.temperature if temperature is None else temperature
            },
        }
        if self.context_size:
            payload["options"]["num_ctx"] = self.context_size
        request = Request(
            self.base_url.rstrip("/") + "/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = data.get("response", "")
        return parse_json_object(text)


@dataclass
class MockProvider:
    name: str = "mock"

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]:
        # Deterministic structured response for tests and offline demos.
        if "section-based news script" in prompt.lower():
            return {
                "headline": "Editor-reviewed SynthPost briefing",
                "dek": "A grounded local mock script generated from the research pack.",
                "category": "news",
                "sections": [
                    {
                        "section_type": "cold_open",
                        "text": "Here is the core development and why it matters right now.",
                        "claim_ids": ["claim_001"],
                    },
                    {
                        "section_type": "context",
                        "text": "The source material gives us the context without requiring unsupported assumptions.",
                        "claim_ids": ["claim_001"],
                    },
                    {
                        "section_type": "key_developments",
                        "text": "The key development is best understood through the documented facts in the research pack.",
                        "claim_ids": ["claim_001"],
                    },
                    {
                        "section_type": "why_it_matters",
                        "text": "For viewers, the importance is the practical impact and the uncertainty still left open.",
                        "claim_ids": ["claim_001"],
                    },
                    {
                        "section_type": "conclusion",
                        "text": "We will keep the attribution visible and separate confirmed facts from analysis.",
                        "claim_ids": ["claim_001"],
                    },
                ],
            }
        return {"ok": True}


def configured_provider() -> LLMProvider:
    provider = os.environ.get("SYNTHPOST_LLM_PROVIDER", "ollama").strip().lower()
    if provider == "mock":
        return MockProvider()
    return OllamaProvider()


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end >= start:
        stripped = stripped[start : end + 1]
    data = json.loads(stripped)
    if not isinstance(data, dict):
        raise ValueError("LLM output must be a JSON object")
    return data


def structured_generate(
    provider: LLMProvider,
    prompt: str,
    schema: dict[str, Any],
    validator,
    *,
    max_retries: int = 2,
) -> tuple[Any, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    current_prompt = prompt
    for attempt in range(max_retries + 1):
        started = time.time()
        try:
            raw = provider.generate_json(current_prompt, schema)
            value = validator(raw)
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "ok": True,
                    "raw": raw,
                    "elapsed_seconds": round(time.time() - started, 3),
                }
            )
            return value, attempts
        except Exception as exc:
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "ok": False,
                    "error": str(exc),
                    "elapsed_seconds": round(time.time() - started, 3),
                }
            )
            current_prompt = (
                prompt
                + "\n\nYour previous response failed validation with this error:\n"
                + str(exc)
                + "\nReturn only corrected JSON."
            )
    raise ValueError(
        f"Structured generation failed after {max_retries + 1} attempts: {attempts[-1].get('error')}"
    )
