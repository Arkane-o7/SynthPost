from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any

from .. import evidence
from ..provenance import artifact_record, record_story_artifact
from ..storage import read_manifest, write_manifest


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def writing_input_for(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("raw", {}) if isinstance(manifest.get("raw"), dict) else {}
    handoff = raw.get("handoff") if isinstance(raw.get("handoff"), dict) else {}
    writing = handoff.get("writing") if isinstance(handoff.get("writing"), dict) else {}
    editorial = raw.get("editorial") if isinstance(raw.get("editorial"), dict) else {}
    selected = raw.get("selected_candidate") if isinstance(raw.get("selected_candidate"), dict) else {}
    return {
        "candidate_id": writing.get("candidate_id") or selected.get("candidate_id") or editorial.get("candidate_id"),
        "headline": writing.get("headline") or raw.get("headline_source", ""),
        "category": writing.get("category") or raw.get("category", ""),
        "summary": writing.get("summary") or raw.get("summary", ""),
        "facts": _string_list(writing.get("facts")) or _string_list(raw.get("facts")),
        "claims": _dict_list(writing.get("claims")) or _dict_list(raw.get("claims")),
        "claim_ids": _string_list(writing.get("claim_ids")) or [
            str(claim.get("claim_id"))
            for claim in _dict_list(raw.get("claims"))
            if claim.get("claim_id")
        ],
        "entities": _string_list(writing.get("entities")) or _string_list(raw.get("entities") or raw.get("key_entities")),
        "sources": _dict_list(writing.get("sources")) or _dict_list(raw.get("sources")),
        "source_metadata": writing.get("source_metadata") if isinstance(writing.get("source_metadata"), dict) else raw.get("source_metadata", {}),
        "why_it_matters": writing.get("why_it_matters") or editorial.get("why_it_matters", ""),
        "synthpost_angle": writing.get("synthpost_angle") or editorial.get("synthpost_angle") or editorial.get("possible_synthpost_angle", ""),
        "audience_curiosity_angle": writing.get("audience_curiosity_angle") or editorial.get("audience_curiosity_angle", ""),
        "explainability_notes": writing.get("explainability_notes") or editorial.get("explainability_notes", ""),
        "score_reasons": writing.get("score_reasons") if isinstance(writing.get("score_reasons"), dict) else editorial.get("score_reasons", {}),
        "scores": writing.get("scores") if isinstance(writing.get("scores"), dict) else editorial.get("scores", {}),
        "selection_reason": writing.get("selection_reason") or editorial.get("selection_reason", ""),
    }


def prompt_for(manifest: dict[str, Any]) -> str:
    writing_input = writing_input_for(manifest)
    sources = writing_input["sources"]
    claims = writing_input["claims"]
    source_lines = "\n".join(
        f"- {source.get('source_id')}: {source.get('name')} ({source.get('url', 'no url')})"
        for source in sources
        if isinstance(source, dict)
    )
    claim_lines = "\n".join(
        f"- {claim.get('claim_id')}: {claim.get('text')}"
        for claim in claims
        if isinstance(claim, dict)
    )
    fact_lines = "\n".join(f"- {fact}" for fact in writing_input["facts"])
    entity_line = ", ".join(writing_input["entities"])
    score_reason_lines = "\n".join(
        f"- {key}: {value}"
        for key, value in (writing_input.get("score_reasons") or {}).items()
        if value
    )
    return (
        "Return exactly one valid compact JSON object for a grounded YouTube news script.\n"
        "Do not write markdown, comments, prose outside JSON, or duplicate JSON keys.\n"
        "Required keys exactly once: text, headline, category, claim_ids, source_ids, caveats.\n"
        "Use only the supplied source summary and claim ledger. Do not fabricate claims.\n"
        "Every factual assertion in text must be supported by one of the supplied claim_ids.\n"
        "Do not infer consequences, causes, risks, impacts, or forecasts beyond the claim text.\n"
        "If the ledger is small, shorter copy is better than unsupported filler.\n"
        "Keep text concise: 25 to 90 words, direct international news desk tone.\n\n"
        f"Candidate ID: {writing_input.get('candidate_id') or ''}\n"
        f"Headline: {writing_input.get('headline', '')}\n"
        f"Category: {writing_input.get('category', '')}\n"
        f"Summary: {writing_input.get('summary', '')}\n"
        f"Entities: {entity_line}\n"
        f"Why it matters: {writing_input.get('why_it_matters') or ''}\n"
        f"SynthPost angle: {writing_input.get('synthpost_angle') or ''}\n"
        f"Audience curiosity angle: {writing_input.get('audience_curiosity_angle') or ''}\n"
        f"Explainability notes: {writing_input.get('explainability_notes') or ''}\n"
        f"Selection reason: {writing_input.get('selection_reason') or ''}\n"
        f"Facts:\n{fact_lines}\n"
        f"Sources:\n{source_lines}\n"
        f"Score reasons:\n{score_reason_lines}\n"
        f"Claims:\n{claim_lines}\n\n"
        "Output shape: "
        '{"text":"...","headline":"...","category":"...","claim_ids":["claim_01"],'
        '"source_ids":["source_01"],"caveats":[]}'
    )


def call_ollama(prompt: str) -> dict[str, Any]:
    model = os.environ.get("SYNTHPOST_OLLAMA_MODEL", "llama3.1")
    timeout = float(os.environ.get("SYNTHPOST_OLLAMA_TIMEOUT", "90"))
    use_chat = os.environ.get("SYNTHPOST_OLLAMA_API", "chat").lower() == "chat"
    url = _ollama_url(use_chat=use_chat)
    if use_chat:
        payload_data: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Output only one valid compact JSON object. No duplicate keys. No markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
            "options": _ollama_options(),
        }
        if _bool_env("SYNTHPOST_OLLAMA_THINK", default=False) is False:
            payload_data["think"] = False
    else:
        payload_data = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": _ollama_options(),
        }
        if _bool_env("SYNTHPOST_OLLAMA_THINK", default=False) is False:
            payload_data["think"] = False
    payload = json.dumps(payload_data).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "Ollama content writing failed. Start Ollama or set "
            "SYNTHPOST_OLLAMA_URL/SYNTHPOST_OLLAMA_MODEL/SYNTHPOST_OLLAMA_TIMEOUT."
        ) from exc
    response_text = _ollama_response_text(data, use_chat=use_chat)
    return _parse_json_response(response_text)


def _ollama_url(*, use_chat: bool) -> str:
    configured = os.environ.get("SYNTHPOST_OLLAMA_URL")
    if configured:
        if use_chat and configured.endswith("/api/generate"):
            return configured.removesuffix("/api/generate") + "/api/chat"
        if not use_chat and configured.endswith("/api/chat"):
            return configured.removesuffix("/api/chat") + "/api/generate"
        return configured
    return "http://localhost:11434/api/chat" if use_chat else "http://localhost:11434/api/generate"


def _ollama_response_text(data: dict[str, Any], *, use_chat: bool) -> str:
    if use_chat:
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        content = str(message.get("content") or "")
        if not content and message.get("thinking"):
            raise RuntimeError(
                "Ollama returned no message content because the model spent its output budget on thinking. "
                "Keep SYNTHPOST_OLLAMA_THINK unset/false or raise SYNTHPOST_OLLAMA_NUM_PREDICT."
            )
        return content
    return str(data.get("response", "{}"))


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _ollama_options() -> dict[str, Any]:
    return {
        "temperature": float(os.environ.get("SYNTHPOST_OLLAMA_TEMPERATURE", "0")),
        "top_p": float(os.environ.get("SYNTHPOST_OLLAMA_TOP_P", "0.7")),
        "repeat_penalty": float(os.environ.get("SYNTHPOST_OLLAMA_REPEAT_PENALTY", "1.25")),
        "num_predict": int(os.environ.get("SYNTHPOST_OLLAMA_NUM_PREDICT", "600")),
        "num_ctx": int(os.environ.get("SYNTHPOST_OLLAMA_NUM_CTX", "4096")),
    }


def _parse_json_response(response_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(response_text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise _non_json_response_error(response_text) from exc
        else:
            raise _non_json_response_error(response_text)
    if not isinstance(parsed, dict):
        raise RuntimeError("Ollama returned JSON, but the script stage expected a JSON object.")
    return parsed


def _non_json_response_error(response_text: str) -> RuntimeError:
    compact = " ".join(response_text.split())
    excerpt = compact[:500]
    return RuntimeError(f"Ollama returned non-JSON content for the script stage. Response excerpt: {excerpt}")


def deterministic_script(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("raw", {})
    headline = str(raw.get("headline_source", "SYNTHPOST BRIEFING")).upper()
    category = str(raw.get("category", "NEWS")).upper()
    claims = raw.get("claims", []) if isinstance(raw.get("claims"), list) else []
    if not claims:
        facts = raw.get("facts", [])
        claims = [{"claim_id": f"claim_{index:02d}", "text": fact} for index, fact in enumerate(facts, start=1)]
    fact_lines = " ".join(str(claim.get("text", "")).rstrip(".") + "." for claim in claims[:3])
    text = (
        f"Good evening. Here is the SynthPost briefing. {raw.get('summary', '')} "
        f"The key facts are these. {fact_lines} We will keep watching the story as more verified details come in."
    )
    claim_ids = [str(claim.get("claim_id")) for claim in claims if claim.get("claim_id")]
    source_ids = sorted(
        {
            str(source_id)
            for claim in claims
            for source_id in (claim.get("source_ids") or [])
            if source_id
        }
    )
    return {
        "text": text.strip(),
        "headline": headline,
        "category": category,
        "claim_ids": claim_ids,
        "source_ids": source_ids,
        "caveats": ["Details may change as more verified reporting becomes available."],
    }


def run(story_json_path: str | Path, *, force: bool = False) -> dict[str, Any]:
    manifest = evidence.normalize_manifest(read_manifest(story_json_path))
    provider = os.environ.get("SYNTHPOST_LLM_PROVIDER", "mock").lower()
    script = manifest.get("script")
    if isinstance(script, dict) and script.get("text") and not force:
        if "SYNTHPOST_LLM_PROVIDER" in os.environ:
            for key, value in _provider_metadata(provider).items():
                script.setdefault(key, value)
        script = evidence.attach_script_evidence(script, manifest["raw"])
        manifest["script"] = script
        manifest["editorial_review"] = evidence.validate_script(script, manifest["raw"])
        write_manifest(story_json_path, manifest)
        record_story_artifact(
            story_json_path,
            "story_manifest_script",
            artifact_record(
                path=story_json_path,
                stage="content_writing",
                input_paths=[story_json_path],
                provider=script.get("llm_provider"),
                model=script.get("llm_model"),
                fresh=False,
                reused=True,
                test_mode=bool(manifest.get("test_mode") or manifest.get("runtime", {}).get("test_mode")),
                render_profile=manifest.get("render_profile") or manifest.get("runtime", {}).get("render_profile") or "production",
            ),
        )
        print("[writing] Reusing script from manifest.")
        return script

    if provider == "ollama":
        script = call_ollama(prompt_for(manifest))
    else:
        script = deterministic_script(manifest)
    script = {**script, **_provider_metadata(provider)}

    required = {"text", "headline", "category", "claim_ids"}
    missing = required - set(script)
    if missing:
        raise ValueError(f"Script provider result missing key(s): {', '.join(sorted(missing))}")
    review = evidence.validate_script(script, manifest["raw"])
    if review["status"] != "pass":
        raise ValueError(f"Script failed evidence review: {', '.join(review['warnings'])}")
    script = evidence.attach_script_evidence(script, manifest["raw"])
    manifest["script"] = script
    manifest["editorial_review"] = review
    write_manifest(story_json_path, manifest)
    record_story_artifact(
        story_json_path,
        "story_manifest_script",
        artifact_record(
            path=story_json_path,
            stage="content_writing",
            input_paths=[story_json_path],
            provider=script.get("llm_provider"),
            model=script.get("llm_model"),
            fresh=True,
            reused=False,
            test_mode=bool(manifest.get("test_mode") or manifest.get("runtime", {}).get("test_mode")),
            render_profile=manifest.get("render_profile") or manifest.get("runtime", {}).get("render_profile") or "production",
        ),
    )
    print("[writing] Wrote script section.")
    return script


def _provider_metadata(provider: str) -> dict[str, str]:
    if provider == "ollama":
        return {
            "llm_provider": "ollama",
            "llm_model": os.environ.get("SYNTHPOST_OLLAMA_MODEL", "llama3.1"),
            "llm_api": os.environ.get("SYNTHPOST_OLLAMA_API", "chat").lower(),
        }
    return {
        "llm_provider": "mock",
        "llm_model": "deterministic_script",
        "llm_api": "local",
    }
