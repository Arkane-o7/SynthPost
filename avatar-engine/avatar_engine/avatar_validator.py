"""Avatar validation for TalkingHead 3D-face requirements.

Validation is metadata-driven for the spike.  The avatar.json declares its
capabilities; the validator enforces them before any render attempt begins.
GLB binary inspection (actual blendshape enumeration) is deferred to a future
Node.js helper that can run three-gltf-validator.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Required metadata fields / values for TalkingHead mode
# ---------------------------------------------------------------------------

REQUIRED_FACE_TYPE = "3d"

# Minimum set of viseme shape names the avatar must declare.
# Accepts both phonetic shorthand (aa, ih, ou, ee, oh) and
# RPM/Oculus-prefixed names (viseme_aa, viseme_I, viseme_U, …).
# Any one of each phoneme group satisfies the requirement.
MINIMUM_VISEME_SHAPES = {"aa", "ih", "ou", "ee", "oh"}

# Aliases: if any of these are present the corresponding minimum is satisfied.
# Includes TalkingHead/RPM/Oculus names plus Character Creator/Reallusion V_* names.
VISEME_ALIASES: dict[str, set[str]] = {
    "aa": {"aa", "viseme_aa", "V_Open", "V_Lip_Open"},
    "ih": {"ih", "viseme_I", "I", "V_Wide", "V_Lip_Open"},
    "ou": {"ou", "viseme_U", "U", "V_Tight_O", "V_Tight"},
    "ee": {"ee", "viseme_E", "E", "V_Wide"},
    "oh": {"oh", "viseme_O", "O", "V_Tight_O", "V_Open"},
}

# Acceptable blendshape profile identifiers
KNOWN_BLENDSHAPE_PROFILES = {
    "arkit",
    "vrm",
    "oculus",
    "talkinghead",
    "arkit_or_vrm",
    "arkit_or_vrm_or_custom",
    "rpm_arkit_oculus",  # Ready Player Me: ARKit + Oculus visemes
    "rpm_arkit",  # RPM with ARKit only
    "rpm_oculus",  # RPM with Oculus visemes only
    "oculus_viseme",
    "reallusion_viseme",  # Character Creator V_* viseme morphs
    "custom",
    "auto_detect",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_avatar_for_talkinghead(
    avatar_metadata: dict[str, Any],
    avatar_id: str = "",
    allow_2d_fallback: bool = False,
) -> dict[str, Any]:
    """Check avatar metadata declares 3D lip / viseme support.

    Parameters
    ----------
    avatar_metadata:
        Parsed content of the avatar's ``avatar.json``.
    avatar_id:
        Human-readable identifier used in error messages.
    allow_2d_fallback:
        If True, a 2D-face avatar is allowed (adds a warning instead of
        failing).  Should only be set when
        ``AVATAR_ENGINE_ALLOW_2D_FACE_FALLBACK=1``.

    Returns
    -------
    dict with keys ``status`` ("pass"/"fail"), ``avatar_id``,
    ``face_type``, ``supports_3d_lips``, ``blendshape_profile``,
    ``required_visemes_present``, ``missing_visemes``, and optional
    ``error`` / ``warnings``.

    Raises
    ------
    AvatarValidationError
        Immediately on any hard failure, unless ``allow_2d_fallback`` is set
        and the only failure is a non-3D face.
    """
    warnings: list[str] = []
    missing_visemes: list[str] = []

    face_type = str(avatar_metadata.get("face_type", "unknown")).lower()
    supports_3d_lips = bool(avatar_metadata.get("supports_3d_lips", False))
    supports_visemes = bool(avatar_metadata.get("supports_visemes", False))
    blendshape_profile = str(avatar_metadata.get("blendshape_profile", "unknown"))
    declared_visemes: list[str] = list(avatar_metadata.get("viseme_shapes", []))
    legacy_2d = bool(avatar_metadata.get("legacy_2d_face_supported", False))

    declared_set = {str(v).lower() for v in declared_visemes}
    # Also check Oculus-prefixed names from oculus_viseme_targets field
    oculus_targets: list[str] = list(avatar_metadata.get("oculus_viseme_targets", []))
    declared_set.update(str(v).lower() for v in oculus_targets)

    for required, aliases in VISEME_ALIASES.items():
        satisfied = any(alias.lower() in declared_set for alias in aliases)
        if not satisfied:
            missing_visemes.append(required)

    # --- face type check ---
    if face_type != REQUIRED_FACE_TYPE:
        msg = (
            f"Avatar '{avatar_id}' declares face_type='{face_type}'; "
            f"TalkingHead mode requires face_type='{REQUIRED_FACE_TYPE}'."
        )
        if allow_2d_fallback and legacy_2d:
            warnings.append(
                msg
                + " Falling back to legacy_2d (AVATAR_ENGINE_ALLOW_2D_FACE_FALLBACK=1)."
            )
        else:
            return _fail(
                avatar_id,
                face_type,
                supports_3d_lips,
                blendshape_profile,
                missing_visemes,
                msg,
            )

    # --- 3D lip support check ---
    if not supports_3d_lips:
        msg = (
            f"Avatar '{avatar_id}' does not declare supports_3d_lips=true. "
            "TalkingHead mode requires 3D lip/viseme controls."
        )
        return _fail(
            avatar_id,
            face_type,
            supports_3d_lips,
            blendshape_profile,
            missing_visemes,
            msg,
        )

    # --- viseme support check ---
    if not supports_visemes:
        warnings.append(
            f"Avatar '{avatar_id}' does not declare supports_visemes=true; "
            "TalkingHead will rely on declared viseme_shapes list only."
        )

    # --- minimum visemes check ---
    if missing_visemes:
        msg = (
            f"Avatar '{avatar_id}' is missing required viseme shapes: "
            f"{missing_visemes}. "
            "Declare them in avatar.json under 'viseme_shapes'."
        )
        return _fail(
            avatar_id,
            face_type,
            supports_3d_lips,
            blendshape_profile,
            missing_visemes,
            msg,
        )

    # --- blendshape profile ---
    if blendshape_profile.lower() not in KNOWN_BLENDSHAPE_PROFILES:
        warnings.append(
            f"Unrecognised blendshape_profile '{blendshape_profile}' in avatar.json. "
            "TalkingHead will use auto-detection."
        )

    return {
        "avatar_id": avatar_id,
        "face_type": face_type,
        "supports_3d_lips": supports_3d_lips,
        "blendshape_profile": blendshape_profile,
        "required_visemes_present": True,
        "missing_visemes": [],
        "status": "pass",
        "warnings": warnings,
    }


def load_avatar_metadata(metadata_path: Path) -> dict[str, Any]:
    """Load and parse avatar.json.  Raises on missing or malformed file."""
    if not metadata_path.exists():
        raise AvatarValidationError(f"Avatar metadata file not found: {metadata_path}")
    try:
        with metadata_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise AvatarValidationError(
            f"Cannot parse avatar.json at {metadata_path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise AvatarValidationError(
            f"Avatar metadata must be a JSON object: {metadata_path}"
        )
    return data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fail(
    avatar_id: str,
    face_type: str,
    supports_3d_lips: bool,
    blendshape_profile: str,
    missing_visemes: list[str],
    error_msg: str,
) -> dict[str, Any]:
    return {
        "avatar_id": avatar_id,
        "face_type": face_type,
        "supports_3d_lips": supports_3d_lips,
        "blendshape_profile": blendshape_profile,
        "required_visemes_present": len(missing_visemes) == 0,
        "missing_visemes": missing_visemes,
        "status": "fail",
        "error": error_msg,
    }


# ---------------------------------------------------------------------------
# Exception type
# ---------------------------------------------------------------------------


class AvatarValidationError(Exception):
    """Raised when avatar validation fails in a way that should abort render."""
