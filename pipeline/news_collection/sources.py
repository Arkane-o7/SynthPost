from __future__ import annotations

import os
from dataclasses import dataclass

from .candidates import compact_text, normalize_category, normalize_source_name


@dataclass(frozen=True)
class FeedSource:
    source_id: str
    name: str
    url: str
    category: str
    reliability_tier: str = "medium"
    source_provider: str = "rss"
    source_type: str = "rss"


DEFAULT_FEED_SOURCES: tuple[FeedSource, ...] = (
    FeedSource("bbc_world", "BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "global", "high"),
    FeedSource("dw_world", "DW World", "https://rss.dw.com/rdf/rss-en-world", "global", "high"),
    FeedSource("firstpost_world", "Firstpost World", "https://www.firstpost.com/commonfeeds/v1/mfp/rss/world.xml", "geopolitics", "high"),
    FeedSource("firstpost_india", "Firstpost India", "https://www.firstpost.com/commonfeeds/v1/mfp/rss/india.xml", "india", "high"),
    FeedSource("pib_india", "PIB India", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", "india", "official"),
    FeedSource("the_verge", "The Verge", "https://www.theverge.com/rss/index.xml", "technology", "high"),
    FeedSource("ars_technica", "Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "technology", "high"),
    FeedSource("mit_tech_review_ai", "MIT Technology Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed", "ai", "high"),
    FeedSource("google_news_ai", "Google News AI", "https://news.google.com/rss/search?q=artificial%20intelligence%20OR%20AI%20chips&hl=en-US&gl=US&ceid=US:en", "ai", "medium"),
    FeedSource("cnbc_economy", "CNBC Economy", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "economy", "high"),
    FeedSource("cnbc_business", "CNBC Business", "https://www.cnbc.com/id/10001147/device/rss/rss.html", "business", "high"),
    FeedSource("energy_gov", "U.S. Department of Energy", "https://www.energy.gov/rss.xml", "energy", "official"),
    FeedSource("iea_news", "International Energy Agency", "https://www.iea.org/rss/news.xml", "energy", "high"),
    FeedSource("defense_gov", "U.S. Department of Defense", "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=20", "defense", "official"),
    FeedSource("dvids_news", "DVIDS", "https://www.dvidshub.net/rss/news", "defense", "official"),
    FeedSource("nasa_breaking", "NASA", "https://www.nasa.gov/rss/dyn/breaking_news.rss", "climate", "official"),
    FeedSource("noaa_news", "NOAA", "https://www.noaa.gov/rss.xml", "climate", "official"),
)


def feed_source_categories() -> set[str]:
    return {source.category for source in DEFAULT_FEED_SOURCES}


def configured_feed_sources() -> list[FeedSource]:
    raw = os.environ.get("SYNTHPOST_RSS_FEEDS", "")
    sources = _parse_feed_sources(raw) if raw else list(DEFAULT_FEED_SOURCES)
    category_filter = {
        item.strip().lower()
        for item in os.environ.get("SYNTHPOST_RSS_CATEGORIES", "").split(",")
        if item.strip()
    }
    if category_filter:
        sources = [source for source in sources if source.category.lower() in category_filter]
    return sources


def _parse_feed_sources(raw: str) -> list[FeedSource]:
    sources: list[FeedSource] = []
    for index, item in enumerate(raw.split(","), start=1):
        text = item.strip()
        if not text:
            continue
        parts = [part.strip() for part in text.split("|")]
        if len(parts) == 1:
            url = parts[0]
            name = normalize_source_name("", source_url=url)
            category = normalize_category("", source_url=url, source_name=name)
            tier = "unknown"
        elif len(parts) == 3:
            category, name, url = parts
            tier = "unknown"
        else:
            category, name, url, tier = (parts + ["unknown"])[:4]
        category = normalize_category(category, source_url=url, source_name=name)
        sources.append(
            FeedSource(
                source_id=f"custom_{index:02d}",
                name=normalize_source_name(name, source_url=url),
                url=compact_text(url),
                category=category,
                reliability_tier=compact_text(tier).lower() or "unknown",
            )
        )
    return sources
