from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from .content_writing import ollama as content_writing
from .direction import avatar
from .news_points import default as news_points
from .visuals import default as visuals
from .compositor import render_story
from . import thumbnails
from .storage import read_manifest


def run_story(
    story_json_path: str | Path,
    *,
    force_avatar: bool = False,
    force_visuals: bool = False,
    force_composite: bool = False,
    skip_avatar_render: bool = False,
    test_mode: bool = False,
    assemble: bool = False,
    thumbnail: bool = False,
    force_thumbnail: bool = False,
    auto_select_thumbnail: bool = False,
) -> None:
    content_writing.run(story_json_path)
    news_points.run(story_json_path)
    visuals.run(story_json_path, force=force_visuals)
    manifest = read_manifest(story_json_path)
    template_name = manifest.get("composition", {}).get("template")
    if avatar.template_requires_avatar(template_name):
        avatar.run(story_json_path, force=force_avatar, render=not skip_avatar_render, test_mode=test_mode)
    else:
        print(f"[direction] Skipping Avatar-Engine for visual-only template: {template_name}")
    render_story(story_json_path, force=force_composite)
    if thumbnail:
        thumbnails.run(story_json_path, force=force_thumbnail, manual_review=not auto_select_thumbnail)

    if assemble:
        manifest = read_manifest(story_json_path)
        subprocess.run(["python3", "assembly/stitch_episode.py", str(manifest["episode_id"])], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one SynthPost story through Milestone 2 stages.")
    parser.add_argument("story_json", type=Path)
    parser.add_argument("--force-avatar", action="store_true")
    parser.add_argument("--force-visuals", action="store_true")
    parser.add_argument("--force-composite", action="store_true")
    parser.add_argument("--skip-avatar-render", action="store_true", help="Use an existing direction.anchor_output_path.")
    parser.add_argument("--test-mode", action="store_true", help="Forward Avatar-Engine test mode when rendering.")
    parser.add_argument("--assemble", action="store_true", help="Run episode assembly after story compositing.")
    parser.add_argument("--thumbnail", action="store_true", help="Generate episode thumbnail candidates from this story.")
    parser.add_argument("--force-thumbnail", action="store_true", help="Regenerate thumbnail candidates even if a best thumbnail exists.")
    parser.add_argument("--auto-select-thumbnail", action="store_true", help="Automatically copy the top-scored thumbnail to thumbnail_best.png.")
    args = parser.parse_args()
    run_story(
        args.story_json,
        force_avatar=args.force_avatar,
        force_visuals=args.force_visuals,
        force_composite=args.force_composite,
        skip_avatar_render=args.skip_avatar_render,
        test_mode=args.test_mode,
        assemble=args.assemble,
        thumbnail=args.thumbnail,
        force_thumbnail=args.force_thumbnail,
        auto_select_thumbnail=args.auto_select_thumbnail,
    )


if __name__ == "__main__":
    main()
