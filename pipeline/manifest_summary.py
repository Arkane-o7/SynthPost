from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .provenance import ffprobe_summary, read_episode_manifest
from .storage import PROJECT_ROOT, episode_dir, read_manifest, resolve_project_path


def story_paths_for_episode(episode: Path) -> list[Path]:
    return sorted((episode / "stories").glob("*/story.json"))


def _artifact_status(record: dict[str, Any] | None) -> str:
    if not record:
        return "unknown"
    if record.get("skipped"):
        return "skipped"
    if record.get("reused"):
        return "reused"
    if record.get("fresh"):
        return "fresh"
    return "unknown"


def _final_artifact(episode_id: str, episode: Path, episode_manifest: dict[str, Any]) -> dict[str, Any]:
    provenance = episode_manifest.get("provenance") if isinstance(episode_manifest.get("provenance"), dict) else {}
    artifacts = provenance.get("artifacts") if isinstance(provenance.get("artifacts"), dict) else {}
    final = artifacts.get("final_video") if isinstance(artifacts.get("final_video"), dict) else {}
    if final.get("path"):
        return final
    for candidate in [episode / "final.mp4", episode / "final_TEST_MODE.mp4"]:
        if candidate.exists():
            return {"path": candidate.relative_to(PROJECT_ROOT).as_posix(), "media": ffprobe_summary(candidate)}
    return {}


def _selected_candidate_summary(raw: dict[str, Any], episode_manifest: dict[str, Any]) -> dict[str, Any]:
    selected = raw.get("selected_candidate") if isinstance(raw.get("selected_candidate"), dict) else {}
    editorial = raw.get("editorial") if isinstance(raw.get("editorial"), dict) else {}
    scores = editorial.get("scores") if isinstance(editorial.get("scores"), dict) else {}
    episode_selection = (
        episode_manifest.get("editorial_selection")
        if isinstance(episode_manifest.get("editorial_selection"), dict)
        else {}
    )
    episode_selected = episode_selection.get("selected_candidates") if isinstance(episode_selection.get("selected_candidates"), list) else []
    first_episode_selected = episode_selected[0] if episode_selected and isinstance(episode_selected[0], dict) else {}
    return {
        "candidate_id": selected.get("candidate_id") or editorial.get("candidate_id") or first_episode_selected.get("candidate_id"),
        "headline": selected.get("headline") or raw.get("headline_source") or first_episode_selected.get("headline"),
        "source": selected.get("source") or selected.get("source_name") or raw.get("source_name") or first_episode_selected.get("source"),
        "source_url": selected.get("source_url") or raw.get("source_url") or first_episode_selected.get("source_url"),
        "source_domain": selected.get("source_domain") or raw.get("source_domain") or first_episode_selected.get("source_domain"),
        "category": selected.get("normalized_category") or selected.get("category") or raw.get("category") or first_episode_selected.get("category"),
        "final_editorial_score": selected.get("final_editorial_score")
        or scores.get("final_editorial_score")
        or first_episode_selected.get("final_editorial_score"),
        "selection_reason": selected.get("selection_reason") or editorial.get("selection_reason") or first_episode_selected.get("selection_reason"),
        "story_candidates_path": raw.get("story_candidates_path") or episode_selection.get("story_candidates_path"),
    }


def summarize_episode(path_or_episode_id: str | Path) -> dict[str, Any]:
    value = Path(path_or_episode_id)
    episode = value if value.is_absolute() or value.exists() else episode_dir(str(path_or_episode_id))
    episode = resolve_project_path(episode)
    episode_id = episode.name
    paths = story_paths_for_episode(episode)
    stories = [read_manifest(path) for path in paths]
    first = stories[0] if stories else {}
    raw = first.get("raw") if isinstance(first.get("raw"), dict) else {}
    script = first.get("script") if isinstance(first.get("script"), dict) else {}
    direction = first.get("direction") if isinstance(first.get("direction"), dict) else {}
    thumbnail = first.get("thumbnail") if isinstance(first.get("thumbnail"), dict) else {}
    visual_bridge = first.get("visual_compositor_bridge") if isinstance(first.get("visual_compositor_bridge"), dict) else {}
    runtime = first.get("runtime") if isinstance(first.get("runtime"), dict) else {}
    provenance = first.get("provenance") if isinstance(first.get("provenance"), dict) else {}
    artifacts = provenance.get("artifacts") if isinstance(provenance.get("artifacts"), dict) else {}
    episode_manifest = read_episode_manifest(episode_id)
    final = _final_artifact(episode_id, episode, episode_manifest)
    final_media = final.get("media") if isinstance(final.get("media"), dict) else ffprobe_summary(final.get("path", ""))
    selected_candidate = _selected_candidate_summary(raw, episode_manifest)

    warnings: list[str] = []
    if not stories:
        warnings.append("No story manifests found.")
    if not final.get("path"):
        warnings.append("Final video artifact missing.")
    if thumbnail and not thumbnail.get("best_path"):
        warnings.append("Thumbnail best_path missing.")
    if not artifacts.get("avatar_anchor"):
        warnings.append("Avatar artifact provenance missing.")
    if runtime.get("test_mode") or first.get("test_mode") or (final.get("test_mode") is True):
        warnings.append("TEST_MODE artifact: do not publish as production.")

    return {
        "episode_id": episode_id,
        "story_count": len(stories),
        "headline": script.get("headline") or raw.get("headline_source") or "unknown",
        "topic": script.get("category") or raw.get("category") or "unknown",
        "selected_candidate": selected_candidate,
        "llm": {
            "provider": script.get("llm_provider") or "unknown",
            "model": script.get("llm_model") or "unknown",
        },
        "tts": {
            "provider": (direction.get("voice") or {}).get("engine") if isinstance(direction.get("voice"), dict) else "unknown",
            "voice": (direction.get("voice") or {}).get("voice_id") if isinstance(direction.get("voice"), dict) else "unknown",
        },
        "render_profile": runtime.get("render_profile") or first.get("render_profile") or "unknown",
        "mode": "TEST_MODE" if runtime.get("test_mode") or first.get("test_mode") else "production",
        "avatar": {
            "status": _artifact_status(artifacts.get("avatar_anchor") if isinstance(artifacts.get("avatar_anchor"), dict) else None),
            "path": (artifacts.get("avatar_anchor") or {}).get("path") if isinstance(artifacts.get("avatar_anchor"), dict) else None,
        },
        "thumbnail": {
            "path": thumbnail.get("best_path"),
            "relevance_score": thumbnail.get("thumbnail_relevance_score"),
        },
        "visuals": {
            "input_source": visual_bridge.get("input_source") or "unknown",
            "selected_count": visual_bridge.get("selected_visual_count"),
            "fallback_count": visual_bridge.get("fallback_count"),
            "manual_review_warning_count": visual_bridge.get("manual_review_warning_count"),
            "unsafe_visual_warning_count": visual_bridge.get("unsafe_visual_warning_count"),
            "rights_categories_used": visual_bridge.get("rights_categories_used") or [],
            "attribution_complete": (visual_bridge.get("attribution") or {}).get("complete")
            if isinstance(visual_bridge.get("attribution"), dict)
            else None,
            "visual_candidates_path": visual_bridge.get("visual_candidates_path"),
            "visual_plan_path": visual_bridge.get("visual_plan_path"),
            "visual_skills_path": visual_bridge.get("visual_skills_path"),
            "compositor_visuals_path": visual_bridge.get("compositor_visuals_path"),
        },
        "final_video": {
            "path": final.get("path"),
            "duration_seconds": final_media.get("duration_seconds") if isinstance(final_media, dict) else None,
            "resolution": (
                f"{final_media.get('width')}x{final_media.get('height')}"
                if isinstance(final_media, dict) and final_media.get("width") and final_media.get("height")
                else None
            ),
        },
        "warnings": warnings,
    }


def print_summary(summary: dict[str, Any]) -> None:
    lines = [
        f"Episode: {summary['episode_id']}",
        f"Story count: {summary['story_count']}",
        f"Headline: {summary['headline']}",
        f"Topic/category: {summary['topic']}",
        f"Selected source: {summary['selected_candidate'].get('source') or 'unknown'}",
        f"Selected category: {summary['selected_candidate'].get('category') or 'unknown'}",
        f"Final editorial score: {summary['selected_candidate'].get('final_editorial_score') or 'unknown'}",
        f"Selection reason: {summary['selected_candidate'].get('selection_reason') or 'unknown'}",
        f"LLM: {summary['llm']['provider']} / {summary['llm']['model']}",
        f"TTS: {summary['tts']['provider']} / {summary['tts']['voice']}",
        f"Render profile: {summary['render_profile']}",
        f"Mode: {summary['mode']}",
        f"Avatar: {summary['avatar']['status']} ({summary['avatar'].get('path') or 'no path'})",
        f"Thumbnail: {summary['thumbnail'].get('path') or 'missing'}; relevance={summary['thumbnail'].get('relevance_score')}",
        (
            f"Visuals: source={summary['visuals'].get('input_source')}; "
            f"selected={summary['visuals'].get('selected_count')}; "
            f"fallbacks={summary['visuals'].get('fallback_count')}; "
            f"rights={','.join(summary['visuals'].get('rights_categories_used') or []) or 'unknown'}"
        ),
        (
            f"Final video: {summary['final_video'].get('path') or 'missing'}; "
            f"duration={summary['final_video'].get('duration_seconds')}; "
            f"resolution={summary['final_video'].get('resolution')}"
        ),
    ]
    warnings = summary.get("warnings") or []
    if warnings:
        lines.append("Warnings/problems:")
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("Warnings/problems: none")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a SynthPost episode manifest summary.")
    parser.add_argument("episode", help="Episode id or path, e.g. episodes/ep_2026-06-24")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    summary = summarize_episode(args.episode)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=True))
    else:
        print_summary(summary)


if __name__ == "__main__":
    main()
