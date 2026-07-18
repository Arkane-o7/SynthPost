"""Hermes-backed discovery and research services with SynthPost-owned contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from pipeline import config
from pipeline.agents.hermes import HermesClient
from pipeline.discovery.assignment_desk import apply_assignment_desk
from pipeline.discovery.discover import (
    canonicalize_url,
    detect_language,
    duplicate_group,
    score_candidate,
)
from pipeline.editorial.charter import CHARTER_VERSION, load_editorial_charter
from pipeline.models import (
    Claim,
    EvidenceItem,
    ResearchPack,
    SourceDefinition,
    SourceDocument,
    SourceType,
    StoryCandidate,
    StoryWorkflowState,
    new_id,
)
from pipeline.research.extract import sha256_text, source_document_from_candidate


Progress = Callable[[float, str], None]
CancelCheck = Callable[[], None]


def _public_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return canonicalize_url(text)


def _iso_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _discovery_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["stories"],
        "properties": {
            "stories": {
                "type": "array",
                "minItems": 1,
                "maxItems": 30,
                "items": {
                    "type": "object",
                    "required": [
                        "title",
                        "url",
                        "publisher",
                        "published_at",
                        "category",
                        "summary",
                        "why_it_matters",
                        "supporting_sources",
                        "confidence",
                    ],
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "publisher": {"type": "string"},
                        "published_at": {"type": ["string", "null"]},
                        "category": {"type": "string"},
                        "summary": {"type": "string"},
                        "why_it_matters": {"type": "string"},
                        "supporting_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "confidence": {"type": "number"},
                        "thumbnail_url": {"type": ["string", "null"]},
                    },
                },
            }
        },
    }


def discover_with_hermes(
    repository,
    *,
    episode_id: str | None = None,
    category: str | None = None,
    progress_callback: Progress | None = None,
    cancel_check: CancelCheck | None = None,
    idempotency_key: str | None = None,
) -> list[StoryCandidate]:
    settings = config.get_settings()
    sources = repository.list_sources(enabled=True, category=category)
    source_context = [
        {
            "name": source.name,
            "category": source.category,
            "homepage_url": source.homepage_url,
            "feed_url": source.feed_url,
            "priority": source.priority,
            "reliability": source.reliability_score,
        }
        for source in sources
    ]
    today = datetime.now(timezone.utc).date().isoformat()
    prompt = f"""
Act as SynthPost's assignment desk. Search the current web for consequential,
well-sourced news ideas suitable for a visual narrated explainer. Today is
{today}. Prefer developments from the last 72 hours, but include an older story
only when a material update occurred recently.

Focus: {category or 'technology, science, infrastructure, energy, business and geopolitics'}.
Find distinct events, not multiple headlines about one event. Reject product
fluff, opinion without a development, celebrity content, routine personnel
moves, and stories without enough evidence for research. Do not invent an India
connection. supporting_sources must contain publisher names or source URLs that
you actually encountered. Every story URL must be a real source page.

Configured SynthPost sources are useful starting points, not an allowlist:
{json.dumps(source_context, ensure_ascii=True)}
""".strip()
    client = HermesClient()

    def agent_progress(status: str, _: dict[str, Any]) -> None:
        if progress_callback:
            progress_callback(0.15 if status == "running" else 0.85, f"Hermes discovery: {status}")

    raw, _state = client.run_json(
        prompt,
        _discovery_schema(),
        session_id=f"synthpost-discovery-{episode_id or 'global'}-{today}",
        idempotency_key=idempotency_key,
        progress_callback=agent_progress,
        cancel_check=cancel_check,
    )
    rows = raw.get("stories")
    if not isinstance(rows, list):
        raise ValueError("Hermes discovery result requires a stories array")
    candidates: list[StoryCandidate] = []
    seen_urls: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = _public_url(row.get("url"))
        title = " ".join(str(row.get("title") or "").split())
        summary = " ".join(str(row.get("summary") or "").split())
        publisher = " ".join(str(row.get("publisher") or "Hermes discovery").split())
        if not url or not title or url in seen_urls:
            continue
        seen_urls.add(url)
        source = SourceDefinition(
            source_id="src_hermes_discovery",
            name=publisher,
            source_type=SourceType.custom_url,
            category=str(row.get("category") or category or "general"),
            priority=70,
            reliability_score=0.65,
            custom=True,
        )
        published_at = _iso_date(row.get("published_at"))
        scores, final, reasons = score_candidate(
            source, title, summary, published_at
        )
        confidence = max(0.0, min(1.0, float(row.get("confidence") or 0.0)))
        candidate = StoryCandidate(
            candidate_id="cand_"
            + hashlib.sha1(f"hermes:{episode_id or 'global'}:{url}".encode()).hexdigest()[:12],
            title=title,
            canonical_url=url,
            source_id=source.source_id,
            source_name=publisher,
            published_at=published_at,
            category=source.category,
            summary=summary[:1200],
            thumbnail_url=_public_url(row.get("thumbnail_url")),
            language=detect_language(f"{title} {summary}"),
            scores=scores,
            final_score=round(final * 0.7 + confidence * 0.3, 3),
            score_reasons=[
                *reasons,
                "Hermes web discovery confidence=" + f"{confidence:.2f}",
                "Hermes rationale: " + str(row.get("why_it_matters") or "")[:500],
            ],
            duplicate_group_id=duplicate_group(title, url),
            supporting_sources=[
                str(item)[:300]
                for item in row.get("supporting_sources", [])
                if str(item).strip()
            ][:12],
            assignment_summary=str(row.get("why_it_matters") or "")[:800],
            assignment_confidence=confidence,
            episode_id=episode_id,
        )
        candidates.append(candidate)
    if not candidates:
        raise ValueError("Hermes discovery returned no valid public story URLs")
    if progress_callback:
        progress_callback(0.92, f"validating and ranking {len(candidates)} Hermes stories")
    return apply_assignment_desk(repository, candidates, use_ai=False)


def _research_schema() -> dict[str, Any]:
    source = {
        "type": "object",
        "required": [
            "source_key", "url", "title", "publisher", "published_at",
            "primary_source", "content_text",
        ],
        "properties": {
            "source_key": {"type": "string"},
            "url": {"type": "string"},
            "title": {"type": "string"},
            "publisher": {"type": ["string", "null"]},
            "author": {"type": ["string", "null"]},
            "published_at": {"type": ["string", "null"]},
            "primary_source": {"type": "boolean"},
            "content_text": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "required": [
            "research_queries", "documents", "evidence", "claims",
            "contradictions", "uncertainties", "research_summary",
        ],
        "properties": {
            "research_queries": {"type": "array", "items": {"type": "string"}},
            "documents": {"type": "array", "minItems": 1, "items": source},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["evidence_key", "source_key", "excerpt", "url"],
                    "properties": {
                        "evidence_key": {"type": "string"},
                        "source_key": {"type": "string"},
                        "excerpt": {"type": "string"},
                        "url": {"type": ["string", "null"]},
                    },
                },
            },
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "claim_text", "evidence_keys", "confidence", "claim_type"
                    ],
                    "properties": {
                        "claim_text": {"type": "string"},
                        "evidence_keys": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "number"},
                        "claim_type": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                },
            },
            "people": {"type": "array", "items": {"type": "string"}},
            "organizations": {"type": "array", "items": {"type": "string"}},
            "locations": {"type": "array", "items": {"type": "string"}},
            "numbers": {"type": "array", "items": {"type": "string"}},
            "dates": {"type": "array", "items": {"type": "string"}},
            "contradictions": {"type": "array", "items": {"type": "string"}},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
            "systems": {"type": "array", "items": {"type": "string"}},
            "stakeholders": {"type": "array", "items": {"type": "string"}},
            "trade_offs": {"type": "array", "items": {"type": "string"}},
            "execution_gaps": {"type": "array", "items": {"type": "string"}},
            "editorial_questions": {"type": "array", "items": {"type": "string"}},
            "research_summary": {"type": "string"},
        },
    }


def _strings(raw: dict[str, Any], key: str, limit: int = 30) -> list[str]:
    value = raw.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:800] for item in value if str(item).strip()][:limit]


def build_research_pack_with_hermes(
    repository,
    story_id: str,
    *,
    progress_callback: Progress | None = None,
    cancel_check: CancelCheck | None = None,
    idempotency_key: str | None = None,
) -> ResearchPack:
    candidate = repository.candidate_for_story(story_id)
    lead = source_document_from_candidate(candidate)
    settings = config.get_settings()
    charter = load_editorial_charter()
    prompt = f"""
Research this selected SynthPost story as a meticulous newsroom researcher.
Use web search and extraction to locate independent coverage and authoritative
primary sources. Prefer current, original documents over summaries. Separate
confirmed facts from claims, projections and analysis. Record contradictions
and uncertainty explicitly. Never create a URL, quotation, statistic or date.

Selected story:
{json.dumps({
    'title': candidate.title,
    'url': candidate.canonical_url,
    'summary': candidate.summary,
    'category': candidate.category,
    'initial_source_text': lead.content_text[:5000],
}, ensure_ascii=True)}

Research lens:
{json.dumps(charter['research_lens'], ensure_ascii=True)}

Return at most {settings.search.research_max_documents} high-value documents.
content_text must contain the useful extracted facts or a faithful source
summary, not navigation or subscription boilerplate. Every evidence item must
refer to a returned source_key, and every supported claim must cite one or more
returned evidence_keys.
""".strip()
    client = HermesClient()

    def agent_progress(status: str, _: dict[str, Any]) -> None:
        if progress_callback:
            progress_callback(0.15 if status == "running" else 0.85, f"Hermes research: {status}")

    raw, _state = client.run_json(
        prompt,
        _research_schema(),
        session_id=f"synthpost-research-{story_id}-{new_id('revision')}",
        idempotency_key=idempotency_key,
        progress_callback=agent_progress,
        cancel_check=cancel_check,
    )
    source_map: dict[str, SourceDocument] = {}
    for row in raw.get("documents", []):
        if not isinstance(row, dict):
            continue
        key = str(row.get("source_key") or "").strip()
        url = _public_url(row.get("url"))
        title = " ".join(str(row.get("title") or "").split())
        content = " ".join(str(row.get("content_text") or "").split())
        if not key or key in source_map or not url or not title or len(content) < 80:
            continue
        source_map[key] = SourceDocument(
            story_id=story_id,
            url=url,
            title=title,
            publisher=str(row.get("publisher") or "").strip() or None,
            author=str(row.get("author") or "").strip() or None,
            published_at=_iso_date(row.get("published_at")),
            content_text=content[:20_000],
            content_hash=sha256_text(content),
            document_type="hermes_research_source",
            primary_source=bool(row.get("primary_source")),
            discovery_method="hermes_web_research",
            relevance_score=1.0,
            extraction_status="extracted",
            warnings=[],
        )
    if not source_map:
        raise ValueError("Hermes research returned no valid source documents")

    evidence_map: dict[str, EvidenceItem] = {}
    for row in raw.get("evidence", []):
        if not isinstance(row, dict):
            continue
        key = str(row.get("evidence_key") or "").strip()
        source = source_map.get(str(row.get("source_key") or "").strip())
        excerpt = " ".join(str(row.get("excerpt") or "").split())
        if not key or key in evidence_map or source is None or len(excerpt) < 20:
            continue
        evidence_map[key] = EvidenceItem(
            document_id=source.document_id,
            excerpt=excerpt[:1000],
            url=source.url,
            location="Hermes extracted evidence",
        )
    if not evidence_map:
        raise ValueError("Hermes research returned no evidence linked to its sources")

    claims: list[Claim] = []
    for row in raw.get("claims", []):
        if not isinstance(row, dict):
            continue
        text = " ".join(str(row.get("claim_text") or "").split())
        evidence_ids = [
            evidence_map[key].evidence_id
            for key in row.get("evidence_keys", [])
            if key in evidence_map
        ]
        if not text or not evidence_ids:
            continue
        confidence = max(0.0, min(1.0, float(row.get("confidence") or 0.0)))
        claims.append(
            Claim(
                claim_text=text[:1200],
                evidence_ids=list(dict.fromkeys(evidence_ids)),
                confidence=confidence,
                claim_type=str(row.get("claim_type") or "fact")[:80],
                supported=True,
                notes=str(row.get("notes") or "Hermes evidence-linked research")[:500],
            )
        )
    if not claims:
        raise ValueError("Hermes research returned no evidence-supported claims")

    pack = ResearchPack(
        story_id=story_id,
        documents=list(source_map.values()),
        research_queries=_strings(raw, "research_queries"),
        evidence=list(evidence_map.values()),
        claims=claims,
        people=_strings(raw, "people"),
        organizations=_strings(raw, "organizations"),
        locations=_strings(raw, "locations"),
        numbers=_strings(raw, "numbers"),
        dates=_strings(raw, "dates"),
        contradictions=_strings(raw, "contradictions"),
        uncertainties=_strings(raw, "uncertainties"),
        systems=_strings(raw, "systems"),
        stakeholders=_strings(raw, "stakeholders"),
        trade_offs=_strings(raw, "trade_offs"),
        execution_gaps=_strings(raw, "execution_gaps"),
        editorial_questions=_strings(raw, "editorial_questions"),
        charter_version=CHARTER_VERSION,
        research_summary=str(raw.get("research_summary") or "").strip()[:2000],
    )
    for document in pack.documents:
        repository.upsert_source_document(document)
    repository.upsert_research_pack(pack)
    if candidate.workflow_state in {
        StoryWorkflowState.selected,
        StoryWorkflowState.researching,
    }:
        if candidate.workflow_state == StoryWorkflowState.selected:
            repository.transition_story(story_id, StoryWorkflowState.researching)
        repository.transition_story(story_id, StoryWorkflowState.research_ready)
    return pack
