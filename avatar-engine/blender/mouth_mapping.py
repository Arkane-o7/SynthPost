from __future__ import annotations

RHU_BARBS = ("A", "B", "C", "D", "E", "F", "G", "H", "X")

CUE_LABELS: dict[str, str] = {
    "A": "closed/rest",
    "B": "M/B/P",
    "C": "E/I",
    "D": "A/open",
    "E": "O",
    "F": "U/W",
    "G": "F/V",
    "H": "L",
    "X": "closed/rest",
}

TEXTURE_MOUTH_MAP: dict[str, str] = {
    "A": "mouth_A.png",
    "B": "mouth_B.png",
    "C": "mouth_C.png",
    "D": "mouth_D.png",
    "E": "mouth_E.png",
    "F": "mouth_F.png",
    "G": "mouth_G.png",
    "H": "mouth_H.png",
    "X": "mouth_X.png",
}

SHAPE_KEY_MOUTH_MAP: dict[str, str] = {
    "A": "mouth_closed",
    "B": "mouth_mbp",
    "C": "mouth_ee",
    "D": "mouth_aa",
    "E": "mouth_oh",
    "F": "mouth_oo",
    "G": "mouth_fv",
    "H": "mouth_lth",
    "X": "mouth_rest",
}

MOUTH_CUE_INDEX: dict[str, int] = {cue: index for index, cue in enumerate(RHU_BARBS)}


def texture_for_cue(cue: str) -> str:
    return TEXTURE_MOUTH_MAP.get(cue.upper(), TEXTURE_MOUTH_MAP["X"])


def shape_key_for_cue(cue: str) -> str:
    return SHAPE_KEY_MOUTH_MAP.get(cue.upper(), SHAPE_KEY_MOUTH_MAP["X"])
