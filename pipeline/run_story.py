from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from .compositor import render_story
from .direction import avatar
from .render_profiles import apply_manifest_runtime, resolve_profile
from .storage import read_manifest, write_manifest


def run_story(
    story_json_path: str | Path,
    *,
    force_avatar: bool = False,
    force_composite: bool = False,
    skip_avatar_render: bool = False,
    test_mode: bool = False,
    assemble: bool = False,
    render_profile: str = "production",
) -> None:
    """Render a pre-authored story manifest.

    After the pipeline rip-out this entrypoint deliberately does not collect news,
    write scripts, plan visuals, generate thumbnails, or choose templates. The
    manifest must already contain the script, composition/template, visual inputs,
    and optional approved timeline needed by Avatar-Engine and Remotion.
    """

    profile = resolve_profile(render_profile)
    manifest = read_manifest(story_json_path)
    apply_manifest_runtime(manifest, render_profile=profile, test_mode=test_mode)
    write_manifest(story_json_path, manifest)
    if test_mode:
        print(
            "[TEST_MODE] WARNING: Story run is labeled TEST_MODE and must not be treated as production output."
        )

    template_name = (
        manifest.get("composition", {}).get("template")
        if isinstance(manifest.get("composition"), dict)
        else None
    )
    if avatar.template_requires_avatar(template_name):
        avatar.run(
            story_json_path,
            force=force_avatar,
            render=not skip_avatar_render,
            test_mode=test_mode,
            render_profile=profile.name,
        )
    else:
        print(
            f"[direction] Skipping Avatar-Engine for visual-only template: {template_name}"
        )

    render_story(
        story_json_path,
        force=force_composite,
        test_mode=test_mode,
        render_profile=profile.name,
    )

    if assemble:
        manifest = read_manifest(story_json_path)
        command = [
            "python3",
            "assembly/stitch_episode.py",
            str(manifest["episode_id"]),
            "--render-profile",
            profile.name,
        ]
        if test_mode:
            command.append("--test-mode")
        subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render one pre-authored SynthPost story manifest."
    )
    parser.add_argument("story_json", type=Path)
    parser.add_argument("--force-avatar", action="store_true")
    parser.add_argument("--force-composite", action="store_true")
    parser.add_argument(
        "--skip-avatar-render",
        action="store_true",
        help="Use an existing direction.anchor_output_path.",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Forward Avatar-Engine test mode when rendering.",
    )
    parser.add_argument(
        "--render-profile",
        choices=["preview", "production", "final_master"],
        default="production",
        help="Render quality profile to record and apply where supported.",
    )
    parser.add_argument(
        "--assemble",
        action="store_true",
        help="Run episode assembly after story compositing.",
    )
    args = parser.parse_args()
    run_story(
        args.story_json,
        force_avatar=args.force_avatar,
        force_composite=args.force_composite,
        skip_avatar_render=args.skip_avatar_render,
        test_mode=args.test_mode,
        assemble=args.assemble,
        render_profile=args.render_profile,
    )


if __name__ == "__main__":
    main()
