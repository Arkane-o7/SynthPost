from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from pipeline.news_collection import rss
from pipeline.news_collection.candidates import (
    SCORE_FIELDS,
    build_candidate_story,
    candidates_payload,
    normalize_category,
    normalize_headline,
    write_story_candidates,
)
from pipeline.run_episode import create_story_manifest
from pipeline.storage import PROJECT_ROOT, read_manifest


class StoryDiscoveryCandidateTests(unittest.TestCase):
    episode_id = "ep_unit_story_candidates"

    def tearDown(self) -> None:
        shutil.rmtree(PROJECT_ROOT / "episodes" / self.episode_id, ignore_errors=True)

    def test_candidate_normalization_and_required_fields(self) -> None:
        candidate = build_candidate_story(
            headline="Nvidia shares fall as new AI chip export rules hit demand",
            source_name="Example Tech",
            source_url="https://example.com/ai/chips",
            published_at="Tue, 23 Jun 2026 10:12:00 GMT",
            category="technology",
            summary="Nvidia shares fell after new AI chip export controls raised concerns about demand. Analysts said data center supply chains could be affected.",
        )
        record = candidate.to_record()

        self.assertEqual(candidate.headline_source, candidate.headline)
        self.assertEqual(record["published_at"], "2026-06-23T10:12:00Z")
        self.assertEqual(record["category"], "ai")
        self.assertEqual(record["normalized_headline"], normalize_headline(candidate.headline))
        self.assertTrue(record["candidate_id"].startswith("cand_"))
        self.assertTrue(record["cluster_id"].startswith("cluster_"))
        self.assertIn("Nvidia", record["key_entities"])
        self.assertGreaterEqual(len(record["facts"]), 1)
        self.assertGreaterEqual(len(record["visual_opportunities"]), 1)
        for field in SCORE_FIELDS:
            self.assertIn(field, record)
            self.assertEqual(record[field], 0.0)

    def test_rss_parse_normalizes_source_date_category_and_facts(self) -> None:
        feed = """
        <rss><channel>
          <title>Example World</title>
          <item>
            <title>India and China expand border surveillance technology</title>
            <link>https://example.com/world/india-china-border</link>
            <pubDate>Wed, 24 Jun 2026 09:00:00 GMT</pubDate>
            <category>Geopolitics</category>
            <description><![CDATA[Officials said new surveillance systems are being deployed near contested areas. Analysts say the move could shift regional security calculations.]]></description>
          </item>
        </channel></rss>
        """

        candidates = rss.parse_feed(feed, url="https://example.com/rss")

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.source_name, "Example World")
        self.assertEqual(candidate.published_at, "2026-06-24T09:00:00Z")
        self.assertEqual(candidate.category, "india")
        self.assertIn("India", candidate.key_entities)
        self.assertTrue(candidate.facts)

    def test_story_candidates_file_payload(self) -> None:
        candidates = [
            build_candidate_story(
                headline="Major energy grid decision affects AI data centers",
                source_name="Example Energy",
                source_url="https://example.com/energy/grid",
                summary="A regulator announced new grid rules for data centers.",
            )
        ]

        output_path = write_story_candidates(self.episode_id, candidates)
        payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload, candidates_payload(self.episode_id, candidates) | {"generated_at": payload["generated_at"]})
        self.assertEqual(payload["candidate_count"], 1)
        self.assertEqual(payload["candidates"][0]["headline"], candidates[0].headline)

    def test_candidate_to_story_manifest_raw_metadata(self) -> None:
        candidate = build_candidate_story(
            headline="Satellite images reveal flooding near major port",
            source_name="Example Climate Desk",
            source_url="https://example.com/climate/flood-port",
            category="climate",
            summary="Satellite images showed flooding near a major port after days of heavy rain.",
        )

        path = create_story_manifest(self.episode_id, "story_001", candidate, test_mode=True, render_profile="preview")
        manifest = read_manifest(path)
        raw = manifest["raw"]

        self.assertEqual(raw["headline_source"], candidate.headline)
        self.assertEqual(raw["editorial"]["candidate_id"], candidate.candidate_id)
        self.assertEqual(raw["key_entities"], candidate.key_entities)
        self.assertEqual(raw["visual_opportunities"], candidate.visual_opportunities)
        self.assertEqual(raw["title_ideas"], candidate.possible_title_ideas)
        self.assertTrue(raw["claims"])
        self.assertTrue(raw["sources"])

    def test_category_normalization_prefers_synthpost_domains(self) -> None:
        self.assertEqual(normalize_category("markets", source_url="https://example.com/tariff-inflation"), "economy")
        self.assertEqual(normalize_category("", source_name="NASA Image and Video Library"), "general")


if __name__ == "__main__":
    unittest.main()
