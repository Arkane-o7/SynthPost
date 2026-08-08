from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pipeline.api.routes.autonomy import router as autonomy_router
from pipeline.autonomy import (
    advance_autonomy_run,
    cancel_autonomy_run,
    episode_revision_fingerprint,
    enforce_green_only_visuals,
    reconcile_autonomy_runs,
    retry_autonomy_run,
    review_autonomy_run,
    start_autonomy_run,
)
from pipeline.db.repository import Repository
from pipeline.jobs.worker import _acknowledge_cancel_request, handle_final_video_qa
from pipeline.llm.providers import ProviderAvailability
from pipeline.models import (
    AutonomyPolicy,
    AutonomyRun,
    AutonomyRunStatus,
    JobStatus,
    MediaType,
    ReviewStatus,
    RightsTier,
    ScriptStatus,
    StoryCandidate,
    StoryWorkflowState,
    TimelineStatus,
    VisualCandidate,
)
from pipeline.video_qa import FinalVideoQAReport
from pipeline.visuals.providers import mark_visuals_revised


AVAILABLE_HERMES = ProviderAvailability(
    name="hermes",
    available=True,
    reason="available in isolated autonomy test",
)


class FakeQAContext:
    def __init__(self, repository: Repository, job) -> None:
        self.repository = repository
        self.job = job
        self.progress_events: list[tuple[float, str]] = []

    def progress(self, progress: float, stage: str) -> None:
        self.progress_events.append((progress, stage))


class AutonomyOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "autonomy.sqlite3"
        self.repository = Repository(self.db_path)

    def tearDown(self) -> None:
        self.repository.close()
        self.temp.cleanup()

    def _episode(self, title: str = "Night shift"):
        project = self.repository.create_project(f"{title} project")
        return self.repository.create_episode(project.project_id, title)

    def _selected_story(self, episode_id: str, suffix: str = "one"):
        candidate = StoryCandidate(
            candidate_id=f"cand_autonomy_{suffix}",
            title=f"Autonomy story {suffix}",
            source_name="Test desk",
        )
        self.repository.upsert_candidate(candidate)
        return self.repository.select_candidate(candidate.candidate_id, episode_id)

    @patch("pipeline.autonomy.provider_availability", return_value=AVAILABLE_HERMES)
    def test_blank_episode_start_persists_correlated_discovery_job(
        self, _availability
    ) -> None:
        episode = self._episode()
        policy = AutonomyPolicy(max_repairs_per_stage=2)
        self.assertEqual(policy.duration_mode, "adaptive")

        run = start_autonomy_run(
            self.repository,
            episode_id=episode.episode_id,
            policy=policy,
        )

        self.assertEqual(run.status, AutonomyRunStatus.running)
        self.assertEqual(run.current_stage, "discovering")
        self.assertIsNone(run.story_id)
        jobs = self.repository.list_jobs(autonomy_run_id=run.run_id)
        self.assertEqual(len(jobs), 1)
        discovery = jobs[0]
        self.assertEqual(discovery.job_type, "discovery")
        self.assertEqual(discovery.autonomy_run_id, run.run_id)
        self.assertEqual(discovery.payload["_autonomy_run_id"], run.run_id)
        self.assertEqual(discovery.payload["episode_id"], episode.episode_id)
        self.assertEqual(discovery.max_attempts, 3)
        self.assertEqual(run.active_job_ids, [discovery.job_id])

        # Reopening SQLite verifies that both the run and job correlation are
        # durable, rather than an in-memory orchestration detail.
        self.repository.close()
        self.repository = Repository(self.db_path)
        persisted = self.repository.get_autonomy_run(run.run_id)
        persisted_job = self.repository.get_job(discovery.job_id)
        self.assertEqual(persisted.current_stage, "discovering")
        self.assertEqual(persisted.job_ids, [discovery.job_id])
        self.assertEqual(persisted_job.autonomy_run_id, run.run_id)

    @patch("pipeline.autonomy.provider_availability", return_value=AVAILABLE_HERMES)
    def test_existing_story_hands_off_to_research_with_bounded_repairs(
        self, _availability
    ) -> None:
        episode = self._episode()
        story = self._selected_story(episode.episode_id)
        policy = AutonomyPolicy(max_repairs_per_stage=3)

        run = start_autonomy_run(
            self.repository,
            episode_id=episode.episode_id,
            story_id=story.story_id,
            policy=policy,
        )

        jobs = self.repository.list_jobs(autonomy_run_id=run.run_id)
        self.assertEqual(len(jobs), 1)
        research = jobs[0]
        self.assertEqual(research.job_type, "research")
        self.assertEqual(research.story_id, story.story_id)
        self.assertEqual(research.autonomy_run_id, run.run_id)
        self.assertEqual(
            research.payload["_restore_workflow_state"],
            StoryWorkflowState.selected.value,
        )
        # One initial attempt plus exactly the configured repair allowance.
        self.assertEqual(research.max_attempts, 4)
        self.assertEqual(
            self.repository.candidate_for_story(story.story_id).workflow_state,
            StoryWorkflowState.researching,
        )

        research.status = JobStatus.failed
        research.attempts = research.max_attempts
        research.error = "simulated recoverable worker failure"
        self.repository.upsert_job(research)
        run.status = AutonomyRunStatus.needs_attention
        self.repository.upsert_autonomy_run(run)

        retried = retry_autonomy_run(self.repository, run.run_id)
        retried_job = self.repository.get_job(research.job_id)
        self.assertEqual(retried.status, AutonomyRunStatus.running)
        self.assertEqual(retried_job.status, JobStatus.queued)
        self.assertEqual(retried_job.attempts, 0)
        self.assertEqual(retried_job.max_attempts, 4)

    @patch("pipeline.autonomy.provider_availability", return_value=AVAILABLE_HERMES)
    def test_retry_adopts_a_story_selected_after_discovery_needed_help(
        self, _availability
    ) -> None:
        episode = self._episode()
        run = start_autonomy_run(
            self.repository,
            episode_id=episode.episode_id,
        )
        discovery = self.repository.list_jobs(autonomy_run_id=run.run_id)[0]
        discovery.status = JobStatus.completed
        discovery.output_paths = {"candidate_count": "0"}
        self.repository.upsert_job(discovery)
        attention = advance_autonomy_run(self.repository, run.run_id)
        self.assertEqual(attention.status, AutonomyRunStatus.needs_attention)

        selected = self._selected_story(episode.episode_id, "editor_choice")
        retried = retry_autonomy_run(self.repository, run.run_id)

        self.assertEqual(retried.story_id, selected.story_id)
        self.assertEqual(retried.candidate_id, selected.candidate_id)
        self.assertEqual(retried.current_stage, "researching")
        research = self.repository.list_jobs(
            autonomy_run_id=run.run_id, job_type="research"
        )
        self.assertEqual(len(research), 1)

    def test_retry_upgrades_a_legacy_script_job_to_adaptive_duration(self) -> None:
        episode = self._episode("Legacy fixed script")
        story = self._selected_story(episode.episode_id, "legacy_script")
        run = AutonomyRun(
            project_id=episode.project_id,
            episode_id=episode.episode_id,
            story_id=story.story_id,
            candidate_id=story.candidate_id,
            status=AutonomyRunStatus.needs_attention,
            current_stage="writing_script",
        )
        self.repository.upsert_autonomy_run(run)
        job = self.repository.create_job(
            "script_generate",
            episode_id=episode.episode_id,
            story_id=story.story_id,
            autonomy_run_id=run.run_id,
            payload={"target_duration_seconds": 600},
        )
        job.status = JobStatus.failed
        job.error = "legacy fixed-duration validation failure"
        self.repository.upsert_job(job)

        retry_autonomy_run(self.repository, run.run_id)

        retried = self.repository.get_job(job.job_id)
        self.assertEqual(retried.status, JobStatus.queued)
        self.assertEqual(retried.payload["duration_mode"], "adaptive")
        self.assertEqual(retried.payload["target_duration_seconds"], 600)

    @patch("pipeline.autonomy.provider_availability", return_value=AVAILABLE_HERMES)
    def test_cancel_stops_jobs_and_restores_editable_story_checkpoint(
        self, _availability
    ) -> None:
        episode = self._episode()
        story = self._selected_story(episode.episode_id)
        run = start_autonomy_run(
            self.repository,
            episode_id=episode.episode_id,
            story_id=story.story_id,
        )
        job = self.repository.list_jobs(autonomy_run_id=run.run_id)[0]
        self.assertEqual(
            self.repository.candidate_for_story(story.story_id).workflow_state,
            StoryWorkflowState.researching,
        )

        cancelled = cancel_autonomy_run(self.repository, run.run_id)

        self.assertEqual(cancelled.status, AutonomyRunStatus.cancelled)
        self.assertEqual(cancelled.current_stage, "cancelled")
        self.assertEqual(cancelled.active_job_ids, [])
        self.assertEqual(self.repository.get_job(job.job_id).status, JobStatus.cancelled)
        self.assertEqual(
            self.repository.candidate_for_story(story.story_id).workflow_state,
            StoryWorkflowState.selected,
        )

    @patch("pipeline.autonomy.provider_availability", return_value=AVAILABLE_HERMES)
    def test_running_cancel_restores_story_only_after_worker_acknowledges(
        self, _availability
    ) -> None:
        episode = self._episode("Running cancellation")
        story = self._selected_story(episode.episode_id, "running_cancel")
        run = start_autonomy_run(
            self.repository,
            episode_id=episode.episode_id,
            story_id=story.story_id,
        )
        job = self.repository.list_jobs(autonomy_run_id=run.run_id)[0]
        job.status = JobStatus.running
        self.repository.upsert_job(job)

        stopping = cancel_autonomy_run(self.repository, run.run_id)
        self.assertEqual(
            self.repository.get_job(job.job_id).status,
            JobStatus.cancel_requested,
        )
        self.assertEqual(stopping.active_job_ids, [job.job_id])
        self.assertEqual(
            self.repository.candidate_for_story(story.story_id).workflow_state,
            StoryWorkflowState.researching,
        )

        _acknowledge_cancel_request(self.repository, job)

        self.assertEqual(
            self.repository.get_job(job.job_id).status,
            JobStatus.cancelled,
        )
        self.assertEqual(
            self.repository.get_autonomy_run(run.run_id).active_job_ids,
            [],
        )
        self.assertEqual(
            self.repository.candidate_for_story(story.story_id).workflow_state,
            StoryWorkflowState.selected,
        )

    def test_database_allows_only_one_concurrent_unreviewed_run_per_episode(
        self,
    ) -> None:
        episode = self._episode("Concurrent")
        barrier = threading.Barrier(2)

        def insert_run(index: int) -> str:
            repository = Repository(self.db_path)
            run = AutonomyRun(
                run_id=f"run_concurrent_{index}",
                project_id=episode.project_id,
                episode_id=episode.episode_id,
            )
            try:
                barrier.wait(timeout=5)
                repository.upsert_autonomy_run(run)
                return "created"
            except sqlite3.IntegrityError:
                return "guarded"
            finally:
                repository.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(insert_run, (1, 2)))

        self.assertCountEqual(outcomes, ["created", "guarded"])
        persisted = self.repository.list_autonomy_runs(
            episode_id=episode.episode_id
        )
        self.assertEqual(len(persisted), 1)
        self.assertIn(persisted[0].run_id, {"run_concurrent_1", "run_concurrent_2"})

    def test_stale_running_copy_cannot_resurrect_a_cancelled_run(self) -> None:
        episode = self._episode("Stale reconcile")
        run = AutonomyRun(
            project_id=episode.project_id,
            episode_id=episode.episode_id,
            status=AutonomyRunStatus.running,
            current_stage="researching",
        )
        self.repository.upsert_autonomy_run(run)
        stale = self.repository.get_autonomy_run(run.run_id)

        cancelled = self.repository.get_autonomy_run(run.run_id)
        cancelled.status = AutonomyRunStatus.cancelled
        cancelled.current_stage = "cancelled"
        self.repository.upsert_autonomy_run(
            cancelled,
            expected_status=AutonomyRunStatus.running,
        )

        stale.status = AutonomyRunStatus.running
        stale.current_stage = "rendering"
        stale.progress = 80
        returned = self.repository.upsert_autonomy_run(stale)

        self.assertEqual(returned.status, AutonomyRunStatus.cancelled)
        persisted = self.repository.get_autonomy_run(run.run_id)
        self.assertEqual(persisted.status, AutonomyRunStatus.cancelled)
        self.assertEqual(persisted.current_stage, "cancelled")
        self.assertNotEqual(persisted.progress, 80)

    def test_terminal_run_rejects_new_or_resurrected_active_jobs(self) -> None:
        episode = self._episode("Terminal queue guard")
        run = AutonomyRun(
            project_id=episode.project_id,
            episode_id=episode.episode_id,
            status=AutonomyRunStatus.running,
        )
        self.repository.upsert_autonomy_run(run)
        old_job = self.repository.create_job(
            "discovery",
            episode_id=episode.episode_id,
            autonomy_run_id=run.run_id,
        )
        old_job.status = JobStatus.cancelled
        self.repository.upsert_job(old_job)
        run.status = AutonomyRunStatus.cancelled
        self.repository.upsert_autonomy_run(
            run, expected_status=AutonomyRunStatus.running
        )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "autonomy run is terminal"):
            self.repository.create_job(
                "research",
                episode_id=episode.episode_id,
                autonomy_run_id=run.run_id,
            )

        old_job.status = JobStatus.queued
        with self.assertRaisesRegex(sqlite3.IntegrityError, "autonomy run is terminal"):
            self.repository.upsert_job(old_job)

    @patch("pipeline.autonomy.provider_availability", return_value=AVAILABLE_HERMES)
    def test_cancel_requested_job_blocks_replacement_run_until_acknowledged(
        self, _availability
    ) -> None:
        episode = self._episode("Cancellation lease")
        incumbent = self.repository.create_job(
            "discovery",
            episode_id=episode.episode_id,
        )
        incumbent.status = JobStatus.running
        incumbent.stage = "fetching_sources"
        self.repository.upsert_job(incumbent)

        stopping = self.repository.request_job_cancellation(incumbent.job_id)
        self.assertEqual(stopping.status, JobStatus.cancel_requested)
        with self.assertRaisesRegex(ValueError, "existing episode jobs"):
            start_autonomy_run(
                self.repository,
                episode_id=episode.episode_id,
            )

        self.assertTrue(
            self.repository.acknowledge_job_cancellation(incumbent.job_id)
        )
        self.assertEqual(
            self.repository.get_job(incumbent.job_id).status,
            JobStatus.cancelled,
        )
        replacement = start_autonomy_run(
            self.repository,
            episode_id=episode.episode_id,
        )
        self.assertEqual(replacement.current_stage, "discovering")

    def _patch_ready_editorial_inputs(self, story_id: str):
        return (
            patch.object(
                self.repository,
                "latest_research_pack",
                return_value=SimpleNamespace(story_id=story_id),
            ),
            patch.object(
                self.repository,
                "latest_script",
                return_value=SimpleNamespace(status=ScriptStatus.approved),
            ),
            patch.object(
                self.repository,
                "latest_timeline",
                return_value=SimpleNamespace(status=TimelineStatus.approved),
            ),
            patch("pipeline.autonomy._current_narration", return_value=True),
        )

    def test_noncompleted_render_job_does_not_advance_to_assembly(self) -> None:
        episode = self._episode("Stale render")
        story = self._selected_story(episode.episode_id, "stale_render")
        story.workflow_state = StoryWorkflowState.timeline_approved
        self.repository.upsert_candidate(story)
        run = AutonomyRun(
            project_id=episode.project_id,
            episode_id=episode.episode_id,
            story_id=story.story_id,
            candidate_id=story.candidate_id,
            status=AutonomyRunStatus.running,
        )
        self.repository.upsert_autonomy_run(run)
        visual_job = self.repository.create_job(
            "visual_search",
            episode_id=episode.episode_id,
            story_id=story.story_id,
            autonomy_run_id=run.run_id,
        )
        visual_job.status = JobStatus.completed
        self.repository.upsert_job(visual_job)
        old_render = self.repository.create_job(
            "render_story",
            episode_id=episode.episode_id,
            story_id=story.story_id,
            autonomy_run_id=run.run_id,
            render_profile="production",
        )
        old_render.status = JobStatus.cancelled
        self.repository.upsert_job(old_render)

        patches = self._patch_ready_editorial_inputs(story.story_id)
        with patches[0], patches[1], patches[2], patches[3]:
            advanced = advance_autonomy_run(self.repository, run.run_id)

        renders = self.repository.list_jobs(
            autonomy_run_id=run.run_id,
            job_type="render_story",
        )
        assemblies = self.repository.list_jobs(
            autonomy_run_id=run.run_id,
            job_type="assemble_episode",
        )
        self.assertEqual(advanced.current_stage, "rendering")
        self.assertCountEqual(
            [job.status for job in renders],
            [JobStatus.cancelled, JobStatus.queued],
        )
        self.assertEqual(assemblies, [])

    def test_noncompleted_assembly_job_does_not_advance_to_final_qa(self) -> None:
        episode = self._episode("Stale assembly")
        story = self._selected_story(episode.episode_id, "stale_assembly")
        story.workflow_state = StoryWorkflowState.assembling
        self.repository.upsert_candidate(story)
        run = AutonomyRun(
            project_id=episode.project_id,
            episode_id=episode.episode_id,
            story_id=story.story_id,
            candidate_id=story.candidate_id,
            status=AutonomyRunStatus.running,
        )
        self.repository.upsert_autonomy_run(run)
        for job_type, status in (
            ("visual_search", JobStatus.completed),
            ("render_story", JobStatus.completed),
            ("assemble_episode", JobStatus.cancelled),
        ):
            job = self.repository.create_job(
                job_type,
                episode_id=episode.episode_id,
                story_id=story.story_id if job_type != "assemble_episode" else None,
                autonomy_run_id=run.run_id,
                render_profile="production",
            )
            job.status = status
            self.repository.upsert_job(job)

        patches = self._patch_ready_editorial_inputs(story.story_id)
        with patches[0], patches[1], patches[2], patches[3]:
            advanced = advance_autonomy_run(self.repository, run.run_id)

        assemblies = self.repository.list_jobs(
            autonomy_run_id=run.run_id,
            job_type="assemble_episode",
        )
        qa_jobs = self.repository.list_jobs(
            autonomy_run_id=run.run_id,
            job_type="final_video_qa",
        )
        self.assertEqual(advanced.current_stage, "assembling")
        self.assertCountEqual(
            [job.status for job in assemblies],
            [JobStatus.cancelled, JobStatus.queued],
        )
        self.assertEqual(qa_jobs, [])

    def test_visual_refresh_requires_a_fresh_timeline_before_rendering(self) -> None:
        episode = self._episode("Visual refresh")
        story = self._selected_story(episode.episode_id, "visual_refresh")
        story.workflow_state = StoryWorkflowState.timeline_approved
        self.repository.upsert_candidate(story)
        run = AutonomyRun(
            project_id=episode.project_id,
            episode_id=episode.episode_id,
            story_id=story.story_id,
            candidate_id=story.candidate_id,
            status=AutonomyRunStatus.running,
        )
        self.repository.upsert_autonomy_run(run)
        visual_job = self.repository.create_job(
            "visual_search",
            episode_id=episode.episode_id,
            story_id=story.story_id,
            autonomy_run_id=run.run_id,
        )
        visual_job.status = JobStatus.completed
        self.repository.upsert_job(visual_job)

        mark_visuals_revised(self.repository, story.story_id)
        self.assertEqual(
            self.repository.candidate_for_story(story.story_id).workflow_state,
            StoryWorkflowState.visuals_review,
        )
        patches = self._patch_ready_editorial_inputs(story.story_id)
        with patches[0], patches[1], patches[2], patches[3]:
            advanced = advance_autonomy_run(self.repository, run.run_id)

        timelines = self.repository.list_jobs(
            autonomy_run_id=run.run_id,
            job_type="timeline_generate",
        )
        renders = self.repository.list_jobs(
            autonomy_run_id=run.run_id,
            job_type="render_story",
        )
        self.assertEqual(advanced.current_stage, "building_timeline")
        self.assertEqual(len(timelines), 1)
        self.assertEqual(timelines[0].status, JobStatus.queued)
        self.assertEqual(renders, [])

    def test_final_video_qa_serializes_the_entire_episode(self) -> None:
        episode = self._episode("Episode QA lease")
        incumbent = self.repository.create_job(
            "render_story",
            episode_id=episode.episode_id,
            story_id="story_first",
        )
        incumbent.status = JobStatus.running
        self.repository.upsert_job(incumbent)
        qa = self.repository.create_job(
            "final_video_qa",
            episode_id=episode.episode_id,
            render_profile="production",
        )

        self.assertIsNone(self.repository.claim_next_job("render"))
        incumbent.status = JobStatus.completed
        self.repository.upsert_job(incumbent)
        claimed_qa = self.repository.claim_next_job("render")
        self.assertIsNotNone(claimed_qa)
        assert claimed_qa is not None
        self.assertEqual(claimed_qa.job_id, qa.job_id)

        later_render = self.repository.create_job(
            "render_story",
            episode_id=episode.episode_id,
            story_id="story_second",
        )
        self.assertIsNone(self.repository.claim_next_job("render"))
        claimed_qa.status = JobStatus.completed
        self.repository.upsert_job(claimed_qa)
        claimed_render = self.repository.claim_next_job("render")
        self.assertIsNotNone(claimed_render)
        assert claimed_render is not None
        self.assertEqual(claimed_render.job_id, later_render.job_id)

    def test_final_qa_rejects_an_mp4_that_changes_during_validation(self) -> None:
        episode = self._episode("Changed MP4")
        output = Path(self.temp.name) / "final.mp4"
        output.write_bytes(b"assembled-video")
        expected_digest = hashlib.sha256(output.read_bytes()).hexdigest()
        job = self.repository.create_job(
            "final_video_qa",
            episode_id=episode.episode_id,
            render_profile="production",
            payload={
                "final_output_path": str(output),
                "qa_report_path": str(Path(self.temp.name) / "final.qa.json"),
                "expected_width": 1920,
                "expected_height": 1080,
                "expected_fps": 30,
                "expected_output_sha256": expected_digest,
                "episode_revision_fingerprint": episode_revision_fingerprint(
                    self.repository, episode.episode_id
                ),
            },
        )
        report = FinalVideoQAReport(
            status="passed",
            passed=True,
            input_path=str(output),
            report_path=job.payload["qa_report_path"],
        )

        def mutate_output(*_args, **_kwargs):
            output.write_bytes(b"changed-during-qa")
            return report

        with patch(
            "pipeline.jobs.worker.run_final_video_qa",
            side_effect=mutate_output,
        ), self.assertRaisesRegex(ValueError, "changed during QA"):
            handle_final_video_qa(FakeQAContext(self.repository, job))

        self.assertIsNone(
            self.repository.get_episode(episode.episode_id).final_output_path
        )

    def test_final_qa_rejects_a_changed_episode_revision_fingerprint(self) -> None:
        episode = self._episode("Changed inputs")
        output = Path(self.temp.name) / "revision-final.mp4"
        output.write_bytes(b"stable-video")
        expected_digest = hashlib.sha256(output.read_bytes()).hexdigest()
        expected_revision = episode_revision_fingerprint(
            self.repository, episode.episode_id
        )
        episode.render_profile = "final_master"
        self.repository.upsert_episode(episode)
        job = self.repository.create_job(
            "final_video_qa",
            episode_id=episode.episode_id,
            render_profile="production",
            payload={
                "final_output_path": str(output),
                "qa_report_path": str(
                    Path(self.temp.name) / "revision-final.qa.json"
                ),
                "expected_width": 1920,
                "expected_height": 1080,
                "expected_fps": 30,
                "expected_output_sha256": expected_digest,
                "episode_revision_fingerprint": expected_revision,
            },
        )
        report = FinalVideoQAReport(
            status="passed",
            passed=True,
            input_path=str(output),
            report_path=job.payload["qa_report_path"],
        )

        with patch(
            "pipeline.jobs.worker.run_final_video_qa",
            return_value=report,
        ), self.assertRaisesRegex(ValueError, "Episode inputs changed"):
            handle_final_video_qa(FakeQAContext(self.repository, job))

        self.assertIsNone(
            self.repository.get_episode(episode.episode_id).final_output_path
        )

    def test_green_only_policy_blocks_every_asset_that_is_not_preapproved_safe(
        self
    ) -> None:
        story_id = "story_rights_policy"
        safe = VisualCandidate(
            asset_id="visual_safe",
            story_id=story_id,
            provider="generated_fallback",
            media_type=MediaType.fallback,
            rights_tier=RightsTier.green,
            review_status=ReviewStatus.approved,
            manual_review_flag=False,
            approval_blockers=[],
        )
        yellow = VisualCandidate(
            asset_id="visual_yellow",
            story_id=story_id,
            provider="search",
            media_type=MediaType.image,
            rights_tier=RightsTier.yellow,
            review_status=ReviewStatus.manual_approved,
            manual_review_flag=False,
            approval_blockers=[],
        )
        blocked_green = VisualCandidate(
            asset_id="visual_green_with_blocker",
            story_id=story_id,
            provider="search",
            media_type=MediaType.video,
            rights_tier=RightsTier.green,
            review_status=ReviewStatus.approved,
            manual_review_flag=False,
            approval_blockers=["contains third-party logo"],
        )
        for visual in (safe, yellow, blocked_green):
            self.repository.upsert_visual(visual)

        blocked_count = enforce_green_only_visuals(self.repository, story_id)

        self.assertEqual(blocked_count, 2)
        self.assertEqual(
            self.repository.get_visual(safe.asset_id).review_status,
            ReviewStatus.approved,
        )
        for asset_id in (yellow.asset_id, blocked_green.asset_id):
            blocked = self.repository.get_visual(asset_id)
            self.assertEqual(blocked.review_status, ReviewStatus.blocked)
            self.assertTrue(
                any("green-only rights policy" in warning for warning in blocked.warnings)
            )

    def test_reconciliation_contains_one_run_failure_and_advances_the_next(self) -> None:
        broken_episode = self._episode("Broken")
        healthy_episode = self._episode("Healthy")
        broken = AutonomyRun(
            project_id=broken_episode.project_id,
            episode_id=broken_episode.episode_id,
            story_id="story_that_does_not_exist",
        )
        healthy = AutonomyRun(
            project_id=healthy_episode.project_id,
            episode_id=healthy_episode.episode_id,
        )
        self.repository.upsert_autonomy_run(broken)
        self.repository.upsert_autonomy_run(healthy)

        reconciled = reconcile_autonomy_runs(self.repository)

        persisted_broken = self.repository.get_autonomy_run(broken.run_id)
        persisted_healthy = self.repository.get_autonomy_run(healthy.run_id)
        self.assertEqual(reconciled, 2)
        self.assertEqual(
            persisted_broken.status, AutonomyRunStatus.needs_attention
        )
        self.assertIn("Autonomy reconciliation failed", persisted_broken.error or "")
        self.assertEqual(persisted_healthy.status, AutonomyRunStatus.running)
        self.assertEqual(persisted_healthy.current_stage, "discovering")
        healthy_jobs = self.repository.list_jobs(
            autonomy_run_id=persisted_healthy.run_id
        )
        self.assertEqual([job.job_type for job in healthy_jobs], ["discovery"])

    def test_review_gate_allows_each_decision_only_after_final_qa_handoff(self) -> None:
        accepted_episode = self._episode("Accepted")
        accepted = AutonomyRun(
            project_id=accepted_episode.project_id,
            episode_id=accepted_episode.episode_id,
            status=AutonomyRunStatus.ready_for_review,
            current_stage="ready_for_review",
            progress=100,
            final_output_path="episodes/accepted/final.mp4",
            qa={"passed": True, "status": "passed"},
        )
        self.repository.upsert_autonomy_run(accepted)

        reviewed = review_autonomy_run(
            self.repository, accepted.run_id, AutonomyRunStatus.accepted
        )
        self.assertEqual(reviewed.status, AutonomyRunStatus.accepted)
        self.assertIsNotNone(reviewed.reviewed_at)
        self.assertIsNone(
            self.repository.unreviewed_autonomy_run(accepted_episode.episode_id)
        )
        with self.assertRaisesRegex(ValueError, "ready-for-review"):
            review_autonomy_run(
                self.repository, accepted.run_id, AutonomyRunStatus.rejected
            )

        rejected_episode = self._episode("Rejected")
        rejected = AutonomyRun(
            project_id=rejected_episode.project_id,
            episode_id=rejected_episode.episode_id,
            status=AutonomyRunStatus.ready_for_review,
            current_stage="ready_for_review",
            progress=100,
        )
        self.repository.upsert_autonomy_run(rejected)
        reviewed = review_autonomy_run(
            self.repository, rejected.run_id, AutonomyRunStatus.rejected
        )
        self.assertEqual(reviewed.status, AutonomyRunStatus.rejected)


class AutonomyAPITests(unittest.TestCase):
    def test_http_create_and_list_use_the_durable_default_hermes_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "autonomy-api.sqlite3"
            repository = Repository(db_path)
            project = repository.create_project("API autonomy")
            episode = repository.create_episode(project.project_id, "API night shift")
            repository.close()

            app = FastAPI()
            app.include_router(autonomy_router)
            client = TestClient(app)

            def repository_factory() -> Repository:
                return Repository(db_path)

            with patch(
                "pipeline.api.routes.autonomy.get_repository",
                side_effect=repository_factory,
            ), patch(
                "pipeline.autonomy.provider_availability",
                return_value=AVAILABLE_HERMES,
            ):
                created = client.post(
                    "/api/autonomy/runs",
                    json={
                        "episode_id": episode.episode_id,
                        "target_duration_seconds": 420,
                        "max_repairs_per_stage": 1,
                    },
                )
                self.assertEqual(created.status_code, 200, created.text)
                payload = created.json()
                self.assertEqual(payload["engine"], "hermes")
                self.assertEqual(payload["policy"]["duration_mode"], "adaptive")
                self.assertEqual(payload["status"], "running")
                self.assertEqual(payload["current_stage"], "discovering")
                self.assertFalse(payload["policy"]["upload_enabled"])

                listed = client.get(
                    "/api/autonomy/runs",
                    params={"episode_id": episode.episode_id},
                )
                self.assertEqual(listed.status_code, 200, listed.text)
                runs = listed.json()
                self.assertEqual(len(runs), 1)
                self.assertEqual(runs[0]["run_id"], payload["run_id"])
                self.assertEqual(runs[0]["active_job_ids"], payload["active_job_ids"])

            verification = Repository(db_path)
            try:
                persisted = verification.get_autonomy_run(payload["run_id"])
                jobs = verification.list_jobs(autonomy_run_id=persisted.run_id)
                self.assertEqual(persisted.engine, "hermes")
                self.assertEqual(len(jobs), 1)
                self.assertEqual(jobs[0].max_attempts, 2)
            finally:
                verification.close()


if __name__ == "__main__":
    unittest.main()
