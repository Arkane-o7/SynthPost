"""Pure timing helpers shared by the experimental Blender CC driver."""

from __future__ import annotations

import math
from typing import Any


FADE_MS = 45.0
BLINK_PERIOD_MS = 4200.0
BLINK_DURATION_MS = 150.0
BLINK_OFFSET_MS = 900.0

OCULUS_TO_REALLUSION: dict[str, dict[str, float]] = {
    "sil": {},
    "PP": {"V_Explosive": 0.34},
    "FF": {"V_Dental_Lip": 0.4, "V_Lip_Open": 0.16},
    "TH": {"V_Dental_Lip": 0.24, "V_Lip_Open": 0.52, "Mouth_Drop_Lower": 0.28, "Jaw_Open": 0.035},
    "DD": {"V_Affricate": 0.3, "V_Lip_Open": 0.58, "Mouth_Drop_Lower": 0.34, "Jaw_Open": 0.04},
    "kk": {"V_Affricate": 0.28, "V_Lip_Open": 0.52, "Mouth_Drop_Lower": 0.28, "Jaw_Open": 0.035},
    "CH": {"V_Affricate": 0.42, "V_Lip_Open": 0.34, "Mouth_Drop_Lower": 0.16, "Jaw_Open": 0.025},
    "SS": {"V_Tight": 0.2, "V_Lip_Open": 0.18, "Jaw_Open": 0.015},
    "nn": {"V_Tight": 0.16, "V_Lip_Open": 0.26, "Mouth_Drop_Lower": 0.12, "Jaw_Open": 0.02},
    "RR": {"V_Tight_O": 0.22, "V_Lip_Open": 0.42, "Mouth_Drop_Lower": 0.2, "Jaw_Open": 0.03},
    "aa": {"V_Lip_Open": 1.0, "V_Open": 0.12, "Mouth_Drop_Lower": 0.72, "Mouth_Drop_Upper": 0.08, "Jaw_Open": 0.08},
    "E": {"V_Wide": 0.22, "V_Lip_Open": 0.82, "Mouth_Drop_Lower": 0.42, "Jaw_Open": 0.045},
    "I": {"V_Wide": 0.34, "V_Lip_Open": 0.42, "Mouth_Drop_Lower": 0.18, "Jaw_Open": 0.02},
    "O": {"V_Tight_O": 0.58, "V_Lip_Open": 0.5, "Mouth_Drop_Lower": 0.28, "Jaw_Open": 0.04},
    "U": {"V_Tight_O": 0.46, "V_Tight": 0.04, "V_Lip_Open": 0.36, "Jaw_Open": 0.02},
}

SOFT_NEUTRAL = {
    "Eye_Blink_L": 0.065,
    "Eye_Blink_R": 0.065,
    "Eye_Squint_L": 0.045,
    "Eye_Squint_R": 0.045,
    "Brow_Raise_Inner_L": 0.018,
    "Brow_Raise_Inner_R": 0.018,
    "Mouth_Smile_L": 0.026,
    "Mouth_Smile_R": 0.026,
}

EXPRESSION_PRESETS: dict[str, dict[str, float]] = {
    "attentive": {
        "Brow_Raise_Inner_L": 0.09,
        "Brow_Raise_Inner_R": 0.09,
        "Eye_Squint_L": 0.035,
        "Eye_Squint_R": 0.035,
    },
    "serious": {
        "Brow_Compress_L": 0.1,
        "Brow_Compress_R": 0.1,
        "Eye_Squint_L": 0.045,
        "Eye_Squint_R": 0.045,
    },
    "warm": {
        "Mouth_Smile_L": 0.12,
        "Mouth_Smile_R": 0.12,
        "Eye_Squint_L": 0.035,
        "Eye_Squint_R": 0.035,
    },
    "concerned": {
        "Brow_Raise_Inner_L": 0.12,
        "Brow_Raise_Inner_R": 0.12,
        "Brow_Drop_L": 0.035,
        "Brow_Drop_R": 0.035,
    },
}


def active_viseme(
    t_ms: float, visemes: list[str], starts_ms: list[float], durations_ms: list[float]
) -> tuple[str, float] | None:
    for cue, start, duration in zip(visemes, starts_ms, durations_ms):
        end = start + duration
        if start <= t_ms <= end:
            fade_in = min(1.0, max(0.0, (t_ms - start) / FADE_MS))
            fade_out = min(1.0, max(0.0, (end - t_ms) / FADE_MS))
            return cue, min(fade_in, fade_out, 1.0)
    return None


def blink_strength(t_ms: float) -> float:
    phase = (t_ms + BLINK_OFFSET_MS) % BLINK_PERIOD_MS
    if phase > BLINK_DURATION_MS:
        return 0.0
    return math.sin((phase / BLINK_DURATION_MS) * math.pi)


def scheduled_blink_strength(t_seconds: float, events: list[dict[str, Any]]) -> float:
    """Evaluate authored blink events, falling back to the legacy cadence."""

    if not events:
        return blink_strength(t_seconds * 1000.0)
    strength = 0.0
    for event in events:
        start = float(event.get("time") or 0.0)
        duration = max(0.001, float(event.get("duration") or 0.15))
        phase = (t_seconds - start) / duration
        if 0.0 <= phase <= 1.0:
            strength = max(
                strength,
                math.sin(phase * math.pi) * float(event.get("strength", 1.0)),
            )
    return max(0.0, min(1.0, strength))


def expression_weights(
    t_seconds: float, events: list[dict[str, Any]]
) -> dict[str, float]:
    """Blend restrained semantic expression presets at a point in time."""

    result: dict[str, float] = {}
    for event in events:
        start = float(event.get("start", event.get("time", 0.0)))
        end = float(
            event.get(
                "end",
                start + float(event.get("duration", 0.0)),
            )
        )
        if end <= start or not start <= t_seconds <= end:
            continue
        span = end - start
        fade = min(max(span * 0.15, 0.08), 0.3)
        envelope = min(
            1.0,
            max(0.0, (t_seconds - start) / fade),
            max(0.0, (end - t_seconds) / fade),
        )
        event_weight = max(0.0, min(1.0, float(event.get("weight", 1.0))))
        preset = EXPRESSION_PRESETS.get(str(event.get("preset") or ""), {})
        for name, value in preset.items():
            result[name] = max(result.get(name, 0.0), value * event_weight * envelope)
    return result


def pulse_at(t_seconds: float, event: dict[str, Any]) -> float:
    half = float(event.get("duration") or 0.9) / 2.0
    distance = abs(t_seconds - float(event.get("time") or 0.0))
    if half <= 0 or distance >= half:
        return 0.0
    return math.sin((1.0 - distance / half) * math.pi * 0.5)
