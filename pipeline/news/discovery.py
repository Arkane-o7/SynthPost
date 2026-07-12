from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from pipeline import config
from pipeline.discovery.discover import (
    canonicalize_url,
    discover_from_source,
    freshness_score,
)
from pipeline.models import StoryCandidate
from pipeline.search.searxng_client import (
    SearXNGResult,
    configured as searxng_configured,
    search,
)


STOP_WORDS = {
    "about",
    "after",
    "against",
    "amid",
    "and",
    "are",
    "but",
    "for",
    "from",
    "has",
    "have",
    "into",
    "its",
    "latest",
    "more",
    "new",
    "news",
    "not",
    "over",
    "says",
    "that",
    "the",
    "their",
    "this",
    "through",
    "under",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "why",
    "with",
}


class NewsCoverageAngle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    angle_name: str
    articles: list[dict[str, Any]] = Field(default_factory=list)


class NewsCoverage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    story_id: str
    queries: list[str] = Field(default_factory=list)
    angles: list[NewsCoverageAngle] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def significant_terms(*values: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        for term in re.findall(r"[a-z0-9]+", value.lower()):
            if len(term) < 3 or term in STOP_WORDS or term in seen:
                continue
            seen.add(term)
            terms.append(term)
    return terms


def research_queries(candidate: StoryCandidate) -> list[str]:
    """Build complementary exact-headline and topic-focused search queries."""

    title = " ".join(candidate.title.split()).strip()
    if not title:
        return []
    title_terms = significant_terms(title)
    summary_terms = significant_terms(candidate.summary)
    category_terms = significant_terms(candidate.category.replace("_", " "))
    focused_terms = [*title_terms[:8]]
    for term in summary_terms:
        if term not in focused_terms and len(focused_terms) < 10:
            focused_terms.append(term)
    topic_terms = [*category_terms, *title_terms[:6]]

    candidates = [
        title,
        " ".join(focused_terms),
        " ".join(dict.fromkeys(topic_terms)),
    ]
    queries: list[str] = []
    seen: set[str] = set()
    for query in candidates:
        normalized = " ".join(query.split()).strip()
        key = normalized.casefold()
        if len(normalized.split()) < 2 or key in seen:
            continue
        seen.add(key)
        queries.append(normalized)
    return queries


def related_article_score(
    candidate: StoryCandidate,
    *,
    title: str,
    snippet: str = "",
    published_at: str | None = None,
) -> float:
    """Score whether a result covers the selected headline and wider topic."""

    headline_terms = set(significant_terms(candidate.title))
    topic_terms = set(
        significant_terms(candidate.title, candidate.summary, candidate.category)
    )
    result_title_terms = set(significant_terms(title))
    result_terms = set(significant_terms(title, snippet))
    headline_overlap = len(headline_terms & result_title_terms) / max(
        1, min(8, len(headline_terms))
    )
    topic_overlap = len(topic_terms & result_terms) / max(
        1, min(12, len(topic_terms))
    )
    title_similarity = SequenceMatcher(
        None, candidate.title.casefold(), title.casefold()
    ).ratio()
    score = (
        headline_overlap * 0.52
        + topic_overlap * 0.18
        + title_similarity * 0.20
        + freshness_score(published_at) * 0.10
    )
    return round(min(1.0, score), 4)


def _article_from_searxng(
    candidate: StoryCandidate, result: SearXNGResult, query: str
) -> dict[str, Any]:
    canonical_url = canonicalize_url(result.url) or result.url
    return {
        "title": result.title,
        "url": canonical_url,
        "source": result.source_domain or result.engine,
        "engine": result.engine,
        "published_at": result.published_date,
        "snippet": result.snippet,
        "query": query,
        "discovery_method": "searxng",
        "relevance_score": related_article_score(
            candidate,
            title=result.title,
            snippet=result.snippet,
            published_at=result.published_date,
        ),
    }


def _articles_from_feed(source, candidate: StoryCandidate) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    for result in discover_from_source(source):
        if not result.canonical_url:
            continue
        articles.append(
            {
                "title": result.title,
                "url": result.canonical_url,
                "source": result.source_name,
                "engine": "rss",
                "published_at": result.published_at,
                "snippet": result.summary,
                "query": candidate.title,
                "discovery_method": "rss_related_coverage",
                "relevance_score": related_article_score(
                    candidate,
                    title=result.title,
                    snippet=result.summary,
                    published_at=result.published_at,
                ),
            }
        )
    return articles


def _publisher_key(article: dict[str, Any]) -> str:
    source = str(article.get("source") or "").strip().casefold()
    if source:
        return source
    url = str(article.get("url") or "")
    return (urlsplit(url).hostname or url).casefold()


def diversified_articles(
    articles: list[dict[str, Any]], *, limit: int
) -> list[dict[str, Any]]:
    """Prefer one relevant article per publisher before allowing repeats."""

    if limit <= 0:
        return []
    by_url: dict[str, dict[str, Any]] = {}
    for article in articles:
        canonical_url = canonicalize_url(article.get("url"))
        if not canonical_url:
            continue
        normalized = {**article, "url": canonical_url}
        existing = by_url.get(canonical_url)
        if existing is None or float(normalized.get("relevance_score") or 0) > float(
            existing.get("relevance_score") or 0
        ):
            by_url[canonical_url] = normalized
    ranked = sorted(
        by_url.values(),
        key=lambda article: (
            -float(article.get("relevance_score") or 0),
            str(article.get("published_at") or ""),
            str(article.get("title") or ""),
        ),
    )
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    publishers: set[str] = set()
    for article in ranked:
        publisher = _publisher_key(article)
        if publisher and publisher in publishers:
            deferred.append(article)
            continue
        selected.append(article)
        if publisher:
            publishers.add(publisher)
        if len(selected) >= limit:
            return selected
    for article in deferred:
        selected.append(article)
        if len(selected) >= limit:
            break
    return selected


def discover_news(candidate: StoryCandidate, repository=None) -> NewsCoverage:
    """Find multi-source coverage using headline/topic queries and RSS fallback."""

    queries = research_queries(candidate)
    if not queries:
        return NewsCoverage(story_id=candidate.story_id or candidate.candidate_id)

    warnings: list[str] = []
    articles: list[dict[str, Any]] = []
    result_limit = max(
        1, int(config.env("SYNTHPOST_SEARXNG_NEWS_RESULTS", "12") or "12")
    )
    per_query_limit = max(4, (result_limit + len(queries) - 1) // len(queries))
    rss_source_limit = max(
        0, int(config.env("SYNTHPOST_RESEARCH_RSS_SOURCE_LIMIT", "10") or "10")
    )
    sources = (
        repository.list_sources(enabled=True)[:rss_source_limit]
        if repository is not None and rss_source_limit
        else []
    )

    futures: dict[Any, tuple[str, Any]] = {}
    max_workers = max(1, min(8, len(queries) + len(sources)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        if searxng_configured():
            for query in queries:
                future = executor.submit(
                    search,
                    query,
                    categories=["news"],
                    time_range=config.env(
                        "SYNTHPOST_SEARXNG_NEWS_TIME_RANGE", "month"
                    ),
                    limit=per_query_limit,
                )
                futures[future] = ("searxng", query)
        for source in sources:
            future = executor.submit(_articles_from_feed, source, candidate)
            futures[future] = ("rss", source.name)

        for future in as_completed(futures):
            method, label = futures[future]
            try:
                values = future.result()
                if method == "searxng":
                    articles.extend(
                        _article_from_searxng(candidate, result, str(label))
                        for result in values
                    )
                else:
                    articles.extend(values)
            except Exception as exc:
                warnings.append(f"{method} research source {label} failed: {exc}")

    lead_url = canonicalize_url(candidate.canonical_url)
    minimum_relevance = config.env_float(
        "SYNTHPOST_RESEARCH_MIN_RELEVANCE", 0.22
    )
    relevant = [
        article
        for article in articles
        if canonicalize_url(article.get("url")) != lead_url
        and float(article.get("relevance_score") or 0) >= minimum_relevance
    ]
    ranked = diversified_articles(relevant, limit=max(result_limit, 12))
    primary = [
        article for article in ranked if float(article["relevance_score"]) >= 0.45
    ]
    alternate = [
        article for article in ranked if float(article["relevance_score"]) < 0.45
    ]
    angles: list[NewsCoverageAngle] = []
    if primary:
        angles.append(
            NewsCoverageAngle(angle_name="Direct Headline Coverage", articles=primary)
        )
    if alternate:
        angles.append(
            NewsCoverageAngle(angle_name="Related Topic Coverage", articles=alternate)
        )
    return NewsCoverage(
        story_id=candidate.story_id or candidate.candidate_id,
        queries=queries,
        angles=angles,
        warnings=warnings,
    )
