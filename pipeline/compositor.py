from __future__ import annotations

import subprocess
from pathlib import Path
import sys

from . import config
from .provenance import artifact_record, record_story_artifact
from .render_profiles import resolve_profile
from .storage import output_is_fresh, read_manifest, resolve_project_path, write_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from synthpost.visuals.compositor_bridge import apply_compositor_bridge  # noqa: E402


def render_story(
    story_json_path: str | Path,
    *,
    force: bool = False,
    test_mode: bool = False,
    render_profile: str = "production",
) -> Path:
    manifest = read_manifest(story_json_path)
    previous_bridge = {
        "compositor_visuals": manifest.get("compositor_visuals"),
        "visual_compositor_bridge": manifest.get("visual_compositor_bridge"),
    }
    manifest = apply_compositor_bridge(manifest, story_json_path)
    next_bridge = {
        "compositor_visuals": manifest.get("compositor_visuals"),
        "visual_compositor_bridge": manifest.get("visual_compositor_bridge"),
    }
    if next_bridge != previous_bridge:
        write_manifest(story_json_path, manifest)
    composition = manifest.get("composition", {})
    output_path = resolve_project_path(composition.get("output_path", ""))
    profile = resolve_profile(render_profile)

    inputs = [story_json_path]
    direction = manifest.get("direction", {})
    if isinstance(direction, dict) and direction.get("anchor_output_path"):
        inputs.append(direction["anchor_output_path"])
    for visual in manifest.get("compositor_visuals") or manifest.get("visuals", []):
        if isinstance(visual, dict) and visual.get("path"):
            inputs.append(visual["path"])

    if output_is_fresh(output_path, inputs) and not force:
        print(f"[compositor] Reusing fresh render: {output_path}")
        preview_path = resolve_project_path(composition.get("preview_path", output_path.with_name("preview.png").as_posix()))
        record_story_artifact(
            story_json_path,
            "composited_video",
            artifact_record(
                path=output_path,
                stage="compositor",
                input_paths=inputs,
                provider="remotion",
                fresh=False,
                reused=True,
                test_mode=test_mode,
                render_profile=profile.name,
                flags={"force": force},
                metadata={"visual_bridge": manifest.get("visual_compositor_bridge")},
            ),
        )
        if preview_path.exists():
            record_story_artifact(
                story_json_path,
                "composition_preview",
                artifact_record(
                    path=preview_path,
                    stage="compositor",
                    input_paths=inputs,
                    provider="remotion",
                    fresh=False,
                    reused=True,
                    test_mode=test_mode,
                    render_profile=profile.name,
                    flags={"force": force},
                    metadata={"visual_bridge": manifest.get("visual_compositor_bridge")},
                ),
            )
        return output_path

    remotion_dir = config.remotion_dir()
    package_json = remotion_dir / "package.json"
    if not package_json.exists():
        raise FileNotFoundError(f"Remotion renderer package not found: {package_json}")

    command = ["npm", "run", "render:story", "--", str(resolve_project_path(story_json_path))]
    if force:
        command.append("--force")
    if test_mode:
        print("[TEST_MODE] WARNING: Remotion composition is using TEST_MODE inputs.")
    print(f"[compositor] Running Remotion renderer: {' '.join(command)}")
    subprocess.run(command, cwd=remotion_dir, check=True)
    if not output_path.exists():
        raise FileNotFoundError(f"Remotion did not create expected composition: {output_path}")
    rendered_manifest = read_manifest(story_json_path)
    rendered_composition = rendered_manifest.get("composition", {}) if isinstance(rendered_manifest.get("composition"), dict) else {}
    preview_path = resolve_project_path(rendered_composition.get("preview_path", output_path.with_name("preview.png").as_posix()))
    record_story_artifact(
        story_json_path,
        "composited_video",
        artifact_record(
            path=output_path,
            stage="compositor",
            input_paths=inputs,
            provider="remotion",
            fresh=True,
            reused=False,
            test_mode=test_mode,
            render_profile=profile.name,
            command=command,
            flags={"force": force},
            metadata={"visual_bridge": rendered_manifest.get("visual_compositor_bridge")},
        ),
    )
    if preview_path.exists():
        record_story_artifact(
            story_json_path,
            "composition_preview",
            artifact_record(
                path=preview_path,
                stage="compositor",
                input_paths=inputs,
                provider="remotion",
                fresh=True,
                reused=False,
                test_mode=test_mode,
                render_profile=profile.name,
                command=command,
                flags={"force": force},
                metadata={"visual_bridge": rendered_manifest.get("visual_compositor_bridge")},
            ),
        )
    return output_path
