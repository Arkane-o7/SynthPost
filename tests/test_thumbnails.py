from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthpost.thumbnails.headlines import word_count
from synthpost.thumbnails.assets import resolve_brief_assets, write_resolved_brief_record
from synthpost.thumbnails.planner import plan_concepts
from synthpost.thumbnails.schema import load_brief
from synthpost.thumbnails.scoring import score_concept
from pipeline.storage import read_manifest
from pipeline.thumbnails import build_brief


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


if __name__ == "__main__":
    unittest.main()
