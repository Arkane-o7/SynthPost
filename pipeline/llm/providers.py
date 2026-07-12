from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
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


def groq_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize a schema to Groq strict structured-output requirements."""

    normalized = {key: value for key, value in schema.items()}
    if normalized.get("type") == "object":
        properties = normalized.get("properties", {})
        normalized["properties"] = {
            key: groq_strict_schema(value) for key, value in properties.items()
        }
        normalized["required"] = list(properties)
        normalized["additionalProperties"] = False
    if isinstance(normalized.get("items"), dict):
        normalized["items"] = groq_strict_schema(normalized["items"])
    for keyword in ("anyOf", "oneOf", "allOf"):
        if isinstance(normalized.get(keyword), list):
            normalized[keyword] = [
                groq_strict_schema(value) for value in normalized[keyword]
            ]
    return normalized


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
    timeout_seconds: float = float(
        os.environ.get("SYNTHPOST_LLM_REQUEST_TIMEOUT_SECONDS", "45")
    )

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
            "Accept": "application/json",
            "User-Agent": "SynthPostStudio/2.0 hosted-llm-client",
        }

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Output only valid JSON matching the provided response schema.",
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": temp,
            "reasoning_effort": "low",
            "include_reasoning": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "synthpost_response",
                    "strict": True,
                    "schema": groq_strict_schema(schema),
                },
            },
        }

        req = Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace").strip()
            raise ValueError(f"Groq HTTP {exc.code}: {body or exc.reason}") from exc

        content = result["choices"][0]["message"]["content"]
        return parse_json_object(content)


@dataclass
class HostedFallbackProvider:
    primary: LLMProvider
    fallback: LLMProvider
    name: str = "groq_then_gemini"

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]:
        try:
            return self.primary.generate_json(prompt, schema, temperature=temperature)
        except Exception as exc:
            print(
                f"[HostedFallbackProvider] Primary {self.primary.name} failed: "
                f"{exc}. Falling back to hosted provider {self.fallback.name}."
            )
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
            section_type = str(payload.get("section_type") or "context")
            return {
                "text": " ".join(expanded_words),
                "claim_ids": claims,
                "lower_third": f"{topic}: {section_type.replace('_', ' ').title()}",
                "chyron": section_type.replace("_", " ").title(),
                "headline_cues": [
                    f"{topic}: {section_type.replace('_', ' ').title()}"
                ],
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
                            f"{topic_words} {section['section_type']} official raw footage"
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
                        "lower_third": "The Core Development Right Now",
                        "chyron": "Breaking Down the Core Development",
                        "headline_cues": ["The Core Development Right Now"],
                    },
                    {
                        "section_type": "context",
                        "text": "The source material gives us the context without requiring unsupported assumptions.",
                        "claim_ids": ["claim_001"],
                        "lower_third": "The Documented Context",
                        "chyron": "What the Source Material Shows",
                        "headline_cues": ["The Documented Context"],
                    },
                    {
                        "section_type": "key_developments",
                        "text": "The key development is best understood through the documented facts in the research pack.",
                        "claim_ids": ["claim_001"],
                        "lower_third": "Key Developments in the Record",
                        "chyron": "The Documented Facts",
                        "headline_cues": ["Key Developments in the Record"],
                    },
                    {
                        "section_type": "why_it_matters",
                        "text": "For viewers, the importance is the practical impact and the uncertainty still left open.",
                        "claim_ids": ["claim_001"],
                        "lower_third": "The Practical Impact for Viewers",
                        "chyron": "Why This Matters",
                        "headline_cues": ["The Practical Impact for Viewers"],
                    },
                    {
                        "section_type": "conclusion",
                        "text": "We will keep the attribution visible and separate confirmed facts from analysis.",
                        "claim_ids": ["claim_001"],
                        "lower_third": "Confirmed Facts, Clearly Attributed",
                        "chyron": "What Is Confirmed",
                        "headline_cues": ["Confirmed Facts, Clearly Attributed"],
                    },
                ],
            }
        return {"ok": True}


def configured_provider(provider_name: str | None = None) -> LLMProvider:
    provider = (
        provider_name or os.environ.get("SYNTHPOST_LLM_PROVIDER", "groq")
    ).strip().lower()
    if provider == "mock":
        return MockProvider()
    if provider == "gemini":
        return GeminiProvider()
    if provider == "groq":
        return GroqProvider()
    if provider in {"hosted_fallback", "groq_then_gemini"}:
        return HostedFallbackProvider(GroqProvider(), GeminiProvider())
    raise ValueError(
        f"Unsupported SYNTHPOST_LLM_PROVIDER: {provider}. "
        "Use groq, gemini, or the explicit hosted_fallback option."
    )


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
