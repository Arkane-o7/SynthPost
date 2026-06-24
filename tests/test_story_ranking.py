from __future__ import annotations

import json
import shutil
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pipeline.news_collection.candidates import SCORE_FIELDS, build_candidate_story
from pipeline.news_collection.ranking import rank_candidates, score_candidate, selected_candidates
from pipeline.run_episode import main as run_episode_main
from pipeline.storage import PROJECT_ROOT, read_manifest


NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def high_impact_ai_story():
    return build_candidate_story(
        headline="Nvidia warns new AI chip export controls could reshape global data center supply chains",
        source_name="The Verge",
        source_url="https://www.theverge.com/ai/chip-export-controls",
        published_at="Wed, 24 Jun 2026 08:00:00 GMT",
        category="ai",
        summary=(
            "Nvidia warned that new AI chip export controls could affect global data center supply chains. "
            "Analysts said the policy may shift frontier model training, semiconductor demand, and US-China technology competition."
        ),
        facts=[
            "Nvidia warned new export controls could affect AI chip demand.",
            "Analysts said data center supply chains may shift.",
            "The rules could affect US-China technology competition.",
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


def filler_story():
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


class StoryRankingTests(unittest.TestCase):
    episode_id = "ep_unit_story_ranking"

    def tearDown(self) -> None:
        shutil.rmtree(PROJECT_ROOT / "episodes" / self.episode_id, ignore_errors=True)

    def test_high_impact_story_outranks_filler(self) -> None:
        ranked = rank_candidates([filler_story(), high_impact_ai_story()], now=NOW)

        self.assertEqual(ranked[0].headline, high_impact_ai_story().headline)
        self.assertEqual(ranked[0].selection_status, "selected")
        self.assertGreater(ranked[0].final_editorial_score, ranked[1].final_editorial_score)
        self.assertIn("score", ranked[0].selection_reason)

    def test_weak_filler_gets_rejection_reasons(self) -> None:
        ranked = rank_candidates([filler_story()], now=NOW)
        candidate = ranked[0]

        self.assertEqual(candidate.selection_status, "rejected")
        self.assertIn("celebrity_or_entertainment_without_public_interest", candidate.rejection_reasons)
        self.assertIn("source_logo_only_visuals", candidate.rejection_reasons)
        self.assertTrue(candidate.rejection_reason)

    def test_freshness_alone_does_not_beat_importance(self) -> None:
        older_important = build_candidate_story(
            headline="India and China expand border surveillance after new military talks",
            source_name="Firstpost",
            source_url="https://www.firstpost.com/world/india-china-border-surveillance",
            published_at="Thu, 18 Jun 2026 09:00:00 GMT",
            category="geopolitics",
            summary=(
                "Officials said India and China expanded border surveillance after military talks. "
                "Analysts said the deployment could affect regional security calculations and defense technology spending."
            ),
            facts=[
                "India and China expanded border surveillance after military talks.",
                "Analysts said the deployment could affect regional security calculations.",
                "The story connects defense technology, borders, and regional security.",
            ],
            key_entities=["India", "China"],
            source_reliability_tier="high",
            visual_opportunities=["Border map", "Satellite imagery", "Official briefing footage"],
        )

        ranked = rank_candidates([filler_story(), older_important], now=NOW)

        self.assertEqual(ranked[0].headline, older_important.headline)
        self.assertGreater(ranked[0].importance_score, ranked[1].importance_score)
        self.assertLess(ranked[0].freshness_score, ranked[1].freshness_score)

    def test_unreliable_sources_are_downranked(self) -> None:
        reliable = score_candidate(high_impact_ai_story(), now=NOW)
        unreliable = score_candidate(
            build_candidate_story(
                headline=high_impact_ai_story().headline,
                source_name="Unknown source",
                source_url="",
                published_at="Wed, 24 Jun 2026 08:00:00 GMT",
                category="ai",
                summary=high_impact_ai_story().summary,
                facts=high_impact_ai_story().facts,
                key_entities=high_impact_ai_story().key_entities,
                source_reliability_tier="low",
                visual_opportunities=high_impact_ai_story().visual_opportunities,
            ),
            now=NOW,
        )

        self.assertLess(unreliable.source_reliability_score, reliable.source_reliability_score)
        self.assertLess(unreliable.final_editorial_score, reliable.final_editorial_score)
        self.assertIn("low_source_reliability", unreliable.rejection_reasons)

    def test_strong_visual_potential_scores_higher(self) -> None:
        weak = build_candidate_story(
            headline="Major energy regulator sets new tariff rules for power grids",
            source_name="Example Energy",
            source_url="https://example.com/energy/grid-rules",
            published_at="Wed, 24 Jun 2026 08:00:00 GMT",
            category="energy",
            summary="A regulator set new tariff rules for power grids, affecting operators and industrial customers.",
            facts=[
                "A regulator set new tariff rules for power grids.",
                "Grid operators and industrial customers may be affected.",
            ],
            key_entities=["FERC"],
            source_reliability_tier="medium",
            visual_opportunities=["Source logo only"],
        )
        strong = build_candidate_story(
            headline=weak.headline,
            source_name=weak.source_name,
            source_url=weak.source_url,
            published_at=weak.published_at,
            category=weak.category,
            summary=weak.summary,
            facts=weak.facts,
            key_entities=weak.key_entities,
            source_reliability_tier=weak.source_reliability_tier,
            visual_opportunities=[
                "Power grid control-room footage",
                "Tariff document screenshot",
                "Regional grid map",
                "Electricity price chart",
            ],
        )

        self.assertGreater(score_candidate(strong, now=NOW).visual_potential_score, score_candidate(weak, now=NOW).visual_potential_score)

    def test_ranked_candidates_include_all_score_fields_and_reasons(self) -> None:
        candidate = rank_candidates([high_impact_ai_story()], now=NOW)[0]
        record = candidate.to_record()

        for field in SCORE_FIELDS:
            self.assertIn(field, record)
            self.assertIsInstance(record[field], float)
            self.assertIn(field, record["score_reasons"])
        self.assertEqual(record["selection_status"], "selected")
        self.assertEqual(record["rejection_reasons"], [])

    def test_final_selection_is_based_on_score_not_input_order(self) -> None:
        ranked = rank_candidates([filler_story(), high_impact_ai_story()], now=NOW)

        selected = selected_candidates(ranked)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].headline, high_impact_ai_story().headline)

    def test_run_episode_writes_selected_highest_ranked_story(self) -> None:
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
            with patch("pipeline.run_episode.rss.collect", return_value=[filler_story(), high_impact_ai_story()]):
                with patch("pipeline.run_episode.run_story"):
                    with patch("subprocess.run"):
                        run_episode_main()

        story = read_manifest(PROJECT_ROOT / "episodes" / self.episode_id / "stories" / "story_001" / "story.json")
        candidates_payload = json.loads((PROJECT_ROOT / "episodes" / self.episode_id / "story_candidates.json").read_text())

        self.assertEqual(story["raw"]["headline_source"], high_impact_ai_story().headline)
        self.assertEqual(story["raw"]["editorial"]["selection_status"], "selected")
        self.assertEqual(candidates_payload["candidates"][0]["selection_status"], "selected")
        self.assertEqual(candidates_payload["candidates"][0]["headline"], high_impact_ai_story().headline)

    def test_pr1_raw_manifest_fields_remain_backward_compatible(self) -> None:
        candidate = rank_candidates([high_impact_ai_story()], now=NOW)[0]
        raw = candidate.to_raw()

        self.assertEqual(raw["headline_source"], candidate.headline)
        self.assertEqual(raw["source_url"], candidate.source_url)
        self.assertEqual(raw["source_name"], candidate.source_name)
        self.assertEqual(raw["entities"], candidate.key_entities)
        self.assertEqual(raw["key_entities"], candidate.key_entities)
        self.assertTrue(raw["facts"])
        self.assertTrue(raw["claims"])
        self.assertTrue(raw["sources"])
        self.assertIn("scores", raw["editorial"])


if __name__ == "__main__":
    unittest.main()
