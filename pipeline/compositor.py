from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from . import config
from .provenance import artifact_record, record_story_artifact
from .render_profiles import resolve_profile
from .storage import output_is_fresh, read_manifest, resolve_project_path


def _visual_input_paths(manifest: dict[str, Any]) -> list[str | Path]:
    inputs: list[str | Path] = []
    for visual in manifest.get("compositor_visuals") or manifest.get("visuals") or []:
        if isinstance(visual, dict) and visual.get("path"):
            inputs.append(str(visual["path"]))
    timeline = (
        manifest.get("approved_timeline")
        if isinstance(manifest.get("approved_timeline"), dict)
        else {}
    )
    for segment in (
        timeline.get("segments", [])
        if isinstance(timeline.get("segments"), list)
        else []
    ):
        visual = segment.get("visual") if isinstance(segment, dict) else None
        if isinstance(visual, dict) and visual.get("path"):
            inputs.append(str(visual["path"]))
    return inputs


def render_story(
    story_json_path: str | Path,
    *,
    force: bool = False,
    test_mode: bool = False,
    render_profile: str = "production",
) -> Path:
    """Render a story manifest with the retained Remotion renderer.

    This is intentionally a thin wrapper after the pipeline rip-out: it no longer
    plans, ranks, bridges, or mutates visuals. The story manifest must already
    contain render-ready `visuals`, `compositor_visuals`, or `approved_timeline`.
    """

    manifest = read_manifest(story_json_path)
    composition = (
        manifest.get("composition", {})
        if isinstance(manifest.get("composition"), dict)
        else {}
    )
    output_path = resolve_project_path(composition.get("output_path", ""))
    if not str(composition.get("output_path", "")).strip():
        story_path = resolve_project_path(story_json_path)
        output_path = story_path.with_name("composited.mp4")
    profile = resolve_profile(render_profile)

    inputs: list[str | Path] = [story_json_path]
    direction = (
        manifest.get("direction", {})
        if isinstance(manifest.get("direction"), dict)
        else {}
    )
    if direction.get("anchor_output_path"):
        inputs.append(str(direction["anchor_output_path"]))
    inputs.extend(_visual_input_paths(manifest))

    if output_is_fresh(output_path, inputs) and not force:
        print(f"[compositor] Reusing fresh render: {output_path}")
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
            ),
        )
        return output_path

    remotion_dir = config.remotion_dir()
    package_json = remotion_dir / "package.json"
    if not package_json.exists():
        raise FileNotFoundError(f"Remotion renderer package not found: {package_json}")

    command = [
        "npm",
        "run",
        "render:story",
        "--",
        str(resolve_project_path(story_json_path)),
    ]
    if force:
        command.append("--force")
    if test_mode:
        print("[TEST_MODE] WARNING: Remotion composition is using TEST_MODE inputs.")
    print(f"[compositor] Running Remotion renderer: {' '.join(command)}")
    subprocess.run(command, cwd=remotion_dir, check=True)
    if not output_path.exists():
        raise FileNotFoundError(
            f"Remotion did not create expected composition: {output_path}"
        )

    rendered_manifest = read_manifest(story_json_path)
    rendered_composition = (
        rendered_manifest.get("composition", {})
        if isinstance(rendered_manifest.get("composition"), dict)
        else {}
    )
    preview_path = resolve_project_path(
        rendered_composition.get(
            "preview_path", output_path.with_name("preview.png").as_posix()
        )
    )
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
            metadata={
                "composition_id": rendered_composition.get("composition_id"),
                "timeline_source": rendered_composition.get("timeline_source"),
            },
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
            ),
        )
    return output_path
