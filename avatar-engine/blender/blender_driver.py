from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import bpy  # type: ignore

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from camera_cuts import add_camera_cuts, seconds_to_frames  # noqa: E402
from expression_presets import apply_expression_preset  # noqa: E402
from gesture_loader import apply_action_gestures, apply_placeholder_gesture  # noqa: E402
from mouth_mapping import MOUTH_CUE_INDEX, RHU_BARBS, SHAPE_KEY_MOUTH_MAP, shape_key_for_cue, texture_for_cue  # noqa: E402


MOUTH_TEXTURE_HANDLER_NAME = "desk_avatar_sync_2d_mouth_texture"


def parse_blender_args() -> Path:
    if "--" not in sys.argv:
        raise SystemExit("Usage in Blender: blender -b template.blend --python blender_driver.py -- jobs/sample_job.json")
    args = sys.argv[sys.argv.index("--") + 1 :]
    if not args:
        raise SystemExit("Missing job JSON path after '--'.")
    path = Path(args[0]).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def find_avatar_mesh() -> Any | None:
    preferred_names = ("Avatar", "Avatar_Mesh", "Head", "Face")
    for name in preferred_names:
        obj = bpy.data.objects.get(name)
        if obj and getattr(obj, "type", "") == "MESH":
            return obj
    for obj in bpy.context.scene.objects:
        if getattr(obj, "type", "") == "MESH" and getattr(getattr(obj, "data", None), "shape_keys", None):
            return obj
    print("[blender] WARNING: No avatar mesh with shape keys found.")
    return None


def add_audio_to_timeline(audio_path: Path) -> None:
    if not audio_path.exists():
        print(f"[blender] WARNING: Audio file missing: {audio_path}")
        return
    scene = bpy.context.scene
    if scene.sequence_editor is None:
        scene.sequence_editor_create()
    try:
        scene.sequence_editor.sequences.new_sound("dialogue", str(audio_path), channel=1, frame_start=1)
        print(f"[blender] Added audio to timeline: {audio_path}")
    except Exception as exc:
        print(f"[blender] WARNING: Could not add audio to timeline: {exc}")


def configure_per_camera_resolution(job: dict[str, Any], width: int, height: int, percentage: int = 100) -> None:
    if bool(job.get("use_per_camera_resolution", True)):
        scale = max(0.01, float(job.get("camera_resolution_scale", 1.0)))
        if scale == 1.0:
            print("[blender] Keeping template per-camera resolution settings.")
            return

        updated = 0
        for obj in bpy.data.objects:
            if getattr(obj, "type", "") != "CAMERA":
                continue
            camera_data = getattr(obj, "data", None)
            props = getattr(camera_data, "per_camera_resolution", None)
            if props is None or not bool(props.use_custom_resolution):
                continue
            props.resolution_x = max(1, int(round(float(props.resolution_x) * scale)))
            props.resolution_y = max(1, int(round(float(props.resolution_y) * scale)))
            updated += 1
        print(f"[blender] Scaled template per-camera resolution settings by {scale:g} for {updated} camera(s).")
        return

    updated = 0
    preserve_portrait_framing = bool(job.get("preserve_portrait_framing", True))
    output_aspect = width / max(1, height)
    for obj in bpy.data.objects:
        if getattr(obj, "type", "") != "CAMERA":
            continue
        camera_data = getattr(obj, "data", None)
        props = getattr(camera_data, "per_camera_resolution", None)
        if props is None:
            continue
        original_aspect = props.resolution_x / max(1, props.resolution_y)
        if preserve_portrait_framing and original_aspect < 1.0 and output_aspect > 1.0:
            set_if_present(camera_data, "sensor_fit", "VERTICAL")
            print(f"[blender] Preserving vertical framing for portrait camera '{obj.name}'.")
        props.use_custom_resolution = True
        props.resolution_x = width
        props.resolution_y = height
        props.resolution_percentage = percentage
        props.pixel_aspect_x = 1.0
        props.pixel_aspect_y = 1.0
        updated += 1

    if updated:
        print(f"[blender] Set per-camera resolution to {width}x{height} at {percentage}% for {updated} camera(s).")


def set_if_present(target: Any, name: str, value: Any) -> None:
    if not hasattr(target, name):
        return
    try:
        setattr(target, name, value)
    except Exception:
        pass


def apply_render_quality(job: dict[str, Any]) -> None:
    quality = str(job.get("render_quality", "final")).lower()
    if quality not in {"draft", "preview", "fast"}:
        return

    scene = bpy.context.scene
    eevee = getattr(scene, "eevee", None)
    if eevee is None:
        return

    set_if_present(eevee, "taa_render_samples", int(job.get("render_samples", 8)))
    set_if_present(eevee, "taa_samples", 4)
    set_if_present(eevee, "use_raytracing", False)
    set_if_present(eevee, "use_volumetric_shadows", False)
    set_if_present(eevee, "volumetric_samples", 8)
    set_if_present(eevee, "volumetric_shadow_samples", 4)
    set_if_present(eevee, "shadow_resolution_scale", 0.25)
    set_if_present(eevee, "shadow_pool_size", 128)
    set_if_present(eevee, "gi_cubemap_resolution", 128)
    set_if_present(eevee, "gi_visibility_resolution", 16)
    set_if_present(eevee, "fast_gi_ray_count", 1)
    set_if_present(eevee, "fast_gi_step_count", 2)
    set_if_present(eevee, "fast_gi_resolution", 1)
    if bool(job.get("disable_shadows", False)):
        set_if_present(eevee, "use_shadows", False)
    print(f"[blender] Render quality: {quality} preview settings enabled.")


def reset_mouth_shape_keys(mesh_object: Any, frame: int) -> None:
    shape_keys = getattr(getattr(mesh_object, "data", None), "shape_keys", None)
    key_blocks = getattr(shape_keys, "key_blocks", None)
    if key_blocks is None:
        return
    for key_name in SHAPE_KEY_MOUTH_MAP.values():
        key = key_blocks.get(key_name)
        if key is not None:
            key.value = 0.0
            key.keyframe_insert("value", frame=frame)


def apply_3d_mouth_animation(mesh_object: Any, mouth_cues: list[dict], fps: int) -> None:
    shape_keys = getattr(getattr(mesh_object, "data", None), "shape_keys", None)
    key_blocks = getattr(shape_keys, "key_blocks", None)
    if key_blocks is None:
        print(f"[blender] WARNING: Object '{mesh_object.name}' has no shape keys for mouth animation.")
        return

    for cue in mouth_cues:
        frame = seconds_to_frames(float(cue.get("start", 0.0)), fps)
        cue_value = str(cue.get("value", "X")).upper()
        reset_mouth_shape_keys(mesh_object, frame)
        key_name = shape_key_for_cue(cue_value)
        key = key_blocks.get(key_name)
        if key is None:
            print(f"[blender] WARNING: Missing mouth shape key '{key_name}', skipping.")
            continue
        key.value = 1.0
        key.keyframe_insert("value", frame=frame)
    print("[blender] Applied 3D mouth animation.")


def set_material_transparency(material: Any) -> None:
    for attr, value in (
        ("blend_method", "BLEND"),
        ("surface_render_method", "BLENDED"),
        ("use_screen_refraction", True),
        ("show_transparent_back", True),
    ):
        try:
            setattr(material, attr, value)
        except Exception:
            pass


def create_mouth_texture_material(initial_image: Any | None) -> tuple[Any, Any | None]:
    material = bpy.data.materials.new("MAT_FACE_Surface_Mouth_Texture")
    material.use_nodes = True
    material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    set_material_transparency(material)

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output_node = nodes.new(type="ShaderNodeOutputMaterial")
    shader_node = nodes.new(type="ShaderNodeBsdfPrincipled")
    transparent_node = nodes.new(type="ShaderNodeBsdfTransparent")
    mix_node = nodes.new(type="ShaderNodeMixShader")
    texture_node = nodes.new(type="ShaderNodeTexImage")
    texture_node.name = "Mouth_Texture_Image"
    texture_node.label = "Mouth Texture"
    texture_node.image = initial_image
    texture_node.extension = "CLIP"
    texture_node.interpolation = "Closest"

    links.new(transparent_node.outputs["BSDF"], mix_node.inputs[1])
    links.new(shader_node.outputs["BSDF"], mix_node.inputs[2])
    links.new(mix_node.outputs["Shader"], output_node.inputs["Surface"])
    links.new(texture_node.outputs["Color"], shader_node.inputs["Base Color"])
    if "Alpha" in texture_node.outputs:
        links.new(texture_node.outputs["Alpha"], mix_node.inputs["Fac"])

    return material, texture_node


def create_fallback_mouth_material() -> Any:
    material = bpy.data.materials.new("MAT_Mouth_Fallback")
    material.diffuse_color = (0.02, 0.01, 0.01, 1.0)
    return material


def load_2d_mouth_images(character: str) -> dict[str, Any]:
    texture_dir = PROJECT_ROOT / "assets" / "characters" / character / "mouth_textures"
    rest_path = texture_dir / texture_for_cue("X")
    fallback_image = None
    if not rest_path.exists():
        print(f"[blender] WARNING: Missing fallback mouth texture '{rest_path}'; using a flat fallback material.")
    else:
        fallback_image = bpy.data.images.load(str(rest_path), check_existing=True)

    images: dict[str, Any] = {}
    for cue_value in RHU_BARBS:
        texture_path = texture_dir / texture_for_cue(cue_value)
        if not texture_path.exists():
            if rest_path.exists():
                print(
                    f"[blender] WARNING: Missing mouth texture '{texture_path}'; "
                    f"falling back to '{rest_path}'."
                )
                images[cue_value] = fallback_image
            else:
                continue
        else:
            images[cue_value] = bpy.data.images.load(str(texture_path), check_existing=True)

    print(f"[blender] Loaded 2D mouth textures from: {texture_dir}")
    return images


def cue_for_frame(frame: int, frame_cues: list[tuple[int, int, str]]) -> str:
    for start_frame, end_frame, cue_value in frame_cues:
        if start_frame <= frame < end_frame:
            return cue_value
    return "X"


def assign_face_material(face_surface: Any, material: Any) -> None:
    if len(face_surface.data.materials) == 0:
        face_surface.data.materials.append(material)
    else:
        face_surface.data.materials[0] = material
    for polygon in face_surface.data.polygons:
        polygon.material_index = 0


def remove_existing_mouth_handlers() -> None:
    bpy.app.handlers.frame_change_pre[:] = [
        handler
        for handler in bpy.app.handlers.frame_change_pre
        if getattr(handler, "__name__", "") != MOUTH_TEXTURE_HANDLER_NAME
    ]


def apply_2d_mouth_animation(job: dict[str, Any], mouth_cues: list[dict], fps: int) -> None:
    face_surface = bpy.data.objects.get("FACE_Surface")
    if face_surface is None:
        print("[blender] WARNING: FACE_Surface missing; cannot apply 2D mouth texture cues.")
        return

    character = str(job.get("character", "avatar_01"))
    images = load_2d_mouth_images(character)
    if not images:
        print("[blender] WARNING: No 2D mouth textures were loaded; using a flat fallback material.")
        assign_face_material(face_surface, create_fallback_mouth_material())
        return

    initial_image = images.get("X") or next(iter(images.values()))
    mouth_material, texture_node = create_mouth_texture_material(initial_image)
    assign_face_material(face_surface, mouth_material)

    frame_cues: list[tuple[int, int, str]] = []
    for cue in mouth_cues:
        frame = seconds_to_frames(float(cue.get("start", 0.0)), fps)
        end_frame = max(frame + 1, seconds_to_frames(float(cue.get("end", cue.get("start", 0.0))), fps))
        cue_value = str(cue.get("value", "X")).upper()
        if cue_value not in images:
            print(f"[blender] WARNING: Unknown mouth cue '{cue_value}'; using X.")
            cue_value = "X"
        frame_cues.append((frame, end_frame, cue_value))
        face_surface["mouth_cue"] = MOUTH_CUE_INDEX.get(cue_value, MOUTH_CUE_INDEX["X"])
        face_surface.keyframe_insert(data_path='["mouth_cue"]', frame=frame)

    remove_existing_mouth_handlers()
    active_cue: dict[str, str | None] = {"value": None}

    def sync_mouth_texture(scene: Any, depsgraph: Any | None = None) -> None:
        cue_value = cue_for_frame(scene.frame_current, frame_cues)
        image = images.get(cue_value) or images.get("X")
        image = image or initial_image
        if image is None or texture_node is None:
            return
        if active_cue["value"] == cue_value and texture_node.image == image:
            return
        active_cue["value"] = cue_value
        texture_node.image = image
        mouth_material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
        mouth_material.update_tag()
        face_surface.data.update_tag()

    sync_mouth_texture.__name__ = MOUTH_TEXTURE_HANDLER_NAME
    bpy.app.handlers.frame_change_pre.append(sync_mouth_texture)
    sync_mouth_texture(bpy.context.scene)
    print("[blender] Applied 2D mouth texture animation on FACE_Surface.")


def apply_performance_beats(job: dict[str, Any], fps: int) -> None:
    avatar_mesh = find_avatar_mesh()
    for beat in job.get("performance_beats", []):
        start_frame = seconds_to_frames(float(beat.get("start", 0.0)), fps)
        end_frame = seconds_to_frames(float(beat.get("end", beat.get("start", 0.0))), fps)
        expression = str(beat.get("expression", "calm"))
        gesture = str(beat.get("gesture", "seated_idle"))
        if avatar_mesh is not None:
            apply_expression_preset(avatar_mesh, expression, start_frame)
        apply_placeholder_gesture(bpy, gesture, start_frame, end_frame)


def configure_render(job: dict[str, Any], mouth_metadata: dict[str, Any]) -> None:
    scene = bpy.context.scene
    fps = int(job.get("fps", 30))
    resolution = job.get("resolution", [1920, 1080])
    duration = float(mouth_metadata.get("duration", 5.0))

    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    apply_render_quality(job)
    scene.render.fps = fps
    scene.render.resolution_x = int(resolution[0])
    scene.render.resolution_y = int(resolution[1])
    scene.render.resolution_percentage = 100
    configure_per_camera_resolution(job, scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage)
    scene.frame_start = 1
    scene.frame_end = max(1, int(duration * fps))
    scene.render.image_settings.file_format = "PNG"
    print(
        "[blender] Render configured: "
        f"{scene.render.fps} fps, "
        f"{scene.render.resolution_x}x{scene.render.resolution_y} at {scene.render.resolution_percentage}%, "
        f"frames 1-{scene.frame_end}."
    )


def camera_for_frame(scene: Any, frame: int) -> Any | None:
    active_camera = scene.camera
    for marker in sorted(scene.timeline_markers, key=lambda item: item.frame):
        if marker.frame <= frame and marker.camera is not None:
            active_camera = marker.camera
        elif marker.frame > frame:
            break
    return active_camera


def apply_camera_resolution(job: dict[str, Any], scene: Any) -> tuple[int, int, int]:
    use_per_camera_resolution = bool(job.get("use_per_camera_resolution", True))
    if use_per_camera_resolution and scene.camera is not None:
        props = getattr(getattr(scene.camera, "data", None), "per_camera_resolution", None)
        if props is not None and bool(props.use_custom_resolution):
            scene.render.resolution_x = int(props.resolution_x)
            scene.render.resolution_y = int(props.resolution_y)
            scene.render.resolution_percentage = int(props.resolution_percentage)
            scene.render.pixel_aspect_x = float(props.pixel_aspect_x)
            scene.render.pixel_aspect_y = float(props.pixel_aspect_y)
            return scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage

    resolution = job.get("resolution", [1920, 1080])
    scene.render.resolution_x = int(resolution[0])
    scene.render.resolution_y = int(resolution[1])
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = 1.0
    scene.render.pixel_aspect_y = 1.0
    return scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage


def render_frame_sequence(job: dict[str, Any], render_dir: Path) -> None:
    scene = bpy.context.scene
    previous_camera_name = None
    previous_resolution = None
    for frame in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(frame)
        camera = camera_for_frame(scene, frame)
        if camera is not None:
            scene.camera = camera
        resolution = apply_camera_resolution(job, scene)
        camera_name = getattr(scene.camera, "name", None)
        if camera_name != previous_camera_name or resolution != previous_resolution:
            print(f"[blender:camera] Frame {frame}: {camera_name} at {resolution[0]}x{resolution[1]} {resolution[2]}%.")
            previous_camera_name = camera_name
            previous_resolution = resolution
        scene.render.filepath = str(render_dir / f"frame_{frame:05d}")
        bpy.ops.render.render(write_still=True)


def main() -> None:
    job_path = parse_blender_args()
    job = load_json(job_path)
    job_id = str(job["job_id"])
    temp_dir = PROJECT_ROOT / "assets" / "temp" / job_id
    render_dir = PROJECT_ROOT / "assets" / "renders" / job_id
    mouth_path = temp_dir / "mouth_cues.json"
    audio_path = temp_dir / "audio.wav"

    mouth_data = load_json(mouth_path)
    mouth_cues = mouth_data.get("mouthCues", [])
    configure_render(job, mouth_data.get("metadata", {}))
    add_audio_to_timeline(audio_path)

    face_mode = str(job.get("face_mode", "2d")).lower()
    if face_mode == "3d":
        avatar_mesh = find_avatar_mesh()
        if avatar_mesh is not None:
            apply_3d_mouth_animation(avatar_mesh, mouth_cues, int(job.get("fps", 30)))
    else:
        apply_2d_mouth_animation(job, mouth_cues, int(job.get("fps", 30)))

    fps = int(job.get("fps", 30))
    apply_performance_beats(job, fps)
    apply_action_gestures(bpy, job, fps, bpy.context.scene.frame_start, bpy.context.scene.frame_end)
    add_camera_cuts(bpy, bpy.context.scene, job.get("camera_cuts", []), fps)

    render_dir.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(render_dir / "frame_#####")
    print(f"[blender] Rendering PNG frames to: {render_dir}")
    render_frame_sequence(job, render_dir)


if __name__ == "__main__":
    main()
