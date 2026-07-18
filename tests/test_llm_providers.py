from __future__ import annotations

import json
import signal
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from pipeline.llm.providers import (
    CodexProvider,
    GeminiProvider,
    GroqProvider,
    HostedFallbackProvider,
    ProviderConfigurationError,
    ProviderRateLimitError,
    _codex_environment,
    _run_codex_command,
    configured_provider,
    groq_strict_schema,
    structured_generate,
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
        self.assertIsInstance(configured_provider("codex"), CodexProvider)
        self.assertIsInstance(configured_provider("groq"), GroqProvider)
        self.assertIsInstance(configured_provider("gemini"), GeminiProvider)
        self.assertIsInstance(
            configured_provider("hosted_fallback"), HostedFallbackProvider
        )

    def test_unsupported_provider_fails_instead_of_silently_falling_back(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported SYNTHPOST_LLM_PROVIDER"):
            configured_provider("local-provider")

    def test_codex_provider_runs_isolated_schema_constrained_generation(self) -> None:
        captured: dict[str, object] = {}

        def run(command, **kwargs):
            captured["command"] = command
            captured["prompt"] = kwargs["prompt"]
            captured["environment"] = kwargs["environment"]
            output_path = Path(
                command[command.index("--output-last-message") + 1]
            )
            schema_path = Path(command[command.index("--output-schema") + 1])
            captured["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
            output_path.write_text('{"ok": true}', encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with patch(
            "pipeline.llm.providers._run_codex_command", side_effect=run
        ):
            value = CodexProvider(
                binary=sys.executable,
                model="gpt-5.6-sol",
                reasoning_effort="medium",
            ).generate_json(
                "Write the result.",
                {"type": "object", "properties": {"ok": {"type": "boolean"}}},
            )

        self.assertEqual(value, {"ok": True})
        command = captured["command"]
        self.assertEqual(command[0], "/usr/bin/sandbox-exec")
        self.assertIn("(deny process-exec)", command[2])
        self.assertIn("(deny process-fork)", command[2])
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("read-only", command)
        self.assertIn("gpt-5.6-sol", command)
        self.assertIn("shell_tool", command)
        self.assertIn("multi_agent", command)
        self.assertIn('web_search="disabled"', command)
        self.assertIn("agents.max_threads=1", command)
        self.assertIn("agents.max_depth=0", command)
        self.assertEqual(captured["schema"]["required"], ["ok"])
        self.assertFalse(captured["schema"]["additionalProperties"])
        self.assertIn("Do not use tools", captured["prompt"])

    def test_codex_child_environment_excludes_credentials_and_pythonpath(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "HOME": "/tmp/home",
                "PATH": "/usr/bin",
                "PYTHONPATH": "/private/source",
                "GROQ_API_KEY": "secret",
                "GEMINI_API_KEY": "secret",
                "CODEX_API_KEY": "secret",
                "CODEX_HOME": "/tmp/codex-home",
            },
            clear=True,
        ):
            environment = _codex_environment()
        self.assertEqual(environment["HOME"], "/tmp/home")
        self.assertEqual(environment["CODEX_HOME"], "/tmp/codex-home")
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("GROQ_API_KEY", environment)
        self.assertNotIn("GEMINI_API_KEY", environment)
        self.assertNotIn("CODEX_API_KEY", environment)

    def test_codex_provider_explains_missing_login(self) -> None:
        failed = subprocess.CompletedProcess(
            ["codex"], 1, stdout="", stderr="Not logged in"
        )
        with patch(
            "pipeline.llm.providers._run_codex_command", return_value=failed
        ):
            with self.assertRaisesRegex(ValueError, "Run `codex login`"):
                CodexProvider(binary=sys.executable).generate_json(
                    "prompt",
                    {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                )

    def test_codex_configuration_failure_is_not_retried(self) -> None:
        provider = _Provider(
            "codex",
            error=ProviderConfigurationError("Codex is not authenticated"),
        )
        with self.assertRaisesRegex(
            ValueError, "Codex is not authenticated"
        ) as raised:
            structured_generate(
                provider,
                "prompt",
                {"type": "object"},
                lambda value: value,
                max_retries=2,
            )
        self.assertEqual(len(raised.exception.attempts), 1)

    def test_codex_process_group_is_stopped_on_outer_job_timeout(self) -> None:
        process = MagicMock()
        process.pid = 4242
        process.poll.return_value = None
        process.communicate.side_effect = [
            TimeoutError("worker deadline"),
            ("", ""),
        ]
        with patch("pipeline.llm.providers.subprocess.Popen", return_value=process), patch(
            "pipeline.llm.providers.os.killpg"
        ) as killpg:
            with self.assertRaisesRegex(TimeoutError, "worker deadline"):
                _run_codex_command(
                    ["codex"],
                    prompt="prompt",
                    timeout_seconds=180,
                    environment={},
                )
        killpg.assert_called_once_with(4242, signal.SIGTERM)
        self.assertEqual(process.communicate.call_count, 2)

    def test_codex_provider_maps_plan_limit_to_retryable_failure(self) -> None:
        failed = subprocess.CompletedProcess(
            ["codex"], 1, stdout="", stderr="Usage limit reached"
        )
        with patch(
            "pipeline.llm.providers._run_codex_command", return_value=failed
        ):
            with self.assertRaises(ProviderRateLimitError):
                CodexProvider(binary=sys.executable).generate_json(
                    "prompt",
                    {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                )

    def test_codex_provider_requires_final_structured_file(self) -> None:
        completed = subprocess.CompletedProcess(
            ["codex"], 0, stdout='{"ok": true}', stderr=""
        )
        with patch(
            "pipeline.llm.providers._run_codex_command", return_value=completed
        ):
            with self.assertRaisesRegex(ValueError, "without writing"):
                CodexProvider(binary=sys.executable).generate_json(
                    "prompt",
                    {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                )

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
        self.assertEqual(body["max_completion_tokens"], 2300)
        self.assertEqual(
            body["response_format"]["json_schema"]["schema"]["type"], "object"
        )
        self.assertTrue(body["response_format"]["json_schema"]["strict"])

    def test_groq_strict_schema_requires_all_declared_fields(self) -> None:
        schema = groq_strict_schema(
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"id": {"type": "string"}},
                        },
                    },
                },
            }
        )
        self.assertEqual(schema["required"], ["name", "items"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["items"]["items"]["required"], ["id"])

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

    def test_temporary_groq_limit_waits_without_consuming_fallback_quota(self) -> None:
        primary = _Provider(
            "groq",
            error=ProviderRateLimitError("temporary limit", retry_after_seconds=2),
        )
        fallback = _Provider("gemini")
        provider = HostedFallbackProvider(primary, fallback)

        with patch("pipeline.llm.providers.time.sleep") as sleep:
            with self.assertRaisesRegex(ValueError, "temporary limit"):
                structured_generate(
                    provider,
                    "original prompt",
                    {"type": "object"},
                    lambda value: value,
                    max_retries=1,
                )

        sleep.assert_called_once_with(3.0)
        self.assertIsNone(provider.last_provider)

    def test_hosted_fallback_reports_both_provider_errors(self) -> None:
        provider = HostedFallbackProvider(
            _Provider("groq", error=RuntimeError("groq limit")),
            _Provider("gemini", error=RuntimeError("gemini quota")),
        )
        with self.assertRaisesRegex(
            ValueError, "Primary groq failed: groq limit; fallback gemini failed"
        ):
            provider.generate_json("prompt", {"type": "object"})


if __name__ == "__main__":
    unittest.main()
