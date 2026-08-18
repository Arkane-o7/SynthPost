from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.channels import (
    get_channel_profile,
    resolved_production,
    script_prompt_context,
)
from pipeline.direction.avatar import browser_avatar_job_from_manifest
from pipeline.narration.service import _request
from pipeline.presenters import render_presenter
from pipeline.models import ScriptDocument, ScriptSection, ScriptStatus
from pipeline.storage import read_manifest, write_manifest


def script() -> ScriptDocument:
    return ScriptDocument(
        story_id="story_channel",
        status=ScriptStatus.approved,
        headline="A channel-owned story",
        dek="Testing production identity",
        category="test",
        sections=[
            ScriptSection(
                section_id="section_001",
                section_type="intro",
                text="This is a complete channel-specific narration beat.",
                claim_ids=["claim_001"],
            )
        ],
    )


class ChannelPackageTests(unittest.TestCase):
    def test_only_synthpost_channel_package_remains(self) -> None:
        synthpost = get_channel_profile("synthpost")
        production = resolved_production(synthpost)
        request = _request(script(), synthpost, test_mode=True)
        self.assertEqual(synthpost.name, "SynthPost")
        self.assertIn("generic futurism", script_prompt_context(synthpost))
        self.assertEqual(production["composition_template"], "timeline_story_synthpost")
        self.assertEqual(request["channel_id"], "synthpost")
        self.assertEqual(request["provider"], "dots_tts")

    def test_synthpost_owns_separate_preview_and_final_renderers(self) -> None:
        production = resolved_production(get_channel_profile("synthpost"))
        self.assertEqual(production["presenter_preview_renderer"], "rocketbox")
        self.assertEqual(production["presenter_final_renderer"], "blender_cc")

    def test_avatar_job_uses_manifest_presenter_package(self) -> None:
        profile = get_channel_profile("synthpost")
        production = resolved_production(profile)
        manifest = {
            "story_id": "story_synthpost",
            "episode_id": "episode_synthpost",
            "channel": {"production": production},
            "script": {"text": "A short presenter test."},
            "composition": {"template": production["composition_template"]},
            "narration": {},
        }
        with tempfile.TemporaryDirectory() as temp, patch(
            "pipeline.direction.avatar.resolve_project_path",
            side_effect=lambda value: Path(temp) / Path(str(value)).name,
        ):
            job = browser_avatar_job_from_manifest(
                manifest,
                12.0,
                render_profile="preview",
                renderer="rocketbox",
            )
        self.assertEqual(job["avatar"]["asset_path"], production["presenter_asset_path"])
        self.assertEqual(job["avatar"]["metadata_path"], production["presenter_metadata_path"])
        self.assertEqual(job["avatar"]["style"], "professional_technology_anchor")

    def test_video_file_presenter_replaces_avatar_engine_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            presenter = root / "presenter.mp4"
            presenter.write_bytes(b"presenter")
            manifest_path = root / "story.json"
            write_manifest(
                manifest_path,
                {
                    "story_id": "story_external",
                    "episode_id": "episode_external",
                    "channel_id": "synthpost",
                    "channel": {
                        "production": {
                            "presenter_provider": "video_file",
                            "presenter_asset_path": str(presenter),
                            "presenter_style": "external_news_presenter",
                            "presenter_background": "transparent",
                        }
                    },
                    "narration": {"duration_seconds": 12.0},
                },
            )
            with patch(
                "pipeline.presenters.render.ffprobe_summary",
                return_value={
                    "duration_seconds": 12.0,
                    "video_codec": "h264",
                    "audio_codec": "aac",
                },
            ):
                direction = render_presenter(manifest_path, render_profile="preview")
            self.assertEqual(direction["presenter_provider"], "video_file")
            self.assertEqual(
                Path(direction["anchor_output_path"]).resolve(), presenter.resolve()
            )
            self.assertEqual(
                read_manifest(manifest_path)["direction"]["presenter_profile"],
                "external_news_presenter",
            )

if __name__ == "__main__":
    unittest.main()
