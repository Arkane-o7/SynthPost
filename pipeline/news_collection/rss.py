from __future__ import annotations

import os
import re
import urllib.request
import xml.etree.ElementTree as ET

from .candidates import CandidateStory, build_candidate_story, compact_text, normalize_category


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def feed_urls() -> list[str]:
    raw = os.environ.get(
        "SYNTHPOST_RSS_FEEDS",
        "https://www.theverge.com/rss/index.xml,https://www.firstpost.com/commonfeeds/v1/mfp/rss/world.xml",
    )
    return [item.strip() for item in raw.split(",") if item.strip()]


def _first_text(item: ET.Element, names: list[str]) -> str:
    for name in names:
        value = item.findtext(name)
        if value:
            return value
    return ""


def parse_feed(data: bytes | str, *, url: str) -> list[CandidateStory]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    channel = root.find("channel")
    source_name = channel.findtext("title", default=url) if channel is not None else url
    items = root.findall(".//item")
    candidates: list[CandidateStory] = []
    for item in items:
        title = strip_html(item.findtext("title", default=""))
        summary = strip_html(item.findtext("description", default=""))
        link = compact_text(item.findtext("link", default=url))
        published = _first_text(item, ["pubDate", "published", "updated"])
        item_category = strip_html(item.findtext("category", default=""))
        if not title:
            continue
        category = normalize_category(item_category, source_url=link or url, source_name=source_name)
        candidates.append(
            build_candidate_story(
                headline=title,
                summary=summary,
                source_url=link or url,
                source_name=source_name,
                category=category,
                published_at=published,
                source_provider="rss",
                source_type="rss",
                feed_url=url,
            )
        )
    return candidates


def fetch_feed(url: str) -> list[CandidateStory]:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return parse_feed(response.read(), url=url)
    except (OSError, TimeoutError, ET.ParseError, ValueError):
        return []


def collect(limit: int = 3) -> list[CandidateStory]:
    stories: list[CandidateStory] = []
    seen: set[str] = set()
    for url in feed_urls():
        try:
            feed_stories = fetch_feed(url)
        except Exception:
            feed_stories = []
        for story in feed_stories:
            key = story.normalized_headline
            if key in seen:
                continue
            seen.add(key)
            stories.append(story)
            if len(stories) >= limit:
                return stories
    return stories
