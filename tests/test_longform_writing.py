from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import evidence
from pipeline.content_writing import ollama


def sample_longform_manifest() -> dict:
    facts = [
        "Nvidia warned AI chip export controls could affect global data center supply chains.",
        "Analysts said the policy may shift frontier model training.",
        "The story connects semiconductor demand and US-China technology competition.",
    ]
    claims = [
        {
            "claim_id": f"claim_{index:02d}",
            "text": fact,
            "source_ids": ["source_01"],
            "evidence": [{"source_id": "source_01", "url": "https://www.theverge.com/ai/chip-export-controls", "quote": fact}],
            "confidence": "source_reported",
            "status": "supported",
        }
        for index, fact in enumerate(facts, start=1)
    ]
    source = {
        "source_id": "source_01",
        "name": "The Verge",
        "url": "https://www.theverge.com/ai/chip-export-controls",
        "title": "Nvidia warns AI chip export controls could reshape data center supply chains",
        "source_type": "rss",
        "source_provider": "rss",
        "domain": "theverge.com",
    }
    raw = {
        "headline_source": "Nvidia warns AI chip export controls could reshape data center supply chains",
        "summary": (
            "Nvidia warned that AI chip export controls could affect global data center supply chains. "
            "Analysts said the policy may shift frontier model training and US-China technology competition."
        ),
        "source_url": "https://www.theverge.com/ai/chip-export-controls",
        "source_name": "The Verge",
        "source_domain": "theverge.com",
        "category": "ai",
        "published_at": "2026-06-24T08:00:00Z",
        "facts": facts,
        "entities": ["Nvidia", "United States", "China"],
        "key_entities": ["Nvidia", "United States", "China"],
        "sources": [source],
        "claims": claims,
        "source_metadata": {
            "source_name": "The Verge",
            "source_url": "https://www.theverge.com/ai/chip-export-controls",
            "source_domain": "theverge.com",
            "source_provider": "rss",
            "source_type": "rss",
        },
        "handoff": {
            "writing": {
                "candidate_id": "cand_ai_chip",
                "headline": "Nvidia warns AI chip export controls could reshape data center supply chains",
                "summary": (
                    "Nvidia warned that AI chip export controls could affect global data center supply chains. "
                    "Analysts said the policy may shift frontier model training and US-China technology competition."
                ),
                "category": "ai",
                "facts": facts,
                "claims": claims,
                "claim_ids": ["claim_01", "claim_02", "claim_03"],
                "entities": ["Nvidia", "United States", "China"],
                "sources": [source],
                "source_metadata": {
                    "source_name": "The Verge",
                    "source_url": "https://www.theverge.com/ai/chip-export-controls",
                    "source_domain": "theverge.com",
                },
                "why_it_matters": "AI accelerators are central to frontier model training and geopolitical leverage.",
                "synthpost_angle": "How export controls turn AI infrastructure into geopolitical leverage.",
                "audience_curiosity_angle": "The story combines market stakes, chip controls, China, and visible data-center demand.",
                "explainability_notes": "The source material names supply chains, training, and competition as context signals.",
                "score_reasons": {
                    "final_editorial_score": "Selected as a high-scoring AI infrastructure story.",
                    "explainability_score": "3 facts and 3 entities make the story explainable.",
                },
                "selection_reason": "Selected as the highest-ranked acceptable story.",
            }
        },
    }
    return {
        "story_id": "story_001",
        "episode_id": "ep_longform_test",
        "raw": raw,
        "script": {},
        "direction": {},
        "visuals": [],
        "points": [],
        "composition": {},
    }


class LongformWritingTests(unittest.TestCase):
    def test_duration_profile_clamps_target_seconds(self) -> None:
        with patch.dict(
            "os.environ",
            {"SYNTHPOST_SCRIPT_DURATION_MODE": "longform", "SYNTHPOST_SCRIPT_TARGET_SECONDS": "1200"},
        ):
            options = ollama.writing_options_for(sample_longform_manifest())

        self.assertEqual(options["duration_mode"], "longform")
        self.assertEqual(options["target_duration_seconds"], 900)
        self.assertEqual(options["min_duration_seconds"], 300)
        self.assertEqual(options["max_duration_seconds"], 900)

    def test_invalid_script_duration_mode_is_rejected(self) -> None:
        with patch.dict("os.environ", {"SYNTHPOST_SCRIPT_DURATION_MODE": "marathon"}):
            with self.assertRaisesRegex(ValueError, "Invalid script duration mode `marathon`"):
                ollama.writing_options_for(sample_longform_manifest())

        manifest = evidence.normalize_manifest(sample_longform_manifest())
        script = ollama.deterministic_script(manifest)
        script["duration_mode"] = "marathon"

        review = ollama.validate_script_contract(script, manifest["raw"])

        self.assertEqual(review["status"], "needs_review")
        self.assertTrue(any("unsupported script duration_mode" in warning for warning in review["warnings"]))

    def test_longform_deterministic_script_has_required_sections_and_duration(self) -> None:
        manifest = evidence.normalize_manifest(sample_longform_manifest())
        with patch.dict(
            "os.environ",
            {"SYNTHPOST_SCRIPT_DURATION_MODE": "longform", "SYNTHPOST_SCRIPT_TARGET_SECONDS": "600"},
        ):
            script = ollama.deterministic_script(manifest)
            review = ollama.validate_script_contract(script, manifest["raw"], ollama.writing_options_for(manifest))

        section_ids = [section["section_id"] for section in script["sections"]]
        self.assertEqual(script["script_version"], ollama.SCRIPT_VERSION)
        self.assertEqual(script["duration_mode"], "longform")
        self.assertEqual(script["target_duration_seconds"], 600)
        self.assertEqual(script["estimated_duration_seconds"], 600)
        self.assertEqual(section_ids, ollama.DURATION_PROFILES["longform"]["section_ids"])
        self.assertTrue(all(section["narration"] for section in script["sections"]))
        self.assertTrue(all(section["source_notes"] for section in script["sections"]))
        self.assertIn("Nvidia warned AI chip export controls", script["text"])
        self.assertEqual(review["status"], "pass")

    def test_prompt_consumes_handoff_metadata_and_duration_mode(self) -> None:
        manifest = evidence.normalize_manifest(sample_longform_manifest())
        with patch.dict(
            "os.environ",
            {"SYNTHPOST_SCRIPT_DURATION_MODE": "longform", "SYNTHPOST_SCRIPT_TARGET_SECONDS": "600"},
        ):
            prompt = ollama.prompt_for(manifest)
            writing_input = ollama.writing_input_for(manifest)

        self.assertEqual(writing_input["candidate_id"], "cand_ai_chip")
        self.assertIn("Duration mode: longform", prompt)
        self.assertIn("Target duration seconds: 600", prompt)
        self.assertIn("opposing_views_uncertainty", prompt)
        self.assertIn("SynthPost angle: How export controls turn AI infrastructure", prompt)
        self.assertIn("Entities: Nvidia, United States, China", prompt)

    def test_groundedness_flags_unsupported_numbers(self) -> None:
        manifest = evidence.normalize_manifest(sample_longform_manifest())
        options = {
            **ollama.DURATION_PROFILES["short"],
            "duration_mode": "short",
            "target_duration_seconds": 75,
            "required_section_ids": ollama.DURATION_PROFILES["short"]["section_ids"],
        }
        script = {
            "script_version": ollama.SCRIPT_VERSION,
            "text": "By 2040, Nvidia will control a new chip market.",
            "headline": "Unsupported Claim",
            "category": "AI",
            "duration_mode": "short",
            "target_duration_seconds": 75,
            "estimated_duration_seconds": 75,
            "claim_ids": ["claim_01"],
            "sections": [
                {
                    "section_id": section_id,
                    "title": section_id,
                    "narration": "By 2040, Nvidia will control a new chip market.",
                    "estimated_duration_seconds": 75 / 4,
                    "claim_ids": ["claim_01"],
                    "source_notes": ["claim_01"],
                }
                for section_id in options["required_section_ids"]
            ],
            "major_claims": [{"text": "By 2040, Nvidia will control a new chip market.", "claim_ids": ["claim_01"]}],
            "caveats": [],
        }

        review = ollama.validate_script_contract(script, manifest["raw"], options)

        self.assertEqual(review["status"], "needs_review")
        self.assertIn("2040", review["groundedness"]["unsupported_factual_markers"])

    def test_groundedness_flags_unsupported_names_and_causal_claims(self) -> None:
        manifest = evidence.normalize_manifest(sample_longform_manifest())
        options = ollama.writing_options_for(manifest)
        section_ids = options["required_section_ids"]
        script = {
            "script_version": ollama.SCRIPT_VERSION,
            "text": "Sam Altman said the policy caused Nvidia's market collapse.",
            "headline": "Unsupported Claim",
            "category": "AI",
            "duration_mode": "short",
            "target_duration_seconds": 75,
            "estimated_duration_seconds": 75,
            "claim_ids": ["claim_01"],
            "sections": [
                {
                    "section_id": section_id,
                    "title": section_id,
                    "narration": "Sam Altman said the policy caused Nvidia's market collapse.",
                    "estimated_duration_seconds": 75 / len(section_ids),
                    "claim_ids": ["claim_01"],
                    "source_notes": ["claim_01"],
                }
                for section_id in section_ids
            ],
            "major_claims": [
                {
                    "text": "Sam Altman said the policy caused Nvidia's market collapse.",
                    "claim_ids": ["claim_01"],
                }
            ],
            "caveats": [],
        }

        review = ollama.validate_script_contract(script, manifest["raw"], options)

        self.assertEqual(review["status"], "needs_review")
        self.assertIn("Sam Altman", review["groundedness"]["unsupported_named_entities"])
        self.assertIn("caused", review["groundedness"]["unsupported_causal_markers"])

    def test_short_form_mode_still_writes_legacy_fields(self) -> None:
        manifest = evidence.normalize_manifest(sample_longform_manifest())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "story.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.dict("os.environ", {"SYNTHPOST_LLM_PROVIDER": "mock", "SYNTHPOST_SCRIPT_DURATION_MODE": "short"}):
                script = ollama.run(path, force=True)

        self.assertEqual(script["duration_mode"], "short")
        self.assertEqual(script["target_duration_seconds"], 75)
        self.assertEqual(script["headline"], script["title"])
        self.assertTrue(script["text"])
        self.assertEqual(script["claim_ids"], ["claim_01", "claim_02", "claim_03"])
        self.assertEqual([section["section_id"] for section in script["sections"]], ollama.DURATION_PROFILES["short"]["section_ids"])
        self.assertEqual(script["contract_review"]["status"], "pass")

    def test_old_provider_shape_is_normalized_into_structured_contract(self) -> None:
        manifest = evidence.normalize_manifest(sample_longform_manifest())
        old_shape = {
            "text": "Nvidia warned AI chip export controls could affect global data center supply chains.",
            "headline": "NVIDIA WARNING",
            "category": "AI",
            "claim_ids": ["claim_01"],
            "source_ids": ["source_01"],
            "caveats": [],
        }
        with patch.dict(
            "os.environ",
            {"SYNTHPOST_SCRIPT_DURATION_MODE": "standard", "SYNTHPOST_SCRIPT_TARGET_SECONDS": "240"},
        ):
            normalized = ollama.normalize_script_contract(old_shape, manifest)
            review = ollama.validate_script_contract(normalized, manifest["raw"], ollama.writing_options_for(manifest))

        self.assertEqual(normalized["duration_mode"], "standard")
        self.assertEqual(normalized["target_duration_seconds"], 240)
        self.assertTrue(normalized["sections"])
        self.assertEqual(review["status"], "pass")

    def test_missing_optional_handoff_metadata_does_not_crash(self) -> None:
        manifest = evidence.normalize_manifest(
            {
                "story_id": "story_001",
                "episode_id": "ep_sparse",
                "raw": {
                    "headline_source": "Sparse policy update",
                    "summary": "Officials published a short policy update.",
                    "source_url": "https://example.com/policy",
                    "source_name": "Example Source",
                    "category": "policy",
                    "published_at": "2026-06-24T09:00:00Z",
                    "facts": ["Officials published a short policy update."],
                },
                "script": {},
                "direction": {},
                "visuals": [],
                "points": [],
                "composition": {},
            }
        )
        with patch.dict("os.environ", {"SYNTHPOST_SCRIPT_DURATION_MODE": "longform"}):
            script = ollama.deterministic_script(manifest)
            review = ollama.validate_script_contract(script, manifest["raw"], ollama.writing_options_for(manifest))

        self.assertEqual(script["duration_mode"], "longform")
        self.assertEqual(review["status"], "pass")


if __name__ == "__main__":
    unittest.main()
