from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from . import config
from .storage import episode_dir, output_is_fresh, resolve_project_path


def endscreen_json_path(episode_id: str) -> Path:
    return episode_dir(episode_id) / "endscreen" / "endscreen.json"


def endscreen_output_path(episode_id: str) -> Path:
    return episode_dir(episode_id) / "endscreen" / "endscreen.mp4"


def render_endscreen(episode_id: str, *, force: bool = False) -> Path:
    json_path = endscreen_json_path(episode_id)
    if not json_path.exists():
        raise FileNotFoundError(f"Endscreen JSON not found: {json_path}")

    output_path = endscreen_output_path(episode_id)
    if output_is_fresh(output_path, [json_path]) and not force:
        print(f"[endscreen] Reusing fresh render: {output_path}")
        return output_path

    remotion_dir = config.remotion_dir()
    package_json = remotion_dir / "package.json"
    if not package_json.exists():
        raise FileNotFoundError(f"Remotion renderer package not found: {package_json}")

    command = ["npm", "run", "render:endscreen", "--", str(resolve_project_path(json_path))]
    print(f"[endscreen] Running Remotion renderer: {' '.join(command)}")
    subprocess.run(command, cwd=remotion_dir, check=True)
    if not output_path.exists():
        raise FileNotFoundError(f"Remotion did not create expected endscreen: {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a SynthPost episode endscreen.")
    parser.add_argument("episode_id")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    render_endscreen(args.episode_id, force=args.force)


if __name__ == "__main__":
    main()
