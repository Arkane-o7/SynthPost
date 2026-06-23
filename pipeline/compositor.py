from __future__ import annotations

import subprocess
from pathlib import Path

from . import config
from .storage import output_is_fresh, read_manifest, resolve_project_path


def render_story(story_json_path: str | Path, *, force: bool = False) -> Path:
    manifest = read_manifest(story_json_path)
    composition = manifest.get("composition", {})
    output_path = resolve_project_path(composition.get("output_path", ""))

    inputs = [story_json_path]
    direction = manifest.get("direction", {})
    if isinstance(direction, dict) and direction.get("anchor_output_path"):
        inputs.append(direction["anchor_output_path"])
    for visual in manifest.get("visuals", []):
        if isinstance(visual, dict) and visual.get("path"):
            inputs.append(visual["path"])

    if output_is_fresh(output_path, inputs) and not force:
        print(f"[compositor] Reusing fresh render: {output_path}")
        return output_path

    remotion_dir = config.remotion_dir()
    package_json = remotion_dir / "package.json"
    if not package_json.exists():
        raise FileNotFoundError(f"Remotion renderer package not found: {package_json}")

    command = ["npm", "run", "render:story", "--", str(resolve_project_path(story_json_path))]
    if force:
        command.append("--force")
    print(f"[compositor] Running Remotion renderer: {' '.join(command)}")
    subprocess.run(command, cwd=remotion_dir, check=True)
    if not output_path.exists():
        raise FileNotFoundError(f"Remotion did not create expected composition: {output_path}")
    return output_path
