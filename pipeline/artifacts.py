from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.storage import episode_dir, project_relative, story_dir, write_manifest


def episode_manifest_path(episode_id: str) -> Path:
    return episode_dir(episode_id) / "episode.json"


def story_manifest_path(episode_id: str, story_id: str) -> Path:
    return story_dir(episode_id, story_id) / "story.json"


def source_documents_path(episode_id: str, story_id: str) -> Path:
    return story_dir(episode_id, story_id) / "source_documents.json"


def research_pack_path(episode_id: str, story_id: str) -> Path:
    return story_dir(episode_id, story_id) / "research_pack.json"


def scripts_dir(episode_id: str, story_id: str) -> Path:
    return story_dir(episode_id, story_id) / "scripts"


def script_revision_path(episode_id: str, story_id: str, version: int) -> Path:
    return scripts_dir(episode_id, story_id) / f"script_v{version:03d}.json"


def timelines_dir(episode_id: str, story_id: str) -> Path:
    return story_dir(episode_id, story_id) / "timelines"


def timeline_revision_path(episode_id: str, story_id: str, version: int) -> Path:
    return timelines_dir(episode_id, story_id) / f"timeline_v{version:03d}.json"


def approved_timeline_path(episode_id: str, story_id: str) -> Path:
    return timelines_dir(episode_id, story_id) / "approved_timeline.json"


def visuals_candidates_path(episode_id: str, story_id: str) -> Path:
    return story_dir(episode_id, story_id) / "visuals" / "candidates.json"


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    temp.replace(path)
    return path


def materialize_story_artifacts(repository, story_id: str) -> dict[str, str]:
    episode = repository.episode_for_story(story_id)
    paths: dict[str, str] = {}
    write_json(
        episode_manifest_path(episode.episode_id), episode.model_dump(mode="json")
    )
    paths["episode"] = project_relative(episode_manifest_path(episode.episode_id))
    docs = repository.list_source_documents(story_id)
    if docs:
        write_json(source_documents_path(episode.episode_id, story_id), docs)
        paths["source_documents"] = project_relative(
            source_documents_path(episode.episode_id, story_id)
        )
    pack = repository.latest_research_pack(story_id)
    if pack:
        write_json(research_pack_path(episode.episode_id, story_id), pack)
        paths["research_pack"] = project_relative(
            research_pack_path(episode.episode_id, story_id)
        )
    script = repository.latest_script(story_id)
    if script:
        write_json(
            script_revision_path(episode.episode_id, story_id, script.version),
            script.model_dump(mode="json"),
        )
        paths["script"] = project_relative(
            script_revision_path(episode.episode_id, story_id, script.version)
        )
    visuals = [
        visual.model_dump(mode="json") for visual in repository.list_visuals(story_id)
    ]
    if visuals:
        write_json(visuals_candidates_path(episode.episode_id, story_id), visuals)
        paths["visual_candidates"] = project_relative(
            visuals_candidates_path(episode.episode_id, story_id)
        )
    timeline = repository.latest_timeline(story_id)
    if timeline:
        write_json(
            timeline_revision_path(episode.episode_id, story_id, timeline.version),
            timeline.model_dump(mode="json"),
        )
        paths["timeline"] = project_relative(
            timeline_revision_path(episode.episode_id, story_id, timeline.version)
        )
        if (
            timeline.status == "approved"
            or getattr(timeline.status, "value", None) == "approved"
        ):
            write_json(
                approved_timeline_path(episode.episode_id, story_id),
                timeline.model_dump(mode="json"),
            )
            paths["approved_timeline"] = project_relative(
                approved_timeline_path(episode.episode_id, story_id)
            )
    return paths
