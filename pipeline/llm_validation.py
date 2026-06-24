from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import project_relative, resolve_project_path


class JsonExtractionError(RuntimeError):
    pass


class ProviderValidationFailure(RuntimeError):
    def __init__(self, audit: dict[str, Any]):
        self.audit = audit
        provider = audit.get("provider") or "unknown"
        model = audit.get("model") or "unknown"
        stage = audit.get("stage") or "unknown"
        retry_count = audit.get("retry_count", 0)
        errors = audit.get("errors") or audit.get("warnings") or []
        message = (
            f"{stage} provider output failed validation after {retry_count} retry attempt(s): "
            f"provider={provider}, model={model}, errors={'; '.join(str(error) for error in errors)}"
        )
        partial_path = audit.get("partial_output_path")
        if partial_path:
            message += f", partial_output_path={partial_path}"
        super().__init__(message)


@dataclass
class ProviderAttempt:
    attempt: int
    status: str
    warnings: list[str]
    errors: list[str]
    output_excerpt: str = ""
    partial_output_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "attempt": self.attempt,
                "status": self.status,
                "warnings": self.warnings,
                "errors": self.errors,
                "output_excerpt": self.output_excerpt,
                "partial_output_path": self.partial_output_path,
            }.items()
            if value not in (None, "", [], {})
        }


def compact_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def response_excerpt(value: object, max_chars: int = 500) -> str:
    return compact_text(value)[:max_chars]


def extract_json_object(response_text: str) -> dict[str, Any]:
    text = str(response_text or "").strip()
    if not text:
        raise JsonExtractionError("provider returned empty output")
    candidates = [text]
    candidates.extend(_fenced_json_candidates(text))
    balanced = _balanced_object_candidate(text)
    if balanced:
        candidates.append(balanced)
    seen: set[str] = set()
    parse_errors: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        for repaired in _repair_candidates(candidate):
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError as exc:
                parse_errors.append(str(exc))
                continue
            if not isinstance(parsed, dict):
                raise JsonExtractionError("provider returned JSON, but expected a JSON object")
            return parsed
    detail = parse_errors[-1] if parse_errors else "no JSON object found"
    raise JsonExtractionError(f"could not extract a valid JSON object: {detail}")


def _fenced_json_candidates(text: str) -> list[str]:
    pattern = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
    return [match.group(1).strip() for match in pattern.finditer(text)]


def _balanced_object_candidate(text: str) -> str:
    start_positions = [index for index, char in enumerate(text) if char == "{"]
    for start in start_positions:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
    return ""


def _repair_candidates(candidate: str) -> list[str]:
    repaired = candidate.strip()
    no_trailing_commas = re.sub(r",\s*([}\]])", r"\1", repaired)
    return [repaired, no_trailing_commas] if no_trailing_commas != repaired else [repaired]


def correction_prompt(original_prompt: str, *, stage: str, errors: list[str], previous_output: object) -> str:
    error_lines = "\n".join(f"- {error}" for error in errors if error)
    previous_excerpt = response_excerpt(previous_output, max_chars=1200)
    return (
        f"{original_prompt}\n\n"
        f"VALIDATION FAILED FOR STAGE: {stage}\n"
        "Return only one corrected JSON object. Do not use markdown fences. Do not add facts, names, "
        "numbers, dates, causes, or claims that are not present in the source material. Preserve the same "
        "contract and include all required fields.\n"
        f"Validation errors:\n{error_lines or '- unknown validation error'}\n"
        f"Previous output excerpt:\n{previous_excerpt}\n"
    )


def run_provider_with_retries(
    *,
    stage: str,
    provider: str,
    model: str,
    prompt: str,
    call_provider: Callable[[str], Any],
    validate_output: Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]],
    max_retries: int = 2,
    debug_dir: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempts: list[ProviderAttempt] = []
    current_prompt = prompt
    last_errors: list[str] = []
    partial_path = ""
    for attempt_index in range(max_retries + 1):
        raw_output: Any = ""
        try:
            raw_output = call_provider(current_prompt)
            parsed = raw_output if isinstance(raw_output, dict) else extract_json_object(str(raw_output))
            normalized, review = validate_output(parsed)
            errors = _review_errors(review)
            if not errors:
                attempts.append(
                    ProviderAttempt(
                        attempt=attempt_index,
                        status="pass",
                        warnings=list(review.get("warnings") or []),
                        errors=[],
                        output_excerpt=response_excerpt(raw_output),
                    )
                )
                return normalized, _audit(
                    stage=stage,
                    provider=provider,
                    model=model,
                    status="pass",
                    retry_count=attempt_index,
                    attempts=attempts,
                    warnings=list(review.get("warnings") or []),
                    errors=[],
                    groundedness_status=_groundedness_status(review),
                )
            last_errors = errors
            partial_path = _save_debug_output(debug_dir, stage, attempt_index, raw_output)
            attempts.append(
                ProviderAttempt(
                    attempt=attempt_index,
                    status="needs_review",
                    warnings=list(review.get("warnings") or []),
                    errors=errors,
                    output_excerpt=response_excerpt(raw_output),
                    partial_output_path=partial_path,
                )
            )
        except Exception as exc:
            last_errors = [str(exc)]
            partial_path = _save_debug_output(debug_dir, stage, attempt_index, raw_output)
            attempts.append(
                ProviderAttempt(
                    attempt=attempt_index,
                    status="error",
                    warnings=[],
                    errors=last_errors,
                    output_excerpt=response_excerpt(raw_output),
                    partial_output_path=partial_path,
                )
            )
        if attempt_index < max_retries:
            current_prompt = correction_prompt(
                prompt,
                stage=stage,
                errors=last_errors,
                previous_output=raw_output,
            )
    audit = _audit(
        stage=stage,
        provider=provider,
        model=model,
        status="failed",
        retry_count=max_retries,
        attempts=attempts,
        warnings=[],
        errors=last_errors,
        groundedness_status="needs_review",
        partial_output_path=partial_path,
    )
    raise ProviderValidationFailure(audit)


def _review_errors(review: dict[str, Any]) -> list[str]:
    if review.get("status") == "pass":
        return []
    values = review.get("errors") or review.get("warnings") or []
    return [str(value) for value in values if str(value)]


def _groundedness_status(review: dict[str, Any]) -> str:
    grounded = review.get("groundedness")
    if isinstance(grounded, dict):
        return str(grounded.get("status") or "unknown")
    if review.get("groundedness_status"):
        return str(review.get("groundedness_status"))
    return "pass" if review.get("status") == "pass" else "needs_review"


def _audit(
    *,
    stage: str,
    provider: str,
    model: str,
    status: str,
    retry_count: int,
    attempts: list[ProviderAttempt],
    warnings: list[str],
    errors: list[str],
    groundedness_status: str,
    partial_output_path: str = "",
) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "provider": provider,
            "model": model,
            "stage": stage,
            "validation_status": status,
            "retry_count": retry_count,
            "warnings": warnings,
            "errors": errors,
            "groundedness_status": groundedness_status,
            "attempts": [attempt.to_dict() for attempt in attempts],
            "partial_output_path": partial_output_path,
        }.items()
        if value not in (None, "", [], {})
    }


def _save_debug_output(debug_dir: str | Path | None, stage: str, attempt_index: int, output: object) -> str:
    if not debug_dir:
        return ""
    directory = resolve_project_path(debug_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stage}_attempt_{attempt_index}.txt"
    path.write_text(str(output or ""), encoding="utf-8")
    return project_relative(path)
