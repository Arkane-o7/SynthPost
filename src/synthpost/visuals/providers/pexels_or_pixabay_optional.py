from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..downloader import safe_filename
from ..models import AssetType, ProviderReport, StorySegment, VisualAsset, VisualProvider, VisualQuery


class PexelsPixabayProvider(VisualProvider):
    name = "pexels_pixabay_optional"

    def __init__(self, project_root: Path, *, per_query: int = 2) -> None:
        self.project_root = project_root
        self.per_query = per_query

    def search(
        self,
        *,
        manifest: dict[str, Any],
        story_json_path: Path,
        segments: list[StorySegment],
        queries: list[VisualQuery],
    ) -> tuple[list[VisualAsset], ProviderReport]:
        report = ProviderReport(provider=self.name, query_count=len(queries))
        assets: list[VisualAsset] = []
        pexels_key = os.environ.get("SYNTHPOST_PEXELS_API_KEY") or os.environ.get("PEXELS_API_KEY")
        pixabay_key = os.environ.get("SYNTHPOST_PIXABAY_API_KEY") or os.environ.get("PIXABAY_API_KEY")
        if not pexels_key and not pixabay_key:
            report.skipped_reason = "PEXELS_API_KEY/PIXABAY_API_KEY not configured"
            return [], report

        for query in queries:
            if pexels_key:
                assets.extend(self._pexels(query, pexels_key, report))
            if pixabay_key:
                assets.extend(self._pixabay(query, pixabay_key, report))
        report.candidate_count = len(assets)
        return assets, report

    def _pexels(self, query: VisualQuery, api_key: str, report: ProviderReport) -> list[VisualAsset]:
        params = urllib.parse.urlencode({"query": query.query, "per_page": self.per_query, "orientation": "landscape"})
        url = f"https://api.pexels.com/videos/search?{params}"
        request = urllib.request.Request(url, headers={"Authorization": api_key, "User-Agent": "SynthPostVisuals/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=18) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            report.warnings.append(f"Pexels query failed: {exc}")
            return []
        assets: list[VisualAsset] = []
        for video in data.get("videos", [])[: self.per_query]:
            files = sorted(
                video.get("video_files", []),
                key=lambda item: (item.get("width") or 0) * (item.get("height") or 0),
                reverse=True,
            )
            if not files:
                continue
            chosen = files[0]
            assets.append(
                VisualAsset(
                    asset_id=safe_filename(f"pexels_{video.get('id')}"),
                    asset_type=AssetType.VIDEO,
                    title=f"Pexels video {video.get('id')}",
                    provider="pexels",
                    remote_url=chosen.get("link"),
                    source_url=video.get("url"),
                    source_name="Pexels",
                    license="Pexels License",
                    usage_note="Pexels API result; attribution not required by Pexels but recommended in credits.",
                    attribution=(((video.get("user") or {}).get("name")) or "Pexels"),
                    keywords=query.keywords,
                    safe_to_use=True,
                    width=chosen.get("width"),
                    height=chosen.get("height"),
                    duration_seconds=video.get("duration"),
                )
            )
        return assets

    def _pixabay(self, query: VisualQuery, api_key: str, report: ProviderReport) -> list[VisualAsset]:
        params = urllib.parse.urlencode({"key": api_key, "q": query.query, "per_page": self.per_query, "safesearch": "true"})
        url = f"https://pixabay.com/api/videos/?{params}"
        try:
            with urllib.request.urlopen(url, timeout=18) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            report.warnings.append(f"Pixabay query failed: {exc}")
            return []
        assets: list[VisualAsset] = []
        for video in data.get("hits", [])[: self.per_query]:
            videos = video.get("videos") or {}
            chosen = videos.get("large") or videos.get("medium") or videos.get("small")
            if not chosen:
                continue
            assets.append(
                VisualAsset(
                    asset_id=safe_filename(f"pixabay_{video.get('id')}"),
                    asset_type=AssetType.VIDEO,
                    title=str(video.get("tags") or f"Pixabay video {video.get('id')}"),
                    provider="pixabay",
                    remote_url=chosen.get("url"),
                    source_url=f"https://pixabay.com/videos/id-{video.get('id')}/",
                    source_name="Pixabay",
                    license="Pixabay Content License",
                    usage_note="Pixabay API result; review current Pixabay license terms before monetized upload.",
                    attribution=video.get("user"),
                    keywords=query.keywords,
                    safe_to_use=True,
                    width=chosen.get("width"),
                    height=chosen.get("height"),
                    duration_seconds=video.get("duration"),
                )
            )
        return assets

