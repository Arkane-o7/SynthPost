from __future__ import annotations

import html.parser
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..downloader import safe_filename
from ..models import AssetType, ProviderReport, StorySegment, VisualAsset, VisualProvider, VisualQuery
from ..query_builder import compact_text, tokenize, unique

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
PUBLIC_OR_OPEN_HOST_SUFFIXES = (
    ".gov",
    ".mil",
    ".int",
    "wikimedia.org",
    "wikipedia.org",
    "un.org",
    "who.int",
    "nasa.gov",
    "noaa.gov",
    "loc.gov",
)


class _MediaLinkParser(html.parser.HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value for key, value in attrs if value}
        if tag == "meta":
            key = (attrs_dict.get("property") or attrs_dict.get("name") or "").lower()
            if key in {"og:image", "twitter:image", "og:video", "twitter:player:stream"}:
                self._add(attrs_dict.get("content"), key)
        elif tag in {"img", "source", "video"}:
            self._add(attrs_dict.get("src") or attrs_dict.get("data-src"), tag)
        elif tag == "a":
            self._add(attrs_dict.get("href"), tag)

    def _add(self, value: str | None, role: str) -> None:
        if not value:
            return
        url = urllib.parse.urljoin(self.base_url, value)
        ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if ext in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            self.links.append((url, role))


class SourcePageProvider(VisualProvider):
    name = "official_source_media"

    def __init__(self, project_root: Path, *, max_assets: int = 6) -> None:
        self.project_root = project_root
        self.max_assets = max_assets

    def search(
        self,
        *,
        manifest: dict[str, Any],
        story_json_path: Path,
        segments: list[StorySegment],
        queries: list[VisualQuery],
    ) -> tuple[list[VisualAsset], ProviderReport]:
        raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
        source_url = compact_text(raw.get("source_url"))
        report = ProviderReport(provider=self.name, query_count=len(queries))
        if not source_url.startswith(("http://", "https://")):
            report.skipped_reason = "raw.source_url is not an HTTP URL"
            return [], report
        if os.environ.get("SYNTHPOST_DISABLE_SOURCE_PAGE_MEDIA", "0") == "1":
            report.skipped_reason = "SYNTHPOST_DISABLE_SOURCE_PAGE_MEDIA=1"
            return [], report

        try:
            links = self._extract_links(source_url)
        except Exception as exc:  # noqa: BLE001 - keep visual acquisition non-blocking.
            report.warnings.append(f"{source_url}: {exc}")
            return [], report

        host_is_open = self._host_is_open(source_url)
        assets: list[VisualAsset] = []
        seen: set[str] = set()
        for index, (url, role) in enumerate(links):
            if url in seen:
                continue
            seen.add(url)
            asset = self._asset(url, role=role, index=index, manifest=manifest, source_url=source_url, host_is_open=host_is_open)
            assets.append(asset)
            if len(assets) >= self.max_assets:
                break
        report.candidate_count = len(assets)
        if not assets:
            report.skipped_reason = "No direct renderable image/video media found on source page"
        return assets, report

    def _extract_links(self, source_url: str) -> list[tuple[str, str]]:
        request = urllib.request.Request(
            source_url,
            headers={"User-Agent": "SynthPostVisuals/0.1 (+local-first news pipeline)"},
        )
        with urllib.request.urlopen(request, timeout=18) as response:
            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type:
                return [(source_url, "source_url")]
            html = response.read(2_000_000).decode("utf-8", errors="ignore")
        parser = _MediaLinkParser(source_url)
        parser.feed(html)
        return parser.links

    def _asset(
        self,
        url: str,
        *,
        role: str,
        index: int,
        manifest: dict[str, Any],
        source_url: str,
        host_is_open: bool,
    ) -> VisualAsset:
        raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
        ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
        title = compact_text(raw.get("headline_source") or raw.get("summary") or f"Source page media {index + 1}")
        source_name = compact_text(raw.get("source_name") or urllib.parse.urlparse(source_url).hostname or "Official Source")
        usage_note = (
            "Direct media discovered on a public/open official source page. Verify embedded third-party credits before upload."
            if host_is_open
            else "Source page media lead only. Not selected automatically because reuse rights are not established."
        )
        keywords = unique(
            [
                *tokenize(title),
                *tokenize(raw.get("category")),
                *tokenize(source_name),
                *tokenize(urllib.parse.urlparse(source_url).hostname or ""),
            ],
            limit=24,
        )
        return VisualAsset(
            asset_id=safe_filename(f"official_source_{index + 1:02d}_{Path(urllib.parse.urlparse(url).path).stem}"),
            asset_type=AssetType.VIDEO if ext in VIDEO_EXTENSIONS else AssetType.IMAGE,
            title=title,
            provider=self.name,
            remote_url=url,
            source_url=source_url,
            source_name=source_name,
            license="public/open official source" if host_is_open else None,
            usage_note=usage_note,
            attribution=f"Source: {source_name}",
            story_id=str(manifest.get("story_id") or ""),
            keywords=keywords,
            safe_to_use=host_is_open,
            fallback_reason=None if host_is_open else "rights_review_required",
            extra={"visual_role": "official_source_page", "source_page_role": role},
        )

    def _host_is_open(self, url: str) -> bool:
        if os.environ.get("SYNTHPOST_TRUST_SOURCE_PAGE_MEDIA", "0") == "1":
            return True
        host = (urllib.parse.urlparse(url).hostname or "").lower().removeprefix("www.")
        return any(host == suffix or host.endswith(suffix) for suffix in PUBLIC_OR_OPEN_HOST_SUFFIXES)
