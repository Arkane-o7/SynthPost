from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from pipeline.llm.providers import OllamaProvider


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
    def test_ollama_provider_sends_json_schema_and_parses_response(self) -> None:
        response = _JSONResponse({"response": '{"ok": true}'})
        provider = OllamaProvider(
            base_url="http://127.0.0.1:11434",
            model="unit-model",
            context_size=8192,
        )
        with patch(
            "pipeline.llm.providers.urlopen", return_value=response
        ) as mocked_urlopen:
            value = provider.generate_json(
                "Return JSON", {"type": "object", "properties": {"ok": {"type": "boolean"}}}
            )
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(value, {"ok": True})
        self.assertEqual(payload["model"], "unit-model")
        self.assertEqual(payload["format"]["type"], "object")
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertEqual(provider.last_model, "unit-model")

    def test_ollama_provider_accepts_reasoning_field_when_response_is_empty(self) -> None:
        response = _JSONResponse(
            {"response": "", "thinking": '{"ok": true}', "done": True}
        )
        provider = OllamaProvider(model="reasoning-model")
        with patch("pipeline.llm.providers.urlopen", return_value=response):
            value = provider.generate_json(
                "Return JSON",
                {"type": "object", "properties": {"ok": {"type": "boolean"}}},
            )
        self.assertEqual(value, {"ok": True})


if __name__ == "__main__":
    unittest.main()
