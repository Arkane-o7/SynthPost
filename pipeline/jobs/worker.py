from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import traceback as traceback_module
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from assembly.stitch_episode import stitch_episode
from pipeline.db.repository import Repository, get_repository
from pipeline.discovery.discover import discover
from pipeline.manifest_builder import build_story_manifest
from pipeline.models import (
    EpisodeStatus,
    JobStatus,
    RenderJob,
    StoryWorkflowState,
    now_iso,
)
from pipeline.research.extract import build_research_pack
from pipeline.scripts.generation import generate_script
from pipeline.storage import PROJECT_ROOT, project_relative, story_manifest_path
from pipeline.timeline.planner import generate_timeline
from pipeline.visuals.providers import search_visuals


class JobContext:
    def __init__(self, repository: Repository, job: RenderJob):
        self.repository = repository
        self.job = job
        log_dir = PROJECT_ROOT / ".synthpost" / "jobs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = log_dir / f"{job.job_id}.log"
        self.job.log_path = project_relative(self.log_path)
        self.repository.upsert_job(self.job)

    def log(self, message: str) -> None:
        line = f"[{now_iso()}] {message}\n"
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        print(line, end="")

    def progress(self, progress: float, stage: str) -> None:
        self.job.progress = max(0.0, min(100.0, progress))
        self.job.stage = stage
        self.repository.upsert_job(self.job)
        self.log(f"{self.job.progress:.0f}% {stage}")


def handle_discovery(ctx: JobContext) -> dict[str, str]:
    payload = ctx.job.payload
    ctx.progress(5, "loading sources")
    candidates = discover(
        ctx.repository,
        episode_id=payload.get("episode_id"),
        category=payload.get("category"),
    )
    ctx.progress(100, f"discovered {len(candidates)} candidates")
    return {"candidate_count": str(len(candidates))}


def handle_research(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.story_id:
        raise ValueError("research job requires story_id")
    ctx.progress(10, "extracting source document")
    pack = build_research_pack(ctx.repository, ctx.job.story_id)
    ctx.progress(100, "research pack ready")
    return {"research_pack_id": pack.research_pack_id}


def handle_script_generate(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.story_id:
        raise ValueError("script job requires story_id")
    ctx.progress(10, "calling structured LLM provider")
    script = generate_script(
        ctx.repository,
        ctx.job.story_id,
        provider_name=ctx.job.payload.get("provider"),
        target_duration_seconds=int(
            ctx.job.payload.get("target_duration_seconds") or 600
        ),
    )
    ctx.progress(100, "script ready for review")
    return {"script_id": script.script_id}


def handle_visual_search(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.story_id:
        raise ValueError("visual search job requires story_id")
    ctx.progress(10, "using AI to plan image/video keywords")
    visuals = search_visuals(ctx.repository, ctx.job.story_id)
    downloadable = sum(1 for visual in visuals if visual.download_path)
    ctx.progress(
        100,
        f"found {len(visuals)} visual candidates ({downloadable} render-ready files)",
    )
    return {"visual_count": str(len(visuals))}


def handle_timeline_generate(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.story_id:
        raise ValueError("timeline job requires story_id")
    ctx.progress(15, "building deterministic timeline draft")
    plan = generate_timeline(ctx.repository, ctx.job.story_id)
    ctx.progress(100, "timeline draft ready")
    return {"timeline_id": plan.timeline_id}


def handle_render_avatar(ctx: JobContext) -> dict[str, str]:
    from pipeline.direction import avatar

    if not ctx.job.story_id:
        raise ValueError("render avatar job requires story_id")
    payload = ctx.job.payload
    render_profile = payload.get("render_profile") or ctx.job.render_profile
    test_mode = bool(payload.get("test_mode", False))
    force = bool(payload.get("force", False))
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
    direction = avatar.run(
        manifest_path,
        force=force,
        render=True,
        test_mode=test_mode,
        render_profile=render_profile,
    )
    if ctx.job.render_profile == "production":
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
    render_profile = payload.get("render_profile") or ctx.job.render_profile
    test_mode = bool(payload.get("test_mode", False))
    force = bool(payload.get("force", False))
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
    if ctx.job.render_profile == "production":
        candidate = ctx.repository.candidate_for_story(ctx.job.story_id)
        if candidate.workflow_state == StoryWorkflowState.rendering_composition:
            ctx.repository.transition_story(
                ctx.job.story_id, StoryWorkflowState.assembling
            )
    ctx.progress(100, "story render completed")
    return {"story_manifest": project_relative(manifest_path)}


def handle_assemble_episode(ctx: JobContext) -> dict[str, str]:
    if not ctx.job.episode_id:
        raise ValueError("assembly job requires episode_id")
    payload = ctx.job.payload
    ctx.progress(20, "normalizing and stitching story clips")
    test_mode = bool(payload.get("test_mode", False))
    output = stitch_episode(
        ctx.job.episode_id,
        force=bool(payload.get("force", False)),
        test_mode=test_mode,
        render_profile=payload.get("render_profile") or ctx.job.render_profile,
    )
    if not test_mode:
        episode = ctx.repository.get_episode(ctx.job.episode_id)
        episode.final_output_path = project_relative(output)
        episode.status = EpisodeStatus.completed
        episode.render_profile = str(
            payload.get("render_profile") or ctx.job.render_profile or "production"
        )
        episode.updated_at = now_iso()
        ctx.repository.upsert_episode(episode)
        for story_id in episode.story_ids:
            try:
                candidate = ctx.repository.candidate_for_story(story_id)
                if candidate.workflow_state == StoryWorkflowState.assembling:
                    ctx.repository.transition_story(
                        story_id, StoryWorkflowState.completed
                    )
            except Exception:
                pass
    ctx.progress(100, "episode assembly completed")
    return {"final_output_path": project_relative(output)}


HANDLERS: dict[str, Callable[[JobContext], dict[str, str]]] = {
    "discovery": handle_discovery,
    "research": handle_research,
    "script_generate": handle_script_generate,
    "visual_search": handle_visual_search,
    "timeline_generate": handle_timeline_generate,
    "render_avatar": handle_render_avatar,
    "render_story": handle_render_story,
    "assemble_episode": handle_assemble_episode,
}


def run_one(repository: Repository) -> bool:
    job = repository.claim_next_job()
    if not job:
        return False
    ctx = JobContext(repository, job)
    handler = HANDLERS.get(job.job_type)
    if not handler:
        job.status = JobStatus.failed
        job.error = f"No handler registered for job_type={job.job_type}"
        job.stage = "failed"
        repository.upsert_job(job)
        return True
    try:
        ctx.progress(1, "running")
        outputs = handler(ctx)
        job.output_paths.update(outputs)
        job.status = JobStatus.completed
        job.progress = 100
        job.stage = "completed"
        job.completed_at = now_iso()
        repository.upsert_job(job)
        ctx.log("completed")
    except Exception as exc:
        if job.job_type == "script_generate" and job.story_id:
            try:
                candidate = repository.candidate_for_story(job.story_id)
                if candidate.workflow_state == StoryWorkflowState.script_generating:
                    repository.transition_story(
                        job.story_id, StoryWorkflowState.research_ready
                    )
            except Exception:
                pass
        job.status = JobStatus.failed
        job.error = str(exc)
        job.traceback = traceback_module.format_exc()
        job.stage = "failed"
        job.completed_at = now_iso()
        repository.upsert_job(job)
        ctx.log("FAILED: " + str(exc))
        ctx.log(job.traceback or "")
    return True


def run_loop(*, once: bool = False, interval: float = 1.0) -> None:
    repository = get_repository()
    try:
        while True:
            did_work = run_one(repository)
            if once:
                return
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
    args = parser.parse_args()
    run_loop(once=args.once, interval=args.interval)


if __name__ == "__main__":
    main()
