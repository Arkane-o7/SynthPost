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
class OllamaProvider:
    base_url: str = os.environ.get(
        "SYNTHPOST_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
    )
    model: str = os.environ.get("SYNTHPOST_OLLAMA_MODEL", "gemma4:26b")
    timeout: float = float(os.environ.get("SYNTHPOST_OLLAMA_TIMEOUT", "300"))
    temperature: float = float(os.environ.get("SYNTHPOST_OLLAMA_TEMPERATURE", "0.2"))
    context_size: int | None = (
        int(os.environ["SYNTHPOST_OLLAMA_CONTEXT_SIZE"])
        if os.environ.get("SYNTHPOST_OLLAMA_CONTEXT_SIZE")
        else None
    )
    name: str = "ollama"
    last_model: str | None = None

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": self.temperature if temperature is None else temperature
        }
        if self.context_size:
            options["num_ctx"] = self.context_size
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": schema,
            "options": options,
        }
        self.last_model = self.model
        request = Request(
            self.base_url.rstrip("/") + "/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        # Reasoning-capable Ollama models such as Qwen 3.5 may place a
        # schema-constrained result in `thinking` and leave `response` empty.
        text = data.get("response") or data.get("thinking") or ""
        return parse_json_object(str(text))


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
        if "editorial-cleanliness classifier" in prompt.lower():
            marker = "EVIDENCE JSON:\n"
            evidence = json.loads(prompt.split(marker, 1)[1])
            blockers = evidence.get("deterministic_blockers", [])
            return {
                "decision": "reject" if blockers else "pass",
                "clean_broll_score": 0.0 if blockers else 0.9,
                "contains_presenter_package": False,
                "reasons": blockers or ["no deterministic broadcast packaging detected"],
            }
        if "long-form section expansion" in prompt.lower():
            marker = "INPUT JSON:\n"
            payload = json.loads(prompt.split(marker, 1)[1])
            target = int(payload.get("target_words") or 100)
            base = str(payload.get("base_outline_text") or "Grounded briefing.")
            words = base.split() or ["Grounded", "briefing"]
            expanded_words = [words[index % len(words)] for index in range(target)]
            claims = payload.get("base_claim_ids") or [
                claim.get("claim_id")
                for claim in payload.get("research", {}).get("claims", [])
                if claim.get("claim_id")
            ][:1]
            topic = str(payload.get("headline") or "SynthPost briefing")
            return {
                "text": " ".join(expanded_words),
                "claim_ids": claims,
                "suggested_visual_types": ["image", "video"],
                "suggested_search_queries": [
                    f"{topic} official editorial photo",
                    f"{topic} official raw footage",
                ],
                "suggested_template_ids": ["split_anchor_visual"],
            }
        if "visual search keyword planner" in prompt.lower():
            marker = "INPUT JSON:\n"
            payload = json.loads(prompt.split(marker, 1)[1])
            topic_words = " ".join(str(payload.get("topic") or "news").split()[:6])
            return {
                "queries": [
                    {
                        "section_id": section["section_id"],
                        "image_query": (
                            f"{topic_words} {section['section_type']} editorial photo"
                        ),
                        "video_query": (
                            f"{topic_words} {section['section_type']} news footage"
                        ),
                        "video_priority": section["section_type"]
                        in {"cold_open", "key_developments", "conclusion"},
                        "rationale": "deterministic offline visual-search plan",
                    }
                    for section in payload.get("sections", [])
                ]
            }
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
    if provider == "ollama":
        return OllamaProvider()
    if provider == "gemini":
        return GeminiProvider()
    if provider == "groq":
        return GroqProvider()
    if provider in {"groq_with_fallback", "fallback"}:
        return FallbackProvider(GroqProvider(), GeminiProvider())
    raise ValueError(f"Unsupported SYNTHPOST_LLM_PROVIDER: {provider}")


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
