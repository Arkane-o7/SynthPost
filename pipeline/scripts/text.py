"""Deterministic script text shaping shared by contracts and generation."""

from __future__ import annotations

import re


def section_overlay_text(text: str, section_type: str, *, max_chars: int) -> str:
    """Create a concise overlay for legacy or manually authored scripts."""

    normalized = " ".join(text.split()).strip(" \t\n\r-–—")
    if not normalized:
        normalized = section_type.replace("_", " ").title()
    first_sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0]
    first_sentence = first_sentence.rstrip(".!?").strip()
    if len(first_sentence) <= max_chars:
        return first_sentence
    shortened = first_sentence[: max_chars + 1].rsplit(" ", 1)[0].rstrip(" ,;:-–—")
    return shortened or first_sentence[:max_chars].rstrip()


def narration_beats(text: str, *, max_words: int = 24) -> list[str]:
    """Split narration into stable sentence/clause beats for timed overlays."""

    normalized = " ".join(text.split()).strip()
    if not normalized:
        return []
    protected: dict[str, str] = {}

    def protect_abbreviation(match: re.Match[str]) -> str:
        token = f"__ABBR_{len(protected)}__"
        protected[token] = match.group(0)
        return token

    sentence_safe = re.sub(r"\b(?:[A-Z]\.){2,}", protect_abbreviation, normalized)
    sentences = re.split(r"(?<=[.!?])\s+", sentence_safe)
    sentences = [
        _restore_abbreviations(sentence, protected).strip()
        for sentence in sentences
        if sentence.strip()
    ]
    beats: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        if len(words) <= max_words:
            beats.append(sentence)
            continue
        clauses = [
            clause.strip()
            for clause in re.split(
                r"(?<=[;:])\s+|\s+[—–]\s+|,\s+(?=(?:and|but|while|which|as)\b)",
                sentence,
                flags=re.IGNORECASE,
            )
            if clause.strip()
        ]
        if len(clauses) == 1:
            clauses = [
                " ".join(words[index : index + max_words])
                for index in range(0, len(words), max_words)
            ]
        beats.extend(clauses)
    merged: list[str] = []
    for beat in beats:
        if merged and len(beat.split()) < 5:
            merged[-1] = f"{merged[-1]} {beat}".strip()
        else:
            merged.append(beat)
    return merged


def _restore_abbreviations(text: str, protected: dict[str, str]) -> str:
    for token, abbreviation in protected.items():
        text = text.replace(token, abbreviation)
    return text


def normalize_section_headline_cues(
    text: str,
    section_type: str,
    provided: list[str] | tuple[str, ...] = (),
) -> list[str]:
    """Return one concise headline per narration beat in spoken order."""

    beats = narration_beats(text)
    if not beats:
        return [section_overlay_text(text, section_type, max_chars=80)]
    cleaned = [
        section_overlay_text(str(value), section_type, max_chars=80)
        for value in provided
        if str(value).strip()
    ]
    if len(cleaned) == len(beats):
        return cleaned
    return [section_overlay_text(beat, section_type, max_chars=80) for beat in beats]


def timed_section_headline_cues(
    text: str,
    section_type: str,
    provided: list[str] | tuple[str, ...],
    duration: float,
) -> list[dict[str, float | str]]:
    """Align section headlines to narration using spoken-word proportions."""

    beats = narration_beats(text)
    headlines = normalize_section_headline_cues(text, section_type, provided)
    if not beats:
        beats = [text or section_type.replace("_", " ")]
    weights = [max(1, len(beat.split())) for beat in beats]
    total_weight = max(1, sum(weights))
    cursor = 0
    cues: list[dict[str, float | str]] = []
    for index, (headline, weight) in enumerate(zip(headlines, weights)):
        start = duration * cursor / total_weight
        cursor += weight
        end = duration if index == len(headlines) - 1 else duration * cursor / total_weight
        cues.append(
            {
                "text": headline,
                "start": round(start, 3),
                "end": round(max(start + 0.01, end), 3),
            }
        )
    return cues
