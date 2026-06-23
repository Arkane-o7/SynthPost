from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy  # type: ignore
from mathutils import Vector  # type: ignore


SCRIPT_DIR = Path(__file__).resolve().parent
PRODUCTION_TEMPLATE_PATH = SCRIPT_DIR / "avatar_template.blend"
OUTPUT_PATH = SCRIPT_DIR / "avatar_template_BASIC.blend"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def make_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    return material


def assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    obj.data.materials.append(material)


def parent_keep_transform(child: bpy.types.Object, parent: bpy.types.Object) -> None:
    matrix_world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = matrix_world


def add_cube(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    material: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    assign_material(obj, material)
    return obj


def add_uv_sphere(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    assign_material(obj, material)
    bpy.ops.object.shade_smooth()
    return obj


def add_plane(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    rotation: tuple[float, float, float],
    material: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    assign_material(obj, material)
    return obj


def add_shape_keys(obj: bpy.types.Object) -> None:
    key_names = [
        "mouth_closed",
        "mouth_mbp",
        "mouth_ee",
        "mouth_aa",
        "mouth_oh",
        "mouth_oo",
        "mouth_fv",
        "mouth_lth",
        "mouth_rest",
        "brow_inner_up",
        "eyes_relaxed",
        "mouth_smile",
        "brow_down_left",
        "brow_down_right",
        "eyes_squint",
        "cheek_raise",
        "brow_outer_up_left",
        "brow_outer_up_right",
        "eyes_wide",
        "jaw_open",
        "mouth_frown",
        "mouth_press",
    ]
    obj.shape_key_add(name="Basis")
    for key_name in key_names:
        obj.shape_key_add(name=key_name)


def create_avatar(materials: dict[str, bpy.types.Material]) -> None:
    body = add_cube("CHAR_Avatar", (0.0, 0.0, 1.2), (0.55, 0.32, 0.85), materials["jacket"])
    add_shape_keys(body)

    head = add_uv_sphere("CHAR_Head", (0.0, -0.02, 2.25), 0.36, materials["skin"])
    neck = add_cube("CHAR_Neck", (0.0, 0.0, 1.82), (0.16, 0.14, 0.18), materials["skin"])
    left_arm = add_cube("CHAR_Arm_L", (-0.62, -0.03, 1.25), (0.16, 0.16, 0.62), materials["jacket"])
    right_arm = add_cube("CHAR_Arm_R", (0.62, -0.03, 1.25), (0.16, 0.16, 0.62), materials["jacket"])

    for part in (head, neck, left_arm, right_arm):
        parent_keep_transform(part, body)

    face = add_plane(
        "FACE_Surface",
        (0.0, -0.37, 2.25),
        (0.42, 0.28, 1.0),
        (math.radians(90.0), 0.0, 0.0),
        materials["face"],
    )
    face["mouth_cue"] = 0
    parent_keep_transform(face, head)


def create_armature() -> None:
    bpy.ops.object.armature_add(enter_editmode=True, location=(0.0, 0.0, 0.0))
    armature = bpy.context.object
    armature.name = "ARM_Avatar"
    armature.data.name = "ARM_Avatar_Data"

    bones = armature.data.edit_bones
    for bone in list(bones):
        bones.remove(bone)

    def add_bone(name: str, head: tuple[float, float, float], tail: tuple[float, float, float]) -> None:
        bone = bones.new(name)
        bone.head = head
        bone.tail = tail
        bone.roll = 0.0

    add_bone("Spine", (0.0, 0.0, 0.7), (0.0, 0.0, 1.75))
    add_bone("Head", (0.0, 0.0, 1.75), (0.0, 0.0, 2.45))
    add_bone("UpperArm.L", (-0.36, 0.0, 1.55), (-0.88, 0.0, 1.2))
    add_bone("UpperArm.R", (0.36, 0.0, 1.55), (0.88, 0.0, 1.2))
    add_bone("Hand.R", (0.88, 0.0, 1.2), (1.08, -0.08, 1.05))

    bpy.ops.object.mode_set(mode="OBJECT")
    armature.show_in_front = True


def create_desk(materials: dict[str, bpy.types.Material]) -> None:
    add_cube("DESK_Main", (0.0, -0.82, 0.78), (1.9, 0.42, 0.12), materials["wood"])
    add_cube("DESK_Leg_FL", (-1.55, -1.12, 0.34), (0.12, 0.12, 0.68), materials["wood"])
    add_cube("DESK_Leg_FR", (1.55, -1.12, 0.34), (0.12, 0.12, 0.68), materials["wood"])
    add_cube("DESK_Leg_BL", (-1.55, -0.52, 0.34), (0.12, 0.12, 0.68), materials["wood"])
    add_cube("DESK_Leg_BR", (1.55, -0.52, 0.34), (0.12, 0.12, 0.68), materials["wood"])


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera(
    name: str,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
    lens: float,
) -> bpy.types.Object:
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = name
    camera.data.lens = lens
    look_at(camera, target)
    return camera


def add_light(
    name: str,
    location: tuple[float, float, float],
    energy: float,
    size: float,
) -> bpy.types.Object:
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.object
    light.name = name
    light.data.energy = energy
    light.data.size = size
    return light


def create_cameras_and_lights() -> None:
    intro = add_camera("CAM_Landscape_Intro", (0.0, -5.3, 2.15), (0.0, -0.2, 1.65), 48.0)
    add_camera("CAM_Portrait_Main", (0.0, -3.4, 2.35), (0.0, -0.1, 2.0), 70.0)
    add_camera("CAM_Landscape_Conclusion", (3.5, -4.1, 2.1), (0.0, -0.15, 1.75), 52.0)
    bpy.context.scene.camera = intro

    add_light("LIGHT_Key", (-2.6, -3.6, 4.2), 600.0, 4.0)
    add_light("LIGHT_Fill", (3.2, -2.4, 2.8), 180.0, 5.0)
    add_light("LIGHT_Rim", (0.0, 2.1, 3.4), 320.0, 3.0)


def configure_scene(materials: dict[str, bpy.types.Material]) -> None:
    floor = add_plane("FLOOR_Main", (0.0, 0.0, 0.0), (5.0, 5.0, 1.0), (0.0, 0.0, 0.0), materials["floor"])
    floor.location.z = -0.02

    scene = bpy.context.scene
    scene.render.fps = 30
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.frame_start = 1
    scene.frame_end = 180
    scene.render.image_settings.file_format = "PNG"

    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue

    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.color = (0.035, 0.04, 0.05)


def parse_force_flag() -> bool:
    if "--" not in sys.argv:
        return False
    script_args = sys.argv[sys.argv.index("--") + 1 :]
    unknown_args = [arg for arg in script_args if arg != "--force"]
    if unknown_args:
        raise SystemExit(f"Unknown argument(s): {', '.join(unknown_args)}")
    return "--force" in script_args


def validate_output_path(force: bool) -> None:
    if PRODUCTION_TEMPLATE_PATH.exists():
        print(f"[template] Production template exists and will not be touched: {PRODUCTION_TEMPLATE_PATH}")
    if OUTPUT_PATH == PRODUCTION_TEMPLATE_PATH:
        raise SystemExit("[template] Refusing to write over the production template.")
    if OUTPUT_PATH.exists() and not force:
        raise SystemExit(
            f"[template] Refusing to overwrite existing dummy template: {OUTPUT_PATH}\n"
            "[template] Re-run with '-- --force' if you intentionally want to replace it."
        )


def main() -> None:
    force = parse_force_flag()
    validate_output_path(force)

    clear_scene()
    materials = {
        "jacket": make_material("MAT_Avatar_Jacket", (0.08, 0.13, 0.2, 1.0)),
        "skin": make_material("MAT_Avatar_Skin", (0.82, 0.58, 0.42, 1.0)),
        "face": make_material("MAT_Face_Surface", (0.95, 0.92, 0.84, 1.0)),
        "wood": make_material("MAT_Desk_Wood", (0.42, 0.25, 0.12, 1.0)),
        "floor": make_material("MAT_Floor", (0.12, 0.13, 0.14, 1.0)),
    }

    create_avatar(materials)
    create_armature()
    create_desk(materials)
    create_cameras_and_lights()
    configure_scene(materials)

    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_PATH), compress=True)
    print(f"[template] Wrote basic dummy Blender template: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
