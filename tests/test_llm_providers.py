from __future__ import annotations

import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from pipeline.llm.providers import (
    GeminiProvider,
    GroqProvider,
    HostedFallbackProvider,
    configured_provider,
    groq_strict_schema,
)


class _Provider:
    def __init__(self, name: str, *, error: Exception | None = None):
        self.name = name
        self.error = error

    def generate_json(self, prompt, schema, *, temperature=None):
        if self.error:
            raise self.error
        return {"provider": self.name}


class _JSONResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class LLMProviderTests(unittest.TestCase):
    def test_configured_provider_defaults_to_hosted_groq(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            provider = configured_provider()
        self.assertIsInstance(provider, GroqProvider)

    def test_configured_provider_supports_hosted_providers(self) -> None:
        self.assertIsInstance(configured_provider("groq"), GroqProvider)
        self.assertIsInstance(configured_provider("gemini"), GeminiProvider)
        self.assertIsInstance(
            configured_provider("hosted_fallback"), HostedFallbackProvider
        )

    def test_unsupported_provider_fails_instead_of_silently_falling_back(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported SYNTHPOST_LLM_PROVIDER"):
            configured_provider("local-provider")

    def test_explicit_hosted_fallback_never_uses_a_local_provider(self) -> None:
        provider = HostedFallbackProvider(
            _Provider("primary", error=RuntimeError("offline")),
            _Provider("hosted-secondary"),
        )
        value = provider.generate_json("prompt", {"type": "object"})
        self.assertEqual(value, {"provider": "hosted-secondary"})

    def test_groq_client_sends_an_explicit_application_user_agent(self) -> None:
        response = _JSONResponse(
            {"choices": [{"message": {"content": '{"ok": true}'}}]}
        )
        with patch.dict("os.environ", {"GROQ_API_KEY": "unit-key"}), patch(
            "pipeline.llm.providers.urlopen", return_value=response
        ) as mocked_urlopen:
            value = GroqProvider().generate_json(
                "Return JSON",
                {"type": "object", "properties": {"ok": {"type": "boolean"}}},
            )
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(mocked_urlopen.call_args.kwargs["timeout"], 45.0)
        self.assertEqual(value, {"ok": True})
        self.assertEqual(
            request.get_header("User-agent"),
            "SynthPostStudio/2.0 hosted-llm-client",
        )
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])

    def test_groq_strict_schema_requires_all_declared_fields(self) -> None:
        schema = groq_strict_schema(
            {"type": "object", "properties": {"name": {"type": "string"}}}
        )
        self.assertEqual(schema["required"], ["name"])
        self.assertFalse(schema["additionalProperties"])

    def test_groq_client_reports_http_error_body(self) -> None:
        error = HTTPError(
            "https://api.groq.com/openai/v1/chat/completions",
            413,
            "Payload Too Large",
            {},
            None,
        )
        error.read = lambda: b'{"error":{"message":"TPM limit 8000"}}'
        with patch.dict("os.environ", {"GROQ_API_KEY": "unit-key"}), patch(
            "pipeline.llm.providers.urlopen", side_effect=error
        ):
            with self.assertRaisesRegex(ValueError, "TPM limit 8000"):
                GroqProvider().generate_json("large prompt", {"type": "object"})


if __name__ == "__main__":
    unittest.main()
