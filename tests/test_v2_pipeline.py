from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from pipeline.db.repository import Repository
from pipeline.discovery.discover import (
    add_manual_story,
    canonicalize_url,
    duplicate_group,
    normalize_title,
    score_candidate,
)
from pipeline.manifest_builder import build_story_manifest
from pipeline.models import (
    ContentRole,
    RightsTier,
    SourceDefinition,
    SourceType,
    StoryWorkflowState,
    VisualCandidate,
)
from pipeline.research.extract import build_research_pack
from pipeline.run_story import _sync_timeline_to_avatar_duration
from pipeline.scripts.generation import approve_script, save_manual_script
from pipeline.storage import PROJECT_ROOT
from pipeline.timeline.planner import (
    approve_timeline,
    choose_template,
    generate_timeline,
)
from pipeline.timeline.validation import validate_timeline
from pipeline.visuals.providers import approve_visual, stage_local_visual
from pipeline.workflow import assert_transition, can_transition


class V2WorkflowAndPipelineTests(unittest.TestCase):
    def test_workflow_blocks_invalid_transition(self) -> None:
        self.assertTrue(
            can_transition(StoryWorkflowState.discovered, StoryWorkflowState.selected)
        )
        with self.assertRaises(ValueError):
            assert_transition(
                StoryWorkflowState.discovered, StoryWorkflowState.completed
            )

    def test_url_canonicalization_and_duplicate_grouping_are_deterministic(
        self,
    ) -> None:
        first = canonicalize_url("HTTPS://Example.com/story/?utm_source=x&b=2#frag")
        second = canonicalize_url("https://example.com/story?b=2")
        self.assertEqual(first, second)
        self.assertEqual(normalize_title("  Big  Story!!! "), "big story")
        self.assertEqual(
            duplicate_group("Title", first), duplicate_group("Other", second)
        )

    def test_story_scoring_is_deterministic(self) -> None:
        source = SourceDefinition(
            name="Unit Feed",
            source_id="src_unit",
            source_type=SourceType.rss,
            feed_url="https://example.com/rss",
            reliability_score=0.8,
        )
        a = score_candidate(
            source,
            "Major AI chip market ruling",
            "A court decision affects billions in the market",
            None,
        )
        b = score_candidate(
            source,
            "Major AI chip market ruling",
            "A court decision affects billions in the market",
            None,
        )
        self.assertEqual(a, b)

    def test_rights_validation_blocks_red_asset(self) -> None:
        with self.assertRaises(ValueError):
            VisualCandidate(
                story_id="story_red",
                provider="unit",
                media_type="image",
                content_role="context",
                rights_tier="red",
                review_status="approved",
            )

    def test_default_timeline_templates_preserve_retained_anchor_look(self) -> None:
        self.assertEqual(choose_template("intro", None, 0), "fullscreen_anchor")
        self.assertEqual(choose_template("context", None, 1), "fallback_anchor")

    def test_avatar_duration_rescale_removes_pure_narration_timeline_gaps(self) -> None:
        manifest = {
            "direction": {"estimated_duration_seconds": 37.8},
            "approved_timeline": {
                "status": "approved",
                "duration_seconds": 30.0,
                "audio_plan": {
                    "duration_seconds": 30.0,
                    "regions": [
                        {"segment_id": "seg_001", "start_time": 0.0, "end_time": 10.0},
                        {"segment_id": "seg_002", "start_time": 10.0, "end_time": 30.0},
                    ],
                },
                "segments": [
                    {
                        "segment_id": "seg_001",
                        "start_time": 0.0,
                        "end_time": 10.0,
                        "duration": 10.0,
                        "audio": {"mode": "narration"},
                        "visual": {"audio_mode": "muted"},
                    },
                    {
                        "segment_id": "seg_002",
                        "start_time": 10.0,
                        "end_time": 30.0,
                        "duration": 20.0,
                        "audio": {"mode": "narration"},
                        "visual": {"audio_mode": "muted"},
                    },
                ],
            },
        }

        changed = _sync_timeline_to_avatar_duration(manifest)

        self.assertTrue(changed)
        timeline = manifest["approved_timeline"]
        segments = timeline["segments"]
        self.assertEqual(timeline["timing_source"], "avatar_duration_rescaled")
        self.assertEqual(timeline["duration_seconds"], 37.8)
        self.assertEqual(segments[0]["start_time"], 0.0)
        self.assertEqual(segments[0]["end_time"], segments[1]["start_time"])
        self.assertEqual(segments[-1]["end_time"], 37.8)
        self.assertAlmostEqual(
            sum(segment["duration"] for segment in segments), 37.8, places=2
        )
        self.assertEqual(timeline["audio_plan"]["regions"][1]["start_time"], 12.6)

    def test_avatar_duration_rescale_skips_source_audio_timelines(self) -> None:
        manifest = {
            "direction": {"estimated_duration_seconds": 37.8},
            "approved_timeline": {
                "status": "approved",
                "duration_seconds": 30.0,
                "segments": [
                    {
                        "segment_id": "seg_001",
                        "start_time": 0.0,
                        "end_time": 30.0,
                        "duration": 30.0,
                        "audio": {"mode": "source"},
                        "visual": {"audio_mode": "original"},
                    }
                ],
            },
        }

        changed = _sync_timeline_to_avatar_duration(manifest)

        self.assertFalse(changed)
        timeline = manifest["approved_timeline"]
        self.assertEqual(timeline["segments"][0]["end_time"], 30.0)
        self.assertIn("source/mixed audio", timeline["timing_sync_warning"])

    def test_manual_vertical_slice_builds_renderer_manifest(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        episode_id = ""
        story_id = None
        try:
            project = repository.create_project("Unit Project")
            episode = repository.create_episode(
                project.project_id, "Unit Episode", render_profile="preview"
            )
            episode_id = episode.episode_id
            candidate = add_manual_story(
                repository,
                title="Unit story for SynthPost Studio",
                body="SynthPost Studio keeps renderer approvals explicit. The timeline uses approved media and blocks unsafe rights states.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            story_id = selected.story_id
            assert story_id is not None
            build_research_pack(repository, story_id)
            script = save_manual_script(
                repository,
                story_id,
                "Unit story for SynthPost Studio",
                "SynthPost Studio keeps renderer approvals explicit.\n\nThe approved timeline becomes the rendering source of truth.",
            )
            approve_script(repository, story_id)
            image = (
                PROJECT_ROOT
                / "compositor"
                / "remotion_renderer"
                / "public"
                / "news"
                / "datacenter-server-racks.jpg"
            )
            visual = stage_local_visual(
                repository,
                story_id,
                image,
                section_ids=[script.sections[-1].section_id],
                content_role=ContentRole.context,
                rights_tier=RightsTier.green,
            )
            approve_visual(repository, visual.asset_id)
            plan = generate_timeline(repository, story_id)
            errors, _warnings = validate_timeline(plan)
            self.assertEqual(errors, [])
            approved = approve_timeline(repository, story_id)
            manifest = build_story_manifest(
                repository, story_id, render_profile="preview", test_mode=True
            )
            self.assertEqual(manifest["approved_timeline"]["status"], "approved")
            self.assertEqual(manifest["composition"]["template"], "timeline_story")
            self.assertTrue(
                (
                    PROJECT_ROOT
                    / "episodes"
                    / episode_id
                    / "stories"
                    / story_id
                    / "story.json"
                ).exists()
            )
        finally:
            repository.close()
            temp.cleanup()
            shutil.rmtree(PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
