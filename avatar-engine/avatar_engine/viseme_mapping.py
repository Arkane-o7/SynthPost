"""Rhubarb mouth-cue → TalkingHead/Oculus viseme mapping.

Rhubarb produces mouth-cue labels A–H and X.  TalkingHead (via the Oculus
lipsync standard) uses a different set: sil, PP, FF, TH, DD, kk, CH, SS,
nn, RR, aa, E, I, O, U.

Reference
---------
Rhubarb labels (from https://github.com/DanielSWolf/rhubarb-lip-sync):
  X  – silence / rest
  A  – closed mouth (m, b, p)
  B  – slightly open (pause / schwa)
  C  – open mouth (consonants like d, k, t)
  D  – wide open / "th"
  E  – ah / open vowel
  F  – ee / narrow vowel
  G  – ou / rounded vowel
  H  – "r"-like
  X  – silence

Oculus lipsync visemes used by TalkingHead:
  sil  – silence
  PP   – bilabial (p, b, m)
  FF   – labiodental (f, v)
  TH   – dental (th)
  DD   – alveolar (d, n, t)
  kk   – velar (k, g)
  CH   – postalveolar (ch, sh, j)
  SS   – sibilant (s, z)
  nn   – nasal (n, ng)
  RR   – approximant (r)
  aa   – open vowel (a)
  E    – mid vowel (e)
  I    – close vowel (i)
  O    – rounded vowel (o)
  U    – close-back vowel (u)
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Core mapping table
# ---------------------------------------------------------------------------

RHUBARB_TO_OCULUS: dict[str, str] = {
    "X": "sil",  # silence / rest
    "A": "PP",  # closed — bilabial consonants (m, b, p)
    "B": "PP",  # slightly open — treated as bilabial rest
    "C": "DD",  # open mouth consonants (d, k, t)
    "D": "TH",  # wide open / "th"
    "E": "aa",  # ah / open vowel
    "F": "I",  # ee / narrow vowel
    "G": "O",  # ou / rounded vowel
    "H": "RR",  # r-like
}

# Fallback viseme when an unknown cue is encountered
FALLBACK_VISEME = "sil"

# Minimum viseme duration (ms) — prevents zero-duration events
MIN_VISEME_DURATION_MS = 20.0


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def rhubarb_cue_to_oculus(cue_label: str) -> str:
    """Map a single Rhubarb cue label to an Oculus viseme ID."""
    return RHUBARB_TO_OCULUS.get(cue_label.upper(), FALLBACK_VISEME)


def convert_rhubarb_json_to_talkinghead(
    rhubarb_data: dict[str, Any],
    custom_mapping: dict[str, str] | None = None,
) -> tuple[list[str], list[float], list[float]]:
    """Convert a parsed Rhubarb JSON result to three parallel arrays.

    Parameters
    ----------
    rhubarb_data:
        Parsed content of a Rhubarb ``--outputFormat json`` file.  The
        expected shape is ``{"mouthCues": [{"start": 0.0, "end": 0.08,
        "value": "A"}, ...]}``.
    custom_mapping:
        Optional per-avatar override of individual Rhubarb labels to Oculus
        viseme names.  Missing labels fall through to ``RHUBARB_TO_OCULUS``.

    Returns
    -------
    visemes : list[str]
        Oculus viseme IDs.
    vtimes : list[float]
        Cue start times in **milliseconds**.
    vdurations : list[float]
        Cue durations in **milliseconds**.
    """
    mapping = dict(RHUBARB_TO_OCULUS)
    if custom_mapping:
        mapping.update({k.upper(): v for k, v in custom_mapping.items()})

    cues: list[dict[str, Any]] = rhubarb_data.get("mouthCues", [])

    visemes: list[str] = []
    vtimes: list[float] = []
    vdurations: list[float] = []

    for cue in cues:
        label = str(cue.get("value", "X")).upper()
        start_s = float(cue.get("start", 0.0))
        end_s = float(cue.get("end", start_s))
        duration_ms = max(MIN_VISEME_DURATION_MS, (end_s - start_s) * 1000.0)

        visemes.append(mapping.get(label, FALLBACK_VISEME))
        vtimes.append(start_s * 1000.0)
        vdurations.append(duration_ms)

    return visemes, vtimes, vdurations


def viseme_mapping_for_avatar(avatar_metadata: dict[str, Any]) -> dict[str, str]:
    """Extract a per-avatar Rhubarb→viseme override from avatar metadata.

    Returns an empty dict if no ``viseme_mapping`` key exists.
    """
    mapping = avatar_metadata.get("viseme_mapping", {})
    if not isinstance(mapping, dict):
        return {}
    return {str(k): str(v) for k, v in mapping.items()}


# ---------------------------------------------------------------------------
# Fixture / smoke helper
# ---------------------------------------------------------------------------


SAMPLE_RHUBARB_CUES: list[dict[str, Any]] = [
    {"start": 0.00, "end": 0.08, "value": "X"},
    {"start": 0.08, "end": 0.16, "value": "A"},
    {"start": 0.16, "end": 0.30, "value": "E"},
    {"start": 0.30, "end": 0.40, "value": "F"},
    {"start": 0.40, "end": 0.55, "value": "B"},
    {"start": 0.55, "end": 0.65, "value": "C"},
    {"start": 0.65, "end": 0.80, "value": "G"},
    {"start": 0.80, "end": 1.00, "value": "X"},
]
