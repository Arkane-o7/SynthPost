from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse

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
        if job.status in {JobStatus.completed, JobStatus.failed}:
            return public_job(job)
        job.status = JobStatus.cancelled
        job.stage = "cancelled"
        job.available_at = None
        repository.upsert_job(job)
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


@router.get("/job-events")
def job_events() -> StreamingResponse:
    def stream():
        last = ""
        while True:
            repository = get_repository()
            try:
                payload = [
                    public_job(job)
                    for job in repository.list_jobs(limit=50)
                ]
            finally:
                repository.close()
            encoded = json.dumps(payload, sort_keys=True)
            if encoded != last:
                yield f"event: jobs\ndata: {encoded}\n\n"
                last = encoded
            time.sleep(1.0)

    return StreamingResponse(stream(), media_type="text/event-stream")
