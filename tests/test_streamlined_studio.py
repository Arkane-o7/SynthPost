from __future__ import annotations

import json
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
            ["synthpost", "meridian", "beyond", "storytime"],
        )
        self.assertEqual(get_channel_profile("meridian").name, "Meridian")
        self.assertEqual(
            get_channel_profile("meridian").default_target_duration_seconds,
            900,
        )
        self.assertNotEqual(
            get_channel_profile("meridian").voice_profile,
            get_channel_profile("beyond").voice_profile,
        )
        self.assertNotEqual(
            get_channel_profile("meridian").template_pack,
            get_channel_profile("synthpost").template_pack,
        )
        with self.assertRaises(FrozenInstanceError):
            profiles[0].name = "Changed"  # type: ignore[misc]

    def test_projects_are_channel_scoped_and_episodes_inherit_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(Path(temp) / "channels.sqlite3")
            try:
                legacy = repository.create_project("Legacy")
                meridian = repository.create_project(
                    "Markets", channel_id="meridian"
                )
                beyond = repository.create_project("World", channel_id="beyond")

                episode = repository.create_episode(
                    meridian.project_id, "Money episode"
                )

                legacy_data = legacy.model_dump(mode="json")
                legacy_data.pop("channel_id")
                legacy_data.pop("profile_version")
                with repository.connection:
                    repository.connection.execute(
                        "UPDATE projects SET data = ? WHERE project_id = ?",
                        (json.dumps(legacy_data), legacy.project_id),
                    )

                self.assertEqual(
                    repository.get_project(legacy.project_id).channel_id,
                    "synthpost",
                )
                self.assertEqual(
                    [
                        item.project_id
                        for item in repository.list_projects(channel_id="meridian")
                    ],
                    [meridian.project_id],
                )
                self.assertEqual(
                    [
                        item.project_id
                        for item in repository.list_projects(channel_id="beyond")
                    ],
                    [beyond.project_id],
                )
                self.assertEqual(
                    [
                        item.project_id
                        for item in repository.list_projects(channel_id="synthpost")
                    ],
                    [legacy.project_id],
                )
                self.assertEqual(episode.channel_id, meridian.channel_id)
                self.assertEqual(
                    episode.profile_version, meridian.profile_version
                )
                self.assertEqual(
                    repository.list_episodes(channel_id="synthpost"), []
                )
                self.assertEqual(
                    repository.list_episodes(channel_id="meridian")[0].episode_id,
                    episode.episode_id,
                )
            finally:
                repository.close()

    def test_candidate_cannot_cross_channel_episode_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(Path(temp) / "candidate-channel.sqlite3")
            try:
                project = repository.create_project(
                    "Meridian", channel_id="meridian"
                )
                episode = repository.create_episode(project.project_id)
                candidate = StoryCandidate(
                    channel_id="beyond",
                    title="World story",
                    source_name="Test desk",
                )
                repository.upsert_candidate(candidate)

                with self.assertRaisesRegex(ValueError, "Cannot add a beyond story"):
                    repository.select_candidate(
                        candidate.candidate_id, episode.episode_id
                    )
                self.assertEqual(
                    repository.get_episode(episode.episode_id).story_ids, []
                )
            finally:
                repository.close()

    def test_candidate_lists_are_channel_scoped_with_legacy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(Path(temp) / "candidate-list-channel.sqlite3")
            try:
                synthpost = StoryCandidate(
                    candidate_id="cand_synthpost",
                    title="AI platform launch",
                    source_name="Test desk",
                )
                meridian = StoryCandidate(
                    candidate_id="cand_meridian",
                    channel_id="meridian",
                    title="Central bank changes rates",
                    source_name="Test desk",
                )
                repository.upsert_candidate(synthpost)
                repository.upsert_candidate(meridian)

                self.assertEqual(
                    [
                        item.candidate_id
                        for item in repository.list_candidates(
                            channel_id="synthpost", include_expired=True
                        )
                    ],
                    [synthpost.candidate_id],
                )
                self.assertEqual(
                    [
                        item.candidate_id
                        for item in repository.list_candidates(
                            channel_id="meridian", include_expired=True
                        )
                    ],
                    [meridian.candidate_id],
                )
            finally:
                repository.close()

    def test_jobs_infer_and_filter_channel_without_schema_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(Path(temp) / "job-channel.sqlite3")
            try:
                project = repository.create_project(
                    "Beyond", channel_id="beyond"
                )
                episode = repository.create_episode(project.project_id)
                beyond_job = repository.create_job(
                    "discovery", episode_id=episode.episode_id
                )
                synthpost_job = repository.create_job("discovery")

                self.assertEqual(beyond_job.channel_id, "beyond")
                self.assertEqual(synthpost_job.channel_id, "synthpost")
                self.assertEqual(
                    [
                        job.job_id
                        for job in repository.list_jobs(channel_id="beyond")
                    ],
                    [beyond_job.job_id],
                )
                self.assertEqual(
                    [
                        job.job_id
                        for job in repository.list_jobs(channel_id="synthpost")
                    ],
                    [synthpost_job.job_id],
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
