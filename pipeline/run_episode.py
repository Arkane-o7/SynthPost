from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .news_collection import rss
from .run_story import run_story
from .storage import PROJECT_ROOT, story_manifest_path, write_manifest


def create_story_manifest(episode_id: str, story_id: str, candidate: rss.CandidateStory) -> Path:
    path = story_manifest_path(episode_id, story_id)
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
    write_manifest(path, manifest)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and render a SynthPost episode.")
    parser.add_argument("--episode-id", default=f"ep_{datetime.utcnow().date().isoformat()}")
    parser.add_argument("--stories", type=int, default=1)
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--skip-avatar-render", action="store_true")
    parser.add_argument("--thumbnail", action="store_true", help="Generate thumbnail candidates for each rendered story.")
    parser.add_argument("--force-thumbnail", action="store_true", help="Regenerate thumbnail candidates even if a best thumbnail exists.")
    parser.add_argument("--auto-select-thumbnail", action="store_true", help="Automatically copy the top-scored thumbnail to thumbnail_best.png.")
    args = parser.parse_args()

    candidates = rss.collect(limit=args.stories)
    if not candidates:
        raise SystemExit("No RSS stories were collected. Check SYNTHPOST_RSS_FEEDS.")

    story_paths = [
        create_story_manifest(args.episode_id, f"story_{index:03d}", candidate)
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
        )

    import subprocess

    subprocess.run(["python3", "assembly/stitch_episode.py", args.episode_id], cwd=PROJECT_ROOT, check=True)
    print(json.dumps({"episode_id": args.episode_id, "stories": [str(path) for path in story_paths]}, indent=2))


if __name__ == "__main__":
    main()
