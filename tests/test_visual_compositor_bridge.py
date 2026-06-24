from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.manifest_summary import summarize_episode
from pipeline.storage import write_manifest
from synthpost.visuals.compositor_bridge import (
    SUPPORTED_SKILL_TYPES,
    apply_compositor_bridge,
    bridge_validation_errors,
    build_compositor_bridge,
    skill_placeholder,
)


def _project_root() -> tempfile.TemporaryDirectory[str]:
    temp_dir = tempfile.TemporaryDirectory()
    root = Path(temp_dir.name)
    (root / "pipeline").mkdir()
    (root / "compositor").mkdir()
    return temp_dir


def _story_path(root: Path) -> Path:
    story_path = root / "episodes" / "ep_test" / "stories" / "story_001" / "story.json"
    story_path.parent.mkdir(parents=True)
    return story_path


def _write_visual_audits(story_path: Path, *, rights_category: str = "public_domain", manual_review: bool = False) -> None:
    visual_dir = story_path.parent / "visuals"
    visual_dir.mkdir(parents=True)
    candidate = {
        "id": "plan_asset",
        "asset_id": "plan_asset",
        "asset_type": "image",
        "provider": "manifest_media",
        "provider_type": "local_library",
        "path": "media/plan.png",
        "asset_url": "media/plan.png",
        "source_url": "https://example.gov/media",
        "source_domain": "example.gov",
        "source_name": "Example Agency",
        "license": "public domain",
        "attribution_text": "Source: Example Agency",
        "attribution_required": True,
        "rights_tier": "green" if rights_category != "fair_use_review_required" else "yellow",
        "rights_confidence": "verified",
        "usage_basis": "public_domain",
        "rights_category": rights_category,
        "manual_review_status": "required" if manual_review else "not_required",
        "needs_manual_review": manual_review,
        "safe_to_use": not manual_review and rights_category != "unknown_or_rejected",
        "selection_status": "selected",
        "motion": {"preset": "push_in"},
    }
    skill = {
        "skill_id": "main_developments_map",
        "story_id": "story_001",
        "episode_id": "ep_test",
        "script_section_id": "main_developments",
        "selected_visual_candidate_id": "plan_asset",
        "skill_type": "map",
        "skill_reason": "location evidence",
        "spec": {"location_names": ["India"], "labels": ["India"], "source_claim_ids": ["claim_01"]},
        "map_spec": {"location_names": ["India"], "labels": ["India"], "source_claim_ids": ["claim_01"]},
        "evidence_claim_ids": ["claim_01"],
        "source_notes": ["Example Agency"],
        "source_url": "https://example.gov/media",
        "source_domain": "example.gov",
        "rights_category": rights_category,
        "attribution_text": "Source: Example Agency",
        "needs_manual_review": manual_review,
        "render_ready": True,
    }
    section = {
        "story_id": "story_001",
        "episode_id": "ep_test",
        "script_section_id": "main_developments",
        "section_title": "India map",
        "section_type": "main_developments",
        "visual_role": "location_visual",
        "selected_visual_candidate_id": "plan_asset",
        "media_type": "map",
        "asset_type": "image",
        "asset_url": "media/plan.png",
        "path": "media/plan.png",
        "source_url": "https://example.gov/media",
        "source_domain": "example.gov",
        "rights_category": rights_category,
        "attribution_text": "Source: Example Agency",
        "start": 0,
        "end": 8,
        "display_duration_seconds": 8,
        "fallback_status": "none",
        "needs_manual_review": manual_review,
        "manual_review_flag": manual_review,
        "visual_skill": skill,
    }
    (visual_dir / "visual_candidates.json").write_text(
        json.dumps(
            {
                "story_id": "story_001",
                "episode_id": "ep_test",
                "chosen_visuals": [candidate],
                "candidates": [candidate],
            }
        ),
        encoding="utf-8",
    )
    (visual_dir / "visual_plan.json").write_text(
        json.dumps(
            {
                "story_id": "story_001",
                "episode_id": "ep_test",
                "sections": [section],
                "skills": [skill],
                "audit": {"fallback_count": 0, "missing_visual_coverage_warnings": []},
                "visual_candidates_path": "episodes/ep_test/stories/story_001/visuals/visual_candidates.json",
                "visual_skills_path": "episodes/ep_test/stories/story_001/visuals/visual_skills.json",
            }
        ),
        encoding="utf-8",
    )
    (visual_dir / "visual_skills.json").write_text(
        json.dumps(
            {
                "story_id": "story_001",
                "episode_id": "ep_test",
                "skill_count": 1,
                "skills": [skill],
                "audit": {"skill_types": {"map": 1}, "warnings": []},
                "visual_plan_path": "episodes/ep_test/stories/story_001/visuals/visual_plan.json",
                "visual_candidates_path": "episodes/ep_test/stories/story_001/visuals/visual_candidates.json",
            }
        ),
        encoding="utf-8",
    )


class VisualCompositorBridgeTests(unittest.TestCase):
    def test_compositor_input_prefers_visual_plan_over_legacy_visuals(self) -> None:
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            story_path = _story_path(root)
            _write_visual_audits(story_path)
            manifest = {
                "story_id": "story_001",
                "episode_id": "ep_test",
                "visuals": [
                    {"path": "media/legacy.png", "start": 0, "end": 8, "sourceLabel": "LEGACY"},
                ],
                "visual_assets": [],
                "visual_plan": {
                    "audit_paths": {
                        "visual_plan": "episodes/ep_test/stories/story_001/visuals/visual_plan.json",
                        "visual_candidates": "episodes/ep_test/stories/story_001/visuals/visual_candidates.json",
                        "visual_skills": "episodes/ep_test/stories/story_001/visuals/visual_skills.json",
                    }
                },
            }

            records, summary = build_compositor_bridge(manifest, story_path)

        self.assertEqual(summary["input_source"], "visual_plan")
        self.assertEqual(records[0]["candidate_id"], "plan_asset")
        self.assertEqual(records[0]["visual_skill_type"], "map")
        self.assertEqual(records[0]["skill_placeholder"]["type"], "map")
        self.assertEqual(records[0]["attribution_text"], "Source: Example Agency")
        self.assertEqual(records[0]["rights_category"], "public_domain")

    def test_legacy_visuals_still_work_without_visual_plan(self) -> None:
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            story_path = _story_path(root)
            manifest = {
                "story_id": "story_001",
                "episode_id": "ep_test",
                "visuals": [{"path": "media/legacy.png", "start": 0, "end": 5, "sourceLabel": "LEGACY"}],
            }

            records, summary = build_compositor_bridge(manifest, story_path)

        self.assertEqual(summary["input_source"], "legacy_visuals")
        self.assertEqual(records[0]["input_source"], "legacy_visuals")
        self.assertEqual(records[0]["render_safety_status"], "legacy_unverified")
        self.assertIn("missing_rights_category", " ".join(records[0]["warnings"]))

    def test_manual_review_and_unsafe_rights_are_not_silently_rendered(self) -> None:
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            story_path = _story_path(root)
            _write_visual_audits(story_path, rights_category="fair_use_review_required", manual_review=True)
            manifest = {
                "story_id": "story_001",
                "episode_id": "ep_test",
                "visual_plan": {
                    "audit_paths": {
                        "visual_plan": "episodes/ep_test/stories/story_001/visuals/visual_plan.json",
                        "visual_candidates": "episodes/ep_test/stories/story_001/visuals/visual_candidates.json",
                        "visual_skills": "episodes/ep_test/stories/story_001/visuals/visual_skills.json",
                    }
                },
            }

            records, summary = build_compositor_bridge(manifest, story_path)
            review_records, review_summary = build_compositor_bridge(manifest, story_path, review_only=True)

        self.assertEqual(records, [])
        self.assertEqual(summary["rejected_visual_count"], 1)
        self.assertEqual(summary["validation_status"], "failed")
        self.assertEqual(summary["unsafe_visual_warning_count"], 1)
        self.assertIn("unsafe_rights_category", " ".join(summary["rejected_visuals"][0]["rejection_reasons"]))
        self.assertTrue(bridge_validation_errors(summary))
        self.assertEqual(review_records[0]["render_safety_status"], "review_only")
        self.assertTrue(review_summary["review_only"])
        self.assertFalse(bridge_validation_errors(review_summary))

    def test_unknown_or_rejected_rights_are_not_compositor_selectable(self) -> None:
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            story_path = _story_path(root)
            _write_visual_audits(story_path, rights_category="unknown_or_rejected")
            manifest = {
                "story_id": "story_001",
                "episode_id": "ep_test",
                "visual_plan": {
                    "audit_paths": {
                        "visual_plan": "episodes/ep_test/stories/story_001/visuals/visual_plan.json",
                        "visual_candidates": "episodes/ep_test/stories/story_001/visuals/visual_candidates.json",
                    }
                },
            }

            records, summary = build_compositor_bridge(manifest, story_path)

        self.assertEqual(records, [])
        self.assertEqual(summary["validation_status"], "failed")
        self.assertEqual(summary["rejected_visuals"][0]["rights_category"], "unknown_or_rejected")

    def test_fair_use_review_required_is_rejected_by_default_without_manual_flag(self) -> None:
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            story_path = _story_path(root)
            _write_visual_audits(story_path, rights_category="fair_use_review_required", manual_review=False)
            manifest = {
                "story_id": "story_001",
                "episode_id": "ep_test",
                "visual_plan": {
                    "audit_paths": {
                        "visual_plan": "episodes/ep_test/stories/story_001/visuals/visual_plan.json",
                        "visual_candidates": "episodes/ep_test/stories/story_001/visuals/visual_candidates.json",
                    }
                },
            }

            records, summary = build_compositor_bridge(manifest, story_path)

        self.assertEqual(records, [])
        self.assertEqual(summary["validation_status"], "failed")
        self.assertIn("fair_use_review_required", summary["rejected_visuals"][0]["rights_category"])

    def test_missing_attribution_is_warned_for_rights_safe_assets(self) -> None:
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            story_path = _story_path(root)
            _write_visual_audits(story_path)
            plan_path = story_path.parent / "visuals" / "visual_plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["sections"][0].pop("attribution_text", None)
            plan["sections"][0]["visual_skill"].pop("attribution_text", None)
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            candidates_path = story_path.parent / "visuals" / "visual_candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["candidates"][0].pop("attribution_text", None)
            candidates["chosen_visuals"][0].pop("attribution_text", None)
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            manifest = {
                "story_id": "story_001",
                "episode_id": "ep_test",
                "visual_plan": {
                    "audit_paths": {
                        "visual_plan": "episodes/ep_test/stories/story_001/visuals/visual_plan.json",
                        "visual_candidates": "episodes/ep_test/stories/story_001/visuals/visual_candidates.json",
                    }
                },
            }

            records, summary = build_compositor_bridge(manifest, story_path)

        self.assertEqual(len(records), 1)
        self.assertFalse(summary["attribution"]["complete"])
        self.assertIn("missing_attribution_text", " ".join(records[0]["warnings"]))

    def test_missing_required_permissive_attribution_blocks_render(self) -> None:
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            story_path = _story_path(root)
            _write_visual_audits(story_path, rights_category="permissive_license")
            plan_path = story_path.parent / "visuals" / "visual_plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["sections"][0].pop("attribution_text", None)
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            candidates_path = story_path.parent / "visuals" / "visual_candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["candidates"][0].pop("attribution_text", None)
            candidates["chosen_visuals"][0].pop("attribution_text", None)
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            manifest = {
                "story_id": "story_001",
                "episode_id": "ep_test",
                "visual_plan": {
                    "audit_paths": {
                        "visual_plan": "episodes/ep_test/stories/story_001/visuals/visual_plan.json",
                        "visual_candidates": "episodes/ep_test/stories/story_001/visuals/visual_candidates.json",
                    }
                },
            }

            records, summary = build_compositor_bridge(manifest, story_path)

        self.assertEqual(records, [])
        self.assertEqual(summary["validation_status"], "failed")
        self.assertEqual(summary["attribution"]["blocking_missing_count"], 0)
        self.assertIn("missing_required_attribution", " ".join(summary["rejected_visuals"][0]["rejection_reasons"]))

    def test_visual_skill_placeholders_cover_all_supported_skill_types(self) -> None:
        for skill_type in SUPPORTED_SKILL_TYPES:
            placeholder = skill_placeholder(
                {
                    "skill_type": skill_type,
                    "spec": {
                        "title": "Title",
                        "location_names": ["India"],
                        "labels": ["India"],
                        "values": [{"value": "42 gigawatts"}],
                        "events": [{"date": "June 18", "label": "Opened"}],
                        "quote_text": "Grounded quote text",
                        "number": "42",
                        "unit": "GW",
                        "bullets": ["Grounded bullet"],
                        "entities": ["Nvidia"],
                    },
                },
                {"section_title": "Section"},
            )

            self.assertEqual(placeholder["render_mode"], "placeholder")
            self.assertEqual(placeholder["type"], skill_type)
            self.assertTrue(placeholder["title"])

    def test_apply_bridge_and_manifest_summary_include_visual_audit_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            episode = Path(temp_dir) / "ep_summary"
            story_path = episode / "stories" / "story_001" / "story.json"
            story_path.parent.mkdir(parents=True)
            manifest = {
                "episode_id": "ep_summary",
                "story_id": "story_001",
                "raw": {"headline_source": "Visual story"},
                "script": {"headline": "Visual story"},
                "direction": {},
                "visuals": [
                    {
                        "path": "media/legacy.png",
                        "start": 0,
                        "end": 5,
                        "sourceLabel": "LEGACY",
                        "rights_category": "first_party_generated",
                        "attribution_text": "Source: SynthPost",
                    }
                ],
                "points": [],
                "composition": {},
            }
            apply_compositor_bridge(manifest, story_path)
            write_manifest(story_path, manifest)

            summary = summarize_episode(episode)

        self.assertEqual(summary["visuals"]["input_source"], "legacy_visuals")
        self.assertEqual(summary["visuals"]["selected_count"], 1)
        self.assertEqual(summary["visuals"]["unsafe_visual_warning_count"], 0)
        self.assertTrue(summary["visuals"]["compositor_visuals_path"].endswith("visuals/compositor_visuals.json"))
        self.assertIn("first_party_generated", summary["visuals"]["rights_categories_used"])

    def test_absolute_local_paths_are_normalized_project_relative(self) -> None:
        with _project_root() as temp_dir:
            root = Path(temp_dir)
            story_path = _story_path(root)
            _write_visual_audits(story_path)
            absolute_media = root / "media" / "plan.png"
            absolute_media.parent.mkdir()
            absolute_media.write_bytes(b"fake")
            plan_path = story_path.parent / "visuals" / "visual_plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["sections"][0]["path"] = str(absolute_media)
            plan["sections"][0]["asset_url"] = str(absolute_media)
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            manifest = {
                "story_id": "story_001",
                "episode_id": "ep_test",
                "visual_plan": {
                    "audit_paths": {
                        "visual_plan": "episodes/ep_test/stories/story_001/visuals/visual_plan.json",
                        "visual_candidates": "episodes/ep_test/stories/story_001/visuals/visual_candidates.json",
                    }
                },
            }

            records, _summary = build_compositor_bridge(manifest, story_path)

        self.assertEqual(records[0]["path"], "media/plan.png")
        self.assertEqual(records[0]["asset_url"], "media/plan.png")


if __name__ == "__main__":
    unittest.main()
