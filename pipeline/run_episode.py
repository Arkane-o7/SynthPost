from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from . import evidence
from .news_collection.candidates import CandidateStory, write_story_candidates
from .news_collection.ranking import rank_candidates, selected_candidates
from .news_collection import rss
from .provenance import now_iso, read_episode_manifest, write_episode_manifest
from .render_profiles import apply_manifest_runtime, resolve_profile
from .run_story import run_story
from .storage import PROJECT_ROOT, project_relative, story_manifest_path, write_manifest


def create_story_manifest(
    episode_id: str,
    story_id: str,
    candidate: CandidateStory,
    *,
    render_profile: str = "production",
    test_mode: bool = False,
    candidate_audit_path: str | Path | None = None,
) -> Path:
    path = story_manifest_path(episode_id, story_id)
    profile = resolve_profile(render_profile)
    raw = candidate.to_raw()
    if candidate_audit_path:
        audit_path = project_relative(candidate_audit_path)
        raw["story_candidates_path"] = audit_path
        if isinstance(raw.get("editorial"), dict):
            raw["editorial"]["story_candidates_path"] = audit_path
        if isinstance(raw.get("selected_candidate"), dict):
            raw["selected_candidate"]["story_candidates_path"] = audit_path
        handoff = raw.get("handoff")
        if isinstance(handoff, dict):
            for value in handoff.values():
                if isinstance(value, dict):
                    value["story_candidates_path"] = audit_path
    manifest = {
        "story_id": story_id,
        "episode_id": episode_id,
        "raw": raw,
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


def _candidate_selection_record(
    candidate: CandidateStory,
    *,
    story_path: Path | None = None,
) -> dict[str, object]:
    record = {
        "candidate_id": candidate.candidate_id,
        "headline": candidate.headline,
        "source": candidate.source_name,
        "source_name": candidate.source_name,
        "source_url": candidate.source_url,
        "source_domain": candidate.source_domain,
        "source_provider": candidate.source_provider,
        "source_type": candidate.source_type,
        "source_category": candidate.source_category,
        "published_at": candidate.published_at,
        "category": candidate.category,
        "normalized_category": candidate.category,
        "final_editorial_score": float(candidate.final_editorial_score),
        "score_reasons": dict(candidate.score_reasons),
        "selection_status": candidate.selection_status,
        "selection_reason": candidate.selection_reason,
        "rejection_reasons": list(candidate.rejection_reasons),
        "why_it_matters": candidate.why_it_matters,
        "synthpost_angle": candidate.possible_synthpost_angle,
        "thumbnail_hook": candidate.possible_thumbnail_hook,
        "visual_opportunities": list(candidate.visual_opportunities),
        "entities": list(candidate.key_entities),
    }
    if story_path:
        record["story_json_path"] = project_relative(story_path)
    return {key: value for key, value in record.items() if value not in (None, "", [], {})}


def record_editorial_selection_manifest(
    *,
    episode_id: str,
    ranked_candidates: list[CandidateStory],
    chosen_candidates: list[CandidateStory],
    candidates_path: Path,
    story_paths: list[Path],
    render_profile: str,
    test_mode: bool,
) -> Path:
    story_path_by_candidate_id = {
        candidate.candidate_id: story_paths[index]
        for index, candidate in enumerate(chosen_candidates[: len(story_paths)])
    }
    rejected_candidates = [candidate for candidate in ranked_candidates if candidate.selection_status == "rejected"]
    manifest = read_episode_manifest(episode_id)
    manifest["episode_id"] = episode_id
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    runtime.update(
        {
            "render_profile": render_profile,
            "test_mode": bool(test_mode),
            "mode": "TEST_MODE" if test_mode else "production",
        }
    )
    manifest["runtime"] = runtime
    manifest["editorial_selection"] = {
        "updated_at": now_iso(),
        "story_candidates_path": project_relative(candidates_path),
        "candidate_count": len(ranked_candidates),
        "selected_count": len(chosen_candidates),
        "rejected_count": len(rejected_candidates),
        "ranked_candidate_ids": [candidate.candidate_id for candidate in ranked_candidates],
        "selected_candidates": [
            _candidate_selection_record(
                candidate,
                story_path=story_path_by_candidate_id.get(candidate.candidate_id),
            )
            for candidate in chosen_candidates
        ],
        "rejected_candidates": [
            _candidate_selection_record(candidate)
            for candidate in rejected_candidates[:10]
        ],
    }
    return write_episode_manifest(episode_id, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and render a SynthPost episode.")
    parser.add_argument("--episode-id", default=f"ep_{datetime.now(timezone.utc).date().isoformat()}")
    parser.add_argument("--stories", type=int, default=1)
    parser.add_argument("--candidate-limit", type=int, default=12, help="Number of normalized story candidates to collect and audit.")
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

    candidate_limit = max(args.stories, args.candidate_limit)
    collected_candidates = rss.collect(limit=candidate_limit)
    if not collected_candidates:
        raise SystemExit("No RSS stories were collected. Check SYNTHPOST_RSS_FEEDS.")
    ranked_candidates = rank_candidates(collected_candidates, select_count=args.stories)
    chosen_candidates = selected_candidates(ranked_candidates)
    if len(chosen_candidates) < args.stories:
        rejected_count = sum(1 for candidate in ranked_candidates if candidate.selection_status == "rejected")
        raise SystemExit(
            f"Only {len(chosen_candidates)} acceptable stories were found after editorial ranking "
            f"({rejected_count} rejected). Increase --candidate-limit or adjust sources."
        )
    candidates_path = write_story_candidates(args.episode_id, ranked_candidates)

    story_paths = [
        create_story_manifest(
            args.episode_id,
            f"story_{index:03d}",
            candidate,
            render_profile=profile.name,
            test_mode=args.test_mode,
            candidate_audit_path=candidates_path,
        )
        for index, candidate in enumerate(chosen_candidates[: args.stories], start=1)
    ]
    episode_manifest_path = record_editorial_selection_manifest(
        episode_id=args.episode_id,
        ranked_candidates=ranked_candidates,
        chosen_candidates=chosen_candidates[: args.stories],
        candidates_path=candidates_path,
        story_paths=story_paths,
        render_profile=profile.name,
        test_mode=args.test_mode,
    )
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
    print(
        json.dumps(
            {
                "episode_id": args.episode_id,
                "story_candidates": str(candidates_path),
                "episode_manifest": str(episode_manifest_path),
                "stories": [str(path) for path in story_paths],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
