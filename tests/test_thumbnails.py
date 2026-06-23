from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthpost.thumbnails.headlines import word_count
from synthpost.thumbnails.assets import resolve_brief_assets, write_resolved_brief_record
from synthpost.thumbnails.planner import plan_concepts
from synthpost.thumbnails.schema import load_brief
from synthpost.thumbnails.scoring import score_concept
from pipeline.storage import read_manifest
from pipeline.thumbnails import build_brief, thumbnail_visual_candidate_report


class ThumbnailGeneratorTests(unittest.TestCase):
    def test_sample_brief_validates_and_plans_three_concepts(self) -> None:
        brief = load_brief(ROOT / "episodes" / "template-previews" / "thumbnail_brief.json")

        concepts = plan_concepts(brief)

        self.assertEqual(len(concepts), 3)
        self.assertEqual(concepts[0].template_id, "authority_warning")
        self.assertTrue(all(word_count(concept.headline_text) <= 6 for concept in concepts))
        self.assertTrue(any(concept.template_id == "money_deal_bomb" for concept in concepts))

    def test_scoring_rejects_overlong_thumbnail_text(self) -> None:
        brief = load_brief(ROOT / "episodes" / "template-previews" / "thumbnail_brief.json")
        concept = plan_concepts(brief, count=1)[0]
        concept.headline_text = "THIS THUMBNAIL TEXT IS FAR TOO LONG TO READ"

        scored = score_concept(concept)

        self.assertLess(scored.score or 0, 80)
        self.assertTrue(any("exceeds 6 words" in warning for warning in scored.warnings))

    def test_plan_command_writes_concepts_shape(self) -> None:
        brief = load_brief(ROOT / "episodes" / "template-previews" / "thumbnail_brief.json")
        concepts = plan_concepts(brief, count=2)

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            for concept in concepts:
                record = concept.to_renderer_record()
                self.assertIn("templateId", record)
                self.assertIn("headlineText", record)
                self.assertIn("mainSubjects", record)
                self.assertIsInstance(record["assets"], list)

    def test_auto_asset_selection_adds_matching_generated_asset(self) -> None:
        brief = load_brief(ROOT / "episodes" / "topic-showcase" / "ai_energy_grid_brief.json")
        brief.assets = []

        resolved, selected = resolve_brief_assets(brief)

        self.assertTrue(selected)
        self.assertTrue(any("energy" in match.asset.id for match in selected))
        self.assertTrue(any(asset.type == "hero_composite" for asset in resolved.assets))

    def test_resolved_brief_remains_schema_valid(self) -> None:
        brief = load_brief(ROOT / "episodes" / "topic-showcase" / "ai_energy_grid_brief.json")
        brief.assets = []
        resolved, selected = resolve_brief_assets(brief)

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "thumbnail_brief_resolved.json"
            write_resolved_brief_record(resolved, output, selected=selected)
            loaded = load_brief(output)

        self.assertEqual(loaded.topic, "energy")
        self.assertTrue(loaded.assets)

    def test_pipeline_story_manifest_builds_thumbnail_brief(self) -> None:
        manifest = read_manifest(ROOT / "episodes" / "ep_2026-06-21-ferc-grid" / "stories" / "story_001" / "story.json")

        brief = build_brief(manifest)

        self.assertEqual(brief.topic, "energy")
        self.assertTrue(any(subject.name == "data center" for subject in brief.main_subjects))
        self.assertIn("clean_market_surge", brief.render_preferences["preferred_templates"])

    def test_lake_naivasha_story_rejects_ai_logo_and_star_thumbnail_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            lake = temp / "kenyawater_oli_20260126_th.jpg"
            logo = temp / "nasa-logo_2x.png"
            stars = temp / "55129740863_8d1388b2d2_o.jpg"
            Image.new("RGB", (1280, 720), "#224466").save(lake)
            Image.new("RGB", (220, 120), "#ffffff").save(logo)
            Image.new("RGB", (1024, 768), "#050515").save(stars)

            manifest = {
                "episode_id": "ep_lake_naivasha",
                "story_id": "story_001",
                "raw": {
                    "headline_source": "Rising Waters Swamp Lake Naivasha",
                    "summary": "Relentless rains are threatening a lake in Kenya's Great Rift Valley.",
                    "source_url": "https://science.nasa.gov/earth/earth-observatory/rising-waters-swamp-lake-naivasha/",
                    "source_name": "NASA",
                    "category": "general",
                    "facts": ["Relentless rains are threatening Lake Naivasha in Kenya."],
                },
                "script": {
                    "headline": "RISING WATERS SWAMP LAKE NAIVASHA",
                    "text": "Relentless rains are threatening Lake Naivasha in Kenya.",
                    "category": "general",
                },
                "visuals": [
                    {
                        "asset_id": "official_source_01_lake",
                        "path": str(lake),
                        "title": "Rising Waters Swamp Lake Naivasha",
                        "source_url": "https://science.nasa.gov/earth/earth-observatory/rising-waters-swamp-lake-naivasha/",
                        "source_name": "NASA",
                        "safe_to_use": True,
                    },
                    {
                        "asset_id": "official_source_03_nasa-logo_2x",
                        "path": str(logo),
                        "title": "Rising Waters Swamp Lake Naivasha",
                        "source_url": "https://science.nasa.gov/earth/earth-observatory/rising-waters-swamp-lake-naivasha/",
                        "source_name": "NASA",
                        "safe_to_use": True,
                    },
                    {
                        "asset_id": "official_source_05_stars",
                        "path": str(stars),
                        "title": "Rising Waters Swamp Lake Naivasha",
                        "source_url": "https://science.nasa.gov/earth/earth-observatory/rising-waters-swamp-lake-naivasha/",
                        "source_name": "NASA",
                        "safe_to_use": True,
                    },
                ],
                "visual_assets": [
                    {
                        "asset_id": "official_source_01_lake",
                        "provider": "official_source_media",
                        "path": str(lake),
                        "remote_url": "https://assets.science.nasa.gov/earth-observatory/kenyawater_oli_20260126_th.jpg",
                        "source_page_role": "og:image",
                        "title": "Rising Waters Swamp Lake Naivasha",
                        "source_url": "https://science.nasa.gov/earth/earth-observatory/rising-waters-swamp-lake-naivasha/",
                        "source_name": "NASA",
                        "safe_to_use": True,
                        "keywords": ["rising", "waters", "swamp", "lake", "naivasha"],
                    },
                    {
                        "asset_id": "official_source_03_nasa-logo_2x",
                        "provider": "official_source_media",
                        "path": str(logo),
                        "remote_url": "https://science.nasa.gov/wp-content/themes/nasa-child/assets/images/nasa-logo@2x.png",
                        "source_page_role": "img",
                        "title": "Rising Waters Swamp Lake Naivasha",
                        "source_url": "https://science.nasa.gov/earth/earth-observatory/rising-waters-swamp-lake-naivasha/",
                        "source_name": "NASA",
                        "safe_to_use": True,
                        "keywords": ["rising", "waters", "swamp", "lake", "naivasha"],
                    },
                    {
                        "asset_id": "official_source_05_stars",
                        "provider": "official_source_media",
                        "path": str(stars),
                        "remote_url": "https://assets.science.nasa.gov/dynamicimage/assets/science/psd/solar-system/skywatching/2026/june/stars.jpg",
                        "source_page_role": "img",
                        "title": "Rising Waters Swamp Lake Naivasha",
                        "source_url": "https://science.nasa.gov/earth/earth-observatory/rising-waters-swamp-lake-naivasha/",
                        "source_name": "NASA",
                        "safe_to_use": True,
                        "keywords": ["rising", "waters", "swamp", "lake", "naivasha"],
                    },
                ],
            }

            brief = build_brief(manifest)
            resolved, selected_library = resolve_brief_assets(brief)
            report = thumbnail_visual_candidate_report(manifest, brief=resolved, selected_library_assets=selected_library)

        self.assertEqual(brief.topic, "science")
        self.assertTrue(any(subject.name == "Lake Naivasha" for subject in brief.main_subjects))
        self.assertFalse(any(subject.name == "AI model" for subject in brief.main_subjects))
        self.assertNotIn("logo_collision", [concept.template_id for concept in plan_concepts(brief, count=3)])
        self.assertEqual([asset.path_or_url for asset in brief.assets], [str(lake)])
        self.assertFalse(selected_library)
        self.assertFalse(any("nvidia" in asset.id.lower() or "ai_energy" in asset.id.lower() for asset in resolved.assets))

        candidates = {candidate["asset_id"]: candidate for candidate in report["candidates"]}
        self.assertTrue(candidates["official_source_01_lake"]["accepted"])
        self.assertIn("publisher logo", candidates["official_source_03_nasa-logo_2x"]["reject_reason"])
        self.assertIn("generic space", candidates["official_source_05_stars"]["reject_reason"])

    def test_hyperwall_schedule_thumbnail_uses_short_story_specific_fallback_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            context_svg = Path(temp_dir) / "seg_01_source_context.svg"
            context_svg.write_text("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1600\" height=\"900\"/>", encoding="utf-8")
            manifest = {
                "episode_id": "ep_hyperwall",
                "story_id": "story_001",
                "raw": {
                    "headline_source": "2026 ALA Hyperwall Schedule",
                    "summary": "American Library Association annual conference schedule for NASA Hyperwall storytelling sessions.",
                    "source_url": "https://science.nasa.gov/earth/2026-ala-hyperwall-schedule/",
                    "source_name": "NASA",
                    "category": "general",
                    "facts": [
                        "American Library Association (ALA) Annual Conference, June 25-29, 2026. Join NASA in the Exhibit Hall (Booth #2243) for Hyperwall Storytelling by NASA experts. Full Hyperwall Agenda below."
                    ],
                },
                "script": {
                    "headline": "2026 ALA Hyperwall Schedule",
                    "text": "NASA announced Hyperwall storytelling sessions for the ALA Annual Conference.",
                    "category": "general",
                },
                "visuals": [
                    {
                        "asset_id": "generated_story_001_seg_01",
                        "provider": "screenshot_provider",
                        "asset_type": "generated",
                        "visual_role": "context_graphic",
                        "path": str(context_svg),
                        "title": "2026 ALA Hyperwall Schedule context graphic",
                        "safe_to_use": True,
                    }
                ],
                "visual_assets": [],
            }

            brief = build_brief(manifest)
            concepts = plan_concepts(brief, count=3)
            report = thumbnail_visual_candidate_report(manifest, brief=brief, selected_library_assets=[])

        self.assertEqual(brief.topic, "science")
        self.assertEqual(brief.stakes, "NASA Hyperwall schedule at ALA 2026.")
        self.assertIn("hyperwall at ala", brief.approved_thumbnail_text)
        self.assertFalse(brief.assets)
        self.assertFalse(any(concept.headline_text == "WHAT WATCH" for concept in concepts))
        self.assertTrue(all((concept.subtitle_text is None or len(concept.subtitle_text) <= 78) for concept in concepts))
        generated = {candidate["asset_id"]: candidate for candidate in report["candidates"]}["generated_story_001_seg_01"]
        self.assertFalse(generated["accepted"])
        self.assertIn("generated context graphic", generated["reject_reason"])


if __name__ == "__main__":
    unittest.main()
