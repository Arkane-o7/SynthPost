from __future__ import annotations

import re

from .models import ThumbnailBrief


NOISE = {
    "breaking",
    "exclusive",
    "alert",
    "huge",
    "the",
    "a",
    "an",
    "to",
    "of",
    "and",
    "in",
    "on",
    "for",
}


def words(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9$%.'’]+", value.upper())


def word_count(value: str) -> int:
    return len(words(value))


def fit_headline(value: str, *, max_words: int = 5) -> str:
    tokens = [token for token in words(value) if token.lower().strip("'’") not in NOISE]
    if not tokens:
        tokens = words(value)
    return " ".join(tokens[:max_words])


def accent_words(headline: str, emotion: str) -> list[str]:
    tokens = words(headline)
    if not tokens:
        return []
    for token in tokens:
        if token.startswith("$") or token[0].isdigit() or token in {"AI", "GPT", "GPU", "CHIP", "STOCK", "BAN", "RISK"}:
            return [token]
    if emotion in {"urgent", "warning", "shocking", "conflict"}:
        for token in tokens:
            if token in {"WARNING", "RISK", "BAN", "CRASH", "PRESSURE", "SHOCK"}:
                return [token]
    return [tokens[-1]]


def subject_name(brief: ThumbnailBrief, subject_type: str) -> str | None:
    for subject in brief.main_subjects:
        if subject.type == subject_type:
            return subject.name
    return None


def default_headlines(brief: ThumbnailBrief) -> list[str]:
    if brief.approved_thumbnail_text:
        return [fit_headline(text, max_words=6) for text in brief.approved_thumbnail_text]

    person = subject_name(brief, "person")
    company = subject_name(brief, "company") or subject_name(brief, "model") or subject_name(brief, "product")
    country = subject_name(brief, "country")
    number = brief.key_numbers[0]["value"] if brief.key_numbers and isinstance(brief.key_numbers[0], dict) else None

    candidates: list[str] = []
    if brief.emotion in {"urgent", "warning", "shocking"} and person:
        last = person.split()[-1].upper()
        candidates.append(f"{last}'S AI WARNING")
    if brief.emotion in {"conflict", "urgent"} and company:
        candidates.append(f"{company} UNDER PRESSURE")
    if number:
        if brief.topic.lower() in {"infrastructure", "ai", "technology"}:
            candidates.append(f"{number} COMPUTE RACE")
        else:
            candidates.append(f"{number} STRATEGIC BET")
    if country and brief.topic.lower() in {"geopolitics", "economy", "infrastructure", "policy"}:
        candidates.append(f"{country} HITS TOP 5")
    if company:
        candidates.append(f"INSIDE {company}'S MOVE")
    candidates.append(fit_headline(brief.episode_headline or brief.video_title, max_words=5))

    forbidden = {text.upper() for text in brief.forbidden_thumbnail_text}
    cleaned: list[str] = []
    for candidate in candidates:
        text = fit_headline(candidate, max_words=6)
        if text and text.upper() not in forbidden and text not in cleaned:
            cleaned.append(text)
    return cleaned
