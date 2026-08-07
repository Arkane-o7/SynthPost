"""Build a reusable CC Action library from native CC or Mixamo FBX clips.

Run through Blender, for example::

  Blender --background --factory-startup --python blender/build_cc_motion_library.py -- \
    --avatar assets/avatars/synthpost_anchor_v1/anchor.glb \
    --manifest assets/motions/synthpost_anchor_v1/motions.json \
    --source IDLE_Neutral=/absolute/path/to/idle.fbx

Source motion binaries and the generated .blend/GLB files are intentionally
local assets and should not be committed without a compatible redistribution
license.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import bpy
from mathutils import Matrix, Quaternion


MIXAMO_TO_CC = {
    "mixamorig:Hips": "CC_Base_Hip",
    "mixamorig:Spine": "CC_Base_Waist",
    "mixamorig:Spine1": "CC_Base_Spine01",
    "mixamorig:Spine2": "CC_Base_Spine02",
    "mixamorig:LeftShoulder": "CC_Base_L_Clavicle",
    "mixamorig:LeftArm": "CC_Base_L_Upperarm",
    "mixamorig:LeftForeArm": "CC_Base_L_Forearm",
    "mixamorig:LeftHand": "CC_Base_L_Hand",
    "mixamorig:RightShoulder": "CC_Base_R_Clavicle",
    "mixamorig:RightArm": "CC_Base_R_Upperarm",
    "mixamorig:RightForeArm": "CC_Base_R_Forearm",
    "mixamorig:RightHand": "CC_Base_R_Hand",
    "mixamorig:LeftUpLeg": "CC_Base_L_Thigh",
    "mixamorig:LeftLeg": "CC_Base_L_Calf",
    "mixamorig:LeftFoot": "CC_Base_L_Foot",
    "mixamorig:LeftToeBase": "CC_Base_L_ToeBase",
    "mixamorig:RightUpLeg": "CC_Base_R_Thigh",
    "mixamorig:RightLeg": "CC_Base_R_Calf",
    "mixamorig:RightFoot": "CC_Base_R_Foot",
    "mixamorig:RightToeBase": "CC_Base_R_ToeBase",
}

for side, source_side in (("L", "Left"), ("R", "Right")):
    for cc_name, mixamo_name in (
        ("Thumb", "Thumb"),
        ("Index", "Index"),
        ("Mid", "Middle"),
        ("Ring", "Ring"),
        ("Pinky", "Pinky"),
    ):
        for segment in (1, 2, 3):
            MIXAMO_TO_CC[
                f"mixamorig:{source_side}Hand{mixamo_name}{segment}"
            ] = f"CC_Base_{side}_{cc_name}{segment}"


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--avatar", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--fps", type=int, default=24)
    return parser.parse_args(argv)


def source_specs(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--source must be CLIP_ID=/path/to/file.fbx, got {value!r}")
        clip_id, raw_path = value.split("=", 1)
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"Motion source is missing: {path}")
        result[clip_id.strip()] = path
    return result


def armature_depth(bone: Any) -> int:
    depth = 0
    parent = bone.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def action_for_armature(armature: Any) -> Any | None:
    animation_data = armature.animation_data
    if animation_data and animation_data.action:
        return animation_data.action
    actions = list(bpy.data.actions)
    return actions[-1] if actions else None


def native_cc_mapping(source: Any, target: Any) -> dict[str, str]:
    target_names = {bone.name for bone in target.data.bones}
    common = {
        bone.name: bone.name for bone in source.data.bones if bone.name in target_names
    }
    return common if len(common) >= 15 else {}


def retarget_action(
    *,
    scene: Any,
    source: Any,
    target: Any,
    source_action: Any,
    action_name: str,
    source_fps: float,
    target_fps: int,
    amplitude: float,
    exclude_head: bool,
    relative_to_first_frame: bool,
) -> Any:
    mapping = native_cc_mapping(source, target) or {
        source_name: target_name
        for source_name, target_name in MIXAMO_TO_CC.items()
        if source.pose.bones.get(source_name) and target.pose.bones.get(target_name)
    }
    if len(mapping) < 12:
        raise RuntimeError(
            f"{action_name}: only {len(mapping)} compatible bones; use Reallusion Blender Auto Setup for this rig"
        )
    if exclude_head:
        mapping = {
            source_name: target_name
            for source_name, target_name in mapping.items()
            if target_name not in {"CC_Base_Head", "CC_Base_NeckTwist01", "CC_Base_NeckTwist02"}
        }

    start, end = (float(value) for value in source_action.frame_range)
    duration = max(1.0 / source_fps, (end - start) / source_fps)
    output_frames = max(2, int(math.ceil(duration * target_fps)) + 1)
    action = bpy.data.actions.new(action_name)
    action.use_fake_user = True
    target.animation_data_create()
    target.animation_data.action = action
    ordered = sorted(
        mapping.items(), key=lambda pair: armature_depth(target.data.bones[pair[1]])
    )

    source_world = source.matrix_world.copy()
    target_world_inverse = target.matrix_world.inverted()
    scene.frame_set(int(start), subframe=start % 1.0)
    source_reference = {
        source_name: source_world @ source.pose.bones[source_name].matrix
        for source_name, _target_name in ordered
    }
    if relative_to_first_frame:
        calibration = {
            "CC_Base_Waist": (0.012, 0.0, 0.0),
            "CC_Base_Spine01": (0.026, 0.0, 0.0),
            "CC_Base_Spine02": (0.034, 0.0, 0.0),
            "CC_Base_R_Upperarm": (0.08, 0.18, 1.48),
            "CC_Base_L_Upperarm": (0.08, -0.18, -1.48),
        }
        for target_name, xyz in calibration.items():
            pose_bone = target.pose.bones.get(target_name)
            if pose_bone is None:
                continue
            pose_bone.rotation_mode = "XYZ"
            pose_bone.rotation_euler = xyz
        bpy.context.view_layer.update()
    target_reference = {
        target_name: target.matrix_world @ target.pose.bones[target_name].matrix
        for _source_name, target_name in ordered
    }
    for output_index in range(output_frames):
        seconds = output_index / target_fps
        source_frame = min(end, start + seconds * source_fps)
        scene.frame_set(int(source_frame), subframe=source_frame % 1.0)
        desired: dict[str, Matrix] = {}
        for source_name, target_name in ordered:
            source_pose = source_world @ source.pose.bones[source_name].matrix
            if relative_to_first_frame:
                world_delta = source_pose @ source_reference[source_name].inverted()
                target_base = target_reference[target_name]
            else:
                source_rest = source_world @ source.data.bones[source_name].matrix_local
                world_delta = source_pose @ source_rest.inverted()
                target_base = target.matrix_world @ target.data.bones[target_name].matrix_local
            desired[target_name] = target_world_inverse @ world_delta @ target_base

        output_frame = output_index + 1
        for _source_name, target_name in ordered:
            pose_bone = target.pose.bones[target_name]
            pose_bone.rotation_mode = "QUATERNION"
            pose_bone.matrix = desired[target_name]
            rotation = pose_bone.rotation_quaternion.copy()
            if amplitude < 1.0:
                rotation = Quaternion().slerp(rotation, amplitude)
            pose_bone.location = (0.0, 0.0, 0.0)
            pose_bone.scale = (1.0, 1.0, 1.0)
            pose_bone.rotation_quaternion = rotation
            pose_bone.keyframe_insert(
                data_path="rotation_quaternion", frame=output_frame, group=target_name
            )

    action.frame_start = 1
    action.frame_end = output_frames
    target.animation_data.action = None
    return action


def export_action_glb(path: Path, armature: Any, action: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    armature.animation_data_create()
    armature.animation_data.action = action
    bpy.context.scene.frame_start = int(action.frame_range[0])
    bpy.context.scene.frame_end = int(action.frame_range[1])
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_animations=True,
        export_animation_mode="ACTIVE_ACTIONS",
        export_force_sampling=True,
        export_frame_range=True,
        export_skins=True,
    )
    armature.animation_data.action = None


def main() -> None:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = source_specs(args.source)
    missing = sorted(set(sources) - set(manifest.get("clips") or {}))
    if missing:
        raise SystemExit(f"Source clip IDs are absent from manifest: {', '.join(missing)}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.avatar.resolve()))
    target = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    target.name = "SynthPost_CC_Armature"
    target.animation_data_clear()
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)

    built: list[str] = []
    for clip_id, path in sources.items():
        before_objects = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=str(path))
        imported = [obj for obj in bpy.data.objects if obj not in before_objects]
        source = next(obj for obj in imported if obj.type == "ARMATURE")
        source_action = action_for_armature(source)
        if source_action is None:
            raise RuntimeError(f"{path} contains no armature Action")
        source_fps = bpy.context.scene.render.fps / max(
            bpy.context.scene.render.fps_base, 0.001
        )
        clip = manifest["clips"][clip_id]
        action = retarget_action(
            scene=bpy.context.scene,
            source=source,
            target=target,
            source_action=source_action,
            action_name=str(clip.get("action") or clip_id),
            source_fps=source_fps,
            target_fps=args.fps,
            amplitude=float(clip.get("amplitude", 1.0)),
            exclude_head=bool(clip.get("exclude_head", True)),
            relative_to_first_frame=bool(clip.get("relative_to_first_frame", False)),
        )
        if source.animation_data:
            source.animation_data.action = None
        if source_action != action:
            bpy.data.actions.remove(source_action)
        web_file = str(clip.get("web_file") or f"web/{clip_id}.glb")
        export_action_glb(manifest_path.parent / web_file, target, action)
        built.append(clip_id)
        for obj in imported:
            bpy.data.objects.remove(obj, do_unlink=True)

    library_path = manifest_path.parent / str(manifest["blender_library"])
    library_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.fps = args.fps
    bpy.ops.wm.save_as_mainfile(filepath=str(library_path), check_existing=False)
    print(
        "SYNTHPOST_MOTION_LIBRARY="
        + json.dumps(
            {"library": str(library_path), "clips": built, "fps": args.fps},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
