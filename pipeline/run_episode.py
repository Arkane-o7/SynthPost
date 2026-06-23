from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from . import evidence
from .news_collection import rss
from .render_profiles import apply_manifest_runtime, resolve_profile
from .run_story import run_story
from .storage import PROJECT_ROOT, story_manifest_path, write_manifest


def create_story_manifest(
    episode_id: str,
    story_id: str,
    candidate: rss.CandidateStory,
    *,
    render_profile: str = "production",
    test_mode: bool = False,
) -> Path:
    path = story_manifest_path(episode_id, story_id)
    profile = resolve_profile(render_profile)
    manifest = {
        "story_id": story_id,
        "episode_id": episode_id,
        "raw": {
            "headline_source": candidate.headline_source,
            "summary": candidate.summary,
            "source_url": candidate.source_url,
            "source_name": candidate.source_name,
            "category": candidate.category,
            "published_at": candidate.published_at,
            "facts": candidate.facts,
        },
        "script": {},
        "direction": {
            "job_id": story_id,
            "voice": {},
            "camera_cuts": [],
            "performance_beats": [],
            "anchor_output_path": f"episodes/{episode_id}/stories/{story_id}/anchor.mp4",
        },
        "visuals": [],
        "points": [],
        "composition": {
            "template": "split_main",
            "output_path": f"episodes/{episode_id}/stories/{story_id}/composited.mp4",
        },
    }
    apply_manifest_runtime(manifest, render_profile=profile, test_mode=test_mode)
    write_manifest(path, evidence.normalize_manifest(manifest))
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and render a SynthPost episode.")
    parser.add_argument("--episode-id", default=f"ep_{datetime.utcnow().date().isoformat()}")
    parser.add_argument("--stories", type=int, default=1)
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument(
        "--render-profile",
        choices=["preview", "production", "final_master"],
        default="production",
        help="Render quality profile to record and apply where supported.",
    )
    parser.add_argument("--skip-avatar-render", action="store_true")
    parser.add_argument("--thumbnail", action="store_true", help="Generate thumbnail candidates for each rendered story.")
    parser.add_argument("--force-thumbnail", action="store_true", help="Regenerate thumbnail candidates even if a best thumbnail exists.")
    parser.add_argument("--auto-select-thumbnail", action="store_true", help="Automatically copy the top-scored thumbnail to thumbnail_best.png.")
    args = parser.parse_args()
    profile = resolve_profile(args.render_profile)
    if args.test_mode:
        print("[TEST_MODE] WARNING: This run will be labeled TEST_MODE and must not be treated as production output.")

    candidates = rss.collect(limit=args.stories)
    if not candidates:
        raise SystemExit("No RSS stories were collected. Check SYNTHPOST_RSS_FEEDS.")

    story_paths = [
        create_story_manifest(
            args.episode_id,
            f"story_{index:03d}",
            candidate,
            render_profile=profile.name,
            test_mode=args.test_mode,
        )
        for index, candidate in enumerate(candidates, start=1)
    ]
    for path in story_paths:
        run_story(
            path,
            test_mode=args.test_mode,
            skip_avatar_render=args.skip_avatar_render,
            thumbnail=args.thumbnail,
            force_thumbnail=args.force_thumbnail,
            auto_select_thumbnail=args.auto_select_thumbnail,
            render_profile=profile.name,
        )

    import subprocess

    command = ["python3", "assembly/stitch_episode.py", args.episode_id, "--render-profile", profile.name]
    if args.test_mode:
        command.append("--test-mode")
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    print(json.dumps({"episode_id": args.episode_id, "stories": [str(path) for path in story_paths]}, indent=2))


if __name__ == "__main__":
    main()
