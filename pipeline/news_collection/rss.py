from __future__ import annotations

import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateStory:
    headline_source: str
    summary: str
    source_url: str
    source_name: str
    category: str
    published_at: str
    facts: list[str]


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def feed_urls() -> list[str]:
    raw = os.environ.get(
        "SYNTHPOST_RSS_FEEDS",
        "https://www.theverge.com/rss/index.xml,https://www.firstpost.com/commonfeeds/v1/mfp/rss/world.xml",
    )
    return [item.strip() for item in raw.split(",") if item.strip()]


def fetch_feed(url: str) -> list[CandidateStory]:
    with urllib.request.urlopen(url, timeout=20) as response:
        root = ET.fromstring(response.read())
    channel = root.find("channel")
    source_name = channel.findtext("title", default=url) if channel is not None else url
    items = root.findall(".//item")
    candidates: list[CandidateStory] = []
    for item in items:
        title = strip_html(item.findtext("title", default=""))
        summary = strip_html(item.findtext("description", default=""))
        link = item.findtext("link", default=url)
        published = item.findtext("pubDate", default="")
        if not title:
            continue
        candidates.append(
            CandidateStory(
                headline_source=title,
                summary=summary,
                source_url=link,
                source_name=source_name,
                category="general",
                published_at=published,
                facts=[summary] if summary else [title],
            )
        )
    return candidates


def collect(limit: int = 3) -> list[CandidateStory]:
    stories: list[CandidateStory] = []
    seen: set[str] = set()
    for url in feed_urls():
        for story in fetch_feed(url):
            key = story.headline_source.lower()
            if key in seen:
                continue
            seen.add(key)
            stories.append(story)
            if len(stories) >= limit:
                return stories
    return stories
