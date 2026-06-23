from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

from ..models import AssetType, ProviderReport, StorySegment, VisualAsset, VisualProvider, VisualQuery


class WebSearchProvider(VisualProvider):
    name = "web_search"

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def search(
        self,
        *,
        manifest: dict[str, Any],
        story_json_path: Path,
        segments: list[StorySegment],
        queries: list[VisualQuery],
    ) -> tuple[list[VisualAsset], ProviderReport]:
        report = ProviderReport(
            provider=self.name,
            query_count=len(queries),
            skipped_reason="metadata-only provider; does not scrape copyrighted media",
        )
        assets: list[VisualAsset] = []
        for query in queries:
            url = "https://www.google.com/search?" + urllib.parse.urlencode({"tbm": "isch", "q": query.query})
            assets.append(
                VisualAsset(
                    asset_id=f"web_lead_{query.segment_id}",
                    asset_type=AssetType.PLACEHOLDER,
                    title=f"Rights review lead: {query.query}",
                    provider=self.name,
                    source_url=url,
                    source_name="Web image search",
                    usage_note="Search lead only. No media downloaded because rights are unknown.",
                    story_id=str(manifest.get("story_id", "")),
                    segment_id=query.segment_id,
                    keywords=query.keywords,
                    safe_to_use=False,
                    fallback_reason="rights_review_required",
                )
            )
        report.candidate_count = len(assets)
        return assets, report

