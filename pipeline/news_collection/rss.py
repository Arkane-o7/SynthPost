from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .cache import fetch_url
from .candidates import CandidateStory, build_candidate_story, clean_fact_text, compact_text, normalize_category
from .dedupe import dedupe_candidates
from .sources import FeedSource, configured_feed_sources


def strip_html(value: str) -> str:
    return clean_fact_text(value)


def feed_sources() -> list[FeedSource]:
    return configured_feed_sources()


def feed_urls() -> list[str]:
    return [source.url for source in feed_sources()]


def _local_name(tag: object) -> str:
    text = str(tag)
    return text.rsplit("}", 1)[-1] if "}" in text else text


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _first_element(element: ET.Element, names: list[str]) -> ET.Element | None:
    for name in names:
        for child in _children(element, name):
            return child
    return None


def _first_text(element: ET.Element, names: list[str]) -> str:
    child = _first_element(element, names)
    if child is None:
        return ""
    return strip_html("".join(child.itertext()))


def _feed_title(root: ET.Element, *, fallback: str) -> str:
    channel = _first_element(root, ["channel"])
    if channel is not None:
        title = _first_text(channel, ["title"])
        if title:
            return title
    return _first_text(root, ["title"]) or fallback


def _feed_items(root: ET.Element) -> list[ET.Element]:
    return [element for element in root.iter() if _local_name(element.tag) in {"item", "entry"}]


def _item_title(item: ET.Element) -> str:
    return _first_text(item, ["title"])


def _item_summary(item: ET.Element) -> str:
    values = [
        _first_text(item, ["description"]),
        _first_text(item, ["summary"]),
        _first_text(item, ["encoded"]),
        _first_text(item, ["content"]),
    ]
    return strip_html(" ".join(value for value in values if value))


def _item_link(item: ET.Element, *, fallback: str) -> str:
    text_link = _first_text(item, ["link"])
    if text_link and re.match(r"^https?://", text_link):
        return text_link
    for link in _children(item, "link"):
        href = compact_text(link.attrib.get("href", ""))
        if href:
            return href
    guid = _first_text(item, ["guid", "id"])
    if guid and re.match(r"^https?://", guid):
        return guid
    return fallback


def _item_category(item: ET.Element) -> str:
    category = _first_element(item, ["category"])
    if category is None:
        return ""
    return strip_html(category.attrib.get("term", "") or "".join(category.itertext()))


def parse_feed(data: bytes | str, *, url: str, source: FeedSource | None = None) -> list[CandidateStory]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    source_name = source.name if source else _feed_title(root, fallback=url)
    feed_category = source.category if source else normalize_category("", source_url=url, source_name=source_name)
    reliability_tier = source.reliability_tier if source else "unknown"
    items = _feed_items(root)
    candidates: list[CandidateStory] = []
    for item in items:
        title = _item_title(item)
        summary = _item_summary(item)
        link = _item_link(item, fallback=url)
        published = _first_text(item, ["pubDate", "published", "updated", "date"])
        item_category = _item_category(item) or feed_category
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
                source_provider=source.source_provider if source else "rss",
                source_type=source.source_type if source else "rss",
                source_category=feed_category,
                feed_url=url,
                source_reliability_tier=reliability_tier,
            )
        )
    return candidates


def fetch_feed(source_or_url: FeedSource | str) -> list[CandidateStory]:
    source = source_or_url if isinstance(source_or_url, FeedSource) else None
    url = source.url if source else str(source_or_url)
    try:
        return parse_feed(fetch_url(url), url=url, source=source)
    except (OSError, TimeoutError, ET.ParseError, ValueError):
        return []


def collect(limit: int = 3) -> list[CandidateStory]:
    stories: list[CandidateStory] = []
    for source in feed_sources():
        try:
            stories.extend(fetch_feed(source))
        except Exception:
            continue
    deduped = dedupe_candidates(stories)
    return deduped[:limit]
