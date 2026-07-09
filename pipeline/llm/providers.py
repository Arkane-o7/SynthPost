from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request, urlopen

from pipeline import env as _env  # noqa: F401 - loads .env/.env.local at import time

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


class LLMProvider(Protocol):
    name: str

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]: ...


@dataclass
class GeminiProvider:
    model: str = os.environ.get("SYNTHPOST_GEMINI_MODEL", "gemini-3.5-flash")
    temperature: float = float(os.environ.get("SYNTHPOST_GEMINI_TEMPERATURE", "0.2"))
    name: str = "gemini"
    last_model: str | None = None

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]:
        if genai is None:
            raise ImportError("google-genai package is required to use GeminiProvider")

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is missing")

        client = genai.Client(api_key=api_key)

        # Enforce JSON output. The generation prompt already includes the schema string.
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=self.temperature if temperature is None else temperature,
            response_schema=schema,
        )

        self.last_model = self.model
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )

        text = response.text or ""
        return parse_json_object(text)


@dataclass
class GroqProvider:
    model: str = os.environ.get("SYNTHPOST_GROQ_MODEL", "openai/gpt-oss-120b")
    temperature: float = float(os.environ.get("SYNTHPOST_GROQ_TEMPERATURE", "0.2"))
    name: str = "groq"
    last_model: str | None = None

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable is missing")

        self.last_model = self.model
        temp = self.temperature if temperature is None else temperature

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": f"You are a helpful assistant. Output ONLY valid JSON matching this schema:\n{json.dumps(schema)}",
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": temp,
            "response_format": {"type": "json_object"},
        }

        req = Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))

        content = result["choices"][0]["message"]["content"]
        return parse_json_object(content)


@dataclass
class FallbackProvider:
    primary: LLMProvider
    fallback: LLMProvider
    name: str = "fallback"

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]:
        try:
            return self.primary.generate_json(prompt, schema, temperature=temperature)
        except Exception as e:
            print(f"[FallbackProvider] Primary {self.primary.name} failed: {e}. Falling back to {self.fallback.name}...")
            return self.fallback.generate_json(prompt, schema, temperature=temperature)


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
                "dek": "A grounded mock script generated from the research pack.",
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
    provider = os.environ.get("SYNTHPOST_LLM_PROVIDER", "groq_with_fallback").strip().lower()
    if provider == "mock":
        return MockProvider()
    elif provider == "gemini":
        return GeminiProvider()
    elif provider == "groq":
        return GroqProvider()
    
    return FallbackProvider(GroqProvider(), GeminiProvider())


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
