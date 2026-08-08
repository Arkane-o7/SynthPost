"""Durable, policy-controlled unattended production orchestration.

Hermes supplies research-aware structured editorial work. SynthPost remains the
control plane: SQLite owns state, deterministic code owns approvals, lane
workers own expensive stages, and the run stops at a versioned MP4 review item.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from typing import Any
from uuid import uuid4

from pipeline.db.repository import Repository
from pipeline.llm.providers import provider_availability
from pipeline.models import (
    AutonomyPolicy,
    AutonomyRun,
    AutonomyRunStatus,
    EpisodeStatus,
    JobStatus,
    RenderJob,
    ReviewStatus,
    RightsTier,
    ScriptStatus,
    StorySelectionStatus,
    StoryWorkflowState,
    TimelineStatus,
    now_iso,
)
from pipeline.narration.service import load_narration_artifact
from pipeline.research.extract import begin_research_revision
from pipeline.render_profiles import resolve_profile
from pipeline.scripts.generation import (
    approve_script,
    begin_script_generation,
    validate_grounding,
)
from pipeline.storage import episode_dir, project_relative, resolve_project_path
from pipeline.timeline.planner import approve_timeline
from pipeline.visuals.providers import begin_visual_search_revision


TERMINAL_RUN_STATUSES = {
    AutonomyRunStatus.ready_for_review,
    AutonomyRunStatus.accepted,
    AutonomyRunStatus.rejected,
    AutonomyRunStatus.cancelled,
}

ACTIVE_JOB_STATUSES = {
    JobStatus.queued,
    JobStatus.paused,
    JobStatus.running,
    JobStatus.cancel_requested,
}

JOB_STAGE: dict[str, tuple[str, float, float]] = {
    "discovery": ("discovering", 2.0, 10.0),
    "research": ("researching", 12.0, 18.0),
    "script_generate": ("writing_script", 30.0, 18.0),
    "narration_generate": ("producing_assets", 48.0, 14.0),
    "visual_search": ("producing_assets", 48.0, 14.0),
    "timeline_generate": ("building_timeline", 62.0, 10.0),
    "render_story": ("rendering", 72.0, 15.0),
    "assemble_episode": ("assembling", 87.0, 7.0),
    "final_video_qa": ("quality_check", 94.0, 5.0),
}


def _persist(
    run: AutonomyRun,
    repository: Repository,
    *,
    expected_status: AutonomyRunStatus | str | None = None,
) -> AutonomyRun:
    jobs = repository.list_jobs(limit=500, autonomy_run_id=run.run_id)
    known_job_ids = list(run.job_ids)
    for job in reversed(jobs):
        if job.job_id not in known_job_ids:
            known_job_ids.append(job.job_id)
    run.job_ids = known_job_ids
    run.active_job_ids = [
        job.job_id
        for job in reversed(jobs)
        if job.status in ACTIVE_JOB_STATUSES
    ]
    return repository.upsert_autonomy_run(run, expected_status=expected_status)


def _set_running(
    run: AutonomyRun,
    repository: Repository,
    *,
    stage: str,
    progress: float,
) -> AutonomyRun:
    run.status = AutonomyRunStatus.running
    run.started_at = run.started_at or now_iso()
    run.current_stage = stage
    run.progress = max(run.progress, min(99.0, progress))
    run.error = None
    return _persist(run, repository)


def _mark_attention(
    run: AutonomyRun,
    repository: Repository,
    message: str,
    *,
    stage: str | None = None,
) -> AutonomyRun:
    run.status = AutonomyRunStatus.needs_attention
    run.current_stage = stage or run.current_stage
    run.error = message
    return _persist(run, repository)


def _queue(
    repository: Repository,
    run: AutonomyRun,
    job_type: str,
    *,
    story_id: str | None = None,
    payload: dict[str, Any] | None = None,
    render_profile: str | None = None,
) -> RenderJob:
    for existing in repository.list_jobs(
        limit=500, autonomy_run_id=run.run_id, job_type=job_type
    ):
        if existing.status in ACTIVE_JOB_STATUSES:
            return existing
    job_payload = {
        **(payload or {}),
        "_autonomy_run_id": run.run_id,
    }
    try:
        job = repository.create_job(
            job_type,
            episode_id=run.episode_id,
            story_id=story_id,
            autonomy_run_id=run.run_id,
            render_profile=render_profile or "preview",
            payload=job_payload,
        )
        # The policy counts repairs after the first attempt. Deterministic
        # validation failures (including final-video QA) still fail closed and
        # are never retried automatically by the worker classifier.
        job.max_attempts = max(1, 1 + run.policy.max_repairs_per_stage)
        repository.upsert_job(job)
    except sqlite3.IntegrityError:
        # A parallel narration/visual completion may reconcile simultaneously.
        for existing in repository.list_jobs(
            limit=500, autonomy_run_id=run.run_id, job_type=job_type
        ):
            if existing.status in ACTIVE_JOB_STATUSES:
                return existing
        raise
    if job.job_id not in run.job_ids:
        run.job_ids.append(job.job_id)
    if job.job_id not in run.active_job_ids:
        run.active_job_ids.append(job.job_id)
    repository.upsert_autonomy_run(run)
    return job


def _candidate_for_run(repository: Repository, run: AutonomyRun):
    if not run.story_id:
        return None
    candidate = repository.candidate_for_story(run.story_id)
    if candidate.episode_id != run.episode_id:
        raise ValueError("Autonomy story no longer belongs to its episode")
    return candidate


def _select_discovered_story(repository: Repository, run: AutonomyRun) -> None:
    candidates = repository.list_candidates(
        channel_id=run.channel_id,
        episode_id=run.episode_id,
        limit=100,
    )
    # If discovery needed editorial help, the editor may select a candidate
    # before pressing Retry. Adopt that durable episode choice instead of
    # repeatedly demanding an automatic candidate.
    selected_candidates = [
        candidate
        for candidate in candidates
        if candidate.selection_status == StorySelectionStatus.selected
        and candidate.story_id
        and candidate.episode_id == run.episode_id
    ]
    if len(selected_candidates) > 1:
        raise ValueError(
            "YOLO production requires exactly one selected story in the episode"
        )
    if selected_candidates:
        selected = selected_candidates[0]
        run.story_id = selected.story_id
        run.candidate_id = selected.candidate_id
        repository.upsert_autonomy_run(run)
        return
    eligible = [
        candidate
        for candidate in candidates
        if candidate.selection_status == StorySelectionStatus.suggested
        and candidate.editorial_fit.eligible
        and candidate.assignment_lane
        in {"recommended", "global_watch", "india_watch"}
    ]
    if not eligible:
        raise ValueError(
            "Discovery finished without an editorially eligible story. "
            "Select a story manually, then retry the run."
        )
    selected = repository.select_candidate(eligible[0].candidate_id, run.episode_id)
    run.story_id = selected.story_id
    run.candidate_id = selected.candidate_id
    repository.upsert_autonomy_run(run)


def _current_narration(repository: Repository, story_id: str) -> bool:
    try:
        return load_narration_artifact(
            repository, story_id, require_current=True
        ) is not None
    except Exception:
        return False


def enforce_green_only_visuals(repository: Repository, story_id: str) -> int:
    """Block every non-approved/non-green visual without self-approving rights."""

    blocked = 0
    for visual in repository.list_visuals(story_id):
        allowed = (
            visual.rights_tier == RightsTier.green
            and visual.review_status == ReviewStatus.approved
            and not visual.manual_review_flag
            and not visual.approval_blockers
        )
        if allowed:
            continue
        if visual.review_status not in {ReviewStatus.rejected, ReviewStatus.blocked}:
            visual.review_status = ReviewStatus.blocked
            visual.reviewed_at = now_iso()
            visual.warnings = list(
                dict.fromkeys(
                    [
                        *visual.warnings,
                        "Excluded by unattended green-only rights policy; available for manual review.",
                    ]
                )
            )
            repository.upsert_visual(visual)
            blocked += 1
    return blocked


def _archive_final_output(
    run: AutonomyRun, source_value: str
) -> tuple[str, str]:
    source = resolve_project_path(source_value)
    if not source.is_file() or source.stat().st_size <= 0:
        raise ValueError("Assembly completed without a readable final MP4")
    destination = episode_dir(run.episode_id) / "autonomy_runs" / run.run_id / "final.mp4"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    digest = hashlib.sha256()
    with destination.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return project_relative(destination), digest.hexdigest()


def episode_revision_fingerprint(repository: Repository, episode_id: str) -> str:
    """Hash every canonical input that can change an episode render."""

    episode = repository.get_episode(episode_id)
    stories: list[dict[str, Any]] = []
    for story_id in episode.story_ids:
        script = repository.latest_script(story_id)
        timeline = repository.latest_timeline(story_id)
        try:
            narration = load_narration_artifact(
                repository, story_id, require_current=True
            )
        except Exception:
            narration = None
        visuals = sorted(
            repository.list_visuals(story_id), key=lambda value: value.asset_id
        )
        stories.append(
            {
                "story_id": story_id,
                "script": script.model_dump(mode="json") if script else None,
                "timeline": timeline.model_dump(mode="json") if timeline else None,
                "narration": (
                    narration.model_dump(mode="json") if narration else None
                ),
                "visuals": [visual.model_dump(mode="json") for visual in visuals],
            }
        )
    canonical = json.dumps(
        {
            "episode_id": episode.episode_id,
            "story_ids": episode.story_ids,
            "render_profile": episode.render_profile,
            "stories": stories,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _latest_by_type(jobs: list[RenderJob], job_type: str) -> RenderJob | None:
    return next((job for job in jobs if job.job_type == job_type), None)


def advance_autonomy_run(repository: Repository, run_id: str) -> AutonomyRun:
    """Reconcile canonical artifacts and enqueue at most the missing next stage."""

    run = repository.get_autonomy_run(run_id)
    if run.status in TERMINAL_RUN_STATUSES:
        return run

    jobs = repository.list_jobs(limit=500, autonomy_run_id=run_id)
    active = [job for job in jobs if job.status in ACTIVE_JOB_STATUSES]
    if active:
        stages = [JOB_STAGE.get(job.job_type, (job.job_type, 0.0, 1.0)) for job in active]
        stage = stages[0][0]
        progress = min(
            base + span * max(0.0, min(100.0, job.progress)) / 100.0
            for job, (_name, base, span) in zip(active, stages)
        )
        return _set_running(run, repository, stage=stage, progress=progress)

    failed = next((job for job in jobs if job.status == JobStatus.failed), None)
    if failed:
        if failed.job_type == "final_video_qa":
            report_value = failed.output_paths.get("qa_report_path")
            if report_value:
                run.qa_report_path = report_value
        return _mark_attention(
            run,
            repository,
            failed.error or f"{failed.job_type} failed",
            stage=JOB_STAGE.get(failed.job_type, (failed.job_type, 0, 0))[0],
        )

    if not run.story_id:
        discovery = _latest_by_type(jobs, "discovery")
        if discovery and discovery.status == JobStatus.completed:
            try:
                _select_discovered_story(repository, run)
            except ValueError as exc:
                return _mark_attention(run, repository, str(exc), stage="discovering")
        else:
            _queue(
                repository,
                run,
                "discovery",
                payload={
                    "episode_id": run.episode_id,
                    "category": run.policy.category,
                },
            )
            return _set_running(run, repository, stage="discovering", progress=2)

    assert run.story_id is not None
    story_id = run.story_id
    candidate = _candidate_for_run(repository, run)
    assert candidate is not None

    research_pack = repository.latest_research_pack(story_id)
    if not research_pack:
        if candidate.workflow_state == StoryWorkflowState.selected:
            restore = begin_research_revision(repository, story_id)
        elif candidate.workflow_state == StoryWorkflowState.researching:
            restore = StoryWorkflowState.selected
        else:
            return _mark_attention(
                run,
                repository,
                f"Story cannot start research from {candidate.workflow_state.value}",
                stage="researching",
            )
        _queue(
            repository,
            run,
            "research",
            story_id=story_id,
            payload={"_restore_workflow_state": restore.value},
        )
        return _set_running(run, repository, stage="researching", progress=12)

    script = repository.latest_script(story_id)
    if not script:
        restore = begin_script_generation(repository, story_id)
        _queue(
            repository,
            run,
            "script_generate",
            story_id=story_id,
            payload={
                "provider": run.policy.provider,
                "target_duration_seconds": run.policy.target_duration_seconds,
                "narration_mode": run.policy.narration_mode.value,
                "_previous_workflow_state": restore.value,
            },
        )
        return _set_running(run, repository, stage="writing_script", progress=30)

    if script.status != ScriptStatus.approved:
        grounding_warnings = validate_grounding(script, research_pack)
        if grounding_warnings:
            run.warnings = list(dict.fromkeys([*run.warnings, *grounding_warnings]))
            return _mark_attention(
                run,
                repository,
                "Script grounding checks require an editor before approval: "
                + "; ".join(grounding_warnings),
                stage="script_review",
            )
        approve_script(repository, story_id)
        candidate = _candidate_for_run(repository, run)
        assert candidate is not None

    narration_ready = _current_narration(repository, story_id)
    visual_job = _latest_by_type(jobs, "visual_search")
    visuals_ready = bool(
        visual_job and visual_job.status == JobStatus.completed
    )
    queued_assets = False
    if not visuals_ready:
        candidate = _candidate_for_run(repository, run)
        assert candidate is not None
        if candidate.workflow_state != StoryWorkflowState.visuals_searching:
            begin_visual_search_revision(repository, story_id)
        _queue(
            repository,
            run,
            "visual_search",
            story_id=story_id,
            payload={
                "provider": run.policy.provider,
                "_restore_workflow_state": "visuals_review",
            },
        )
        queued_assets = True
    if not narration_ready:
        _queue(
            repository,
            run,
            "narration_generate",
            story_id=story_id,
        )
        queued_assets = True
    if queued_assets:
        return _set_running(run, repository, stage="producing_assets", progress=48)

    blocked = enforce_green_only_visuals(repository, story_id)
    if blocked:
        warning = f"Green-only policy excluded {blocked} visual candidate(s); presenter fallbacks remain active."
        run.warnings = list(dict.fromkeys([*run.warnings, warning]))
        repository.upsert_autonomy_run(run)

    candidate = _candidate_for_run(repository, run)
    assert candidate is not None
    if candidate.workflow_state == StoryWorkflowState.visuals_review:
        _queue(
            repository,
            run,
            "timeline_generate",
            story_id=story_id,
        )
        return _set_running(run, repository, stage="building_timeline", progress=62)

    timeline = repository.latest_timeline(story_id)
    if not timeline:
        _queue(
            repository,
            run,
            "timeline_generate",
            story_id=story_id,
        )
        return _set_running(run, repository, stage="building_timeline", progress=62)
    if timeline.status != TimelineStatus.approved:
        approve_timeline(repository, story_id)

    render = _latest_by_type(jobs, "render_story")
    if not render or render.status != JobStatus.completed:
        candidate = _candidate_for_run(repository, run)
        assert candidate is not None
        if candidate.workflow_state != StoryWorkflowState.rendering_composition:
            repository.transition_story(
                story_id, StoryWorkflowState.rendering_composition
            )
        _queue(
            repository,
            run,
            "render_story",
            story_id=story_id,
            render_profile=run.policy.render_profile,
            payload={
                "render_profile": run.policy.render_profile,
                "test_mode": False,
                "force": False,
                "skip_avatar_render": False,
                "_continue_to_assembly": True,
            },
        )
        return _set_running(run, repository, stage="rendering", progress=72)

    assembly = _latest_by_type(jobs, "assemble_episode")
    if not assembly or assembly.status != JobStatus.completed:
        _queue(
            repository,
            run,
            "assemble_episode",
            render_profile=run.policy.render_profile,
            payload={
                "render_profile": run.policy.render_profile,
                "test_mode": False,
                "force": False,
            },
        )
        return _set_running(run, repository, stage="assembling", progress=87)

    qa_job = _latest_by_type(jobs, "final_video_qa")
    if not qa_job:
        output_value = assembly.output_paths.get("final_output_path")
        if not output_value:
            return _mark_attention(
                run,
                repository,
                "Assembly completed without recording final_output_path",
                stage="assembling",
            )
        archived, digest = _archive_final_output(run, output_value)
        run.final_output_path = archived
        run.final_output_sha256 = digest
        qa_path = (
            episode_dir(run.episode_id)
            / "autonomy_runs"
            / run.run_id
            / "final.qa.json"
        )
        run.qa_report_path = project_relative(qa_path)
        repository.upsert_autonomy_run(run)
        profile = resolve_profile(run.policy.render_profile)
        _queue(
            repository,
            run,
            "final_video_qa",
            render_profile=run.policy.render_profile,
            payload={
                "final_output_path": archived,
                "qa_report_path": run.qa_report_path,
                "expected_width": profile.width,
                "expected_height": profile.height,
                "expected_fps": profile.fps,
                "expected_output_sha256": digest,
                "episode_revision_fingerprint": episode_revision_fingerprint(
                    repository, run.episode_id
                ),
            },
        )
        return _set_running(run, repository, stage="quality_check", progress=94)

    if qa_job.status != JobStatus.completed:
        return _mark_attention(
            run,
            repository,
            qa_job.error or "Final video QA did not complete",
            stage="quality_check",
        )

    run.status = AutonomyRunStatus.ready_for_review
    run.current_stage = "ready_for_review"
    run.progress = 100.0
    run.error = None
    run.completed_at = now_iso()
    qa_value = qa_job.output_paths.get("qa_report_path")
    if qa_value:
        run.qa_report_path = qa_value
    run = _persist(run, repository)
    if run.status != AutonomyRunStatus.ready_for_review:
        return run
    try:
        episode = repository.get_episode(run.episode_id)
        incomplete: list[str] = []
        for episode_story_id in episode.story_ids:
            candidate = repository.candidate_for_story(episode_story_id)
            if candidate.workflow_state == StoryWorkflowState.assembling:
                repository.transition_story(
                    episode_story_id, StoryWorkflowState.completed
                )
            elif candidate.workflow_state != StoryWorkflowState.completed:
                incomplete.append(episode_story_id)
        if incomplete:
            raise ValueError(
                "A story revision started after assembly: " + ", ".join(incomplete)
            )
        if not run.final_output_path:
            raise ValueError("Final QA completed without a versioned MP4")
        episode.final_output_path = run.final_output_path
        episode.render_profile = run.policy.render_profile
        episode.status = EpisodeStatus.completed
        episode.updated_at = now_iso()
        repository.upsert_episode(episode)
    except Exception as exc:
        run.status = AutonomyRunStatus.needs_attention
        run.current_stage = "quality_check"
        run.error = f"QA passed but review handoff failed: {exc}"
        return _persist(
            run,
            repository,
            expected_status=AutonomyRunStatus.ready_for_review,
        )
    return run


def start_autonomy_run(
    repository: Repository,
    *,
    episode_id: str,
    story_id: str | None = None,
    policy: AutonomyPolicy | None = None,
) -> AutonomyRun:
    episode = repository.get_episode(episode_id)
    existing = repository.unreviewed_autonomy_run(episode_id)
    if existing:
        raise ValueError(
            f"Episode already has an unreviewed autonomy run: {existing.run_id}"
        )
    active_jobs = [
        job
        for job in repository.list_jobs(limit=500, episode_id=episode_id)
        if job.status in ACTIVE_JOB_STATUSES
    ]
    if active_jobs:
        raise ValueError("Wait for existing episode jobs to finish before starting YOLO production")
    if len(episode.story_ids) > 1:
        raise ValueError(
            "YOLO production currently requires a one-story episode so another story cannot block assembly"
        )
    resolved_policy = policy or AutonomyPolicy()
    if story_id is None and len(episode.story_ids) == 1:
        story_id = episode.story_ids[0]
    if story_id is None and not resolved_policy.auto_select_story:
        raise ValueError(
            "Select a story before starting a run with automatic story selection disabled"
        )
    selected_candidate = None
    if story_id:
        selected_candidate = repository.candidate_for_story(story_id)
        if selected_candidate.episode_id != episode_id:
            raise ValueError("Selected story does not belong to this episode")
        if episode.story_ids and episode.story_ids != [story_id]:
            raise ValueError("YOLO production cannot replace another episode story")

    availability = provider_availability(resolved_policy.provider)
    if not availability.available:
        raise ValueError(f"{resolved_policy.provider} is unavailable: {availability.reason}")
    run = AutonomyRun(
        channel_id=episode.channel_id,
        project_id=episode.project_id,
        episode_id=episode_id,
        story_id=story_id,
        candidate_id=(selected_candidate.candidate_id if selected_candidate else None),
        engine=resolved_policy.provider,
        policy=resolved_policy,
    )
    episode.status = EpisodeStatus.in_progress
    episode.updated_at = now_iso()
    repository.upsert_episode(episode)
    try:
        repository.upsert_autonomy_run(run)
    except sqlite3.IntegrityError as exc:
        existing = repository.unreviewed_autonomy_run(episode_id)
        detail = existing.run_id if existing else "another request"
        raise ValueError(
            f"Episode already has an unreviewed autonomy run: {detail}"
        ) from exc
    return advance_autonomy_run(repository, run.run_id)


def _restore_story_for_manual_takeover(
    repository: Repository, run: AutonomyRun
) -> None:
    """Leave an interrupted story at the closest editable checkpoint."""

    if not run.story_id:
        return
    candidate = repository.candidate_for_story(run.story_id)
    current = candidate.workflow_state
    target: StoryWorkflowState | None = None
    if current == StoryWorkflowState.researching:
        target = (
            StoryWorkflowState.research_ready
            if repository.latest_research_pack(run.story_id)
            else StoryWorkflowState.selected
        )
    elif current == StoryWorkflowState.script_generating:
        target = StoryWorkflowState.research_ready
    elif current == StoryWorkflowState.visuals_searching:
        target = StoryWorkflowState.visuals_review
    elif current in {
        StoryWorkflowState.rendering_avatar,
        StoryWorkflowState.rendering_composition,
        StoryWorkflowState.assembling,
    }:
        target = StoryWorkflowState.timeline_review
    if target is not None:
        repository.transition_story(run.story_id, target)


def finalize_cancelled_autonomy_run(
    repository: Repository, run_id: str
) -> AutonomyRun:
    """Restore the manual checkpoint after every running handler has exited."""

    run = repository.get_autonomy_run(run_id)
    if run.status != AutonomyRunStatus.cancelled:
        return run
    active = [
        job
        for job in repository.list_jobs(limit=500, autonomy_run_id=run_id)
        if job.status in ACTIVE_JOB_STATUSES
    ]
    if active:
        return _persist(
            run,
            repository,
            expected_status=AutonomyRunStatus.cancelled,
        )
    try:
        _restore_story_for_manual_takeover(repository, run)
    except Exception as exc:
        run.warnings = list(
            dict.fromkeys(
                [
                    *run.warnings,
                    f"Manual takeover could not restore the story checkpoint: {exc}",
                ]
            )
        )
    return _persist(
        run,
        repository,
        expected_status=AutonomyRunStatus.cancelled,
    )


def cancel_autonomy_run(repository: Repository, run_id: str) -> AutonomyRun:
    run = repository.get_autonomy_run(run_id)
    if run.status in {
        AutonomyRunStatus.accepted,
        AutonomyRunStatus.rejected,
        AutonomyRunStatus.ready_for_review,
    }:
        return run
    if run.status != AutonomyRunStatus.cancelled:
        previous_status = run.status
        run.status = AutonomyRunStatus.cancelled
        run.current_stage = "cancelled"
        run.error = None
        run.completed_at = now_iso()
        run = _persist(
            run,
            repository,
            expected_status=previous_status,
        )
        if run.status != AutonomyRunStatus.cancelled:
            return run
    for job in repository.list_jobs(limit=500, autonomy_run_id=run_id):
        if job.status not in ACTIVE_JOB_STATUSES:
            continue
        repository.request_job_cancellation(job.job_id)
    return finalize_cancelled_autonomy_run(repository, run_id)


def retry_autonomy_run(repository: Repository, run_id: str) -> AutonomyRun:
    run = repository.get_autonomy_run(run_id)
    if run.status != AutonomyRunStatus.needs_attention:
        raise ValueError("Only a run that needs attention can be retried")
    active = [
        job
        for job in repository.list_jobs(limit=500, autonomy_run_id=run_id)
        if job.status in ACTIVE_JOB_STATUSES
    ]
    if active:
        raise ValueError("Wait for the remaining run jobs to finish before retrying")
    failed = next(
        (
            job
            for job in repository.list_jobs(limit=500, autonomy_run_id=run_id)
            if job.status in {JobStatus.failed, JobStatus.cancelled}
        ),
        None,
    )
    if failed:
        failed.status = JobStatus.queued
        failed.progress = 0
        failed.stage = "queued_for_autonomy_retry"
        failed.last_error = failed.error
        failed.error = None
        failed.traceback = None
        failed.failure_kind = None
        failed.available_at = None
        failed.started_at = None
        failed.completed_at = None
        failed.attempts = 0
        failed.max_attempts = max(1, 1 + run.policy.max_repairs_per_stage)
        repository.upsert_job(failed)
    run.status = AutonomyRunStatus.running
    run.error = None
    run.completed_at = None
    run = _persist(
        run,
        repository,
        expected_status=AutonomyRunStatus.needs_attention,
    )
    if run.status != AutonomyRunStatus.running:
        return run
    return advance_autonomy_run(repository, run_id)


def review_autonomy_run(
    repository: Repository, run_id: str, decision: AutonomyRunStatus
) -> AutonomyRun:
    if decision not in {AutonomyRunStatus.accepted, AutonomyRunStatus.rejected}:
        raise ValueError("Review decision must be accepted or rejected")
    run = repository.get_autonomy_run(run_id)
    if run.status != AutonomyRunStatus.ready_for_review:
        raise ValueError("Only a ready-for-review video can be accepted or rejected")
    run.status = decision
    run.current_stage = decision.value
    run.reviewed_at = now_iso()
    return _persist(
        run,
        repository,
        expected_status=AutonomyRunStatus.ready_for_review,
    )


def reconcile_autonomy_runs(repository: Repository) -> int:
    reconciled = 0
    for run in repository.list_autonomy_runs(limit=500):
        if run.status not in {
            AutonomyRunStatus.queued,
            AutonomyRunStatus.running,
        }:
            continue
        before = (run.status, run.current_stage, tuple(run.job_ids))
        try:
            updated = advance_autonomy_run(repository, run.run_id)
        except Exception as exc:
            updated = repository.get_autonomy_run(run.run_id)
            _mark_attention(
                updated,
                repository,
                f"Autonomy reconciliation failed: {exc}",
            )
        after = (updated.status, updated.current_stage, tuple(updated.job_ids))
        if before != after:
            reconciled += 1
    return reconciled


def autonomy_run_view(repository: Repository, run: AutonomyRun) -> dict[str, Any]:
    project = repository.get_project(run.project_id)
    episode = repository.get_episode(run.episode_id)
    story_title = None
    if run.story_id:
        try:
            story_title = repository.candidate_for_story(run.story_id).title
        except Exception:
            story_title = None
    data = run.model_dump(mode="json")
    raw_qa = data.get("qa")
    if isinstance(raw_qa, dict):
        metrics = raw_qa.get("metrics") if isinstance(raw_qa.get("metrics"), dict) else {}
        findings = raw_qa.get("findings") if isinstance(raw_qa.get("findings"), list) else []
        checks = [
            {
                "check_id": str(finding.get("code") or "qa_finding"),
                "label": str(finding.get("code") or "QA finding").replace("_", " ").title(),
                "status": "warning" if finding.get("severity") == "warning" else "failed",
                "detail": str(finding.get("message") or "Final-video QA finding"),
            }
            for finding in findings
            if isinstance(finding, dict)
        ]
        if raw_qa.get("passed"):
            checks = [
                {
                    "check_id": "container_decode",
                    "label": "Container & full decode",
                    "status": "passed",
                    "detail": "FFprobe parsed the MP4 and FFmpeg decoded the complete audio/video program.",
                },
                {
                    "check_id": "production_profile",
                    "label": "Production profile",
                    "status": "passed",
                    "detail": "Resolution and frame rate match the selected production profile.",
                },
                {
                    "check_id": "audio_delivery",
                    "label": "Audio delivery",
                    "status": "passed",
                    "detail": "A/V sync, integrated loudness, and true peak passed the delivery gate.",
                },
                *checks,
            ]
        data["qa"] = {
            **raw_qa,
            "status": raw_qa.get("status") or ("passed" if raw_qa.get("passed") else "failed"),
            "checks": checks,
            "duration_seconds": metrics.get("duration_seconds"),
            "width": metrics.get("width"),
            "height": metrics.get("height"),
            "video_codec": metrics.get("video_codec"),
            "audio_codec": metrics.get("audio_codec"),
            "size_bytes": metrics.get("size_bytes"),
        }
    data.update(
        {
            "project_title": project.title,
            "episode_title": episode.title,
            "story_title": story_title,
        }
    )
    return data


__all__ = [
    "advance_autonomy_run",
    "autonomy_run_view",
    "cancel_autonomy_run",
    "episode_revision_fingerprint",
    "enforce_green_only_visuals",
    "finalize_cancelled_autonomy_run",
    "reconcile_autonomy_runs",
    "retry_autonomy_run",
    "review_autonomy_run",
    "start_autonomy_run",
]
