from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.news_collection import rss
from pipeline.news_collection.cache import fetch_url
from pipeline.news_collection.candidates import build_candidate_story
from pipeline.news_collection.dedupe import dedupe_candidates
from pipeline.news_collection.ranking import rank_candidates, selected_candidates
from pipeline.news_collection.sources import FeedSource, feed_source_categories


class FakeResponse:
    def __init__(self, data: bytes):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.data


class NewsCollectionSourceTests(unittest.TestCase):
    def test_default_sources_cover_required_categories(self) -> None:
        self.assertTrue(
            {
                "global",
                "india",
                "technology",
                "ai",
                "economy",
                "business",
                "energy",
                "geopolitics",
                "defense",
                "climate",
            }.issubset(feed_source_categories())
        )

    def test_source_metadata_and_atom_parsing_are_normalized(self) -> None:
        atom = """
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Example Atom</title>
          <entry>
            <title>NASA releases satellite images showing rapid coastal flooding</title>
            <link href="https://example.gov/climate/flooding?utm_source=rss" />
            <updated>2026-06-24T08:30:00Z</updated>
            <category term="Climate" />
            <summary><![CDATA[<p>NASA released satellite images showing coastal flooding after days of heavy rain.</p><p>Officials said ports and roads could face disruption.</p>]]></summary>
          </entry>
        </feed>
        """
        source = FeedSource("nasa_test", "NASA RSS Feed", "https://example.gov/rss", "climate", "official")

        candidates = rss.parse_feed(atom, url=source.url, source=source)

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.source_name, "NASA")
        self.assertEqual(candidate.source_provider, "rss")
        self.assertEqual(candidate.source_type, "rss")
        self.assertEqual(candidate.source_category, "climate")
        self.assertEqual(candidate.feed_url, source.url)
        self.assertEqual(candidate.source_domain, "example.gov")
        self.assertEqual(candidate.published_at, "2026-06-24T08:30:00Z")
        self.assertEqual(candidate.category, "climate")
        self.assertTrue(all("<" not in fact for fact in candidate.facts))
        self.assertGreaterEqual(len(candidate.facts), 2)

    def test_malformed_and_missing_feed_fields_degrade_gracefully(self) -> None:
        self.assertEqual(rss.parse_feed("<rss><channel><item>", url="https://bad.example/rss"), [])

        feed = """
        <rss><channel>
          <item>
            <title>Central bank warns tariff shock may hit inflation</title>
          </item>
        </channel></rss>
        """
        candidates = rss.parse_feed(feed, url="https://fallback.example/rss")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source_url, "https://fallback.example/rss")
        self.assertEqual(candidates[0].source_name, "fallback.example")
        self.assertTrue(candidates[0].facts)

    def test_feed_failure_does_not_break_collection(self) -> None:
        sources = [
            FeedSource("bad", "Bad Feed", "https://bad.example/rss", "general", "unknown"),
            FeedSource("ok", "Ok Feed", "https://ok.example/rss", "technology", "high"),
        ]
        survivor = build_candidate_story(
            headline="OpenAI announces new enterprise AI safety controls",
            source_name="Ok Feed",
            source_url="https://ok.example/ai/safety",
            category="ai",
            summary="OpenAI announced new enterprise AI safety controls. Companies said the rules could affect deployment.",
            source_reliability_tier="high",
        )

        with patch("pipeline.news_collection.rss.feed_sources", return_value=sources):
            with patch("pipeline.news_collection.rss.fetch_feed", side_effect=[OSError("offline"), [survivor]]):
                collected = rss.collect(limit=3)

        self.assertEqual([candidate.headline for candidate in collected], [survivor.headline])

    def test_dedupe_merges_similar_headlines_and_keeps_stronger_source(self) -> None:
        weaker = build_candidate_story(
            headline="AI chip controls may hit Nvidia data center demand",
            source_name="Unknown Tech",
            source_url="https://unknown.example/story-1",
            category="ai",
            summary="AI chip controls may hit Nvidia data center demand.",
            facts=["AI chip controls may hit Nvidia data center demand."],
            key_entities=["Nvidia"],
            source_reliability_tier="unknown",
        )
        stronger = build_candidate_story(
            headline="Nvidia AI chip controls could hit data center demand",
            source_name="The Verge",
            source_url="https://www.theverge.com/ai/chip-controls",
            category="ai",
            summary=(
                "Nvidia AI chip controls could hit data center demand. "
                "Analysts said the policy may affect supply chains and US-China technology competition."
            ),
            facts=[
                "Nvidia AI chip controls could hit data center demand.",
                "Analysts said the policy may affect supply chains.",
            ],
            key_entities=["Nvidia"],
            source_reliability_tier="high",
        )

        deduped = dedupe_candidates([weaker, stronger])

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].source_name, "The Verge")
        self.assertEqual(deduped[0].dedupe_status, "merged")
        self.assertIn(weaker.candidate_id, deduped[0].dedupe_merged_candidate_ids)
        self.assertTrue(deduped[0].dedupe_reasons)

    def test_cache_hit_and_miss_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            with patch("urllib.request.urlopen", return_value=FakeResponse(b"<rss>first</rss>")) as opener:
                first = fetch_url("https://example.com/rss", cache_dir=cache_dir, ttl_seconds=3600)
            with patch("urllib.request.urlopen", return_value=FakeResponse(b"<rss>second</rss>")) as opener_again:
                second = fetch_url("https://example.com/rss", cache_dir=cache_dir, ttl_seconds=3600)

        self.assertEqual(first, b"<rss>first</rss>")
        self.assertEqual(second, b"<rss>first</rss>")
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(opener_again.call_count, 0)

    def test_stronger_raw_facts_are_grounded_and_linked_to_claims(self) -> None:
        candidate = build_candidate_story(
            headline="Grid operators face 30-day tariff deadline",
            source_name="Example Energy",
            source_url="https://example.com/energy/grid-tariff",
            category="energy",
            summary=(
                "<p>FERC said standardized rules are intended to support grid reliability.</p>"
                "<p>The agency launched a fast-track proceeding on June 18.</p>"
                "<p>Operators have 30 days to submit tariff plans.</p>"
            ),
        )
        raw = candidate.to_raw()

        self.assertGreaterEqual(len(raw["facts"]), 3)
        self.assertTrue(all("<" not in fact for fact in raw["facts"]))
        self.assertEqual([claim["text"] for claim in raw["claims"]], raw["facts"])
        self.assertTrue(all(claim["evidence"][0]["url"] == candidate.source_url for claim in raw["claims"]))

    def test_ranking_still_selects_best_candidate_after_dedupe(self) -> None:
        filler = build_candidate_story(
            headline="Actor shares behind-the-scenes selfie after party",
            source_name="Entertainment Wire",
            source_url="https://gossip.example/selfie",
            category="celebrity",
            summary="An actor shared a selfie and fans reacted online.",
            facts=["An actor shared a selfie."],
            source_reliability_tier="medium",
            visual_opportunities=["Source logo only"],
        )
        duplicate_ai = build_candidate_story(
            headline="Nvidia AI chip controls could hit data center demand",
            source_name="The Verge",
            source_url="https://www.theverge.com/ai/chip-controls",
            category="ai",
            summary=(
                "Nvidia AI chip controls could hit data center demand. "
                "Analysts said the policy may affect supply chains and US-China technology competition."
            ),
            facts=[
                "Nvidia AI chip controls could hit data center demand.",
                "Analysts said the policy may affect supply chains.",
                "The story could affect US-China technology competition.",
            ],
            key_entities=["Nvidia", "China"],
            source_reliability_tier="high",
            visual_opportunities=["Nvidia event footage", "AI chip data center video", "Policy document screenshot"],
        )
        deduped = dedupe_candidates([filler, duplicate_ai, duplicate_ai])
        ranked = rank_candidates(deduped, select_count=1)

        self.assertEqual(selected_candidates(ranked)[0].headline, duplicate_ai.headline)
        self.assertEqual(len([candidate for candidate in ranked if "Nvidia" in candidate.headline]), 1)


if __name__ == "__main__":
    unittest.main()
