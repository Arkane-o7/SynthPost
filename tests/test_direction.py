from __future__ import annotations

import json
import os
import shutil
import unittest
from unittest.mock import patch

from pipeline.direction.avatar import (
    avatar_job_from_manifest,
    camera_cuts_for,
    camera_for_template,
    native_segment_export,
    template_requires_avatar,
)
from pipeline.storage import PROJECT_ROOT


class DirectionTemplateTests(unittest.TestCase):
    def tearDown(self) -> None:
        shutil.rmtree(
            PROJECT_ROOT / "episodes" / "ep_unit_direction", ignore_errors=True
        )
        shutil.rmtree(
            PROJECT_ROOT
            / "avatar-engine"
            / "assets"
            / "temp"
            / "synthpost"
            / "ep_unit_direction",
            ignore_errors=True,
        )

    def test_full_screen_anchor_uses_landscape_intro(self) -> None:
        self.assertEqual(camera_for_template("full_screen_anchor"), "landscape_intro")
        self.assertEqual(
            camera_for_template("news-full-screen-anchor"), "landscape_intro"
        )
        self.assertEqual(
            camera_cuts_for(20, "opening_anchor")[0]["camera"], "landscape_intro"
        )

    def test_split_main_uses_front_close(self) -> None:
        self.assertEqual(camera_for_template("split_main"), "front_close")
        self.assertEqual(camera_cuts_for(20, "split_main")[0]["camera"], "front_close")

    def test_full_screen_news_visuals_skips_avatar(self) -> None:
        self.assertFalse(template_requires_avatar("FullScreenNewsVisuals"))
        self.assertFalse(template_requires_avatar("full-screen-news-visuals"))
        self.assertTrue(template_requires_avatar("split_main"))

    def test_native_segment_export_reads_avatar_engine_manifest(self) -> None:
        anchor_path = (
            PROJECT_ROOT
            / "episodes"
            / "ep_unit_direction"
            / "stories"
            / "story_001"
            / "anchor.mp4"
        )
        export_dir = anchor_path.with_suffix("")
        segment_path = export_dir / "001_portrait_main.mp4"
        export_dir.mkdir(parents=True)
        segment_path.write_bytes(b"segment")
        (export_dir / "edit_manifest.json").write_text(
            json.dumps(
                {
                    "export_mode": "native_segments",
                    "segments": [
                        {
                            "index": 1,
                            "camera": "portrait_main",
                            "path": segment_path.as_posix(),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        export = native_segment_export(anchor_path)

        self.assertIsNotNone(export)
        assert export is not None
        self.assertEqual(export["path"], segment_path)
        self.assertEqual(export["export_mode"], "native_segments")

    def test_browser_avatar_job_matches_cc4_contract(self) -> None:
        script_text = "Good evening. This is a contract test."
        manifest = {
            "episode_id": "ep_unit_direction",
            "story_id": "story_001",
            "script": {"text": script_text},
            "composition": {"template": "split_main"},
        }
        env = {
            "SYNTHPOST_AVATAR_VOICE_ID": "af_bella",
            "SYNTHPOST_AVATAR_RENDER_BACKGROUND": "chroma_green",
            "SYNTHPOST_AVATAR_ASSET_PATH": "assets/avatars/synthpost_anchor_v1/anchor.glb",
            "SYNTHPOST_AVATAR_META_PATH": "assets/avatars/synthpost_anchor_v1/avatar.json",
        }

        with patch.dict(os.environ, env, clear=False):
            job = avatar_job_from_manifest(
                manifest, 8.2, render_profile="preview", renderer="rocketbox"
            )

        self.assertEqual(job["renderer"], "rocketbox")
        self.assertEqual(job["script"], script_text)
        self.assertEqual(job["script_text"], script_text)
        self.assertEqual(job["voice"]["voice_id"], "af_bella")
        self.assertEqual(
            job["audio_path"],
            "assets/temp/synthpost/ep_unit_direction/story_001/voice.wav",
        )
        self.assertEqual(
            job["viseme_path"],
            "assets/temp/synthpost/ep_unit_direction/story_001/rhubarb.json",
        )
        self.assertEqual(
            job["avatar"]["asset_path"], "assets/avatars/synthpost_anchor_v1/anchor.glb"
        )
        self.assertEqual(job["camera"]["name"], "front_close")
        self.assertEqual(job["camera"]["width"], 1280)
        self.assertEqual(job["camera"]["height"], 720)
        self.assertEqual(job["face"]["mode"], "3d_viseme")
        self.assertEqual(job["render"]["background"], "chroma_green")
        self.assertTrue(
            job["render"]["output_path"].endswith(
                "episodes/ep_unit_direction/stories/story_001/anchor.mp4"
            )
        )

    def test_explicit_blender_renderer_keeps_legacy_job_contract(self) -> None:
        manifest = {
            "episode_id": "ep_unit_direction",
            "story_id": "story_001",
            "script": {"text": "Good evening. This is a legacy test."},
            "composition": {"template": "full_screen_anchor"},
        }

        job = avatar_job_from_manifest(
            manifest, 10.0, render_profile="production", renderer="blender"
        )

        self.assertEqual(job["renderer"], "blender")
        self.assertEqual(job["face_mode"], "2d")
        self.assertEqual(job["camera_cuts"][0]["camera"], "landscape_intro")
        self.assertIn("output_path", job)

    def test_avatar_jobs_reuse_canonical_audio_and_exact_beat_clock(self) -> None:
        audio_path = (
            "episodes/ep_unit_direction/stories/story_001/"
            "narration/script_v001/narration.wav"
        )
        canonical_audio = PROJECT_ROOT / audio_path
        canonical_audio.parent.mkdir(parents=True, exist_ok=True)
        canonical_audio.write_bytes(b"canonical-wav")
        manifest = {
            "episode_id": "ep_unit_direction",
            "story_id": "story_001",
            "script": {"text": "First beat. Second beat."},
            "narration": {
                "audio_path": audio_path,
                "duration_seconds": 2.5,
                "beats": [
                    {"beat_id": "b1", "start_time": 0.0, "end_time": 1.1},
                    {"beat_id": "b2", "start_time": 1.1, "end_time": 2.5},
                ],
            },
            "composition": {"template": "split_main"},
        }

        browser_job = avatar_job_from_manifest(
            manifest, 2.5, render_profile="preview", renderer="rocketbox"
        )
        self.assertEqual(browser_job["audio_source"], "canonical_narration")
        self.assertEqual(
            browser_job["audio_path"],
            "assets/temp/synthpost/ep_unit_direction/story_001/voice.wav",
        )
        self.assertEqual(browser_job["canonical_audio_path"], audio_path)
        self.assertEqual(
            browser_job["animation"]["gesture_events"][0]["time"], 1.1
        )

        blender_job = avatar_job_from_manifest(
            manifest, 2.5, render_profile="preview", renderer="blender"
        )
        self.assertEqual(blender_job["audio_source"], "canonical_narration")
        self.assertEqual(blender_job["canonical_audio_path"], audio_path)
        self.assertEqual(
            blender_job["performance_beats"][1]["timing_source"],
            "kokoro_exact_samples",
        )


if __name__ == "__main__":
    unittest.main()
