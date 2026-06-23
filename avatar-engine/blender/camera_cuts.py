from __future__ import annotations

from typing import Any

CAMERA_NAME_MAP: dict[str, str] = {
    "portrait_main": "CAM_Portrait_Main",
    "landscape_intro": "CAM_Landscape_Intro",
    "landscape_conclusion": "CAM_Landscape_Conclusion",
    # Backwards-compatible aliases for older job files.
    "front_medium": "CAM_Portrait_Main",
    "front_close": "CAM_Landscape_Conclusion",
    "side_threequarter": "CAM_Landscape_Intro",
}


def seconds_to_frames(seconds: float, fps: int) -> int:
    return max(1, int(round(seconds * fps)) + 1)


def lookup_camera(bpy_module: Any, camera_key: str) -> Any | None:
    object_name = CAMERA_NAME_MAP.get(camera_key, camera_key)
    camera = bpy_module.data.objects.get(object_name)
    if camera is None:
        print(f"[blender:camera] WARNING: Camera '{object_name}' is missing.")
    return camera


def add_camera_cuts(bpy_module: Any, scene: Any, cuts: list[dict], fps: int) -> None:
    if not cuts:
        print("[blender:camera] No camera cuts defined.")
        return

    for cut in cuts:
        start_seconds = float(cut.get("start", 0.0))
        camera_key = str(cut.get("camera", "portrait_main"))
        camera = lookup_camera(bpy_module, camera_key)
        if camera is None:
            continue
        frame = seconds_to_frames(start_seconds, fps)
        marker = scene.timeline_markers.new(f"cut_{camera_key}_{frame}", frame=frame)
        marker.camera = camera
        if scene.camera is None:
            scene.camera = camera
        print(f"[blender:camera] Added camera cut '{camera_key}' at frame {frame}.")
