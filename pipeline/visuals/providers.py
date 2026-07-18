from __future__ import annotations

import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import socket
import shutil
import subprocess
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pipeline import config
from pipeline.agents.hermes import HermesClient
from pipeline.llm.providers import (
    StructuredGenerationError,
    configured_provider,
    structured_generate,
)
from pipeline.editorial.charter import CHARTER_VERSION, charter_prompt_context, show_format_for
from pipeline.models import (
    ContentRole,
    GenerationAudit,
    MediaType,
    ReviewStatus,
    RightsTier,
    ScriptStatus,
    StoryWorkflowState,
    VisualCandidate,
    now_iso,
)
from pipeline.provenance import ffprobe_summary
from pipeline.search.searxng_client import (
    SearXNGError,
    SearXNGResult,
    configured as searxng_configured,
    search as searxng_search,
)
from pipeline.storage import (
    episode_media_inbox_dir,
    project_relative,
    resolve_project_path,
    story_dir,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
DOCUMENT_EXTENSIONS = {".pdf"}
SUPPORTED_VISUAL_EXTENSIONS = frozenset(
    IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | DOCUMENT_EXTENSIONS
)
REMOTE_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
SPLIT_VISUAL_ASPECT_RATIO = 1300 / 860
FULLSCREEN_VISUAL_ASPECT_RATIO = 16 / 9


@dataclass(frozen=True)
class VisualQueryPlan:
    section_id: str | None
    image_query: str
    video_query: str
    video_priority: bool
    rationale: str


class VisualSource(Protocol):
    """Small extension boundary for visual candidate discovery sources."""

    name: str

    def available(self) -> bool: ...

    def search(
        self,
        repository,
        story_id: str,
        *,
        progress_callback: Callable[[float, str], None] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> list[VisualCandidate]: ...


def _assert_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("remote media URL must use http(s)")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
            )
        }
    except socket.gaierror as exc:
        raise ValueError(f"could not resolve remote media host: {parsed.hostname}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("remote media URL resolved to a private or local address")


class _PublicOnlyRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _assert_public_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _PageImageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.image_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "meta" or self.image_url:
            return
        values = {key.casefold(): value for key, value in attrs if value}
        marker = (values.get("property") or values.get("name") or "").casefold()
        if marker in {"og:image", "og:image:url", "twitter:image"}:
            self.image_url = values.get("content")


def _prefer_original_social_image_url(url: str) -> str:
    """Remove known social-preview resizing while retaining signed CDN params."""

    parsed = urlparse(url)
    if not (parsed.hostname or "").casefold().endswith("fbcdn.net"):
        return url
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "ctp"
    ]
    return urlunparse(parsed._replace(query=urlencode(query)))


def _resolve_page_image_url(url: str) -> str:
    """Resolve a public source page's Open Graph image for explicit acquisition."""

    _assert_public_http_url(url)
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml;q=0.9",
            "User-Agent": "Mozilla/5.0 SynthPostStudio/2.0 editorial image resolver",
        },
    )
    timeout = config.get_settings().visuals.download_timeout_seconds
    opener = build_opener(_PublicOnlyRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        final_url = response.geturl()
        _assert_public_http_url(final_url)
        if response.headers.get_content_type().casefold() not in {
            "text/html",
            "application/xhtml+xml",
        }:
            raise ValueError("visual source page did not return HTML metadata")
        parser = _PageImageMetadataParser()
        parser.feed(
            response.read(2 * 1024 * 1024).decode(
                response.headers.get_content_charset() or "utf-8",
                errors="replace",
            )
        )
    if not parser.image_url:
        raise ValueError("visual source page does not expose an Open Graph image")
    resolved = _prefer_original_social_image_url(
        urljoin(final_url, parser.image_url)
    )
    _assert_public_http_url(resolved)
    return resolved


def _image_suffix_from_bytes(data: bytes) -> str | None:
    """Return the actual raster format instead of trusting remote MIME labels."""

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _normalize_image_extension(path: Path) -> Path:
    """Rename a raster whose saved suffix disagrees with its actual payload."""

    if path.suffix.lower() not in IMAGE_EXTENSIONS or path.suffix.lower() == ".svg":
        return path
    with path.open("rb") as handle:
        detected_suffix = _image_suffix_from_bytes(handle.read(16))
    if not detected_suffix or detected_suffix == path.suffix.lower():
        return path
    corrected = path.with_suffix(detected_suffix)
    path.replace(corrected)
    return corrected


def _download_remote_image(url: str, destination_stem: Path) -> Path:
    _assert_public_http_url(url)
    request = Request(
        url,
        headers={
            "Accept": "image/jpeg,image/png,image/webp,image/gif;q=0.8",
            "User-Agent": "SynthPostStudio/2.0 local editorial tool",
        },
    )
    settings = config.get_settings().visuals
    timeout = settings.download_timeout_seconds
    max_bytes = settings.download_max_bytes
    opener = build_opener(_PublicOnlyRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        _assert_public_http_url(response.geturl())
        content_type = response.headers.get_content_type().lower()
        declared_suffix = REMOTE_IMAGE_TYPES.get(content_type)
        if not declared_suffix:
            raise ValueError(f"remote result is not a supported image ({content_type})")
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError("remote image exceeds SYNTHPOST_VISUAL_DOWNLOAD_MAX_BYTES")
        first_chunk = response.read(1024 * 256)
        detected_suffix = _image_suffix_from_bytes(first_chunk)
        if not detected_suffix:
            raise ValueError(
                f"remote result declared {content_type} but contained no supported image"
            )
        destination = destination_stem.with_suffix(detected_suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        total = len(first_chunk)
        if total > max_bytes:
            raise ValueError("remote image exceeds SYNTHPOST_VISUAL_DOWNLOAD_MAX_BYTES")
        with destination.open("wb") as handle:
            handle.write(first_chunk)
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise ValueError(
                        "remote image exceeds SYNTHPOST_VISUAL_DOWNLOAD_MAX_BYTES"
                    )
                handle.write(chunk)
    if destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("remote image was empty")
    return destination


def _download_remote_video(
    url: str,
    destination_stem: Path,
    *,
    allow_long_source: bool = False,
) -> Path:
    _assert_public_http_url(url)
    settings = config.get_settings().visuals
    binary = settings.yt_dlp_binary
    resolved_binary = shutil.which(binary)
    if not resolved_binary:
        raise ValueError("yt-dlp is not installed or SYNTHPOST_YT_DLP is invalid")
    destination_stem.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = settings.download_max_bytes
    max_duration = settings.video_max_duration_seconds
    clip_seconds = max(5, settings.video_clip_seconds)
    output_template = str(destination_stem) + ".%(ext)s"
    # A cancelled yt-dlp run can leave a plausible partial file behind. A
    # retry must not mistake stale output for the current attempt's result.
    for stale in destination_stem.parent.glob(destination_stem.name + ".*"):
        if stale.is_file() and stale.suffix.lower() in VIDEO_EXTENSIONS:
            stale.unlink(missing_ok=True)
    common_command = [
        resolved_binary,
        "--no-playlist",
        "--no-progress",
        "--socket-timeout",
        str(settings.searxng_socket_timeout_seconds),
        "--retries",
        "1",
        "--fragment-retries",
        "1",
        "--js-runtimes",
        "node",
        "--restrict-filenames",
        "--max-filesize",
        str(max_bytes),
    ]
    if not allow_long_source:
        common_command.extend(
            ["--match-filter", f"duration <= {max_duration}"]
        )
    common_command.extend([
        "--download-sections",
        f"*0-{clip_seconds}",
        "--force-keyframes-at-cuts",
        "--format-sort",
        "res:1080,ext:mp4:m4a",
        "--merge-output-format",
        "mp4",
        "-o",
        output_template,
        url,
    ])
    format_attempts = [
        "bv*[height>=720][height<=1080]+ba/b[height>=720][height<=1080]",
        "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
        "best[ext=mp4]/best",
    ]
    errors: list[str] = []
    total_timeout = max(15.0, settings.video_timeout_seconds)
    deadline = time.monotonic() + total_timeout
    for selector in format_attempts:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            errors.append("video download exhausted its total time budget")
            break
        command = common_command[:]
        format_index = command.index("--merge-output-format")
        command[format_index:format_index] = ["-f", selector]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=remaining,
            )
        except subprocess.TimeoutExpired:
            errors.append("video download timed out")
            continue
        candidates = sorted(
            (
                path
                for path in destination_stem.parent.glob(destination_stem.name + ".*")
                if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for candidate in candidates:
            candidate_size = candidate.stat().st_size
            if 0 < candidate_size <= max_bytes:
                return candidate
            candidate.unlink(missing_ok=True)
            errors.append("downloaded video was empty or exceeded the size limit")
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        errors.append(detail[-1] if detail else f"format {selector!r} produced no file")
    raise ValueError(errors[-1] if errors else "yt-dlp completed without a supported video file")


def media_type_for(path: Path) -> MediaType:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return MediaType.video
    if ext in DOCUMENT_EXTENSIONS:
        return MediaType.document
    if ext in IMAGE_EXTENSIONS:
        return MediaType.image
    supported = ", ".join(sorted(SUPPORTED_VISUAL_EXTENSIONS))
    raise ValueError(f"unsupported visual file type; expected one of: {supported}")


def media_metadata(path: Path) -> dict:
    data = ffprobe_summary(path)
    if data:
        return data
    return {}


def _broadcast_aspect_range(media_type: MediaType | str | None = None) -> tuple[float, float]:
    media_value = media_type.value if hasattr(media_type, "value") else media_type
    settings = config.get_settings().visuals
    tolerance = max(
        0.05,
        settings.image_aspect_tolerance
        if media_value == MediaType.image.value
        else settings.aspect_tolerance,
    )
    return (
        SPLIT_VISUAL_ASPECT_RATIO - tolerance,
        FULLSCREEN_VISUAL_ASPECT_RATIO + tolerance,
    )


def broadcast_media_fit(
    width: int | None,
    height: int | None,
    media_type: MediaType | str | None = None,
) -> tuple[bool, str, float]:
    """Check whether media can fill the two landscape news layouts cleanly."""

    if not width or not height:
        return False, "media dimensions could not be verified", 0.0
    settings = config.get_settings().visuals
    min_width = settings.min_width
    min_height = settings.min_height
    ratio = width / height
    min_ratio, max_ratio = _broadcast_aspect_range(media_type)
    if ratio < min_ratio or ratio > max_ratio:
        return (
            False,
            f"aspect ratio {ratio:.3f} is outside landscape range "
            f"{min_ratio:.3f}-{max_ratio:.3f}",
            0.0,
        )
    if width < min_width or height < min_height:
        return (
            False,
            f"resolution {width}x{height} is below {min_width}x{min_height}",
            0.0,
        )
    nearest_delta = min(
        abs(ratio - SPLIT_VISUAL_ASPECT_RATIO),
        abs(ratio - FULLSCREEN_VISUAL_ASPECT_RATIO),
    )
    media_value = media_type.value if hasattr(media_type, "value") else media_type
    tolerance = (
        settings.image_aspect_tolerance
        if media_value == MediaType.image.value
        else settings.aspect_tolerance
    )
    aspect_score = max(0.0, 1.0 - nearest_delta / max(tolerance, 0.05))
    resolution_score = min(1.0, (width * height) / (1920 * 1080))
    quality_score = round(0.55 + 0.25 * aspect_score + 0.20 * resolution_score, 3)
    return True, f"broadcast-fit {width}x{height} at {ratio:.3f}:1", quality_score


def visual_media_dir(episode_id: str, story_id: str) -> Path:
    return story_dir(episode_id, story_id) / "visuals" / "media"


def visual_thumbnail_dir(episode_id: str, story_id: str) -> Path:
    return story_dir(episode_id, story_id) / "visuals" / "thumbnails"


def safe_filename(name: str) -> str:
    stem = Path(name).stem.replace(" ", "_")[:80] or "visual"
    suffix = Path(name).suffix.lower() or ".bin"
    clean = "".join(char for char in stem if char.isalnum() or char in {"_", "-", "."})
    return f"{clean}{suffix}"


def _local_asset_id(story_id: str, source: Path) -> str:
    digest = hashlib.sha1(
        f"{story_id}\n{source.resolve().as_posix()}".encode("utf-8")
    ).hexdigest()
    return f"visual_{digest[:20]}"


def _validated_section_ids(
    repository, story_id: str, section_ids: list[str] | None
) -> list[str]:
    normalized = list(dict.fromkeys(section_id.strip() for section_id in section_ids or []))
    if any(not section_id for section_id in normalized):
        raise ValueError("visual section_ids cannot contain empty values")
    if not normalized:
        return []
    script = repository.latest_script(story_id)
    if not script:
        raise ValueError("visuals cannot be assigned to sections before a script exists")
    known = {section.section_id for section in script.sections}
    unknown = sorted(set(normalized) - known)
    if unknown:
        raise ValueError(f"unknown visual section_ids: {unknown}")
    return normalized


def create_thumbnail(path: Path, destination: Path) -> Path | None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        thumb = destination.with_suffix(
            path.suffix.lower() if path.suffix.lower() != ".svg" else ".svg"
        )
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
            "-update",
            "1",
            str(thumb),
        ]
        try:
            subprocess.run(command, check=True)
            return thumb
        except (FileNotFoundError, subprocess.CalledProcessError):
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
    if content_role == ContentRole.fallback:
        raise ValueError(
            "local media cannot use the fallback content role; choose its editorial role"
        )
    source = resolve_project_path(source_path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Local visual not found: {source}")
    if source.suffix.lower() not in SUPPORTED_VISUAL_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_VISUAL_EXTENSIONS))
        raise ValueError(f"unsupported visual file type; expected one of: {supported}")
    episode = repository.episode_for_story(story_id)
    original_name = source.name
    episode_inbox = episode_media_inbox_dir(
        episode.project_id, episode.episode_id
    ).resolve()
    episode_inbox.mkdir(parents=True, exist_ok=True)
    source = source.resolve()
    if not source.is_relative_to(episode_inbox):
        # Treat an arbitrary path entered in Studio as an import. The durable
        # source must live under this episode so another production can never
        # discover or process it accidentally.
        digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:10]
        imported_dir = episode_inbox / "imports" / story_id
        imported_dir.mkdir(parents=True, exist_ok=True)
        imported = imported_dir / safe_filename(
            f"{source.stem}-{digest}{source.suffix.lower()}"
        )
        if source != imported.resolve():
            shutil.copy2(source, imported)
        source = imported.resolve()
    asset_id = _local_asset_id(story_id, source)
    media_root = visual_media_dir(episode.episode_id, story_id)
    media_root.mkdir(parents=True, exist_ok=True)
    safe_name = Path(safe_filename(source.name))
    destination = media_root / (
        f"{safe_name.stem}-{asset_id.rsplit('_', 1)[-1][-8:]}{safe_name.suffix}"
    )
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    metadata = media_metadata(destination)
    local_stat = destination.stat()
    media_type = media_type_for(destination)
    thumbnail = create_thumbnail(
        destination,
        visual_thumbnail_dir(episode.episode_id, story_id) / destination.stem,
    )
    # Episode-library media is not evidence for every section. Keep it
    # unassigned unless the editor or source integration supplies an explicit
    # mapping; approved unassigned media can still be distributed by the
    # timeline planner without contaminating other section search results.
    effective_section_ids = _validated_section_ids(
        repository, story_id, section_ids
    )
    visual = VisualCandidate(
        asset_id=asset_id,
        story_id=story_id,
        section_ids=effective_section_ids,
        provider="local_upload",
        source_url=project_relative(source),
        source_domain="local",
        download_path=project_relative(destination),
        thumbnail_path=project_relative(thumbnail) if thumbnail else None,
        media_type=media_type,
        mime_type=mimetypes.guess_type(destination.name)[0],
        width=metadata.get("width"),
        height=metadata.get("height"),
        duration_seconds=metadata.get("duration_seconds"),
        has_audio=(bool(metadata.get("audio_codec")) if media_type == MediaType.video else False),
        title=title or Path(original_name).stem.replace("_", " ").title(),
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
        attribution_text=f"Source: user-provided ({original_name})",
        manual_review_flag=rights_tier != RightsTier.green,
        review_status=ReviewStatus.suggested,
        warnings=[
            "Local upload requires editor rights review before production rendering"
        ]
        if rights_tier == RightsTier.yellow
        else [],
        motion={"preset": "push_in", "intensity": 0.22},
        source_class="user_owned",
        source_identity=f"user-provided ({original_name})",
        source_verified=True,
        source_metadata={
            "local_file_size": local_stat.st_size,
            "local_file_mtime_ns": local_stat.st_mtime_ns,
        },
        content_cleanliness_status="needs_review",
        approval_blockers=[],
    )
    visual = _merge_rediscovered_visual(repository, visual)
    repository.upsert_visual(visual)
    candidate = repository.candidate_for_story(story_id)
    if candidate.workflow_state == StoryWorkflowState.script_approved:
        repository.transition_story(story_id, StoryWorkflowState.visuals_searching)
        repository.transition_story(story_id, StoryWorkflowState.visuals_review)
    return visual


def _advance_to_visuals_review(repository, story_id: str) -> None:
    candidate = repository.candidate_for_story(story_id)
    if candidate.workflow_state == StoryWorkflowState.script_approved:
        repository.transition_story(story_id, StoryWorkflowState.visuals_searching)
        repository.transition_story(story_id, StoryWorkflowState.visuals_review)
    elif candidate.workflow_state == StoryWorkflowState.visuals_searching:
        repository.transition_story(story_id, StoryWorkflowState.visuals_review)


def generate_script_visual_cards(repository, story_id: str) -> list[VisualCandidate]:
    """Create semantic anchor-only fallbacks, never synthetic image cards.

    The legacy implementation wrote a headline-and-paragraph SVG for every
    section. When the broadcast shell rendered that SVG as normal media it
    duplicated the headline, narration, attribution, and lower third. Fallbacks
    are now data-only signals that tell the planner to keep the presenter on
    screen until an editor approves real media.
    """
    if not config.get_settings().visuals.generate_fallback_visuals:
        return []
    existing = [
        visual
        for visual in repository.list_visuals(story_id)
        if visual.provider in {"generated_visual_card", "synthpost_anchor_fallback"}
    ]

    script = repository.latest_script(story_id)
    if not script:
        return []

    by_section = {
        section_id: visual
        for visual in existing
        for section_id in visual.section_ids
    }
    visuals: list[VisualCandidate] = []
    for section in script.sections:
        if not section.text.strip():
            continue
        current = by_section.get(section.section_id)
        payload = dict(
            section_ids=[section.section_id],
            provider="synthpost_anchor_fallback",
            source_url=None,
            source_domain="synthpost.local",
            download_path=None,
            thumbnail_path=None,
            media_type=MediaType.fallback,
            mime_type=None,
            width=None,
            height=None,
            title=f"{section.section_type.replace('_', ' ').title()} — Anchor-only fallback",
            description=(
                "Automatic safe fallback: keep the presenter on screen without "
                "generating or displaying synthetic imagery."
            ),
            creator="SynthPost Studio",
            relevance_score=0.0,
            visual_quality_score=1.0,
            source_authority=1.0,
            content_role=ContentRole.fallback,
            rights_tier=RightsTier.green,
            rights_confidence=1.0,
            usage_basis="synthpost_anchor_only_fallback",
            license="not_applicable",
            attribution_required=False,
            attribution_text="",
            manual_review_flag=False,
            review_status=ReviewStatus.approved,
            warnings=["Presenter-only fallback; no generated image is rendered."],
            motion={},
            has_audio=False,
        )
        visual = (
            current.model_copy(update=payload)
            if current
            else VisualCandidate(story_id=story_id, **payload)
        )
        repository.upsert_visual(visual)
        visuals.append(visual)
    return visuals


def search_episode_media_inbox(
    repository,
    story_id: str,
    *,
    section_ids: list[str] | None = None,
    generate_fallback: bool = True,
) -> list[VisualCandidate]:
    episode = repository.episode_for_story(story_id)
    drop = episode_media_inbox_dir(episode.project_id, episode.episode_id)
    drop.mkdir(parents=True, exist_ok=True)
    visuals: list[VisualCandidate] = []
    if drop.exists():
        for path in sorted(drop.rglob("*")):
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
                    usage_basis="episode_media_inbox",
                )
            )
    if not visuals and generate_fallback:
        visuals = generate_script_visual_cards(repository, story_id)
    _advance_to_visuals_review(repository, story_id)
    return visuals


def _visual_search_queries(repository, story_id: str) -> list[tuple[str | None, str]]:
    """Build a deterministic per-section fallback when AI planning is disabled."""

    script = repository.latest_script(story_id)
    candidate = repository.candidate_for_story(story_id)
    queries: list[tuple[str | None, str]] = []
    seen: set[str] = set()
    if script:
        for section in script.sections:
            suggestions = [
                value.strip()
                for value in section.suggested_search_queries
                if value.strip()
            ]
            if not suggestions:
                label = section.section_type.replace("_", " ")
                suggestions = [f"{script.headline} {label} news"]
            query = suggestions[0]
            normalized = " ".join(query.lower().split())
            if normalized in seen:
                continue
            seen.add(normalized)
            queries.append((section.section_id, query))
    fallback = candidate.title.strip()
    if not queries and fallback and " ".join(fallback.lower().split()) not in seen:
        queries.append((None, f"{fallback} news"))
    return queries


_VIDEO_QUERY_MARKERS = {"clip", "footage", "video"}
_NON_VIDEO_QUERY_TOKENS = {"chart", "diagram", "infographic", "map", "timeline"}


def _video_query(seed: str, headline: str) -> str:
    seed = re.sub(
        r"\b(?:breaking news|news coverage|news report|news footage|explainer)\b",
        " ",
        seed,
        flags=re.IGNORECASE,
    )
    tokens = [
        token
        for token in seed.split()
        if token.lower().strip(".,:;()[]") not in _NON_VIDEO_QUERY_TOKENS
    ]
    query = " ".join(tokens).strip() or headline.strip()
    if not re.search(r"\b(?:official|raw|b[- ]?roll|press)\b", query, re.IGNORECASE):
        query = f"{query} official raw footage"
    return query


def _image_query(seed: str) -> str:
    return " ".join(
        token
        for token in seed.split()
        if token.lower().strip(".,:;()[]") not in _VIDEO_QUERY_MARKERS
    ).strip()


def _fallback_visual_search_plan(repository, story_id: str) -> list[VisualQueryPlan]:
    script = repository.latest_script(story_id)
    section_by_id = (
        {section.section_id: section for section in script.sections}
        if script
        else {}
    )
    plans: list[VisualQueryPlan] = []
    for section_id, image_query in _visual_search_queries(repository, story_id):
        section = section_by_id.get(section_id) if section_id else None
        suggestions = (
            [
                query.strip()
                for query in section.suggested_search_queries
                if query.strip()
            ]
            if section
            else []
        )
        video_seed = suggestions[1] if len(suggestions) > 1 else image_query
        suggested_types = {
            value.strip().lower()
            for value in (section.suggested_visual_types if section else [])
        }
        section_type = section.section_type if section else ""
        source_clip = section.source_clip if section else None
        video_priority = (
            source_clip is not None
            or "video" in suggested_types
            or section_type
            in {
                "cold_open",
                "key_developments",
                "conclusion",
            }
        )
        plans.append(
            VisualQueryPlan(
                section_id=section_id,
                image_query=image_query,
                video_query=_video_query(
                    source_clip.search_query if source_clip else video_seed,
                    script.headline if script else image_query,
                ),
                video_priority=video_priority,
                rationale=(
                    "stored script query fallback; AI keyword planning disabled"
                ),
            )
        )
    return plans


def _visual_query_schema() -> dict:
    return {
        "type": "object",
        "required": ["queries"],
        "properties": {
            "queries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "section_id",
                        "image_query",
                        "video_query",
                        "video_priority",
                        "rationale",
                    ],
                    "properties": {
                        "section_id": {"type": "string"},
                        "image_query": {"type": "string"},
                        "video_query": {"type": "string"},
                        "video_priority": {"type": "boolean"},
                        "rationale": {"type": "string"},
                    },
                },
            }
        },
    }


_YEAR_TOKEN = re.compile(r"\b(?:19|20)\d{2}\b")


def _remove_unsupported_years(query: str, supported_years: set[str]) -> str:
    """Drop invented date filters without discarding an otherwise grounded query."""

    return " ".join(
        _YEAR_TOKEN.sub(
            lambda match: match.group(0)
            if match.group(0) in supported_years
            else " ",
            query,
        ).split()
    )


def _validate_ai_visual_plan(
    raw: dict,
    *,
    section_ids: set[str],
    provider_name: str,
    supported_years: set[str],
) -> list[VisualQueryPlan]:
    rows = raw.get("queries")
    if not isinstance(rows, list):
        raise ValueError("visual keyword plan must contain a queries array")
    plans: list[VisualQueryPlan] = []
    seen_sections: set[str] = set()
    seen_queries: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("every visual keyword entry must be an object")
        section_id = str(row.get("section_id") or "").strip()
        if section_id not in section_ids or section_id in seen_sections:
            raise ValueError(f"invalid or duplicate section_id: {section_id}")
        image_seed = _remove_unsupported_years(
            " ".join(str(row.get("image_query") or "").split()),
            supported_years,
        )
        video_seed = _remove_unsupported_years(
            " ".join(str(row.get("video_query") or "").split()),
            supported_years,
        )
        image_query = _image_query(image_seed)
        video_query = _video_query(
            video_seed, image_query
        )
        if not image_query or image_query.lower() == video_query.lower():
            raise ValueError(f"section {section_id} needs distinct image/video queries")
        for query in (image_query, video_query):
            word_count = len(query.split())
            if word_count < 3 or word_count > 18:
                raise ValueError(
                    f"query for {section_id} must contain 3-18 words: {query!r}"
                )
            normalized = query.lower()
            if normalized in seen_queries:
                raise ValueError(f"duplicate visual search query: {query}")
            seen_queries.add(normalized)
        seen_sections.add(section_id)
        plans.append(
            VisualQueryPlan(
                section_id=section_id,
                image_query=image_query,
                video_query=video_query,
                video_priority=bool(row.get("video_priority")),
                rationale=(
                    f"AI keyword planner ({provider_name}): "
                    f"{str(row.get('rationale') or 'section-grounded query').strip()}"
                ),
            )
        )
    missing = section_ids - seen_sections
    if missing:
        raise ValueError(f"visual keyword plan omitted sections: {sorted(missing)}")
    return plans


def _visual_search_plan(repository, story_id: str) -> list[VisualQueryPlan]:
    script = repository.latest_script(story_id)
    candidate = repository.candidate_for_story(story_id)
    if not script:
        return _fallback_visual_search_plan(repository, story_id)
    if not config.get_settings().visuals.ai_query_planning:
        return _fallback_visual_search_plan(repository, story_id)

    provider_name = (
        "hermes"
        if config.get_settings().hermes.visual_provider == "hermes"
        else None
    )
    provider = configured_provider(provider_name)
    research_pack_loader = getattr(repository, "latest_research_pack", None)
    research_pack = (
        research_pack_loader(story_id) if research_pack_loader else None
    ) or {}
    claim_by_id = {
        str(claim.get("claim_id")): str(claim.get("claim_text") or "")
        for claim in research_pack.get("claims", [])
        if claim.get("claim_id")
    }
    prompt_input = {
        "topic": candidate.title,
        "headline": script.headline,
        "category": script.category,
        "verified_dates": research_pack.get("dates", []),
        "verified_people": research_pack.get("people", []),
        "verified_organizations": research_pack.get("organizations", []),
        "verified_locations": research_pack.get("locations", []),
        "sections": [
            {
                "section_id": section.section_id,
                "section_type": section.section_type,
                "narration": section.text[:900],
                "claim_ids": section.claim_ids,
                "linked_claims": [
                    claim_by_id[claim_id]
                    for claim_id in section.claim_ids
                    if claim_id in claim_by_id
                ],
                "visual_direction": section.suggested_visual_types,
                "source_clip": (
                    section.source_clip.model_dump(mode="json")
                    if section.source_clip
                    else None
                ),
            }
            for section in script.sections
        ],
    }
    editorial_fit = getattr(candidate, "editorial_fit", None)
    primary_topic = getattr(editorial_fit, "primary_topic", script.category)
    prompt = f"""
You are SynthPost's visual search keyword planner.
Turn the supplied news topic and section narration into search-engine keyword phrases for SearXNG.

{charter_prompt_context(show_format=script.narration_mode.value)}

For every section return exactly one image_query and one distinct video_query.
- Ground both queries in concrete verified names, organizations, objects, events, places, and dates present in the input.
- image_query should favor a map, system diagram, sourced data visual, infrastructure,
  primary document, authentic editorial photograph, product demonstration or real interface.
- video_query should seek the original event/person/place from an official primary source and use "official video", "raw footage", "B-roll", or "press footage".
- Never ask for "news coverage", "breaking news", "explainer", "news report", or a finished broadcaster package.
- Prefer named primary sources such as the responsible ministry, agency, organization, event operator, or official press office.
- Target horizontal broadcast media close to 16:9 or 3:2. Prefer 1920x1080 or larger and never request portrait/vertical media.
- Prefer event-authentic footage over generic stock, CGI, explainers, thumbnails, presenter monologues, or speculative imagery.
- Use concise keyword phrases of 3-18 words; do not write sentences or instructions.
- Do not invent an event, appearance, location, date, or person that the input does not support.
- Treat linked_claims and verified entities as factual grounding. Legacy search-query hints are intentionally excluded.
- Set video_priority true only when motion materially improves the section.
- When source_clip is present, video_priority MUST be true and video_query must
  target that exact original audible moment—not generic B-roll or a news package.
- Explain the concrete subject choice briefly in rationale.

INPUT JSON:
{json.dumps(prompt_input, ensure_ascii=True)}
""".strip()
    generation_error: StructuredGenerationError | None = None
    try:
        plans, _attempts = structured_generate(
            provider,
            prompt,
            _visual_query_schema(),
            lambda raw: _validate_ai_visual_plan(
                raw,
                section_ids={section.section_id for section in script.sections},
                provider_name=provider.name,
                supported_years=set(
                    re.findall(r"\b(?:19|20)\d{2}\b", json.dumps(prompt_input))
                ),
            ),
            max_retries=2,
        )
    except StructuredGenerationError as exc:
        plans = []
        _attempts = exc.attempts
        generation_error = exc
    latest_attempt = _attempts[-1] if _attempts else {}
    audit_saver = getattr(repository, "save_generation_audit", None)
    if audit_saver:
        audit_saver(GenerationAudit(
            story_id=story_id,
            stage="visual_query_planner",
            prompt_version="synthpost.visual-query.v2",
            charter_version=CHARTER_VERSION,
            provider=str(latest_attempt.get("provider") or provider.name),
            model=latest_attempt.get("model"),
            prompt_text=prompt,
            response=latest_attempt.get("raw") if isinstance(latest_attempt.get("raw"), dict) else None,
            attempts=_attempts,
            validation_events=[
                {
                    "attempt": attempt.get("attempt"),
                    "ok": attempt.get("ok", False),
                    "error": attempt.get("error"),
                }
                for attempt in _attempts
            ],
            normalization_events=(
                [
                    {
                        "kind": "visual_query_plan_validated",
                        "section_count": len(plans),
                        "reason": "preserved section IDs and verified date constraints",
                    }
                ]
                if not generation_error
                else []
            ),
            status="failed" if generation_error else "completed",
        ))
    if generation_error:
        # Query planning is an optional optimization. Keep the visual stage
        # usable during provider or validation failures by searching the
        # script-authored section hints, while retaining the failed audit above.
        plans = _fallback_visual_search_plan(repository, story_id)
    source_clip_by_section = {
        section.section_id: section.source_clip
        for section in script.sections
        if section.source_clip is not None
    }
    return [
        VisualQueryPlan(
            section_id=plan.section_id,
            image_query=plan.image_query,
            video_query=_video_query(
                source_clip_by_section[plan.section_id].search_query,
                script.headline,
            ),
            video_priority=True,
            rationale=(
                f"authored source-audio insert: {plan.rationale}"
            ),
        )
        if plan.section_id in source_clip_by_section
        else plan
        for plan in plans
    ]


def _visual_search_tasks(
    plans: list[VisualQueryPlan], max_queries: int
) -> list[tuple[VisualQueryPlan, str, str, MediaType]]:
    """Allocate the exact SearXNG request budget across sections and media."""

    primary: list[tuple[VisualQueryPlan, str, str, MediaType]] = []
    secondary: list[tuple[VisualQueryPlan, str, str, MediaType]] = []
    for plan in plans:
        image_task = (plan, "images", plan.image_query, MediaType.image)
        video_task = (plan, "videos", plan.video_query, MediaType.video)
        if plan.video_priority:
            primary.append(video_task)
            secondary.append(image_task)
        else:
            primary.append(image_task)
            secondary.append(video_task)
    return (primary + secondary)[:max_queries]


def _remote_asset_id(story_id: str, media_url: str) -> str:
    digest = hashlib.sha1(f"{story_id}\n{media_url}".encode("utf-8")).hexdigest()
    return f"visual_{digest[:20]}"


def _relevance_score(result: SearXNGResult, rank: int) -> float:
    rank_score = max(0.25, 0.88 - (rank * 0.07))
    engine_score = result.score / (result.score + 1.0) if result.score > 0 else 0.0
    return round(min(0.95, max(rank_score, engine_score)), 3)


_VISUAL_QUERY_STOPWORDS = {
    "and",
    "for",
    "from",
    "how",
    "india",
    "news",
    "the",
    "with",
    "clip",
    "footage",
    "image",
    "landscape",
    "photo",
    "resolution",
    "1080p",
    "horizontal",
    "video",
}


def _result_matches_query(result: SearXNGResult, query: str) -> bool:
    query_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if len(token) > 2 and token not in _VISUAL_QUERY_STOPWORDS
    }
    if not query_tokens:
        return True
    result_tokens = set(
        re.findall(
            r"[a-z0-9]+",
            f"{result.title} {result.snippet} {result.url}".lower(),
        )
    )
    overlap = query_tokens & result_tokens
    required = 1 if len(query_tokens) <= 2 else 2
    return len(overlap) >= required


def _find_visual(repository, story_id: str, asset_id: str) -> VisualCandidate | None:
    return next(
        (
            candidate
            for candidate in repository.list_visuals(story_id)
            if candidate.asset_id == asset_id
        ),
        None,
    )


def _merge_rediscovered_visual(
    repository,
    discovered: VisualCandidate,
    *,
    media_reacquired: bool = False,
) -> VisualCandidate:
    """Keep acquired media and editor decisions when search finds an asset again.

    Remote result URLs are often short-lived. Re-running discovery must be able
    to add another section association or refresh descriptive metadata without
    replacing a usable local file with a newly failed download attempt.
    """

    existing = _find_visual(
        repository, discovered.story_id, discovered.asset_id
    )
    if existing is None:
        return discovered

    section_ids = list(dict.fromkeys([*existing.section_ids, *discovered.section_ids]))
    source_metadata = {**existing.source_metadata, **discovered.source_metadata}
    updates: dict[str, Any] = {
        "section_ids": section_ids,
        "source_metadata": source_metadata,
    }

    fingerprint_keys = ("local_file_size", "local_file_mtime_ns")
    existing_fingerprint = tuple(
        existing.source_metadata.get(key) for key in fingerprint_keys
    )
    discovered_fingerprint = tuple(
        discovered.source_metadata.get(key) for key in fingerprint_keys
    )
    fingerprints_are_known = all(value is not None for value in existing_fingerprint) and all(
        value is not None for value in discovered_fingerprint
    )
    media_identity_changed = (
        fingerprints_are_known and existing_fingerprint != discovered_fingerprint
    )
    if not media_identity_changed:
        updates["created_at"] = existing.created_at

    existing_media_value = existing.download_path or existing.quarantine_path
    existing_media_is_available = bool(
        existing_media_value
        and resolve_project_path(existing_media_value).is_file()
    )
    relocating_local_media = bool(
        discovered.provider == "local_upload"
        and discovered.download_path
        and discovered.download_path != existing.download_path
    )
    if (
        existing_media_is_available
        and not media_identity_changed
        and not media_reacquired
    ):
        for field_name in (
            "download_path",
            "quarantine_path",
            "thumbnail_path",
            "mime_type",
            "width",
            "height",
            "duration_seconds",
            "has_audio",
            "visual_quality_score",
            "content_cleanliness_status",
            "contains_third_party_logo",
            "detected_brands",
            "contains_lower_third",
            "contains_ticker",
            "contains_presenter",
            "ocr_findings",
            "scan_timestamps",
            "analysis_frame_paths",
            "contact_sheet_path",
            "clean_broll_score",
            "content_analysis_version",
            "content_analysis_provider",
            "content_analysis_evidence",
            "approval_blockers",
            "warnings",
        ):
            if relocating_local_media and field_name in {
                "download_path",
                "quarantine_path",
                "thumbnail_path",
            }:
                continue
            updates[field_name] = getattr(existing, field_name)

    editor_state_exists = (
        existing.review_status != ReviewStatus.suggested
        or existing.broadcast_fit_override
        or existing.trim_start is not None
        or existing.trim_end is not None
    )
    if (
        editor_state_exists
        and not media_identity_changed
        and not media_reacquired
    ):
        for field_name in (
            "rights_tier",
            "rights_confidence",
            "usage_basis",
            "license",
            "attribution_required",
            "attribution_text",
            "manual_review_flag",
            "review_status",
            "reviewed_at",
            "broadcast_fit_override",
            "trim_start",
            "trim_end",
            "motion",
        ):
            updates[field_name] = getattr(existing, field_name)
        if not existing_media_is_available:
            updates["warnings"] = list(
                dict.fromkeys([*existing.warnings, *discovered.warnings])
            )

    return discovered.model_copy(update=updates)


def _stage_searxng_result(
    repository,
    story_id: str,
    section_id: str | None,
    result: SearXNGResult,
    media_type: MediaType,
    rank: int,
    *,
    acquire_video: bool | None = None,
) -> VisualCandidate | None:
    episode = repository.episode_for_story(story_id)
    media_root = visual_media_dir(episode.episode_id, story_id)
    media_root.mkdir(parents=True, exist_ok=True)
    source_domain = result.source_domain or urlparse(result.url).hostname
    warnings = [
        "SearXNG is a discovery source, not a license grant; verify ownership, "
        "license, and editorial-use basis before approval"
    ]
    direct_media_url = result.image_url if media_type == MediaType.image else result.url
    asset_basis = direct_media_url or result.thumbnail_url or result.url
    asset_id = _remote_asset_id(story_id, asset_basis)
    stem = media_root / asset_id
    download_path: Path | None = None
    quarantine_path: Path | None = None
    thumbnail: Path | None = None
    visual_settings = config.get_settings().visuals
    existing = _find_visual(repository, story_id, asset_id)
    existing_media_was_missing = False
    if existing:
        existing_media_value = existing.download_path or existing.quarantine_path
        existing_media_was_missing = bool(
            existing_media_value
            and not resolve_project_path(existing_media_value).is_file()
        )
    if existing and existing.download_path:
        existing_path = resolve_project_path(existing.download_path)
        if existing_path.is_file():
            download_path = existing_path
    if existing and existing.thumbnail_path:
        existing_thumbnail = resolve_project_path(existing.thumbnail_path)
        if existing_thumbnail.is_file():
            thumbnail = existing_thumbnail
    should_acquire_video = (
        visual_settings.download_videos if acquire_video is None else acquire_video
    )
    if media_type == MediaType.image and result.image_url and download_path is None:
        try:
            download_path = _download_remote_image(result.image_url, stem)
            thumbnail = create_thumbnail(
                download_path,
                visual_thumbnail_dir(episode.episode_id, story_id) / asset_id,
            )
        except Exception as exc:
            warnings.append(f"image download failed: {exc}")
    if (
        media_type == MediaType.video
        and should_acquire_video
        and download_path is None
    ):
        try:
            download_path = _download_remote_video(result.url, stem)
            thumbnail = create_thumbnail(
                download_path,
                visual_thumbnail_dir(episode.episode_id, story_id) / asset_id,
            )
        except Exception as exc:
            warnings.append(f"video download failed: {exc}")
    elif media_type == MediaType.video and download_path is None:
        warnings.append(
            "video is a research lead only; use Download video to acquire a local copy"
        )

    metadata = media_metadata(download_path) if download_path else {}
    visual_quality_score = 0.35
    if download_path:
        eligible, fit_reason, visual_quality_score = broadcast_media_fit(
            metadata.get("width"), metadata.get("height"), media_type
        )
        if visual_settings.enforce_broadcast_fit and not eligible:
            warnings.append(f"broadcast layout warning: {fit_reason}")
            # Retain technically valid media for explicit editor review. The
            # timeline excludes it unless a manual broadcast-fit override is
            # recorded during approval.
            visual_quality_score = 0.0
        elif eligible:
            warnings.append(fit_reason)

    analysis_data: dict[str, Any] = {
        "source_class": "editor_review",
        "source_identity": source_domain or result.engine,
        "source_metadata": {
            "search_result_title": result.title,
            "source_url": result.url,
            "image_url": result.image_url,
        },
        # Downloading verifies the file, not its editorial cleanliness. The
        # editor records that decision explicitly when approving the asset.
        "content_cleanliness_status": "needs_review" if download_path else "not_scanned",
        "content_analysis_evidence": [],
        "approval_blockers": [],
    }

    if thumbnail is None and result.thumbnail_url:
        try:
            thumbnail = _download_remote_image(
                result.thumbnail_url,
                visual_thumbnail_dir(episode.episode_id, story_id) / asset_id,
            )
        except Exception as exc:
            warnings.append(f"thumbnail download failed: {exc}")

    media_path = download_path
    visual = VisualCandidate(
        asset_id=asset_id,
        story_id=story_id,
        section_ids=[section_id] if section_id else [],
        provider=f"searxng:{result.engine}",
        source_url=result.url,
        source_domain=source_domain,
        download_path=project_relative(download_path) if download_path else None,
        quarantine_path=(
            project_relative(quarantine_path) if quarantine_path else None
        ),
        thumbnail_path=project_relative(thumbnail) if thumbnail else None,
        media_type=media_type,
        mime_type=(
            mimetypes.guess_type(media_path.name)[0] if media_path else None
        ),
        width=metadata.get("width"),
        height=metadata.get("height"),
        duration_seconds=metadata.get("duration_seconds"),
        has_audio=(
            bool(metadata.get("audio_codec"))
            if media_type == MediaType.video
            else False
        ),
        title=result.title,
        description=result.snippet,
        creator=source_domain,
        published_at=result.published_date,
        relevance_score=_relevance_score(result, rank),
        visual_quality_score=visual_quality_score,
        source_authority=0.5,
        content_role=(
            ContentRole.primary_footage
            if media_type == MediaType.video
            else ContentRole.context
        ),
        rights_tier=RightsTier.yellow,
        rights_confidence=0.0,
        usage_basis="editor_manual_review_required",
        license="unknown_requires_editor_verification",
        attribution_required=True,
        attribution_text=f"Source: {source_domain or result.engine}",
        manual_review_flag=True,
        review_status=ReviewStatus.suggested,
        warnings=warnings,
        motion={"preset": "slow_push", "intensity": 0.18},
        **analysis_data,
    )
    if not download_path and not visual_settings.include_leads:
        if thumbnail:
            thumbnail.unlink(missing_ok=True)
        return None
    visual = _merge_rediscovered_visual(
        repository,
        visual,
        media_reacquired=existing_media_was_missing and bool(download_path),
    )
    repository.upsert_visual(visual)
    return visual


def search_searxng_visuals(
    repository,
    story_id: str,
    *,
    progress_callback=None,
    cancel_check=None,
) -> list[VisualCandidate]:
    visual_settings = config.get_settings().visuals
    if not searxng_configured() or visual_settings.disable_web_visuals:
        return []
    image_limit = visual_settings.image_results_per_query
    video_limit = visual_settings.video_results_per_query
    visuals: list[VisualCandidate] = []
    seen_media: dict[str, VisualCandidate] = {}
    preexisting_local_asset_ids = {
        visual.asset_id
        for visual in repository.list_visuals(story_id)
        if visual.download_path
        and resolve_project_path(visual.download_path).is_file()
    }
    errors: list[str] = []
    downloaded_videos = 0
    video_download_limit = visual_settings.video_download_limit
    downloads_enabled = visual_settings.download_videos
    max_queries = visual_settings.visual_max_queries
    tasks = _visual_search_tasks(
        _visual_search_plan(repository, story_id), max_queries
    )
    total_tasks = max(1, len(tasks))
    if progress_callback:
        progress_callback(0.08, "AI keyword plan ready; searching visual sources")
    for task_index, (plan, category, query, media_type) in enumerate(tasks):
        if cancel_check:
            cancel_check()
        if progress_callback:
            progress_callback(
                0.08 + (0.84 * task_index / total_tasks),
                f"searching {category}: {query[:72]}",
            )
        limit = image_limit if media_type == MediaType.image else video_limit
        if limit <= 0:
            continue
        try:
            search_limit = max(
                limit * 4, limit
            )
            results = searxng_search(
                query, categories=[category], limit=search_limit
            )
        except SearXNGError as exc:
            errors.append(f"{category} search for {query!r}: {exc}")
            continue
        accepted = 0
        staged = 0
        for rank, result in enumerate(results):
            if cancel_check:
                cancel_check()
            if not _result_matches_query(result, query):
                continue
            media_url = (
                result.image_url if media_type == MediaType.image else result.url
            )
            if not media_url:
                continue
            if media_url in seen_media:
                rediscovered = seen_media[media_url]
                if plan.section_id and plan.section_id not in rediscovered.section_ids:
                    rediscovered.section_ids.append(plan.section_id)
                    repository.upsert_visual(rediscovered)
                accepted += 1
                if accepted >= limit:
                    break
                continue
            visual = _stage_searxng_result(
                repository,
                story_id,
                plan.section_id,
                result,
                media_type,
                rank,
                acquire_video=(
                    downloads_enabled
                    and downloaded_videos < video_download_limit
                )
                if media_type == MediaType.video
                else None,
            )
            if visual is None:
                continue
            seen_media[media_url] = visual
            visuals.append(visual)
            staged += 1
            if (
                media_type == MediaType.video
                and visual.download_path
                and visual.asset_id not in preexisting_local_asset_ids
            ):
                downloaded_videos += 1
                preexisting_local_asset_ids.add(visual.asset_id)
            if media_type == MediaType.image and not visual.download_path:
                if staged >= max(limit * 2, 6):
                    break
                continue
            if (
                media_type == MediaType.video
                and downloads_enabled
                and not visual.download_path
                and downloaded_videos < video_download_limit
            ):
                if staged >= max(limit * 2, 3):
                    break
                continue
            accepted += 1
            if accepted >= limit:
                break
    if errors and not visuals:
        raise SearXNGError("; ".join(errors[:3]))
    if progress_callback:
        progress_callback(0.95, "visual source search complete")
    return visuals


@dataclass(frozen=True)
class EpisodeMediaInboxSource:
    name: str = "episode_media_inbox"

    def available(self) -> bool:
        return True

    def search(
        self,
        repository,
        story_id: str,
        *,
        progress_callback=None,
        cancel_check=None,
    ) -> list[VisualCandidate]:
        return search_episode_media_inbox(
            repository, story_id, generate_fallback=False
        )


@dataclass(frozen=True)
class SearXNGVisualSource:
    name: str = "searxng"

    def available(self) -> bool:
        return searxng_configured()

    def search(
        self,
        repository,
        story_id: str,
        *,
        progress_callback=None,
        cancel_check=None,
    ) -> list[VisualCandidate]:
        return search_searxng_visuals(
            repository,
            story_id,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )


def _hermes_visual_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["candidates"],
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "section_id",
                        "media_type",
                        "title",
                        "source_url",
                        "media_url",
                        "thumbnail_url",
                        "description",
                        "rationale",
                        "confidence",
                    ],
                    "properties": {
                        "section_id": {"type": "string"},
                        "media_type": {
                            "type": "string",
                            "enum": ["image", "video"],
                        },
                        "title": {"type": "string"},
                        "source_url": {"type": "string"},
                        "media_url": {"type": ["string", "null"]},
                        "thumbnail_url": {"type": ["string", "null"]},
                        "description": {"type": "string"},
                        "rationale": {"type": "string"},
                        "publisher": {"type": ["string", "null"]},
                        "published_at": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                    },
                },
            }
        },
    }


def search_hermes_visuals(
    repository,
    story_id: str,
    *,
    progress_callback=None,
    cancel_check=None,
) -> list[VisualCandidate]:
    """Ask Hermes for real image/video leads, then stage them through SynthPost."""

    script = repository.latest_script(story_id)
    if not script:
        return []
    candidate = repository.candidate_for_story(story_id)
    research = repository.latest_research_pack(story_id) or {}
    prompt_input = {
        "story": candidate.title,
        "verified_people": research.get("people", []),
        "verified_organizations": research.get("organizations", []),
        "verified_locations": research.get("locations", []),
        "verified_dates": research.get("dates", []),
        "sections": [
            {
                "section_id": section.section_id,
                "narration": section.text,
                "visual_direction": section.suggested_visual_types,
            }
            for section in script.sections
        ],
    }
    prompt = f"""
Find authentic editorial image and video leads for this approved SynthPost
script. Use web search, extraction, browser and vision tools where helpful.
Return up to two strong candidates per section. Prefer original official media,
primary documents, real event footage, named people/places/objects and clean
horizontal visuals. Avoid broadcaster packages, commentary videos, generic
stock, AI-generated imagery and unrelated thumbnails.

source_url must be the real public page where an editor can verify provenance.
For images, media_url should be the best direct image URL you actually found.
For videos, source_url should be the watch/source page and media_url may be null.
Do not claim a license. SynthPost will mark every result for manual rights review.
Do not invent URLs. A missing usable candidate is better than an unrelated one.

INPUT JSON:
{json.dumps(prompt_input, ensure_ascii=True)}
""".strip()
    client = HermesClient()

    def agent_progress(status: str, _: dict[str, Any]) -> None:
        if progress_callback:
            progress_callback(
                0.08 if status == "running" else 0.72,
                f"Hermes visual aggregation: {status}",
            )

    raw, _state = client.run_json(
        prompt,
        _hermes_visual_schema(),
        session_id=f"synthpost-visuals-{story_id}-{script.script_id}",
        progress_callback=agent_progress,
        cancel_check=cancel_check,
    )
    valid_sections = {section.section_id for section in script.sections}
    visuals: list[VisualCandidate] = []
    seen: set[tuple[str, str]] = set()
    for rank, row in enumerate(raw.get("candidates", [])):
        if cancel_check:
            cancel_check()
        if not isinstance(row, dict):
            continue
        section_id = str(row.get("section_id") or "").strip()
        media_value = str(row.get("media_type") or "").strip().lower()
        source_url = str(row.get("source_url") or "").strip()
        if section_id not in valid_sections or media_value not in {"image", "video"}:
            continue
        try:
            _assert_public_http_url(source_url)
        except ValueError:
            continue
        media_type = MediaType(media_value)
        media_url = str(row.get("media_url") or "").strip() or None
        thumbnail_url = str(row.get("thumbnail_url") or "").strip() or None
        if media_url:
            try:
                _assert_public_http_url(media_url)
            except ValueError:
                media_url = None
        if thumbnail_url:
            try:
                _assert_public_http_url(thumbnail_url)
            except ValueError:
                thumbnail_url = None
        identity = (source_url, media_url or "")
        if identity in seen:
            continue
        seen.add(identity)
        result = SearXNGResult(
            title=str(row.get("title") or source_url)[:500],
            url=source_url,
            snippet=(
                str(row.get("description") or "")
                + "\nHermes rationale: "
                + str(row.get("rationale") or "")
            )[:1200],
            engine="hermes",
            category="images" if media_type == MediaType.image else "videos",
            source_domain=urlparse(source_url).hostname,
            published_date=str(row.get("published_at") or "") or None,
            image_url=media_url if media_type == MediaType.image else None,
            thumbnail_url=thumbnail_url,
            score=max(0.0, min(1.0, float(row.get("confidence") or 0.0))),
            metadata={"hermes_rationale": str(row.get("rationale") or "")[:500]},
        )
        visual = _stage_searxng_result(
            repository,
            story_id,
            section_id,
            result,
            media_type,
            rank,
        )
        if visual is None:
            continue
        visual.provider = "hermes"
        visual.source_metadata["agent"] = "hermes"
        visual.source_metadata["rationale"] = str(row.get("rationale") or "")[:500]
        repository.upsert_visual(visual)
        visuals.append(visual)
    if not visuals:
        raise ValueError("Hermes returned no valid public visual candidates")
    if progress_callback:
        progress_callback(0.92, f"staged {len(visuals)} Hermes visual leads")
    return visuals


@dataclass(frozen=True)
class HermesVisualSource:
    name: str = "hermes"

    def available(self) -> bool:
        settings = config.get_settings().hermes
        return settings.enabled and settings.visual_provider == "hermes"

    def search(
        self,
        repository,
        story_id: str,
        *,
        progress_callback=None,
        cancel_check=None,
    ) -> list[VisualCandidate]:
        return search_hermes_visuals(
            repository,
            story_id,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )


def configured_visual_sources() -> tuple[VisualSource, ...]:
    """Return sources in deterministic precedence order.

    Add a source by implementing ``VisualSource`` and registering it here; the
    orchestration, review policy, and fallback generation stay unchanged.
    """

    sources: list[VisualSource] = [EpisodeMediaInboxSource()]
    if config.get_settings().hermes.visual_provider == "hermes":
        sources.append(HermesVisualSource())
    sources.append(SearXNGVisualSource())
    return tuple(sources)


def search_visuals(
    repository,
    story_id: str,
    *,
    progress_callback=None,
    cancel_check=None,
) -> list[VisualCandidate]:
    """Search local media, optional Hermes leads, SearXNG, then fallbacks."""

    script = repository.latest_script(story_id)
    if not script or script.status != ScriptStatus.approved:
        raise ValueError(
            "The latest script revision must be approved before searching for visuals"
        )
    visuals: list[VisualCandidate] = []
    for source in configured_visual_sources():
        if not source.available():
            continue
        if cancel_check:
            cancel_check()
        if progress_callback and source.name == "searxng":
            progress_callback(0.03, "local episode media scanned; planning web search")
        try:
            visuals.extend(
                source.search(
                    repository,
                    story_id,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                )
            )
        except SearXNGError:
            # Local media can keep a story moving, but when SearXNG is the only
            # configured source its outage must be visible as a failed job.
            if not visuals:
                raise
    # Always provide a rights-safe, local option for every script section. Web
    # discovery can be irrelevant or unusable until an editor clears rights;
    # one arbitrary file in the drop folder must not suppress all fallbacks.
    if cancel_check:
        cancel_check()
    visuals.extend(generate_script_visual_cards(repository, story_id))
    _advance_to_visuals_review(repository, story_id)
    return visuals


def analyze_visual(repository, asset_id: str) -> VisualCandidate:
    """Restore legacy quarantined media to the editor-controlled review flow.

    Kept under the existing endpoint name for API compatibility. No classifier,
    OCR scan, source preflight, or quarantine decision is performed.
    """
    visual = repository.get_visual(asset_id)
    media_value = visual.download_path or visual.quarantine_path
    if not media_value:
        raise ValueError("visual has no local media available for editor review")
    media_path = resolve_project_path(media_value)
    if not media_path.is_file():
        raise ValueError(f"visual media is missing: {media_value}")
    metadata = media_metadata(media_path)
    visual.width = metadata.get("width") or visual.width
    visual.height = metadata.get("height") or visual.height
    visual.duration_seconds = metadata.get("duration_seconds") or visual.duration_seconds
    visual.download_path = media_value
    visual.quarantine_path = None
    visual.content_cleanliness_status = "needs_review"
    visual.approval_blockers = []
    visual.content_analysis_evidence = []
    visual.content_analysis_provider = None
    visual.rights_tier = RightsTier.yellow
    visual.rights_confidence = 0.0
    visual.usage_basis = "editor_manual_review_required"
    if visual.review_status in {ReviewStatus.blocked, ReviewStatus.rejected}:
        visual.review_status = ReviewStatus.suggested
        visual.reviewed_at = None
    repository.upsert_visual(visual)
    return visual


def download_visual(repository, asset_id: str) -> VisualCandidate:
    """Acquire an image/video search lead for explicit manual approval."""

    visual = repository.get_visual(asset_id)
    if visual.media_type not in {MediaType.image, MediaType.video}:
        raise ValueError("only image and video research leads can be downloaded")
    media_path: Path | None = None
    acquisition_warning: str | None = None
    if visual.download_path:
        existing_path = resolve_project_path(visual.download_path)
        if existing_path.is_file():
            media_path = existing_path
    acquired_new_copy = media_path is None

    episode = repository.episode_for_story(visual.story_id)
    if media_path is None:
        if not visual.source_url:
            raise ValueError("visual research lead has no source URL")
        media_root = visual_media_dir(episode.episode_id, visual.story_id)
        media_root.mkdir(parents=True, exist_ok=True)
        destination_stem = (
            media_root / safe_filename(visual.asset_id).rsplit(".", 1)[0]
        )
        if visual.media_type == MediaType.video:
            media_path = _download_remote_video(
                visual.source_url,
                destination_stem,
                allow_long_source=True,
            )
        else:
            source_metadata = (
                visual.source_metadata
                if isinstance(visual.source_metadata, dict)
                else {}
            )
            direct_url = str(source_metadata.get("image_url") or visual.source_url)
            try:
                media_path = _download_remote_image(direct_url, destination_stem)
            except (ValueError, HTTPError, URLError, TimeoutError) as direct_error:
                try:
                    resolved_url = _resolve_page_image_url(visual.source_url)
                    media_path = _download_remote_image(
                        resolved_url,
                        destination_stem,
                    )
                except Exception as page_error:
                    preview_path = (
                        resolve_project_path(visual.thumbnail_path)
                        if visual.thumbnail_path
                        else None
                    )
                    if preview_path and preview_path.is_file():
                        with preview_path.open("rb") as preview_handle:
                            preview_suffix = _image_suffix_from_bytes(
                                preview_handle.read(16)
                            )
                    else:
                        preview_suffix = None
                    if preview_path and preview_suffix:
                        media_path = destination_stem.with_suffix(preview_suffix)
                        shutil.copy2(preview_path, media_path)
                        acquisition_warning = (
                            "full-resolution image was unavailable; using the cached "
                            "search preview for explicit editor review"
                        )
                    else:
                        raise ValueError(
                            f"image acquisition failed: {direct_error}; "
                            f"source-page resolution failed: {page_error}"
                        ) from page_error
    if visual.media_type == MediaType.image:
        media_path = _normalize_image_extension(media_path)
    metadata = media_metadata(media_path)
    width = metadata.get("width")
    height = metadata.get("height")
    eligible, fit_reason, quality_score = broadcast_media_fit(
        width, height, visual.media_type
    )
    thumbnail = create_thumbnail(
        media_path,
        visual_thumbnail_dir(episode.episode_id, visual.story_id) / visual.asset_id,
    )

    obsolete_warning = re.compile(
        r"(?:image|video) download failed|download rejected for broadcast layout|"
        r"video is a research lead only|"
        r"enable SYNTHPOST_SEARXNG_DOWNLOAD_VIDEOS|"
        r"yt-dlp completed without a supported video file|"
        r"requested format is not available|broadcast layout warning",
        re.IGNORECASE,
    )
    visual.warnings = [
        warning for warning in visual.warnings if not obsolete_warning.search(warning)
    ]
    if not eligible:
        visual.warnings.append(f"broadcast layout warning: {fit_reason}")
    if acquisition_warning:
        visual.warnings.append(acquisition_warning)
    visual.warnings = list(dict.fromkeys(visual.warnings))
    visual.download_path = project_relative(media_path)
    visual.quarantine_path = None
    visual.thumbnail_path = project_relative(thumbnail) if thumbnail else visual.thumbnail_path
    visual.mime_type = mimetypes.guess_type(media_path.name)[0]
    visual.width = width
    visual.height = height
    visual.duration_seconds = metadata.get("duration_seconds")
    visual.has_audio = (
        bool(metadata.get("audio_codec"))
        if visual.media_type == MediaType.video
        else False
    )
    visual.visual_quality_score = quality_score
    visual.content_cleanliness_status = "needs_review"
    visual.approval_blockers = []
    visual.content_analysis_evidence = []
    visual.rights_tier = RightsTier.yellow
    visual.rights_confidence = 0.0
    visual.usage_basis = "editor_manual_review_required"
    visual.manual_review_flag = True
    if acquired_new_copy:
        visual.review_status = ReviewStatus.suggested
        visual.reviewed_at = None
        visual.broadcast_fit_override = False
    repository.upsert_visual(visual)
    return visual


def approve_visual(
    repository,
    asset_id: str,
    *,
    manual: bool = False,
    attribution_text: str | None = None,
) -> VisualCandidate:
    visual = repository.get_visual(asset_id)
    if not visual.download_path:
        raise ValueError(
            "visual is a research lead without local media; download or stage a "
            "local file before approval"
        )
    if not resolve_project_path(visual.download_path).is_file():
        raise ValueError(f"visual media file is missing: {visual.download_path}")
    if (
        visual.media_type in {MediaType.image, MediaType.video}
        and config.get_settings().visuals.enforce_broadcast_fit
    ):
        eligible, fit_reason, _score = broadcast_media_fit(
            visual.width, visual.height, visual.media_type
        )
        if not eligible:
            if not manual:
                raise ValueError(
                    f"visual is not suitable for broadcast layouts: {fit_reason}"
                )
            visual.broadcast_fit_override = True
            visual.warnings = list(dict.fromkeys([
                *visual.warnings,
                "manual broadcast-fit override: "
                f"{fit_reason}; templates may crop or letterbox this asset",
            ]))
    if visual.rights_tier == RightsTier.red and manual:
        visual.rights_tier = RightsTier.yellow
        visual.rights_confidence = 0.0
        visual.usage_basis = "editor_manual_review_required"
        visual.approval_blockers = []
        visual.content_cleanliness_status = "passed"
    elif visual.rights_tier == RightsTier.red:
        raise ValueError("red-tier assets require explicit manual approval")
    if visual.rights_tier == RightsTier.yellow and not manual:
        raise ValueError("yellow-tier assets require manual approval")
    effective_attribution = (
        attribution_text if attribution_text is not None else visual.attribution_text
    )
    if visual.attribution_required and not (effective_attribution or "").strip():
        raise ValueError("an attribution is required before this visual can be approved")
    visual.review_status = (
        ReviewStatus.manual_approved if manual else ReviewStatus.approved
    )
    visual.reviewed_at = now_iso()
    visual.content_cleanliness_status = "passed"
    if attribution_text is not None:
        visual.attribution_text = attribution_text
    repository.upsert_visual(visual)
    return visual


def reject_visual(
    repository, asset_id: str, *, blocked: bool = False
) -> VisualCandidate:
    visual = repository.get_visual(asset_id)
    visual.review_status = ReviewStatus.blocked if blocked else ReviewStatus.rejected
    visual.reviewed_at = now_iso()
    repository.upsert_visual(visual)
    return visual


def update_visual(repository, asset_id: str, patch: dict) -> VisualCandidate:
    visual = repository.get_visual(asset_id)
    data = visual.model_dump(mode="json")
    normalized_patch = dict(patch)
    if normalized_patch.get("section_ids") is not None:
        normalized_patch["section_ids"] = _validated_section_ids(
            repository, visual.story_id, normalized_patch["section_ids"]
        )
    for key in ("motion", "section_ids", "content_role"):
        if normalized_patch.get(key) is None:
            normalized_patch.pop(key, None)
    data.update(normalized_patch)
    trim_start = data.get("trim_start")
    trim_end = data.get("trim_end")
    if data.get("content_role") == ContentRole.fallback.value:
        raise ValueError(
            "downloaded media cannot use the fallback content role; choose its editorial role"
        )
    if (
        trim_start is not None or trim_end is not None
    ) and visual.media_type != MediaType.video:
        raise ValueError("trim points can only be set on video visuals")
    if trim_start is not None and trim_end is not None and trim_end <= trim_start:
        raise ValueError("trim_end must be greater than trim_start")
    if (
        trim_end is not None
        and visual.duration_seconds is not None
        and trim_end > visual.duration_seconds
    ):
        raise ValueError(
            f"trim_end cannot exceed media duration ({visual.duration_seconds:.3f}s)"
        )
    if (
        visual.review_status in {ReviewStatus.approved, ReviewStatus.manual_approved}
        and visual.attribution_required
        and not (data.get("attribution_text") or "").strip()
    ):
        raise ValueError("an approved visual cannot have an empty attribution")
    updated = VisualCandidate.model_validate(data)
    repository.upsert_visual(updated)
    return updated
