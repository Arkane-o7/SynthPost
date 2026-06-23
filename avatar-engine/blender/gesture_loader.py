from __future__ import annotations

from typing import Any

GESTURES = {
    "seated_idle",
    "hands_on_desk",
    "explain_small",
    "nod_yes",
    "point_camera",
}

ACTION_GESTURES = (
    "IDLE_Neutral",
    "HEAD_Nod_Small",
    "HEAD_Shake_Small",
    "RIGHT_Hand_Emphasis",
    "LEFT_Hand_Emphasis",
    "BOTH_Hands_Open",
    "LEAN_Forward",
    "LEAN_Back",
    "SHOULDER_Shrug",
    "RESET_Seated_Pose",
)


def find_armature(bpy_module: Any) -> Any | None:
    for obj in bpy_module.context.scene.objects:
        if getattr(obj, "type", "") == "ARMATURE":
            return obj
    print("[blender:gesture] WARNING: No armature found; skipping gestures.")
    return None


def find_avatar_armature(bpy_module: Any) -> Any | None:
    armature = bpy_module.data.objects.get("ARM_Avatar")
    if armature is None:
        print("[blender:action] WARNING: ARM_Avatar missing; skipping Action gestures.")
        return None
    if getattr(armature, "type", "") != "ARMATURE":
        print("[blender:action] WARNING: ARM_Avatar is not an armature; skipping Action gestures.")
        return None
    return armature


def pose_bone(armature: Any, *names: str) -> Any | None:
    for name in names:
        bone = armature.pose.bones.get(name)
        if bone is not None:
            return bone
    print(f"[blender:gesture] WARNING: Missing expected bone from {names}; skipping that motion.")
    return None


def key_bone_rotation(bone: Any, frame: int, rotation: tuple[float, float, float]) -> None:
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = rotation
    bone.keyframe_insert(data_path="rotation_euler", frame=frame)


def apply_placeholder_gesture(bpy_module: Any, gesture_name: str, start_frame: int, end_frame: int) -> None:
    if gesture_name not in GESTURES:
        print(f"[blender:gesture] WARNING: Unknown gesture '{gesture_name}', skipping.")
        return

    armature = find_armature(bpy_module)
    if armature is None:
        return

    # TODO: Replace these procedural rotations with loaded Blender Actions.
    mid_frame = max(start_frame + 1, (start_frame + end_frame) // 2)
    head = pose_bone(armature, "Head", "head", "DEF-head")
    left_arm = pose_bone(armature, "UpperArm.L", "upper_arm.L", "DEF-upper_arm.L")
    right_arm = pose_bone(armature, "UpperArm.R", "upper_arm.R", "DEF-upper_arm.R")
    right_hand = pose_bone(armature, "Hand.R", "hand.R", "DEF-hand.R")

    if gesture_name == "seated_idle":
        if head:
            key_bone_rotation(head, start_frame, (0.0, 0.0, 0.0))
            key_bone_rotation(head, end_frame, (0.03, 0.0, 0.0))
    elif gesture_name == "hands_on_desk":
        for bone in (left_arm, right_arm):
            if bone:
                key_bone_rotation(bone, start_frame, (0.35, 0.0, 0.0))
                key_bone_rotation(bone, end_frame, (0.35, 0.0, 0.0))
    elif gesture_name == "explain_small":
        if right_arm:
            key_bone_rotation(right_arm, start_frame, (0.25, 0.0, -0.15))
            key_bone_rotation(right_arm, mid_frame, (0.55, 0.1, -0.35))
            key_bone_rotation(right_arm, end_frame, (0.25, 0.0, -0.15))
    elif gesture_name == "nod_yes":
        if head:
            key_bone_rotation(head, start_frame, (0.0, 0.0, 0.0))
            key_bone_rotation(head, mid_frame, (0.18, 0.0, 0.0))
            key_bone_rotation(head, end_frame, (0.0, 0.0, 0.0))
    elif gesture_name == "point_camera":
        if right_arm:
            key_bone_rotation(right_arm, start_frame, (0.2, -0.25, -0.25))
            key_bone_rotation(right_arm, mid_frame, (0.85, -0.45, -0.15))
            key_bone_rotation(right_arm, end_frame, (0.2, -0.25, -0.25))
        if right_hand:
            key_bone_rotation(right_hand, mid_frame, (0.0, 0.0, -0.2))

    print(f"[blender:gesture] Applied placeholder gesture '{gesture_name}'.")


def action_frame_length(action: Any) -> float:
    start, end = action.frame_range
    return max(1.0, float(end) - float(start))


def make_action_strip(track: Any, name: str, action: Any, start_frame: int) -> Any | None:
    try:
        return track.strips.new(name=name, start=start_frame, action=action)
    except Exception as exc:
        print(f"[blender:action] WARNING: Could not create NLA strip '{name}': {exc}")
        return None


def configure_action_strip(
    strip: Any,
    action: Any,
    start_frame: int,
    duration_frames: int | None,
    strength: float,
    blend_in: int,
    blend_out: int,
    repeat_to_frame: int | None = None,
) -> None:
    action_start, action_end = action.frame_range
    strip.action_frame_start = action_start
    strip.action_frame_end = action_end
    strip.frame_start = start_frame
    if repeat_to_frame is not None:
        strip.frame_end = repeat_to_frame
        try:
            strip.repeat = max(1.0, (repeat_to_frame - start_frame) / action_frame_length(action))
        except Exception:
            pass
    elif duration_frames is not None:
        strip.frame_end = max(start_frame + 1, start_frame + duration_frames)
    try:
        strip.influence = max(0.0, min(1.0, strength))
    except Exception:
        pass
    for attr, value in (("blend_in", blend_in), ("blend_out", blend_out)):
        try:
            setattr(strip, attr, max(0, value))
        except Exception:
            pass
    try:
        strip.blend_type = "COMBINE"
    except Exception:
        pass


def apply_idle_action(bpy_module: Any, armature: Any, start_frame: int, end_frame: int) -> None:
    action = bpy_module.data.actions.get("IDLE_Neutral")
    if action is None:
        print("[blender:action] WARNING: Optional idle Action 'IDLE_Neutral' missing; continuing without idle.")
        return

    animation_data = armature.animation_data_create()
    track = animation_data.nla_tracks.new()
    track.name = "desk_avatar_idle"
    strip = make_action_strip(track, "IDLE_Neutral", action, start_frame)
    if strip is None:
        return
    configure_action_strip(
        strip=strip,
        action=action,
        start_frame=start_frame,
        duration_frames=None,
        strength=0.35,
        blend_in=0,
        blend_out=0,
        repeat_to_frame=max(end_frame, start_frame + 1),
    )
    print("[blender:action] Applied looping idle Action 'IDLE_Neutral'.")


def apply_action_gestures(bpy_module: Any, job: dict[str, Any], fps: int, start_frame: int, end_frame: int) -> None:
    armature = find_avatar_armature(bpy_module)
    if armature is None:
        return

    apply_idle_action(bpy_module, armature, start_frame, end_frame)

    gestures = job.get("gestures", [])
    if not gestures:
        print("[blender:action] No Action gestures provided in job.")
        return
    if not isinstance(gestures, list):
        print("[blender:action] WARNING: Job field 'gestures' must be an array; skipping Action gestures.")
        return

    animation_data = armature.animation_data_create()
    track = animation_data.nla_tracks.new()
    track.name = "desk_avatar_gestures"

    applied = 0
    for index, gesture in enumerate(gestures):
        if not isinstance(gesture, dict):
            print(f"[blender:action] WARNING: Gesture #{index + 1} is not an object; skipping.")
            continue
        action_name = str(gesture.get("action", "")).strip()
        if not action_name:
            print(f"[blender:action] WARNING: Gesture #{index + 1} is missing 'action'; skipping.")
            continue
        action = bpy_module.data.actions.get(action_name)
        if action is None:
            print(f"[blender:action] WARNING: Missing Action '{action_name}'; skipping gesture.")
            continue

        start = seconds_to_frame(float(gesture.get("time", 0.0)), fps)
        duration = gesture.get("duration")
        duration_frames = None
        if duration is not None:
            duration_frames = max(1, int(round(float(duration) * fps)))
        strength = float(gesture.get("strength", 1.0))
        blend_in = int(round(float(gesture.get("blend_in", 0.1)) * fps))
        blend_out = int(round(float(gesture.get("blend_out", 0.15)) * fps))

        strip = make_action_strip(track, f"{action_name}_{index + 1}", action, start)
        if strip is None:
            continue
        configure_action_strip(strip, action, start, duration_frames, strength, blend_in, blend_out)
        applied += 1
        print(f"[blender:action] Applied Action '{action_name}' at frame {start}.")

    print(f"[blender:action] Applied {applied} Action gesture(s).")


def seconds_to_frame(seconds: float, fps: int) -> int:
    return max(1, int(round(seconds * fps)) + 1)
