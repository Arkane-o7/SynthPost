from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.channels import (
    get_channel_profile,
    prompt_identity,
    resolved_production,
    script_prompt_context,
    segmentation_prompt_context,
    visual_prompt_context,
)
from pipeline.direction.avatar import browser_avatar_job_from_manifest
from pipeline.narration.service import _request
from pipeline.presenters import render_presenter
from pipeline.models import (
    ContentRole,
    MediaType,
    ScriptDocument,
    ScriptSection,
    ScriptStatus,
    VisualCandidate,
)
from pipeline.storage import read_manifest, write_manifest
from pipeline.timeline.planner import select_template, storytime_scene_cue


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
    def test_each_channel_owns_distinct_prompts_and_production_assets(self) -> None:
        profiles = [
            get_channel_profile(value)
            for value in ("synthpost", "meridian", "beyond", "storytime")
        ]
        self.assertEqual(len({item.prompts.script for item in profiles}), 4)
        self.assertEqual(len({item.prompts.segmentation for item in profiles}), 4)
        self.assertEqual(len({item.prompts.visual_search for item in profiles}), 4)
        self.assertEqual(len({item.production.composition_template for item in profiles}), 4)
        self.assertEqual(len({item.production.presenter_asset_path for item in profiles}), 4)
        self.assertEqual(len({item.production.narrator_voice_id for item in profiles}), 4)
        self.assertEqual(len({item.production.outro_path for item in profiles}), 4)
        self.assertEqual(len({item.production.brand.accent for item in profiles}), 4)

    def test_prompt_packages_have_channel_specific_editorial_rules(self) -> None:
        synthpost = get_channel_profile("synthpost")
        meridian = get_channel_profile("meridian")
        beyond = get_channel_profile("beyond")
        storytime = get_channel_profile("storytime")
        self.assertIn("generic futurism", script_prompt_context(synthpost))
        self.assertIn("who pays, who benefits", script_prompt_context(meridian))
        self.assertIn("what each side says", script_prompt_context(beyond))
        self.assertIn("fewer, longer analytical sections", segmentation_prompt_context(meridian))
        self.assertIn("original event footage", visual_prompt_context(beyond))
        self.assertIn("first-person animated story", script_prompt_context(storytime))
        self.assertIn("four-to-nine-second", segmentation_prompt_context(storytime))
        self.assertIn("procedural animation", visual_prompt_context(storytime))
        self.assertEqual(
            prompt_identity(meridian, "narrative-script"),
            "meridian.narrative-script.prompts-v3",
        )

    def test_storytime_owns_procedural_cast_and_voice(self) -> None:
        profile = get_channel_profile("storytime")
        production = resolved_production(profile)
        request = _request(script(), profile, test_mode=True)
        self.assertEqual(profile.name, "Sidequest")
        self.assertEqual(production["composition_template"], "timeline_story_storytime")
        self.assertEqual(production["presenter_provider"], "procedural_puppet")
        self.assertEqual(production["presenter_renderer"], "remotion")
        self.assertIsNone(production["presenter_asset_path"])
        self.assertEqual(request["channel_id"], "storytime")
        self.assertEqual(request["provider"], "edge_tts")
        self.assertEqual(request["voice_id"], "en-US-AvaMultilingualNeural")
        self.assertEqual(request["voice_speed"], 1.04)
        self.assertIsNone(request["voice_profile_path"])

    def test_storytime_template_policy_maps_story_beats_to_scene_grammar(self) -> None:
        opening = select_template(
            "hook",
            None,
            0,
            total_sections=4,
            script_text="This is the moment I knew I had made a mistake.",
            template_policy="storytime_animation_v1",
        )
        dialogue = select_template(
            "development",
            None,
            1,
            total_sections=4,
            script_text='Then she asked, "Did you actually send that?"',
            template_policy="storytime_animation_v1",
        )
        imagined = select_template(
            "development",
            None,
            2,
            total_sections=4,
            script_text="In my head, the entire school had already seen it.",
            template_policy="storytime_animation_v1",
        )
        cue = storytime_scene_cue(
            script_text="I froze in the classroom while everyone stared.",
            section_type="development",
            section_index=2,
            shot_index=0,
        )
        self.assertEqual(opening.template_id, "storytime_cold_open")
        self.assertEqual(dialogue.template_id, "storytime_dialogue_two_shot")
        self.assertEqual(imagined.template_id, "storytime_imagination_burst")
        self.assertEqual(cue["location"], "school")
        self.assertEqual(cue["action"], "freeze")

        local_memory = VisualCandidate(
            story_id="story_storytime",
            provider="local_upload",
            media_type=MediaType.image,
            content_role=ContentRole.context,
        )
        decorative_search_result = local_memory.model_copy(
            update={"provider": "searxng"}
        )
        memory = select_template(
            "development",
            local_memory,
            1,
            total_sections=4,
            script_text="This is the photo I kept.",
            template_policy="storytime_animation_v1",
        )
        procedural = select_template(
            "development",
            decorative_search_result,
            1,
            total_sections=4,
            script_text="Then she asked what I had done.",
            template_policy="storytime_animation_v1",
        )
        self.assertEqual(memory.template_id, "storytime_memory_cutaway")
        self.assertEqual(procedural.template_id, "storytime_dialogue_two_shot")

    def test_narration_request_uses_channel_voice_not_global_voice(self) -> None:
        meridian = get_channel_profile("meridian")
        request = _request(script(), meridian, test_mode=True)
        self.assertEqual(request["channel_id"], "meridian")
        self.assertEqual(request["voice_id"], "meridian_narrator")
        self.assertEqual(request["voice_speed"], 0.94)
        self.assertIn("meridian.dtprofile", str(request["voice_profile_path"]))

    def test_meridian_uses_png_presenter_package(self) -> None:
        meridian = get_channel_profile("meridian")
        production = resolved_production(meridian)
        self.assertEqual(production["presenter_provider"], "png_puppet")
        self.assertEqual(production["presenter_renderer"], "remotion")
        self.assertIn(
            "meridian/presenter/character.json",
            production["presenter_asset_path"],
        )

    def test_synthpost_owns_separate_preview_and_final_renderers(self) -> None:
        production = resolved_production(get_channel_profile("synthpost"))
        self.assertEqual(production["presenter_preview_renderer"], "rocketbox")
        self.assertEqual(production["presenter_final_renderer"], "blender_cc")

    def test_avatar_job_uses_manifest_presenter_package(self) -> None:
        profile = get_channel_profile("beyond")
        production = resolved_production(profile)
        manifest = {
            "story_id": "story_beyond",
            "episode_id": "episode_beyond",
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
        self.assertEqual(job["avatar"]["style"], "international_news_anchor")

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
                    "channel_id": "beyond",
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

    def test_png_presenter_pins_character_and_exact_narration_clock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            neutral = root / "neutral.png"
            speaking = root / "speaking.png"
            neutral.write_bytes(b"neutral pose")
            speaking.write_bytes(b"speaking pose")
            character = root / "character.json"
            character.write_text(
                json.dumps(
                    {
                        "contract_version": "synthea.presenter.png_puppet.v1",
                        "character_id": "meridian_test",
                        "name": "Meridian Test Analyst",
                        "poses": {
                            "neutral": str(neutral),
                            "speaking": str(speaking),
                        },
                    }
                ),
                encoding="utf-8",
            )
            narration = root / "narration.wav"
            narration.write_bytes(b"narration")
            manifest_path = root / "story.json"
            write_manifest(
                manifest_path,
                {
                    "story_id": "story_meridian",
                    "episode_id": "episode_meridian",
                    "channel_id": "meridian",
                    "channel": {
                        "production": {
                            "presenter_provider": "png_puppet",
                            "presenter_asset_path": str(character),
                            "presenter_style": "meridian_editorial_analyst",
                            "presenter_background": "transparent",
                        }
                    },
                    "narration": {
                        "audio_path": str(narration),
                        "duration_seconds": 12.0,
                        "timing_source": "tts_exact_samples",
                        "beats": [
                            {
                                "start_time": 0.0,
                                "speech_end_time": 11.6,
                                "end_time": 12.0,
                            }
                        ],
                    },
                },
            )
            with patch(
                "pipeline.presenters.render.ffprobe_summary",
                return_value={
                    "duration_seconds": 12.0,
                    "audio_codec": "pcm_s16le",
                },
            ):
                direction = render_presenter(manifest_path, render_profile="preview")

            self.assertEqual(direction["presenter_provider"], "png_puppet")
            self.assertEqual(direction["duration_source"], "canonical_narration")
            self.assertEqual(
                set(direction["presenter_pose_paths"]),
                {"neutral", "speaking"},
            )
            self.assertEqual(
                Path(direction["presenter_manifest_path"]).resolve(),
                character.resolve(),
            )
            self.assertEqual(
                Path(direction["narration_audio_path"]).resolve(),
                narration.resolve(),
            )
            self.assertNotIn("anchor_output_path", direction)

    def test_procedural_presenter_uses_narration_as_master_clock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            narration = root / "narration.wav"
            narration.write_bytes(b"narration")
            manifest_path = root / "story.json"
            write_manifest(
                manifest_path,
                {
                    "story_id": "story_storytime",
                    "episode_id": "episode_storytime",
                    "channel_id": "storytime",
                    "channel": {
                        "production": {
                            "presenter_provider": "procedural_puppet",
                            "presenter_style": "sidequest_line_cast",
                            "presenter_background": "transparent",
                        }
                    },
                    "narration": {
                        "audio_path": str(narration),
                        "duration_seconds": 9.0,
                        "timing_source": "tts_exact_samples",
                        "beats": [
                            {
                                "start_time": 0.0,
                                "speech_end_time": 8.7,
                                "end_time": 9.0,
                            }
                        ],
                    },
                },
            )
            with patch(
                "pipeline.presenters.render.ffprobe_summary",
                return_value={"duration_seconds": 9.0, "audio_codec": "pcm_s16le"},
            ):
                direction = render_presenter(manifest_path, render_profile="preview")

            self.assertEqual(direction["presenter_provider"], "procedural_puppet")
            self.assertEqual(direction["presenter_renderer"], "remotion")
            self.assertEqual(direction["duration_source"], "canonical_narration")
            self.assertEqual(
                Path(direction["narration_audio_path"]).resolve(),
                narration.resolve(),
            )
            self.assertNotIn("anchor_output_path", direction)


if __name__ == "__main__":
    unittest.main()
