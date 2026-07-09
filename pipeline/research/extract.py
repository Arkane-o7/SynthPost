from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pipeline.models import (
    Claim,
    EvidenceItem,
    ResearchPack,
    SourceDocument,
    StoryWorkflowState,
)
from pipeline.workflow import can_transition


class ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip = False
        self.parts: list[str] = []
        self.title: str = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header"}:
            self.skip = True
        if tag == "title":
            self._in_title = True
        if tag in {"p", "h1", "h2", "h3", "li", "blockquote"} and not self.skip:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header"}:
            self.skip = False
        if tag == "title":
            self._in_title = False
        if tag in {"p", "h1", "h2", "h3", "li", "blockquote"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title += text + " "
        if not self.skip:
            self.parts.append(text + " ")

    def readable_text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


BOILERPLATE_PATTERNS = [
    r"\bsubscribe\b",
    r"\bsign in\b",
    r"\bskip to\b",
    r"\baccessibility help\b",
    r"\bsearch close\b",
    r"\bunlock this article\b",
    r"\bcomplete digital access\b",
    r"\bcancel anytime\b",
    r"\btrial\b",
    r"\bpremium digital\b",
    r"\bstandard digital\b",
    r"\bnewsletters\b",
]


def boilerplate_hits(text: str) -> int:
    value = text.lower()
    return sum(1 for pattern in BOILERPLATE_PATTERNS if re.search(pattern, value))


def clean_extracted_text(text: str) -> str:
    sentences = sentence_split(text)
    if not sentences:
        return text.strip()
    cleaned = [
        sentence
        for sentence in sentences
        if boilerplate_hits(sentence) == 0 and len(sentence.split()) >= 6
    ]
    return " ".join(cleaned).strip() or text.strip()


def fetch_url_text(url: str, *, timeout: float = 16.0) -> tuple[str, str, list[str]]:
    request = Request(
        url, headers={"User-Agent": "SynthPostStudio/2.0 local editorial tool"}
    )
    warnings: list[str] = []
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read(2_500_000)
    if "html" not in content_type and not raw.lstrip().startswith(b"<"):
        warnings.append(f"non-html content type: {content_type or 'unknown'}")
    decoded = raw.decode("utf-8", errors="replace")
    parser = ReadableHTMLParser()
    parser.feed(decoded)
    text = parser.readable_text()
    title = re.sub(r"\s+", " ", parser.title).strip()
    return title, text, warnings


def sentence_split(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) > 30]


def extract_numbers(text: str) -> list[str]:
    return sorted(
        set(
            re.findall(
                r"\b(?:\$|₹|€|£)?\d+(?:\.\d+)?\s?(?:%|million|billion|trillion|crore|lakh|GW|MW|km|miles|years?)?\b",
                text,
                flags=re.I,
            )
        )
    )


def extract_dates(text: str) -> list[str]:
    patterns = [
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
        r"\b20\d{2}\b",
    ]
    values: set[str] = set()
    for pattern in patterns:
        values.update(re.findall(pattern, text, flags=re.I))
    return sorted(values)


def extract_entities(text: str) -> tuple[list[str], list[str], list[str]]:
    candidates = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b", text)
    stop = {
        "The",
        "This",
        "That",
        "A",
        "An",
        "In",
        "On",
        "For",
        "With",
        "From",
        "By",
        "As",
        "At",
        "It",
        "But",
    }
    clean = [
        item for item in candidates if item.split()[0] not in stop and len(item) > 3
    ]
    people = sorted(set(item for item in clean if len(item.split()) >= 2))
    org_keywords = (
        "Agency",
        "Commission",
        "Court",
        "Ministry",
        "Department",
        "Company",
        "Inc",
        "Ltd",
        "Bank",
        "University",
        "Institute",
        "Council",
        "Government",
    )
    organizations = sorted(set(item for item in clean if item.endswith(org_keywords)))
    locations = sorted(
        set(
            item
            for item in clean
            if item
            in {
                "India",
                "China",
                "United States",
                "Europe",
                "Russia",
                "Ukraine",
                "Delhi",
                "Mumbai",
                "Bengaluru",
                "Washington",
                "London",
                "Paris",
                "Tokyo",
            }
        )
    )
    return people, organizations, locations


def source_document_from_candidate(candidate) -> SourceDocument:
    warnings: list[str] = []
    if candidate.manual_body:
        title = candidate.title
        text = candidate.manual_body
        url = candidate.canonical_url
    elif candidate.canonical_url:
        try:
            title, text, warnings = fetch_url_text(candidate.canonical_url)
            title = title or candidate.title
            raw_text = text
            text = clean_extracted_text(raw_text)
            if candidate.summary and (
                len(text) < 300 or boilerplate_hits(raw_text) >= 3
            ):
                text = f"{candidate.title}. {candidate.summary}".strip()
                warnings.append(
                    "article extraction looked paywalled/boilerplate-heavy; using feed title and summary"
                )
            elif len(text) < 300:
                warnings.append(
                    "extracted text is short; article may be paywalled, script-heavy, or blocked"
                )
        except Exception as exc:
            title = candidate.title
            text = candidate.summary or candidate.title
            warnings.append(f"article fetch failed: {exc}")
        url = candidate.canonical_url
    else:
        title = candidate.title
        text = candidate.summary or candidate.title
        url = None
        warnings.append(
            "manual/custom topic has no URL; evidence is editor-provided text only"
        )
    publisher = candidate.source_name
    return SourceDocument(
        story_id=candidate.story_id or candidate.candidate_id,
        url=url,
        title=title,
        publisher=publisher,
        author=candidate.author,
        published_at=candidate.published_at,
        content_text=text,
        content_hash=sha256_text(text),
        document_type="manual_story" if candidate.manual_body else "article",
        primary_source=False,
        extraction_status="extracted" if text else "failed",
        warnings=warnings,
    )


def build_research_pack(repository, story_id: str) -> ResearchPack:
    candidate = repository.candidate_for_story(story_id)
    document = source_document_from_candidate(candidate)
    repository.upsert_source_document(document)
    sentences = sentence_split(document.content_text)
    evidence: list[EvidenceItem] = []
    claims: list[Claim] = []
    for index, sentence in enumerate(sentences, start=1):
        evidence_item = EvidenceItem(
            evidence_id=f"ev_{index:03d}",
            document_id=document.document_id,
            excerpt=sentence[:500],
            location=f"sentence:{index}",
            url=document.url,
        )
        claim = Claim(
            claim_id=f"claim_{index:03d}",
            claim_text=sentence,
            evidence_ids=[evidence_item.evidence_id],
            confidence=0.72 if document.extraction_status == "extracted" else 0.45,
            claim_type="fact",
            supported=bool(sentence),
            notes="Extracted deterministically from source document.",
        )
        evidence.append(evidence_item)
        claims.append(claim)
    people, organizations, locations = extract_entities(document.content_text)
    numbers = extract_numbers(document.content_text)
    dates = extract_dates(document.content_text)
    summary_sentences = sentences[:4] or [candidate.summary or candidate.title]
    pack = ResearchPack(
        story_id=story_id,
        documents=[document],
        evidence=evidence,
        claims=claims,
        people=people,
        organizations=organizations,
        locations=locations,
        numbers=numbers,
        dates=dates,
        contradictions=[],
        uncertainties=document.warnings,
        research_summary=" ".join(summary_sentences)[:1200],
    )
    repository.upsert_research_pack(pack)
    if candidate.workflow_state in {
        StoryWorkflowState.selected,
        StoryWorkflowState.researching,
    }:
        if candidate.workflow_state == StoryWorkflowState.selected:
            repository.transition_story(story_id, StoryWorkflowState.researching)
        repository.transition_story(story_id, StoryWorkflowState.research_ready)
    return pack


def approve_research_pack(repository, story_id: str) -> ResearchPack:
    data = repository.latest_research_pack(story_id)
    if not data:
        raise ValueError(f"No research pack exists for story: {story_id}")
    pack = ResearchPack.model_validate(data)
    pack.status = "approved"
    repository.upsert_research_pack(pack)
    return pack
