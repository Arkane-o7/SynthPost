from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pipeline import evidence
from pipeline.content_writing import ollama
from pipeline.llm_validation import ProviderValidationFailure, extract_json_object, run_provider_with_retries
from pipeline.news_points import default as news_points
from pipeline.storage import read_manifest, write_manifest
from tests.test_longform_writing import sample_longform_manifest


def normalized_manifest() -> dict:
    return evidence.normalize_manifest(sample_longform_manifest())


def valid_provider_script(manifest: dict, *, mode: str = "short") -> dict:
    with patch.dict(
        "os.environ",
        {
            "SYNTHPOST_SCRIPT_DURATION_MODE": mode,
            "SYNTHPOST_SCRIPT_TARGET_SECONDS": "600" if mode == "longform" else "75",
        },
    ):
        return ollama.deterministic_script(manifest)


def valid_news_points_contract(manifest: dict) -> dict:
    return news_points._deterministic_contract(manifest)


class LlmValidationRetryTests(unittest.TestCase):
    def test_raw_json_is_extracted(self) -> None:
        parsed = extract_json_object('{"ok": true, "value": 1}')
        self.assertEqual(parsed, {"ok": True, "value": 1})

    def test_markdown_fenced_json_is_extracted(self) -> None:
        parsed = extract_json_object('```json\n{"ok": true, "value": 1}\n```')
        self.assertEqual(parsed, {"ok": True, "value": 1})

    def test_prose_wrapped_json_with_trailing_text_is_extracted(self) -> None:
        parsed = extract_json_object('Here is the JSON:\n{"ok": true, "items": [1, 2]}\nDone.')
        self.assertEqual(parsed["items"], [1, 2])

    def test_minor_trailing_comma_json_is_repaired(self) -> None:
        parsed = extract_json_object('{"ok": true, "items": [1, 2,],}')
        self.assertEqual(parsed["ok"], True)
        self.assertEqual(parsed["items"], [1, 2])

    def test_malformed_json_triggers_retry(self) -> None:
        calls: list[str] = []

        def call_provider(prompt: str) -> str:
            calls.append(prompt)
            if len(calls) == 1:
                return "not json"
            return '{"ok": true}'

        normalized, audit = run_provider_with_retries(
            stage="unit_stage",
            provider="mock_llm",
            model="fixture",
            prompt="Return JSON.",
            call_provider=call_provider,
            validate_output=lambda output: (output, {"status": "pass", "warnings": []}),
            max_retries=1,
        )

        self.assertEqual(normalized, {"ok": True})
        self.assertEqual(audit["retry_count"], 1)
        self.assertIn("VALIDATION FAILED FOR STAGE", calls[1])

    def test_repeated_invalid_output_fails_clearly(self) -> None:
        with self.assertRaisesRegex(ProviderValidationFailure, "unit_stage provider output failed validation"):
            run_provider_with_retries(
                stage="unit_stage",
                provider="mock_llm",
                model="fixture",
                prompt="Return JSON.",
                call_provider=lambda _prompt: "{}",
                validate_output=lambda output: (output, {"status": "needs_review", "warnings": ["missing required field"]}),
                max_retries=1,
            )

    def test_content_writer_retries_missing_required_fields(self) -> None:
        manifest = normalized_manifest()
        valid_script = valid_provider_script(manifest)
        first = {key: value for key, value in valid_script.items() if key != "text"}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "story.json"
            write_manifest(path, manifest)
            with patch.dict(
                "os.environ",
                {
                    "SYNTHPOST_LLM_PROVIDER": "ollama",
                    "SYNTHPOST_LLM_MAX_RETRIES": "1",
                    "SYNTHPOST_SCRIPT_DURATION_MODE": "short",
                },
            ), patch("pipeline.content_writing.ollama.call_ollama_text", side_effect=[json.dumps(first), json.dumps(valid_script)]):
                script = ollama.run(path, force=True)
            updated = read_manifest(path)

        audit = updated["provider_validation"]["content_writing"]
        self.assertEqual(script["provider_validation"]["retry_count"], 1)
        self.assertEqual(audit["validation_status"], "pass")
        self.assertEqual(audit["retry_count"], 1)
        self.assertEqual(script["llm_provider"], "ollama")

    def test_content_writer_retries_groundedness_failures(self) -> None:
        manifest = normalized_manifest()
        valid_script = valid_provider_script(manifest)
        ungrounded_script = json.loads(json.dumps(valid_script))
        ungrounded_script["text"] += " This changes everything."
        ungrounded_script["sections"][0]["narration"] += " This changes everything."
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "story.json"
            write_manifest(path, manifest)
            with patch.dict(
                "os.environ",
                {
                    "SYNTHPOST_LLM_PROVIDER": "ollama",
                    "SYNTHPOST_LLM_MAX_RETRIES": "1",
                    "SYNTHPOST_SCRIPT_DURATION_MODE": "short",
                },
            ), patch(
                "pipeline.content_writing.ollama.call_ollama_text",
                side_effect=[json.dumps(ungrounded_script), json.dumps(valid_script)],
            ):
                script = ollama.run(path, force=True)
            updated = read_manifest(path)

        audit = updated["provider_validation"]["content_writing"]
        self.assertEqual(script["provider_validation"]["retry_count"], 1)
        self.assertEqual(audit["validation_status"], "pass")
        self.assertTrue(any("clickbait phrase" in error for error in audit["attempts"][0]["errors"]))

    def test_content_writer_failed_retries_write_audit(self) -> None:
        manifest = normalized_manifest()
        invalid = {"headline": "BROKEN"}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "story.json"
            write_manifest(path, manifest)
            with patch.dict(
                "os.environ",
                {"SYNTHPOST_LLM_PROVIDER": "ollama", "SYNTHPOST_LLM_MAX_RETRIES": "1"},
            ), patch("pipeline.content_writing.ollama.call_ollama_text", return_value=json.dumps(invalid)):
                with self.assertRaisesRegex(ProviderValidationFailure, "content_writing provider output failed validation"):
                    ollama.run(path, force=True)
            updated = read_manifest(path)

        audit = updated["provider_validation"]["content_writing"]
        self.assertEqual(audit["validation_status"], "failed")
        self.assertEqual(audit["retry_count"], 1)
        self.assertTrue(audit["errors"])

    def test_news_points_retries_missing_claim_ids_and_source_notes(self) -> None:
        manifest = normalized_manifest()
        manifest["script"] = valid_provider_script(manifest)
        valid_contract = valid_news_points_contract(manifest)
        section_id = valid_contract["sections"][0]["section_id"]
        invalid_contract = {
            "sections": [
                {
                    "section_id": section_id,
                    "key_points": [{"text": "Nvidia warned AI chip export controls could affect global data center supply chains"}],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "story.json"
            write_manifest(path, manifest)
            with patch.dict(
                "os.environ",
                {
                    "SYNTHPOST_NEWS_POINTS_PROVIDER": "ollama",
                    "SYNTHPOST_LLM_MAX_RETRIES": "1",
                },
            ), patch(
                "pipeline.content_writing.ollama.call_ollama_text",
                side_effect=[json.dumps(invalid_contract), json.dumps(valid_contract)],
            ):
                points = news_points.run(path, force=True)
            updated = read_manifest(path)

        self.assertTrue(points)
        audit = updated["provider_validation"]["news_points"]
        self.assertEqual(audit["validation_status"], "pass")
        self.assertEqual(audit["retry_count"], 1)
        self.assertEqual(updated["news_points_review"]["retry_count"], 1)

    def test_groundedness_flags_clickbait_language(self) -> None:
        manifest = normalized_manifest()
        script = valid_provider_script(manifest)
        script["text"] += " This changes everything."
        script["sections"][0]["narration"] += " This changes everything."

        review = ollama.validate_script_contract(script, manifest["raw"], ollama.writing_options_for(manifest))

        self.assertEqual(review["status"], "needs_review")
        self.assertIn("this changes everything", review["groundedness"]["clickbait_markers"])

    def test_mock_provider_remains_deterministic(self) -> None:
        manifest = normalized_manifest()
        with patch.dict("os.environ", {"SYNTHPOST_LLM_PROVIDER": "mock", "SYNTHPOST_SCRIPT_DURATION_MODE": "short"}):
            first = ollama.deterministic_script(manifest)
            second = ollama.deterministic_script(manifest)

        self.assertEqual(first["text"], second["text"])
        self.assertEqual(first["sections"], second["sections"])

    def test_ollama_chat_payload_preserves_think_false(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"message": {"content": "{\"ok\": true}"}}).encode("utf-8")

        def fake_urlopen(request: object, timeout: float) -> FakeResponse:
            captured["timeout"] = timeout
            captured["payload"] = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
            return FakeResponse()

        with patch.dict(
            "os.environ",
            {
                "SYNTHPOST_OLLAMA_API": "chat",
                "SYNTHPOST_OLLAMA_MODEL": "gemma4:26b",
                "SYNTHPOST_OLLAMA_THINK": "0",
            },
        ), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            parsed = ollama.call_ollama("Return JSON.")

        payload = captured["payload"]
        self.assertEqual(parsed, {"ok": True})
        self.assertEqual(payload["model"], "gemma4:26b")
        self.assertEqual(payload["think"], False)
        self.assertIn("messages", payload)


if __name__ == "__main__":
    unittest.main()
