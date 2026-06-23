from __future__ import annotations

from typing import Any

EXPRESSION_PRESETS: dict[str, dict[str, float]] = {
    "calm": {
        "brow_inner_up": 0.1,
        "eyes_relaxed": 0.25,
        "mouth_smile": 0.05,
    },
    "focused": {
        "brow_down_left": 0.3,
        "brow_down_right": 0.3,
        "eyes_squint": 0.2,
    },
    "smile": {
        "mouth_smile": 0.75,
        "cheek_raise": 0.35,
        "eyes_squint": 0.15,
    },
    "surprised": {
        "brow_inner_up": 0.8,
        "brow_outer_up_left": 0.6,
        "brow_outer_up_right": 0.6,
        "eyes_wide": 0.7,
        "jaw_open": 0.35,
    },
    "confused": {
        "brow_down_left": 0.45,
        "brow_outer_up_right": 0.45,
        "mouth_frown": 0.25,
    },
    "serious": {
        "brow_down_left": 0.45,
        "brow_down_right": 0.45,
        "mouth_press": 0.25,
        "eyes_squint": 0.25,
    },
}


def apply_expression_preset(mesh_object: Any, preset_name: str, frame: int) -> None:
    preset = EXPRESSION_PRESETS.get(preset_name)
    if preset is None:
        print(f"[blender:expression] WARNING: Unknown expression preset '{preset_name}'.")
        return

    shape_keys = getattr(getattr(mesh_object, "data", None), "shape_keys", None)
    key_blocks = getattr(shape_keys, "key_blocks", None)
    if key_blocks is None:
        print(f"[blender:expression] WARNING: Object '{mesh_object.name}' has no shape keys.")
        return

    for key_name, weight in preset.items():
        key = key_blocks.get(key_name)
        if key is None:
            print(f"[blender:expression] WARNING: Missing shape key '{key_name}', skipping.")
            continue
        key.value = weight
        key.keyframe_insert("value", frame=frame)
