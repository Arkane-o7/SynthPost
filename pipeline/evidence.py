from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import read_manifest, write_manifest


def compact_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def split_sentences(value: object) -> list[str]:
    text = compact_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if len(part.split()) >= 6]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": "source_01",
        "name": compact_text(raw.get("source_name") or "Unknown source"),
        "url": compact_text(raw.get("source_url")),
        "title": compact_text(raw.get("headline_source") or raw.get("summary")),
        "published_at": compact_text(raw.get("published_at")),
        "source_type": compact_text(raw.get("source_type") or "primary"),
        "retrieved_at": _utc_now(),
    }


def _normalize_sources(raw: dict[str, Any]) -> list[dict[str, Any]]:
    existing = raw.get("sources")
    sources: list[dict[str, Any]] = []
    if isinstance(existing, list):
        for index, item in enumerate(existing, start=1):
            if not isinstance(item, dict):
                continue
            source = dict(item)
            source["source_id"] = compact_text(source.get("source_id")) or f"source_{index:02d}"
            source["name"] = compact_text(source.get("name") or source.get("source_name") or raw.get("source_name"))
            source["url"] = compact_text(source.get("url") or source.get("source_url") or raw.get("source_url"))
            source["title"] = compact_text(source.get("title") or raw.get("headline_source"))
            source["published_at"] = compact_text(source.get("published_at") or raw.get("published_at"))
            source["source_type"] = compact_text(source.get("source_type") or "primary")
            source["retrieved_at"] = compact_text(source.get("retrieved_at") or _utc_now())
            sources.append({key: value for key, value in source.items() if value not in ("", None, [], {})})
    if not sources:
        source = _source_from_raw(raw)
        sources.append({key: value for key, value in source.items() if value not in ("", None, [], {})})
    return sources


def _claim_texts_from_raw(raw: dict[str, Any]) -> list[str]:
    facts = raw.get("facts")
    texts: list[str] = []
    if isinstance(facts, list):
        texts.extend(compact_text(fact) for fact in facts if compact_text(fact))
    if not texts:
        texts.extend(compact_text(item) for item in [raw.get("summary"), raw.get("headline_source")] if compact_text(item))
    seen: set[str] = set()
    unique_texts: list[str] = []
    for text in texts:
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_texts.append(text)
    return unique_texts


def _claim_from_text(index: int, text: str, source: dict[str, Any]) -> dict[str, Any]:
    source_id = compact_text(source.get("source_id") or "source_01")
    source_url = compact_text(source.get("url"))
    return {
        "claim_id": f"claim_{index:02d}",
        "text": text,
        "source_ids": [source_id],
        "evidence": [
            {
                "source_id": source_id,
                "url": source_url,
                "quote": text,
            }
        ],
        "confidence": "source_reported",
        "status": "supported",
    }


def _normalize_claims(raw: dict[str, Any], sources: list[dict[str, Any]], *, force: bool = False) -> list[dict[str, Any]]:
    existing = raw.get("claims")
    source = sources[0] if sources else {"source_id": "source_01"}
    source_ids = {compact_text(item.get("source_id")) for item in sources if isinstance(item, dict)}
    if isinstance(existing, list) and existing and not force:
        claims: list[dict[str, Any]] = []
        for index, item in enumerate(existing, start=1):
            if not isinstance(item, dict):
                continue
            text = compact_text(item.get("text") or item.get("claim") or item.get("quote"))
            if not text:
                continue
            claim = dict(item)
            claim["claim_id"] = compact_text(claim.get("claim_id")) or f"claim_{index:02d}"
            claim["text"] = text
            ids = claim.get("source_ids")
            if not isinstance(ids, list) or not ids:
                ids = [compact_text(source.get("source_id") or "source_01")]
            claim["source_ids"] = [compact_text(value) for value in ids if compact_text(value) in source_ids] or [
                compact_text(source.get("source_id") or "source_01")
            ]
            evidence = claim.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                claim["evidence"] = [
                    {
                        "source_id": claim["source_ids"][0],
                        "url": compact_text(source.get("url")),
                        "quote": text,
                    }
                ]
            claim["confidence"] = compact_text(claim.get("confidence") or "source_reported")
            claim["status"] = compact_text(claim.get("status") or "supported")
            claims.append({key: value for key, value in claim.items() if value not in ("", None, [], {})})
        if claims:
            return claims
    return [_claim_from_text(index, text, source) for index, text in enumerate(_claim_texts_from_raw(raw), start=1)]


def build_evidence_summary(sources: list[dict[str, Any]], claims: list[dict[str, Any]]) -> dict[str, Any]:
    unsupported = [claim.get("claim_id") for claim in claims if claim.get("status") not in {"supported", "verified"}]
    return {
        "source_count": len(sources),
        "claim_count": len(claims),
        "unsupported_claim_ids": unsupported,
        "status": "ready" if sources and claims and not unsupported else "needs_review",
    }


def normalize_manifest(manifest: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    raw = manifest.get("raw")
    if not isinstance(raw, dict):
        raise ValueError("Story manifest is missing raw source material.")
    raw = dict(raw)
    sources = _normalize_sources(raw)
    claims = _normalize_claims(raw, sources, force=force)
    raw["sources"] = sources
    raw["claims"] = claims
    raw["evidence_summary"] = build_evidence_summary(sources, claims)
    manifest["raw"] = raw
    return manifest


def _claim_map(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    claims = raw.get("claims") if isinstance(raw.get("claims"), list) else []
    return {
        compact_text(claim.get("claim_id")): claim
        for claim in claims
        if isinstance(claim, dict) and compact_text(claim.get("claim_id"))
    }


def _source_ids_for_claims(raw: dict[str, Any], claim_ids: list[str]) -> list[str]:
    claims = _claim_map(raw)
    seen: set[str] = set()
    result: list[str] = []
    for claim_id in claim_ids:
        claim = claims.get(claim_id)
        if not claim:
            continue
        for source_id in claim.get("source_ids", []):
            source_id = compact_text(source_id)
            if source_id and source_id not in seen:
                seen.add(source_id)
                result.append(source_id)
    return result


def normalize_script_claim_ids(script: dict[str, Any]) -> list[str]:
    raw_ids = script.get("claim_ids")
    if not isinstance(raw_ids, list):
        raw_claims = script.get("claims")
        if isinstance(raw_claims, list):
            raw_ids = [
                item.get("claim_id") if isinstance(item, dict) else item
                for item in raw_claims
            ]
        else:
            raw_ids = []
    seen: set[str] = set()
    claim_ids: list[str] = []
    for value in raw_ids:
        claim_id = compact_text(value)
        if claim_id and claim_id not in seen:
            seen.add(claim_id)
            claim_ids.append(claim_id)
    return claim_ids


def validate_script(script: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    claim_ids = normalize_script_claim_ids(script)
    known_claims = _claim_map(raw)
    unknown_claim_ids = [claim_id for claim_id in claim_ids if claim_id not in known_claims]
    warnings: list[str] = []
    if not compact_text(script.get("text")):
        warnings.append("script.text is empty")
    if not claim_ids:
        warnings.append("script does not cite claim_ids")
    if unknown_claim_ids:
        warnings.append("script cites unknown claim_ids")
    status = "pass" if not warnings else "needs_review"
    return {
        "status": status,
        "claim_ids": [claim_id for claim_id in claim_ids if claim_id in known_claims],
        "source_ids": _source_ids_for_claims(raw, [claim_id for claim_id in claim_ids if claim_id in known_claims]),
        "unknown_claim_ids": unknown_claim_ids,
        "sentence_count": len(split_sentences(script.get("text"))),
        "warnings": warnings,
    }


def attach_script_evidence(script: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    review = validate_script(script, raw)
    script = dict(script)
    script["claim_ids"] = review["claim_ids"]
    script["source_ids"] = review["source_ids"]
    script["evidence_summary"] = {
        "status": review["status"],
        "claim_count": len(review["claim_ids"]),
        "source_count": len(review["source_ids"]),
        "warnings": review["warnings"],
    }
    return script


def run(story_json_path: str | Path, *, force: bool = False) -> dict[str, Any]:
    manifest = normalize_manifest(read_manifest(story_json_path), force=force)
    write_manifest(story_json_path, manifest)
    print(
        "[evidence] Indexed "
        f"{manifest['raw']['evidence_summary']['claim_count']} claim(s) from "
        f"{manifest['raw']['evidence_summary']['source_count']} source(s)."
    )
    return manifest["raw"]
