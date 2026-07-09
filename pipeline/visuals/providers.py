from __future__ import annotations

import html
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


def _wrap_svg_text(text: str, *, max_chars: int = 48, max_lines: int = 4) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines


def _visual_card_svg(*, section_label: str, headline: str, summary: str) -> str:
    headline_lines = _wrap_svg_text(headline.upper(), max_chars=36, max_lines=3)
    summary_lines = _wrap_svg_text(summary, max_chars=62, max_lines=5)
    headline_tspans = "".join(
        f'<tspan x="132" dy="{0 if index == 0 else 72}">{html.escape(line)}</tspan>'
        for index, line in enumerate(headline_lines)
    )
    summary_tspans = "".join(
        f'<tspan x="132" dy="{0 if index == 0 else 42}">{html.escape(line)}</tspan>'
        for index, line in enumerate(summary_lines)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">
  <rect width="1920" height="1080" fill="#050A14"/>
  <rect x="96" y="96" width="1728" height="888" rx="28" fill="#08111F" stroke="#17385F" stroke-width="2"/>
  <rect x="96" y="96" width="18" height="888" fill="#D92D27"/>
  <circle cx="1700" cy="214" r="88" fill="#0E2A4A" opacity="0.75"/>
  <circle cx="1748" cy="164" r="42" fill="#1E70FF" opacity="0.75"/>
  <text x="132" y="184" fill="#8FA7C6" font-family="Arial, Helvetica, sans-serif" font-size="34" letter-spacing="8">SYNTHPOST</text>
  <text x="132" y="268" fill="#FFFFFF" font-family="Georgia, 'Times New Roman', serif" font-size="72" font-weight="700">{headline_tspans}</text>
  <text x="132" y="602" fill="#C8D3E3" font-family="Arial, Helvetica, sans-serif" font-size="36">{summary_tspans}</text>
  <rect x="132" y="860" width="520" height="4" fill="#1E70FF"/>
  <text x="132" y="930" fill="#7F93AD" font-family="Arial, Helvetica, sans-serif" font-size="30" letter-spacing="3">{html.escape(section_label.upper())}</text>
  <text x="1668" y="930" text-anchor="end" fill="#415A78" font-family="Arial, Helvetica, sans-serif" font-size="26">LOCAL GENERATED VISUAL</text>
</svg>"""


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
    # When no explicit section_ids are provided, try to auto-assign from the
    # approved script so the timeline planner can map this visual to segments.
    effective_section_ids = section_ids or []
    if not effective_section_ids:
        try:
            script = repository.latest_script(story_id, approved=True)
            if script and script.sections:
                effective_section_ids = [s.section_id for s in script.sections]
        except Exception:
            pass
    visual = VisualCandidate(
        story_id=story_id,
        section_ids=effective_section_ids,
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


def _advance_to_visuals_review(repository, story_id: str) -> None:
    candidate = repository.candidate_for_story(story_id)
    try:
        if candidate.workflow_state == StoryWorkflowState.script_approved:
            repository.transition_story(story_id, StoryWorkflowState.visuals_searching)
            repository.transition_story(story_id, StoryWorkflowState.visuals_review)
        elif candidate.workflow_state == StoryWorkflowState.visuals_searching:
            repository.transition_story(story_id, StoryWorkflowState.visuals_review)
    except Exception:
        pass


def generate_script_visual_cards(repository, story_id: str) -> list[VisualCandidate]:
    if not config.env_bool("SYNTHPOST_GENERATE_FALLBACK_VISUALS", True):
        return []
    existing = [
        visual
        for visual in repository.list_visuals(story_id)
        if visual.provider == "generated_visual_card"
    ]
    if existing:
        return existing

    script = repository.latest_script(
        story_id, approved=True
    ) or repository.latest_script(story_id)
    if not script:
        return []

    episode = repository.episode_for_story(story_id)
    media_root = visual_media_dir(episode.episode_id, story_id)
    media_root.mkdir(parents=True, exist_ok=True)
    visuals: list[VisualCandidate] = []
    for index, section in enumerate(script.sections, start=1):
        if not section.text.strip():
            continue
        file_name = f"generated_{index:02d}_{section.section_type}.svg"
        path = media_root / file_name
        path.write_text(
            _visual_card_svg(
                section_label=section.section_type.replace("_", " "),
                headline=script.headline,
                summary=section.text.strip(),
            )
        )
        visual = VisualCandidate(
            story_id=story_id,
            section_ids=[section.section_id],
            provider="generated_visual_card",
            source_url=project_relative(path),
            source_domain="synthpost.local",
            download_path=project_relative(path),
            thumbnail_path=project_relative(path),
            media_type=MediaType.image,
            mime_type="image/svg+xml",
            width=1920,
            height=1080,
            title=f"{section.section_type.replace('_', ' ').title()} Visual Card",
            description="Automatically generated SynthPost editorial card for this script section.",
            creator="SynthPost Studio",
            relevance_score=0.55,
            visual_quality_score=0.55,
            source_authority=1.0,
            content_role=ContentRole.context,
            rights_tier=RightsTier.green,
            rights_confidence=1.0,
            usage_basis="synthpost_generated_editorial_graphic",
            license="generated_by_synthpost_local_project",
            attribution_required=False,
            attribution_text="SynthPost generated visual",
            manual_review_flag=False,
            review_status=ReviewStatus.approved,
            warnings=[],
            motion={"preset": "slow_push", "intensity": 0.16},
        )
        repository.upsert_visual(visual)
        visuals.append(visual)
    return visuals


def search_local_drop_folder(
    repository, story_id: str, *, section_ids: list[str] | None = None
) -> list[VisualCandidate]:
    drop = resolve_project_path(
        os.environ.get("SYNTHPOST_MEDIA_DROP_DIR", "media_drop")
    )
    visuals: list[VisualCandidate] = []
    if drop.exists():
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
    if not visuals:
        visuals = generate_script_visual_cards(repository, story_id)
    _advance_to_visuals_review(repository, story_id)
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
