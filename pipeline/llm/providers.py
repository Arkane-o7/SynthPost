from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pipeline import config as app_config
from pipeline.observability import safe_text

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


class StructuredGenerationError(ValueError):
    def __init__(self, message: str, attempts: list[dict[str, Any]]):
        super().__init__(message)
        self.attempts = attempts


class ProviderRateLimitError(ValueError):
    def __init__(self, message: str, *, retry_after_seconds: float = 60.0):
        super().__init__(message)
        self.retry_after_seconds = max(0.0, retry_after_seconds)


@dataclass(frozen=True)
class ProviderAvailability:
    name: str
    available: bool
    reason: str
    supports_structured_json: bool = True


def provider_availability(provider_name: str | None = None) -> ProviderAvailability:
    """Report configuration capability without making a network request."""

    name = (provider_name or app_config.get_settings().llm.provider).strip().lower()
    settings = app_config.get_settings().llm
    if name == "mock":
        return ProviderAvailability(name, True, "deterministic offline provider")
    if name == "hermes":
        settings = app_config.get_settings().hermes
        problem = settings.configuration_problem()
        return ProviderAvailability(
            name,
            not problem,
            problem or f"configured at {settings.base_url}",
        )
    if name == "gemini":
        if genai is None:
            return ProviderAvailability(name, False, "google-genai is not installed")
        return ProviderAvailability(
            name,
            bool(settings.gemini_api_key),
            "configured" if settings.gemini_api_key else "GEMINI_API_KEY is missing",
        )
    if name == "groq":
        return ProviderAvailability(
            name,
            bool(settings.groq_api_key),
            "configured" if settings.groq_api_key else "GROQ_API_KEY is missing",
        )
    if name in {"hosted_fallback", "groq_then_gemini"}:
        problem = settings.provider_problem()
        return ProviderAvailability(
            "hosted_fallback", not problem, problem or "both hosted providers configured"
        )
    return ProviderAvailability(name, False, "unsupported provider")


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
    model: str = field(
        default_factory=lambda: app_config.get_settings().llm.gemini_model
    )
    temperature: float = field(
        default_factory=lambda: app_config.get_settings().llm.gemini_temperature
    )
    name: str = "gemini"
    last_model: str | None = None
    timeout_seconds: float = field(
        default_factory=lambda: app_config.get_settings().llm.request_timeout_seconds
    )

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]:
        if genai is None:
            raise ImportError("google-genai package is required to use GeminiProvider")

        api_key = app_config.get_settings().llm.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is missing")

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=max(1, int(self.timeout_seconds * 1000)),
                retry_options=types.HttpRetryOptions(
                    attempts=2,
                    initial_delay=1.0,
                    max_delay=3.0,
                ),
            ),
        )

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
    model: str = field(default_factory=lambda: app_config.get_settings().llm.groq_model)
    temperature: float = field(
        default_factory=lambda: app_config.get_settings().llm.groq_temperature
    )
    name: str = "groq"
    last_model: str | None = None
    timeout_seconds: float = field(
        default_factory=lambda: app_config.get_settings().llm.request_timeout_seconds
    )
    max_completion_tokens: int = field(
        default_factory=lambda: app_config.get_settings().llm.groq_max_completion_tokens
    )

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]:
        api_key = app_config.get_settings().llm.groq_api_key
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
            "max_completion_tokens": self.max_completion_tokens,
            # Script generation needs the token budget for the long structured
            # answer, rather than an invisible reasoning trace.
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
            # urllib otherwise hides the provider's useful JSON error body behind
            # a generic message such as "HTTP Error 413: Payload Too Large".
            body = exc.read().decode("utf-8", errors="replace").strip()
            if exc.code == 429:
                match = re.search(r"try again in\s+([\d.]+)s", body, re.IGNORECASE)
                retry_after = float(match.group(1)) if match else 60.0
                raise ProviderRateLimitError(
                    f"Groq HTTP {exc.code}: {body or exc.reason}",
                    retry_after_seconds=retry_after,
                ) from exc
            raise ValueError(f"Groq HTTP {exc.code}: {body or exc.reason}") from exc

        content = result["choices"][0]["message"]["content"]
        return parse_json_object(content)


@dataclass
class HostedFallbackProvider:
    primary: LLMProvider
    fallback: LLMProvider
    name: str = "groq_then_gemini"
    last_provider: str | None = None
    last_model: str | None = None
    last_primary_error: str | None = None

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]:
        try:
            value = self.primary.generate_json(prompt, schema, temperature=temperature)
            self.last_provider = self.primary.name
            self.last_model = getattr(self.primary, "last_model", None)
            return value
        except ProviderRateLimitError:
            # A temporary primary-provider token window is not a reason to burn
            # fallback quota. structured_generate will honor its retry delay.
            # Clear stage-local attribution so a later contract-level fallback
            # does not mistake this primary failure for a stale provider result
            # retained from an earlier generation stage.
            self.last_provider = None
            self.last_model = None
            raise
        except Exception as exc:
            self.last_primary_error = str(exc)
            print(safe_text(
                f"[HostedFallbackProvider] Primary {self.primary.name} failed: "
                f"{exc}. Falling back to hosted provider {self.fallback.name}."
            ))
            try:
                value = self.fallback.generate_json(
                    prompt, schema, temperature=temperature
                )
            except Exception as fallback_exc:
                raise ValueError(
                    f"Primary {self.primary.name} failed: {exc}; "
                    f"fallback {self.fallback.name} failed: {fallback_exc}"
                ) from fallback_exc
            self.last_provider = self.fallback.name
            self.last_model = getattr(self.fallback, "last_model", None)
            return value


@dataclass
class MockProvider:
    name: str = "mock"

    def generate_json(
        self, prompt: str, schema: dict[str, Any], *, temperature: float | None = None
    ) -> dict[str, Any]:
        # Deterministic structured response for tests and offline demos.
        if "senior assignment editor" in prompt.lower():
            marker = "INPUT JSON:\n"
            payload = json.loads(prompt.split(marker, 1)[1])
            assessments = []
            for item in payload:
                impact = str(item.get("deterministic_india_hypothesis") or "")
                rejected = bool(item.get("rejection_signals"))
                consequence = 0.25 if rejected else 0.72
                india_score = 0.0 if rejected else (0.58 if impact else 0.25)
                verdict = "reject" if rejected else ("recommended" if impact else "global_watch")
                assessments.append(
                    {
                        "candidate_id": item["candidate_id"],
                        "verdict": verdict,
                        "consequence_score": consequence,
                        "india_score": india_score,
                        "evidence_score": 0.68,
                        "confidence": 0.78,
                        "reason": "Deterministic mock assignment-desk assessment.",
                        "india_impact": impact,
                        "recommended_format": "signal",
                    }
                )
            return {"assessments": assessments}
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
        if "narrative brief architect" in prompt.lower():
            marker = "INPUT JSON:\n"
            payload = json.loads(prompt.split(marker, 1)[1])
            claims = [
                str(claim.get("claim_id"))
                for claim in payload.get("claims", [])
                if claim.get("claim_id")
            ]
            primary_claim = claims[:1]
            return {
                "headline": "India-rooted systems briefing",
                "dek": str(
                    payload.get("research_summary")
                    or "A grounded explanation of evidence, consequences and uncertainty."
                )[:180],
                "category": "news",
                "thesis": "The documented development matters because implementation will determine its practical impact.",
                "opening_strategy": "Begin once with the verified development, then advance directly into evidence.",
                "closing_strategy": "End with the unresolved execution test viewers should watch next.",
                "arc": [
                    {
                        "section_type": "cold_open",
                        "purpose": "Establish the verified development and central question once.",
                        "claim_ids": primary_claim,
                        "must_not_repeat": [],
                    },
                    {
                        "section_type": "context",
                        "purpose": "Explain the documented system and relevant background.",
                        "claim_ids": primary_claim,
                        "must_not_repeat": ["the opening scene"],
                    },
                    {
                        "section_type": "key_developments",
                        "purpose": "Advance through evidence and implementation details.",
                        "claim_ids": primary_claim,
                        "must_not_repeat": ["the basic premise"],
                    },
                    {
                        "section_type": "uncertainty",
                        "purpose": "Identify the documented constraint and what remains unproven.",
                        "claim_ids": primary_claim,
                        "must_not_repeat": ["background already established"],
                    },
                    {
                        "section_type": "conclusion",
                        "purpose": "Synthesize the evidence and identify the next verifiable test.",
                        "claim_ids": primary_claim,
                        "must_not_repeat": ["the opening scene", "the full mechanism"],
                    },
                ],
            }
        if (
            "senior narrative writer" in prompt.lower()
            or "narrative continuity editor" in prompt.lower()
        ):
            marker = "INPUT JSON:\n"
            payload = json.loads(prompt.split(marker, 1)[1])
            research = payload.get("research", {})
            claims = [
                str(claim.get("claim_id"))
                for claim in research.get("claims", [])
                if claim.get("claim_id")
            ]
            primary_claim = claims[:1]
            target_match = re.search(r"(?:about|approximately)\s+(\d+)\s+spoken words", prompt)
            target_words = int(target_match.group(1)) if target_match else 145
            templates = [
                "A documented Indian pilot is moving from proposal to a practical test, creating a clear question about whether implementation can match its ambition.",
                "The available research establishes the core development without requiring speculation about results that have not yet been demonstrated.",
                "That distinction matters because an announced design and a proven operating system are different stages of evidence.",
                "Existing infrastructure, technical constraints and operator decisions now shape what can happen beyond the initial demonstration.",
                "For passengers and planners, the practical value depends on reliability, capacity and costs rather than the novelty of the underlying idea.",
                "The evidence also shows that execution will require coordination across engineering, procurement and day-to-day operations.",
                "Those requirements create a measurable test: performance must remain consistent when the pilot encounters ordinary operating conditions.",
                "Until those results are available, the responsible conclusion is neither dismissal nor celebration but careful attention to verified progress.",
                "A successful trial could inform wider investment, while a weak result would expose which assumptions need to be revised.",
                "The next meaningful update will therefore be operational data that compares the documented promise with repeatable performance.",
            ]
            chosen: list[str] = []
            word_total = 0
            for sentence in templates:
                chosen.append(sentence)
                word_total += len(sentence.split())
                if word_total >= target_words * 0.9:
                    break
            subjects = [
                "engineers",
                "operators",
                "planners",
                "auditors",
                "researchers",
                "manufacturers",
                "regulators",
                "technicians",
                "analysts",
                "investigators",
                "designers",
                "inspectors",
                "coordinators",
                "suppliers",
                "reviewers",
                "specialists",
                "evaluators",
            ]
            systems = [
                "field performance",
                "operating reliability",
                "supply resilience",
                "technical integration",
                "production readiness",
                "maintenance demand",
                "capacity planning",
                "cost discipline",
                "safety evidence",
                "deployment timing",
                "quality control",
                "infrastructure fit",
                "procurement risk",
                "service continuity",
                "workforce preparation",
                "component durability",
                "implementation evidence",
                "commercial viability",
                "system efficiency",
            ]
            methods = [
                "repeatable trials",
                "measured comparisons",
                "documented inspections",
                "controlled demonstrations",
                "independent checks",
                "operational reviews",
                "structured pilots",
                "field observations",
                "verified benchmarks",
                "practical exercises",
                "staged evaluations",
                "recorded outcomes",
                "technical audits",
                "deployment rehearsals",
                "production samples",
                "service simulations",
                "evidence reviews",
                "performance monitoring",
                "implementation studies",
                "reliability assessments",
                "comparative analysis",
                "readiness testing",
                "process validation",
            ]
            outcomes = [
                "credible adoption",
                "stable delivery",
                "lower exposure",
                "repeatable performance",
                "responsible expansion",
                "practical savings",
                "safer operation",
                "durable capacity",
                "clear accountability",
                "informed investment",
                "measurable progress",
                "reliable service",
                "stronger coordination",
                "better procurement",
                "consistent quality",
                "faster learning",
                "sound planning",
                "resilient production",
                "transparent decisions",
                "effective maintenance",
                "scalable execution",
                "verified improvement",
                "sustainable operation",
                "commercial confidence",
                "public value",
                "technical maturity",
                "operational confidence",
                "balanced growth",
                "reduced uncertainty",
            ]
            conditions = [
                "routine demand",
                "limited budgets",
                "regional constraints",
                "real schedules",
                "variable workloads",
                "public scrutiny",
                "supplier pressure",
                "maintenance cycles",
                "changing conditions",
                "scale requirements",
                "daily service",
                "field constraints",
                "production limits",
                "staffing needs",
                "weather exposure",
                "network demand",
                "market pressure",
                "regulatory review",
                "longer trials",
                "customer use",
                "factory routines",
                "distribution limits",
                "resource scarcity",
                "technical change",
                "competitive pressure",
                "local requirements",
                "operational stress",
                "deployment delays",
                "quality variation",
                "future expansion",
                "independent oversight",
            ]
            actions = [
                "inspect",
                "measure",
                "compare",
                "trace",
                "evaluate",
                "monitor",
                "test",
                "review",
                "map",
                "verify",
                "study",
                "benchmark",
                "observe",
            ]
            relations = [
                "relates",
                "compares",
                "connects",
                "contrasts",
                "matches",
                "links",
                "balances",
                "tests",
                "frames",
                "weighs",
                "checks",
            ]
            while word_total < target_words * 0.85:
                index = len(chosen)
                subject = subjects[index % len(subjects)]
                system = systems[(index * 5) % len(systems)]
                method = methods[(index * 7) % len(methods)]
                outcome = outcomes[(index * 11) % len(outcomes)]
                condition = conditions[(index * 13) % len(conditions)]
                action = actions[(index * 3) % len(actions)]
                relation = relations[(index * 5) % len(relations)]
                sentence = (
                    f"{subject.capitalize()} {action} {system} through the {method}, "
                    f"and the review {relation} {outcome} to {condition}. For the "
                    f"decision, this creates a basis for {subject} to {action} "
                    f"{system} and {outcome}."
                )
                chosen.append(sentence)
                word_total += len(sentence.split())
            return {
                "headline": "India-rooted systems briefing",
                "dek": str(
                    research.get("research_summary")
                    or "A grounded SynthPost explanation."
                )[:180],
                "category": "news",
                "beats": [
                    {
                        "beat_id": f"beat_{index:03d}",
                        "text": sentence,
                        "claim_ids": primary_claim,
                    }
                    for index, sentence in enumerate(chosen, start=1)
                ],
            }
        if "narrative segmentation editor" in prompt.lower():
            marker = "INPUT JSON:\n"
            payload = json.loads(prompt.split(marker, 1)[1])
            beat_ids = [
                str(beat.get("beat_id"))
                for beat in payload.get("draft", {}).get("beats", [])
                if beat.get("beat_id")
            ]
            section_types = [
                "cold_open",
                "context",
                "key_developments",
                "uncertainty",
                "conclusion",
            ][: len(beat_ids)]
            sections = []
            start = 0
            for index, section_type in enumerate(section_types):
                remaining_sections = len(section_types) - index
                remaining_beats = len(beat_ids) - start
                take = max(1, round(remaining_beats / remaining_sections))
                end = len(beat_ids) if index == len(section_types) - 1 else start + take
                assigned = beat_ids[start:end]
                start = end
                sections.append(
                    {
                        "section_type": section_type,
                        "beat_ids": assigned,
                        "suggested_visual_types": ["image", "video"],
                        "suggested_search_queries": [
                            f"India {section_type.replace('_', ' ')} editorial photo",
                            f"India {section_type.replace('_', ' ')} official raw footage",
                        ],
                        "suggested_template_ids": ["split_anchor_visual"],
                        "lower_third": section_type.replace("_", " ").title(),
                        "chyron": f"{section_type.replace('_', ' ').title()} explained",
                        "source_clip": None,
                    }
                )
            return {"sections": sections}
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
                "source_clip": None,
            }
        if "senior headline editor" in prompt.lower():
            marker = "INPUT JSON:\n"
            payload = json.loads(prompt.split(marker, 1)[1])
            output_sections = []
            for section in payload.get("sections", []):
                section_label = str(section.get("section_type") or "story").replace("_", " ")
                cues = []
                for beat in section.get("beats", []):
                    words = str(beat.get("narration") or section_label).split()
                    text = " ".join(words[:10]).rstrip(".,:;!?") or section_label.title()
                    cues.append({"beat_id": beat["beat_id"], "text": text[:80]})
                output_sections.append(
                    {
                        "section_id": section["section_id"],
                        "lower_third": f"{section_label.title()}: Evidence and consequences"[:80],
                        "chyron": f"{section_label.title()} explained"[:64],
                        "cues": cues,
                    }
                )
            return {
                "headline": "India-rooted systems briefing explains evidence, stakes and execution gaps",
                "dek": str(payload.get("research_summary") or "A grounded SynthPost explanation.")[:180],
                "sections": output_sections,
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
                        "source_clip": None,
                    },
                    {
                        "section_type": "context",
                        "text": "The source material gives us the context without requiring unsupported assumptions.",
                        "claim_ids": ["claim_001"],
                        "lower_third": "The Documented Context",
                        "chyron": "What the Source Material Shows",
                        "headline_cues": ["The Documented Context"],
                        "source_clip": None,
                    },
                    {
                        "section_type": "key_developments",
                        "text": "The key development is best understood through the documented facts in the research pack.",
                        "claim_ids": ["claim_001"],
                        "lower_third": "Key Developments in the Record",
                        "chyron": "The Documented Facts",
                        "headline_cues": ["Key Developments in the Record"],
                        "source_clip": None,
                    },
                    {
                        "section_type": "why_it_matters",
                        "text": "For viewers, the importance is the practical impact and the uncertainty still left open.",
                        "claim_ids": ["claim_001"],
                        "lower_third": "The Practical Impact for Viewers",
                        "chyron": "Why This Matters",
                        "headline_cues": ["The Practical Impact for Viewers"],
                        "source_clip": None,
                    },
                    {
                        "section_type": "conclusion",
                        "text": "We will keep the attribution visible and separate confirmed facts from analysis.",
                        "claim_ids": ["claim_001"],
                        "lower_third": "Confirmed Facts, Clearly Attributed",
                        "chyron": "What Is Confirmed",
                        "headline_cues": ["Confirmed Facts, Clearly Attributed"],
                        "source_clip": None,
                    },
                ],
            }
        return {"ok": True}


def configured_provider(provider_name: str | None = None) -> LLMProvider:
    provider = (provider_name or app_config.get_settings().llm.provider).strip().lower()
    if provider == "mock":
        return MockProvider()
    if provider == "hermes":
        # Imported lazily to keep the generic provider module independent of
        # agent-runtime initialization and avoid a module import cycle.
        from pipeline.agents.hermes import HermesProvider

        return HermesProvider()
    if provider == "gemini":
        return GeminiProvider()
    if provider == "groq":
        return GroqProvider()
    if provider in {"hosted_fallback", "groq_then_gemini"}:
        return HostedFallbackProvider(GroqProvider(), GeminiProvider())
    raise ValueError(
        f"Unsupported SYNTHPOST_LLM_PROVIDER: {provider}. "
        "Use groq, gemini, hermes, or the explicit hosted_fallback option."
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
        raw: dict[str, Any] | None = None
        try:
            raw = provider.generate_json(current_prompt, schema)
            value = validator(raw)
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "ok": True,
                    "prompt": current_prompt,
                    "raw": raw,
                    "provider": getattr(provider, "last_provider", None)
                    or provider.name,
                    "model": getattr(provider, "last_model", None),
                    "run_id": getattr(provider, "last_run_id", None),
                    "elapsed_seconds": round(time.time() - started, 3),
                }
            )
            return value, attempts
        except ProviderRateLimitError as exc:
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "ok": False,
                    "prompt": current_prompt,
                    "error": str(exc),
                    "provider": getattr(provider, "last_provider", None)
                    or provider.name,
                    "model": getattr(provider, "last_model", None),
                    "run_id": getattr(provider, "last_run_id", None),
                    "elapsed_seconds": round(time.time() - started, 3),
                    "retry_after_seconds": exc.retry_after_seconds,
                }
            )
            if attempt < max_retries:
                time.sleep(min(65.0, exc.retry_after_seconds + 1.0))
                current_prompt = prompt
                continue
        except Exception as exc:
            failure = {
                "attempt": attempt + 1,
                "ok": False,
                "prompt": current_prompt,
                "error": str(exc),
                "provider": getattr(provider, "last_provider", None)
                or provider.name,
                "model": getattr(provider, "last_model", None),
                "run_id": getattr(provider, "last_run_id", None),
                "elapsed_seconds": round(time.time() - started, 3),
            }
            if isinstance(raw, dict):
                failure["raw"] = raw
            attempts.append(failure)
            if "request too large" in str(exc).casefold():
                break
            current_prompt = (
                prompt
                + "\n\nYour previous response failed validation with this error:\n"
                + str(exc)
                + "\nReturn only corrected JSON."
            )
    raise StructuredGenerationError(
        f"Structured generation failed after {max_retries + 1} attempts: {attempts[-1].get('error')}",
        attempts,
    )
