from __future__ import annotations

import mimetypes
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from pipeline import config
from pipeline.models import (
    ContentRole,
    MediaType,
    ReviewStatus,
    RightsTier,
    StoryWorkflowState,
    VisualCandidate,
)
from pipeline.provenance import ffprobe_summary
from pipeline.storage import (
    PROJECT_ROOT,
    project_relative,
    resolve_project_path,
    story_dir,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
DOCUMENT_EXTENSIONS = {".pdf"}


def media_type_for(path: Path) -> MediaType:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return MediaType.video
    if ext in DOCUMENT_EXTENSIONS:
        return MediaType.document
    return MediaType.image


def media_metadata(path: Path) -> dict:
    data = ffprobe_summary(path)
    if data:
        return data
    return {}


def visual_media_dir(episode_id: str, story_id: str) -> Path:
    return story_dir(episode_id, story_id) / "visuals" / "media"


def visual_thumbnail_dir(episode_id: str, story_id: str) -> Path:
    return story_dir(episode_id, story_id) / "visuals" / "thumbnails"


def safe_filename(name: str) -> str:
    stem = Path(name).stem.replace(" ", "_")[:80] or "visual"
    suffix = Path(name).suffix.lower() or ".bin"
    clean = "".join(char for char in stem if char.isalnum() or char in {"_", "-", "."})
    return f"{clean}{suffix}"


def create_thumbnail(path: Path, destination: Path) -> Path | None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        thumb = destination.with_suffix(
            path.suffix.lower() if path.suffix.lower() != ".svg" else ".svg"
        )
        if not thumb.exists():
            shutil.copy2(path, thumb)
        return thumb
    if ext in VIDEO_EXTENSIONS:
        thumb = destination.with_suffix(".jpg")
        command = [
            config.ffmpeg_binary(),
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(thumb),
        ]
        try:
            subprocess.run(command, check=True)
            return thumb
        except Exception:
            return None
    return None


def stage_local_visual(
    repository,
    story_id: str,
    source_path: str | Path,
    *,
    title: str | None = None,
    content_role: ContentRole = ContentRole.context,
    section_ids: list[str] | None = None,
    rights_tier: RightsTier = RightsTier.yellow,
    usage_basis: str = "user_provided_local_media",
) -> VisualCandidate:
    source = resolve_project_path(source_path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Local visual not found: {source}")
    episode = repository.episode_for_story(story_id)
    media_root = visual_media_dir(episode.episode_id, story_id)
    media_root.mkdir(parents=True, exist_ok=True)
    destination = media_root / safe_filename(source.name)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    metadata = media_metadata(destination)
    media_type = media_type_for(destination)
    thumbnail = create_thumbnail(
        destination,
        visual_thumbnail_dir(episode.episode_id, story_id) / destination.stem,
    )
    visual = VisualCandidate(
        story_id=story_id,
        section_ids=section_ids or [],
        provider="local_upload",
        source_url=source.as_posix(),
        source_domain="local",
        download_path=project_relative(destination),
        thumbnail_path=project_relative(thumbnail) if thumbnail else None,
        media_type=media_type,
        mime_type=mimetypes.guess_type(destination.name)[0],
        width=metadata.get("width"),
        height=metadata.get("height"),
        duration_seconds=metadata.get("duration_seconds"),
        title=title or source.stem.replace("_", " ").title(),
        description="User-provided local media staged for editorial review.",
        creator="user_provided",
        relevance_score=0.7,
        visual_quality_score=0.65,
        source_authority=0.6,
        content_role=content_role,
        rights_tier=rights_tier,
        rights_confidence=0.55 if rights_tier == RightsTier.yellow else 0.8,
        usage_basis=usage_basis,
        license="user_provided_review_required"
        if rights_tier == RightsTier.yellow
        else "editor_asserted_safe",
        attribution_required=True,
        attribution_text=f"Source: user-provided ({source.name})",
        manual_review_flag=rights_tier != RightsTier.green,
        review_status=ReviewStatus.suggested,
        warnings=[
            "Local upload requires editor rights review before production rendering"
        ]
        if rights_tier == RightsTier.yellow
        else [],
        motion={"preset": "push_in", "intensity": 0.22},
    )
    repository.upsert_visual(visual)
    candidate = repository.candidate_for_story(story_id)
    if candidate.workflow_state == StoryWorkflowState.script_approved:
        try:
            repository.transition_story(story_id, StoryWorkflowState.visuals_searching)
            repository.transition_story(story_id, StoryWorkflowState.visuals_review)
        except Exception:
            pass
    return visual


def search_local_drop_folder(
    repository, story_id: str, *, section_ids: list[str] | None = None
) -> list[VisualCandidate]:
    drop = resolve_project_path(
        os.environ.get("SYNTHPOST_MEDIA_DROP_DIR", "media_drop")
    )
    if not drop.exists():
        return []
    visuals: list[VisualCandidate] = []
    for path in sorted(drop.iterdir()):
        if (
            not path.is_file()
            or path.suffix.lower()
            not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | DOCUMENT_EXTENSIONS
        ):
            continue
        visuals.append(
            stage_local_visual(
                repository,
                story_id,
                path,
                section_ids=section_ids,
                rights_tier=RightsTier.yellow,
                usage_basis="local_drop_folder",
            )
        )
    return visuals


def approve_visual(
    repository,
    asset_id: str,
    *,
    manual: bool = False,
    attribution_text: str | None = None,
) -> VisualCandidate:
    visual = repository.get_visual(asset_id)
    if visual.rights_tier == RightsTier.red:
        raise ValueError("red-tier assets cannot be approved")
    if visual.rights_tier == RightsTier.yellow and not manual:
        raise ValueError("yellow-tier assets require manual approval")
    visual.review_status = (
        ReviewStatus.manual_approved if manual else ReviewStatus.approved
    )
    if attribution_text is not None:
        visual.attribution_text = attribution_text
    repository.upsert_visual(visual)
    return visual


def reject_visual(
    repository, asset_id: str, *, blocked: bool = False
) -> VisualCandidate:
    visual = repository.get_visual(asset_id)
    visual.review_status = ReviewStatus.blocked if blocked else ReviewStatus.rejected
    repository.upsert_visual(visual)
    return visual


def update_visual(repository, asset_id: str, patch: dict) -> VisualCandidate:
    visual = repository.get_visual(asset_id)
    data = visual.model_dump(mode="json")
    data.update({key: value for key, value in patch.items() if value is not None})
    updated = VisualCandidate.model_validate(data)
    repository.upsert_visual(updated)
    return updated
