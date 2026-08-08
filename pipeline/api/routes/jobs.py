from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse

from pipeline.channels import ChannelId
from pipeline.db.repository import get_repository
from pipeline.jobs.policy import default_max_attempts
from pipeline.models import JobStatus, StoryWorkflowState
from pipeline.storage import resolve_project_path

router = APIRouter(prefix="/api", tags=["jobs"])


def public_job(job) -> dict[str, Any]:
    """Return the Studio-safe view; full tracebacks stay in local logs/SQLite."""

    return job.model_dump(mode="json", exclude={"traceback"})


@router.get("/jobs")
def list_jobs(
    channel_id: ChannelId | None = None,
    story_id: str | None = None,
    episode_id: str | None = None,
    job_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    repository = get_repository()
    try:
        return [
            public_job(job)
            for job in repository.list_jobs(
                max(1, min(limit, 500)),
                channel_id=channel_id,
                story_id=story_id,
                episode_id=episode_id,
                job_type=job_type,
            )
        ]
    finally:
        repository.close()


@router.get("/jobs/{job_id}")
def read_job(job_id: str) -> dict[str, Any]:
    repository = get_repository()
    try:
        return public_job(repository.get_job(job_id))
    finally:
        repository.close()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    repository = get_repository()
    try:
        job = repository.get_job(job_id)
        if job.autonomy_run_id:
            from pipeline.autonomy import cancel_autonomy_run

            cancel_autonomy_run(repository, job.autonomy_run_id)
            return public_job(repository.get_job(job_id))
        if job.status in {
            JobStatus.completed,
            JobStatus.failed,
            JobStatus.cancelled,
            JobStatus.cancel_requested,
        }:
            return public_job(job)
        job = repository.request_job_cancellation(job_id)
        if job.status == JobStatus.cancel_requested:
            return public_job(job)
        if job.job_type == "script_generate" and job.story_id:
            candidate = repository.candidate_for_story(job.story_id)
            if candidate.workflow_state == StoryWorkflowState.script_generating:
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
        elif job.job_type == "research" and job.story_id:
            candidate = repository.candidate_for_story(job.story_id)
            if candidate.workflow_state == StoryWorkflowState.researching:
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
        elif job.job_type == "visual_search" and job.story_id:
            candidate = repository.candidate_for_story(job.story_id)
            if candidate.workflow_state == StoryWorkflowState.visuals_searching:
                repository.transition_story(
                    job.story_id, StoryWorkflowState.visuals_review
                )
        return public_job(job)
    finally:
        repository.close()


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: str) -> dict[str, Any]:
    repository = get_repository()
    try:
        job = repository.get_job(job_id)
        if job.autonomy_run_id:
            raise ValueError("Use the autonomy run controls to pause or stop this job")
        if job.status == JobStatus.paused:
            return public_job(job)
        if job.status != JobStatus.queued:
            raise ValueError("Only queued jobs can be paused; cancel a running job instead")
        job.status = JobStatus.paused
        job.stage = "paused_by_editor"
        repository.upsert_job(job)
        return public_job(job)
    finally:
        repository.close()


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict[str, Any]:
    repository = get_repository()
    try:
        job = repository.get_job(job_id)
        if job.autonomy_run_id:
            raise ValueError("Use the autonomy run controls to resume or retry this job")
        if job.status != JobStatus.paused:
            raise ValueError("Only paused jobs can be resumed")
        job.status = JobStatus.queued
        job.stage = "queued_after_pause"
        job.available_at = None
        repository.upsert_job(job)
        return public_job(job)
    finally:
        repository.close()


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict[str, Any]:
    repository = get_repository()
    try:
        job = repository.get_job(job_id)
        if job.autonomy_run_id:
            from pipeline.autonomy import retry_autonomy_run

            retry_autonomy_run(repository, job.autonomy_run_id)
            return public_job(repository.get_job(job_id))
        if job.status not in {JobStatus.failed, JobStatus.cancelled}:
            raise ValueError("Only failed or cancelled jobs can be retried")
        job.status = JobStatus.queued
        job.progress = 0
        job.stage = "queued_for_retry"
        job.last_error = job.error
        job.error = None
        job.traceback = None
        job.failure_kind = None
        job.available_at = None
        job.started_at = None
        job.completed_at = None
        job.attempts = 0
        job.max_attempts = default_max_attempts(job.job_type)
        repository.upsert_job(job)
        return public_job(job)
    finally:
        repository.close()


@router.get("/jobs/{job_id}/logs")
def job_logs(job_id: str) -> Response:
    repository = get_repository()
    try:
        job = repository.get_job(job_id)
        if not job.log_path:
            return Response("", media_type="text/plain")
        path = resolve_project_path(job.log_path)
        if not path.exists():
            return Response("", media_type="text/plain")
        return Response(
            path.read_text(encoding="utf-8", errors="replace"),
            media_type="text/plain",
        )
    finally:
        repository.close()


async def _job_event_stream(
    channel_id: ChannelId | None = None,
) -> AsyncIterator[str]:
    """Stream job updates without reserving a request-worker thread.

    A synchronous infinite generator is adapted by Starlette through its
    thread pool. Every open Studio tab would therefore retain one worker
    forever, eventually starving normal API requests and leaving Studio on
    its loading screen. An async generator sleeps cooperatively and is
    cancelled by StreamingResponse as soon as the client disconnects.
    """

    last = ""
    while True:
        repository = get_repository()
        try:
            payload = [
                public_job(job)
                for job in repository.list_jobs(limit=50, channel_id=channel_id)
            ]
        finally:
            repository.close()
        encoded = json.dumps(payload, sort_keys=True)
        if encoded != last:
            yield f"event: jobs\ndata: {encoded}\n\n"
            last = encoded
        await asyncio.sleep(1.0)


@router.get("/job-events")
async def job_events(channel_id: ChannelId | None = None) -> StreamingResponse:

    return StreamingResponse(
        _job_event_stream(channel_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
