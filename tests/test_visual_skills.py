from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthpost.visuals.models import (
    AssetType,
    ProviderReport,
    StorySegment,
    VisualAsset,
    VisualPlanEntry,
    VisualProvider,
    VisualQuery,
)
from synthpost.visuals.planner import build_visual_plan
from synthpost.visuals.providers.screenshot_provider import ScreenshotProvider
from synthpost.visuals.skills import build_visual_skill_specs


class FixtureVisualProvider(VisualProvider):
    def __init__(self, assets: list[VisualAsset], *, name: str = "manifest_media") -> None:
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


def _story_path(root: Path) -> Path:
    story_path = root / "episodes" / "ep_test" / "stories" / "story_001" / "story.json"
    story_path.parent.mkdir(parents=True)
    story_path.write_text("{}", encoding="utf-8")
    return story_path


def _project_root() -> tempfile.TemporaryDirectory[str]:
    temp_dir = tempfile.TemporaryDirectory()
    root = Path(temp_dir.name)
    (root / "pipeline").mkdir()
    (root / "compositor").mkdir()
    return temp_dir


def _media(root: Path, name: str) -> str:
    path = root / name
    path.write_bytes(b"fake")
    return str(path)


class VisualSkillTests(unittest.TestCase):
    def test_global_visual_opportunities_do_not_override_entity_section_skill(self) -> None:
        manifest = {
            "story_id": "story_001",
            "episode_id": "ep_test",
            "raw": {
                "headline_source": "Grid demand affects AI chips",
                "summary": "The plan references 42 gigawatts of demand and an 18 percent reserve margin.",
                "source_url": "https://example.gov/story",
                "source_name": "Example Agency",
                "category": "technology",
                "facts": ["The plan references 42 gigawatts of demand and an 18 percent reserve margin."],
                "handoff": {
                    "visuals": {
                        "entities": ["Nvidia"],
                        "visual_opportunities": ["grid demand chart", "data callout for reserve margin"],
                    }
                },
            },
            "script": {
                "sections": [
                    {
                        "section_id": "why_it_matters",
                        "title": "Nvidia chips in the supply chain",
                        "narration": "Nvidia is one entity in the wider AI chip supply chain.",
                        "claim_ids": ["claim_entity"],
                        "source_notes": ["Example Agency"],
                    }
                ]
            },
        }
        entry = VisualPlanEntry(
            story_id="story_001",
            episode_id="ep_test",
            section_id="why_it_matters",
            section_title="Nvidia chips in the supply chain",
            section_type="why_it_matters",
            visual_role="entity_visual",
            selected_visual_candidate_id="nvidia_entity",
            media_type="image",
            asset_type="image",
            start=0,
            end=10,
            rights_category="official_public",
        )
        asset = VisualAsset(
            "nvidia_entity",
            AssetType.IMAGE,
            "Nvidia AI chip entity visual",
            "manifest_media",
            safe_to_use=True,
            entities=["Nvidia"],
        )

        specs, audit = build_visual_skill_specs(manifest, entries=[entry], selected_assets=[asset])

        self.assertEqual(specs[0].skill_type, "entity_card")
        self.assertEqual(audit["skill_types"], {"entity_card": 1})

    def test_map_and_entity_specs_are_assigned_from_section_context(self) -> None:
        manifest = {
            "story_id": "story_001",
            "episode_id": "ep_test",
            "raw": {
                "headline_source": "India and China expand border surveillance",
                "summary": "India and China are central to the border surveillance story.",
                "source_url": "https://example.gov/border",
                "source_name": "Example Agency",
                "category": "geopolitics",
                "facts": ["India and China are expanding border surveillance systems."],
                "handoff": {
                    "visuals": {
                        "entities": ["India", "China", "Nvidia"],
                        "visual_opportunities": ["map of the India China border", "entity card for Nvidia chips"],
                    }
                },
            },
            "script": {
                "headline": "BORDER SURVEILLANCE",
                "category": "GEOPOLITICS",
                "text": "India and China are expanding border surveillance systems.",
                "target_duration_seconds": 24,
                "sections": [
                    {
                        "section_id": "background_context",
                        "title": "India China border map",
                        "narration": "India and China are central to this border surveillance story.",
                        "estimated_duration_seconds": 12,
                        "claim_ids": ["claim_01"],
                        "source_notes": ["Example Agency"],
                    },
                    {
                        "section_id": "why_it_matters",
                        "title": "Nvidia chips in the surveillance stack",
                        "narration": "Nvidia is one entity in the wider AI chip supply chain.",
                        "estimated_duration_seconds": 12,
                        "claim_ids": ["claim_01"],
                        "source_notes": ["Example Agency"],
                    },
                ],
            },
        }
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            assets = [
                VisualAsset(
                    "border_map",
                    AssetType.MAP,
                    "India China border surveillance map",
                    "official_source_media",
                    path=_media(root, "border_map.png"),
                    source_url="https://example.gov/map",
                    source_name="Example Agency",
                    license="public domain",
                    usage_note="public domain government work",
                    safe_to_use=True,
                    entities=["India", "China"],
                ),
                VisualAsset(
                    "nvidia_entity",
                    AssetType.IMAGE,
                    "Nvidia AI chip entity visual",
                    "manifest_media",
                    path=_media(root, "nvidia.png"),
                    source_url="https://example.gov/nvidia",
                    source_name="Example Agency",
                    license="user provided",
                    usage_note="user provided",
                    safe_to_use=True,
                    entities=["Nvidia"],
                ),
            ]
            story_path = _story_path(root)

            build_visual_plan(manifest, story_path, providers=[FixtureVisualProvider(assets)])
            visual_skills = json.loads((story_path.parent / "visuals" / "visual_skills.json").read_text(encoding="utf-8"))

        by_section = {skill["script_section_id"]: skill for skill in visual_skills["skills"]}
        self.assertEqual(by_section["background_context"]["skill_type"], "map")
        self.assertIn("India", by_section["background_context"]["map_spec"]["location_names"])
        self.assertEqual(by_section["why_it_matters"]["skill_type"], "entity_card")
        self.assertIn("Nvidia", by_section["why_it_matters"]["entity_card_spec"]["entities"])

    def test_dates_and_numbers_produce_timeline_and_chart_specs(self) -> None:
        manifest = {
            "story_id": "story_001",
            "episode_id": "ep_test",
            "raw": {
                "headline_source": "Grid operators face tariff deadline",
                "summary": "Operators face dated milestones and capacity figures.",
                "source_url": "https://example.gov/grid",
                "source_name": "Energy Agency",
                "category": "energy",
                "claims": [
                    {
                        "claim_id": "claim_timeline",
                        "text": "The agency opened the process on June 18 and expects filings by July 30.",
                    },
                    {
                        "claim_id": "claim_numbers",
                        "text": "The plan references 42 gigawatts of demand and an 18 percent reserve margin.",
                    },
                ],
            },
            "script": {
                "headline": "GRID DEADLINE",
                "category": "ENERGY",
                "text": "The agency opened the process on June 18 and expects filings by July 30.",
                "target_duration_seconds": 24,
                "sections": [
                    {
                        "section_id": "main_developments",
                        "title": "Timeline of tariff filings",
                        "narration": "The agency opened the process on June 18 and expects filings by July 30.",
                        "estimated_duration_seconds": 12,
                        "claim_ids": ["claim_timeline"],
                        "source_notes": ["Energy Agency"],
                    },
                    {
                        "section_id": "stakes_consequences",
                        "title": "Grid demand data",
                        "narration": "The plan references 42 gigawatts of demand and an 18 percent reserve margin.",
                        "estimated_duration_seconds": 12,
                        "claim_ids": ["claim_numbers"],
                        "source_notes": ["Energy Agency"],
                    },
                ],
            },
        }
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            assets = [
                VisualAsset(
                    "timeline_visual",
                    AssetType.IMAGE,
                    "Timeline tariff filings June July",
                    "manifest_media",
                    path=_media(root, "timeline.png"),
                    source_url="https://example.gov/timeline",
                    source_name="Energy Agency",
                    license="user provided",
                    usage_note="user provided",
                    safe_to_use=True,
                ),
                VisualAsset(
                    "grid_chart",
                    AssetType.CHART,
                    "Grid demand data chart 42 gigawatts 18 percent",
                    "manifest_media",
                    path=_media(root, "grid_chart.png"),
                    source_url="https://example.gov/chart",
                    source_name="Energy Agency",
                    license="user provided",
                    usage_note="user provided",
                    safe_to_use=True,
                ),
            ]
            story_path = _story_path(root)

            build_visual_plan(manifest, story_path, providers=[FixtureVisualProvider(assets)])
            visual_skills = json.loads((story_path.parent / "visuals" / "visual_skills.json").read_text(encoding="utf-8"))

        by_section = {skill["script_section_id"]: skill for skill in visual_skills["skills"]}
        self.assertEqual(by_section["main_developments"]["skill_type"], "timeline")
        self.assertEqual(len(by_section["main_developments"]["timeline_spec"]["events"]), 2)
        self.assertEqual(by_section["stakes_consequences"]["skill_type"], "chart")
        values = [item["value"] for item in by_section["stakes_consequences"]["chart_spec"]["values"]]
        self.assertIn("42 gigawatts", values)
        self.assertIn("18 percent", values)

    def test_document_and_quote_specs_preserve_source_and_attribution(self) -> None:
        manifest = {
            "story_id": "story_001",
            "episode_id": "ep_test",
            "raw": {
                "headline_source": "Regulator publishes grid order",
                "summary": "A regulator published an order and a quoted statement.",
                "source_url": "https://example.gov/order",
                "source_name": "Energy Agency",
                "category": "energy",
                "claims": [
                    {
                        "claim_id": "claim_doc",
                        "text": "The order says operators must file tariff revisions.",
                    },
                    {
                        "claim_id": "claim_quote",
                        "text": "The agency said \"Reliability remains the central test for this rule.\"",
                    },
                ],
            },
            "script": {
                "headline": "GRID ORDER",
                "category": "ENERGY",
                "text": "The agency published an order and a quote.",
                "target_duration_seconds": 24,
                "sections": [
                    {
                        "section_id": "main_developments",
                        "title": "Regulatory filing document",
                        "narration": "The order says operators must file tariff revisions.",
                        "estimated_duration_seconds": 12,
                        "claim_ids": ["claim_doc"],
                        "source_notes": ["Energy Agency"],
                    },
                    {
                        "section_id": "opposing_views_uncertainty",
                        "title": "Official quote on reliability",
                        "narration": "The agency said reliability remains central.",
                        "estimated_duration_seconds": 12,
                        "claim_ids": ["claim_quote"],
                        "source_notes": ["Energy Agency"],
                    },
                ],
            },
        }
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            assets = [
                VisualAsset(
                    "order_doc",
                    AssetType.DOCUMENT,
                    "Regulatory filing document tariff revisions",
                    "official_source_media",
                    path=_media(root, "order.png"),
                    source_url="https://example.gov/order.pdf",
                    source_name="Energy Agency",
                    license="public domain",
                    usage_note="public domain government work",
                    attribution="Energy Agency",
                    safe_to_use=True,
                ),
                VisualAsset(
                    "quote_visual",
                    AssetType.IMAGE,
                    "Official quote reliability press briefing",
                    "manifest_media",
                    path=_media(root, "quote.jpg"),
                    source_url="https://example.gov/quote",
                    source_name="Energy Agency",
                    license="user provided",
                    usage_note="user provided",
                    attribution="Energy Agency",
                    safe_to_use=True,
                ),
            ]
            story_path = _story_path(root)

            build_visual_plan(manifest, story_path, providers=[FixtureVisualProvider(assets)])
            visual_skills = json.loads((story_path.parent / "visuals" / "visual_skills.json").read_text(encoding="utf-8"))

        by_section = {skill["script_section_id"]: skill for skill in visual_skills["skills"]}
        self.assertEqual(by_section["main_developments"]["skill_type"], "document_callout")
        self.assertEqual(by_section["main_developments"]["document_callout_spec"]["source_url"], "https://example.gov/order.pdf")
        self.assertIn("Source: Energy Agency", by_section["main_developments"]["attribution_text"])
        self.assertEqual(by_section["opposing_views_uncertainty"]["skill_type"], "quote_card")
        self.assertIn("Reliability remains", by_section["opposing_views_uncertainty"]["quote_card_spec"]["quote_text"])

    def test_unsupported_numbers_dates_and_quotes_fall_back_without_invention(self) -> None:
        manifest = {
            "story_id": "story_001",
            "episode_id": "ep_test",
            "raw": {
                "headline_source": "Agency issues nonnumeric update",
                "summary": "The source text contains no quotes, no dates, and no numeric values.",
                "source_url": "https://example.gov/update",
                "source_name": "Example Agency",
                "category": "energy",
            },
            "script": {
                "headline": "AGENCY UPDATE",
                "category": "ENERGY",
                "text": "The agency issued a nonnumeric update.",
                "target_duration_seconds": 24,
                "sections": [
                    {
                        "section_id": "stakes_consequences",
                        "title": "Data callout requested",
                        "narration": "The source text contains no numeric values.",
                        "estimated_duration_seconds": 12,
                        "claim_ids": ["claim_missing"],
                        "source_notes": ["Example Agency"],
                    },
                    {
                        "section_id": "opposing_views_uncertainty",
                        "title": "Official quote requested",
                        "narration": "The source text contains no quotes.",
                        "estimated_duration_seconds": 12,
                        "claim_ids": ["claim_missing"],
                        "source_notes": ["Example Agency"],
                    },
                ],
            },
        }
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            assets = [
                VisualAsset(
                    "empty_chart",
                    AssetType.CHART,
                    "Data callout requested chart",
                    "manifest_media",
                    path=_media(root, "chart.png"),
                    source_url="https://example.gov/chart",
                    source_name="Example Agency",
                    license="user provided",
                    usage_note="user provided",
                    safe_to_use=True,
                ),
                VisualAsset(
                    "empty_quote",
                    AssetType.IMAGE,
                    "Official quote requested briefing",
                    "manifest_media",
                    path=_media(root, "quote.png"),
                    source_url="https://example.gov/quote",
                    source_name="Example Agency",
                    license="user provided",
                    usage_note="user provided",
                    safe_to_use=True,
                ),
            ]
            story_path = _story_path(root)

            build_visual_plan(manifest, story_path, providers=[FixtureVisualProvider(assets)])
            visual_skills = json.loads((story_path.parent / "visuals" / "visual_skills.json").read_text(encoding="utf-8"))

        by_section = {skill["script_section_id"]: skill for skill in visual_skills["skills"]}
        self.assertEqual(by_section["stakes_consequences"]["skill_type"], "context_card")
        self.assertIn("data_callout_unsupported_no_grounded_number", by_section["stakes_consequences"]["warnings"])
        self.assertEqual(by_section["opposing_views_uncertainty"]["skill_type"], "context_card")
        self.assertIn("quote_card_unsupported_no_grounded_quote", by_section["opposing_views_uncertainty"]["warnings"])
        self.assertTrue(visual_skills["audit"]["unsupported_skill_warnings"])

    def test_generated_context_cards_are_first_party_skill_specs_and_legacy_safe(self) -> None:
        manifest = {
            "story_id": "story_001",
            "episode_id": "ep_test",
            "raw": {
                "headline_source": "Grid operators face new power rules",
                "summary": "A regulator is changing the process for large electricity users.",
                "source_url": "https://example.gov/news",
                "source_name": "Example Agency",
                "category": "energy",
                "facts": ["Operators must file revised tariffs within thirty days."],
            },
            "script": {
                "headline": "GRID RULES",
                "category": "ENERGY",
                "text": "Grid operators face new filing requirements.",
            },
            "direction": {"estimated_duration_seconds": 12},
            "composition": {},
        }
        with _project_root() as temp_dir, patch.dict(
            "os.environ",
            {"SYNTHPOST_ENABLE_CONTEXT_GRAPHICS": "auto", "SYNTHPOST_VISUAL_MIN_SEGMENTS": "2"},
        ):
            root = Path(temp_dir)
            story_path = _story_path(root)

            plan = build_visual_plan(manifest, story_path, providers=[ScreenshotProvider(root)])
            visual_plan = json.loads((story_path.parent / "visuals" / "visual_plan.json").read_text(encoding="utf-8"))
            visual_skills = json.loads((story_path.parent / "visuals" / "visual_skills.json").read_text(encoding="utf-8"))

        self.assertEqual(len(plan.manifest_visuals), len(visual_skills["skills"]))
        self.assertTrue(all(section["visual_skill"]["skill_type"] == "context_card" for section in visual_plan["sections"]))
        self.assertTrue(all(skill["rights_category"] == "first_party_generated" for skill in visual_skills["skills"]))
        self.assertTrue(all(skill["context_card_spec"]["rights_category"] == "first_party_generated" for skill in visual_skills["skills"]))


if __name__ == "__main__":
    unittest.main()
