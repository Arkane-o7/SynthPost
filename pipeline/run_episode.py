from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from assembly.stitch_episode import stitch_episode
from pipeline.db.repository import get_repository
from pipeline.discovery.discover import add_manual_story
from pipeline.discovery.seeds import seed_sources
from pipeline.manifest_builder import build_story_manifest
from pipeline.models import ContentRole, EpisodeStatus, RightsTier
from pipeline.research.extract import build_research_pack
from pipeline.scripts.generation import approve_script, save_manual_script
from pipeline.storage import PROJECT_ROOT, story_manifest_path
from pipeline.timeline.planner import approve_timeline, generate_timeline
from pipeline.visuals.providers import approve_visual, stage_local_visual


def ensure_demo_project(repository):
    projects = repository.list_projects()
    if projects:
        return projects[0]
    return repository.create_project(
        "SynthPost V2 Demo",
        default_category="technology",
        default_render_profile="preview",
    )


def create_demo_episode(*, render_profile: str = "preview") -> tuple[str, str]:
    repository = get_repository()
    try:
        seed_sources(repository)
        project = ensure_demo_project(repository)
        episode = repository.create_episode(
            project.project_id, "Local V2 vertical slice", render_profile=render_profile
        )
        body = (
            "SynthPost Studio is being rebuilt as a local-first newsroom production editor. "
            "The retained renderer can consume an approved timeline, stage visual media, and render a story through Remotion. "
            "The new application stores projects, episodes, sources, scripts, visuals, timelines, jobs, and artifacts in SQLite. "
            "Human approval remains required before final rendering, especially for visual rights and generated scripts."
        )
        candidate = add_manual_story(
            repository,
            title="SynthPost Studio V2 rebuild reaches manual vertical slice",
            body=body,
            category="technology",
            episode_id=episode.episode_id,
        )
        selected = repository.select_candidate(
            candidate.candidate_id, episode.episode_id
        )
        story_id = selected.story_id or candidate.candidate_id
        build_research_pack(repository, story_id)
        script = save_manual_script(
            repository,
            story_id,
            "SynthPost Studio V2 rebuild reaches manual vertical slice",
            """
SynthPost Studio now starts from a clean rendering shell instead of the old automated newsroom pipeline.

The first vertical slice is deliberately editorial: create an episode, select a story, review a script, approve visuals, build a timeline, and only then render.

The system keeps the retained Remotion templates, avatar integration boundary, render profiles, provenance helpers, and ffmpeg episode assembly.

This demo uses local editor-approved media from the retained renderer assets, while the production workflow blocks unsafe rights states before rendering.
""".strip(),
            category="technology",
        )
        approve_script(repository, story_id)
        visual_path = (
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
            visual_path,
            title="Datacenter racks retained renderer image",
            content_role=ContentRole.context,
            section_ids=[
                script.sections[1].section_id
                if len(script.sections) > 1
                else script.sections[0].section_id
            ],
            rights_tier=RightsTier.green,
            usage_basis="repo_editor_approved_demo_asset",
        )
        approve_visual(
            repository,
            visual.asset_id,
            manual=False,
            attribution_text="Source: SynthPost retained renderer demo asset",
        )
        generate_timeline(repository, story_id)
        approve_timeline(repository, story_id)
        build_story_manifest(
            repository, story_id, render_profile=render_profile, test_mode=False
        )
        return episode.episode_id, story_id
    finally:
        repository.close()


def render_story_only(
    episode_id: str,
    story_id: str,
    *,
    render_profile: str,
    force: bool,
    test_mode: bool,
    skip_avatar_render: bool,
) -> Path:
    from pipeline.run_story import run_story

    manifest_path = story_manifest_path(episode_id, story_id)
    previous = os.environ.get("SYNTHPOST_ALLOW_PLACEHOLDER_ANCHOR")
    if skip_avatar_render:
        os.environ["SYNTHPOST_ALLOW_PLACEHOLDER_ANCHOR"] = "1"
    try:
        run_story(
            manifest_path,
            force_avatar=force,
            force_composite=force,
            skip_avatar_render=skip_avatar_render,
            test_mode=test_mode,
            render_profile=render_profile,
        )
    finally:
        if previous is None:
            os.environ.pop("SYNTHPOST_ALLOW_PLACEHOLDER_ANCHOR", None)
        else:
            os.environ["SYNTHPOST_ALLOW_PLACEHOLDER_ANCHOR"] = previous
    return manifest_path


def run_episode(
    episode_id: str,
    *,
    render_profile: str = "preview",
    force: bool = False,
    test_mode: bool = False,
    skip_avatar_render: bool = True,
) -> Path:
    repository = get_repository()
    try:
        episode = repository.get_episode(episode_id)
        for story_id in episode.story_ids:
            build_story_manifest(
                repository, story_id, render_profile=render_profile, test_mode=test_mode
            )
            render_story_only(
                episode_id,
                story_id,
                render_profile=render_profile,
                force=force,
                test_mode=test_mode,
                skip_avatar_render=skip_avatar_render,
            )
        final = stitch_episode(
            episode_id, force=force, test_mode=test_mode, render_profile=render_profile
        )
        episode.final_output_path = str(final.relative_to(PROJECT_ROOT))
        episode.status = EpisodeStatus.completed
        repository.upsert_episode(episode)
        return final
    finally:
        repository.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="High-level SynthPost V2 episode orchestration."
    )
    parser.add_argument(
        "episode_id",
        nargs="?",
        help="Episode ID to render. Use --create-demo to create one first.",
    )
    parser.add_argument(
        "--create-demo",
        action="store_true",
        help="Create a deterministic local manual vertical-slice episode.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Create demo if needed, render story with placeholder anchor, and assemble TEST_MODE final.",
    )
    parser.add_argument(
        "--render-profile",
        choices=["preview", "production", "final_master"],
        default="preview",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--test-mode", action="store_true", default=False)
    parser.add_argument(
        "--with-avatar",
        action="store_true",
        help="Invoke real Avatar Engine instead of placeholder anchor path.",
    )
    args = parser.parse_args()

    episode_id = args.episode_id
    if args.create_demo or args.smoke or not episode_id:
        episode_id, story_id = create_demo_episode(render_profile=args.render_profile)
        print(f"[run_episode] Created demo episode={episode_id} story={story_id}")
    if args.smoke or episode_id:
        final = run_episode(
            episode_id,
            render_profile=args.render_profile,
            force=args.force,
            test_mode=args.test_mode or args.smoke,
            skip_avatar_render=not args.with_avatar,
        )
        print(f"[run_episode] Final episode: {final}")


if __name__ == "__main__":
    main()
