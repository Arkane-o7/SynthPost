from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..downloader import safe_filename
from ..models import AssetType, ProviderReport, StorySegment, VisualAsset, VisualProvider, VisualQuery

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OPEN_LICENSE_HINTS = ("public domain", "cc0", "cc-by", "cc by", "creative commons", "own work")


class WikimediaProvider(VisualProvider):
    name = "wikimedia"

    def __init__(self, project_root: Path, *, per_query: int = 3) -> None:
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
        if os.environ.get("SYNTHPOST_DISABLE_WEB_VISUALS", "0") == "1":
            return [], ProviderReport(provider=self.name, skipped_reason="SYNTHPOST_DISABLE_WEB_VISUALS=1")

        report = ProviderReport(provider=self.name, query_count=len(queries))
        assets: list[VisualAsset] = []
        seen: set[str] = set()
        for query in queries:
            search_query = self._commons_query(query)
            try:
                results = self._search_commons(search_query)
            except Exception as exc:  # noqa: BLE001 - provider should degrade, not fail the pipeline.
                report.warnings.append(f"{search_query}: {exc}")
                continue
            for item in results:
                if not self._is_renderable_item(item):
                    continue
                asset = self._asset_from_item(item, query)
                key = asset.identity_key()
                if key in seen:
                    continue
                seen.add(key)
                assets.append(asset)
        report.candidate_count = len(assets)
        return assets, report

    def _commons_query(self, query: VisualQuery) -> str:
        terms = [query.query, *query.keywords[:4]]
        text = " ".join(term for term in terms if term)
        return re.sub(r"\s+", " ", text).strip()

    def _search_commons(self, query: str) -> list[dict[str, Any]]:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrlimit": str(self.per_query),
            "gsrsearch": query,
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
        }
        url = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": "SynthPostVisuals/0.1"})
        with urllib.request.urlopen(request, timeout=18) as response:
            data = json.loads(response.read().decode("utf-8"))
        pages = (data.get("query") or {}).get("pages") or {}
        return [page for page in pages.values() if page.get("imageinfo")]

    def _is_renderable_item(self, item: dict[str, Any]) -> bool:
        info = item["imageinfo"][0]
        mime = str(info.get("mime") or "")
        url = str(info.get("url") or "")
        if not (mime.startswith("image/") or mime.startswith("video/")):
            return False
        return not urllib.parse.urlparse(url).path.lower().endswith(".pdf")

    def _asset_from_item(self, item: dict[str, Any], query: VisualQuery) -> VisualAsset:
        info = item["imageinfo"][0]
        metadata = info.get("extmetadata") or {}
        title = str(item.get("title") or "Wikimedia media").replace("File:", "")
        mime = str(info.get("mime") or "")
        asset_type = AssetType.VIDEO if mime.startswith("video/") else self._infer_image_type(title)
        license_name = self._metadata_value(metadata, "LicenseShortName") or self._metadata_value(metadata, "UsageTerms")
        usage_note = self._metadata_value(metadata, "UsageTerms")
        artist = self._clean_html(self._metadata_value(metadata, "Artist"))
        credit = self._clean_html(self._metadata_value(metadata, "Credit"))
        attribution = credit or artist
        safe_to_use = self._is_open_license(" ".join(part for part in [license_name, usage_note] if part))
        source_url = info.get("descriptionurl")
        return VisualAsset(
            asset_id=safe_filename(f"commons_{item.get('pageid', title)}"),
            asset_type=asset_type,
            title=title,
            provider=self.name,
            remote_url=info.get("url"),
            source_url=source_url,
            source_name="Wikimedia Commons",
            license=license_name,
            usage_note=usage_note or "Open-license metadata from Wikimedia Commons; verify attribution before upload.",
            attribution=attribution,
            keywords=query.keywords,
            safe_to_use=safe_to_use,
            width=info.get("width"),
            height=info.get("height"),
            extra={"commons_pageid": item.get("pageid")},
        )

    def _metadata_value(self, metadata: dict[str, Any], key: str) -> str | None:
        value = metadata.get(key)
        if isinstance(value, dict):
            return self._clean_html(str(value.get("value") or "")) or None
        return self._clean_html(str(value or "")) or None

    def _clean_html(self, value: str | None) -> str:
        if not value:
            return ""
        text = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", html.unescape(text)).strip()

    def _is_open_license(self, text: str) -> bool:
        lowered = text.lower()
        if "fair use" in lowered or "non-free" in lowered:
            return False
        return any(hint in lowered for hint in OPEN_LICENSE_HINTS)

    def _infer_image_type(self, title: str) -> AssetType:
        lowered = title.lower()
        if "map" in lowered:
            return AssetType.MAP
        if "chart" in lowered or "graph" in lowered:
            return AssetType.CHART
        if "satellite" in lowered:
            return AssetType.SATELLITE
        if "document" in lowered or "order" in lowered or "statement" in lowered:
            return AssetType.DOCUMENT
        return AssetType.IMAGE
