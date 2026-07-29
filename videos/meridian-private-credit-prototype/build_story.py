#!/usr/bin/env python3
"""Build the Meridian private-credit visual prototype manifest.

The builder uses exact dots.tts timing when all nine beats are available. Until
then it creates a silent review track with conservative word-count timing so
the visual direction can be reviewed without substituting another narrator.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
VIDEO = Path(__file__).resolve().parent
REQUEST = VIDEO / "narration-request.json"
TIMING = VIDEO / "narration-timing-raw.json"
NARRATION = VIDEO / "narration-raw.wav"
SILENCE = VIDEO / "narration-preview-silence.wav"
STORY = VIDEO / "story.json"


def beat_windows(units: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    if TIMING.is_file() and NARRATION.is_file():
        raw = json.loads(TIMING.read_text(encoding="utf-8"))
        raw_beats = raw.get("beats", [])
        if len(raw_beats) == len(units):
            rate = float(raw.get("sample_rate", 48_000))
            beats = [
                {
                    "beat_id": beat["beat_id"],
                    "section_id": beat["section_id"],
                    "start_time": beat["start_sample"] / rate,
                    "speech_end_time": beat["speech_end_sample"] / rate,
                    "end_time": beat["end_sample"] / rate,
                }
                for beat in raw_beats
            ]
            return beats, True

    cursor = 0.0
    beats: list[dict[str, Any]] = []
    # Calibrated from pc001 using the locked Meridian dots.tts profile.
    words_per_second = 2.18
    for unit in units:
        duration = max(4.5, len(unit["text"].split()) / words_per_second)
        start = cursor
        speech_end = start + duration
        cursor = speech_end + float(unit.get("pause_after_ms", 0)) / 1000
        beats.append(
            {
                "beat_id": unit["beat_id"],
                "section_id": unit["section_id"],
                "start_time": start,
                "speech_end_time": speech_end,
                "end_time": cursor,
            }
        )
    return beats, False


def ensure_silence(duration: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            f"{duration:.3f}",
            "-c:a",
            "pcm_s16le",
            str(SILENCE),
        ],
        check=True,
    )


def media(path: str, *, media_type: str, source: str, url: str) -> dict[str, Any]:
    return {
        "asset_id": Path(path).stem,
        "path": f"videos/meridian-private-credit-prototype/{path}",
        "media_type": media_type,
        "content_role": "evidence",
        "source": source,
        "source_url": url,
        "attribution_text": source,
        "rights_tier": "green",
        "review_status": "approved",
    }


def segment(
    beat: dict[str, Any],
    unit: dict[str, Any],
    *,
    template: str,
    scene_id: str,
    data: dict[str, Any] | None = None,
    visible: bool = False,
    presenter: dict[str, Any] | None = None,
    visual: dict[str, Any] | None = None,
    assets: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    narrative_function: str = "explain",
    visual_role: str = "clarify",
) -> dict[str, Any]:
    start = float(beat["start_time"])
    end = float(beat["end_time"])
    overlay_data = dict(data or {})
    if presenter:
        overlay_data["meridian_presenter"] = presenter
    return {
        "segment_id": f"segment_{unit['beat_id']}",
        "beat_id": unit["beat_id"],
        "scene_id": scene_id,
        "section_id": unit["section_id"],
        "start_time": start,
        "end_time": end,
        "duration": end - start,
        "narrative_function": narrative_function,
        "visual_role": visual_role,
        "transition_in": "paper_sweep" if start == 0 else "hard_cut",
        "transition_out": "hard_cut",
        "script_text": unit["text"],
        "internal_events": events or [],
        "scene_assets": assets or {},
        "anchor": {
            "visible": visible,
            "speaking": True,
            "camera": "editorial_canvas",
        },
        "visual": visual or {"media_type": "fallback", "content_role": "fallback"},
        "template": {"template_id": template},
        "audio": {
            "mode": "narration",
            "narration_volume": 1,
            "source_volume": 0,
            "ducking": False,
        },
        "overlays": {"data": overlay_data},
        "status": "approved",
    }


def main() -> None:
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    units = request["units"]
    beats, exact = beat_windows(units)
    duration = float(beats[-1]["end_time"])
    if not exact:
        ensure_silence(duration)
    audio_path = NARRATION if exact else SILENCE

    fed_url = "https://www.federalreserve.gov/publications/files/financial-stability-report-20260508.pdf"
    imf_url = "https://www.imf.org/-/media/files/publications/gfsr/2024/april/english/ch2.pdf"

    segments = [
        segment(
            beats[0],
            units[0],
            template="meridian_clipping_board",
            scene_id="private_credit_headline",
            visual=media(
                "media/fed-private-credit-page.png",
                media_type="document",
                source="Federal Reserve · Financial Stability Report · May 2026",
                url=fed_url,
            ),
            data={
                "clipping_kind": "headline",
                "source": "THE MERIDIAN LEDGER",
                "date": "JULY 29, 2026",
                "headline": "The bank loan that left the bank",
                "deck": "Private credit moved lending outside banks. The risk did not travel quite as far.",
            },
            narrative_function="open_with_paradox",
            visual_role="hook_and_frame",
        ),
        segment(
            beats[1],
            units[1],
            template="meridian_data_board",
            scene_id="fed_scale",
            visual=media(
                "media/fed-private-credit-figure.png",
                media_type="document",
                source="Federal Reserve · private-credit market estimates",
                url=fed_url,
            ),
            narrative_function="establish_scale",
            visual_role="prove_with_primary_source",
        ),
        segment(
            beats[2],
            units[2],
            template="meridian_narrator_evidence",
            scene_id="liquidity_correction",
            visible=True,
            presenter={
                "pose": "shrug",
                "placement": "lower_right",
                "motion": "pop",
                "width": 1210,
            },
            data={
                "quote_headline": "Shadow banking.\nBut not a bank run.",
                "quote_body": "Long-duration capital removes the classic deposit-run mechanism—while leaving other risks intact.",
                "bubble_text": "A comforting distinction. Mostly.",
            },
            narrative_function="correct_intuition",
            visual_role="presenter_reaction",
        ),
        segment(
            beats[3],
            units[3],
            template="meridian_mechanism",
            scene_id="borrower_mechanism",
            data={
                "heading": "Why borrowers pay for private credit",
                "mechanism_nodes": [
                    {"number": "1", "title": "Certainty", "body": "One negotiated lender instead of a marketed bond"},
                    {"number": "2", "title": "Speed", "body": "Fewer syndication steps and faster execution"},
                    {"number": "3", "title": "Custom terms", "body": "Covenants shaped around one transaction"},
                ],
            },
            narrative_function="explain_demand",
            visual_role="mechanism_diagram",
        ),
        segment(
            beats[4],
            units[4],
            template="meridian_document_highlight",
            scene_id="imf_risk_document",
            assets={
                "document": media(
                    "media/imf-private-credit-page.png",
                    media_type="document",
                    source="IMF · Global Financial Stability Report · April 2024",
                    url=imf_url,
                )
            },
            data={
                "document_quote": "Near-term risks may be contained, while opacity, floating rates, subjective valuations, and interconnected leverage make losses harder to observe.",
                "document_source": "IMF · GLOBAL FINANCIAL STABILITY REPORT · APRIL 2024",
            },
            narrative_function="introduce_risk",
            visual_role="document_evidence",
        ),
        segment(
            beats[5],
            units[5],
            template="meridian_clipping_board",
            scene_id="banks_did_not_vanish",
            data={
                "clipping_kind": "social",
                "display_name": "Meridian Research Desk",
                "handle": "@meridianresearch",
                "post": "The loan left the bank balance sheet. The financing chain did not. Banks still lend to funds, provide subscription lines, and finance portfolios.",
                "context": "Credit moved. Exposure remained connected.",
                "source": "FEDERAL RESERVE · MAY 2026",
                "date": "RESEARCH NOTE",
                "replies": "38",
                "reposts": "214",
                "likes": "1.8K",
            },
            narrative_function="reveal_twist",
            visual_role="social_clipping",
        ),
        segment(
            beats[6],
            units[6],
            template="meridian_narrator_tokens",
            scene_id="capital_chain",
            visible=True,
            presenter={
                "pose": "pointing",
                "placement": "lower_right",
                "motion": "slide",
                "width": 1210,
            },
            data={
                "heading": "Liquidity risk returns through\nthe access products.",
                "hub_label": "PRIVATE CREDIT",
            },
            events=[
                {"event_id": "bank", "type": "add_token", "at": 0.5, "payload": {"label": "BANK LINES"}},
                {"event_id": "fund", "type": "add_token", "at": 1.8, "payload": {"label": "CREDIT FUNDS"}},
                {"event_id": "borrower", "type": "add_token", "at": 3.1, "payload": {"label": "BORROWERS"}},
                {"event_id": "retail", "type": "add_token", "at": 4.4, "payload": {"label": "RETAIL VEHICLES"}},
                {"event_id": "redemptions", "type": "add_token", "at": 5.7, "payload": {"label": "REDEMPTIONS"}},
            ],
            narrative_function="map_interconnection",
            visual_role="presenter_corkboard",
        ),
        segment(
            beats[7],
            units[7],
            template="meridian_footage_montage",
            scene_id="quiet_lending_machine",
            assets={
                "datacenter": media(
                    "media/fed-system.mp4",
                    media_type="video",
                    source="Federal Reserve · public information footage",
                    url="https://www.federalreserve.gov/",
                ),
                "developer": media(
                    "media/roof-workers.mp4",
                    media_type="video",
                    source="Pexels · construction business footage",
                    url="https://www.pexels.com/",
                ),
            },
            data={
                "first_headline": "A quieter lending machine.",
                "second_headline": "The borrowers are still real businesses.",
                "first_source": "FEDERAL RESERVE · PUBLIC INFORMATION FOOTAGE",
                "second_source": "PEXELS · LICENSED STOCK FOOTAGE",
                "switch_at": max(3.2, (float(beats[7]["end_time"]) - float(beats[7]["start_time"])) * 0.52),
            },
            narrative_function="synthesize",
            visual_role="footage_breath",
        ),
        segment(
            beats[8],
            units[8],
            template="meridian_sparse_thesis",
            scene_id="visibility_trade",
            data={
                "thesis_lead": "The real trade is\nvisibility for flexibility.",
                "thesis_support": "That works beautifully—until everyone asks",
                "thesis_keyword": "WHAT IS IT WORTH?",
                "thesis_final": "An illiquid loan only looks calm while nobody needs a public price.",
            },
            narrative_function="close_with_tension",
            visual_role="thesis",
        ),
    ]

    manifest = {
        "story_id": "story_meridian_private_credit_prototype",
        "episode_id": "episode_meridian_private_credit_prototype",
        "channel_id": "meridian",
        "channel": {
            "channel_id": "meridian",
            "name": "Meridian",
            "tagline": "Follow the money",
            "production": {
                "composition_template": "timeline_story_meridian",
                "template_policy": "meridian_editorial_canvas_v2",
                "presenter_provider": "png_puppet",
                "brand": {
                    "navy": "#0D1012",
                    "deep_blue": "#171B1E",
                    "accent": "#D5A94E",
                    "accent_secondary": "#8FB7A1",
                    "danger": "#C65D52",
                    "white": "#F5F7FA",
                    "muted": "#AEB4B0",
                    "ink": "#080A0B",
                },
            },
        },
        "raw": {
            "headline_source": "The bank loan that left the bank",
            "source_name": "Meridian research desk",
            "published_at": "2026-07-29T00:00:00+05:30",
            "category": "private credit",
        },
        "script": {
            "headline": "The bank loan that left the bank",
            "category": "financial system",
        },
        "direction": {
            "fps": 24,
            "estimated_duration_seconds": duration,
            "presenter_provider": "png_puppet",
            "presenter_manifest_path": "assets/channels/meridian/presenter/character.json",
            "narration_audio_path": str(audio_path.relative_to(ROOT)),
        },
        "narration": {
            "audio_path": str(audio_path.relative_to(ROOT)),
            "provider": "dots_tts",
            "model": request["model_name"],
            "voice_id": request["voice_id"],
            "timing_source": "exact" if exact else "word_count_preview",
            "preview_audio": not exact,
            "duration_seconds": duration,
            "beats": beats,
        },
        "runtime": {
            "render_profile_settings": {"fps": 24, "width": 1920, "height": 1080}
        },
        "approved_timeline": {
            "timeline_id": "timeline_meridian_private_credit_prototype",
            "story_id": "story_meridian_private_credit_prototype",
            "version": 1,
            "status": "approved",
            "segments": segments,
        },
        "composition": {
            "template": "timeline_story_meridian",
            "duration_seconds": duration,
            "output_path": "videos/meridian-private-credit-prototype/review.mp4",
            "preview_path": "videos/meridian-private-credit-prototype/preview.png",
        },
    }
    STORY.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "story": str(STORY),
                "duration_seconds": round(duration, 3),
                "exact_narration": exact,
                "audio": str(audio_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
