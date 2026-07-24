from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.api.main import api_render_avatar, api_render_story
from pipeline.api.schemas import RenderRequest
from pipeline.db.repository import Repository
from pipeline.discovery.discover import add_manual_story
from pipeline.manifest_builder import build_story_manifest
from pipeline.jobs.worker import _restore_workflow_after_terminal_failure
from pipeline.models import (
    EpisodeStatus,
    RenderJob,
    ResearchPack,
    ScriptStatus,
    StoryWorkflowState,
    TimelineStatus,
)
from pipeline.research.extract import begin_research_revision
from pipeline.visuals.providers import (
    begin_visual_search_revision,
    mark_visuals_revised,
)
from pipeline.workflow import can_transition


class CompletedProductionBacktrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "backtracking.sqlite3"
        repository = Repository(self.database_path)
        project = repository.create_project("Backtracking")
        episode = repository.create_episode(project.project_id, "Episode")
        candidate = add_manual_story(
            repository,
            title="Completed story",
            body="A completed story needs an editorial revision.",
            episode_id=episode.episode_id,
        )
        selected = repository.select_candidate(
            candidate.candidate_id,
            episode.episode_id,
        )
        assert selected.story_id is not None
        self.story_id = selected.story_id
        self.episode_id = episode.episode_id
        selected.workflow_state = StoryWorkflowState.completed
        repository.upsert_candidate(selected)
        persisted_episode = repository.get_episode(episode.episode_id)
        persisted_episode.status = EpisodeStatus.completed
        persisted_episode.final_output_path = "episodes/previous-final.mp4"
        repository.upsert_episode(persisted_episode)
        repository.close()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def repository(self) -> Repository:
        return Repository(self.database_path)

    def assert_reopened(
        self,
        expected_state: StoryWorkflowState,
    ) -> None:
        repository = self.repository()
        try:
            self.assertEqual(
                repository.candidate_for_story(self.story_id).workflow_state,
                expected_state,
            )
            episode = repository.get_episode(self.episode_id)
            self.assertEqual(episode.status, EpisodeStatus.in_progress)
            self.assertEqual(
                episode.final_output_path,
                "episodes/previous-final.mp4",
            )
        finally:
            repository.close()

    def reset_completed(self) -> None:
        repository = self.repository()
        try:
            candidate = repository.candidate_for_story(self.story_id)
            candidate.workflow_state = StoryWorkflowState.completed
            repository.upsert_candidate(candidate)
            episode = repository.get_episode(self.episode_id)
            episode.status = EpisodeStatus.completed
            repository.upsert_episode(episode)
        finally:
            repository.close()

    def test_completed_state_supports_every_edit_and_render_rollback(self) -> None:
        for target in (
            StoryWorkflowState.researching,
            StoryWorkflowState.script_review,
            StoryWorkflowState.visuals_searching,
            StoryWorkflowState.visuals_review,
            StoryWorkflowState.timeline_review,
            StoryWorkflowState.rendering_avatar,
            StoryWorkflowState.rendering_composition,
        ):
            with self.subTest(target=target.value):
                self.assertTrue(can_transition(StoryWorkflowState.completed, target))

    def test_research_revision_reopens_completed_episode(self) -> None:
        repository = self.repository()
        try:
            repository.upsert_research_pack(ResearchPack(story_id=self.story_id))
            restore_state = begin_research_revision(repository, self.story_id)
            self.assertEqual(restore_state, StoryWorkflowState.research_ready)
        finally:
            repository.close()
        self.assert_reopened(StoryWorkflowState.researching)

    def test_visual_revision_reopens_completed_episode(self) -> None:
        repository = self.repository()
        try:
            mark_visuals_revised(repository, self.story_id)
        finally:
            repository.close()
        self.assert_reopened(StoryWorkflowState.visuals_review)

        self.reset_completed()
        repository = self.repository()
        try:
            begin_visual_search_revision(repository, self.story_id)
        finally:
            repository.close()
        self.assert_reopened(StoryWorkflowState.visuals_searching)

    def test_preview_is_non_destructive_but_production_render_reopens(self) -> None:
        with patch(
            "pipeline.api.main.repo",
            side_effect=lambda: self.repository(),
        ):
            api_render_story(
                self.story_id,
                RenderRequest(render_profile="preview", test_mode=True),
            )
        repository = self.repository()
        try:
            self.assertEqual(
                repository.candidate_for_story(self.story_id).workflow_state,
                StoryWorkflowState.completed,
            )
            self.assertEqual(
                repository.get_episode(self.episode_id).status,
                EpisodeStatus.completed,
            )
        finally:
            repository.close()

        with patch(
            "pipeline.api.main.repo",
            side_effect=lambda: self.repository(),
        ):
            api_render_story(
                self.story_id,
                RenderRequest(render_profile="production", test_mode=False),
            )
        self.assert_reopened(StoryWorkflowState.rendering_composition)

    def test_avatar_rerender_reopens_completed_episode(self) -> None:
        with patch(
            "pipeline.api.main.repo",
            side_effect=lambda: self.repository(),
        ):
            api_render_avatar(
                self.story_id,
                RenderRequest(render_profile="production", test_mode=False),
            )
        self.assert_reopened(StoryWorkflowState.rendering_avatar)

    def test_manifest_rejects_stale_downstream_state(self) -> None:
        repository = MagicMock()
        repository.episode_for_story.return_value = MagicMock()
        repository.candidate_for_story.return_value = MagicMock(
            workflow_state=StoryWorkflowState.visuals_review
        )
        repository.latest_script.return_value = MagicMock(
            status=ScriptStatus.approved,
            created_at="2026-01-01T00:00:00Z",
        )
        repository.latest_timeline.return_value = MagicMock(
            status=TimelineStatus.approved,
            created_at="2026-01-01T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "upstream revisions"):
            build_story_manifest(repository, self.story_id)

    def test_failed_revision_jobs_restore_their_review_stage(self) -> None:
        repository = self.repository()
        try:
            candidate = repository.candidate_for_story(self.story_id)
            candidate.workflow_state = StoryWorkflowState.researching
            repository.upsert_candidate(candidate)
            research_job = RenderJob(
                job_type="research",
                story_id=self.story_id,
                payload={"_restore_workflow_state": "research_ready"},
            )
            self.assertIsNone(
                _restore_workflow_after_terminal_failure(
                    repository,
                    research_job,
                )
            )
            self.assertEqual(
                repository.candidate_for_story(self.story_id).workflow_state,
                StoryWorkflowState.research_ready,
            )

            candidate = repository.candidate_for_story(self.story_id)
            candidate.workflow_state = StoryWorkflowState.visuals_searching
            repository.upsert_candidate(candidate)
            visual_job = RenderJob(
                job_type="visual_search",
                story_id=self.story_id,
            )
            self.assertIsNone(
                _restore_workflow_after_terminal_failure(
                    repository,
                    visual_job,
                )
            )
            self.assertEqual(
                repository.candidate_for_story(self.story_id).workflow_state,
                StoryWorkflowState.visuals_review,
            )
        finally:
            repository.close()


if __name__ == "__main__":
    unittest.main()
