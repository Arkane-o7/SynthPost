from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pipeline.db.repository import Repository
from pipeline.discovery.discover import (
    add_manual_story,
    canonicalize_url,
    discover,
    duplicate_group,
    fetch_feed,
    normalize_title,
    score_candidate,
)
from pipeline.discovery.assignment_desk import (
    apply_assignment_desk,
    cluster_candidates,
)
from pipeline.editorial.charter import CHARTER_VERSION, assess_editorial_fit
from pipeline.manifest_builder import (
    build_story_manifest,
    hydrate_timeline_visuals,
    timeline_narration_text,
)
from pipeline.models import (
    ApprovalStatus,
    AudioMode,
    ContentRole,
    EpisodeStatus,
    JobStatus,
    MediaType,
    NarrativeArcItem,
    NarrativeBeat,
    NarrativeBrief,
    NarrativeDraft,
    NarrationArtifact,
    NarrationBeatTiming,
    NarrationSectionTiming,
    NarrationMode,
    Claim,
    ResearchPack,
    ReviewStatus,
    RightsTier,
    ScriptDocument,
    ScriptSection,
    SegmentAnchor,
    SegmentAudio,
    SegmentOverlays,
    SegmentTemplate,
    SegmentVisual,
    SourceDefinition,
    SourceClipCue,
    SourceType,
    StoryCandidate,
    StorySelectionStatus,
    StoryWorkflowState,
    TimelinePlan,
    TimelineSegment,
    VisualCandidate,
    narration_beats,
    timed_section_headline_cues,
)
from pipeline.research.extract import build_research_pack
from pipeline.narration.service import generate_narration
from pipeline.run_story import _sync_timeline_to_avatar_duration
from pipeline.scripts.generation import (
    approve_script,
    reconcile_script_revision_workflows,
    save_manual_script,
)
from pipeline.scripts.generation import (
    compact_research_pack_for_prompt,
    _validate_narrative_draft,
    _validate_narrative_segmentation,
    expand_long_form_script,
    generation_prompt,
    narrative_quality_issues,
    narrative_research_pack_for_prompt,
    script_from_narrative,
    script_from_llm_json,
    section_word_targets,
    generate_script,
    validate_grounding,
)
from pipeline.llm.providers import MockProvider, StructuredGenerationError
from pipeline.storage import (
    PROJECT_ROOT,
    episode_media_inbox_dir,
    resolve_project_path,
)
from pipeline.timeline.planner import (
    approved_visuals_by_section,
    approve_timeline,
    choose_template,
    choose_audio_mode,
    generate_timeline,
    select_template,
)
from pipeline.timeline.templates import (
    TEMPLATE_REGISTRY,
    template_compatible,
    template_registry_json,
)
from pipeline.timeline.validation import validate_timeline
from pipeline.visuals.providers import (
    _result_matches_query,
    _validate_ai_visual_plan,
    _visual_search_plan,
    _visual_search_queries,
    _visual_search_tasks,
    approve_visual,
    search_episode_media_inbox,
    stage_local_visual,
    update_visual,
)
from pipeline.workflow import assert_transition, can_transition
from pipeline.jobs.worker import (
    HANDLERS,
    _restore_script_state_after_terminal_failure,
    handle_assemble_episode,
    recover_stale_jobs,
    run_one,
)
from pipeline.jobs.policy import classify_failure
from assembly.stitch_episode import story_manifests


def exact_test_narration(script: ScriptDocument) -> NarrationArtifact:
    """Build a compact sample-derived artifact for isolated planner tests."""

    raw = [
        (section, beat)
        for section in script.sections
        for beat in section.beats
    ]
    timings: list[NarrationBeatTiming] = []
    cursor = 0
    for section, beat in raw:
        speech_end = cursor + 24_000
        end = speech_end + (1_920 if beat is not raw[-1][1] else 0)
        timings.append(
            NarrationBeatTiming(
                beat_id=beat.beat_id,
                section_id=section.section_id,
                text=beat.text,
                start_time=cursor / 24_000,
                speech_end_time=speech_end / 24_000,
                end_time=end / 24_000,
                pause_after_seconds=(end - speech_end) / 24_000,
                start_sample=cursor,
                speech_end_sample=speech_end,
                end_sample=end,
            )
        )
        cursor = end
    sections = []
    for section in script.sections:
        beats = [beat for beat in timings if beat.section_id == section.section_id]
        sections.append(
            NarrationSectionTiming(
                section_id=section.section_id,
                beat_ids=[beat.beat_id for beat in beats],
                start_time=beats[0].start_time,
                speech_end_time=beats[-1].speech_end_time,
                end_time=beats[-1].end_time,
                duration_seconds=beats[-1].end_time - beats[0].start_time,
            )
        )
    return NarrationArtifact(
        story_id=script.story_id,
        episode_id="episode_test",
        script_id=script.script_id,
        script_version=script.version,
        input_hash="test",
        voice_id="af_heart",
        voice_speed=1.1,
        language_code="a",
        sample_rate=24_000,
        audio_path=__file__,
        duration_seconds=cursor / 24_000,
        beats=timings,
        sections=sections,
    )


class V2WorkflowAndPipelineTests(unittest.TestCase):
    def test_feed_fetch_enforces_a_hard_curl_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch(
            "pipeline.discovery.discover.CACHE_DIR", Path(temp)
        ), patch(
            "pipeline.discovery.discover.shutil.which", return_value="/usr/bin/curl"
        ), patch(
            "pipeline.discovery.discover.subprocess.run",
            side_effect=subprocess.TimeoutExpired("curl", 2),
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                fetch_feed("https://hung-feed.example/rss", timeout=2)

    def test_worker_recovers_abandoned_running_jobs(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "stale-jobs.sqlite3")
        try:
            job = repository.create_job("discovery")
            job.status = JobStatus.running
            job.stage = "loading sources"
            job.updated_at = "2020-01-01T00:00:00Z"
            data = job.model_dump(mode="json")
            repository.connection.execute(
                "UPDATE render_jobs SET status = ?, stage = ?, data = ?, updated_at = ? WHERE job_id = ?",
                (
                    "running",
                    job.stage,
                    json.dumps(data),
                    job.updated_at,
                    job.job_id,
                ),
            )

            self.assertEqual(recover_stale_jobs(repository), 1)
            recovered = repository.get_job(job.job_id)
            self.assertEqual(recovered.status, JobStatus.queued)
            self.assertEqual(recovered.stage, "retry_wait")
            self.assertEqual(recovered.failure_kind, "worker_lost")
            self.assertIsNotNone(recovered.available_at)
        finally:
            repository.close()
            temp.cleanup()

    def test_stale_job_fails_after_automatic_retry_budget_is_exhausted(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "stale-exhausted.sqlite3")
        try:
            job = repository.create_job("render_story")
            job.status = JobStatus.running
            job.attempts = job.max_attempts
            job.updated_at = "2020-01-01T00:00:00Z"
            data = job.model_dump(mode="json")
            repository.connection.execute(
                "UPDATE render_jobs SET status = ?, attempts = ?, data = ?, updated_at = ? WHERE job_id = ?",
                (
                    "running",
                    job.attempts,
                    json.dumps(data),
                    job.updated_at,
                    job.job_id,
                ),
            )

            self.assertEqual(recover_stale_jobs(repository, "render"), 1)
            recovered = repository.get_job(job.job_id)
            self.assertEqual(recovered.status, JobStatus.failed)
            self.assertEqual(recovered.stage, "failed_stale_worker")
        finally:
            repository.close()
            temp.cleanup()

    def test_queue_lanes_claim_independently(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "lane-jobs.sqlite3")
        try:
            render = repository.create_job("render_story")
            editorial = repository.create_job("research")
            media = repository.create_job("visual_search")

            editorial_claim = repository.claim_next_job("editorial")
            media_claim = repository.claim_next_job("media")
            render_claim = repository.claim_next_job("render")

            self.assertEqual(editorial_claim.job_id, editorial.job_id)
            self.assertEqual(media_claim.job_id, media.job_id)
            self.assertEqual(render_claim.job_id, render.job_id)
            self.assertEqual(editorial_claim.attempts, 1)
            self.assertEqual(media_claim.attempts, 1)
            self.assertEqual(render_claim.attempts, 1)
        finally:
            repository.close()
            temp.cleanup()

    def test_parallel_claims_allow_independent_episodes(self) -> None:
        temp = tempfile.TemporaryDirectory()
        db_path = Path(temp.name) / "parallel-episodes.sqlite3"
        first = Repository(db_path)
        second = Repository(db_path)
        try:
            first_job = first.create_job(
                "render_story", episode_id="ep_alpha", story_id="story_alpha"
            )
            second_job = first.create_job(
                "render_story", episode_id="ep_beta", story_id="story_beta"
            )

            first_claim = first.claim_next_job("render")
            second_claim = second.claim_next_job("render")

            self.assertEqual(first_claim.job_id, first_job.job_id)
            self.assertEqual(second_claim.job_id, second_job.job_id)
            self.assertEqual(first_claim.status, JobStatus.running)
            self.assertEqual(second_claim.status, JobStatus.running)
        finally:
            first.close()
            second.close()
            temp.cleanup()

    def test_parallel_claims_serialize_stages_for_the_same_story(self) -> None:
        temp = tempfile.TemporaryDirectory()
        db_path = Path(temp.name) / "same-story.sqlite3"
        first = Repository(db_path)
        second = Repository(db_path)
        try:
            avatar = first.create_job(
                "render_avatar", episode_id="ep_one", story_id="story_one"
            )
            composition = first.create_job(
                "render_story", episode_id="ep_one", story_id="story_one"
            )

            claimed_avatar = first.claim_next_job("render")
            self.assertEqual(claimed_avatar.job_id, avatar.job_id)
            self.assertIsNone(second.claim_next_job("render"))

            claimed_avatar.status = JobStatus.completed
            self.assertTrue(
                first.update_job_if_status(claimed_avatar, JobStatus.running)
            )
            claimed_composition = second.claim_next_job("render")
            self.assertEqual(claimed_composition.job_id, composition.job_id)
        finally:
            first.close()
            second.close()
            temp.cleanup()

    def test_assembly_is_exclusive_with_story_work_in_its_episode(self) -> None:
        temp = tempfile.TemporaryDirectory()
        db_path = Path(temp.name) / "assembly-exclusive.sqlite3"
        first = Repository(db_path)
        second = Repository(db_path)
        try:
            story = first.create_job(
                "render_story", episode_id="ep_one", story_id="story_one"
            )
            first.create_job("assemble_episode", episode_id="ep_one")
            other_episode = first.create_job(
                "render_story", episode_id="ep_two", story_id="story_two"
            )

            self.assertEqual(first.claim_next_job("render").job_id, story.job_id)
            # The assembly job is blocked, but unrelated episode work remains eligible.
            self.assertEqual(
                second.claim_next_job("render").job_id, other_episode.job_id
            )
            self.assertIsNone(first.claim_next_job("render"))
        finally:
            first.close()
            second.close()
            temp.cleanup()

    def test_automatic_retry_waits_for_backoff_and_preserves_last_error(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "retry-jobs.sqlite3")
        try:
            job = repository.create_job("research")
            with patch.dict(
                HANDLERS,
                {"research": Mock(side_effect=TimeoutError("upstream timed out"))},
            ), patch.dict(
                "os.environ",
                {"SYNTHPOST_JOB_RETRY_BASE_SECONDS": "60"},
            ):
                self.assertTrue(run_one(repository, "editorial"))

            retrying = repository.get_job(job.job_id)
            self.assertEqual(retrying.status, JobStatus.queued)
            self.assertEqual(retrying.stage, "retry_wait")
            self.assertEqual(retrying.failure_kind, "timeout")
            self.assertEqual(retrying.last_error, "upstream timed out")
            self.assertEqual(retrying.attempts, 1)
            self.assertIsNotNone(retrying.available_at)
            self.assertIsNone(repository.claim_next_job("editorial"))
        finally:
            repository.close()
            temp.cleanup()

    def test_deterministic_validation_failure_does_not_retry(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "permanent-job.sqlite3")
        try:
            job = repository.create_job("research")
            with patch.dict(
                HANDLERS,
                {"research": Mock(side_effect=ValueError("invalid research input"))},
            ):
                self.assertTrue(run_one(repository, "editorial"))

            failed = repository.get_job(job.job_id)
            self.assertEqual(failed.status, JobStatus.failed)
            self.assertEqual(failed.failure_kind, "validation")
            self.assertEqual(failed.attempts, 1)
            self.assertIsNone(failed.available_at)
        finally:
            repository.close()
            temp.cleanup()

    def test_retry_policy_distinguishes_quota_from_missing_provider_package(self) -> None:
        quota = classify_failure(
            "script_generate",
            1,
            ValueError("429 RESOURCE_EXHAUSTED; retryDelay: 38s"),
        )
        configuration = classify_failure(
            "script_generate",
            1,
            ValueError("google-genai package is required to use GeminiProvider"),
        )

        self.assertTrue(quota.retryable)
        self.assertEqual(quota.kind, "rate_limited")
        self.assertGreaterEqual(quota.delay_seconds, 38)
        self.assertFalse(configuration.retryable)
        self.assertEqual(configuration.kind, "configuration")

    def test_queue_claim_is_exclusive_and_cancelled_job_cannot_be_resurrected(
        self,
    ) -> None:
        temp = tempfile.TemporaryDirectory()
        db_path = Path(temp.name) / "atomic-jobs.sqlite3"
        first = Repository(db_path)
        second = Repository(db_path)
        try:
            queued = first.create_job("discovery")
            claimed = first.claim_next_job()
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.job_id, queued.job_id)
            self.assertIsNone(second.claim_next_job())

            cancelled = second.get_job(queued.job_id)
            cancelled.status = JobStatus.cancelled
            cancelled.stage = "cancelled"
            second.upsert_job(cancelled)

            claimed.status = JobStatus.completed
            claimed.stage = "completed"
            self.assertFalse(
                first.update_job_if_status(claimed, JobStatus.running)
            )
            self.assertEqual(
                first.get_job(queued.job_id).status, JobStatus.cancelled
            )
        finally:
            first.close()
            second.close()
            temp.cleanup()

    def test_job_heartbeat_preserves_authoritative_status(self) -> None:
        temp = tempfile.TemporaryDirectory()
        db_path = Path(temp.name) / "heartbeat-jobs.sqlite3"
        worker = Repository(db_path)
        controller = Repository(db_path)
        try:
            job = worker.create_job("visual_search")
            claimed = worker.claim_next_job()
            self.assertIsNotNone(claimed)
            self.assertEqual(
                worker.heartbeat_job(job.job_id), JobStatus.running
            )

            cancelled = controller.get_job(job.job_id)
            cancelled.status = JobStatus.cancelled
            cancelled.stage = "cancelled"
            controller.upsert_job(cancelled)
            self.assertEqual(
                worker.heartbeat_job(job.job_id), JobStatus.cancelled
            )
        finally:
            worker.close()
            controller.close()
            temp.cleanup()

    def test_split_anchor_accepts_primary_video_footage(self) -> None:
        self.assertTrue(
            template_compatible(
                "split_anchor_visual", "video", "primary_footage"
            )
        )

    def test_paused_job_stays_out_of_worker_queue_until_resumed(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "paused-job.sqlite3")
        try:
            project = repository.create_project("Remote control")
            episode = repository.create_episode(project.project_id, "Phone episode")
            job = repository.create_job(
                "assemble_episode",
                episode_id=episode.episode_id,
                render_profile="production",
            )
            job.status = JobStatus.paused
            job.stage = "paused_by_editor"
            repository.upsert_job(job)

            self.assertIsNone(repository.claim_next_job())

            job.status = JobStatus.queued
            job.stage = "queued_after_pause"
            repository.upsert_job(job)
            claimed = repository.claim_next_job()
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.job_id, job.job_id)
            self.assertEqual(claimed.status, JobStatus.running)
        finally:
            repository.close()
            temp.cleanup()

    def test_episode_candidate_listing_excludes_global_and_other_episode_rows(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "candidate-isolation.sqlite3")
        try:
            project = repository.create_project("Candidate isolation")
            episode_a = repository.create_episode(project.project_id, "Episode A")
            episode_b = repository.create_episode(project.project_id, "Episode B")
            candidate_a = add_manual_story(
                repository,
                title="Episode A story",
                body="Only A should see this.",
                episode_id=episode_a.episode_id,
            )
            repository.select_candidate(candidate_a.candidate_id, episode_a.episode_id)
            suggested_a = add_manual_story(
                repository,
                title="Higher-scored Episode A suggestion",
                body="This remains only a suggestion.",
                episode_id=episode_a.episode_id,
            )
            suggested_a.final_score = 1.0
            repository.upsert_candidate(suggested_a)
            add_manual_story(
                repository,
                title="Episode B story",
                body="Only B should see this.",
                episode_id=episode_b.episode_id,
            )
            add_manual_story(
                repository,
                title="Unassigned story",
                body="This is not attached to an episode.",
            )

            rows = repository.list_candidates(episode_id=episode_a.episode_id)

            self.assertEqual(rows[0].candidate_id, candidate_a.candidate_id)
            self.assertEqual(
                {row.candidate_id for row in rows},
                {candidate_a.candidate_id, suggested_a.candidate_id},
            )
        finally:
            repository.close()
            temp.cleanup()

    def test_local_visual_search_is_isolated_by_project_and_episode(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "isolated-media.sqlite3")
        project_dirs: list[Path] = []
        try:
            source = (
                PROJECT_ROOT
                / "compositor"
                / "remotion_renderer"
                / "public"
                / "news"
                / "datacenter-server-racks.jpg"
            )
            story_ids: list[str] = []
            inboxes: list[Path] = []
            for index in range(2):
                project = repository.create_project(f"Isolated Project {index}")
                episode = repository.create_episode(
                    project.project_id, f"Episode {index}"
                )
                candidate = add_manual_story(
                    repository,
                    title=f"Isolated story {index}",
                    body="A scoped media test story.",
                    episode_id=episode.episode_id,
                )
                selected = repository.select_candidate(
                    candidate.candidate_id, episode.episode_id
                )
                assert selected.story_id is not None
                story_ids.append(selected.story_id)
                inbox = episode_media_inbox_dir(
                    project.project_id, episode.episode_id
                )
                inbox.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, inbox / f"episode-{index}.jpg")
                inboxes.append(inbox)
                project_dirs.append(PROJECT_ROOT / "projects" / project.project_id)

            visuals = search_episode_media_inbox(
                repository, story_ids[0], generate_fallback=False
            )
            self.assertEqual(len(visuals), 1)
            self.assertTrue(visuals[0].source_url.endswith("episode-0.jpg"))
            self.assertNotIn("episode-1.jpg", visuals[0].source_url)
        finally:
            repository.close()
            temp.cleanup()
            for directory in project_dirs:
                shutil.rmtree(directory, ignore_errors=True)

    def test_same_named_inbox_files_get_distinct_story_media_paths(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "same-name-media.sqlite3")
        project_dir: Path | None = None
        episode_id = ""
        try:
            project = repository.create_project("Same-name media")
            project_dir = PROJECT_ROOT / "projects" / project.project_id
            episode = repository.create_episode(project.project_id, "Episode")
            episode_id = episode.episode_id
            candidate = add_manual_story(
                repository,
                title="Same-name media story",
                body="Two source folders may contain files with the same name.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id
            inbox = episode_media_inbox_dir(project.project_id, episode.episode_id)
            first = inbox / "first" / "image.jpg"
            second = inbox / "second" / "image.jpg"
            first.parent.mkdir(parents=True, exist_ok=True)
            second.parent.mkdir(parents=True, exist_ok=True)
            first.write_bytes(b"first-image")
            second.write_bytes(b"second-image")

            first_visual = stage_local_visual(repository, selected.story_id, first)
            second_visual = stage_local_visual(repository, selected.story_id, second)

            self.assertNotEqual(first_visual.asset_id, second_visual.asset_id)
            self.assertNotEqual(first_visual.download_path, second_visual.download_path)
            self.assertEqual(
                resolve_project_path(first_visual.download_path or "").read_bytes(),
                b"first-image",
            )
            self.assertEqual(
                resolve_project_path(second_visual.download_path or "").read_bytes(),
                b"second-image",
            )
        finally:
            repository.close()
            temp.cleanup()
            if episode_id:
                shutil.rmtree(
                    PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True
                )
            if project_dir is not None:
                shutil.rmtree(project_dir, ignore_errors=True)

    def test_staging_external_media_imports_it_into_the_active_episode(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "media-import.sqlite3")
        project_dir: Path | None = None
        episode_id = ""
        try:
            project = repository.create_project("Scoped imports")
            project_dir = PROJECT_ROOT / "projects" / project.project_id
            episode = repository.create_episode(project.project_id, "One episode")
            episode_id = episode.episode_id
            candidate = add_manual_story(
                repository,
                title="Scoped import story",
                body="A local file should be copied into this episode only.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id is not None
            external = (
                PROJECT_ROOT
                / "compositor"
                / "remotion_renderer"
                / "public"
                / "news"
                / "datacenter-server-racks.jpg"
            )

            visual = stage_local_visual(repository, selected.story_id, external)

            inbox = episode_media_inbox_dir(project.project_id, episode.episode_id)
            imported = resolve_project_path(visual.source_url or "")
            self.assertTrue(imported.is_relative_to(inbox.resolve()))
            self.assertTrue(imported.exists())
            self.assertNotEqual(imported, external.resolve())
            self.assertIn("datacenter-server-racks.jpg", visual.attribution_text)
        finally:
            repository.close()
            temp.cleanup()
            if project_dir is not None:
                shutil.rmtree(project_dir, ignore_errors=True)
            if episode_id:
                shutil.rmtree(
                    PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True
                )

    def test_local_media_rescan_preserves_decision_until_file_changes(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "media-rescan.sqlite3")
        episode_id = ""
        project_dir: Path | None = None
        try:
            project = repository.create_project("Rescan decisions")
            project_dir = PROJECT_ROOT / "projects" / project.project_id
            episode = repository.create_episode(project.project_id, "Episode")
            episode_id = episode.episode_id
            candidate = add_manual_story(
                repository,
                title="Local media rescan",
                body="The same local visual may be scanned more than once.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id
            source = Path(temp.name) / "editor-image.jpg"
            source.write_bytes(b"first-image")

            staged = stage_local_visual(repository, selected.story_id, source)
            approved = approve_visual(repository, staged.asset_id, manual=True)
            rescanned = stage_local_visual(repository, selected.story_id, source)

            self.assertEqual(rescanned.review_status, ReviewStatus.manual_approved)
            self.assertEqual(rescanned.reviewed_at, approved.reviewed_at)

            source.write_bytes(b"replacement-image-with-different-size")
            replaced = stage_local_visual(repository, selected.story_id, source)

            self.assertEqual(replaced.asset_id, staged.asset_id)
            self.assertEqual(replaced.review_status, ReviewStatus.suggested)
            self.assertIsNone(replaced.reviewed_at)
            self.assertEqual(
                resolve_project_path(replaced.thumbnail_path or "").read_bytes(),
                source.read_bytes(),
            )
        finally:
            repository.close()
            temp.cleanup()
            if episode_id:
                shutil.rmtree(
                    PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True
                )
            if project_dir is not None:
                shutil.rmtree(project_dir, ignore_errors=True)

    def test_long_form_script_expands_in_section_sized_chunks(self) -> None:
        outline = ScriptDocument(
            story_id="story_long_form",
            headline="Hydrogen train pilot",
            sections=[
                ScriptSection(
                    section_id="sec_001_cold_open",
                    section_type="cold_open",
                    text="A grounded hydrogen train pilot is beginning.",
                    claim_ids=["claim_001"],
                )
            ],
        )
        pack = {
            "story_id": "story_long_form",
            "research_summary": "A sourced pilot briefing.",
            "documents": [],
            "claims": [
                {
                    "claim_id": "claim_001",
                    "claim_text": "The hydrogen train pilot is documented.",
                }
            ],
            "evidence": [],
        }

        expanded, attempts = expand_long_form_script(
            MockProvider(), outline, pack, target_duration_seconds=600
        )

        self.assertEqual(len(expanded.sections), 9)
        self.assertGreaterEqual(expanded.estimated_duration_seconds, 590)
        self.assertLessEqual(expanded.estimated_duration_seconds, 610)
        self.assertEqual(attempts, 9)
        self.assertEqual(
            expanded.lower_thirds,
            [section.lower_third for section in expanded.sections],
        )
        self.assertEqual(
            expanded.chyrons,
            [section.chyron for section in expanded.sections],
        )

    def test_narrative_quality_gate_rejects_vimag_style_restarts(self) -> None:
        draft = NarrativeDraft(
            headline="Vimag Labs magnet-free motor",
            beats=[
                NarrativeBeat(
                    beat_id="beat_001",
                    text=(
                        "In a modest Bengaluru lab, engineers watch a prototype "
                        "motor spin silently without a permanent magnet."
                    ),
                ),
                NarrativeBeat(
                    beat_id="beat_002",
                    text=(
                        "In a Bengaluru lab, engineers fire up a prototype motor "
                        "that never touches a rare-earth magnet."
                    ),
                ),
                NarrativeBeat(
                    beat_id="beat_003",
                    text=(
                        "In a Bengaluru lab, engineers watch the prototype motor "
                        "spin silently as electronic controls create its field."
                    ),
                ),
                NarrativeBeat(
                    beat_id="beat_004",
                    text=(
                        "In a Bangalore lab, engineers fire a pulse through the "
                        "prototype motor and watch the rotor spin."
                    ),
                ),
                NarrativeBeat(
                    beat_id="beat_005",
                    text=(
                        "The production test remains unresolved. investors will "
                        "watch the company's rollout for evidence."
                    ),
                ),
            ],
        )

        issues = narrative_quality_issues(draft)

        self.assertTrue(
            any("same scene or framing" in issue for issue in issues), issues
        )
        self.assertTrue(
            any("lowercase" in issue for issue in issues), issues
        )

    def test_narrative_research_projection_excludes_unrelated_search_claims(self) -> None:
        pack = {
            "research_summary": "Vimag Labs develops a magnet-free electric motor. Reviewed sources.",
            "claims": [
                {
                    "claim_id": "claim_motor",
                    "claim_text": "Vimag Labs develops a magnet-free electric motor.",
                    "evidence_ids": ["ev_motor"],
                    "supported": True,
                },
                {
                    "claim_id": "claim_patent",
                    "claim_text": "The magnet-free motor uses electronic field control.",
                    "evidence_ids": ["ev_patent"],
                    "supported": True,
                },
                {
                    "claim_id": "claim_health",
                    "claim_text": "India announced a separate medical research programme.",
                    "evidence_ids": ["ev_health"],
                    "supported": True,
                },
            ],
            "evidence": [
                {
                    "evidence_id": "ev_motor",
                    "document_id": "doc_motor",
                    "excerpt": "Vimag's magnet-free electric motor is being tested.",
                },
                {
                    "evidence_id": "ev_patent",
                    "document_id": "doc_motor",
                    "excerpt": "The motor controls its magnetic field electronically.",
                },
                {
                    "evidence_id": "ev_health",
                    "document_id": "doc_health",
                    "excerpt": "A medical research programme was announced.",
                },
            ],
            "documents": [
                {
                    "document_id": "doc_motor",
                    "title": "Vimag magnet-free electric motor",
                    "content_text": "Complete lead article about Vimag's motor.",
                },
                {
                    "document_id": "doc_health",
                    "title": "India medical research programme",
                    "content_text": "Complete second-ranked article body.",
                },
                {
                    "document_id": "doc_third",
                    "title": "Third-ranked source",
                    "content_text": "Complete third-ranked article body.",
                },
                {
                    "document_id": "doc_fourth",
                    "title": "Fourth-ranked source",
                    "content_text": "Complete fourth-ranked article body.",
                },
                {
                    "document_id": "doc_fifth",
                    "title": "Fifth-ranked source",
                    "content_text": "Lower-ranked article body.",
                },
            ],
            "systems": ["ai", "electric motor supply chain"],
            "trade_offs": [
                "The motor controls its magnetic field electronically.",
                "Magnet export restrictions forced automakers to cut production.",
            ],
        }

        projected = narrative_research_pack_for_prompt(pack)

        self.assertEqual(
            {claim["claim_id"] for claim in projected["claims"]},
            {"claim_motor", "claim_patent"},
        )
        self.assertEqual(
            {document["document_id"] for document in projected["documents"]},
            {"doc_motor", "doc_health", "doc_third", "doc_fourth"},
        )
        self.assertEqual(
            projected["documents"][0]["content_text"],
            "Complete lead article about Vimag's motor.",
        )
        self.assertEqual(
            projected["documents"][1]["content_text"],
            "Complete second-ranked article body.",
        )
        self.assertEqual(
            projected["documents"][2]["content_text"],
            "Complete third-ranked article body.",
        )
        self.assertEqual(
            projected["documents"][3]["content_text"],
            "Complete fourth-ranked article body.",
        )
        self.assertNotIn("ai", projected["systems"])
        self.assertNotIn(
            "Magnet export restrictions forced automakers to cut production.",
            projected["trade_offs"],
        )
        self.assertIn(
            "The motor controls its magnetic field electronically.",
            projected["trade_offs"],
        )

    def test_narrative_contract_rejects_spoken_claim_ids(self) -> None:
        pack = {
            "research_summary": "Vimag Labs develops a magnet-free motor.",
            "claims": [
                {
                    "claim_id": "claim_001",
                    "claim_text": "Vimag Labs develops a magnet-free motor.",
                    "supported": True,
                    "evidence_ids": [],
                }
            ],
            "evidence": [],
            "documents": [],
        }
        raw = {
            "headline": "Magnet-free motor",
            "dek": "A documented development.",
            "category": "news",
            "beats": [
                {
                    "beat_id": "one",
                    "text": "Vimag says its motor avoids permanent magnets (claim_001).",
                    "claim_ids": ["claim_001"],
                },
                {
                    "beat_id": "two",
                    "text": "Electronic controls generate the field instead.",
                    "claim_ids": ["claim_001"],
                },
                {
                    "beat_id": "three",
                    "text": "Commercial performance remains to be tested.",
                    "claim_ids": ["claim_001"],
                },
            ],
        }

        with self.assertRaisesRegex(ValueError, "internal claim/evidence ID"):
            _validate_narrative_draft(raw, pack, target_duration_seconds=10)

    def test_narrative_contract_requires_claim_link_on_every_beat(self) -> None:
        pack = {
            "research_summary": "Vimag Labs develops a magnet-free motor.",
            "claims": [
                {
                    "claim_id": "claim_001",
                    "claim_text": "Vimag Labs develops a magnet-free motor.",
                    "supported": True,
                    "evidence_ids": [],
                }
            ],
            "evidence": [],
            "documents": [],
        }
        raw = {
            "headline": "Magnet-free motor",
            "dek": "A documented development.",
            "category": "news",
            "beats": [
                {
                    "beat_id": "one",
                    "text": "Vimag says its motor avoids permanent magnets.",
                    "claim_ids": ["claim_001"],
                },
                {
                    "beat_id": "two",
                    "text": "The next step is commercial validation.",
                    "claim_ids": [],
                },
                {
                    "beat_id": "three",
                    "text": "That result will determine what follows.",
                    "claim_ids": ["claim_001"],
                },
            ],
        }

        with self.assertRaisesRegex(ValueError, "link at least one supported claim"):
            _validate_narrative_draft(raw, pack, target_duration_seconds=10)

    def test_narrative_contract_rejects_paragraph_sized_section_beats(self) -> None:
        pack = {
            "research_summary": "India is testing a documented rail pilot.",
            "claims": [
                {
                    "claim_id": "claim_001",
                    "claim_text": "India is testing a documented rail pilot.",
                    "supported": True,
                    "evidence_ids": [],
                }
            ],
            "evidence": [],
            "documents": [],
        }
        paragraph = " ".join(["Documented operations continue under review"] * 14) + "."
        raw = {
            "headline": "Rail pilot",
            "dek": "A documented test.",
            "category": "news",
            "beats": [
                {
                    "beat_id": str(index),
                    "text": paragraph,
                    "claim_ids": ["claim_001"],
                }
                for index in range(3)
            ],
        }

        with self.assertRaisesRegex(ValueError, "sentence or major clause"):
            _validate_narrative_draft(raw, pack, target_duration_seconds=10)

    def test_segmentation_groups_beats_without_rewriting_narration(self) -> None:
        draft = NarrativeDraft(
            headline="A coherent briefing",
            dek="One continuous narration.",
            beats=[
                NarrativeBeat(
                    beat_id=f"beat_{index:03d}",
                    text=text,
                    claim_ids=["claim_001"],
                )
                for index, text in enumerate(
                    [
                        "A verified pilot has started in India.",
                        "Its operating evidence now becomes the central test.",
                        "Existing infrastructure defines the practical constraint.",
                        "Operators must compare reliability with the documented goal.",
                        "The result remains uncertain until repeatable data arrives.",
                        "That evidence will determine whether expansion is justified.",
                    ],
                    start=1,
                )
            ],
        )
        raw = {
            "sections": [
                {
                    "section_type": "cold_open",
                    "beat_ids": ["beat_001", "beat_002"],
                    "suggested_visual_types": ["video"],
                    "suggested_search_queries": [
                        "India pilot facility editorial photo",
                        "India pilot official raw footage",
                    ],
                    "suggested_template_ids": ["fullscreen_anchor"],
                    "lower_third": "A documented pilot begins",
                    "chyron": "The central test",
                    "source_clip": None,
                },
                {
                    "section_type": "context",
                    "beat_ids": ["beat_003", "beat_004"],
                    "suggested_visual_types": ["diagram"],
                    "suggested_search_queries": [
                        "India pilot infrastructure diagram",
                        "India operators official B-roll",
                    ],
                    "suggested_template_ids": ["split_anchor_visual"],
                    "lower_third": "Infrastructure shapes execution",
                    "chyron": "The operating constraint",
                    "source_clip": None,
                },
                {
                    "section_type": "conclusion",
                    "beat_ids": ["beat_005", "beat_006"],
                    "suggested_visual_types": ["context"],
                    "suggested_search_queries": [
                        "India pilot test results document",
                        "India pilot results official video",
                    ],
                    "suggested_template_ids": ["fullscreen_news_visual"],
                    "lower_third": "Evidence will decide expansion",
                    "chyron": "What to watch",
                    "source_clip": None,
                },
            ]
        }
        segmentation = _validate_narrative_segmentation(raw, draft)
        script = script_from_narrative(
            "story_narrative",
            draft,
            segmentation,
            {
                "claims": [
                    {
                        "claim_id": "claim_001",
                        "supported": True,
                        "evidence_ids": [],
                    }
                ],
                "evidence": [],
                "documents": [],
            },
        )

        self.assertEqual(" ".join(script.text.split()), draft.text)
        self.assertEqual(
            [
                beat_id
                for section in segmentation.sections
                for beat_id in section.beat_ids
            ],
            [beat.beat_id for beat in draft.beats],
        )

    def test_narration_mode_is_independent_from_duration(self) -> None:
        prompt = generation_prompt(
            {"story_id": "story_mode", "claims": [], "evidence": []},
            target_duration_seconds=600,
            narration_mode=NarrationMode.signal,
        )

        self.assertIn("Format: SynthPost Signal", prompt)
        self.assertIn("Fast, presenter-led and decisive", prompt)
        self.assertIn("Target duration: 600 seconds", prompt)
        self.assertNotIn("Format: SynthPost Explained", prompt)
        self.assertIn("source_clip as null", prompt)
        self.assertIn("External videos are muted B-roll", prompt)
        self.assertIn("narration must", prompt)
        self.assertIn("remain continuous", prompt)

    def test_legacy_static_overlays_are_backfilled_from_each_section(self) -> None:
        script = ScriptDocument(
            story_id="story_legacy_overlays",
            headline="One episode headline repeated everywhere",
            sections=[
                ScriptSection(
                    section_id="sec_001_cold_open",
                    section_type="cold_open",
                    text="A surprise vote changed the Senate race overnight.",
                ),
                ScriptSection(
                    section_id="sec_002_context",
                    section_type="context",
                    text="The vacancy follows a candidate's unexpected withdrawal.",
                ),
                ScriptSection(
                    section_id="sec_003_conclusion",
                    section_type="conclusion",
                    text="Party leaders must now find a replacement before the deadline.",
                ),
            ],
            lower_thirds=["One episode headline repeated everywhere"],
            chyrons=["One episode headline repeated everywhere"],
        )

        self.assertEqual(len(script.lower_thirds), 3)
        self.assertEqual(len(set(script.lower_thirds)), 3)
        self.assertEqual(len(set(script.chyrons)), 3)
        self.assertEqual(
            script.lower_thirds,
            [section.lower_third for section in script.sections],
        )
        self.assertNotIn(script.headline, script.lower_thirds)

    def test_headline_cues_follow_spoken_beats_inside_one_section(self) -> None:
        text = (
            "The candidate withdrew from the Senate race overnight. "
            "Party officials now face a compressed replacement deadline. "
            "The decision could reshape control of the chamber."
        )
        beats = narration_beats(text)
        cues = timed_section_headline_cues(text, "key_developments", [], 18.0)

        self.assertEqual(len(beats), 3)
        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[0]["start"], 0.0)
        self.assertEqual(cues[-1]["end"], 18.0)
        self.assertLess(float(cues[0]["end"]), float(cues[1]["end"]))
        self.assertEqual(len({str(cue["text"]) for cue in cues}), 3)

    def test_narration_beats_preserve_approved_punctuation(self) -> None:
        text = (
            "The plan is explicit: review the script, approve the visuals, "
            "and only then render — while keeping the original wording intact."
        )
        beats = narration_beats(text, max_words=8)
        self.assertEqual(" ".join(beats), text)

    def test_fullscreen_audio_policy_keeps_narration_for_broll_video(
        self,
    ) -> None:
        image = VisualCandidate(
            story_id="story_audio_policy",
            provider="unit",
            media_type=MediaType.image,
            content_role=ContentRole.context,
        )
        silent_video = VisualCandidate(
            story_id="story_audio_policy",
            provider="unit",
            media_type=MediaType.video,
            content_role=ContentRole.primary_footage,
            has_audio=False,
        )
        audible_video = silent_video.model_copy(update={"has_audio": True})

        self.assertEqual(
            choose_audio_mode("fullscreen_news_visual", image),
            AudioMode.narration,
        )
        self.assertEqual(
            choose_audio_mode("fullscreen_news_visual", silent_video),
            AudioMode.narration,
        )
        self.assertEqual(
            choose_audio_mode("fullscreen_news_visual", audible_video),
            AudioMode.narration,
        )
        self.assertEqual(
            choose_audio_mode("split_anchor_visual", audible_video),
            AudioMode.narration,
        )
        self.assertEqual(
            choose_audio_mode(
                "fullscreen_news_visual",
                audible_video,
                authored_source_clip=True,
            ),
            AudioMode.narration,
        )
        with patch(
            "pipeline.config.source_audio_inserts_enabled", return_value=True
        ):
            self.assertEqual(
                choose_audio_mode(
                    "fullscreen_news_visual",
                    audible_video,
                    authored_source_clip=True,
                ),
                AudioMode.source,
            )

    def test_authored_source_clip_creates_a_real_narration_pause(self) -> None:
        section = ScriptSection(
            section_id="sec_001_key_developments",
            section_type="key_developments",
            text="The minister then stated the policy in unusually direct terms.",
            estimated_duration_seconds=12,
            claim_ids=["claim_001"],
            lower_third="Minister states the policy directly",
            chyron="The policy in the minister's words",
            source_clip=SourceClipCue(
                duration_seconds=6,
                search_query="minister policy announcement official video",
                description="Hear the minister state the policy at the lectern.",
                fallback_narration="The minister said the policy would begin immediately.",
                speaker="The minister",
                quote="The policy begins immediately.",
            ),
        )
        script = ScriptDocument(
            story_id="story_source_pause",
            headline="Source pause test",
            status="approved",
            sections=[section],
            estimated_duration_seconds=12,
        )
        video = VisualCandidate(
            asset_id="visual_source_pause",
            story_id=script.story_id,
            section_ids=[section.section_id],
            provider="unit",
            download_path=__file__,
            media_type=MediaType.video,
            content_role=ContentRole.primary_footage,
            width=1920,
            height=1080,
            duration_seconds=20,
            has_audio=True,
            attribution_text="Official source",
            rights_tier=RightsTier.green,
            review_status=ReviewStatus.approved,
        )
        repository = Mock()
        repository.latest_script.return_value = script
        repository.list_visuals.return_value = [video]
        repository.save_timeline.side_effect = lambda plan: plan
        repository.candidate_for_story.return_value = SimpleNamespace(
            workflow_state=StoryWorkflowState.timeline_review
        )

        with patch(
            "pipeline.timeline.planner.load_narration_artifact",
            return_value=exact_test_narration(script),
        ):
            production_plan = generate_timeline(repository, script.story_id)
        self.assertEqual(len(production_plan.segments), 1)
        production_segment = production_plan.segments[0]
        self.assertEqual(production_segment.audio.mode, AudioMode.narration)
        self.assertEqual(production_segment.visual.audio_mode, "muted")
        self.assertTrue(production_segment.anchor.speaking)
        self.assertIn(
            "The minister said the policy would begin immediately.",
            timeline_narration_text(production_plan),
        )

        with patch(
            "pipeline.config.source_audio_inserts_enabled", return_value=True
        ), patch(
            "pipeline.timeline.planner.load_narration_artifact",
            return_value=exact_test_narration(script),
        ):
            plan = generate_timeline(repository, script.story_id)

        self.assertEqual(len(plan.segments), 2)
        narration, source = plan.segments
        self.assertEqual(narration.audio.mode, AudioMode.narration)
        self.assertTrue(narration.anchor.speaking)
        self.assertEqual(source.audio.mode, AudioMode.source)
        self.assertFalse(source.anchor.speaking)
        self.assertEqual(source.template.template_id, "fullscreen_news_visual")
        self.assertEqual(source.visual.audio_mode, "original")
        self.assertEqual(source.visual.trim_start, 0)
        self.assertEqual(source.visual.trim_end, 6)
        self.assertEqual(source.script_text, "")
        self.assertEqual(source.overlays.data["playback_mode"], "source_clip")
        self.assertEqual(
            timeline_narration_text(plan),
            "The minister then stated the policy in unusually direct terms.",
        )

        repository.list_visuals.return_value = []
        with patch(
            "pipeline.config.source_audio_inserts_enabled", return_value=True
        ), patch(
            "pipeline.timeline.planner.load_narration_artifact",
            return_value=exact_test_narration(script),
        ):
            fallback_plan = generate_timeline(repository, script.story_id)
        fallback = fallback_plan.segments[-1]
        self.assertEqual(fallback.audio.mode, AudioMode.narration)
        self.assertTrue(fallback.anchor.speaking)
        self.assertEqual(fallback.template.template_id, "fallback_anchor")
        self.assertEqual(
            fallback.script_text,
            "The minister said the policy would begin immediately.",
        )
        self.assertEqual(
            fallback.overlays.data["playback_mode"], "source_clip_fallback"
        )
        self.assertIn(
            "The minister said the policy would begin immediately.",
            timeline_narration_text(fallback_plan),
        )

    def test_structured_script_parses_grounded_source_clip_direction(self) -> None:
        raw = {
            "headline": "Policy announcement",
            "dek": "A verified announcement.",
            "category": "policy",
            "sections": [
                {
                    "section_type": "key_developments",
                    "text": "The minister described when the policy would begin.",
                    "claim_ids": ["claim_001"],
                    "lower_third": "Minister gives the implementation date",
                    "chyron": "The minister's announcement",
                    "headline_cues": ["Minister gives the implementation date"],
                    "suggested_visual_types": ["context"],
                    "suggested_search_queries": [
                        "ministry policy announcement photo",
                        "ministry policy announcement official video",
                    ],
                    "suggested_template_ids": ["split_anchor_visual"],
                    "source_clip": {
                        "duration_seconds": 7,
                        "search_query": "minister policy announcement official video",
                        "description": "Hear the implementation date in the announcement.",
                        "fallback_narration": "The minister said implementation would begin immediately.",
                        "speaker": "The minister",
                        "quote": "",
                    },
                }
            ],
        }
        pack = {
            "claims": [{"claim_id": "claim_001"}],
            "documents": [],
            "evidence": [],
        }

        with patch(
            "pipeline.config.source_audio_inserts_enabled", return_value=True
        ):
            script = script_from_llm_json("story_source_contract", raw, pack)
        section = script.sections[0]

        self.assertIsNotNone(section.source_clip)
        self.assertGreater(section.estimated_duration_seconds, 7)
        self.assertIn("source_audio", section.suggested_visual_types)
        self.assertEqual(
            section.suggested_search_queries[-1],
            "minister policy announcement official video",
        )
        self.assertIn("fullscreen_news_visual", section.suggested_template_ids)

    def test_grounding_reports_each_number_missing_from_research(self) -> None:
        script = ScriptDocument(
            story_id="story_numeric_grounding",
            headline="Pilot update",
            sections=[
                ScriptSection(
                    section_id="sec_001",
                    section_type="key_developments",
                    text="The supported 5 million pilot will begin in 2035.",
                    claim_ids=["claim_001"],
                )
            ],
        )
        pack = {
            "numbers": ["5 million"],
            "claims": [
                {
                    "claim_id": "claim_001",
                    "claim_text": "The pilot is backed by 5 million in funding.",
                    "supported": True,
                    "evidence_ids": ["ev_001"],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "ev_001",
                    "excerpt": "Funding for the pilot totals 5 million.",
                }
            ],
        }

        warnings = validate_grounding(script, pack)

        self.assertEqual(
            warnings,
            [
                "script contains numbers that were not observed in the research "
                "pack: 2035"
            ],
        )

    def test_editorial_template_policy_creates_balanced_story_rhythm(self) -> None:
        hero = VisualCandidate(
            asset_id="visual_hero",
            story_id="story_template_rhythm",
            provider="unit",
            media_type=MediaType.image,
            content_role=ContentRole.context,
            rights_tier=RightsTier.green,
            review_status="approved",
            relevance_score=0.65,
            visual_quality_score=0.65,
            width=1600,
            height=900,
        )
        fallback = VisualCandidate(
            asset_id="visual_anchor_fallback",
            story_id="story_template_rhythm",
            provider="synthpost_anchor_fallback",
            media_type=MediaType.fallback,
            content_role=ContentRole.fallback,
            rights_tier=RightsTier.green,
            review_status="approved",
        )
        section_types = [
            "cold_open",
            "context",
            "key_developments",
            "why_it_matters",
            "uncertainty",
            "conclusion",
        ]
        visuals = [hero, hero, hero, hero, fallback, hero]
        selected: list[str] = []

        self.assertEqual(len(section_types), len(visuals))
        for index, (section_type, visual) in enumerate(zip(section_types, visuals)):
            decision = select_template(
                section_type,
                visual,
                index,
                total_sections=len(section_types),
                previous_templates=selected,
                script_text=(
                    "This editorial narration explains the development with enough "
                    "context, evidence, operational detail, and careful qualification "
                    "to require a composed visual rhythm without becoming an overly "
                    "long or crowded television segment."
                ),
            )
            selected.append(decision.template_id)

        self.assertEqual(
            selected,
            [
                "fullscreen_anchor",
                "split_anchor_visual",
                "fullscreen_news_visual",
                "split_anchor_visual",
                "fullscreen_anchor",
                "fullscreen_news_visual",
            ],
        )
        self.assertTrue(
            all(
                len(set(selected[index : index + 3])) > 1
                for index in range(len(selected) - 2)
            )
        )

    def test_real_media_outranks_anchor_only_fallback(self) -> None:
        fallback = VisualCandidate(
            asset_id="visual_fallback",
            story_id="story_visual_priority",
            section_ids=["sec_context"],
            provider="synthpost_anchor_fallback",
            media_type=MediaType.fallback,
            content_role=ContentRole.fallback,
            rights_tier=RightsTier.green,
            review_status="approved",
            visual_quality_score=1.0,
        )
        real = VisualCandidate(
            asset_id="visual_real",
            story_id="story_visual_priority",
            section_ids=["sec_context"],
            provider="unit",
            media_type=MediaType.image,
            content_role=ContentRole.context,
            rights_tier=RightsTier.green,
            review_status="approved",
            download_path=__file__,
            relevance_score=0.6,
            width=1920,
            height=1080,
            content_cleanliness_status="passed",
        )

        selected = approved_visuals_by_section([fallback, real])

        self.assertEqual(selected["sec_context"].asset_id, "visual_real")
        self.assertEqual(choose_template("context", fallback, 2), "fallback_anchor")

        undersized = real.model_copy(
            update={
                "asset_id": "visual_undersized",
                "width": 1024,
                "height": 576,
            }
        )
        selected_without_hd = approved_visuals_by_section([fallback, undersized])
        self.assertEqual(
            selected_without_hd["sec_context"].asset_id, "visual_fallback"
        )

    def test_timeline_auto_selects_best_suggestion_and_approval_pins_choice(self) -> None:
        fallback = VisualCandidate(
            asset_id="visual_auto_fallback",
            story_id="story_auto_visual",
            section_ids=["sec_context"],
            provider="synthpost_anchor_fallback",
            media_type=MediaType.fallback,
            content_role=ContentRole.fallback,
            rights_tier=RightsTier.green,
            review_status="approved",
        )
        strongest = VisualCandidate(
            asset_id="visual_auto_strongest",
            story_id="story_auto_visual",
            section_ids=["sec_context"],
            provider="unit",
            download_path=__file__,
            media_type=MediaType.image,
            content_role=ContentRole.context,
            rights_tier=RightsTier.yellow,
            review_status="suggested",
            relevance_score=0.94,
            visual_quality_score=0.75,
            width=1920,
            height=1080,
        )
        weaker = strongest.model_copy(
            update={
                "asset_id": "visual_auto_weaker",
                "relevance_score": 0.62,
                "visual_quality_score": 0.61,
            }
        )

        automatic = approved_visuals_by_section([fallback, weaker, strongest])
        self.assertEqual(automatic["sec_context"].asset_id, strongest.asset_id)

        pinned = weaker.model_copy(
            update={
                "rights_tier": RightsTier.green,
                "review_status": ReviewStatus.approved,
            }
        )
        explicit = approved_visuals_by_section([fallback, strongest, pinned])
        self.assertEqual(explicit["sec_context"].asset_id, pinned.asset_id)

        older_approval = strongest.model_copy(
            update={
                "review_status": ReviewStatus.manual_approved,
                "reviewed_at": "2026-07-14T10:00:00Z",
            }
        )
        latest_approval = weaker.model_copy(
            update={
                "review_status": ReviewStatus.manual_approved,
                "reviewed_at": "2026-07-14T11:00:00Z",
            }
        )
        repinned = approved_visuals_by_section(
            [fallback, older_approval, latest_approval]
        )
        self.assertEqual(repinned["sec_context"].asset_id, latest_approval.asset_id)

    def test_visual_patch_validates_sections_and_trim_window(self) -> None:
        visual = VisualCandidate(
            asset_id="visual_patch",
            story_id="story_patch",
            section_ids=["sec_context"],
            provider="unit",
            download_path=__file__,
            media_type=MediaType.video,
            duration_seconds=10.0,
        )
        script = ScriptDocument(
            story_id=visual.story_id,
            headline="Patch validation",
            sections=[
                ScriptSection(
                    section_id="sec_context",
                    section_type="context",
                    text="A section.",
                )
            ],
        )

        class VisualRepository:
            def get_visual(self, _asset_id: str):
                return visual

            def latest_script(self, _story_id: str, *, approved: bool = False):
                return script

            def upsert_visual(self, updated: VisualCandidate):
                self.saved = updated

        repository = VisualRepository()
        updated = update_visual(
            repository,
            visual.asset_id,
            {
                "section_ids": ["sec_context", "sec_context"],
                "trim_start": 2.0,
                "trim_end": 8.0,
            },
        )
        self.assertEqual(updated.section_ids, ["sec_context"])
        with self.assertRaisesRegex(ValueError, "unknown visual section_ids"):
            update_visual(
                repository, visual.asset_id, {"section_ids": ["sec_missing"]}
            )
        with self.assertRaisesRegex(ValueError, "greater than trim_start"):
            update_visual(
                repository,
                visual.asset_id,
                {"trim_start": 8.0, "trim_end": 2.0},
            )
        with self.assertRaisesRegex(ValueError, "cannot exceed media duration"):
            update_visual(repository, visual.asset_id, {"trim_end": 11.0})
        with self.assertRaisesRegex(ValueError, "fallback content role"):
            update_visual(
                repository,
                visual.asset_id,
                {"content_role": ContentRole.fallback},
            )

        visual.media_type = MediaType.image
        visual.trim_start = None
        visual.trim_end = None
        with self.assertRaisesRegex(ValueError, "only be set on video"):
            update_visual(repository, visual.asset_id, {"trim_start": 1.0})

        visual.review_status = ReviewStatus.manual_approved
        visual.attribution_text = "Unit source"
        with self.assertRaisesRegex(ValueError, "cannot have an empty attribution"):
            update_visual(repository, visual.asset_id, {"attribution_text": None})

    def test_legacy_visual_warnings_are_normalized_for_local_media(self) -> None:
        visual = VisualCandidate(
            story_id="story_warning_compat",
            provider="unit",
            download_path=__file__,
            media_type=MediaType.image,
            warnings=[
                "image download failed: expired URL",
                "download rejected for broadcast layout: aspect ratio 0.700 is outside range",
                "broadcast layout warning: aspect ratio 0.700 is outside range",
            ],
        )

        self.assertEqual(
            visual.warnings,
            [
                "broadcast layout warning: aspect ratio 0.700 is outside range",
            ],
        )

    def test_suggested_visual_is_valid_for_render_without_approval(self) -> None:
        plan = TimelinePlan(
            story_id="story_auto_render",
            status="review",
            segments=[
                TimelineSegment(
                    segment_id="seg_001",
                    section_id="sec_context",
                    start_time=0,
                    end_time=5,
                    duration=5,
                    script_text="A section with an automatically selected visual.",
                    visual=SegmentVisual(
                        asset_id="visual_suggested",
                        path=__file__,
                        media_type=MediaType.image,
                        content_role=ContentRole.context,
                        rights_tier=RightsTier.yellow,
                        review_status=ReviewStatus.suggested,
                        attribution_text="Unit source",
                        content_cleanliness_status="not_scanned",
                        approval_blockers=["legacy classifier warning"],
                    ),
                    template=SegmentTemplate(template_id="split_anchor_visual"),
                    overlays=SegmentOverlays(attribution="Unit source"),
                )
            ],
        )

        errors, warnings = validate_timeline(plan, check_media_exists=True)
        self.assertEqual(errors, [])
        self.assertTrue(any("selected automatically" in item for item in warnings))

    def test_manifest_replaces_legacy_generated_card_with_anchor_fallback(self) -> None:
        plan = TimelinePlan(
            story_id="story_legacy_fallback",
            status="approved",
            segments=[
                TimelineSegment(
                    segment_id="seg_001",
                    section_id="sec_uncertainty",
                    start_time=0,
                    end_time=5,
                    duration=5,
                    script_text="A section without approved source media.",
                    visual=SegmentVisual(
                        asset_id="visual_legacy_generated",
                        path="legacy-generated-card.svg",
                        media_type=MediaType.image,
                        content_role=ContentRole.context,
                        attribution_text="SynthPost generated visual",
                    ),
                    template=SegmentTemplate(template_id="split_anchor_visual"),
                    overlays=SegmentOverlays(
                        attribution="SynthPost generated visual"
                    ),
                )
            ],
        )
        current = VisualCandidate(
            asset_id="visual_legacy_generated",
            story_id="story_legacy_fallback",
            section_ids=["sec_uncertainty"],
            provider="generated_visual_card",
            media_type=MediaType.image,
            content_role=ContentRole.context,
            rights_tier=RightsTier.green,
            review_status="approved",
        )

        hydrated = hydrate_timeline_visuals(plan, [current])
        segment = hydrated.segments[0]

        self.assertEqual(segment.template.template_id, "fallback_anchor")
        self.assertTrue(segment.anchor.visible)
        self.assertIsNone(segment.visual.asset_id)
        self.assertIsNone(segment.visual.path)
        self.assertEqual(segment.visual.media_type, MediaType.fallback)
        self.assertEqual(segment.visual.content_role, ContentRole.fallback)
        self.assertEqual(segment.overlays.attribution, "")

    def test_episode_assembly_rejects_missing_selected_story_manifest(self) -> None:
        temp = tempfile.TemporaryDirectory()
        episode_root = Path(temp.name) / "episode"
        episode_root.mkdir()
        (episode_root / "episode.json").write_text(
            '{"story_ids":["story_ready","story_missing"]}', encoding="utf-8"
        )
        ready = episode_root / "stories" / "story_ready" / "story.json"
        ready.parent.mkdir(parents=True)
        ready.write_text("{}", encoding="utf-8")
        try:
            with patch(
                "assembly.stitch_episode.episode_dir", return_value=episode_root
            ):
                with self.assertRaisesRegex(FileNotFoundError, "story_missing"):
                    story_manifests("ep_test")
        finally:
            temp.cleanup()

    def test_rediscovery_preserves_selected_story_state(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        try:
            project = repository.create_project("Rediscovery Project")
            selected_episode = repository.create_episode(
                project.project_id, "Selected Episode"
            )
            other_episode = repository.create_episode(
                project.project_id, "Other Episode"
            )
            original = StoryCandidate(
                candidate_id="cand_stable",
                title="Original headline",
                canonical_url="https://example.com/story",
                source_name="Example",
            )
            repository.upsert_candidate(original)
            selected = repository.select_candidate(
                original.candidate_id, selected_episode.episode_id
            )

            rediscovered = StoryCandidate(
                candidate_id="cand_stable",
                title="Updated headline",
                canonical_url="https://example.com/story",
                source_name="Example",
                episode_id=other_episode.episode_id,
            )
            repository.upsert_candidate(rediscovered)

            persisted = repository.get_candidate(original.candidate_id)
            self.assertEqual(persisted.title, "Updated headline")
            self.assertEqual(persisted.episode_id, selected_episode.episode_id)
            self.assertEqual(persisted.story_id, selected.story_id)
            self.assertEqual(
                persisted.selection_status, StorySelectionStatus.selected
            )
            self.assertEqual(persisted.workflow_state, StoryWorkflowState.selected)
        finally:
            repository.close()
            temp.cleanup()

    def test_manifest_hydrates_approved_timeline_attribution(self) -> None:
        plan = TimelinePlan(
            story_id="story_attribution",
            status="approved",
            segments=[
                TimelineSegment(
                    segment_id="seg_001",
                    section_id="sec_001_context",
                    start_time=0,
                    end_time=5,
                    duration=5,
                    script_text="A sourced segment.",
                    visual=SegmentVisual(
                        asset_id="visual_current",
                        path="old.jpg",
                        attribution_text="Old label",
                    ),
                    template=SegmentTemplate(template_id="split_anchor_visual"),
                    audio=SegmentAudio(),
                    overlays=SegmentOverlays(attribution="Old label"),
                )
            ],
        )
        current = VisualCandidate(
            asset_id="visual_current",
            story_id="story_attribution",
            provider="searxng:images",
            download_path=__file__,
            attribution_text="Corrected source",
            media_type="image",
            rights_tier="yellow",
            review_status="manual_approved",
        )

        hydrated = hydrate_timeline_visuals(plan, [current])

        self.assertEqual(hydrated.segments[0].visual.path, __file__)
        self.assertEqual(
            hydrated.segments[0].visual.attribution_text, "Corrected source"
        )
        self.assertEqual(
            hydrated.segments[0].overlays.attribution, "Corrected source"
        )
        self.assertEqual(plan.segments[0].visual.attribution_text, "Old label")

    def test_manifest_upgrades_legacy_fullscreen_source_audio_to_narrated_broll(
        self,
    ) -> None:
        plan = TimelinePlan(
            story_id="story_legacy_source_audio",
            status="approved",
            segments=[
                TimelineSegment(
                    segment_id="seg_001",
                    section_id="sec_context",
                    start_time=0,
                    end_time=5,
                    duration=5,
                    script_text="Narration must remain audible over this clip.",
                    anchor=SegmentAnchor(visible=False, speaking=False),
                    visual=SegmentVisual(
                        asset_id="visual_video",
                        path=__file__,
                        media_type=MediaType.video,
                        content_role=ContentRole.primary_footage,
                        review_status=ReviewStatus.suggested,
                        audio_mode="original",
                        has_audio=True,
                    ),
                    template=SegmentTemplate(template_id="fullscreen_news_visual"),
                    audio=SegmentAudio(
                        mode=AudioMode.source,
                        narration_volume=0,
                        source_volume=1,
                    ),
                    overlays=SegmentOverlays(attribution="Source: unit"),
                )
            ],
        )
        current = VisualCandidate(
            asset_id="visual_video",
            story_id=plan.story_id,
            provider="unit",
            download_path=__file__,
            media_type=MediaType.video,
            content_role=ContentRole.primary_footage,
            rights_tier=RightsTier.yellow,
            review_status=ReviewStatus.suggested,
            has_audio=True,
        )

        hydrated = hydrate_timeline_visuals(plan, [current])
        segment = hydrated.segments[0]

        self.assertEqual(segment.audio.mode, AudioMode.narration)
        self.assertEqual(segment.audio.narration_volume, 1)
        self.assertEqual(segment.audio.source_volume, 0)
        self.assertEqual(segment.visual.audio_mode, "muted")
        self.assertTrue(segment.anchor.speaking)

        authored_plan = plan.model_copy(deep=True)
        authored_segment = authored_plan.segments[0]
        authored_segment.script_text = ""
        authored_segment.overlays.data = {
            "playback_mode": "source_clip",
            "source_clip": {
                "duration_seconds": 5,
                "search_query": "official speech video",
                "description": "Hear the original statement.",
                "fallback_narration": "The official confirmed the change.",
                "speaker": "The official",
                "quote": "",
            },
        }
        authored = hydrate_timeline_visuals(authored_plan, [current]).segments[0]
        self.assertEqual(authored.audio.mode, AudioMode.narration)
        self.assertEqual(authored.visual.audio_mode, "muted")
        self.assertTrue(authored.anchor.speaking)
        self.assertEqual(authored.script_text, "The official confirmed the change.")
        self.assertEqual(
            authored.overlays.data["playback_mode"],
            "source_clip_muted_broll",
        )

        with patch(
            "pipeline.config.source_audio_inserts_enabled", return_value=True
        ):
            experimental = hydrate_timeline_visuals(
                authored_plan, [current]
            ).segments[0]
        self.assertEqual(experimental.audio.mode, AudioMode.source)
        self.assertEqual(experimental.visual.audio_mode, "original")
        self.assertFalse(experimental.anchor.speaking)

        missing = hydrate_timeline_visuals(authored_plan, []).segments[0]
        self.assertEqual(missing.audio.mode, AudioMode.narration)
        self.assertEqual(missing.template.template_id, "fallback_anchor")
        self.assertTrue(missing.anchor.speaking)
        self.assertEqual(missing.script_text, "The official confirmed the change.")
        self.assertEqual(
            missing.overlays.data["playback_mode"], "source_clip_fallback"
        )

    def test_manifest_uses_fallback_only_when_selected_media_becomes_unusable(self) -> None:
        plan = TimelinePlan(
            story_id="story_missing_selected_visual",
            status="approved",
            segments=[
                TimelineSegment(
                    segment_id="seg_001",
                    section_id="sec_context",
                    start_time=0,
                    end_time=5,
                    duration=5,
                    script_text="A visual-led section.",
                    anchor=SegmentAnchor(visible=False, speaking=False),
                    visual=SegmentVisual(
                        asset_id="visual_missing",
                        path="previous.mp4",
                        media_type=MediaType.video,
                        content_role=ContentRole.primary_footage,
                        review_status=ReviewStatus.suggested,
                        audio_mode="original",
                    ),
                    template=SegmentTemplate(template_id="fullscreen_news_visual"),
                    audio=SegmentAudio(
                        mode=AudioMode.source,
                        narration_volume=0,
                        source_volume=1,
                    ),
                    overlays=SegmentOverlays(attribution="Source: unit"),
                )
            ],
        )
        missing = VisualCandidate(
            asset_id="visual_missing",
            story_id=plan.story_id,
            provider="unit",
            download_path="definitely-missing.mp4",
            media_type=MediaType.video,
            content_role=ContentRole.primary_footage,
            rights_tier=RightsTier.yellow,
            review_status=ReviewStatus.suggested,
        )

        hydrated = hydrate_timeline_visuals(plan, [missing])
        segment = hydrated.segments[0]
        self.assertIsNone(segment.visual.asset_id)
        self.assertEqual(segment.visual.media_type, MediaType.fallback)
        self.assertEqual(segment.template.template_id, "fallback_anchor")
        self.assertTrue(segment.anchor.visible)
        self.assertTrue(segment.anchor.speaking)
        self.assertEqual(segment.audio.mode, AudioMode.narration)

    def test_visual_search_filters_unrelated_engine_results(self) -> None:
        from pipeline.search.searxng_client import SearXNGResult

        unrelated = SearXNGResult(
            title="How to download Ultraviewer on a laptop",
            url="https://example.com/ultraviewer",
            snippet="A computer tutorial.",
            engine="unit",
            category="videos",
        )
        relevant = SearXNGResult(
            title="Hydrogen train begins Jind–Sonipat trials",
            url="https://example.com/hydrogen-train",
            snippet="Railway pilot coverage.",
            engine="unit",
            category="images",
        )

        self.assertFalse(_result_matches_query(unrelated, "hydrogen train launch date"))
        self.assertTrue(_result_matches_query(relevant, "hydrogen train launch date"))

    def test_fallback_visual_queries_cover_every_section(self) -> None:
        class QueryRepository:
            def latest_script(self, story_id: str, *, approved: bool = False):
                return ScriptDocument(
                    story_id=story_id,
                    headline="Hydrogen train",
                    status="approved",
                    sections=[
                        ScriptSection(
                            section_id=f"sec_{index:03d}_context",
                            section_type="context",
                            text=f"Section {index}",
                            suggested_search_queries=[
                                f"section {index} primary",
                                f"section {index} secondary",
                            ],
                        )
                        for index in range(1, 4)
                    ],
                )

            def candidate_for_story(self, story_id: str):
                return type("Candidate", (), {"title": "Hydrogen train"})()

        queries = _visual_search_queries(QueryRepository(), "story_unit")

        self.assertEqual(
            queries,
            [
                ("sec_001_context", "section 1 primary"),
                ("sec_002_context", "section 2 primary"),
                ("sec_003_context", "section 3 primary"),
            ],
        )

    def test_visual_query_plan_uses_separate_grounded_footage_query(self) -> None:
        class QueryProvider:
            name = "unit-ai"

            def generate_json(self, prompt, schema, *, temperature=None):
                self.prompt = prompt
                return {
                    "queries": [
                        {
                            "section_id": "sec_001_cold_open",
                            "image_query": "Jind Sonipat hydrogen train launch photo",
                            "video_query": "PM Modi hydrogen train flag off video",
                            "video_priority": True,
                            "rationale": "the opening needs launch footage",
                        }
                    ]
                }

        class QueryRepository:
            def latest_script(self, story_id: str, *, approved: bool = False):
                return ScriptDocument(
                    story_id=story_id,
                    headline="India hydrogen train pilot",
                    status="approved",
                    sections=[
                        ScriptSection(
                            section_id="sec_001_cold_open",
                            section_type="cold_open",
                            text="The Jind Sonipat hydrogen train pilot begins.",
                            suggested_visual_types=["image", "video"],
                            suggested_search_queries=[
                                "Jind Sonipat hydrogen train launch photo",
                                "PM Modi hydrogen train flag off video",
                            ],
                        )
                    ],
                )

            def candidate_for_story(self, story_id: str):
                return type(
                    "Candidate", (), {"title": "India hydrogen train pilot"}
                )()

        provider = QueryProvider()
        with patch(
            "pipeline.visuals.providers.configured_provider",
            return_value=provider,
        ):
            plans = _visual_search_plan(QueryRepository(), "story_unit")

        self.assertEqual(len(plans), 1)
        self.assertEqual(
            plans[0].image_query, "Jind Sonipat hydrogen train launch photo"
        )
        self.assertEqual(
            plans[0].video_query,
            "PM Modi hydrogen train flag off video official raw footage",
        )
        self.assertTrue(plans[0].video_priority)
        self.assertIn("visual search keyword planner", provider.prompt)
        self.assertIn("India hydrogen train pilot", provider.prompt)

    def test_visual_query_plan_removes_unsupported_years(self) -> None:
        plans = _validate_ai_visual_plan(
            {
                "queries": [
                    {
                        "section_id": "sec_001_context",
                        "image_query": "Vimag Labs magnet free motor 2030 prototype",
                        "video_query": "Vimag Labs 2030 motor official demonstration",
                        "video_priority": True,
                        "rationale": "show the physical motor",
                    }
                ]
            },
            section_ids={"sec_001_context"},
            provider_name="unit-ai",
            supported_years={"2025"},
        )

        self.assertEqual(
            plans[0].image_query, "Vimag Labs magnet free motor prototype"
        )
        self.assertEqual(
            plans[0].video_query,
            "Vimag Labs motor official demonstration",
        )
        self.assertNotIn("2030", plans[0].image_query)
        self.assertNotIn("2030", plans[0].video_query)

    def test_visual_query_plan_falls_back_when_ai_planning_fails(self) -> None:
        class QueryProvider:
            name = "unit-ai"

        class QueryRepository:
            def latest_script(self, story_id: str, *, approved: bool = False):
                return ScriptDocument(
                    story_id=story_id,
                    headline="Vimag magnet-free motor",
                    status="approved",
                    sections=[
                        ScriptSection(
                            section_id="sec_001_context",
                            section_type="context",
                            text="Vimag demonstrates its magnet-free motor.",
                            suggested_search_queries=[
                                "Vimag magnet free motor prototype",
                                "Vimag motor demonstration footage",
                            ],
                        )
                    ],
                )

            def candidate_for_story(self, story_id: str):
                return type(
                    "Candidate", (), {"title": "Vimag magnet-free motor"}
                )()

        error = StructuredGenerationError(
            "invalid AI query plan",
            [{"attempt": 1, "ok": False, "error": "invalid plan"}],
        )
        with (
            patch(
                "pipeline.visuals.providers.configured_provider",
                return_value=QueryProvider(),
            ),
            patch(
                "pipeline.visuals.providers.structured_generate",
                side_effect=error,
            ),
        ):
            plans = _visual_search_plan(QueryRepository(), "story_unit")

        self.assertEqual(len(plans), 1)
        self.assertEqual(
            plans[0].image_query, "Vimag magnet free motor prototype"
        )
        self.assertIn("stored script query fallback", plans[0].rationale)

    def test_manual_approval_overrides_broadcast_fit(self) -> None:
        visual = VisualCandidate(
            asset_id="visual_portrait",
            story_id="story_unit",
            section_ids=["sec_001_context"],
            provider="unit",
            download_path="README.md",
            media_type=MediaType.video,
            width=608,
            height=1080,
            rights_tier=RightsTier.yellow,
            attribution_text="Source: unit",
        )

        class VisualRepository:
            def get_visual(self, asset_id: str):
                self.asserted_id = asset_id
                return visual

            def upsert_visual(self, updated: VisualCandidate):
                self.saved = updated

        repository = VisualRepository()
        approved = approve_visual(repository, visual.asset_id, manual=True)

        self.assertEqual(approved.review_status, ReviewStatus.manual_approved)
        self.assertTrue(approved.broadcast_fit_override)
        self.assertIn(
            "sec_001_context",
            approved_visuals_by_section([approved]),
        )

    def test_visual_query_cap_counts_actual_searxng_requests(self) -> None:
        plans = [
            type(
                "Plan",
                (),
                {
                    "section_id": f"sec_{index}",
                    "image_query": f"section {index} editorial image",
                    "video_query": f"section {index} news footage",
                    "video_priority": index % 2 == 0,
                },
            )()
            for index in range(1, 5)
        ]

        tasks = _visual_search_tasks(plans, max_queries=6)

        self.assertEqual(len(tasks), 6)
        self.assertEqual(
            {task[0].section_id for task in tasks[:4]},
            {"sec_1", "sec_2", "sec_3", "sec_4"},
        )
        self.assertEqual(tasks[0][1], "images")
        self.assertEqual(tasks[1][1], "videos")

    def test_visual_relevance_requires_more_than_one_generic_overlap(self) -> None:
        from pipeline.search.searxng_client import SearXNGResult

        weak = SearXNGResult(
            title="Hydrogen cars explained",
            url="https://example.com/hydrogen-cars",
            snippet="Passenger vehicle technology.",
            engine="unit",
            category="images",
        )

        self.assertFalse(
            _result_matches_query(
                weak, "Jind Sonipat hydrogen train launch photo"
            )
        )

    def test_manual_script_edit_preserves_generated_provenance(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        try:
            project = repository.create_project("Script provenance")
            episode = repository.create_episode(project.project_id, "Episode")
            candidate = add_manual_story(
                repository,
                title="Hydrogen train pilot",
                body="A sourced test story.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(candidate.candidate_id, episode.episode_id)
            story_id = selected.story_id
            assert story_id is not None
            generated = ScriptDocument(
                story_id=story_id,
                headline="Generated headline",
                category="transport",
                source_ids=["doc_primary"],
                warnings=["llm_provider=groq"],
                sections=[
                    ScriptSection(
                        section_id="sec_001_cold_open",
                        section_type="cold_open",
                        text="Generated paragraph.",
                        claim_ids=["claim_launch"],
                        suggested_visual_types=["train"],
                        suggested_search_queries=["Jind hydrogen train"],
                        suggested_template_ids=["fullscreen_visual"],
                        editorial_notes=["Keep date hedged"],
                    )
                ],
            )
            repository.save_script(generated)

            edited = save_manual_script(
                repository,
                story_id,
                "Edited headline",
                "A more careful, viewer-focused paragraph.",
            )

            self.assertEqual(edited.category, "transport")
            self.assertEqual(edited.source_ids, ["doc_primary"])
            self.assertEqual(edited.warnings, ["llm_provider=groq"])
            self.assertEqual(edited.sections[0].section_id, "sec_001_cold_open")
            self.assertEqual(edited.sections[0].section_type, "cold_open")
            self.assertEqual(edited.sections[0].claim_ids, ["claim_launch"])
            self.assertEqual(
                edited.sections[0].suggested_search_queries,
                ["Jind hydrogen train"],
            )
            self.assertEqual(edited.sections[0].editorial_notes, ["Keep date hedged"])
        finally:
            repository.close()
            temp.cleanup()

    def test_short_script_word_targets_are_positive_and_sum_to_target(self) -> None:
        targets = section_word_targets(90)
        self.assertEqual(sum(targets.values()), round(90 * 145 / 60))
        self.assertTrue(all(value > 0 for value in targets.values()))
        self.assertNotIn("outro", targets)

    def test_generation_prompt_pack_includes_full_top_four_article_bodies(self) -> None:
        compact = compact_research_pack_for_prompt(
            {
                "story_id": "story_unit",
                "documents": [
                    {
                        "document_id": "doc_lead",
                        "title": "Lead source",
                        "content_text": "complete lead article body",
                    },
                    {
                        "document_id": "doc_second",
                        "title": "Second source",
                        "content_text": "complete second article body",
                    },
                    {
                        "document_id": "doc_third",
                        "title": "Third source",
                        "content_text": "complete third article body",
                    },
                    {
                        "document_id": "doc_fourth",
                        "title": "Fourth source",
                        "content_text": "complete fourth article body",
                    },
                    {
                        "document_id": "doc_fifth",
                        "title": "Fifth source",
                        "content_text": "lower-ranked article body",
                    },
                ],
                "claims": [],
                "people": ["boilerplate entity"],
            }
        )
        self.assertEqual(
            compact["documents"][0]["content_text"],
            "complete lead article body",
        )
        self.assertEqual(
            compact["documents"][1]["content_text"],
            "complete second article body",
        )
        self.assertEqual(
            compact["documents"][2]["content_text"],
            "complete third article body",
        )
        self.assertEqual(
            compact["documents"][3]["content_text"],
            "complete fourth article body",
        )
        self.assertNotIn("content_text", compact["documents"][4])
        self.assertNotIn("people", compact)

    def test_generation_prompt_pack_removes_redundant_claim_notes(self) -> None:
        compact = compact_research_pack_for_prompt(
            {
                "claims": [
                    {
                        "claim_id": "claim_001",
                        "claim_text": "Grounded fact",
                        "notes": "Repeated extraction metadata",
                    }
                ],
                "evidence": [
                    {
                        "evidence_id": "ev_001",
                        "document_id": "doc_001",
                        "excerpt": "x" * 400,
                        "url": "https://example.com/repeated-url",
                    }
                ],
            }
        )
        self.assertNotIn("notes", compact["claims"][0])
        self.assertNotIn("url", compact["evidence"][0])
        self.assertEqual(len(compact["evidence"][0]["excerpt"]), 180)

    def test_workflow_blocks_invalid_transition(self) -> None:
        self.assertTrue(
            can_transition(StoryWorkflowState.discovered, StoryWorkflowState.selected)
        )
        with self.assertRaises(ValueError):
            assert_transition(
                StoryWorkflowState.discovered, StoryWorkflowState.completed
            )
        self.assertTrue(
            can_transition(
                StoryWorkflowState.completed, StoryWorkflowState.script_review
            )
        )
        self.assertTrue(
            can_transition(
                StoryWorkflowState.completed, StoryWorkflowState.timeline_review
            )
        )

    def test_new_script_revision_invalidates_completed_workflow_state(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "script-revision.sqlite3")
        try:
            project = repository.create_project("Script revision")
            episode = repository.create_episode(project.project_id, "Episode")
            candidate = add_manual_story(
                repository,
                title="Completed story",
                body="The existing production has already completed.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id
            selected.workflow_state = StoryWorkflowState.completed
            repository.upsert_candidate(selected)
            episode = repository.get_episode(episode.episode_id)
            episode.status = EpisodeStatus.completed
            episode.final_output_path = "episodes/previous-final.mp4"
            repository.upsert_episode(episode)

            save_manual_script(
                repository,
                selected.story_id,
                "Revised story",
                "A revised script now requires a fresh editorial review.",
            )

            self.assertEqual(
                repository.candidate_for_story(selected.story_id).workflow_state,
                StoryWorkflowState.script_review,
            )
            reopened = repository.get_episode(episode.episode_id)
            self.assertEqual(reopened.status, EpisodeStatus.in_progress)
            self.assertEqual(
                reopened.final_output_path, "episodes/previous-final.mp4"
            )
            approved = approve_script(repository, selected.story_id)
            self.assertEqual(approved.status.value, "approved")
            self.assertTrue(
                all(
                    section.approval_status == ApprovalStatus.approved
                    for section in approved.sections
                )
            )
        finally:
            repository.close()
            temp.cleanup()

    def test_completed_story_regeneration_reopens_before_job_runs(self) -> None:
        temp = tempfile.TemporaryDirectory()
        database_path = Path(temp.name) / "completed-regenerate.sqlite3"
        repository = Repository(database_path)
        try:
            project = repository.create_project("Completed regeneration")
            episode = repository.create_episode(project.project_id, "Episode")
            candidate = add_manual_story(
                repository,
                title="Completed story",
                body="The first production has already completed.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id
            selected.workflow_state = StoryWorkflowState.completed
            repository.upsert_candidate(selected)
            episode = repository.get_episode(episode.episode_id)
            episode.status = EpisodeStatus.completed
            episode.final_output_path = "episodes/previous-final.mp4"
            repository.upsert_episode(episode)
            repository.upsert_research_pack(
                ResearchPack(
                    story_id=selected.story_id,
                    claims=[
                        Claim(
                            claim_id="claim_revision",
                            claim_text="The completed story has supported research.",
                            supported=True,
                        )
                    ],
                    research_summary="Research retained for a production revision.",
                )
            )

            from pipeline.api.main import start_script_generation
            from pipeline.api.schemas import GenerateScriptRequest

            with patch("pipeline.api.main.repo", return_value=repository):
                job = start_script_generation(
                    selected.story_id,
                    GenerateScriptRequest(
                        provider="mock",
                        target_duration_seconds=60,
                        narration_mode="signal",
                    ),
                )

            repository = Repository(database_path)
            self.assertEqual(
                job["payload"]["_previous_workflow_state"], "script_review"
            )
            self.assertEqual(
                repository.candidate_for_story(selected.story_id).workflow_state,
                StoryWorkflowState.script_generating,
            )
            reopened = repository.get_episode(episode.episode_id)
            self.assertEqual(reopened.status, EpisodeStatus.in_progress)
            self.assertEqual(
                reopened.final_output_path, "episodes/previous-final.mp4"
            )
        finally:
            repository.close()
            temp.cleanup()

    def test_inflight_assembly_cannot_recomplete_a_revised_episode(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "assembly-revision.sqlite3")
        try:
            project = repository.create_project("Assembly revision")
            episode = repository.create_episode(project.project_id, "Episode")
            candidate = add_manual_story(
                repository,
                title="Revised during assembly",
                body="The editor found an issue while assembly was running.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id
            selected.workflow_state = StoryWorkflowState.script_review
            repository.upsert_candidate(selected)
            episode = repository.get_episode(episode.episode_id)

            context = SimpleNamespace(
                repository=repository,
                job=SimpleNamespace(
                    episode_id=episode.episode_id,
                    payload={"render_profile": "production"},
                    render_profile="production",
                ),
                progress=lambda *_args: None,
                log=lambda *_args, **_kwargs: None,
            )
            output = PROJECT_ROOT / "episodes" / episode.episode_id / "final.mp4"
            with patch("pipeline.jobs.worker.stitch_episode", return_value=output):
                handle_assemble_episode(context)

            revised_episode = repository.get_episode(episode.episode_id)
            self.assertEqual(revised_episode.status, EpisodeStatus.in_progress)
            self.assertEqual(
                repository.candidate_for_story(selected.story_id).workflow_state,
                StoryWorkflowState.script_review,
            )
        finally:
            repository.close()
            temp.cleanup()

    def test_startup_reconciles_legacy_unapproved_completed_revision(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "legacy-revision.sqlite3")
        try:
            project = repository.create_project("Legacy revision")
            episode = repository.create_episode(project.project_id, "Episode")
            candidate = add_manual_story(
                repository,
                title="Legacy completed story",
                body="An older server persisted a draft without reopening production.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id
            save_manual_script(
                repository,
                selected.story_id,
                "Legacy revision",
                "This newer draft must be reviewed before production continues.",
            )
            selected = repository.candidate_for_story(selected.story_id)
            selected.workflow_state = StoryWorkflowState.completed
            repository.upsert_candidate(selected)
            episode = repository.get_episode(episode.episode_id)
            episode.status = EpisodeStatus.completed
            episode.final_output_path = "episodes/legacy-final.mp4"
            repository.upsert_episode(episode)

            repaired = reconcile_script_revision_workflows(repository)

            self.assertEqual(repaired, 1)
            self.assertEqual(
                repository.candidate_for_story(selected.story_id).workflow_state,
                StoryWorkflowState.script_review,
            )
            reopened = repository.get_episode(episode.episode_id)
            self.assertEqual(reopened.status, EpisodeStatus.in_progress)
            self.assertEqual(reopened.final_output_path, "episodes/legacy-final.mp4")
            self.assertEqual(reconcile_script_revision_workflows(repository), 0)
        finally:
            repository.close()
            temp.cleanup()

    def test_rejected_script_transition_does_not_persist_a_revision(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "script-transition.sqlite3")
        try:
            project = repository.create_project("Cancelled script")
            episode = repository.create_episode(project.project_id, "Episode")
            candidate = add_manual_story(
                repository,
                title="Cancelled story",
                body="This story was removed from production.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id
            repository.transition_story(
                selected.story_id, StoryWorkflowState.cancelled
            )

            with self.assertRaisesRegex(ValueError, "workflow state cancelled"):
                save_manual_script(
                    repository,
                    selected.story_id,
                    "Should not persist",
                    "This invalid revision must not be written.",
                )

            self.assertIsNone(repository.latest_script(selected.story_id))
        finally:
            repository.close()
            temp.cleanup()

    def test_failed_regeneration_restores_previous_script_review_state(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "script-rollback.sqlite3")
        try:
            project = repository.create_project("Script rollback")
            episode = repository.create_episode(project.project_id, "Episode")
            candidate = add_manual_story(
                repository,
                title="Review story",
                body="The current draft is awaiting editorial review.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id
            selected.workflow_state = StoryWorkflowState.script_generating
            repository.upsert_candidate(selected)
            job = repository.create_job(
                "script_generate",
                episode_id=episode.episode_id,
                story_id=selected.story_id,
                payload={"_previous_workflow_state": "script_review"},
            )

            _restore_script_state_after_terminal_failure(repository, job)

            self.assertEqual(
                repository.candidate_for_story(selected.story_id).workflow_state,
                StoryWorkflowState.script_review,
            )
        finally:
            repository.close()
            temp.cleanup()

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

    def test_editorial_charter_prioritizes_systems_and_rejects_shopping(self) -> None:
        source = SourceDefinition(
            name="India Systems Desk",
            source_id="src_charter",
            source_type=SourceType.rss,
            feed_url="https://example.com/rss",
            country="in",
            reliability_score=0.9,
        )
        infrastructure = assess_editorial_fit(
            source,
            "India expands semiconductor manufacturing capacity despite power constraints",
            "The policy affects supply chains, factory jobs and electricity infrastructure.",
        )
        shopping = assess_editorial_fit(
            source,
            "The 10 best AI laptops to buy under ₹80,000",
            "A shopping guide with discounts and deals.",
        )

        self.assertEqual(infrastructure.charter_version, CHARTER_VERSION)
        self.assertTrue(infrastructure.eligible)
        self.assertGreaterEqual(len(infrastructure.matched_criteria), 3)
        self.assertFalse(shopping.eligible)
        self.assertIn("shopping", shopping.rejection_signals)

    def test_global_assignment_desk_rejects_local_churn_and_personnel_news(self) -> None:
        india_source = SourceDefinition(
            name="India General Desk",
            source_id="src_india_general",
            source_type=SourceType.rss,
            feed_url="https://example.com/india.xml",
            country="in",
            reliability_score=0.9,
        )
        global_ai_source = SourceDefinition(
            name="Global AI Desk",
            source_id="src_global_ai",
            source_type=SourceType.rss,
            feed_url="https://example.com/ai.xml",
            category="artificial_intelligence",
            country="us",
            reliability_score=0.9,
        )

        courthouse = assess_editorial_fit(
            india_source,
            "CJI inaugurates Gurugram's Tower of Justice",
            "The new court complex includes bar rooms and childcare facilities.",
        )
        local_crime = assess_editorial_fit(
            india_source,
            "Law student plotted her mother's murder as a road accident in Jaipur",
            "Police arrested the student after investigating the local crime.",
        )
        appointment = assess_editorial_fit(
            global_ai_source,
            "Jinhua Zhao named head of the Department of Urban Studies and Planning",
            "The university appointment combines behavioural science with AI policy.",
        )

        self.assertFalse(courthouse.eligible)
        self.assertIn("ceremonial_or_personnel", courthouse.rejection_signals)
        self.assertFalse(local_crime.eligible)
        self.assertIn("local_crime_or_accident", local_crime.rejection_signals)
        self.assertFalse(appointment.eligible)
        self.assertIn("ceremonial_or_personnel", appointment.rejection_signals)

    def test_global_assignment_desk_accepts_global_shift_with_india_angle(self) -> None:
        source = SourceDefinition(
            name="Global Technology Desk",
            source_id="src_global_technology",
            source_type=SourceType.rss,
            feed_url="https://example.com/technology.xml",
            category="technology",
            country="us",
            reliability_score=0.9,
        )
        candidate = assess_editorial_fit(
            source,
            "New US export controls reshape the global AI chip market",
            "The regulation changes semiconductor supply chains, data-centre investment and competition, with consequences for India's AI industry.",
        )

        self.assertTrue(candidate.eligible)
        self.assertIn(candidate.primary_topic, {"artificial_intelligence", "business"})
        self.assertIn("system_change", candidate.matched_criteria)
        self.assertIn("india_connection", candidate.matched_criteria)

    def test_assignment_desk_clusters_events_and_keeps_one_source_priority_leader(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "assignment-desk.sqlite3")
        try:
            primary = SourceDefinition(
                source_id="src_primary",
                name="Primary Wire",
                source_type=SourceType.rss,
                feed_url="https://example.com/primary.xml",
                category="technology",
                country="us",
                priority=96,
                reliability_score=0.94,
            )
            secondary = primary.model_copy(
                update={
                    "source_id": "src_secondary",
                    "name": "Secondary Blog",
                    "feed_url": "https://example.com/secondary.xml",
                    "priority": 55,
                    "reliability_score": 0.7,
                }
            )
            repository.upsert_source(primary)
            repository.upsert_source(secondary)

            def make(source: SourceDefinition, candidate_id: str, title: str) -> StoryCandidate:
                summary = "The global AI platform agreement changes market access, competition and data-centre infrastructure."
                scores, final, reasons = score_candidate(source, title, summary, None)
                return StoryCandidate(
                    candidate_id=candidate_id,
                    title=title,
                    source_id=source.source_id,
                    source_name=source.name,
                    category=source.category,
                    summary=summary,
                    scores=scores,
                    editorial_fit=assess_editorial_fit(source, title, summary),
                    final_score=final,
                    score_reasons=reasons,
                )

            candidates = [
                make(primary, "cand_primary", "Apple and OpenAI sign global AI platform agreement"),
                make(secondary, "cand_secondary", "OpenAI and Apple sign an AI platform agreement globally"),
            ]
            clusters = cluster_candidates(
                candidates,
                source_priorities={primary.source_id: 96, secondary.source_id: 55},
            )
            self.assertEqual(len(clusters), 1)
            self.assertEqual(clusters[0].leader.candidate_id, "cand_primary")

            leaders = apply_assignment_desk(repository, candidates, use_ai=False)
            self.assertEqual(len(leaders), 1)
            self.assertEqual(leaders[0].cluster_size, 2)
            self.assertEqual(
                repository.get_candidate("cand_secondary").selection_status,
                StorySelectionStatus.duplicate,
            )
            self.assertEqual(
                [item.candidate_id for item in repository.list_candidates()],
                ["cand_primary"],
            )

            unrelated = make(
                secondary,
                "cand_unrelated",
                "Nvidia opens a robotics research lab - Secondary Blog",
            )
            publisher_suffix_peer = make(
                secondary,
                "cand_suffix_peer",
                "Microsoft changes cloud pricing in Asia - Secondary Blog",
            )
            self.assertEqual(
                len(cluster_candidates([unrelated, publisher_suffix_peer])),
                2,
            )
        finally:
            repository.close()
            temp.cleanup()

    def test_assignment_desk_rejects_product_fluff_and_labels_global_india_hypothesis(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "assignment-quality.sqlite3")
        try:
            source = SourceDefinition(
                source_id="src_global",
                name="Global Technology Wire",
                source_type=SourceType.rss,
                feed_url="https://example.com/global.xml",
                category="technology",
                country="us",
                priority=90,
                reliability_score=0.9,
            )
            repository.upsert_source(source)

            def make(candidate_id: str, title: str, summary: str) -> StoryCandidate:
                scores, final, reasons = score_candidate(source, title, summary, None)
                return StoryCandidate(
                    candidate_id=candidate_id,
                    title=title,
                    source_id=source.source_id,
                    source_name=source.name,
                    category=source.category,
                    summary=summary,
                    scores=scores,
                    editorial_fit=assess_editorial_fit(source, title, summary),
                    final_score=final,
                    score_reasons=reasons,
                )

            strong = make(
                "cand_chips",
                "US tightens global AI chip export controls",
                "The regulation changes semiconductor supply chains, cloud capacity, investment and market competition.",
            )
            fluff = make(
                "cand_fluff",
                "Celebrity wears the best AI smart glasses at a showcase",
                "A hands-on review of a new consumer gadget.",
            )
            leaders = apply_assignment_desk(repository, [strong, fluff], use_ai=False)
            by_id = {item.candidate_id: item for item in leaders}
            self.assertIn(by_id["cand_chips"].assignment_lane, {"recommended", "global_watch"})
            self.assertGreater(by_id["cand_chips"].editorial_fit.india_impact_confidence, 0)
            self.assertIn("Indian", by_id["cand_chips"].editorial_fit.india_impact)
            self.assertEqual(by_id["cand_fluff"].assignment_lane, "rejected")
        finally:
            repository.close()
            temp.cleanup()

    def test_discovery_records_source_health_and_reports_progress(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "discovery-health.sqlite3")
        try:
            healthy = SourceDefinition(
                source_id="src_healthy",
                name="Healthy Feed",
                source_type=SourceType.rss,
                feed_url="https://example.com/healthy.xml",
            )
            broken = healthy.model_copy(
                update={
                    "source_id": "src_broken",
                    "name": "Broken Feed",
                    "feed_url": "https://example.com/broken.xml",
                }
            )
            repository.upsert_source(healthy)
            repository.upsert_source(broken)
            progress: list[tuple[float, str]] = []

            def fake_fetch(source: SourceDefinition, *, seen_groups=None):
                if source.source_id == broken.source_id:
                    raise OSError("feed unavailable")
                return [
                    StoryCandidate(
                        candidate_id="cand_health",
                        title="India expands AI data-centre capacity",
                        source_id=source.source_id,
                        source_name=source.name,
                    )
                ]

            with patch(
                "pipeline.discovery.discover.discover_from_source",
                side_effect=fake_fetch,
            ), patch(
                "pipeline.discovery.discover.apply_assignment_desk",
                side_effect=lambda _repository, candidates, use_ai: candidates,
            ):
                rows = discover(
                    repository,
                    progress_callback=lambda fraction, stage: progress.append(
                        (fraction, stage)
                    ),
                )

            self.assertEqual([item.candidate_id for item in rows], ["cand_health"])
            healthy_after = repository.get_source(healthy.source_id)
            broken_after = repository.get_source(broken.source_id)
            self.assertEqual(healthy_after.last_item_count, 1)
            self.assertIsNotNone(healthy_after.last_success_at)
            self.assertIn("feed unavailable", broken_after.last_error or "")
            self.assertEqual(broken_after.consecutive_failures, 1)
            self.assertEqual(progress[-1][0], 1.0)
            self.assertIn("clustering and ranking", progress[-1][1])
        finally:
            repository.close()
            temp.cleanup()

    def test_script_generation_persists_prompts_responses_and_normalization(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "generation-audit.sqlite3")
        try:
            project = repository.create_project("Editorial audit")
            episode = repository.create_episode(project.project_id, "Charter test")
            candidate = add_manual_story(
                repository,
                title="India tests a new hydrogen rail system",
                body="India is testing hydrogen rail infrastructure. The pilot has documented capacity constraints.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(candidate.candidate_id, episode.episode_id)
            assert selected.story_id
            repository.upsert_research_pack(
                ResearchPack(
                    story_id=selected.story_id,
                    claims=[
                        Claim(
                            claim_id="claim_001",
                            claim_text="India is testing hydrogen rail infrastructure.",
                            supported=True,
                        )
                    ],
                    systems=["infrastructure", "rail", "energy"],
                    stakeholders=["passengers", "rail operators"],
                    execution_gaps=["The pilot has documented capacity constraints."],
                    research_summary="A documented Indian hydrogen rail pilot.",
                )
            )
            with patch(
                "pipeline.scripts.generation.config.env_bool", return_value=False
            ):
                script = generate_script(
                    repository,
                    selected.story_id,
                    provider_name="mock",
                    target_duration_seconds=60,
                    narration_mode="deep_dive",
                )

            audits = repository.list_generation_audits(selected.story_id)
            self.assertEqual(
                {audit.stage for audit in audits},
                {
                    "narrative_brief",
                    "narrative_draft",
                    "narrative_segmentation",
                    "headline_editor",
                },
            )
            self.assertTrue(all(audit.prompt_text for audit in audits))
            self.assertTrue(all(audit.response for audit in audits))
            self.assertTrue(any(audit.normalization_events for audit in audits))
            self.assertIn(f"editorial_charter={CHARTER_VERSION}", script.warnings)
            self.assertEqual(script.narration_mode, NarrationMode.deep_dive)
            self.assertIn("narration_mode=deep_dive", script.warnings)
            script_audit = next(
                audit for audit in audits if audit.stage == "narrative_draft"
            )
            self.assertIn("Format: SynthPost Deep Dive", script_audit.prompt_text)
            self.assertIn("narrative_first=true", script.warnings)
            self.assertIn("narrative_quality_gate=passed", script.warnings)
            self.assertTrue(all(section.headline_cues for section in script.sections))
        finally:
            repository.close()
            temp.cleanup()

    def test_headline_failure_keeps_accepted_narrative_script(self) -> None:
        class InvalidHeadlineProvider(MockProvider):
            def generate_json(self, prompt, schema, *, temperature=None):
                if "senior headline editor" in prompt.lower():
                    return {
                        "headline": "Hydrogen rail test",
                        "dek": "A grounded test.",
                        "sections": [],
                    }
                return super().generate_json(
                    prompt, schema, temperature=temperature
                )

        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "headline-fallback.sqlite3")
        try:
            project = repository.create_project("Headline fallback")
            episode = repository.create_episode(project.project_id, "Fallback test")
            candidate = add_manual_story(
                repository,
                title="India tests a new hydrogen rail system",
                body="India is testing documented hydrogen rail infrastructure.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id
            repository.upsert_research_pack(
                ResearchPack(
                    story_id=selected.story_id,
                    claims=[
                        Claim(
                            claim_id="claim_001",
                            claim_text="India is testing hydrogen rail infrastructure.",
                            supported=True,
                        )
                    ],
                    research_summary="A documented Indian hydrogen rail pilot.",
                )
            )
            with patch(
                "pipeline.scripts.generation.configured_provider",
                return_value=InvalidHeadlineProvider(),
            ), patch(
                "pipeline.scripts.generation.config.env_bool", return_value=False
            ):
                script = generate_script(
                    repository,
                    selected.story_id,
                    target_duration_seconds=60,
                    narration_mode="signal",
                )

            self.assertIn(
                "headline_editor=fallback_to_narrative_metadata", script.warnings
            )
            self.assertTrue(script.sections)
            self.assertTrue(all(section.headline_cues for section in script.sections))
            headline_audit = next(
                audit
                for audit in repository.list_generation_audits(selected.story_id)
                if audit.stage == "headline_editor"
            )
            self.assertEqual(headline_audit.status, "failed")
        finally:
            repository.close()
            temp.cleanup()

    def test_mock_provider_supports_configured_narrative_durations(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "mock-long-form.sqlite3")
        try:
            project = repository.create_project("Mock long form")
            episode = repository.create_episode(project.project_id, "Offline demo")
            candidate = add_manual_story(
                repository,
                title="India tests a documented transport pilot",
                body="The pilot is entering a documented operating trial.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id
            repository.upsert_research_pack(
                ResearchPack(
                    story_id=selected.story_id,
                    claims=[
                        Claim(
                            claim_id="claim_001",
                            claim_text="The transport pilot is entering an operating trial.",
                            supported=True,
                        )
                    ],
                    research_summary="A documented Indian transport pilot.",
                )
            )

            for duration, minimum_words in ((600, 1_200), (7_200, 14_000)):
                script = generate_script(
                    repository,
                    selected.story_id,
                    provider_name="mock",
                    target_duration_seconds=duration,
                    narration_mode="explained",
                )
                self.assertIn("narrative_quality_gate=passed", script.warnings)
                self.assertGreater(len(script.text.split()), minimum_words)
            draft_audit = next(
                audit
                for audit in repository.list_generation_audits(selected.story_id)
                if audit.stage == "narrative_draft"
                and "Target duration: 7200 seconds" in audit.prompt_text
            )
            draft = _validate_narrative_draft(
                draft_audit.response,
                repository.latest_research_pack(selected.story_id) or {},
                target_duration_seconds=7_200,
            )
            self.assertEqual(narrative_quality_issues(draft), [])
        finally:
            repository.close()
            temp.cleanup()

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

    def test_anchor_timeline_retains_preferred_visual_for_editor_template_switch(
        self,
    ) -> None:
        section = ScriptSection(
            section_id="sec_001_cold_open",
            section_type="cold_open",
            text="A presenter opens the story while an approved image remains available.",
            estimated_duration_seconds=8,
            claim_ids=["claim_001"],
            lower_third="Approved visual remains available",
        )
        script = ScriptDocument(
            story_id="story_anchor_preferred_visual",
            headline="Preferred visual test",
            status="approved",
            sections=[section],
            estimated_duration_seconds=8,
        )
        visual = VisualCandidate(
            asset_id="visual_anchor_preferred",
            story_id=script.story_id,
            section_ids=[section.section_id],
            provider="unit",
            download_path=__file__,
            media_type=MediaType.image,
            content_role=ContentRole.context,
            width=1920,
            height=1080,
            attribution_text="Unit source",
            rights_tier=RightsTier.green,
            review_status=ReviewStatus.approved,
        )
        repository = Mock()
        repository.latest_script.return_value = script
        repository.list_visuals.return_value = [visual]
        repository.save_timeline.side_effect = lambda plan: plan
        repository.candidate_for_story.return_value = SimpleNamespace(
            workflow_state=StoryWorkflowState.timeline_review
        )

        with patch(
            "pipeline.timeline.planner.load_narration_artifact",
            return_value=exact_test_narration(script),
        ):
            plan = generate_timeline(repository, script.story_id)

        segment = plan.segments[0]
        self.assertEqual(segment.template.template_id, "fullscreen_anchor")
        self.assertIsNone(segment.visual.asset_id)
        self.assertEqual(segment.visual.media_type, MediaType.fallback)
        self.assertEqual(
            segment.overlays.data["preferred_visual_asset_id"],
            visual.asset_id,
        )

    def test_non_quote_card_templates_are_blacklisted_for_production(self) -> None:
        blacklisted = {
            "document_callout",
            "chart_explainer",
            "map_explainer",
            "timeline_explainer",
            "comparison_card",
            "bullet_summary",
            "source_screenshot",
            "fallback_context_card",
        }
        production_registry = template_registry_json()
        production_ids = {template["template_id"] for template in production_registry}
        all_ids = {
            template["template_id"]
            for template in template_registry_json(production_only=False)
        }
        self.assertIn("quote_card", production_ids)
        self.assertTrue(blacklisted.issubset(all_ids))
        self.assertTrue(blacklisted.isdisjoint(production_ids))
        for template in production_registry:
            self.assertNotIn(template["fallback_template_id"], blacklisted)
        for template_id in blacklisted:
            self.assertFalse(TEMPLATE_REGISTRY[template_id].production_enabled)
            self.assertIn(
                "Blacklisted", TEMPLATE_REGISTRY[template_id].blacklist_reason or ""
            )

    def test_planner_routes_documents_charts_and_maps_to_retained_split_shell(
        self,
    ) -> None:
        for media_type, content_role in [
            (MediaType.document, ContentRole.document),
            (MediaType.chart, ContentRole.data),
            (MediaType.map, ContentRole.location),
        ]:
            visual = VisualCandidate(
                story_id="story_template_blacklist",
                provider="unit",
                media_type=media_type,
                content_role=content_role,
                rights_tier=RightsTier.green,
                review_status="approved",
            )
            self.assertEqual(
                choose_template("context", visual, 1), "split_anchor_visual"
            )

    def test_validation_rejects_blacklisted_card_templates(self) -> None:
        plan = TimelinePlan(
            story_id="story_blacklisted_template",
            segments=[
                TimelineSegment(
                    segment_id="seg_001",
                    section_id="context_1",
                    start_time=0,
                    end_time=4,
                    duration=4,
                    script_text="A blacklisted card should not pass production validation.",
                    anchor=SegmentAnchor(visible=False, speaking=True),
                    visual=SegmentVisual(
                        media_type=MediaType.fallback,
                        content_role=ContentRole.fallback,
                    ),
                    template=SegmentTemplate(template_id="fallback_context_card"),
                    audio=SegmentAudio(),
                    overlays=SegmentOverlays(),
                )
            ],
        )

        errors, _warnings = validate_timeline(plan, check_media_exists=False)

        self.assertTrue(any("blacklisted for production" in error for error in errors))

    def test_avatar_duration_rescale_removes_pure_narration_timeline_gaps(self) -> None:
        manifest = {
            "script": {"text": "One sentence. Another sentence."},
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
        self.assertEqual(timeline["audio_plan"]["regions"][1]["duration"], 25.2)
        self.assertEqual(
            timeline["duration_seconds"],
            manifest["direction"]["performance_beats"][-1]["end"],
        )

    def test_avatar_duration_rescale_prefers_real_audio_duration(self) -> None:
        manifest = {
            "direction": {
                "estimated_duration_seconds": 30.0,
                "audio_duration_seconds": 42.0,
            },
            "approved_timeline": {
                "status": "APPROVED",
                "segments": [
                    {
                        "segment_id": "seg_001",
                        "start_time": 0.0,
                        "end_time": 10.0,
                        "duration": 10.0,
                        "audio": {"mode": "narration"},
                        "visual": {"audio_mode": "muted"},
                    }
                ],
            },
        }

        changed = _sync_timeline_to_avatar_duration(manifest)

        self.assertTrue(changed)
        self.assertEqual(manifest["approved_timeline"]["duration_seconds"], 42.0)
        self.assertEqual(manifest["approved_timeline"]["segments"][0]["end_time"], 42.0)

    def test_avatar_duration_rescale_preserves_source_audio_pause(self) -> None:
        manifest = {
            "direction": {
                "estimated_duration_seconds": 30.0,
                "audio_duration_seconds": 30.0,
            },
            "script": {"text": "Narration before. Narration after."},
            "approved_timeline": {
                "status": "approved",
                "duration_seconds": 25.0,
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
                        "end_time": 15.0,
                        "duration": 5.0,
                        "audio": {"mode": "source"},
                        "visual": {"audio_mode": "original"},
                    },
                    {
                        "segment_id": "seg_003",
                        "start_time": 15.0,
                        "end_time": 25.0,
                        "duration": 10.0,
                        "audio": {"mode": "narration"},
                        "visual": {"audio_mode": "muted"},
                    },
                ],
            },
        }

        changed = _sync_timeline_to_avatar_duration(manifest)

        self.assertTrue(changed)
        timeline = manifest["approved_timeline"]
        self.assertEqual(timeline["segments"][0]["end_time"], 15.0)
        self.assertEqual(timeline["segments"][1]["start_time"], 15.0)
        self.assertEqual(timeline["segments"][1]["end_time"], 20.0)
        self.assertEqual(timeline["segments"][2]["start_time"], 20.0)
        self.assertEqual(timeline["segments"][2]["end_time"], 35.0)
        self.assertEqual(timeline["duration_seconds"], 35.0)

    def test_manual_vertical_slice_builds_renderer_manifest(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        episode_id = ""
        project_id = ""
        story_id = None
        try:
            project = repository.create_project("Unit Project")
            project_id = project.project_id
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
                "SynthPost Studio keeps renderer approvals explicit. "
                "Editors can change the headline while the same layout remains on screen.\n\n"
                "The approved timeline becomes the rendering source of truth.",
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
            visual.content_cleanliness_status = "passed"
            repository.upsert_visual(visual)
            approve_visual(repository, visual.asset_id)
            narration_artifact = generate_narration(
                repository, story_id, test_mode=True
            )
            with patch(
                "pipeline.timeline.planner.load_narration_artifact",
                return_value=narration_artifact,
            ):
                plan = generate_timeline(repository, story_id)
            first_segment_cues = plan.segments[0].overlays.data["headline_cues"]
            self.assertEqual(len(first_segment_cues), 2)
            self.assertEqual(first_segment_cues[0]["start"], 0.0)
            self.assertEqual(
                first_segment_cues[-1]["end"], plan.segments[0].duration
            )
            self.assertNotEqual(
                first_segment_cues[0]["text"], first_segment_cues[1]["text"]
            )
            self.assertEqual(
                [segment.overlays.lower_third for segment in plan.segments],
                [section.lower_third for section in script.sections],
            )
            self.assertEqual(
                [segment.overlays.chyron for segment in plan.segments],
                [section.chyron for section in script.sections],
            )
            self.assertEqual(
                len({segment.overlays.lower_third for segment in plan.segments}),
                len(plan.segments),
            )
            errors, _warnings = validate_timeline(plan)
            self.assertEqual(errors, [])
            with patch(
                "pipeline.timeline.planner.load_narration_artifact",
                return_value=narration_artifact,
            ):
                approved = approve_timeline(repository, story_id)
            with patch(
                "pipeline.manifest_builder.load_narration_artifact",
                return_value=narration_artifact,
            ):
                manifest = build_story_manifest(
                    repository, story_id, render_profile="preview", test_mode=True
                )
            self.assertEqual(manifest["approved_timeline"]["status"], "approved")
            self.assertEqual(manifest["composition"]["template"], "timeline_story")
            save_manual_script(
                repository,
                story_id,
                "A newer editorial revision",
                "This revised narration must invalidate the old renderer inputs.",
            )
            with self.assertRaisesRegex(ValueError, "latest script revision"):
                build_story_manifest(
                    repository, story_id, render_profile="preview", test_mode=True
                )
            approve_script(repository, story_id)
            with self.assertRaisesRegex(ValueError, "newer production revision"):
                build_story_manifest(
                    repository, story_id, render_profile="preview", test_mode=True
                )
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
            shutil.rmtree(PROJECT_ROOT / "projects" / project_id, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
