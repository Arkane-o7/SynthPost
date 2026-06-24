from __future__ import annotations

import json
import shutil
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

from pipeline.content_writing.ollama import prompt_for, writing_input_for
from pipeline.manifest_summary import summarize_episode
from pipeline.news_collection.candidates import build_candidate_story
from pipeline.news_collection.ranking import rank_candidates
from pipeline.provenance import read_episode_manifest
from pipeline.run_episode import create_story_manifest, main as run_episode_main
from pipeline.storage import PROJECT_ROOT, read_manifest
from pipeline.thumbnails import brief_record_for_story, thumbnail_handoff_for_manifest

ROOT = PROJECT_ROOT
SRC_DIR = ROOT / "src"
if SRC_DIR.as_posix() not in sys.path:
    sys.path.insert(0, SRC_DIR.as_posix())

from synthpost.visuals.query_builder import build_story_segments, build_visual_queries, visual_handoff_for_manifest


NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def selected_ai_candidate():
    candidate = build_candidate_story(
        headline="Nvidia warns AI chip export controls could reshape data center supply chains",
        source_name="The Verge",
        source_url="https://www.theverge.com/ai/chip-export-controls",
        published_at="Wed, 24 Jun 2026 08:00:00 GMT",
        category="ai",
        summary=(
            "Nvidia warned that AI chip export controls could affect global data center supply chains. "
            "Analysts said the policy may shift frontier model training and US-China technology competition."
        ),
        facts=[
            "Nvidia warned AI chip export controls could affect global data center supply chains.",
            "Analysts said the policy may shift frontier model training.",
            "The story connects semiconductor demand and US-China technology competition.",
        ],
        key_entities=["Nvidia", "United States", "China"],
        source_reliability_tier="high",
        visual_opportunities=[
            "Nvidia event footage",
            "AI chip and data center video",
            "Export-control document screenshot",
            "Market chart showing semiconductor impact",
        ],
    )
    candidate = replace(
        candidate,
        why_it_matters="AI accelerators are central to frontier model training and geopolitical leverage.",
        why_it_could_perform_well="The story combines market stakes, chip controls, China, and visible data-center demand.",
        possible_synthpost_angle="How export controls turn AI infrastructure into geopolitical leverage.",
        possible_thumbnail_hook="AI CHIP RULES HIT THE DATA CENTER RACE",
        possible_title_ideas=[
            "AI Chip Controls Put Data Centers Under Pressure",
            "Nvidia Warning Shows the New AI Supply Chain Risk",
        ],
    )
    return rank_candidates([candidate], now=NOW)[0]


def filler_candidate():
    return build_candidate_story(
        headline="Actor shares behind-the-scenes selfie after a weekend party",
        source_name="Entertainment Wire",
        source_url="https://gossip.example/actor-party-selfie",
        published_at="Wed, 24 Jun 2026 11:30:00 GMT",
        category="celebrity",
        summary="An actor shared a selfie after a weekend party and fans reacted online.",
        facts=["An actor shared a selfie after a weekend party."],
        key_entities=["Actor"],
        source_reliability_tier="medium",
        visual_opportunities=["Source logo only"],
    )


class EditorialHandoffTests(unittest.TestCase):
    episode_id = "ep_unit_editorial_handoff"

    def tearDown(self) -> None:
        shutil.rmtree(PROJECT_ROOT / "episodes" / self.episode_id, ignore_errors=True)

    def _manifest(self) -> dict:
        candidate = selected_ai_candidate()
        audit_path = PROJECT_ROOT / "episodes" / self.episode_id / "story_candidates.json"
        path = create_story_manifest(
            self.episode_id,
            "story_001",
            candidate,
            test_mode=True,
            render_profile="preview",
            candidate_audit_path=audit_path,
        )
        return read_manifest(path)

    def test_selected_candidate_metadata_flows_into_story_raw(self) -> None:
        manifest = self._manifest()
        raw = manifest["raw"]
        selected = raw["selected_candidate"]

        self.assertEqual(selected["candidate_id"], raw["editorial"]["candidate_id"])
        self.assertEqual(selected["headline"], raw["headline_source"])
        self.assertEqual(selected["source"], "The Verge")
        self.assertEqual(selected["source_domain"], "theverge.com")
        self.assertEqual(selected["source_provider"], "rss")
        self.assertEqual(selected["source_type"], "rss")
        self.assertEqual(selected["normalized_category"], "ai")
        self.assertEqual(selected["selection_status"], "selected")
        self.assertIn("final_editorial_score", selected["scores"])
        self.assertEqual(selected["final_editorial_score"], raw["editorial"]["scores"]["final_editorial_score"])
        self.assertIn("Selected as the highest-ranked", selected["selection_reason"])
        self.assertEqual(raw["story_candidates_path"], f"episodes/{self.episode_id}/story_candidates.json")
        self.assertEqual(raw["source_metadata"]["source_domain"], "theverge.com")

    def test_writing_input_receives_facts_claims_entities_angle_and_scores(self) -> None:
        manifest = self._manifest()
        writing = writing_input_for(manifest)
        prompt = prompt_for(manifest)

        self.assertEqual(writing["candidate_id"], manifest["raw"]["editorial"]["candidate_id"])
        self.assertIn("Nvidia", writing["entities"])
        self.assertTrue(writing["facts"])
        self.assertEqual([claim["text"] for claim in writing["claims"]], manifest["raw"]["facts"])
        self.assertIn("geopolitical leverage", writing["synthpost_angle"])
        self.assertIn("final_editorial_score", writing["score_reasons"])
        self.assertIn("SynthPost angle: How export controls turn AI infrastructure", prompt)
        self.assertIn("Entities: Nvidia, United States, China", prompt)

    def test_visual_handoff_feeds_visual_query_planning(self) -> None:
        manifest = self._manifest()
        handoff = visual_handoff_for_manifest(manifest)
        segments = build_story_segments(manifest, target_count=3)
        queries = build_visual_queries(manifest, segments)
        combined_queries = " ".join(query.query for query in queries)

        self.assertIn("Export-control document screenshot", handoff["visual_opportunities"])
        self.assertIn("Nvidia", handoff["entities"])
        self.assertEqual(handoff["source_metadata"]["source_domain"], "theverge.com")
        self.assertIn("Nvidia", combined_queries)
        self.assertIn("AI chip and data center video", combined_queries)

    def test_thumbnail_handoff_feeds_thumbnail_brief(self) -> None:
        manifest = self._manifest()
        handoff = thumbnail_handoff_for_manifest(manifest)
        record = brief_record_for_story(manifest)

        self.assertEqual(handoff["thumbnail_hook"], "AI CHIP RULES HIT THE DATA CENTER RACE")
        self.assertIn("Nvidia", handoff["entities"])
        self.assertEqual(handoff["source_domain"], "theverge.com")
        self.assertIn("AI Chip Controls Put Data Centers", handoff["title_ideas"][0])
        self.assertEqual(record["handoff"]["thumbnail_hook"], handoff["thumbnail_hook"])
        self.assertEqual(record["story_angle"], "How export controls turn AI infrastructure into geopolitical leverage.")
        self.assertEqual(record["curiosity_gap"], handoff["audience_curiosity_angle"])

    def test_manifest_summary_includes_selected_candidate_score_source_and_reason(self) -> None:
        self._manifest()
        summary = summarize_episode(PROJECT_ROOT / "episodes" / self.episode_id)

        selected = summary["selected_candidate"]
        self.assertEqual(selected["source"], "The Verge")
        self.assertEqual(selected["category"], "ai")
        self.assertIsInstance(selected["final_editorial_score"], float)
        self.assertIn("Selected as the highest-ranked", selected["selection_reason"])

    def test_missing_optional_editorial_fields_degrade_gracefully(self) -> None:
        candidate = build_candidate_story(
            headline="Sparse policy update",
            source_name="Example Source",
            source_url="https://example.com/policy",
            category="policy",
            summary="Officials published a short policy update.",
            facts=["Officials published a short policy update."],
        )
        path = create_story_manifest(self.episode_id, "story_001", candidate, test_mode=True, render_profile="preview")
        manifest = read_manifest(path)

        self.assertTrue(writing_input_for(manifest)["facts"])
        self.assertIsInstance(visual_handoff_for_manifest(manifest)["visual_opportunities"], list)
        self.assertIsInstance(thumbnail_handoff_for_manifest(manifest)["entities"], list)
        self.assertEqual(summarize_episode(PROJECT_ROOT / "episodes" / self.episode_id)["headline"], "Sparse policy update")

    def test_legacy_raw_without_handoff_still_exposes_source_metadata(self) -> None:
        manifest = {
            "episode_id": self.episode_id,
            "story_id": "story_001",
            "raw": {
                "headline_source": "Legacy source story",
                "summary": "A legacy story manifest has no selected-candidate handoff.",
                "source_name": "Example Legacy",
                "source_url": "https://legacy.example/news/story",
                "source_domain": "legacy.example",
                "category": "technology",
                "published_at": "2026-06-24T09:00:00Z",
                "facts": ["A legacy story manifest has no selected-candidate handoff."],
                "entities": ["Legacy"],
                "visual_opportunities": ["Source-page screenshot"],
                "title_ideas": ["Legacy Source Story"],
                "thumbnail_hooks": ["LEGACY SOURCE STORY"],
            },
            "script": {},
            "direction": {},
            "visuals": [],
            "points": [],
            "composition": {},
        }

        writing = writing_input_for(manifest)
        visuals = visual_handoff_for_manifest(manifest)
        thumbnail = thumbnail_handoff_for_manifest(manifest)

        self.assertEqual(writing["source_metadata"]["source_url"], "https://legacy.example/news/story")
        self.assertEqual(visuals["source_metadata"]["source_domain"], "legacy.example")
        self.assertEqual(thumbnail["source_url"], "https://legacy.example/news/story")
        self.assertEqual(thumbnail["source_domain"], "legacy.example")

    def test_run_episode_records_editorial_selection_in_episode_manifest(self) -> None:
        argv = [
            "run_episode.py",
            "--episode-id",
            self.episode_id,
            "--stories",
            "1",
            "--candidate-limit",
            "2",
            "--test-mode",
            "--render-profile",
            "preview",
            "--skip-avatar-render",
        ]
        with patch.object(sys, "argv", argv):
            with patch("pipeline.run_episode.rss.collect", return_value=[filler_candidate(), selected_ai_candidate()]):
                with patch("pipeline.run_episode.run_story"):
                    with patch("subprocess.run"):
                        run_episode_main()

        episode_manifest = read_episode_manifest(self.episode_id)
        selection = episode_manifest["editorial_selection"]
        story = read_manifest(PROJECT_ROOT / "episodes" / self.episode_id / "stories" / "story_001" / "story.json")
        candidates_payload = json.loads((PROJECT_ROOT / "episodes" / self.episode_id / "story_candidates.json").read_text())

        self.assertEqual(selection["story_candidates_path"], f"episodes/{self.episode_id}/story_candidates.json")
        self.assertEqual(selection["selected_count"], 1)
        self.assertEqual(selection["rejected_count"], 1)
        self.assertEqual(selection["selected_candidates"][0]["candidate_id"], story["raw"]["selected_candidate"]["candidate_id"])
        self.assertEqual(selection["selected_candidates"][0]["story_json_path"], f"episodes/{self.episode_id}/stories/story_001/story.json")
        self.assertEqual(candidates_payload["candidates"][0]["selection_status"], "selected")
        self.assertTrue(selection["rejected_candidates"][0]["rejection_reasons"])


if __name__ == "__main__":
    unittest.main()
