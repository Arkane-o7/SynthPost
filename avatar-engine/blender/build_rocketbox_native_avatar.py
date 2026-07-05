"""Build a native-Rocketbox animated GLB for the custom Three.js renderer.

This is intentionally different from build_rocketbox_avatar.py:

- Keeps Rocketbox/Biped body bone names (`Bip01 ...`) so Rocketbox's own
  animation FBXs can play directly.
- Renames only facial blend shapes to renderer-friendly names:
  `AA_VI_*` -> `viseme_*`, `AK_*` -> ARKit camelCase.
- Imports a curated set of Rocketbox male anchor-friendly animation FBXs and
  stores each as a separate GLB animation clip.
- Exports one self-contained GLB used by the `rocketbox` renderer.

Run from desk-avatar-engine root:

  /Applications/Blender.app/Contents/MacOS/Blender --background \
    --python blender/build_rocketbox_native_avatar.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
ROCKETBOX_ROOT = PROJECT_ROOT.parent / "Microsoft-Rocketbox"
CHAR_ROOT = ROCKETBOX_ROOT / "Assets/Avatars/Professions/Business_Male_01"
ANIM_ROOT = ROCKETBOX_ROOT / "Assets/Animations/all_animations_max_motextr_static"

AVATAR_FBX = CHAR_ROOT / "Export" / "Business_Male_01_facial.fbx"
TEXTURE_DIR = CHAR_ROOT / "Textures"
OUTPUT_GLB = PROJECT_ROOT / "assets/avatars/business_male_01/avatar.glb"

# Conservative anchor-friendly animation set. Static = no walking/root motion.
ANIMATION_FILES: dict[str, str] = {
    "idle_neutral_01": "m_idle_neutral_01.max.fbx",
    "idle_neutral_02": "m_idle_neutral_02.max.fbx",
    "idle_breathe_01": "m_idle_breathe_01.max.fbx",
    "talk_neutral_01": "m_gestic_talk_neutral_01.max.fbx",
    "talk_neutral_02": "m_gestic_talk_neutral_02.max.fbx",
    "talk_relaxed_01": "m_gestic_talk_relaxed_01.max.fbx",
    "talk_relaxed_02": "m_gestic_talk_relaxed_02.max.fbx",
    "presentation_left_01": "m_gestic_presentation_left_01.max.fbx",
    "presentation_right_01": "m_gestic_presentation_right_01.max.fbx",
    "shrug_01": "m_gestic_shrug_01.max.fbx",
}

VISEME_RENAME: dict[str, str] = {
    "AA_VI_00_Sil": "viseme_sil",
    "AA_VI_01_PP": "viseme_PP",
    "AA_VI_02_FF": "viseme_FF",
    "AA_VI_03_TH": "viseme_TH",
    "AA_VI_04_DD": "viseme_DD",
    "AA_VI_05_KK": "viseme_kk",
    "AA_VI_06_CH": "viseme_CH",
    "AA_VI_07_SS": "viseme_SS",
    "AA_VI_08_nn": "viseme_nn",
    "AA_VI_09_RR": "viseme_RR",
    "AA_VI_10_aa": "viseme_aa",
    "AA_VI_11_E": "viseme_E",
    "AA_VI_12_I": "viseme_I",
    "AA_VI_13_O": "viseme_O",
    "AA_VI_14_U": "viseme_U",
}

ARKIT_RENAME: dict[str, str] = {
    "AK_01_BrowDownLeft": "browDownLeft",
    "AK_02_BrowDownRight": "browDownRight",
    "AK_03_BrowInnerUp": "browInnerUp",
    "AK_04_BrowOuterUpLeft": "browOuterUpLeft",
    "AK_05_BrowOuterUpRight": "browOuterUpRight",
    "AK_06_CheekPuff": "cheekPuff",
    "AK_07_CheekSquintLeft": "cheekSquintLeft",
    "AK_08_CheekSquintRight": "cheekSquintRight",
    "AK_09_EyeBlinkLeft": "eyeBlinkLeft",
    "AK_10_EyeBlinkRight": "eyeBlinkRight",
    "AK_11_EyeLookDownLeft": "eyeLookDownLeft",
    "AK_12_EyeLookDownRight": "eyeLookDownRight",
    "AK_13_EyeLookInLeft": "eyeLookInLeft",
    "AK_14_EyeLookInRight": "eyeLookInRight",
    "AK_15_EyeLookOutLeft": "eyeLookOutLeft",
    "AK_16_EyeLookOutRight": "eyeLookOutRight",
    "AK_17_EyeLookUpLeft": "eyeLookUpLeft",
    "AK_18_EyeLookUpRight": "eyeLookUpRight",
    "AK_19_EyeSquintLeft": "eyeSquintLeft",
    "AK_20_EyeSquintRight": "eyeSquintRight",
    "AK_21_EyeWideLeft": "eyeWideLeft",
    "AK_22_EyeWideRight": "eyeWideRight",
    "AK_23_JawForward": "jawForward",
    "AK_24_JawLeft": "jawLeft",
    "AK_25_JawOpen": "jawOpen",
    "AK_26_JawRight": "jawRight",
    "AK_27_MouthClose": "mouthClose",
    "AK_28_MouthDimpleLeft": "mouthDimpleLeft",
    "AK_29_MouthDimpleRight": "mouthDimpleRight",
    "AK_30_MouthFrownLeft": "mouthFrownLeft",
    "AK_31_MouthFrownRight": "mouthFrownRight",
    "AK_32_MouthFunnel": "mouthFunnel",
    "AK_33_MouthLeft": "mouthLeft",
    "AK_34_MouthLowerDownLeft": "mouthLowerDownLeft",
    "AK_35_MouthLowerDownRight": "mouthLowerDownRight",
    "AK_36_MouthPressLeft": "mouthPressLeft",
    "AK_37_MouthPressRight": "mouthPressRight",
    "AK_38_MouthPucker": "mouthPucker",
    "AK_39_MouthRight": "mouthRight",
    "AK_40_MouthRollLower": "mouthRollLower",
    "AK_41_MouthRollUpper": "mouthRollUpper",
    "AK_42_MouthShrugLower": "mouthShrugLower",
    "AK_43_MouthShrugUpper": "mouthShrugUpper",
    "AK_44_MouthSmileLeft": "mouthSmileLeft",
    "AK_45_MouthSmileRight": "mouthSmileRight",
    "AK_46_MouthStretchLeft": "mouthStretchLeft",
    "AK_47_MouthStretchRight": "mouthStretchRight",
    "AK_48_MouthUpperUpLeft": "mouthUpperUpLeft",
    "AK_49_MouthUpperUpRight": "mouthUpperUpRight",
    "AK_50_NoseSneerLeft": "noseSneerLeft",
    "AK_51_NoseSneerRight": "noseSneerRight",
    "AK_52_TongueOut": "tongueOut",
}

TEXTURE_FILES = [
    "m005_body_color.tga",
    "m005_body_normal.tga",
    "m005_body_specular.tga",
    "m005_head_color.tga",
    "m005_head_normal.tga",
    "m005_head_specular.tga",
    "m005_opacity_color.tga",
]


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for collection in (
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.materials,
        bpy.data.images,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.actions,
    ):
        for item in list(collection):
            collection.remove(item)
    print("[native-build] Scene cleared.")


def import_fbx(path: Path, *, use_anim: bool) -> list[bpy.types.Object]:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(
        filepath=str(path),
        use_anim=use_anim,
        automatic_bone_orientation=False,
        ignore_leaf_bones=False,
        force_connect_children=False,
    )
    return [obj for obj in bpy.data.objects if obj not in before]


def import_avatar() -> bpy.types.Object:
    if not AVATAR_FBX.exists():
        sys.exit(f"[native-build] ERROR: avatar FBX missing: {AVATAR_FBX}")
    print(f"[native-build] Importing avatar: {AVATAR_FBX}")
    import_fbx(AVATAR_FBX, use_anim=False)

    # The FBX file itself should contain one avatar armature named Bip01.
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if not armatures:
        sys.exit("[native-build] ERROR: no armature found after avatar import.")
    avatar_armature = armatures[0]
    avatar_armature.name = "Bip01"
    avatar_armature.data.name = "Bip01"
    print(f"[native-build] Avatar armature: {avatar_armature.name}")

    # Remove imported/default cameras/lights/non-avatar primitive meshes.
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT", "EMPTY"}:
            bpy.data.objects.remove(obj, do_unlink=True)
        elif obj.type == "MESH" and not obj.data.shape_keys:
            # Business_Male_01 is the only morph mesh we need; this removes stray Cube etc.
            bpy.data.objects.remove(obj, do_unlink=True)

    return avatar_armature


def relink_textures() -> None:
    local_tex = {name.lower(): TEXTURE_DIR / name for name in TEXTURE_FILES}
    for img in bpy.data.images:
        filename = Path(img.filepath).name.lower()
        if filename in local_tex and local_tex[filename].exists():
            img.filepath = str(local_tex[filename])
            img.reload()
    print("[native-build] Textures relinked.")


def fix_opacity_material() -> None:
    mat = bpy.data.materials.get("m005_opacity")
    if not mat:
        return
    mat.blend_method = "BLEND"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "CLIP"
    mat.use_backface_culling = False
    if not mat.use_nodes:
        return
    nt = mat.node_tree
    bsdf = next((node for node in nt.nodes if node.type == "BSDF_PRINCIPLED"), None)
    if not bsdf:
        return
    for link in list(nt.links):
        if (
            link.to_node == bsdf
            and link.to_socket.name == "Alpha"
            and link.from_node.type == "TEX_IMAGE"
        ):
            image_node = link.from_node
            nt.links.remove(link)
            nt.links.new(image_node.outputs["Alpha"], bsdf.inputs["Alpha"])
            break
    print("[native-build] Opacity material fixed.")


def rename_shape_keys() -> None:
    rename = {**VISEME_RENAME, **ARKIT_RENAME}
    visemes = 0
    arkit = 0
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.data.shape_keys:
            continue
        for key in obj.data.shape_keys.key_blocks:
            if key.name in rename:
                if key.name in VISEME_RENAME:
                    visemes += 1
                else:
                    arkit += 1
                key.name = rename[key.name]
    print(f"[native-build] Shape keys renamed: {visemes} visemes, {arkit} ARKit.")


def safe_action_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name.strip())
    return re.sub(r"_+", "_", name).strip("_")


def clear_object_animation(obj: bpy.types.Object) -> None:
    if obj.animation_data:
        obj.animation_data_clear()


def import_animation_clip(
    base_armature: bpy.types.Object, clip_name: str, fbx_name: str
) -> None:
    path = ANIM_ROOT / fbx_name
    if not path.exists():
        print(f"[native-build] WARNING: animation missing, skipped: {path}")
        return

    print(f"[native-build] Importing animation: {clip_name} ← {fbx_name}")
    new_objects = import_fbx(path, use_anim=True)
    anim_armatures = [obj for obj in new_objects if obj.type == "ARMATURE"]
    if not anim_armatures:
        print(f"[native-build] WARNING: no armature in animation {fbx_name}; skipped.")
        return

    source = anim_armatures[0]
    action = source.animation_data.action if source.animation_data else None
    if action is None:
        print(f"[native-build] WARNING: no action in animation {fbx_name}; skipped.")
        for obj in new_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        return

    copied = action.copy()
    copied.name = safe_action_name(clip_name)
    copied.use_fake_user = True

    base_armature.animation_data_create()
    track = base_armature.animation_data.nla_tracks.new()
    track.name = copied.name
    start = int(copied.frame_range[0])
    strip = track.strips.new(copied.name, start, copied)
    strip.action_frame_start = copied.frame_range[0]
    strip.action_frame_end = copied.frame_range[1]

    # Assign once so Blender marks it as associated with this armature; leave NLA tracks for export.
    base_armature.animation_data.action = copied

    for obj in new_objects:
        bpy.data.objects.remove(obj, do_unlink=True)
    print(f"[native-build] Added clip: {copied.name} frames {copied.frame_range[:]}.")


def import_animation_set(base_armature: bpy.types.Object) -> None:
    # The base FBX was imported without animation; add Rocketbox native actions now.
    for clip_name, filename in ANIMATION_FILES.items():
        import_animation_clip(base_armature, clip_name, filename)

    if base_armature.animation_data:
        base_armature.animation_data.action = None

    # Blender keeps the original imported action data-blocks even after deleting
    # each temporary FBX armature. Remove those source actions so the GLB contains
    # only our clean, named clips.
    wanted = {safe_action_name(name) for name in ANIMATION_FILES}
    for action in list(bpy.data.actions):
        if action.name not in wanted:
            bpy.data.actions.remove(action)

    print(f"[native-build] Total clean actions: {len(bpy.data.actions)}")


def verify() -> None:
    print("\n[native-build] ── Verification ─────────────────────────────")
    for obj in bpy.data.objects:
        print(f"  Object: {obj.name} type={obj.type}")
        if obj.type == "ARMATURE":
            print(
                f"    Bones: {len(obj.data.bones)}; sample={[b.name for b in obj.data.bones[:6]]}"
            )
        if obj.type == "MESH" and obj.data.shape_keys:
            keys = [k.name for k in obj.data.shape_keys.key_blocks]
            missing = [name for name in VISEME_RENAME.values() if name not in keys]
            print(f"    Shape keys: {len(keys)}; visemes={15 - len(missing)}/15")
            if missing:
                print(f"    Missing visemes: {missing}")
    print(f"  Actions: {[a.name for a in bpy.data.actions]}")
    print("[native-build] ─────────────────────────────────────────────\n")


def export_glb() -> None:
    OUTPUT_GLB.parent.mkdir(parents=True, exist_ok=True)
    print(f"[native-build] Exporting GLB: {OUTPUT_GLB}")
    bpy.ops.export_scene.gltf(
        filepath=str(OUTPUT_GLB),
        export_format="GLB",
        export_apply=False,
        export_normals=True,
        export_texcoords=True,
        export_attributes=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_morph=True,
        export_morph_normal=True,
        export_morph_tangent=False,
        export_skins=True,
        export_all_influences=False,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_force_sampling=True,
        export_frame_range=False,
        export_cameras=False,
        export_lights=False,
        export_yup=True,
    )
    print(
        f"[native-build] Wrote {OUTPUT_GLB} ({OUTPUT_GLB.stat().st_size / 1048576:.1f} MB)"
    )


def main() -> None:
    print("\n[native-build] ══ Rocketbox native animated avatar build ══")
    clear_scene()
    base = import_avatar()
    relink_textures()
    fix_opacity_material()
    rename_shape_keys()
    import_animation_set(base)
    verify()
    export_glb()
    print("[native-build] ══ Done ═════════════════════════════════════\n")


main()
