from __future__ import annotations

import csv
import json
import math
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pipeline import config
from pipeline.llm.providers import configured_provider, structured_generate
from pipeline.storage import project_relative


ANALYSIS_VERSION = "editorial_cleanliness_v1"

NEWS_BRANDS: dict[str, tuple[str, ...]] = {
    "Aaj Tak": ("aaj tak", "aajtak"),
    "ANI": ("ani news", "ani"),
    "BBC": ("bbc news", "bbc"),
    "CNBC": ("cnbc",),
    "CNN": ("cnn news", "cnn"),
    "ET Now": ("et now", "etnow"),
    "Hindustan Times": ("hindustan times", "ht media"),
    "India Today": ("india today",),
    "Mint": ("livemint", "mint"),
    "NDTV": ("ndtv",),
    "News18": ("news18", "cnn-news18"),
    "Republic": ("republic tv", "republic world"),
    "Reuters": ("reuters",),
    "Sakshi TV": ("sakshi tv",),
    "Times Now": ("times now",),
    "TOI": ("toi bharat", "times of india"),
    "WION": ("wion",),
    "Zee News": ("zee news",),
}

OFFICIAL_SOURCE_PHRASES = (
    "indian railways",
    "ministry of railways",
    "ministry of information and broadcasting",
    "pib india",
    "press information bureau",
    "pmo india",
    "narendra modi official",
)


def _env_csv(name: str) -> set[str]:
    return {
        value.strip().lower()
        for value in (config.env(name, "") or "").split(",")
        if value.strip()
    }


def _phrase_present(text: str, phrase: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    needle = re.sub(r"[^a-z0-9]+", " ", phrase.lower()).strip()
    return bool(needle and re.search(rf"\b{re.escape(needle)}\b", normalized))


def detected_news_brands(text: str) -> list[str]:
    return sorted(
        brand
        for brand, phrases in NEWS_BRANDS.items()
        if any(_phrase_present(text, phrase) for phrase in phrases)
    )


@dataclass
class SourceAssessment:
    source_class: str = "unknown"
    identity: str = ""
    channel_id: str | None = None
    channel_name: str | None = None
    verified: bool = False
    detected_brands: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def model_data(self) -> dict[str, Any]:
        return asdict(self)


def probe_video_source(url: str) -> dict[str, Any]:
    binary = config.env("SYNTHPOST_YT_DLP", "yt-dlp") or "yt-dlp"
    resolved = shutil.which(binary)
    if not resolved:
        raise ValueError("yt-dlp is unavailable for source metadata preflight")
    completed = subprocess.run(
        [
            resolved,
            "--no-playlist",
            "--skip-download",
            "--dump-single-json",
            "--js-runtimes",
            "node",
            url,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=config.env_float("SYNTHPOST_SEARXNG_VIDEO_TIMEOUT", 300.0),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        raise ValueError(
            "video metadata preflight failed"
            + (f": {detail[-1][:500]}" if detail else "")
        )
    raw = json.loads(completed.stdout)
    keep = {
        "id",
        "title",
        "description",
        "uploader",
        "uploader_id",
        "uploader_url",
        "channel",
        "channel_id",
        "channel_url",
        "webpage_url",
        "original_url",
        "extractor",
        "extractor_key",
        "duration",
        "width",
        "height",
        "aspect_ratio",
        "license",
        "availability",
        "categories",
        "tags",
    }
    return {key: raw.get(key) for key in keep if raw.get(key) not in (None, "", [])}


def assess_video_source(
    *, url: str, title: str, source_domain: str | None, metadata: dict[str, Any]
) -> SourceAssessment:
    channel_name = str(metadata.get("channel") or metadata.get("uploader") or "").strip()
    channel_id = str(
        metadata.get("channel_id") or metadata.get("uploader_id") or ""
    ).strip() or None
    identity = channel_name or source_domain or "unknown source"
    identity_text = " ".join([identity, str(source_domain or "")])
    descriptive_text = " ".join(
        [
            identity_text,
            str(metadata.get("description") or "")[:1500],
        ]
    )
    brands = detected_news_brands(identity_text)
    approved_ids = _env_csv("SYNTHPOST_VIDEO_APPROVED_CHANNEL_IDS")
    approved_names = _env_csv("SYNTHPOST_VIDEO_APPROVED_SOURCE_NAMES")
    blocked_names = _env_csv("SYNTHPOST_VIDEO_BLOCKED_SOURCE_NAMES")
    normalized_identity = identity.lower()
    explicitly_approved = bool(
        (channel_id and channel_id.lower() in approved_ids)
        or any(value in normalized_identity for value in approved_names)
    )
    explicitly_blocked = bool(
        any(value in normalized_identity for value in blocked_names)
    )
    official = explicitly_approved or any(
        _phrase_present(descriptive_text, phrase) for phrase in OFFICIAL_SOURCE_PHRASES
    )
    blockers: list[str] = []
    if explicitly_blocked or brands:
        source_class = "news_broadcaster"
        blockers.append(
            "competing news publisher source detected"
            + (f": {', '.join(brands)}" if brands else "")
        )
    elif official:
        source_class = "official_primary_source"
    else:
        source_class = "unknown"
    return SourceAssessment(
        source_class=source_class,
        identity=identity,
        channel_id=channel_id,
        channel_name=channel_name or None,
        verified=explicitly_approved,
        detected_brands=brands,
        blockers=blockers,
        metadata={
            **metadata,
            "search_result_title": title,
            "source_url": url,
        },
    )


def _sample_timestamps(duration: float | None) -> list[float]:
    if not duration or duration <= 1:
        return [0.0]
    values = [
        min(1.0, duration * 0.02),
        duration * 0.10,
        duration * 0.25,
        duration * 0.50,
        duration * 0.75,
        duration * 0.90,
        max(0.0, duration - 1.0),
    ]
    unique: list[float] = []
    for value in values:
        rounded = round(max(0.0, min(duration - 0.05, value)), 3)
        if rounded not in unique:
            unique.append(rounded)
    return unique


def extract_representative_frames(
    path: Path, analysis_dir: Path, *, duration: float | None, is_video: bool
) -> tuple[list[Path], list[float]]:
    analysis_dir.mkdir(parents=True, exist_ok=True)
    timestamps = _sample_timestamps(duration) if is_video else [0.0]
    frames: list[Path] = []
    for index, timestamp in enumerate(timestamps, start=1):
        destination = analysis_dir / f"frame_{index:02d}_{timestamp:07.3f}s.jpg"
        command = [
            config.ffmpeg_binary(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
        ]
        if is_video:
            command.extend(["-ss", str(timestamp)])
        command.extend(
            [
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-update",
                "1",
                str(destination),
            ]
        )
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode == 0 and destination.exists():
            frames.append(destination)
    if not frames:
        raise ValueError("content scan could not extract representative frames")
    return frames, timestamps[: len(frames)]


def _ocr_frame(path: Path, frame_index: int) -> list[dict[str, Any]]:
    binary = shutil.which(config.env("SYNTHPOST_TESSERACT", "tesseract") or "tesseract")
    if not binary:
        raise ValueError("tesseract is unavailable for visual overlay analysis")
    completed = subprocess.run(
        [binary, str(path), "stdout", "--psm", "11", "tsv"],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if completed.returncode != 0:
        raise ValueError("tesseract OCR failed")
    rows = list(csv.DictReader(completed.stdout.splitlines(), delimiter="\t"))
    findings: list[dict[str, Any]] = []
    for row in rows:
        text = " ".join(str(row.get("text") or "").split()).strip()
        try:
            confidence = float(row.get("conf") or -1)
            left = int(row.get("left") or 0)
            top = int(row.get("top") or 0)
            width = int(row.get("width") or 0)
            height = int(row.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if confidence < 45 or len(re.sub(r"[^a-zA-Z0-9]", "", text)) < 2:
            continue
        findings.append(
            {
                "frame_index": frame_index,
                "text": text[:120],
                "confidence": round(confidence, 1),
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            }
        )
    return findings


def _region(item: dict[str, Any], frame_width: int, frame_height: int) -> str:
    center_x = (item["left"] + item["width"] / 2) / max(frame_width, 1)
    center_y = (item["top"] + item["height"] / 2) / max(frame_height, 1)
    if center_y >= 0.82:
        return "bottom_ticker"
    if center_y >= 0.62:
        return "lower_third"
    if center_y <= 0.32 and center_x <= 0.38:
        return "top_left"
    if center_y <= 0.32 and center_x >= 0.62:
        return "top_right"
    return "scene"


def _contact_sheet(frames: list[Path], destination: Path) -> Path | None:
    binary = shutil.which("montage") or shutil.which("magick")
    if not binary:
        return None
    command = [binary]
    if Path(binary).name == "magick":
        command.append("montage")
    command.extend(str(frame) for frame in frames)
    command.extend(
        [
            "-thumbnail",
            "480x270",
            "-tile",
            "4x",
            "-geometry",
            "+8+8",
            "-background",
            "#07101d",
            str(destination),
        ]
    )
    subprocess.run(command, check=False, capture_output=True, text=True)
    # ImageMagick can return a warning status for a missing optional label font
    # while still producing a valid contact sheet. The artifact itself is the
    # authoritative success signal.
    return destination if destination.exists() else None


def _ai_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "decision",
            "clean_broll_score",
            "contains_presenter_package",
            "reasons",
        ],
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["pass", "reject", "needs_review"],
            },
            "clean_broll_score": {"type": "number"},
            "contains_presenter_package": {"type": "boolean"},
            "reasons": {"type": "array", "items": {"type": "string"}},
        },
    }


def _validate_ai_result(raw: dict[str, Any]) -> dict[str, Any]:
    decision = str(raw.get("decision") or "").strip()
    if decision not in {"pass", "reject", "needs_review"}:
        raise ValueError("invalid content-cleanliness decision")
    try:
        score = float(raw.get("clean_broll_score"))
    except (TypeError, ValueError) as exc:
        raise ValueError("clean_broll_score must be numeric") from exc
    reasons = [str(value).strip() for value in raw.get("reasons", []) if str(value).strip()]
    if not reasons:
        raise ValueError("content-cleanliness classifier must provide reasons")
    return {
        "decision": decision,
        "clean_broll_score": max(0.0, min(1.0, score)),
        "contains_presenter_package": bool(raw.get("contains_presenter_package")),
        "reasons": reasons[:8],
    }


def _ai_classify(evidence: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if not config.env_bool("SYNTHPOST_AI_VISUAL_CLEANLINESS", True):
        raise ValueError("AI visual cleanliness classification is disabled")
    provider = configured_provider()
    prompt = f"""
You are SynthPost's editorial-cleanliness classifier for visual media.
Classify only from the supplied source metadata and deterministic OCR evidence.
Do not invent visual observations that are not in the evidence.

Reject finished packages from competing news publishers, including publisher
logos, persistent watermarks, lower-thirds, tickers, presenter packages, and
subscribe/promotional overlays. Official primary-source footage may pass this
cleanliness stage when no third-party broadcaster packaging is indicated, but
rights approval remains a separate human decision. Unknown evidence or a scan
that cannot rule out branded packaging must return needs_review.

Return a clean_broll_score from 0.0 to 1.0 and concise evidence-based reasons.

EVIDENCE JSON:
{json.dumps(evidence, ensure_ascii=True)}
""".strip()
    result, _attempts = structured_generate(
        provider,
        prompt,
        _ai_schema(),
        _validate_ai_result,
        max_retries=2,
    )
    return result, provider.name


def analyze_media_cleanliness(
    path: Path,
    analysis_dir: Path,
    *,
    duration: float | None,
    is_video: bool,
    width: int,
    height: int,
    source: SourceAssessment,
) -> dict[str, Any]:
    frames, timestamps = extract_representative_frames(
        path, analysis_dir, duration=duration, is_video=is_video
    )
    ocr_findings: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        ocr_findings.extend(_ocr_frame(frame, index))
    normalized_occurrences: dict[tuple[str, str], set[int]] = {}
    for item in ocr_findings:
        token = re.sub(r"[^a-z0-9]+", "", item["text"].lower())
        if len(token) < 3:
            continue
        region = _region(item, width, height)
        item["region"] = region
        normalized_occurrences.setdefault((token, region), set()).add(
            int(item["frame_index"])
        )
    persistence_threshold = max(2, math.ceil(len(frames) * 0.35))
    persistent = [
        {"text": token, "region": region, "frame_count": len(frame_ids)}
        for (token, region), frame_ids in normalized_occurrences.items()
        if region != "scene" and len(frame_ids) >= persistence_threshold
    ]
    all_ocr_text = " ".join(item["text"] for item in ocr_findings)
    frame_brands = detected_news_brands(all_ocr_text)
    detected_brands = sorted(set(source.detected_brands + frame_brands))
    persistent_lower = [
        item
        for item in persistent
        if item["region"] in {"lower_third", "bottom_ticker"}
    ]
    contains_lower_third = len(persistent_lower) >= 2
    contains_ticker = sum(
        1 for item in persistent if item["region"] == "bottom_ticker"
    ) >= 2
    hard_blockers = list(source.blockers)
    if detected_brands:
        hard_blockers.append(
            f"competing publisher branding detected: {', '.join(detected_brands)}"
        )
    if contains_lower_third:
        hard_blockers.append("persistent publisher-style lower-third detected")
    if contains_ticker:
        hard_blockers.append("persistent ticker or promotional strip detected")
    contact_sheet = _contact_sheet(frames, analysis_dir / "contact_sheet.jpg")
    evidence = {
        "analysis_version": ANALYSIS_VERSION,
        "source": source.model_data(),
        "sample_count": len(frames),
        "scan_timestamps": timestamps,
        "detected_brands": detected_brands,
        "persistent_overlay_text": persistent[:40],
        "contains_lower_third": contains_lower_third,
        "contains_ticker": contains_ticker,
        "ocr_text_sample": [item["text"] for item in ocr_findings[:80]],
        "deterministic_blockers": hard_blockers,
    }
    ai_provider: str | None = None
    try:
        ai_result, ai_provider = _ai_classify(evidence)
    except Exception as exc:
        ai_result = {
            "decision": "needs_review",
            "clean_broll_score": 0.0,
            "contains_presenter_package": False,
            "reasons": [f"AI cleanliness classification unavailable: {exc}"],
        }
    blockers = list(dict.fromkeys(hard_blockers))
    if ai_result["contains_presenter_package"]:
        blockers.append("presenter or finished news package detected by AI classifier")
    if blockers or ai_result["decision"] == "reject":
        status = "rejected"
    elif ai_result["decision"] == "pass":
        status = "passed"
    else:
        status = "needs_review"
    if status != "passed" and not blockers:
        decision_reason = next(
            (
                str(reason).strip()
                for reason in ai_result.get("reasons", [])
                if str(reason).strip()
            ),
            "classifier returned needs_review",
        )
        blockers.append(f"cleanliness review required: {decision_reason}")
    if is_video and source.source_class == "unknown":
        blockers.append(
            "video source identity is not an approved primary, licensed, or user-owned source"
        )
    return {
        "content_cleanliness_status": status,
        "source_class": source.source_class,
        "source_identity": source.identity,
        "source_channel_id": source.channel_id,
        "source_channel_name": source.channel_name,
        "source_verified": source.verified,
        "source_metadata": source.metadata,
        "contains_third_party_logo": bool(detected_brands),
        "detected_brands": detected_brands,
        "contains_lower_third": contains_lower_third,
        "contains_ticker": contains_ticker,
        "contains_presenter": bool(ai_result["contains_presenter_package"]),
        "ocr_findings": ocr_findings[:240],
        "scan_timestamps": timestamps,
        "analysis_frame_paths": [project_relative(frame) for frame in frames],
        "contact_sheet_path": project_relative(contact_sheet) if contact_sheet else None,
        "clean_broll_score": round(float(ai_result["clean_broll_score"]), 3),
        "content_analysis_version": ANALYSIS_VERSION,
        "content_analysis_provider": ai_provider,
        "content_analysis_evidence": list(
            dict.fromkeys(hard_blockers + ai_result["reasons"])
        ),
        "approval_blockers": list(dict.fromkeys(blockers)),
    }
