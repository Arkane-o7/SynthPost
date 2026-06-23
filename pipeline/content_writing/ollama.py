from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any

from ..storage import read_manifest, write_manifest


def prompt_for(manifest: dict[str, Any]) -> str:
    raw = manifest.get("raw", {})
    facts = "\n".join(f"- {fact}" for fact in raw.get("facts", []))
    return (
        "Write grounded broadcast anchor copy for a YouTube news segment.\n"
        "Use only the supplied source summary and facts. Do not fabricate claims.\n"
        "Tone: concise, direct, international news desk. Target 60 to 90 seconds.\n\n"
        f"Headline: {raw.get('headline_source', '')}\n"
        f"Category: {raw.get('category', '')}\n"
        f"Summary: {raw.get('summary', '')}\n"
        f"Facts:\n{facts}\n\n"
        "Return JSON with keys text, headline, category."
    )


def call_ollama(prompt: str) -> dict[str, Any]:
    url = os.environ.get("SYNTHPOST_OLLAMA_URL", "http://localhost:11434/api/generate")
    model = os.environ.get("SYNTHPOST_OLLAMA_MODEL", "llama3.1")
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "Ollama content writing failed. Start Ollama or set SYNTHPOST_OLLAMA_URL/SYNTHPOST_OLLAMA_MODEL."
        ) from exc
    try:
        return json.loads(data.get("response", "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned non-JSON content for the script stage.") from exc


def deterministic_script(manifest: dict[str, Any]) -> dict[str, str]:
    raw = manifest.get("raw", {})
    headline = str(raw.get("headline_source", "SYNTHPOST BRIEFING")).upper()
    category = str(raw.get("category", "NEWS")).upper()
    facts = raw.get("facts", [])
    fact_lines = " ".join(str(fact).rstrip(".") + "." for fact in facts[:3])
    text = (
        f"Good evening. Here is the SynthPost briefing. {raw.get('summary', '')} "
        f"The key facts are these. {fact_lines} We will keep watching the story as more verified details come in."
    )
    return {"text": text.strip(), "headline": headline, "category": category}


def run(story_json_path: str | Path, *, force: bool = False) -> dict[str, Any]:
    manifest = read_manifest(story_json_path)
    script = manifest.get("script")
    if isinstance(script, dict) and script.get("text") and not force:
        print("[writing] Reusing script from manifest.")
        return script

    provider = os.environ.get("SYNTHPOST_LLM_PROVIDER", "mock").lower()
    if provider == "ollama":
        script = call_ollama(prompt_for(manifest))
    else:
        script = deterministic_script(manifest)

    required = {"text", "headline", "category"}
    missing = required - set(script)
    if missing:
        raise ValueError(f"Script provider result missing key(s): {', '.join(sorted(missing))}")
    manifest["script"] = script
    write_manifest(story_json_path, manifest)
    print("[writing] Wrote script section.")
    return script
