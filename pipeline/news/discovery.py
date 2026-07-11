from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pipeline import config
from pipeline.discovery.discover import canonicalize_url
from pipeline.models import StoryCandidate
from pipeline.search.searxng_client import search


class NewsCoverageAngle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    angle_name: str
    articles: list[dict[str, Any]] = Field(default_factory=list)


class NewsCoverage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    story_id: str
    angles: list[NewsCoverageAngle] = Field(default_factory=list)


def discover_news(candidate: StoryCandidate) -> NewsCoverage:
    title = candidate.title or ""
    if not title:
        return NewsCoverage(story_id=candidate.story_id or candidate.candidate_id)

    limit = max(
        1, int(config.env("SYNTHPOST_SEARXNG_NEWS_RESULTS", "12") or "12")
    )
    results = search(
        title,
        categories=["news"],
        time_range=config.env("SYNTHPOST_SEARXNG_NEWS_TIME_RANGE", "month"),
        limit=limit,
    )

    primary_angle = NewsCoverageAngle(angle_name="Primary Coverage")
    alternate_angle = NewsCoverageAngle(angle_name="Alternate Coverage")

    seen_urls: set[str] = set()
    for res in results:
        canonical_url = canonicalize_url(res.url) or res.url
        if canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)

        article = {
            "title": res.title,
            "url": canonical_url,
            "source": res.source_domain or res.engine,
            "engine": res.engine,
            "published_at": res.published_date,
            "snippet": res.snippet,
        }

        # Simple heuristic to split into primary/alternate based on title similarity
        # A more advanced version would use embedding similarities
        story_words = {word for word in title.lower().split() if len(word) > 3}
        result_words = {word for word in res.title.lower().split() if len(word) > 3}
        words_in_common = story_words & result_words
        if len(words_in_common) >= 3:
            primary_angle.articles.append(article)
        else:
            alternate_angle.articles.append(article)

    angles: list[NewsCoverageAngle] = []
    if primary_angle.articles:
        angles.append(primary_angle)
    if alternate_angle.articles:
        angles.append(alternate_angle)

    return NewsCoverage(
        story_id=candidate.story_id or candidate.candidate_id, angles=angles
    )
