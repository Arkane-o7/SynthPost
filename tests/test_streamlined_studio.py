from __future__ import annotations

import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from pipeline.api.main import _queue_final_video_job
from pipeline.channels import get_channel_profile, list_channel_profiles
from pipeline.db.repository import NotFoundError, Repository
from pipeline.jobs.worker import handle_research
from pipeline.models import (
    RenderJob,
    ResearchPack,
    StoryCandidate,
    StorySelectionStatus,
    StoryWorkflowState,
)


def selected_story(
    repository: Repository,
    episode_id: str,
    *,
    workflow_state: StoryWorkflowState,
) -> StoryCandidate:
    story = StoryCandidate(
        title="Streamlined Studio story",
        source_name="Test desk",
        episode_id=episode_id,
        story_id="story_streamlined",
        selection_status=StorySelectionStatus.selected,
        workflow_state=workflow_state,
    )
    repository.upsert_candidate(story)
    repository.add_story_to_episode(episode_id, story.story_id)
    return story


class FakeResearchContext:
    def __init__(self, repository: Repository, job: RenderJob):
        self.repository = repository
        self.job = job
        self.progress_events: list[tuple[float, str]] = []

    def progress(self, progress: float, stage: str) -> None:
        self.progress_events.append((progress, stage))


class StreamlinedStudioTests(unittest.TestCase):
    def test_builtin_channel_registry_is_complete_and_immutable(self) -> None:
        profiles = list_channel_profiles()

        self.assertEqual(
            [profile.channel_id for profile in profiles],
            ["synthpost"],
        )
        self.assertEqual(get_channel_profile("synthpost").name, "SynthPost")
        with self.assertRaises(FrozenInstanceError):
            profiles[0].name = "Changed"  # type: ignore[misc]

    def test_projects_episodes_candidates_and_jobs_default_to_synthpost(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(Path(temp) / "synthpost-only.sqlite3")
            try:
                project = repository.create_project("SynthPost")
                episode = repository.create_episode(project.project_id, "Episode")
                candidate = StoryCandidate(
                    title="AI platform launch",
                    source_name="Test desk",
                )
                repository.upsert_candidate(candidate)
                job = repository.create_job("discovery", episode_id=episode.episode_id)

                self.assertEqual(project.channel_id, "synthpost")
                self.assertEqual(episode.channel_id, "synthpost")
                self.assertEqual(candidate.channel_id, "synthpost")
                self.assertEqual(job.channel_id, "synthpost")
                self.assertEqual(
                    [item.project_id for item in repository.list_projects(channel_id="synthpost")],
                    [project.project_id],
                )
                self.assertEqual(
                    [item.candidate_id for item in repository.list_candidates(channel_id="synthpost", include_expired=True)],
                    [candidate.candidate_id],
                )
            finally:
                repository.close()

    def test_unnamed_projects_and_episodes_receive_ordered_dated_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(Path(temp) / "studio.sqlite3")
            try:
                first_project = repository.create_project()
                second_project = repository.create_project()
                first_episode = repository.create_episode(first_project.project_id)
                second_episode = repository.create_episode(first_project.project_id)

                self.assertTrue(first_project.title.startswith("Project 1 · "))
                self.assertTrue(second_project.title.startswith("Project 2 · "))
                self.assertTrue(first_episode.title.startswith("Episode 1 · "))
                self.assertTrue(second_episode.title.startswith("Episode 2 · "))
                self.assertEqual(first_episode.render_profile, "production")
            finally:
                repository.close()

    def test_projects_and_episodes_can_be_pinned_and_deleted_safely(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(Path(temp) / "studio.sqlite3")
            try:
                first_project = repository.create_project("First project")
                second_project = repository.create_project("Second project")
                first_episode = repository.create_episode(
                    first_project.project_id, "First episode"
                )
                second_episode = repository.create_episode(
                    first_project.project_id, "Second episode"
                )

                repository.update_project(first_project.project_id, {"pinned": True})
                repository.update_episode(first_episode.episode_id, {"pinned": True})

                self.assertEqual(
                    repository.list_projects()[0].project_id,
                    first_project.project_id,
                )
                self.assertEqual(
                    repository.list_episodes(first_project.project_id)[0].episode_id,
                    first_episode.episode_id,
                )

                repository.delete_episode(first_episode.episode_id)
                with self.assertRaises(NotFoundError):
                    repository.get_episode(first_episode.episode_id)
                self.assertEqual(
                    repository.get_episode(second_episode.episode_id).project_id,
                    first_project.project_id,
                )

                repository.delete_project(first_project.project_id)
                with self.assertRaises(NotFoundError):
                    repository.get_project(first_project.project_id)
                with self.assertRaises(NotFoundError):
                    repository.get_episode(second_episode.episode_id)
                self.assertEqual(
                    repository.get_project(second_project.project_id).title,
                    "Second project",
                )
            finally:
                repository.close()

    def test_active_jobs_block_episode_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(Path(temp) / "studio.sqlite3")
            try:
                project = repository.create_project("Protected project")
                episode = repository.create_episode(
                    project.project_id, "Protected episode"
                )
                repository.create_job("discovery", episode_id=episode.episode_id)

                with self.assertRaisesRegex(ValueError, "active jobs"):
                    repository.delete_episode(episode.episode_id)
                self.assertEqual(
                    repository.get_episode(episode.episode_id).title,
                    "Protected episode",
                )
            finally:
                repository.close()

    def test_research_job_can_continue_directly_into_script_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(Path(temp) / "studio.sqlite3")
            try:
                project = repository.create_project("Project")
                episode = repository.create_episode(project.project_id, "Episode")
                story = selected_story(
                    repository,
                    episode.episode_id,
                    workflow_state=StoryWorkflowState.researching,
                )
                job = RenderJob(
                    job_type="research",
                    episode_id=episode.episode_id,
                    story_id=story.story_id,
                    payload={
                        "_continue_to_script": True,
                        "target_duration_seconds": 420,
                        "narration_mode": "signal",
                    },
                )
                context = FakeResearchContext(repository, job)
                pack = ResearchPack(story_id=story.story_id)

                def finish_research(*_args, **_kwargs):
                    repository.upsert_research_pack(pack)
                    repository.transition_story(
                        story.story_id, StoryWorkflowState.research_ready
                    )
                    return pack

                with patch(
                    "pipeline.jobs.worker.build_research_pack",
                    side_effect=finish_research,
                ):
                    outputs = handle_research(context)

                script_job = repository.active_job(
                    "script_generate", story_id=story.story_id
                )
                self.assertEqual(outputs["research_pack_id"], pack.research_pack_id)
                self.assertIsNotNone(script_job)
                assert script_job is not None
                self.assertEqual(script_job.payload["target_duration_seconds"], 420)
                self.assertEqual(script_job.payload["narration_mode"], "signal")
                self.assertEqual(
                    repository.candidate_for_story(story.story_id).workflow_state,
                    StoryWorkflowState.script_generating,
                )
            finally:
                repository.close()

    def test_final_video_action_queues_production_render_with_assembly_handoff(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(Path(temp) / "studio.sqlite3")
            try:
                project = repository.create_project("Project")
                episode = repository.create_episode(project.project_id, "Episode")
                story = selected_story(
                    repository,
                    episode.episode_id,
                    workflow_state=StoryWorkflowState.timeline_approved,
                )

                job = _queue_final_video_job(repository, story.story_id)

                self.assertEqual(job.job_type, "render_story")
                self.assertEqual(job.render_profile, "production")
                self.assertFalse(job.payload["skip_avatar_render"])
                self.assertTrue(job.payload["_continue_to_assembly"])
                self.assertEqual(
                    repository.candidate_for_story(story.story_id).workflow_state,
                    StoryWorkflowState.rendering_composition,
                )
            finally:
                repository.close()


if __name__ == "__main__":
    unittest.main()
