from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthpost.visuals.providers.manifest_media import ManifestMediaProvider
from synthpost.visuals.models import AssetType, ProviderReport, StorySegment, VisualAsset, VisualProvider, VisualQuery
from synthpost.visuals.policy import asset_is_selectable, normalize_asset_metadata
from synthpost.visuals.providers.source_page import SourcePageProvider
from synthpost.visuals.providers.free_sources import (
    DropfolderSourceProvider,
    SOURCE_PROFILES,
    SocialReferenceIngestProvider,
)
from synthpost.visuals.providers.screenshot_provider import ScreenshotProvider
from synthpost.visuals.query_builder import build_story_segments, build_visual_queries
from synthpost.visuals.planner import build_visual_plan
from synthpost.visuals.ranker import rank_assets_for_segment
from synthpost.visuals.validator import validate_asset
from pipeline.visuals.default import _has_visual_metadata


class FixtureVisualProvider(VisualProvider):
    def __init__(self, name: str, assets: list[VisualAsset]) -> None:
        self.name = name
        self.assets = assets

    def search(
        self,
        *,
        manifest: dict,
        story_json_path: Path,
        segments: list[StorySegment],
        queries: list[VisualQuery],
    ) -> tuple[list[VisualAsset], ProviderReport]:
        return self.assets, ProviderReport(provider=self.name, query_count=len(queries), candidate_count=len(self.assets))


class VisualPlanningTests(unittest.TestCase):
    def test_segments_expand_from_facts_and_script(self) -> None:
        manifest = {
            "story_id": "story_001",
            "episode_id": "ep_test",
            "raw": {
                "headline_source": "Grid operators face new power rules",
                "summary": "A regulator is changing the process for large electricity users.",
                "source_url": "https://example.gov/news",
                "source_name": "Example Agency",
                "category": "energy",
                "facts": [
                    "Operators must file revised tariffs within thirty days.",
                    "Large data centers are part of the load growth pressure.",
                    "The order emphasizes reliability and cost transparency.",
                ],
            },
            "script": {
                "headline": "GRID RULES CHANGE FOR LARGE LOADS",
                "category": "ENERGY",
                "text": (
                    "The first sentence explains the federal grid decision in plain terms. "
                    "The second sentence explains why data centers matter for power planning. "
                    "The third sentence explains what utilities must file next."
                ),
            },
            "direction": {"estimated_duration_seconds": 54},
            "composition": {"headlines": [{"text": "GRID RULES CHANGE", "start": 0}]},
        }

        segments = build_story_segments(manifest, target_count=5)

        self.assertEqual(len(segments), 5)
        self.assertEqual(segments[0].start, 0)
        self.assertGreater(segments[-1].end, segments[-1].start)
        self.assertTrue(any("data" in segment.keywords for segment in segments))

    def test_manifest_media_keeps_rights_metadata(self) -> None:
        manifest = {
            "story_id": "story_001",
            "raw": {
                "source_url": "https://example.gov/source",
                "source_name": "Example Agency",
                "official_media": [
                    {
                        "url": "https://example.gov/media/briefing.mp4",
                        "asset_type": "video",
                        "license": "public domain",
                        "usage_note": "Official briefing footage.",
                        "source_name": "Example Agency",
                        "keywords": "briefing grid rules",
                    }
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            story_path = Path(temp_dir) / "episodes" / "ep_test" / "stories" / "story_001" / "story.json"
            story_path.parent.mkdir(parents=True)
            provider = ManifestMediaProvider(ROOT)
            segments = build_story_segments(
                {
                    **manifest,
                    "script": {"headline": "GRID RULES", "text": "Briefing grid rules are discussed.", "category": "energy"},
                    "direction": {"estimated_duration_seconds": 20},
                    "composition": {},
                },
                target_count=1,
            )
            queries = build_visual_queries(manifest, segments)

            assets, report = provider.search(
                manifest=manifest,
                story_json_path=story_path,
                segments=segments,
                queries=queries,
            )

        self.assertEqual(report.candidate_count, 1)
        self.assertEqual(assets[0].asset_type.value, "video")
        self.assertEqual(assets[0].source_name, "Example Agency")
        self.assertTrue(assets[0].safe_to_use)
        self.assertEqual(assets[0].license, "public domain")
        normalize_asset_metadata(assets[0])
        self.assertEqual(assets[0].rights_tier, "green")
        self.assertEqual(assets[0].rights_confidence, "verified")
        self.assertIn(assets[0].media_type, {"video", "photo"})

    def test_pb_shabd_and_pib_are_separate_dropfolder_providers(self) -> None:
        profiles = {profile.provider: profile for profile in SOURCE_PROFILES}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pb_path = root / "media" / "sources" / "pb_shabd_dropfolder" / "cabinet.mp4"
            pib_path = root / "media" / "sources" / "pib_india" / "policy.jpg"
            pb_path.parent.mkdir(parents=True)
            pib_path.parent.mkdir(parents=True)
            pb_path.write_bytes(b"fake")
            pib_path.write_bytes(b"fake")

            pb_assets, pb_report = DropfolderSourceProvider(root, profiles["pb_shabd_dropfolder"]).search(
                manifest={"story_id": "story_001"},
                story_json_path=root / "episodes" / "ep" / "stories" / "story" / "story.json",
                segments=[],
                queries=[],
            )
            pib_assets, pib_report = DropfolderSourceProvider(root, profiles["pib_india"]).search(
                manifest={"story_id": "story_001"},
                story_json_path=root / "episodes" / "ep" / "stories" / "story" / "story.json",
                segments=[],
                queries=[],
            )

        self.assertEqual(pb_report.provider, "pb_shabd_dropfolder")
        self.assertEqual(pib_report.provider, "pib_india")
        self.assertEqual(pb_report.candidate_count, 1)
        self.assertEqual(pib_report.candidate_count, 1)
        self.assertEqual(pb_assets[0].source_name, "PB-SHABD / Prasar Bharati")
        self.assertEqual(pib_assets[0].source_name, "Press Information Bureau India")

    def test_green_official_ranks_above_yellow_social_and_stock(self) -> None:
        segment = StorySegment("seg_01", "FLOOD RESPONSE", "official flood response footage", 0, 10, ["flood", "response"])
        query = VisualQuery("seg_01", "flood response", ["flood", "response"], [AssetType.VIDEO, AssetType.IMAGE], 0, 10)
        official = normalize_asset_metadata(
            VisualAsset(
                "official",
                AssetType.VIDEO,
                "Flood response footage",
                "dvids",
                path="media/flood.mp4",
                source_name="DVIDS",
                license="public domain",
                usage_note="public domain government work",
                safe_to_use=True,
            )
        )
        social = normalize_asset_metadata(
            VisualAsset(
                "social",
                AssetType.VIDEO,
                "Flood response footage",
                "social_reference_ingest",
                path="media/social.mp4",
                source_name="TikTok",
                safe_to_use=True,
                rights_tier="yellow",
                manual_review_status="required",
            )
        )
        stock = normalize_asset_metadata(
            VisualAsset(
                "stock",
                AssetType.VIDEO,
                "Flood water",
                "pexels",
                remote_url="https://example.com/stock.mp4",
                source_name="Pexels",
                license="Pexels License",
                safe_to_use=True,
            )
        )

        ranked = rank_assets_for_segment([stock, social, official], segment, query)

        self.assertEqual(ranked[0].asset_id, "official")
        ranked_scores = {asset.asset_id: asset.relevance_score for asset in ranked}
        self.assertLess(ranked_scores["stock"], ranked_scores["official"])

    def test_yellow_social_requires_flag_and_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "social.mp4"
            media.write_bytes(b"fake")
            provider = SocialReferenceIngestProvider(root)
            assets, _ = provider.search(
                manifest={
                    "story_id": "story_001",
                    "raw": {
                        "approved_social_media": [
                            {
                                "path": str(media),
                                "manual_review_status": "approved",
                                "creator": "@source",
                                "source_url": "https://www.tiktok.com/@source/video/1",
                            }
                        ]
                    },
                },
                story_json_path=root / "story.json",
                segments=[],
                queries=[],
            )

        social = normalize_asset_metadata(assets[0])
        self.assertEqual(social.rights_tier, "yellow")
        self.assertFalse(asset_is_selectable(social))
        with patch.dict("os.environ", {"SYNTHPOST_ALLOW_RISKY_SOCIAL": "1"}):
            normalize_asset_metadata(social)
            self.assertTrue(asset_is_selectable(social))

    def test_still_visuals_get_motion_and_cc_assets_get_attribution(self) -> None:
        commons = normalize_asset_metadata(
            VisualAsset(
                "commons",
                AssetType.IMAGE,
                "Parliament building",
                "wikimedia",
                remote_url="https://example.com/image.jpg",
                source_name="Wikimedia Commons",
                license="CC BY-SA 4.0",
                attribution="Example Author",
                safe_to_use=True,
            )
        )

        self.assertTrue(commons.attribution_required)
        self.assertIn("Example Author", commons.attribution_text or "")
        self.assertEqual(commons.motion["preset"], "push_in")

    def test_visual_candidate_record_contains_pr8_contract_fields(self) -> None:
        asset = normalize_asset_metadata(
            VisualAsset(
                "dvids_briefing",
                AssetType.VIDEO,
                "Nvidia AI chip briefing footage",
                "dvids",
                path="media/briefing.mp4",
                source_url="https://www.dvidshub.net/video/123/ai-chip-briefing",
                source_name="DVIDS",
                license="public domain",
                usage_note="public domain government work",
                attribution="U.S. Air Force",
                safe_to_use=True,
                entities=["Nvidia", "AI chips"],
            )
        )
        segment = StorySegment("seg_01", "AI chip controls", "Nvidia AI chip export controls", 0, 8, ["Nvidia", "AI chips"])
        query = VisualQuery("seg_01", "Nvidia AI chips", ["Nvidia", "AI chips"], [AssetType.VIDEO], 0, 8)

        ranked = rank_assets_for_segment([asset], segment, query)[0]
        record = ranked.to_record()

        self.assertEqual(record["id"], "dvids_briefing")
        self.assertEqual(record["provider_type"], "official")
        self.assertEqual(record["source_domain"], "dvidshub.net")
        self.assertEqual(record["asset_url"], "media/briefing.mp4")
        self.assertEqual(record["rights_category"], "public_domain")
        self.assertFalse(record["needs_manual_review"])
        self.assertIn("nvidia", record["matched_story_entities"])
        self.assertIn("score=", record["relevance_reason"])

    def test_unknown_rights_are_flagged_and_not_selectable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "unknown.jpg"
            media.write_bytes(b"fake")
            asset = normalize_asset_metadata(
                VisualAsset(
                    "unknown",
                    AssetType.IMAGE,
                    "Unverified event image",
                    "unknown_web_source",
                    path=str(media),
                    source_name="Unknown Web Source",
                    safe_to_use=True,
                )
            )
            warnings = validate_asset(asset, project_root=root)

        self.assertFalse(asset.safe_to_use)
        self.assertEqual(asset.rights_category, "unknown_or_rejected")
        self.assertTrue(asset.needs_manual_review)
        self.assertFalse(asset_is_selectable(asset))
        self.assertTrue(any("unknown or rejected rights" in warning for warning in warnings))

    def test_global_ranker_rejects_logos_and_generic_space_for_non_space_story(self) -> None:
        segment = StorySegment("seg_01", "Flood response", "official flood response", 0, 10, ["flood", "response"])
        query = VisualQuery("seg_01", "flood response", ["flood", "response"], [AssetType.IMAGE], 0, 10)
        logo = normalize_asset_metadata(
            VisualAsset(
                "logo",
                AssetType.IMAGE,
                "NASA logo",
                "nasa_media",
                path="media/nasa_logo.png",
                source_name="NASA",
                license="public domain",
                usage_note="public domain government work",
                safe_to_use=True,
            )
        )
        stars = normalize_asset_metadata(
            VisualAsset(
                "stars",
                AssetType.IMAGE,
                "Generic stars image",
                "nasa_media",
                path="media/stars.jpg",
                source_name="NASA",
                license="public domain",
                usage_note="public domain government work",
                safe_to_use=True,
            )
        )

        ranked = {asset.asset_id: asset for asset in rank_assets_for_segment([logo, stars], segment, query)}

        self.assertEqual(ranked["logo"].selection_status, "rejected")
        self.assertIn("publisher_logo_rejected", ranked["logo"].rejection_reasons)
        self.assertEqual(ranked["stars"].selection_status, "rejected")
        self.assertIn("generic_space_media_rejected_for_non_space_story", ranked["stars"].rejection_reasons)

    def test_generic_space_media_is_allowed_for_relevant_space_story(self) -> None:
        segment = StorySegment(
            "seg_01",
            "Space telescope maps galaxy stars",
            "A space telescope released new galaxy and stars imagery.",
            0,
            10,
            ["space", "telescope", "galaxy", "stars"],
        )
        query = VisualQuery(
            "seg_01",
            "space telescope galaxy stars",
            ["space", "telescope", "galaxy", "stars"],
            [AssetType.IMAGE],
            0,
            10,
        )
        stars = normalize_asset_metadata(
            VisualAsset(
                "stars",
                AssetType.IMAGE,
                "Galaxy stars from space telescope",
                "nasa_media",
                path="media/stars.jpg",
                source_name="NASA",
                license="public domain",
                usage_note="public domain government work",
                safe_to_use=True,
            )
        )

        ranked = rank_assets_for_segment([stars], segment, query)[0]

        self.assertNotEqual(ranked.selection_status, "rejected")
        self.assertNotIn("generic_space_media_rejected_for_non_space_story", ranked.rejection_reasons)
        self.assertGreater(ranked.relevance_score, 0)

    def test_unrelated_official_visual_is_rejected(self) -> None:
        segment = StorySegment("seg_01", "Flood response", "official flood response", 0, 10, ["flood", "response"])
        query = VisualQuery("seg_01", "flood response", ["flood", "response"], [AssetType.IMAGE], 0, 10)
        unrelated = normalize_asset_metadata(
            VisualAsset(
                "unrelated",
                AssetType.IMAGE,
                "Stock exchange factory update",
                "dvids",
                path="media/stock_exchange_factory.jpg",
                source_name="DVIDS",
                license="public domain",
                usage_note="public domain government work",
                safe_to_use=True,
            )
        )

        ranked = rank_assets_for_segment([unrelated], segment, query)[0]

        self.assertEqual(ranked.selection_status, "rejected")
        self.assertIn("unrelated_to_current_story", ranked.rejection_reasons)
        self.assertEqual(ranked.relevance_score, 0)

    def test_entity_matching_visual_candidates_outrank_generic_visuals(self) -> None:
        segment = StorySegment("seg_01", "Nvidia export controls", "Nvidia AI chip controls", 0, 10, ["Nvidia", "AI chips"])
        query = VisualQuery("seg_01", "Nvidia AI chips", ["Nvidia", "AI chips"], [AssetType.VIDEO, AssetType.IMAGE], 0, 10)
        matched = normalize_asset_metadata(
            VisualAsset(
                "matched",
                AssetType.IMAGE,
                "Nvidia AI chip data center",
                "manifest_media",
                path="media/nvidia.jpg",
                source_name="Official media",
                license="user provided",
                usage_note="user provided",
                safe_to_use=True,
                entities=["Nvidia", "AI chips"],
            )
        )
        generic = normalize_asset_metadata(
            VisualAsset(
                "generic",
                AssetType.IMAGE,
                "Generic office building",
                "pexels",
                remote_url="https://example.com/office.jpg",
                source_name="Pexels",
                license="Pexels License",
                usage_note="stock fallback",
                safe_to_use=True,
            )
        )

        ranked = rank_assets_for_segment([generic, matched], segment, query)

        self.assertEqual(ranked[0].asset_id, "matched")
        self.assertGreater(ranked[0].relevance_score, ranked[1].relevance_score)

    def test_generated_context_graphics_fill_story_specific_visuals_by_default(self) -> None:
        manifest = {
            "story_id": "story_001",
            "episode_id": "ep_test",
            "raw": {
                "headline_source": "Grid operators face new power rules",
                "summary": "A regulator is changing the process for large electricity users.",
                "source_url": "https://example.gov/news",
                "source_name": "Example Agency",
                "category": "energy",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "text": "Operators must file revised tariffs within thirty days.",
                        "source_ids": ["source_01"],
                    },
                    {
                        "claim_id": "claim_02",
                        "text": "Large data centers are part of the load growth pressure.",
                        "source_ids": ["source_01"],
                    },
                ],
            },
            "script": {
                "headline": "GRID RULES",
                "category": "ENERGY",
                "text": "Grid operators face new filing requirements. Data centers are increasing power demand.",
            },
            "direction": {"estimated_duration_seconds": 24},
            "composition": {},
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {"SYNTHPOST_ENABLE_CONTEXT_GRAPHICS": "auto", "SYNTHPOST_VISUAL_MIN_SEGMENTS": "2"},
        ):
            root = Path(temp_dir)
            (root / "pipeline").mkdir()
            (root / "compositor").mkdir()
            story_path = root / "episodes" / "ep_test" / "stories" / "story_001" / "story.json"
            story_path.parent.mkdir(parents=True)
            story_path.write_text("{}", encoding="utf-8")

            plan = build_visual_plan(manifest, story_path, providers=[ScreenshotProvider(root)])

        self.assertEqual(len(plan.manifest_visuals), len(plan.segments))
        self.assertTrue(all(visual["provider"] == "screenshot_provider" for visual in plan.manifest_visuals))
        self.assertTrue(any(visual["asset_type"] == "document" for visual in plan.manifest_visuals))
        self.assertTrue(all(visual["safe_to_use"] for visual in plan.manifest_visuals))
        self.assertTrue(all(visual["rights_tier"] == "green" for visual in plan.manifest_visuals))
        self.assertTrue(all(visual["rights_category"] == "first_party_generated" for visual in plan.manifest_visuals))

    def test_visual_candidates_audit_file_is_written_with_statuses_and_manual_review_flags(self) -> None:
        manifest = {
            "story_id": "story_001",
            "episode_id": "ep_test",
            "raw": {
                "headline_source": "Nvidia export controls reshape AI chip supply",
                "summary": "Nvidia AI chip controls could affect data center supply chains.",
                "source_url": "https://example.gov/news",
                "source_name": "Example Agency",
                "category": "ai",
                "facts": ["Nvidia AI chip controls could affect data center supply chains."],
                "handoff": {
                    "visuals": {
                        "entities": ["Nvidia", "AI chips"],
                        "visual_opportunities": ["Official Nvidia briefing footage"],
                        "source_metadata": {"source_domain": "example.gov"},
                    }
                },
            },
            "script": {
                "headline": "AI CHIP CONTROLS",
                "category": "AI",
                "text": "Nvidia AI chip controls could affect data center supply chains.",
            },
            "direction": {"estimated_duration_seconds": 16},
            "composition": {},
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {"SYNTHPOST_ENABLE_CONTEXT_GRAPHICS": "0", "SYNTHPOST_VISUAL_MIN_SEGMENTS": "1"},
        ):
            root = Path(temp_dir)
            (root / "pipeline").mkdir()
            (root / "compositor").mkdir()
            media = root / "nvidia_briefing.jpg"
            logo = root / "nasa_logo.png"
            unknown = root / "unknown.jpg"
            for path in (media, logo, unknown):
                path.write_bytes(b"fake")
            story_path = root / "episodes" / "ep_test" / "stories" / "story_001" / "story.json"
            story_path.parent.mkdir(parents=True)
            story_path.write_text("{}", encoding="utf-8")
            provider = FixtureVisualProvider(
                "dvids",
                [
                    VisualAsset(
                        "official",
                        AssetType.IMAGE,
                        "Nvidia AI chip briefing",
                        "dvids",
                        path=str(media),
                        source_url="https://www.dvidshub.net/image/1",
                        source_name="DVIDS",
                        license="public domain",
                        usage_note="public domain government work",
                        safe_to_use=True,
                        entities=["Nvidia", "AI chips"],
                    ),
                    VisualAsset(
                        "logo",
                        AssetType.IMAGE,
                        "NASA logo",
                        "dvids",
                        path=str(logo),
                        source_url="https://www.dvidshub.net/image/logo",
                        source_name="DVIDS",
                        license="public domain",
                        usage_note="public domain government work",
                        safe_to_use=True,
                    ),
                    VisualAsset(
                        "unknown",
                        AssetType.IMAGE,
                        "Unverified Nvidia image",
                        "unknown_web_source",
                        path=str(unknown),
                        source_name="Unknown",
                        safe_to_use=True,
                    ),
                ],
            )

            plan = build_visual_plan(manifest, story_path, providers=[provider])
            audit_path = story_path.parent / "visuals" / "visual_candidates.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))

        statuses = {record["id"]: record["selection_status"] for record in audit["candidates"]}
        rejected = {record["id"]: record.get("rejection_reasons", []) for record in audit["candidates"]}
        self.assertEqual(plan.selected_assets[0].asset_id, "official")
        self.assertEqual(statuses["official"], "selected")
        self.assertEqual(statuses["logo"], "rejected")
        self.assertIn("publisher_logo_rejected", rejected["logo"])
        self.assertEqual(statuses["unknown"], "rejected")
        self.assertTrue(audit["manual_review_flags"])
        self.assertEqual(audit["chosen_visuals"][0]["id"], "official")

    def test_visual_reuse_requires_pr8_candidate_metadata(self) -> None:
        old_record = {
            "asset_type": "image",
            "source_name": "Example Agency",
            "license": "public domain",
            "usage_note": "Official media",
            "downloaded_path": "media/example.jpg",
            "relevance_score": 75,
            "safe_to_use": True,
            "rights_tier": "green",
            "rights_confidence": "verified",
            "usage_basis": "public_domain",
            "source_authority": "official",
            "content_role": "evidence",
            "media_type": "photo",
            "risk_level": "low",
            "manual_review_status": "not_required",
        }
        enriched_record = {
            **old_record,
            "provider_type": "official",
            "source_domain": "example.gov",
            "asset_url": "media/example.jpg",
            "rights_category": "public_domain",
            "needs_manual_review": False,
            "selection_status": "selected",
        }

        self.assertFalse(_has_visual_metadata([old_record]))
        self.assertTrue(_has_visual_metadata([enriched_record]))

    def test_source_page_provider_rejects_logos_and_generic_space_media(self) -> None:
        manifest = {
            "story_id": "story_001",
            "raw": {
                "headline_source": "Rising Waters Swamp Lake Naivasha",
                "summary": "Relentless rains are threatening a lake in Kenya's Great Rift Valley.",
                "source_url": "https://science.nasa.gov/earth/earth-observatory/rising-waters-swamp-lake-naivasha/",
                "source_name": "NASA",
                "category": "general",
            },
        }
        provider = SourcePageProvider(ROOT)

        with patch.object(
            provider,
            "_extract_links",
            return_value=[
                (
                    "https://assets.science.nasa.gov/content/dam/science/esd/eo/images/iotd/2026/rising-waters-swamp-lake-naivasha/kenyawater_oli_20260126_th.jpg",
                    "og:image",
                ),
                ("https://science.nasa.gov/wp-content/uploads/2023/10/NASA_logo-1.png", "img"),
                ("https://science.nasa.gov/wp-content/themes/nasa-child/assets/images/nasa-logo@2x.png", "img"),
                (
                    "https://assets.science.nasa.gov/dynamicimage/assets/science/psd/solar-system/skywatching/2026/june/stars.jpg",
                    "img",
                ),
                ("https://www.nasa.gov/wp-content/uploads/2026/06/daphne-concept-artwork-1.jpg", "img"),
            ],
        ):
            assets, report = provider.search(
                manifest=manifest,
                story_json_path=ROOT / "episodes" / "ep" / "stories" / "story_001" / "story.json",
                segments=[],
                queries=[],
            )

        self.assertEqual([asset.asset_id for asset in assets], ["official_source_01_kenyawater_oli_20260126_th"])
        self.assertEqual(report.candidate_count, 1)
        self.assertTrue(any("publisher logo" in warning for warning in report.warnings))
        self.assertTrue(any("generic space" in warning for warning in report.warnings))
        self.assertTrue(any("does not match current story terms" in warning for warning in report.warnings))

    def test_generated_context_svg_wraps_long_titles_for_frame(self) -> None:
        segment = StorySegment(
            "seg_01",
            "THE AMERICAN LIBRARY ASSOCIATION ANNUAL CONFERENCE WILL TAKE PLACE FROM JUNE 25 TO JUNE 29, 2026",
            "The American Library Association annual conference will take place from June 25 to June 29, 2026. NASA will host Hyperwall sessions.",
            0,
            8,
            ["american", "library", "association", "conference", "nasa"],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "context.svg"
            provider = ScreenshotProvider(Path(temp_dir))

            provider._write_context_svg(
                path,
                manifest={"raw": {"source_name": "NASA"}, "script": {"category": "general"}},
                segment=segment,
            )

            svg = path.read_text(encoding="utf-8")

        self.assertIn('font-size="58"', svg)
        self.assertIn("THE AMERICAN LIBRARY", svg)
        self.assertIn("ASSOCIATION ANNUAL", svg)
        self.assertNotIn("THE AMERICAN LIBRARY ASSOCIATION ANNUAL", svg)


if __name__ == "__main__":
    unittest.main()
