from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import evidence
from pipeline.content_writing import ollama


def sample_manifest() -> dict:
    return {
        "story_id": "story_001",
        "episode_id": "ep_test",
        "raw": {
            "headline_source": "Grid operators face new large-load rules",
            "summary": "A regulator ordered grid operators to standardize large-load interconnection rules.",
            "source_url": "https://example.gov/grid-order",
            "source_name": "Example Regulator",
            "category": "energy",
            "published_at": "2026-06-21T12:00:00Z",
            "facts": [
                "Grid operators must submit tariff revisions within thirty days.",
                "The order covers large industrial users including data centers.",
            ],
        },
        "script": {},
        "direction": {},
        "visuals": [],
        "points": [],
        "composition": {},
    }


class EvidenceLedgerTests(unittest.TestCase):
    def test_normalize_manifest_builds_sources_claims_and_summary(self) -> None:
        manifest = evidence.normalize_manifest(sample_manifest())

        raw = manifest["raw"]
        self.assertEqual(raw["sources"][0]["source_id"], "source_01")
        self.assertEqual(raw["claims"][0]["claim_id"], "claim_01")
        self.assertEqual(raw["claims"][0]["source_ids"], ["source_01"])
        self.assertEqual(raw["evidence_summary"]["status"], "ready")

    def test_content_writer_requires_and_attaches_claim_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            story_path = Path(temp_dir) / "story.json"
            story_path.write_text(json.dumps(sample_manifest()), encoding="utf-8")

            with patch.dict("os.environ", {"SYNTHPOST_LLM_PROVIDER": "mock"}):
                script = ollama.run(story_path, force=True)

            manifest = json.loads(story_path.read_text(encoding="utf-8"))

        self.assertEqual(script["claim_ids"], ["claim_01", "claim_02"])
        self.assertEqual(script["source_ids"], ["source_01"])
        self.assertEqual(script["llm_provider"], "mock")
        self.assertEqual(script["llm_model"], "deterministic_script")
        self.assertEqual(script["evidence_summary"]["status"], "pass")
        self.assertEqual(manifest["editorial_review"]["status"], "pass")

    def test_unknown_script_claim_id_fails_review(self) -> None:
        manifest = evidence.normalize_manifest(sample_manifest())
        review = evidence.validate_script(
            {"text": "A sourced sentence.", "claim_ids": ["claim_99"]},
            manifest["raw"],
        )

        self.assertEqual(review["status"], "needs_review")
        self.assertEqual(review["unknown_claim_ids"], ["claim_99"])

    def test_ollama_parser_accepts_wrapped_json_object(self) -> None:
        parsed = ollama._parse_json_response('Here is the JSON: {"text": "ok", "claim_ids": ["claim_01"]}')

        self.assertEqual(parsed["text"], "ok")
        self.assertEqual(parsed["claim_ids"], ["claim_01"])

    def test_ollama_chat_url_derives_from_generate_url(self) -> None:
        with patch.dict("os.environ", {"SYNTHPOST_OLLAMA_URL": "http://localhost:11434/api/generate"}):
            self.assertEqual(ollama._ollama_url(use_chat=True), "http://localhost:11434/api/chat")

    def test_ollama_chat_response_rejects_thinking_without_content(self) -> None:
        with self.assertRaises(RuntimeError):
            ollama._ollama_response_text({"message": {"thinking": "still thinking"}}, use_chat=True)

    def test_ollama_provider_metadata_records_model_and_api(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "SYNTHPOST_OLLAMA_MODEL": "gemma4:26b",
                "SYNTHPOST_OLLAMA_API": "chat",
            },
        ):
            metadata = ollama._provider_metadata("ollama")

        self.assertEqual(metadata["llm_provider"], "ollama")
        self.assertEqual(metadata["llm_model"], "gemma4:26b")
        self.assertEqual(metadata["llm_api"], "chat")

    def test_reused_script_can_record_explicit_provider_metadata(self) -> None:
        manifest = evidence.normalize_manifest(sample_manifest())
        manifest["script"] = {
            "text": "Grid operators must submit tariff revisions within thirty days.",
            "headline": "Grid operators face new large-load rules",
            "category": "energy",
            "claim_ids": ["claim_01"],
            "source_ids": ["source_01"],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            story_path = Path(temp_dir) / "story.json"
            story_path.write_text(json.dumps(manifest), encoding="utf-8")

            with patch.dict(
                "os.environ",
                {"SYNTHPOST_LLM_PROVIDER": "ollama", "SYNTHPOST_OLLAMA_MODEL": "gemma4:26b"},
            ):
                script = ollama.run(story_path, force=False)

        self.assertEqual(script["llm_provider"], "ollama")
        self.assertEqual(script["llm_model"], "gemma4:26b")


if __name__ == "__main__":
    unittest.main()
