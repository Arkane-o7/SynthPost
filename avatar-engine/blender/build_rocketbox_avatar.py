"""build_rocketbox_avatar.py

Converts Microsoft Rocketbox Business_Male_01_facial.fbx into a
TalkingHead-compatible GLB ready to drop into the avatar engine pipeline.

What this script does
---------------------
1.  Clears the default Blender scene.
2.  Imports Business_Male_01_facial.fbx (mesh + full rig + all blend shapes).
3.  Re-links every texture image to the correct local Textures/ folder
    (the FBX encodes Windows absolute paths that don't exist on macOS).
4.  Enables ALPHA_BLEND on the hair/opacity material and fixes its alpha link.
5.  Renames the 15 Rocketbox AA_VI_XX_* viseme shape keys to the
    TalkingHead/Oculus names  (viseme_sil, viseme_PP, … viseme_U).
6.  Renames the 52 AK_XX_* ARKit shape keys to camelCase
    (browDownLeft, eyeBlinkLeft, jawOpen, mouthSmileLeft, …).
7.  Retargets the Biped bone names to the Mixamo/RPM convention that
    TalkingHead's animation system expects
    (Bip01 Pelvis → Hips, Bip01 L UpperArm → LeftArm, …).
8.  Deletes the default Cube object left by a fresh Blender session.
9.  Exports the result as a self-contained GLB (textures embedded).

Run (headless, from project root):
  /Applications/Blender.app/Contents/MacOS/Blender --background \\
      --python blender/build_rocketbox_avatar.py

Outputs:
  assets/avatars/business_male_01/avatar.glb
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

# This script lives in  desk-avatar-engine/blender/
_SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _SCRIPT_DIR.parent  # desk-avatar-engine/
ROCKETBOX_ROOT = PROJECT_ROOT.parent / "Microsoft-Rocketbox"
CHAR_ROOT = ROCKETBOX_ROOT / "Assets/Avatars/Professions/Business_Male_01"

FBX_PATH = CHAR_ROOT / "Export" / "Business_Male_01_facial.fbx"
TEXTURE_DIR = CHAR_ROOT / "Textures"
OUTPUT_GLB = PROJECT_ROOT / "assets/avatars/business_male_01/avatar.glb"

# ---------------------------------------------------------------------------
# Shape-key rename tables
# ---------------------------------------------------------------------------

# Rocketbox AA_VI prefix  →  TalkingHead/Oculus viseme names
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

# Rocketbox AK prefix  →  ARKit camelCase names (used by TalkingHead expressions)
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

# ---------------------------------------------------------------------------
# Bone rename table  — 3ds Max Biped  →  Mixamo / ReadyPlayerMe convention
# ---------------------------------------------------------------------------
# TalkingHead drives idle / gesture animations using Mixamo bone names.
# Face bones (jaw, eyes) below the head are left as-is; TalkingHead
# handles face motion entirely through blend shapes.
BONE_RENAME: dict[str, str] = {
    # ── Spine / torso ──────────────────────────────────────────────────────
    "Bip01 Pelvis": "Hips",
    "Bip01 Spine": "Spine",
    "Bip01 Spine1": "Spine1",
    "Bip01 Spine2": "Spine2",
    "Bip01 Neck": "Neck",
    "Bip01 Head": "Head",
    # ── Eyes (TalkingHead uses these for procedural gaze) ──────────────────
    "Bip01 REye": "RightEye",
    "Bip01 LEye": "LeftEye",
    # ── Left arm ───────────────────────────────────────────────────────────
    "Bip01 L Clavicle": "LeftShoulder",
    "Bip01 L UpperArm": "LeftArm",
    "Bip01 L Forearm": "LeftForeArm",
    "Bip01 L Hand": "LeftHand",
    # ── Left fingers ───────────────────────────────────────────────────────
    "Bip01 L Finger0": "LeftHandThumb1",
    "Bip01 L Finger01": "LeftHandThumb2",
    "Bip01 L Finger02": "LeftHandThumb3",
    "Bip01 L Finger1": "LeftHandIndex1",
    "Bip01 L Finger11": "LeftHandIndex2",
    "Bip01 L Finger12": "LeftHandIndex3",
    "Bip01 L Finger2": "LeftHandMiddle1",
    "Bip01 L Finger21": "LeftHandMiddle2",
    "Bip01 L Finger22": "LeftHandMiddle3",
    "Bip01 L Finger3": "LeftHandRing1",
    "Bip01 L Finger31": "LeftHandRing2",
    "Bip01 L Finger32": "LeftHandRing3",
    "Bip01 L Finger4": "LeftHandPinky1",
    "Bip01 L Finger41": "LeftHandPinky2",
    "Bip01 L Finger42": "LeftHandPinky3",
    # ── Right arm ──────────────────────────────────────────────────────────
    "Bip01 R Clavicle": "RightShoulder",
    "Bip01 R UpperArm": "RightArm",
    "Bip01 R Forearm": "RightForeArm",
    "Bip01 R Hand": "RightHand",
    # ── Right fingers ──────────────────────────────────────────────────────
    "Bip01 R Finger0": "RightHandThumb1",
    "Bip01 R Finger01": "RightHandThumb2",
    "Bip01 R Finger02": "RightHandThumb3",
    "Bip01 R Finger1": "RightHandIndex1",
    "Bip01 R Finger11": "RightHandIndex2",
    "Bip01 R Finger12": "RightHandIndex3",
    "Bip01 R Finger2": "RightHandMiddle1",
    "Bip01 R Finger21": "RightHandMiddle2",
    "Bip01 R Finger22": "RightHandMiddle3",
    "Bip01 R Finger3": "RightHandRing1",
    "Bip01 R Finger31": "RightHandRing2",
    "Bip01 R Finger32": "RightHandRing3",
    "Bip01 R Finger4": "RightHandPinky1",
    "Bip01 R Finger41": "RightHandPinky2",
    "Bip01 R Finger42": "RightHandPinky3",
    # ── Legs ───────────────────────────────────────────────────────────────
    "Bip01 L Thigh": "LeftUpLeg",
    "Bip01 L Calf": "LeftLeg",
    "Bip01 L Foot": "LeftFoot",
    "Bip01 L Toe0": "LeftToeBase",
    "Bip01 R Thigh": "RightUpLeg",
    "Bip01 R Calf": "RightLeg",
    "Bip01 R Foot": "RightFoot",
    "Bip01 R Toe0": "RightToeBase",
}

# ---------------------------------------------------------------------------
# Texture filename  →  correct local path
# ---------------------------------------------------------------------------
TEXTURE_FILES = [
    "m005_body_color.tga",
    "m005_body_normal.tga",
    "m005_body_specular.tga",
    "m005_head_color.tga",
    "m005_head_normal.tga",
    "m005_head_specular.tga",
    "m005_opacity_color.tga",
]


# ===========================================================================
# Steps
# ===========================================================================


def step_clear_scene() -> None:
    """Remove everything from the default Blender scene."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block_collection in (
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.materials,
        bpy.data.images,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for item in list(block_collection):
            block_collection.remove(item)
    print("[build] Scene cleared.")


def step_import_fbx() -> None:
    """Import the facial FBX. It contains mesh + Biped rig + all blend shapes."""
    if not FBX_PATH.exists():
        sys.exit(f"[build] ERROR: FBX not found: {FBX_PATH}")
    print(f"[build] Importing FBX: {FBX_PATH}")
    bpy.ops.import_scene.fbx(
        filepath=str(FBX_PATH),
        use_anim=False,  # no animation data needed
        automatic_bone_orientation=False,
        ignore_leaf_bones=False,  # keep all bones — Rocketbox has no Nub bones,
        # and fingertip/toe bones are required by TalkingHead
        force_connect_children=False,
    )
    print("[build] FBX imported.")


def step_relink_textures() -> None:
    """Re-point every image from its old Windows path to the local Textures/ folder."""
    if not TEXTURE_DIR.exists():
        sys.exit(f"[build] ERROR: Textures folder not found: {TEXTURE_DIR}")

    # Build a quick lookup: filename (lowercase) → absolute local Path
    local_tex: dict[str, Path] = {}
    for fname in TEXTURE_FILES:
        p = TEXTURE_DIR / fname
        if p.exists():
            local_tex[fname.lower()] = p
        else:
            print(f"[build] WARNING: texture file not found: {p}")

    for img in bpy.data.images:
        fname = Path(img.filepath).name.lower()
        if fname in local_tex:
            new_path = str(local_tex[fname])
            if img.filepath != new_path:
                img.filepath = new_path
                img.reload()
                print(f"[build] Re-linked: {fname} → {new_path}")
        elif img.filepath and img.filepath != "<builtin>":
            print(
                f"[build] WARNING: no local match for image '{img.name}' "
                f"(filepath={img.filepath!r})"
            )

    print("[build] Texture re-linking done.")


def step_fix_opacity_material() -> None:
    """Set the hair/opacity material to alpha-blended transparency."""
    mat = bpy.data.materials.get("m005_opacity")
    if mat is None:
        print("[build] WARNING: m005_opacity material not found, skipping.")
        return

    # Enable alpha blend so hair strands render transparently.
    # shadow_method was removed in Blender 4.0; guard for both 3.x and 4.x.
    mat.blend_method = "BLEND"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "CLIP"
    mat.use_backface_culling = False

    # Ensure the Alpha socket uses the alpha CHANNEL of the color texture,
    # not its colour values.  The FBX import wires Color→Alpha; we switch to Alpha→Alpha.
    if not mat.use_nodes:
        return
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return

    # Find the Image Texture feeding into the Alpha socket
    for lnk in list(nt.links):
        if lnk.to_node == bsdf and lnk.to_socket.name == "Alpha":
            src_node = lnk.from_node
            if src_node.type == "TEX_IMAGE":
                # Rewire: use the Alpha output instead of the Color output
                nt.links.remove(lnk)
                nt.links.new(src_node.outputs["Alpha"], bsdf.inputs["Alpha"])
                print("[build] m005_opacity: rewired Alpha channel for transparency.")
            break

    print("[build] m005_opacity material fixed.")


def step_rename_shape_keys() -> None:
    """Rename Rocketbox AA_VI and AK shape keys to TalkingHead conventions."""
    all_renames = {**VISEME_RENAME, **ARKIT_RENAME}
    renamed_viseme = 0
    renamed_arkit = 0

    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.data.shape_keys:
            continue
        for kb in obj.data.shape_keys.key_blocks:
            if kb.name in all_renames:
                new_name = all_renames[kb.name]
                if kb.name in VISEME_RENAME:
                    renamed_viseme += 1
                else:
                    renamed_arkit += 1
                kb.name = new_name

    print(
        f"[build] Shape keys renamed: {renamed_viseme} visemes, {renamed_arkit} ARKit."
    )
    if renamed_viseme < 15:
        print(
            f"[build] WARNING: expected 15 viseme renames, got {renamed_viseme}. "
            "Check the FBX for missing AA_VI shapes."
        )


def step_rename_armature_object() -> None:
    """Rename the armature Object and its data-block to 'Armature'.

    TalkingHead calls gltf.scene.getObjectByName('Armature') to find the
    skeleton root.  The Biped FBX import names it 'Bip01'; we must rename it.
    """
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            old_name = obj.name
            obj.name = "Armature"
            obj.data.name = "Armature"
            print(f"[build] Armature object renamed: {old_name!r} → 'Armature'")
            return
    print("[build] WARNING: no ARMATURE object found to rename.")


def step_rename_bones() -> None:
    """Rename Biped bones to Mixamo/RPM names for TalkingHead compatibility."""
    renamed = 0
    skipped = 0

    for obj in bpy.data.objects:
        if obj.type != "ARMATURE":
            continue
        # Must be in Edit Mode to rename bones (use object mode data instead)
        arm = obj.data
        for bone in arm.bones:
            if bone.name in BONE_RENAME:
                bone.name = BONE_RENAME[bone.name]
                renamed += 1
            else:
                skipped += 1

    print(
        f"[build] Bones renamed: {renamed} remapped, {skipped} left as-is (face rig)."
    )


def step_apply_scale() -> None:
    """Apply the 0.01 scale and clear object-level rotations so the GLB has
    identity node transforms and the character renders upright in TalkingHead.

    What the FBX importer produces:
      - Armature: scale=0.01 (cm→m), rotation=(0°,0°,−90° Z), location=(0,0,0.89m)
      - Mesh:     scale=1,    rotation=(0°,0°,+90° Z)
    TalkingHead calls armature.scale.setScalar(1) after loading, so the 0.01
    scale MUST be baked into bone data before export.
    TalkingHead does NOT touch rotation, but the −90° Z on the armature ends up
    as a −90° Y in glTF/Three.js, rotating the character sideways.  Zeroing both
    rotations before applying scale lets the bone Z-up data drive the Y-up glTF
    correctly (Blender Z → glTF Y handles the conversion).
    """
    # Step 1: zero out object-level rotations (preserve bone local data)
    for obj in bpy.data.objects:
        if obj.type in ("ARMATURE", "MESH"):
            obj.rotation_euler = (0.0, 0.0, 0.0)
    print("[build] Object rotations zeroed.")

    # Step 2: bake scale (and the now-zero rotation) so all nodes export at (1,1,1)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.transform_apply(scale=True, location=False, rotation=False)
    print("[build] Scale applied — all objects now at scale (1, 1, 1).")


def step_delete_default_cube() -> None:
    """Remove the leftover default Cube mesh if the scene still has one."""
    cube = bpy.data.objects.get("Cube")
    if cube:
        bpy.data.objects.remove(cube, do_unlink=True)
        print("[build] Default Cube removed.")


def step_verify() -> None:
    """Print a quick sanity report before exporting."""
    print("\n[build] ── Verification ────────────────────────────────────────")
    for obj in bpy.data.objects:
        print(f"  Object: {obj.name!r:40s}  type={obj.type}")
        if obj.type == "MESH" and obj.data.shape_keys:
            keys = [kb.name for kb in obj.data.shape_keys.key_blocks]
            visemes = [k for k in keys if k.startswith("viseme_")]
            arkit = [k for k in keys if k[0].islower() and not k.startswith("viseme_")]
            print(
                f"    Shape keys total={len(keys)}, visemes={len(visemes)}, ARKit≈{len(arkit)}"
            )
            missing = [v for v in VISEME_RENAME.values() if v not in keys]
            if missing:
                print(f"    MISSING VISEMES: {missing}")
            else:
                print(f"    All 15 Oculus visemes present ✓")
        if obj.type == "ARMATURE":
            bones = [b.name for b in obj.data.bones]
            mixamo_found = [b for b in bones if b in BONE_RENAME.values()]
            print(f"    Bones total={len(bones)}, Mixamo-named={len(mixamo_found)}")
    print("[build] ─────────────────────────────────────────────────────────\n")


def step_export_glb() -> None:
    """Export the whole scene as a self-contained GLB."""
    OUTPUT_GLB.parent.mkdir(parents=True, exist_ok=True)
    print(f"[build] Exporting GLB → {OUTPUT_GLB}")

    bpy.ops.export_scene.gltf(
        filepath=str(OUTPUT_GLB),
        export_format="GLB",
        # Geometry
        export_apply=False,
        export_normals=True,
        export_texcoords=True,
        export_attributes=True,
        # Materials / textures — embed everything in the single GLB file
        export_materials="EXPORT",
        export_image_format="AUTO",  # TGA → PNG automatically
        # Shape keys (morph targets)
        export_morph=True,
        export_morph_normal=True,
        export_morph_tangent=False,
        # Skinning
        export_skins=True,
        export_all_influences=False,
        # Animations — none to export from a static T-pose
        export_animations=False,
        # Cameras / lights — not needed in avatar GLB
        export_cameras=False,
        export_lights=False,
        # Coordinate system
        export_yup=True,
    )

    size_mb = OUTPUT_GLB.stat().st_size / 1_048_576
    print(f"[build] GLB written: {OUTPUT_GLB} ({size_mb:.1f} MB)")


# ===========================================================================
# Main
# ===========================================================================


def main() -> None:
    print("\n[build] ══ build_rocketbox_avatar.py ════════════════════════════")
    step_clear_scene()
    step_import_fbx()
    step_relink_textures()
    step_fix_opacity_material()
    step_rename_shape_keys()
    step_rename_armature_object()
    step_rename_bones()
    step_apply_scale()
    step_delete_default_cube()
    step_verify()
    step_export_glb()
    print("[build] ══ Done ══════════════════════════════════════════════════\n")


main()
