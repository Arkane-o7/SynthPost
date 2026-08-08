from __future__ import annotations

import subprocess
import sys

from fastapi import APIRouter, HTTPException

from pipeline.api.schemas import (
    AutonomyOutputRevealView,
    AutonomyRunCreate,
    AutonomyRunView,
)
from pipeline.autonomy import (
    advance_autonomy_run,
    autonomy_run_view,
    cancel_autonomy_run,
    reconcile_autonomy_runs,
    retry_autonomy_run,
    review_autonomy_run,
    start_autonomy_run,
)
from pipeline.channels import ChannelId
from pipeline.db.repository import Repository, get_repository
from pipeline.models import AutonomyPolicy, AutonomyRun, AutonomyRunStatus
from pipeline.storage import PROJECT_ROOT, project_relative, resolve_project_path


router = APIRouter(prefix="/api/autonomy", tags=["autonomy"])


def _view(repository: Repository, run: AutonomyRun) -> AutonomyRunView:
    return AutonomyRunView.model_validate(autonomy_run_view(repository, run))


@router.post("/runs", response_model=AutonomyRunView)
def create_run(payload: AutonomyRunCreate) -> AutonomyRunView:
    repository = get_repository()
    try:
        policy = AutonomyPolicy(
            provider=payload.provider,
            target_duration_seconds=payload.target_duration_seconds,
            narration_mode=payload.narration_mode,
            category=payload.category,
            render_profile=payload.render_profile,
            max_repairs_per_stage=payload.max_repairs_per_stage,
        )
        run = start_autonomy_run(
            repository,
            episode_id=payload.episode_id,
            story_id=payload.story_id,
            policy=policy,
        )
        return _view(repository, run)
    finally:
        repository.close()


@router.get("/runs", response_model=list[AutonomyRunView])
def list_runs(
    channel_id: ChannelId | None = None,
    episode_id: str | None = None,
    status: AutonomyRunStatus | None = None,
    limit: int = 100,
) -> list[AutonomyRunView]:
    repository = get_repository()
    try:
        reconcile_autonomy_runs(repository)
        return [
            _view(repository, run)
            for run in repository.list_autonomy_runs(
                channel_id=channel_id,
                episode_id=episode_id,
                status=status,
                limit=limit,
            )
        ]
    finally:
        repository.close()


@router.get("/runs/{run_id}", response_model=AutonomyRunView)
def read_run(run_id: str) -> AutonomyRunView:
    repository = get_repository()
    try:
        run = repository.get_autonomy_run(run_id)
        if run.status in {AutonomyRunStatus.queued, AutonomyRunStatus.running}:
            run = advance_autonomy_run(repository, run_id)
        return _view(repository, run)
    finally:
        repository.close()


@router.post("/runs/{run_id}/cancel", response_model=AutonomyRunView)
def cancel_run(run_id: str) -> AutonomyRunView:
    repository = get_repository()
    try:
        return _view(repository, cancel_autonomy_run(repository, run_id))
    finally:
        repository.close()


@router.post("/runs/{run_id}/retry", response_model=AutonomyRunView)
def retry_run(run_id: str) -> AutonomyRunView:
    repository = get_repository()
    try:
        return _view(repository, retry_autonomy_run(repository, run_id))
    finally:
        repository.close()


@router.post("/runs/{run_id}/accept", response_model=AutonomyRunView)
def accept_run(run_id: str) -> AutonomyRunView:
    repository = get_repository()
    try:
        run = review_autonomy_run(
            repository, run_id, AutonomyRunStatus.accepted
        )
        return _view(repository, run)
    finally:
        repository.close()


@router.post("/runs/{run_id}/reject", response_model=AutonomyRunView)
def reject_run(run_id: str) -> AutonomyRunView:
    repository = get_repository()
    try:
        run = review_autonomy_run(
            repository, run_id, AutonomyRunStatus.rejected
        )
        return _view(repository, run)
    finally:
        repository.close()


@router.post(
    "/runs/{run_id}/reveal-output", response_model=AutonomyOutputRevealView
)
def reveal_run_output(run_id: str) -> AutonomyOutputRevealView:
    repository = get_repository()
    try:
        run = repository.get_autonomy_run(run_id)
        if not run.final_output_path:
            raise HTTPException(status_code=404, detail="Run has no final output yet")
        output = resolve_project_path(run.final_output_path).resolve()
        if not output.is_relative_to(PROJECT_ROOT.resolve()):
            raise HTTPException(status_code=400, detail="Final output is outside the project")
        if not output.is_file():
            raise HTTPException(status_code=404, detail="Final output file is missing")
        if sys.platform != "darwin":
            raise HTTPException(
                status_code=501, detail="Show in Finder is only available on macOS"
            )
        try:
            subprocess.run(["open", "-R", str(output)], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise HTTPException(
                status_code=500, detail="Finder could not reveal the output"
            ) from exc
        return AutonomyOutputRevealView(
            revealed=True, path=project_relative(output)
        )
    finally:
        repository.close()
