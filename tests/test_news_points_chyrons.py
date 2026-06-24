from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import evidence
from pipeline.content_writing import ollama
from pipeline.news_points import default as news_points
from pipeline.storage import read_manifest, write_manifest
from tests.test_longform_writing import sample_longform_manifest


def scripted_manifest(*, mode: str = "longform") -> dict:
    manifest = evidence.normalize_manifest(sample_longform_manifest())
    with patch.dict(
        "os.environ",
        {
            "SYNTHPOST_SCRIPT_DURATION_MODE": mode,
            "SYNTHPOST_SCRIPT_TARGET_SECONDS": "600" if mode == "longform" else "75",
        },
    ):
        script = ollama.deterministic_script(manifest)
    manifest["script"] = script
    return manifest


def word_count(text: str) -> int:
    return len(news_points._words(text))


class NewsPointsChyronsTests(unittest.TestCase):
    def test_chyrons_are_generated_per_script_section(self) -> None:
        manifest = scripted_manifest()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "story.json"
            write_manifest(path, manifest)
            with patch.dict("os.environ", {"SYNTHPOST_NEWS_POINTS_PROVIDER": "mock"}):
                points = news_points.run(path, force=True)
            updated = read_manifest(path)

        sections = updated["script"]["sections"]
        self.assertEqual(len(sections), len(ollama.DURATION_PROFILES["longform"]["section_ids"]))
        self.assertGreaterEqual(len(points), 3)
        self.assertGreaterEqual(len(updated["chyrons"]), 3)
        self.assertEqual(updated["news_points_review"]["status"], "pass")
        for section in sections:
            self.assertTrue(section["key_points"])
            self.assertTrue(section["lower_thirds"])
            self.assertTrue(section["chyrons"])
            self.assertTrue(section["on_screen_bullets"])
            self.assertTrue(section["key_points"][0]["claim_ids"])

    def test_flattened_points_and_chyrons_are_deduped(self) -> None:
        manifest = scripted_manifest()
        contract = news_points.normalize_contract(news_points._deterministic_contract(manifest), manifest)

        point_texts = [item["text"].lower() for item in contract["points"]]
        chyron_texts = [item["text"].lower() for item in contract["chyrons"]]

        self.assertEqual(len(point_texts), len(set(point_texts)))
        self.assertEqual(len(chyron_texts), len(set(chyron_texts)))
        self.assertGreaterEqual(len(chyron_texts), 3)

    def test_generated_screen_text_respects_length_limits(self) -> None:
        manifest = scripted_manifest()
        contract = news_points.normalize_contract(news_points._deterministic_contract(manifest), manifest)

        for section in contract["sections"]:
            for field, limits in news_points.FIELD_LIMITS.items():
                for item in section[field]:
                    self.assertLessEqual(word_count(item["text"]), limits["max_words"], f"{field}: {item['text']}")
                    self.assertLessEqual(len(item["text"]), limits["max_chars"], f"{field}: {item['text']}")

    def test_chyrons_are_grounded_in_claims_and_evidence(self) -> None:
        manifest = scripted_manifest()
        contract = news_points.normalize_contract(news_points._deterministic_contract(manifest), manifest)
        review = news_points.validate_contract(contract, manifest)

        self.assertEqual(review["status"], "pass")
        for point in contract["points"]:
            self.assertTrue(point["claim_ids"])
            grounding = news_points._item_grounding_review(point, manifest["raw"])
            self.assertEqual(grounding["status"], "pass")

    def test_unsupported_screen_claims_are_rejected(self) -> None:
        manifest = scripted_manifest(mode="short")
        section_id = manifest["script"]["sections"][0]["section_id"]
        contract = {
            "provider": "ollama",
            "model": "fixture",
            "sections": [
                {
                    "section_id": section_id,
                    "key_points": [
                        {
                            "text": "Sam Altman caused Nvidia market collapse by 2040",
                            "type": "key_fact",
                            "section_id": section_id,
                            "claim_ids": ["claim_01"],
                            "source_notes": ["claim_01"],
                            "start": 0,
                            "end": 6,
                        }
                    ],
                    "lower_thirds": [],
                    "chyrons": [],
                    "on_screen_bullets": [],
                    "quote_cards": [],
                    "data_callouts": [],
                }
            ],
        }

        normalized = news_points.normalize_contract(contract, manifest)
        review = normalized["review"]

        self.assertEqual(review["status"], "needs_review")
        self.assertTrue(any("unsupported named entity" in warning for warning in review["warnings"]))
        self.assertTrue(any("unsupported factual marker: 2040" in warning for warning in review["warnings"]))
        self.assertTrue(any("unsupported causal marker" in warning for warning in review["warnings"]))

    def test_provider_items_without_claim_ids_get_traceable_fallbacks(self) -> None:
        manifest = scripted_manifest(mode="short")
        section_id = manifest["script"]["sections"][0]["section_id"]
        contract = {
            "provider": "ollama",
            "model": "fixture",
            "sections": [
                {
                    "section_id": section_id,
                    "key_points": [{"text": "Nvidia warned AI chip export controls could affect global data center supply chains"}],
                    "lower_thirds": [{"text": "Nvidia warned AI chip export controls could affect global data center supply chains"}],
                    "chyrons": [],
                    "on_screen_bullets": [],
                    "quote_cards": [],
                    "data_callouts": [],
                }
            ],
        }

        normalized = news_points.normalize_contract(contract, manifest)
        provider_item = normalized["sections"][0]["key_points"][0]

        self.assertEqual(normalized["review"]["status"], "pass")
        self.assertTrue(provider_item["claim_ids"])
        self.assertTrue(provider_item["source_notes"])

    def test_short_form_scripts_still_generate_points(self) -> None:
        manifest = scripted_manifest(mode="short")
        contract = news_points.normalize_contract(news_points._deterministic_contract(manifest), manifest)

        self.assertEqual(len(contract["sections"]), len(ollama.DURATION_PROFILES["short"]["section_ids"]))
        self.assertEqual(contract["review"]["status"], "pass")
        self.assertTrue(contract["points"])
        self.assertTrue(contract["chyrons"])

    def test_missing_optional_section_metadata_does_not_crash(self) -> None:
        manifest = evidence.normalize_manifest(
            {
                "story_id": "story_001",
                "episode_id": "ep_sparse_chyron",
                "raw": {
                    "headline_source": "Officials publish grid policy update",
                    "summary": "Officials published a short grid policy update.",
                    "source_url": "https://example.com/grid",
                    "source_name": "Example Source",
                    "category": "energy",
                    "published_at": "2026-06-24T09:00:00Z",
                    "facts": ["Officials published a short grid policy update."],
                },
                "script": {
                    "text": "Officials published a short grid policy update.",
                    "headline": "GRID POLICY UPDATE",
                    "category": "ENERGY",
                    "claim_ids": ["claim_01"],
                },
                "direction": {},
                "visuals": [],
                "points": [],
                "composition": {},
            }
        )

        contract = news_points.normalize_contract(news_points._deterministic_contract(manifest), manifest)

        self.assertEqual(contract["review"]["status"], "pass")
        self.assertTrue(contract["points"])
        self.assertEqual(contract["sections"][0]["section_id"], "main_developments")

    def test_legacy_scripts_without_chyrons_remain_valid(self) -> None:
        manifest = scripted_manifest(mode="short")
        manifest["script"].pop("sections")
        manifest["points"] = []

        points = news_points.derive_points(manifest)

        self.assertTrue(points)
        self.assertIn("text", points[0])
        self.assertIn("start", points[0])

    def test_story_manifest_schema_includes_chyron_contract(self) -> None:
        schema_path = Path("pipeline/schemas/story_manifest.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertIn("screenTextItem", schema["definitions"])
        section_props = schema["properties"]["script"]["properties"]["sections"]["items"]["properties"]
        self.assertIn("key_points", section_props)
        self.assertIn("lower_thirds", section_props)
        self.assertIn("chyrons", section_props)
        self.assertIn("news_points_review", schema["properties"])
        self.assertIn("chyrons", schema["properties"])


if __name__ == "__main__":
    unittest.main()
