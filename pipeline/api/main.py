from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pipeline import config
from pipeline.api.schemas import (
    CandidateAction,
    CustomTopic,
    CustomUrl,
    DiscoveryStart,
    EpisodeCreate,
    EpisodePatch,
    GenerateScriptRequest,
    ManualScript,
    ManualStory,
    ProjectCreate,
    ProjectPatch,
    RenderRequest,
    SourceCreate,
    SourcePatch,
    VisualPatch,
    VisualStageRequest,
)
from pipeline.api.routes.jobs import router as jobs_router
from pipeline.db.repository import NotFoundError, Repository, get_repository
from pipeline.discovery.discover import (
    add_custom_topic,
    add_custom_url,
    add_manual_story,
    discover_from_source,
    rescore_existing_candidates,
)
from pipeline.discovery.assignment_desk import rebuild_assignment_desk
from pipeline.discovery.seeds import seed_sources
from pipeline.editorial.charter import load_editorial_charter
from pipeline.manifest_builder import build_story_manifest
from pipeline.narration.service import load_narration_artifact
from pipeline.models import (
    ReviewStatus,
    ScriptDocument,
    ScriptStatus,
    SourceDefinition,
    StorySelectionStatus,
    StoryWorkflowState,
    TimelinePlan,
    TimelineStatus,
)
from pipeline.observability import LogContext, format_event
from pipeline.scripts.generation import (
    approve_script,
    begin_script_generation,
    reconcile_script_revision_workflows,
    save_manual_script,
)
from pipeline.storage import (
    PROJECT_ROOT,
    episode_media_inbox_dir,
    project_relative,
    resolve_project_path,
)
from pipeline.timeline.planner import approve_timeline, generate_timeline
from pipeline.timeline.templates import template_registry_json
from pipeline.timeline.validation import validate_timeline
from pipeline.visuals.providers import (
    SUPPORTED_VISUAL_EXTENSIONS,
    analyze_visual,
    approve_visual,
    download_visual,
    reject_visual,
    stage_local_visual,
    update_visual,
)

app = FastAPI(title="SynthPost Studio API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(jobs_router)


async def _write_streamed_upload(
    request: Request,
    destination: Path,
    *,
    max_bytes: int,
) -> int:
    """Write a request body atomically while enforcing the configured size cap."""

    partial_path = destination.with_name(
        f".{destination.name}.{uuid4().hex}.uploading"
    )
    bytes_written = 0
    try:
        with partial_path.open("wb") as handle:
            async for chunk in request.stream():
                if not chunk:
                    continue
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise ValueError(
                        "visual upload exceeds SYNTHPOST_VISUAL_DOWNLOAD_MAX_BYTES"
                    )
                handle.write(chunk)
        if bytes_written == 0:
            raise ValueError("empty upload body")
        partial_path.replace(destination)
        return bytes_written
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise


def repo() -> Repository:
    return get_repository()


@app.on_event("startup")
def startup() -> None:
    config.validate_startup()
    repository = repo()
    try:
        seed_sources(repository)
        rescored = rescore_existing_candidates(repository)
        if rescored:
            rebuild_assignment_desk(repository, use_ai=False)
        reconciled = reconcile_script_revision_workflows(repository)
        if reconciled:
            print(
                format_event(
                    "workflow_reconciled",
                    f"Reopened {reconciled} stor{'y' if reconciled == 1 else 'ies'} "
                    "with a newer unapproved script revision",
                    context=LogContext(stage="startup"),
                    fields={"story_count": reconciled},
                )
            )
    finally:
        repository.close()


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=404, content={"error": {"code": "not_found", "message": str(exc)}}
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "validation_error", "message": str(exc)}},
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    jobs = config.get_settings().jobs
    return {
        "ok": True,
        "name": "SynthPost Studio",
        "version": "2.0.0",
        "worker_capacity": {
            "editorial": jobs.editorial_workers,
            "media": jobs.media_workers,
            "render": jobs.render_workers,
        },
    }


@app.get("/api/templates")
def templates() -> list[dict[str, Any]]:
    return template_registry_json()


@app.get("/api/editorial/charter")
def editorial_charter() -> dict[str, Any]:
    return load_editorial_charter()


@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    repository = repo()
    try:
        return [
            project.model_dump(mode="json") for project in repository.list_projects()
        ]
    finally:
        repository.close()


@app.post("/api/projects")
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    repository = repo()
    try:
        project = repository.create_project(
            payload.title,
            default_category=payload.default_category,
            default_render_profile=payload.default_render_profile,
        )
        return project.model_dump(mode="json")
    finally:
        repository.close()


@app.get("/api/projects/{project_id}")
def read_project(project_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        return repository.get_project(project_id).model_dump(mode="json")
    finally:
        repository.close()


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, patch: ProjectPatch) -> dict[str, Any]:
    repository = repo()
    try:
        return repository.update_project(
            project_id, patch.model_dump(exclude_none=True)
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.get("/api/episodes")
def list_episodes(project_id: str | None = None) -> list[dict[str, Any]]:
    repository = repo()
    try:
        return [
            episode.model_dump(mode="json")
            for episode in repository.list_episodes(project_id)
        ]
    finally:
        repository.close()


@app.post("/api/projects/{project_id}/episodes")
def create_episode(project_id: str, payload: EpisodeCreate) -> dict[str, Any]:
    repository = repo()
    try:
        return repository.create_episode(
            project_id, payload.title, render_profile=payload.render_profile
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.get("/api/episodes/{episode_id}")
def read_episode(episode_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        return repository.get_episode(episode_id).model_dump(mode="json")
    finally:
        repository.close()


@app.patch("/api/episodes/{episode_id}")
def update_episode(episode_id: str, patch: EpisodePatch) -> dict[str, Any]:
    repository = repo()
    try:
        return repository.update_episode(
            episode_id, patch.model_dump(exclude_none=True)
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.get("/api/sources")
def list_sources(
    enabled: bool | None = None, category: str | None = None
) -> list[dict[str, Any]]:
    repository = repo()
    try:
        return [
            source.model_dump(mode="json")
            for source in repository.list_sources(enabled=enabled, category=category)
        ]
    finally:
        repository.close()


@app.post("/api/sources")
def create_source(payload: SourceCreate) -> dict[str, Any]:
    repository = repo()
    try:
        source = SourceDefinition(**payload.model_dump())
        repository.upsert_source(source)
        return source.model_dump(mode="json")
    finally:
        repository.close()


@app.patch("/api/sources/{source_id}")
def update_source(source_id: str, patch: SourcePatch) -> dict[str, Any]:
    repository = repo()
    try:
        return repository.update_source(
            source_id, patch.model_dump(exclude_none=True)
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/sources/{source_id}/test")
def test_source(source_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        source = repository.get_source(source_id)
        candidates = discover_from_source(source)[:5]
        return {
            "ok": True,
            "count": len(candidates),
            "sample": [candidate.model_dump(mode="json") for candidate in candidates],
        }
    finally:
        repository.close()


@app.post("/api/discovery/start")
def start_discovery(payload: DiscoveryStart) -> dict[str, Any]:
    repository = repo()
    try:
        active = repository.active_job("discovery", episode_id=payload.episode_id)
        if active:
            return active.model_dump(mode="json")
        job = repository.create_job(
            "discovery", episode_id=payload.episode_id, payload=payload.model_dump()
        )
        return job.model_dump(mode="json")
    finally:
        repository.close()


@app.get("/api/discovery/candidates")
def list_candidates(
    episode_id: str | None = None,
    status: StorySelectionStatus | None = None,
    category: str | None = None,
    search: str | None = None,
    lane: str | None = None,
    include_duplicates: bool = False,
    include_expired: bool = False,
) -> list[dict[str, Any]]:
    repository = repo()
    try:
        candidates = repository.list_candidates(
            episode_id=episode_id,
            status=status,
            category=category,
            search=search,
            limit=250,
            include_duplicates=include_duplicates,
            include_expired=include_expired,
        )
        if lane:
            candidates = [item for item in candidates if item.assignment_lane == lane]
        return [candidate.model_dump(mode="json") for candidate in candidates]
    finally:
        repository.close()


@app.get("/api/discovery/candidates/{candidate_id}")
def read_candidate(candidate_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        return repository.get_candidate(candidate_id).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/discovery/candidates/{candidate_id}/select")
def select_candidate(candidate_id: str, payload: CandidateAction) -> dict[str, Any]:
    if not payload.episode_id:
        raise ValueError("episode_id is required to select a story")
    repository = repo()
    try:
        return repository.select_candidate(candidate_id, payload.episode_id).model_dump(
            mode="json"
        )
    finally:
        repository.close()


@app.post("/api/discovery/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str, payload: CandidateAction) -> dict[str, Any]:
    repository = repo()
    try:
        return repository.reject_candidate(candidate_id, payload.reasons).model_dump(
            mode="json"
        )
    finally:
        repository.close()


@app.post("/api/discovery/custom-topic")
def api_custom_topic(payload: CustomTopic) -> dict[str, Any]:
    repository = repo()
    try:
        return add_custom_topic(
            repository,
            title=payload.title,
            summary=payload.summary,
            category=payload.category,
            episode_id=payload.episode_id,
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/discovery/custom-url")
def api_custom_url(payload: CustomUrl) -> dict[str, Any]:
    repository = repo()
    try:
        return add_custom_url(
            repository,
            url=payload.url,
            title=payload.title,
            summary=payload.summary,
            category=payload.category,
            episode_id=payload.episode_id,
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/discovery/manual-story")
def api_manual_story(payload: ManualStory) -> dict[str, Any]:
    repository = repo()
    try:
        return add_manual_story(
            repository,
            title=payload.title,
            body=payload.body,
            category=payload.category,
            episode_id=payload.episode_id,
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/research/start")
def start_research(story_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        episode = repository.episode_for_story(story_id)
        job = repository.create_job(
            "research", episode_id=episode.episode_id, story_id=story_id
        )
        return job.model_dump(mode="json")
    finally:
        repository.close()


@app.get("/api/stories/{story_id}/research")
def read_research(story_id: str) -> dict[str, Any] | None:
    repository = repo()
    try:
        return repository.latest_research_pack(story_id)
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/script/generate")
def start_script_generation(
    story_id: str, payload: GenerateScriptRequest
) -> dict[str, Any]:
    repository = repo()
    try:
        episode = repository.episode_for_story(story_id)
        active_job = repository.active_job("script_generate", story_id=story_id)
        if active_job:
            return active_job.model_dump(mode="json")
        if not repository.latest_research_pack(story_id):
            raise ValueError(
                "Research must be completed before generating a script revision"
            )
        restore_state = begin_script_generation(repository, story_id)
        job_payload = payload.model_dump()
        job_payload["_previous_workflow_state"] = restore_state.value
        try:
            job = repository.create_job(
                "script_generate",
                episode_id=episode.episode_id,
                story_id=story_id,
                payload=job_payload,
            )
        except Exception:
            candidate = repository.candidate_for_story(story_id)
            if candidate.workflow_state == StoryWorkflowState.script_generating:
                repository.transition_story(story_id, restore_state)
            raise
        return job.model_dump(mode="json")
    finally:
        repository.close()


@app.get("/api/stories/{story_id}/script")
def read_script(story_id: str, approved: bool = False) -> dict[str, Any] | None:
    repository = repo()
    try:
        script = repository.latest_script(story_id, approved=approved)
        return script.model_dump(mode="json") if script else None
    finally:
        repository.close()


@app.get("/api/stories/{story_id}/generation-audits")
def generation_audits(story_id: str, limit: int = 50) -> list[dict[str, Any]]:
    repository = repo()
    try:
        return [
            audit.model_dump(mode="json")
            for audit in repository.list_generation_audits(story_id, limit=limit)
        ]
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/script/manual")
def save_script(story_id: str, payload: ManualScript) -> dict[str, Any]:
    repository = repo()
    try:
        if repository.active_job("script_generate", story_id=story_id):
            raise ValueError(
                "Wait for the active script generation to finish before saving edits"
            )
        return save_manual_script(
            repository,
            story_id,
            payload.headline,
            payload.text,
            category=payload.category,
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/script/approve")
def api_approve_script(story_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        if repository.active_job("script_generate", story_id=story_id):
            raise ValueError(
                "Wait for the active script generation to finish before approving"
            )
        script = approve_script(repository, story_id)
        # Narration and visual discovery both become eligible after approval.
        # The queue's same-story serialization still prevents overlapping writes.
        episode = repository.episode_for_story(story_id)
        for job_type in ("narration_generate", "visual_search"):
            try:
                if not repository.active_job(job_type, story_id=story_id):
                    repository.create_job(
                        job_type,
                        episode_id=episode.episode_id,
                        story_id=story_id,
                    )
            except Exception as exc:
                print(
                    format_event(
                        "post_script_job_enqueue_failed",
                        f"Failed to auto-queue {job_type}: {exc}",
                        level="WARNING",
                        context=LogContext(
                            story_id=story_id, stage="script_approve"
                        ),
                    )
                )
        return script.model_dump(mode="json")
    finally:
        repository.close()


@app.get("/api/stories/{story_id}/narration")
def read_narration(story_id: str) -> dict[str, Any] | None:
    repository = repo()
    try:
        artifact = load_narration_artifact(
            repository, story_id, require_current=False
        )
        return artifact.model_dump(mode="json") if artifact else None
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/narration/generate")
def queue_narration(story_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        script = repository.latest_script(story_id)
        if not script or script.status != ScriptStatus.approved:
            raise ValueError(
                "Approve the latest script before generating Kokoro narration"
            )
        episode = repository.episode_for_story(story_id)
        job = repository.active_job(
            "narration_generate", story_id=story_id
        ) or repository.create_job(
            "narration_generate",
            episode_id=episode.episode_id,
            story_id=story_id,
        )
        return job.model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/visuals/search")
def search_visuals(story_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        episode = repository.episode_for_story(story_id)
        job = repository.active_job(
            "visual_search", story_id=story_id
        ) or repository.create_job(
            "visual_search", episode_id=episode.episode_id, story_id=story_id
        )
        return job.model_dump(mode="json")
    finally:
        repository.close()


@app.get("/api/stories/{story_id}/visuals")
def list_visuals(story_id: str) -> list[dict[str, Any]]:
    repository = repo()
    try:
        return [
            visual.model_dump(mode="json")
            for visual in repository.list_visuals(story_id)
        ]
    finally:
        repository.close()


@app.get("/api/stories/{story_id}/visuals/local-folder")
def local_visual_folder(story_id: str) -> dict[str, str]:
    repository = repo()
    try:
        episode = repository.episode_for_story(story_id)
        folder = episode_media_inbox_dir(episode.project_id, episode.episode_id)
        folder.mkdir(parents=True, exist_ok=True)
        return {
            "project_id": episode.project_id,
            "episode_id": episode.episode_id,
            "path": project_relative(folder),
        }
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/visuals/stage-local")
def stage_visual(story_id: str, payload: VisualStageRequest) -> dict[str, Any]:
    repository = repo()
    try:
        return stage_local_visual(
            repository,
            story_id,
            payload.path,
            title=payload.title,
            content_role=payload.content_role,
            section_ids=payload.section_ids,
            rights_tier=payload.rights_tier,
            usage_basis=payload.usage_basis,
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/visuals/upload-bytes")
async def upload_visual_bytes(
    story_id: str, request: Request, filename: str = "upload.bin"
) -> dict[str, Any]:
    repository = repo()
    try:
        episode_id = repository.episode_for_story(story_id).episode_id
        episode = repository.get_episode(episode_id)
        upload_dir = episode_media_inbox_dir(
            episode.project_id, episode_id
        ) / "uploads" / story_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe = (
            "".join(
                char
                for char in Path(filename).name
                if char.isalnum() or char in {"_", "-", "."}
            )
            or "upload.bin"
        )
        if Path(safe).suffix.lower() not in SUPPORTED_VISUAL_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_VISUAL_EXTENSIONS))
            raise ValueError(f"unsupported visual file type; expected one of: {supported}")
        safe_path = Path(safe)
        path = upload_dir / (
            f"{safe_path.stem}-{uuid4().hex[:10]}{safe_path.suffix.lower()}"
        )
        max_bytes = config.get_settings().visuals.download_max_bytes
        await _write_streamed_upload(request, path, max_bytes=max_bytes)
        return stage_local_visual(
            repository,
            story_id,
            path,
            title=Path(filename).stem,
            usage_basis="browser_upload",
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/visuals/{asset_id}/approve")
def api_approve_visual(asset_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        return approve_visual(repository, asset_id, manual=False).model_dump(
            mode="json"
        )
    finally:
        repository.close()


@app.post("/api/visuals/{asset_id}/analyze")
def api_analyze_visual(asset_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        return analyze_visual(repository, asset_id).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/visuals/{asset_id}/download")
def api_download_visual(asset_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        return download_visual(repository, asset_id).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/visuals/{asset_id}/manual-approve")
def api_manual_approve_visual(
    asset_id: str, patch: VisualPatch | None = None
) -> dict[str, Any]:
    repository = repo()
    try:
        return approve_visual(
            repository,
            asset_id,
            manual=True,
            attribution_text=patch.attribution_text if patch else None,
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/visuals/{asset_id}/reject")
def api_reject_visual(asset_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        return reject_visual(repository, asset_id).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/visuals/{asset_id}/block")
def api_block_visual(asset_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        return reject_visual(repository, asset_id, blocked=True).model_dump(mode="json")
    finally:
        repository.close()


@app.patch("/api/visuals/{asset_id}")
def api_patch_visual(asset_id: str, patch: VisualPatch) -> dict[str, Any]:
    repository = repo()
    try:
        return update_visual(
            repository, asset_id, patch.model_dump(exclude_unset=True)
        ).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/timeline/generate")
def api_generate_timeline(story_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        return generate_timeline(repository, story_id).model_dump(mode="json")
    finally:
        repository.close()


@app.get("/api/stories/{story_id}/timeline")
def read_timeline(story_id: str, approved: bool = False) -> dict[str, Any] | None:
    repository = repo()
    try:
        timeline = repository.latest_timeline(story_id, approved=approved)
        return timeline.model_dump(mode="json") if timeline else None
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/timeline/save")
def save_timeline(story_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    repository = repo()
    try:
        payload["story_id"] = story_id
        plan = TimelinePlan.model_validate(payload)
        errors, warnings = validate_timeline(plan)
        plan.validation_errors = errors
        plan.validation_warnings = warnings
        return repository.save_timeline(plan).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/timeline/validate")
def api_validate_timeline(
    story_id: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    repository = repo()
    try:
        plan = (
            TimelinePlan.model_validate(payload)
            if payload
            else repository.latest_timeline(story_id)
        )
        if not plan:
            raise ValueError("No timeline exists")
        errors, warnings = validate_timeline(plan)
        return {"ok": not errors, "errors": errors, "warnings": warnings}
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/timeline/approve")
def api_approve_timeline(story_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        return approve_timeline(repository, story_id).model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/manifest/build")
def api_build_manifest(story_id: str, payload: RenderRequest) -> dict[str, Any]:
    repository = repo()
    try:
        return build_story_manifest(
            repository,
            story_id,
            render_profile=payload.render_profile,
            test_mode=payload.test_mode,
        )
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/render/avatar")
def api_render_avatar(story_id: str, payload: RenderRequest) -> dict[str, Any]:
    repository = repo()
    try:
        episode = repository.episode_for_story(story_id)
        candidate = repository.candidate_for_story(story_id)
        if candidate.workflow_state == StoryWorkflowState.timeline_approved:
            repository.transition_story(story_id, StoryWorkflowState.rendering_avatar)
        job = repository.active_job(
            "render_avatar",
            story_id=story_id,
            render_profile=payload.render_profile,
        ) or repository.create_job(
            "render_avatar",
            episode_id=episode.episode_id,
            story_id=story_id,
            render_profile=payload.render_profile,
            payload=payload.model_dump(),
        )
        return job.model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/stories/{story_id}/render/story")
def api_render_story(story_id: str, payload: RenderRequest) -> dict[str, Any]:
    repository = repo()
    try:
        episode = repository.episode_for_story(story_id)
        candidate = repository.candidate_for_story(story_id)
        if candidate.workflow_state == StoryWorkflowState.timeline_approved:
            repository.transition_story(
                story_id, StoryWorkflowState.rendering_composition
            )
        elif candidate.workflow_state == StoryWorkflowState.rendering_avatar:
            repository.transition_story(
                story_id, StoryWorkflowState.rendering_composition
            )
        job = repository.active_job(
            "render_story",
            story_id=story_id,
            render_profile=payload.render_profile,
        ) or repository.create_job(
            "render_story",
            episode_id=episode.episode_id,
            story_id=story_id,
            render_profile=payload.render_profile,
            payload=payload.model_dump(),
        )
        return job.model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/episodes/{episode_id}/assemble")
def api_assemble_episode(episode_id: str, payload: RenderRequest) -> dict[str, Any]:
    repository = repo()
    try:
        episode = repository.get_episode(episode_id)
        for story_id in episode.story_ids:
            try:
                candidate = repository.candidate_for_story(story_id)
                if candidate.workflow_state == StoryWorkflowState.rendering_composition:
                    repository.transition_story(story_id, StoryWorkflowState.assembling)
            except Exception as exc:
                # Assembly should still be queueable for an episode even if one
                # historical story record cannot be advanced cleanly.
                print(
                    format_event(
                        "workflow_transition_skipped",
                        f"Could not advance historical story before assembly: {exc}",
                        level="WARNING",
                        context=LogContext(
                            episode_id=episode_id,
                            story_id=story_id,
                            stage="assemble_episode",
                        ),
                    )
                )
        job = repository.active_job(
            "assemble_episode",
            episode_id=episode_id,
            render_profile=payload.render_profile,
        ) or repository.create_job(
            "assemble_episode",
            episode_id=episode_id,
            render_profile=payload.render_profile,
            payload=payload.model_dump(),
        )
        return job.model_dump(mode="json")
    finally:
        repository.close()


@app.post("/api/episodes/{episode_id}/reveal-output")
def api_reveal_episode_output(episode_id: str) -> dict[str, Any]:
    repository = repo()
    try:
        episode = repository.get_episode(episode_id)
        if not episode.final_output_path:
            raise HTTPException(status_code=404, detail="Episode has no final output yet")
        output = resolve_project_path(episode.final_output_path).resolve()
        project_root = PROJECT_ROOT.resolve()
        if not output.is_relative_to(project_root):
            raise HTTPException(status_code=400, detail="Final output is outside the project")
        if not output.is_file():
            raise HTTPException(status_code=404, detail="Final output file is missing")
        if sys.platform != "darwin":
            raise HTTPException(status_code=501, detail="Show in Finder is only available on macOS")
        try:
            subprocess.run(["open", "-R", str(output)], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise HTTPException(status_code=500, detail="Finder could not reveal the output") from exc
        return {"revealed": True, "path": project_relative(output)}
    finally:
        repository.close()


@app.get("/api/artifacts/{artifact_path:path}")
def serve_artifact(artifact_path: str) -> FileResponse:
    resolved = resolve_project_path(artifact_path).resolve()
    root = PROJECT_ROOT.resolve()
    if not resolved.is_relative_to(root):
        raise HTTPException(
            status_code=403, detail="Artifact path escapes project root"
        )
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(resolved)


# The remote/mobile build is served by the same localhost-only process as the
# API. Tailscale Serve can then proxy one port without exposing SQLite, media
# folders, the worker, or a development server directly to the network.
WEB_DIST = PROJECT_ROOT / "web" / "dist"
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="studio")


if __name__ == "__main__":
    import uvicorn

    settings = config.validate_startup()
    uvicorn.run(
        "pipeline.api.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=False,
    )
