"""Build and render a fresh EEVEE scene for a modern CC avatar job.

Executed by Blender. It never opens the protected legacy template and saves
only to the explicit ignored experiment path supplied by the adapter.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import bpy
from mathutils import Euler, Vector


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blender.performance_importer import (
    EXPRESSION_PRESETS,
    OCULUS_TO_REALLUSION,
    SOFT_NEUTRAL,
    active_viseme,
    expression_weights,
    scheduled_blink_strength,
)
from blender.cc_motion_library import apply_motion_library


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    return parser.parse_args(argv)


def input_named(node: Any, *names: str) -> Any | None:
    for name in names:
        if name in node.inputs:
            return node.inputs[name]
    return None


def set_input(node: Any, value: Any, *names: str) -> None:
    socket = input_named(node, *names)
    if socket is not None:
        socket.default_value = value


def image_node(nodes: Any, path: Path, name: str) -> Any:
    image = bpy.data.images.load(str(path), check_existing=True)
    image.colorspace_settings.name = "Non-Color"
    node = nodes.new("ShaderNodeTexImage")
    node.name = name
    node.label = name
    node.image = image
    return node


def configure_material(material: Any, entry: dict[str, Any], avatar_root: Path) -> int:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return 0
    semantic = entry.get("class", "generic")
    textures = entry.get("textures") or {}
    loaded = 0

    set_input(bsdf, 0.0, "Metallic")
    if semantic == "skin":
        set_input(bsdf, 0.46, "Roughness")
        set_input(bsdf, 1.4, "IOR")
        set_input(bsdf, 0.34, "Specular IOR Level", "Specular")
        set_input(bsdf, (1.0, 0.42, 0.32), "Subsurface Radius")
        set_input(bsdf, 0.075, "Subsurface Weight", "Subsurface")
        set_input(bsdf, 0.03, "Coat Weight", "Clearcoat")
        set_input(bsdf, 0.65, "Coat Roughness", "Clearcoat Roughness")
    elif semantic == "eye":
        set_input(bsdf, 0.38, "Roughness")
        set_input(bsdf, 0.32, "Specular IOR Level", "Specular")
    elif semantic == "cornea":
        set_input(bsdf, 0.08, "Roughness")
        set_input(bsdf, 1.376, "IOR")
        set_input(bsdf, 0.8, "Coat Weight", "Clearcoat")
        set_input(bsdf, 0.05, "Coat Roughness", "Clearcoat Roughness")
    elif semantic == "eye_occlusion":
        set_input(bsdf, 0.72, "Roughness")
        set_input(bsdf, 0.2, "Alpha")
    elif semantic == "tearline":
        set_input(bsdf, 0.06, "Roughness")
        set_input(bsdf, 0.35, "Alpha")
        set_input(bsdf, 1.0, "Coat Weight", "Clearcoat")
    elif semantic in {"hair", "eyelash"}:
        set_input(bsdf, 0.55, "Roughness")
        set_input(bsdf, 0.2, "Specular IOR Level", "Specular")
    elif semantic == "teeth":
        set_input(bsdf, (0.92, 0.86, 0.75, 1.0), "Base Color")
        set_input(bsdf, 0.42, "Roughness")
    elif semantic == "tongue":
        set_input(bsdf, 0.52, "Roughness")
    elif semantic == "cloth":
        set_input(bsdf, 0.82, "Roughness")
        set_input(bsdf, 0.15, "Specular IOR Level", "Specular")

    for slot, relative in textures.items():
        path = avatar_root / relative
        if not path.is_file():
            continue
        tex = image_node(nodes, path, f"SynthPost_{slot}")
        loaded += 1
        if slot == "roughness":
            target = input_named(bsdf, "Roughness")
            if target is not None:
                links.new(tex.outputs["Color"], target)
        elif slot == "sss" and semantic == "skin":
            target = input_named(bsdf, "Subsurface Weight", "Subsurface")
            if target is not None:
                multiply = nodes.new("ShaderNodeMath")
                multiply.operation = "MULTIPLY"
                multiply.inputs[1].default_value = 0.075
                links.new(tex.outputs["Color"], multiply.inputs[0])
                links.new(multiply.outputs[0], target)
        elif slot == "ao":
            base = input_named(bsdf, "Base Color")
            if base is not None and base.is_linked:
                source = base.links[0].from_socket
                links.remove(base.links[0])
                mix = nodes.new("ShaderNodeMixRGB")
                mix.blend_type = "MULTIPLY"
                mix.inputs[0].default_value = 0.3
                links.new(source, mix.inputs[1])
                links.new(tex.outputs["Color"], mix.inputs[2])
                links.new(mix.outputs[0], base)

    if semantic in {"eye_occlusion", "tearline", "hair", "eyelash"}:
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "DITHERED"
        elif hasattr(material, "blend_method"):
            material.blend_method = "BLEND"
    return loaded


def world_bounds(objects: list[Any]) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    low = Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners)))
    high = Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))
    return low, high


def point_camera(camera: Any, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def add_area(name: str, color: tuple[float, float, float], energy: float, size: float, location: tuple[float, float, float], target: Vector) -> None:
    data = bpy.data.lights.new(name=name, type="AREA")
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def install_performance_handler(scene: Any, meshes: list[Any], job: dict[str, Any]) -> None:
    visemes = list(job["precomputed_visemes"]["visemes"])
    starts = [float(v) for v in job["precomputed_visemes"]["vtimes"]]
    durations = [float(v) for v in job["precomputed_visemes"]["vdurations"]]
    performance = job.get("performance") or {}
    blink_events = list(performance.get("blink_events") or [])
    expression_events = list(performance.get("expression_events") or [])
    controlled = sorted(
        {name for mapping in OCULUS_TO_REALLUSION.values() for name in mapping}
        | {name for mapping in EXPRESSION_PRESETS.values() for name in mapping}
    )
    shape_blocks = [obj.data.shape_keys.key_blocks for obj in meshes if getattr(obj.data, "shape_keys", None)]

    def update(_scene: Any, _depsgraph: Any = None) -> None:
        # Frame 1 is always narration time zero. Sparse rendering temporarily
        # changes scene.frame_start for each visible window, so it must not
        # become the performance clock origin.
        t = max(0.0, (scene.frame_current - 1) / scene.render.fps)
        t_ms = t * 1000.0
        for blocks in shape_blocks:
            for name in controlled:
                if name in blocks:
                    blocks[name].value = 0.0
            for name, value in SOFT_NEUTRAL.items():
                if name in blocks:
                    blocks[name].value = value
        active = active_viseme(t_ms, visemes, starts, durations)
        if active:
            cue, strength = active
            for name, weight in OCULUS_TO_REALLUSION.get(cue, {}).items():
                for blocks in shape_blocks:
                    if name in blocks:
                        blocks[name].value = max(blocks[name].value, strength * weight)
        for name, value in expression_weights(t, expression_events).items():
            for blocks in shape_blocks:
                if name in blocks:
                    blocks[name].value = max(blocks[name].value, value)
        blink = scheduled_blink_strength(t, blink_events)
        if blink > 0:
            for blocks in shape_blocks:
                for name in ("Eye_Blink_L", "Eye_Blink_R"):
                    if name in blocks:
                        blocks[name].value = max(blocks[name].value, blink)

    bpy.app.handlers.frame_change_pre.clear()
    bpy.app.handlers.frame_change_pre.append(update)
    update(scene)


def apply_static_anchor_pose(armature: Any | None) -> None:
    """Use a restrained rest pose only when no authored idle is available."""

    if armature is None:
        return
    calibration = {
        "CC_Base_Waist": (0.012, 0.0, 0.0),
        "CC_Base_Spine01": (0.026, 0.0, 0.0),
        "CC_Base_Spine02": (0.034, 0.0, 0.0),
        "CC_Base_R_Upperarm": (0.08, 0.18, 1.48),
        "CC_Base_L_Upperarm": (0.08, -0.18, -1.48),
    }
    for name, xyz in calibration.items():
        bone = armature.pose.bones.get(name)
        if bone is None:
            continue
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion = bone.rotation_quaternion @ Euler(
            xyz, "XYZ"
        ).to_quaternion()


def main() -> None:
    started = time.monotonic()
    args = parse_args()
    job = json.loads(args.job.read_text(encoding="utf-8"))
    asset_path = Path(job["asset_path"])
    avatar_root = Path(job["avatar_root"])
    output_dir = Path(job["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    import_started = time.monotonic()
    bpy.ops.import_scene.gltf(filepath=str(asset_path))
    import_seconds = time.monotonic() - import_started
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    render_settings = job.get("render_settings") or {}
    resolution_scale = float(render_settings.get("resolution_scale", 1.0))
    scene.render.resolution_x = max(
        1, int(round(int(job["camera"]["width"]) * resolution_scale))
    )
    scene.render.resolution_y = max(
        1, int(round(int(job["camera"]["height"]) * resolution_scale))
    )
    scene.render.resolution_percentage = 100
    scene.render.fps = int(job["camera"]["fps"])
    scene.frame_start = 1
    scene.frame_end = int(math.ceil(float(job["duration_seconds"]) * scene.render.fps))
    if getattr(scene, "eevee", None) is not None:
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = int(render_settings.get("samples", 32))
        if hasattr(scene.eevee, "use_raytracing"):
            scene.eevee.use_raytracing = False
    frame_format = str(render_settings.get("frame_format", "PNG")).upper()
    scene.render.image_settings.file_format = frame_format
    presenter_pass = render_settings.get("presenter_pass") or {}
    transparent = bool(presenter_pass.get("transparent", False))
    scene.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    scene.render.image_settings.color_depth = "8"
    if frame_format in {"JPEG", "WEBP"}:
        scene.render.image_settings.quality = int(render_settings.get("frame_quality", 95))
    if frame_format == "PNG":
        scene.render.image_settings.compression = int(render_settings.get("png_compression", 15))
    scene.render.film_transparent = transparent
    crop = presenter_pass.get("crop")
    if presenter_pass.get("enabled") and crop:
        scene.render.use_border = True
        scene.render.use_crop_to_border = True
        scene.render.border_min_x = float(crop[0])
        scene.render.border_min_y = float(crop[1])
        scene.render.border_max_x = float(crop[2])
        scene.render.border_max_y = float(crop[3])
    frames_dir = output_dir / "frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(frames_dir / "frame_")
    scene.render.use_file_extension = True
    if scene.world is None:
        scene.world = bpy.data.worlds.new("SynthPost_World")
        scene.world.use_nodes = True
    scene.world.color = (0.01, 0.01, 0.012)
    if scene.world.use_nodes:
        background = scene.world.node_tree.nodes.get("Background")
        if background:
            # AgX maps these linear values to the same near-charcoal output used
            # by the browser gate (approximately sRGB 28/28/30).
            background.inputs["Color"].default_value = (0.03, 0.03, 0.035, 1.0)
            background.inputs["Strength"].default_value = 1.0
    scene.view_settings.look = "AgX - Medium High Contrast"

    stray_names = {"cube", "icosphere", "sphere", "plane"}
    for obj in scene.objects:
        normalized = obj.name.lower().split(".", 1)[0]
        if obj.type == "MESH" and normalized in stray_names:
            obj.hide_render = True
            obj.hide_viewport = True
    meshes = [
        obj for obj in scene.objects if obj.type == "MESH" and not obj.hide_render
    ]
    armature = next((obj for obj in scene.objects if obj.type == "ARMATURE"), None)
    for obj in scene.objects:
        obj.animation_data_clear()
    for obj in meshes:
        if getattr(obj.data, "shape_keys", None):
            obj.data.shape_keys.animation_data_clear()

    profile = job["material_profile"]
    loaded_textures = 0
    resolved_materials = 0
    for material in bpy.data.materials:
        entry = profile["materials"].get(material.name)
        if entry:
            loaded_textures += configure_material(material, entry, avatar_root)
            resolved_materials += 1

    low, high = world_bounds(meshes)
    size = high - low
    center = (low + high) * 0.5
    target = Vector((center.x, center.y, low.z + size.z * 0.80))
    distance = (
        size.z
        * 0.58
        * float(job.get("distance_multiplier") or 3.5)
        * 1.08
    )
    camera_data = bpy.data.cameras.new("SynthPost_Camera")
    camera_data.lens = 85
    camera = bpy.data.objects.new("SynthPost_Camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (target.x, target.y - distance, target.z + size.z * 0.02)
    point_camera(camera, target)
    scene.camera = camera

    add_area("Key", (1.0, 0.78, 0.62), 520, 2.2, (2.5, -3.2, target.z + 1.1), target)
    add_area("Fill", (0.62, 0.75, 1.0), 105, 2.8, (-3.0, -2.5, target.z + 0.5), target)
    add_area("Rim", (0.72, 0.82, 1.0), 280, 1.8, (-1.6, 2.5, target.z + 1.0), target)

    motion_diagnostics = apply_motion_library(
        bpy, armature=armature, scene=scene, job=job
    )
    if motion_diagnostics.get("idle") is None:
        apply_static_anchor_pose(armature)
    install_performance_handler(scene, meshes, job)
    scene.frame_set(scene.frame_start)
    scene_path = Path(job["scene_path"])
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path), check_existing=False)

    setup_seconds = time.monotonic() - started
    render_started = time.monotonic()
    render_windows = list(render_settings.get("render_windows") or [])
    rendered_windows: list[dict[str, Any]] = []
    full_frame_end = scene.frame_end
    if render_windows:
        for index, window in enumerate(render_windows):
            source_start = float(window["source_start"])
            source_end = min(float(window["source_end"]), float(job["duration_seconds"]))
            start_frame = max(1, int(math.floor(source_start * scene.render.fps)) + 1)
            end_frame = min(
                full_frame_end,
                max(start_frame, int(math.ceil(source_end * scene.render.fps))),
            )
            window_dir = frames_dir / f"window_{index + 1:03d}"
            window_dir.mkdir(parents=True, exist_ok=True)
            scene.frame_start = start_frame
            scene.frame_end = end_frame
            scene.render.filepath = str(window_dir / "frame_")
            bpy.ops.render.render(animation=True, write_still=True)
            rendered_windows.append(
                {
                    **window,
                    "index": index + 1,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "frame_count": end_frame - start_frame + 1,
                }
            )
        scene.frame_start = 1
        scene.frame_end = full_frame_end
        scene.render.filepath = str(frames_dir / "frame_")
    else:
        bpy.ops.render.render(animation=True, write_still=True)
    render_seconds = time.monotonic() - render_started
    rendered_frame_count = (
        sum(int(window["frame_count"]) for window in rendered_windows)
        if rendered_windows
        else scene.frame_end - scene.frame_start + 1
    )
    diagnostics = {
        "renderer": "blender_cc",
        "blender_version": bpy.app.version_string,
        "engine": scene.render.engine,
        "gpu_backend": getattr(bpy.context.preferences.system, "gpu_backend", None),
        "platform": platform.platform(),
        "render_profile": render_settings.get("profile"),
        "render_samples": getattr(getattr(scene, "eevee", None), "taa_render_samples", None),
        "ray_tracing": getattr(getattr(scene, "eevee", None), "use_raytracing", None),
        "frame_format": frame_format,
        "frame_color_mode": scene.render.image_settings.color_mode,
        "resolution_scale": resolution_scale,
        "output_resolution": (
            f"{int(round(scene.render.resolution_x * ((crop[2] - crop[0]) if crop else 1.0)))}x"
            f"{int(round(scene.render.resolution_y * ((crop[3] - crop[1]) if crop else 1.0)))}"
        ),
        "presenter_pass": presenter_pass,
        "motion_library": motion_diagnostics,
        "import_seconds": round(import_seconds, 3),
        "setup_seconds": round(setup_seconds, 3),
        "render_seconds": round(render_seconds, 3),
        "frame_count": rendered_frame_count,
        "source_frame_count": full_frame_end,
        "render_windows": rendered_windows,
        "mesh_count": len(meshes),
        "material_count": len(bpy.data.materials),
        "resolved_material_count": resolved_materials,
        "loaded_texture_count": loaded_textures,
        "armature": armature.name if armature else None,
        "bone_count": len(armature.data.bones) if armature else 0,
        "bounds": {"min": list(low), "max": list(high), "size": list(size)},
        "camera": {"location": list(camera.location), "target": list(target), "lens_mm": camera_data.lens},
        "scene_path": str(scene_path),
    }
    Path(job["diagnostics_path"]).write_text(json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
