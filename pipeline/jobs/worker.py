from __future__ import annotations

import argparse
import fcntl
import os
import signal
import subprocess
import sys
import threading
import time
import traceback as traceback_module
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO
from datetime import datetime, timezone

from assembly.stitch_episode import stitch_episode
from pipeline import config
from pipeline.db.repository import NotFoundError, Repository, get_repository
from pipeline.db.sqlite import database_path
from pipeline.discovery.discover import discover
from pipeline.manifest_builder import build_story_manifest
from pipeline.narration.service import generate_narration
from pipeline.models import (
    EpisodeStatus,
    JobQueueLane,
    JobStatus,
    RenderJob,
    StoryWorkflowState,
    now_iso,
)
from pipeline.observability import LogContext, safe_text, write_event
from pipeline.jobs.policy import classify_failure, retry_time
from pipeline.provenance import file_sha256
from pipeline.research.extract import build_research_pack
from pipeline.scripts.generation import begin_script_generation, generate_script
from pipeline.storage import (
    PROJECT_ROOT,
    project_relative,
    resolve_project_path,
    story_manifest_path,
)
from pipeline.timeline.planner import generate_timeline
from pipeline.video_qa import FinalVideoQAError, run_final_video_qa
from pipeline.visuals.providers import search_visuals
from pipeline.stages import contract_for


class JobCancelled(RuntimeError):
    pass


def _project_id_for_job(repository: Repository, job: RenderJob) -> str | None:
    try:
        if job.episode_id:
            return repository.get_episode(job.episode_id).project_id
        if job.story_id:
            return repository.episode_for_story(job.story_id).project_id
    except NotFoundError:
        return None
    return None


class JobContext:
    def __init__(self, repository: Repository, job: RenderJob):
        self.repository = repository
        self.job = job
        log_dir = PROJECT_ROOT / ".synthpost" / "jobs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = log_dir / f"{job.job_id}.log"
        self.job.log_path = project_relative(self.log_path)
        self._stop_heartbeat = threading.Event()
        self._cancelled = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self.log_context = LogContext(
            project_id=_project_id_for_job(repository, job),
            episode_id=job.episode_id,
            story_id=job.story_id,
            job_id=job.job_id,
            stage=job.job_type,
        )
        if not self.repository.update_job_if_status(self.job, JobStatus.running):
            raise JobCancelled(f"job {job.job_id} was cancelled before it started")

    def log(
        self,
        message: str,
        *,
        event: str = "job_message",
        level: str = "INFO",
        fields: dict[str, object] | None = None,
    ) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            line = write_event(
                handle,
                event,
                message,
                level=level,
                context=self.log_context,
                fields=fields,
            )
        print(line, flush=True)

    def progress(self, progress: float, stage: str) -> None:
        self.raise_if_cancelled()
        self.job.progress = max(0.0, min(100.0, progress))
        self.job.stage = stage
        if not self.repository.update_job_if_status(self.job, JobStatus.running):
            self._cancelled.set()
            raise JobCancelled(f"job {self.job.job_id} was cancelled")
        self.log(
            f"{self.job.progress:.0f}% {stage}",
            event="stage_progress",
            fields={"progress": round(self.job.progress, 2)},
        )

    def start_heartbeat(self) -> None:
        interval = config.get_settings().jobs.heartbeat_seconds

        def heartbeat() -> None:
            repository = Repository(self.repository.db_path)
            try:
                while not self._stop_heartbeat.wait(interval):
                    try:
                        status = repository.heartbeat_job(self.job.job_id)
                    except Exception as exc:
                        self.log(
                            f"heartbeat warning: {exc}",
                            event="job_heartbeat_failed",
                            level="WARNING",
                        )
                        continue
                    if status == JobStatus.cancel_requested:
                        self._cancelled.set()
                        # Keep heartbeating until the handler exits. The
                        # cancel-requested row is an intentional queue lease.
                        continue
                    if status != JobStatus.running:
                        self._cancelled.set()
                        return
            finally:
                repository.close()

        self._heartbeat_thread = threading.Thread(
            target=heartbeat,
            name=f"job-heartbeat-{self.job.job_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._stop_heartbeat.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2.0)

    def raise_if_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise JobCancelled(f"job {self.job.job_id} was cancelled")


def handle_discovery(ctx: JobContext) -> dict[str, str]:
    payload = ctx.job.payload
    stats: dict[str, int] = {}
    ctx.progress(5, "loading sources")
    candidates = discover(
        ctx.repository,
        episode_id=payload.get("episode_id"),
        category=payload.get("category"),
        stats=stats,
        progress_callback=lambda fraction, stage: ctx.progress(
            8 + fraction * 80, stage
        ),
    )
    ctx.progress(
        100,
        f"discovery complete · {stats.get('new_entry_count', 0)} new · "
        f"{stats.get('seen_entry_count', 0)} seen before · "
        f"{len(candidates)} ranked stories",
    )
    return {
        "candidate_count": str(len(candidates)),
        "feed_entry_count": str(stats.get("feed_entry_count", 0)),
        "new_entry_count": str(stats.get("new_entry_count", 0)),
        "seen_entry_count": str(stats.get("seen_entry_count", 0)),
    }


def handle_research(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.story_id:
        raise ValueError("research job requires story_id")
    ctx.progress(10, "extracting source document")
    pack = build_research_pack(ctx.repository, ctx.job.story_id)
    publishers = {
        document.publisher for document in pack.documents if document.publisher
    }
    ctx.progress(
        90,
        f"research pack ready: {len(pack.documents)} articles from "
        f"{len(publishers)} publishers",
    )
    if ctx.job.payload.get("_continue_to_script"):
        autonomy_run_id = getattr(ctx.job, "autonomy_run_id", None)
        ctx.progress(96, "queuing script draft from the completed research")
        restore_state = begin_script_generation(ctx.repository, ctx.job.story_id)
        script_payload = {
            "provider": ctx.job.payload.get("provider"),
            "target_duration_seconds": int(
                ctx.job.payload.get("target_duration_seconds") or 600
            ),
            "narration_mode": str(
                ctx.job.payload.get("narration_mode") or "explained"
            ),
            "_previous_workflow_state": restore_state.value,
        }
        if autonomy_run_id:
            script_payload["_autonomy_run_id"] = autonomy_run_id
        try:
            ctx.repository.create_job(
                "script_generate",
                episode_id=ctx.job.episode_id,
                story_id=ctx.job.story_id,
                autonomy_run_id=autonomy_run_id,
                payload=script_payload,
            )
        except Exception:
            candidate = ctx.repository.candidate_for_story(ctx.job.story_id)
            if candidate.workflow_state == StoryWorkflowState.script_generating:
                ctx.repository.transition_story(ctx.job.story_id, restore_state)
            raise
    ctx.progress(
        100,
        (
            "research complete; script drafting queued"
            if ctx.job.payload.get("_continue_to_script")
            else "research complete"
        ),
    )
    return {
        "research_pack_id": pack.research_pack_id,
        "document_count": str(len(pack.documents)),
        "publisher_count": str(len(publishers)),
        "query_count": str(len(pack.research_queries)),
    }


def handle_script_generate(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.story_id:
        raise ValueError("script job requires story_id")
    ctx.progress(10, "planning coherent production narration")
    script = generate_script(
        ctx.repository,
        ctx.job.story_id,
        provider_name=ctx.job.payload.get("provider"),
        target_duration_seconds=int(
            ctx.job.payload.get("target_duration_seconds") or 600
        ),
        narration_mode=str(ctx.job.payload.get("narration_mode") or "explained"),
        progress_callback=lambda fraction, stage: ctx.progress(
            10 + (max(0.0, min(1.0, fraction)) * 85), stage
        ),
    )
    ctx.progress(100, "script ready for review")
    return {"script_id": script.script_id}


def handle_visual_search(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.story_id:
        raise ValueError("visual search job requires story_id")
    ctx.progress(10, "using AI to plan image/video keywords")
    visuals = search_visuals(
        ctx.repository,
        ctx.job.story_id,
        progress_callback=lambda fraction, stage: ctx.progress(
            10 + (max(0.0, min(1.0, fraction)) * 80), stage
        ),
        cancel_check=ctx.raise_if_cancelled,
        provider_name=ctx.job.payload.get("provider"),
    )
    downloadable = sum(1 for visual in visuals if visual.download_path)
    ctx.progress(
        100,
        f"found {len(visuals)} visual candidates ({downloadable} render-ready files)",
    )
    return {"visual_count": str(len(visuals))}


def handle_narration_generate(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.story_id:
        raise ValueError("narration job requires story_id")
    ctx.progress(5, "loading approved script and dots.tts voice profile")
    artifact = generate_narration(
        ctx.repository,
        ctx.job.story_id,
        force=bool(ctx.job.payload.get("force", False)),
        test_mode=bool(ctx.job.payload.get("test_mode", False)),
    )
    ctx.progress(100, "sample-exact dots.tts narration ready")
    return {
        "narration_path": artifact.audio_path,
        "alignment_path": project_relative(
            story_manifest_path(artifact.episode_id, artifact.story_id).parent
            / "narration"
            / f"script_v{artifact.script_version:03d}"
            / "alignment.json"
        ),
    }


def handle_timeline_generate(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.story_id:
        raise ValueError("timeline job requires story_id")
    ctx.progress(15, "building deterministic timeline draft")
    plan = generate_timeline(ctx.repository, ctx.job.story_id)
    ctx.progress(100, "timeline draft ready")
    return {"timeline_id": plan.timeline_id}


def handle_render_avatar(ctx: JobContext) -> dict[str, str]:
    from pipeline.presenters import render_presenter

    if not ctx.job.story_id:
        raise ValueError("render avatar job requires story_id")
    payload = ctx.job.payload
    render_profile = payload.get("render_profile") or ctx.job.render_profile
    test_mode = bool(payload.get("test_mode", False))
    force = bool(payload.get("force", False)) or getattr(ctx.job, "attempts", 0) > 1
    ctx.progress(5, "building renderer manifest before avatar render")
    build_story_manifest(
        ctx.repository,
        ctx.job.story_id,
        render_profile=render_profile,
        test_mode=test_mode,
    )
    episode = ctx.repository.episode_for_story(ctx.job.story_id)
    manifest_path = story_manifest_path(episode.episode_id, ctx.job.story_id)
    ctx.progress(25, "invoking Avatar Engine")
    direction = render_presenter(
        manifest_path,
        force=force,
        render=True,
        test_mode=test_mode,
        render_profile=render_profile,
    )
    if not test_mode and render_profile in {"production", "final_master"}:
        candidate = ctx.repository.candidate_for_story(ctx.job.story_id)
        if candidate.workflow_state == StoryWorkflowState.rendering_avatar:
            ctx.repository.transition_story(
                ctx.job.story_id, StoryWorkflowState.rendering_composition
            )
    ctx.progress(100, "avatar render completed")
    return {
        "story_manifest": project_relative(manifest_path),
        "anchor_output_path": str(direction.get("anchor_output_path", "")),
    }


def handle_render_story(ctx: JobContext) -> dict[str, str]:
    from pipeline.run_story import run_story

    if not ctx.job.story_id:
        raise ValueError("render story job requires story_id")
    payload = ctx.job.payload
    autonomy_run_id = getattr(ctx.job, "autonomy_run_id", None)
    render_profile = payload.get("render_profile") or ctx.job.render_profile
    test_mode = bool(payload.get("test_mode", False))
    force = bool(payload.get("force", False)) or getattr(ctx.job, "attempts", 0) > 1
    skip_avatar = bool(payload.get("skip_avatar_render", True))
    ctx.progress(5, "building renderer manifest")
    build_story_manifest(
        ctx.repository,
        ctx.job.story_id,
        render_profile=render_profile,
        test_mode=test_mode,
    )
    episode = ctx.repository.episode_for_story(ctx.job.story_id)
    manifest_path = story_manifest_path(episode.episode_id, ctx.job.story_id)
    ctx.progress(20, "rendering Remotion story")
    previous = os.environ.get("SYNTHPOST_ALLOW_PLACEHOLDER_ANCHOR")
    if skip_avatar:
        os.environ["SYNTHPOST_ALLOW_PLACEHOLDER_ANCHOR"] = "1"
    try:
        run_story(
            manifest_path,
            force_composite=force,
            skip_avatar_render=skip_avatar,
            test_mode=test_mode,
            render_profile=render_profile,
        )
    finally:
        if previous is None:
            os.environ.pop("SYNTHPOST_ALLOW_PLACEHOLDER_ANCHOR", None)
        else:
            os.environ["SYNTHPOST_ALLOW_PLACEHOLDER_ANCHOR"] = previous
    if not test_mode and render_profile in {"production", "final_master"}:
        candidate = ctx.repository.candidate_for_story(ctx.job.story_id)
        if candidate.workflow_state == StoryWorkflowState.rendering_composition:
            ctx.repository.transition_story(
                ctx.job.story_id, StoryWorkflowState.assembling
            )
        episode = ctx.repository.episode_for_story(ctx.job.story_id)
        story_states = []
        for episode_story_id in episode.story_ids:
            try:
                story_states.append(
                    ctx.repository.candidate_for_story(
                        episode_story_id
                    ).workflow_state
                )
            except Exception:
                story_states.append(None)
        ready_to_assemble = bool(story_states) and all(
            state
            in {
                StoryWorkflowState.assembling,
                StoryWorkflowState.completed,
            }
            for state in story_states
        )
        if (
            ready_to_assemble
            and not autonomy_run_id
            and not ctx.repository.active_job(
                "assemble_episode",
                episode_id=episode.episode_id,
                render_profile=render_profile,
            )
        ):
            ctx.progress(96, "queuing final episode assembly and brand outro")
            ctx.repository.create_job(
                "assemble_episode",
                episode_id=episode.episode_id,
                autonomy_run_id=autonomy_run_id,
                render_profile=render_profile,
                payload={
                    "render_profile": render_profile,
                    "test_mode": False,
                    "force": False,
                    "_autonomy_run_id": autonomy_run_id,
                },
            )
    ctx.progress(100, "story render completed")
    return {"story_manifest": project_relative(manifest_path)}


def handle_assemble_episode(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.episode_id:
        raise ValueError("assembly job requires episode_id")
    payload = ctx.job.payload
    autonomy_run_id = getattr(ctx.job, "autonomy_run_id", None)
    ctx.progress(20, "normalizing and stitching story clips")
    test_mode = bool(payload.get("test_mode", False))
    output = stitch_episode(
        ctx.job.episode_id,
        force=bool(payload.get("force", False))
        or getattr(ctx.job, "attempts", 0) > 1,
        test_mode=test_mode,
        render_profile=payload.get("render_profile") or ctx.job.render_profile,
    )
    if not test_mode:
        episode = ctx.repository.get_episode(ctx.job.episode_id)
        episode.render_profile = str(
            payload.get("render_profile") or ctx.job.render_profile or "production"
        )
        if autonomy_run_id:
            # The versioned output is published only after final_video_qa passes.
            episode.status = EpisodeStatus.in_progress
            episode.updated_at = now_iso()
            ctx.repository.upsert_episode(episode)
            ctx.progress(100, "episode assembly completed; strict MP4 QA pending")
            return {"final_output_path": project_relative(output)}

        episode.final_output_path = project_relative(output)
        revision_in_progress = False
        for story_id in episode.story_ids:
            try:
                candidate = ctx.repository.candidate_for_story(story_id)
                if candidate.workflow_state == StoryWorkflowState.assembling:
                    ctx.repository.transition_story(
                        story_id, StoryWorkflowState.completed
                    )
                elif candidate.workflow_state != StoryWorkflowState.completed:
                    revision_in_progress = True
            except Exception as exc:
                ctx.log(
                    f"Could not advance story completion state: {exc}",
                    event="workflow_transition_skipped",
                    level="WARNING",
                    fields={"affected_story_id": story_id},
                )
        episode.status = (
            EpisodeStatus.in_progress
            if revision_in_progress
            else EpisodeStatus.completed
        )
        episode.updated_at = now_iso()
        ctx.repository.upsert_episode(episode)
    ctx.progress(100, "episode assembly completed")
    return {"final_output_path": project_relative(output)}


def handle_final_video_qa(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.episode_id:
        raise ValueError("final video QA job requires episode_id")
    payload = ctx.job.payload
    autonomy_run_id = getattr(ctx.job, "autonomy_run_id", None)
    final_output_path = str(payload.get("final_output_path") or "")
    qa_report_path = str(payload.get("qa_report_path") or "")
    if not final_output_path or not qa_report_path:
        raise ValueError("final video QA requires final_output_path and qa_report_path")
    expected_digest = str(payload.get("expected_output_sha256") or "")
    expected_revision = str(payload.get("episode_revision_fingerprint") or "")
    if not expected_digest or not expected_revision:
        raise ValueError(
            "final video QA requires an output hash and episode revision fingerprint"
        )
    resolved_output = resolve_project_path(final_output_path)
    if file_sha256(resolved_output) != expected_digest:
        raise ValueError("Final MP4 changed after assembly; refusing stale QA input")
    ctx.progress(8, "probing final MP4 streams and production profile")
    try:
        report = run_final_video_qa(
            final_output_path,
            qa_report_path,
            expected_width=int(payload["expected_width"]),
            expected_height=int(payload["expected_height"]),
            expected_fps=float(payload["expected_fps"]),
        )
    except FinalVideoQAError as exc:
        ctx.job.output_paths.update(
            {
                "final_output_path": final_output_path,
                "qa_report_path": qa_report_path,
                "qa_status": "failed",
            }
        )
        if autonomy_run_id:
            run = ctx.repository.get_autonomy_run(autonomy_run_id)
            run.qa = exc.report.model_dump(mode="json")
            run.qa_report_path = qa_report_path
            ctx.repository.upsert_autonomy_run(run)
        raise

    ctx.progress(92, "technical QA passed; verifying immutable render inputs")
    from pipeline.autonomy import episode_revision_fingerprint

    if episode_revision_fingerprint(ctx.repository, ctx.job.episode_id) != expected_revision:
        raise ValueError(
            "Episode inputs changed after assembly; refusing to publish stale QA output"
        )
    if file_sha256(resolved_output) != expected_digest:
        raise ValueError("Final MP4 changed during QA; refusing stale QA output")
    if autonomy_run_id:
        run = ctx.repository.get_autonomy_run(autonomy_run_id)
        run.qa = report.model_dump(mode="json")
        run.qa_report_path = qa_report_path
        ctx.repository.upsert_autonomy_run(run)
    ctx.progress(100, "final MP4 passed QA; review handoff pending")
    return {
        "final_output_path": final_output_path,
        "qa_report_path": qa_report_path,
        "qa_status": "passed",
    }


HANDLERS: dict[str, Callable[[JobContext], dict[str, str]]] = {
    "discovery": handle_discovery,
    "research": handle_research,
    "script_generate": handle_script_generate,
    "narration_generate": handle_narration_generate,
    "visual_search": handle_visual_search,
    "timeline_generate": handle_timeline_generate,
    "render_avatar": handle_render_avatar,
    "render_story": handle_render_story,
    "assemble_episode": handle_assemble_episode,
    "final_video_qa": handle_final_video_qa,
}

JOB_TIMEOUT_SECONDS = {
    "discovery": 5 * 60,
    "research": 30 * 60,
    "script_generate": 20 * 60,
    "narration_generate": 30 * 60,
    "visual_search": 12 * 60,
    "timeline_generate": 5 * 60,
}

STALE_JOB_SECONDS = {
    **JOB_TIMEOUT_SECONDS,
    "render_avatar": 3 * 60 * 60,
    "render_story": 3 * 60 * 60,
    "assemble_episode": 60 * 60,
    "final_video_qa": 60 * 60,
}


@contextmanager
def job_deadline(job_type: str):
    """Interrupt non-render jobs that exceed their queue safety budget."""

    seconds = JOB_TIMEOUT_SECONDS.get(job_type)
    if not seconds or not hasattr(signal, "SIGALRM"):
        yield
        return

    def expired(_signum, _frame):
        raise TimeoutError(
            f"{job_type} exceeded its {seconds // 60}-minute execution limit"
        )

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _restore_workflow_after_terminal_failure(
    repository: Repository, job: RenderJob
) -> str | None:
    if not job.story_id:
        return None
    try:
        candidate = repository.candidate_for_story(job.story_id)
        if (
            job.job_type == "script_generate"
            and candidate.workflow_state == StoryWorkflowState.script_generating
        ):
            previous_value = job.payload.get("_previous_workflow_state")
            try:
                previous_state = StoryWorkflowState(str(previous_value))
            except ValueError:
                previous_state = StoryWorkflowState.research_ready
            if previous_state not in {
                StoryWorkflowState.research_ready,
                StoryWorkflowState.script_review,
            }:
                previous_state = StoryWorkflowState.research_ready
            repository.transition_story(
                job.story_id, previous_state
            )
        elif (
            job.job_type == "research"
            and candidate.workflow_state == StoryWorkflowState.researching
        ):
            previous_value = job.payload.get("_restore_workflow_state")
            try:
                previous_state = StoryWorkflowState(str(previous_value))
            except ValueError:
                previous_state = StoryWorkflowState.research_ready
            if previous_state not in {
                StoryWorkflowState.selected,
                StoryWorkflowState.research_ready,
            }:
                previous_state = StoryWorkflowState.research_ready
            repository.transition_story(job.story_id, previous_state)
        elif (
            job.job_type == "visual_search"
            and candidate.workflow_state == StoryWorkflowState.visuals_searching
        ):
            repository.transition_story(
                job.story_id, StoryWorkflowState.visuals_review
            )
    except Exception as exc:
        return safe_text(exc)
    return None


def _reconcile_autonomy_after_job(
    repository: Repository, job: RenderJob, *, logger=None
) -> None:
    if not job.autonomy_run_id:
        return
    try:
        from pipeline.autonomy import advance_autonomy_run

        advance_autonomy_run(repository, job.autonomy_run_id)
    except Exception as exc:
        message = f"Autonomy reconciliation warning: {safe_text(exc)}"
        if logger:
            logger(message, event="autonomy_reconcile_failed", level="WARNING")
        else:
            print(f"[worker] WARNING: {message}", flush=True)


def _acknowledge_cancel_request(repository: Repository, job: RenderJob) -> None:
    """Release a stop lease only after its handler is no longer executing."""

    try:
        authoritative = repository.get_job(job.job_id)
    except NotFoundError:
        return
    if authoritative.status != JobStatus.cancel_requested:
        return
    if not repository.acknowledge_job_cancellation(job.job_id):
        return
    if authoritative.autonomy_run_id:
        try:
            from pipeline.autonomy import finalize_cancelled_autonomy_run

            finalize_cancelled_autonomy_run(
                repository, authoritative.autonomy_run_id
            )
        except Exception as exc:
            print(
                "[worker] WARNING: could not finalize cancelled autonomy run: "
                f"{safe_text(exc)}",
                flush=True,
            )
    else:
        restore_error = _restore_workflow_after_terminal_failure(
            repository, authoritative
        )
        if restore_error:
            print(
                "[worker] WARNING: could not restore cancelled job state: "
                f"{restore_error}",
                flush=True,
            )


# Compatibility alias retained for tests and local tooling that imported the
# earlier script-only helper before it was expanded to all revision jobs.
_restore_script_state_after_terminal_failure = (
    _restore_workflow_after_terminal_failure
)


def recover_stale_jobs(
    repository: Repository, queue_lane: JobQueueLane | str | None = None
) -> int:
    """Close abandoned running records left by a crash or laptop restart."""

    now = datetime.now(timezone.utc)
    recovered = 0
    for job in repository.list_jobs(limit=500):
        if job.status not in {JobStatus.running, JobStatus.cancel_requested}:
            continue
        lane_value = (
            queue_lane.value if isinstance(queue_lane, JobQueueLane) else queue_lane
        )
        if lane_value and job.queue_lane.value != lane_value:
            continue
        limit = STALE_JOB_SECONDS.get(job.job_type, 60 * 60)
        try:
            updated = datetime.fromisoformat(job.updated_at.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            updated = now
        age = max(0.0, (now - updated).total_seconds())
        if age <= limit:
            continue
        if job.status == JobStatus.cancel_requested:
            if repository.acknowledge_job_cancellation(job.job_id):
                if job.autonomy_run_id:
                    try:
                        from pipeline.autonomy import finalize_cancelled_autonomy_run

                        finalize_cancelled_autonomy_run(
                            repository, job.autonomy_run_id
                        )
                    except Exception as exc:
                        print(
                            "[worker] WARNING: could not finalize stale cancelled run: "
                            f"{safe_text(exc)}",
                            flush=True,
                        )
                else:
                    _restore_workflow_after_terminal_failure(repository, job)
                recovered += 1
            continue
        stale_error = (
            f"Worker stopped updating this {job.job_type} job for "
            f"{int(age // 60)} minutes; it was released from the queue. Retry it if needed."
        )
        job.last_error = stale_error
        job.error = stale_error
        job.failure_kind = "worker_lost"
        job.traceback = None
        if job.attempts < job.max_attempts:
            decision = classify_failure(
                job.job_type,
                job.attempts,
                TimeoutError(stale_error),
            )
            job.status = JobStatus.queued
            job.stage = "retry_wait"
            job.progress = 0
            job.available_at = retry_time(decision.delay_seconds)
            job.completed_at = None
        else:
            job.status = JobStatus.failed
            job.stage = "failed_stale_worker"
            job.completed_at = now_iso()
        if not repository.update_job_if_status(job, JobStatus.running):
            continue
        if job.status == JobStatus.failed:
            restore_error = _restore_workflow_after_terminal_failure(
                repository, job
            )
            if restore_error:
                print(
                    "[worker] WARNING: could not restore revision workflow state "
                    f"for {job.job_id}: {restore_error}",
                    flush=True,
                )
            _reconcile_autonomy_after_job(repository, job)
        recovered += 1
    return recovered


def run_one(
    repository: Repository, queue_lane: JobQueueLane | str | None = None
) -> bool:
    job = repository.claim_next_job(queue_lane)
    if not job:
        return False
    try:
        ctx = JobContext(repository, job)
    except JobCancelled:
        _acknowledge_cancel_request(repository, job)
        return True
    handler = HANDLERS.get(job.job_type)
    if not handler:
        job.status = JobStatus.failed
        job.error = f"No handler registered for job_type={job.job_type}"
        job.stage = "failed"
        if repository.update_job_if_status(job, JobStatus.running):
            _reconcile_autonomy_after_job(repository, job)
        else:
            _acknowledge_cancel_request(repository, job)
        return True
    try:
        contract = contract_for(job.job_type)
        # Handlers retain their legacy field checks because historical queues may
        # contain partially denormalized jobs. Output validation is enforced here.
        started_at = time.monotonic()
        ctx.start_heartbeat()
        ctx.progress(1, "running")
        with job_deadline(job.job_type):
            outputs = handler(ctx)
        contract.validate_outputs(outputs)
        ctx.raise_if_cancelled()
        job.output_paths.update(outputs)
        job.status = JobStatus.completed
        job.progress = 100
        job.stage = "completed"
        job.completed_at = now_iso()
        if repository.update_job_if_status(job, JobStatus.running):
            ctx.log(
                "completed",
                event="stage_completed",
                fields={
                    "elapsed_seconds": round(time.monotonic() - started_at, 3),
                    "outputs": sorted(outputs),
                },
            )
            _reconcile_autonomy_after_job(repository, job, logger=ctx.log)
        else:
            ctx.log("completion discarded because the job was cancelled")
    except JobCancelled as exc:
        ctx.log(str(exc))
    except Exception as exc:
        decision = classify_failure(job.job_type, job.attempts, exc)
        job.error = safe_text(exc)
        job.last_error = job.error
        job.failure_kind = decision.kind
        job.traceback = traceback_module.format_exc()
        if decision.retryable and job.attempts < job.max_attempts:
            job.status = JobStatus.queued
            job.progress = 0
            job.stage = "retry_wait"
            job.available_at = retry_time(decision.delay_seconds)
            job.completed_at = None
        else:
            job.status = JobStatus.failed
            job.stage = "failed"
            job.available_at = None
            job.completed_at = now_iso()
        if repository.update_job_if_status(job, JobStatus.running):
            if job.status == JobStatus.queued:
                ctx.log(
                    f"RETRY: attempt {job.attempts}/{job.max_attempts} failed "
                    f"({decision.kind}); next attempt at {job.available_at}",
                    event="stage_retry_scheduled",
                    level="WARNING",
                    fields={"failure_kind": decision.kind},
                )
                ctx.log(str(exc), event="stage_failure", level="WARNING")
            else:
                restore_error = _restore_workflow_after_terminal_failure(
                    repository, job
                )
                if restore_error:
                    ctx.log(
                        "Could not restore the prior revision workflow state: "
                        + restore_error,
                        event="workflow_restore_failed",
                        level="WARNING",
                    )
                ctx.log(
                    "FAILED: " + str(exc),
                    event="stage_failed",
                    level="ERROR",
                    fields={"failure_kind": decision.kind},
                )
                ctx.log(job.traceback or "", event="stage_traceback", level="ERROR")
                _reconcile_autonomy_after_job(repository, job, logger=ctx.log)
        else:
            ctx.log("failure discarded because the job was cancelled")
    finally:
        ctx.stop_heartbeat()
        _acknowledge_cancel_request(repository, job)
    return True


@dataclass(frozen=True)
class WorkerLease:
    lanes: tuple[str, ...]
    slot: int


def _unlock(handles: list[TextIO]) -> None:
    for handle in reversed(handles):
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


@contextmanager
def worker_process_lock(
    queue_lane: JobQueueLane | str | None = None, *, slot: int | None = None
):
    """Lease one configured process slot in a lane (or in every lane)."""

    lane_value = queue_lane.value if isinstance(queue_lane, JobQueueLane) else queue_lane
    lane_names = [lane_value] if lane_value else [lane.value for lane in JobQueueLane]
    settings = config.get_settings().jobs
    capacities = {lane: settings.workers_for(lane) for lane in lane_names}
    max_shared_slot = min(capacities.values())
    if slot is not None and (slot < 1 or slot > max_shared_slot):
        capacity_text = ", ".join(
            f"{lane}={capacity}" for lane, capacity in capacities.items()
        )
        raise ValueError(
            f"Worker slot {slot} is outside configured capacity ({capacity_text})."
        )

    db_path = database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_guards: list[TextIO] = []
    slot_handles: list[TextIO] = []
    try:
        # Old SynthPost workers held an exclusive unnumbered lane lock. Shared
        # guards let new slot workers coexist with one another while refusing
        # to overlap a still-running pre-concurrency worker during an upgrade.
        for lane_name in lane_names:
            legacy_path = db_path.with_suffix(f".worker.{lane_name}.lock")
            handle = legacy_path.open("a+", encoding="utf-8")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                handle.close()
                raise RuntimeError(
                    f"A legacy SynthPost worker still owns the {lane_name} lane; "
                    "stop it before starting the parallel worker pool."
                ) from exc
            legacy_guards.append(handle)

        selected_slot: int | None = None
        candidates = (
            [slot] if slot is not None else list(range(1, max_shared_slot + 1))
        )
        for candidate in candidates:
            assert candidate is not None
            candidate_handles: list[TextIO] = []
            try:
                for lane_name in lane_names:
                    lock_path = db_path.with_suffix(
                        f".worker.{lane_name}.{candidate}.lock"
                    )
                    handle = lock_path.open("a+", encoding="utf-8")
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        handle.close()
                        raise
                    candidate_handles.append(handle)
            except BlockingIOError:
                _unlock(candidate_handles)
                continue
            selected_slot = candidate
            slot_handles = candidate_handles
            break

        if selected_slot is None:
            label = lane_value or "all"
            raise RuntimeError(
                f"No free {label} worker slots (configured capacity={max_shared_slot})."
            )
        for handle in slot_handles:
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
        yield WorkerLease(tuple(lane_names), selected_slot)
    finally:
        _unlock(slot_handles)
        _unlock(legacy_guards)


def run_loop(
    *,
    once: bool = False,
    interval: float = 1.0,
    queue_lane: JobQueueLane | str | None = None,
    slot: int | None = None,
) -> None:
    with worker_process_lock(queue_lane, slot=slot) as lease:
        print(
            f"SynthPost worker started: lanes={','.join(lease.lanes)} slot={lease.slot}",
            flush=True,
        )
        repository = get_repository()
        try:
            recovered = recover_stale_jobs(repository, queue_lane)
            if recovered:
                print(f"Recovered {recovered} stale running job(s).", flush=True)
            if "editorial" in lease.lanes and lease.slot == 1:
                from pipeline.autonomy import reconcile_autonomy_runs

                reconcile_autonomy_runs(repository)
            last_recovery = time.monotonic()
            while True:
                did_work = run_one(repository, queue_lane)
                if once:
                    return
                if time.monotonic() - last_recovery >= 30:
                    recovered = recover_stale_jobs(repository, queue_lane)
                    if recovered:
                        print(
                            f"Recovered {recovered} stale running job(s).",
                            flush=True,
                        )
                    if "editorial" in lease.lanes and lease.slot == 1:
                        from pipeline.autonomy import reconcile_autonomy_runs

                        reconcile_autonomy_runs(repository)
                    last_recovery = time.monotonic()
                if not did_work:
                    time.sleep(interval)
        finally:
            repository.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the local SynthPost Studio SQLite-backed worker."
    )
    parser.add_argument(
        "--once", action="store_true", help="Run one queued job and exit."
    )
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument(
        "--lane",
        choices=["all", *[lane.value for lane in JobQueueLane]],
        default="all",
        help="Consume one independent queue lane, or all lanes for compatibility.",
    )
    parser.add_argument(
        "--slot",
        type=int,
        help="Explicit 1-based worker slot. Omit to lease the first free slot.",
    )
    args = parser.parse_args()
    run_loop(
        once=args.once,
        interval=args.interval,
        queue_lane=None if args.lane == "all" else args.lane,
        slot=args.slot,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("SynthPost worker stopped.", flush=True)
