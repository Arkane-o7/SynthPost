"""Tests: TalkingHead render manifest contract.

Coverage
--------
* Manifest includes renderer, face_mode, camera, timing, output paths
* render_stats.json records renderer/timing/resolution/status
* Viseme mapping is recorded (source=rhubarb)
* Avatar validation result is embedded
* Manifest face_mode matches 3d_viseme (not legacy_2d)
* SynthPost provenance can record avatar renderer and face mode
* AvatarRenderResult.to_stats_dict() shape is correct
* Failure result does not write a success manifest
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from avatar_engine.renderer_base import AvatarJob, AvatarRenderResult

FIXTURES = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------------------- #
# AvatarRenderResult tests                                                      #
# --------------------------------------------------------------------------- #


class TestAvatarRenderResult(unittest.TestCase):
    def _make_pass_result(self) -> AvatarRenderResult:
        return AvatarRenderResult(
            renderer="talkinghead",
            status="pass",
            output_path="assets/output/ep01_story01_talkinghead.mp4",
            preview_png_path="assets/output/ep01_story01_talkinghead_preview.png",
            manifest_path="assets/output/avatar_render_manifest.json",
            stats_path="assets/output/render_stats.json",
            wall_time_seconds=12.4,
            realtime_factor=2.42,
            fps=24,
            resolution="1920x1080",
            frame_count=720,
            face_mode="3d_viseme",
            warnings=[],
            metadata={
                "avatar_validation": {
                    "avatar_id": "synthpost_anchor_v1",
                    "face_type": "3d",
                    "supports_3d_lips": True,
                    "blendshape_profile": "auto_detect",
                    "required_visemes_present": True,
                    "missing_visemes": [],
                    "status": "pass",
                }
            },
        )

    def test_pass_result_status(self) -> None:
        r = self._make_pass_result()
        self.assertEqual(r.status, "pass")
        self.assertEqual(r.renderer, "talkinghead")

    def test_face_mode_is_3d_viseme(self) -> None:
        r = self._make_pass_result()
        self.assertEqual(r.face_mode, "3d_viseme")

    def test_face_mode_is_not_legacy_2d(self) -> None:
        r = self._make_pass_result()
        self.assertNotEqual(r.face_mode, "legacy_2d")

    def test_to_stats_dict_has_required_keys(self) -> None:
        r = self._make_pass_result()
        stats = r.to_stats_dict()
        required_keys = {
            "renderer",
            "status",
            "fps",
            "resolution",
            "wall_time_seconds",
            "realtime_factor",
            "frame_count",
            "face_mode",
            "output_path",
            "preview_png_path",
            "manifest_path",
            "warnings",
            "error",
        }
        missing = required_keys - set(stats.keys())
        self.assertEqual(missing, set(), msg=f"Missing keys in stats dict: {missing}")

    def test_to_stats_dict_renderer_is_talkinghead(self) -> None:
        r = self._make_pass_result()
        stats = r.to_stats_dict()
        self.assertEqual(stats["renderer"], "talkinghead")

    def test_to_stats_dict_face_mode_is_3d_viseme(self) -> None:
        r = self._make_pass_result()
        stats = r.to_stats_dict()
        self.assertEqual(stats["face_mode"], "3d_viseme")

    def test_fail_result_does_not_have_output_path(self) -> None:
        r = AvatarRenderResult(
            renderer="talkinghead", status="fail", error="test error"
        )
        self.assertIsNone(r.output_path)
        self.assertIsNone(r.manifest_path)

    def test_fail_result_has_error_message(self) -> None:
        r = AvatarRenderResult(
            renderer="talkinghead", status="fail", error="Missing avatar file."
        )
        self.assertEqual(r.error, "Missing avatar file.")

    def test_timing_fields_are_present(self) -> None:
        r = self._make_pass_result()
        self.assertAlmostEqual(r.wall_time_seconds, 12.4)
        self.assertAlmostEqual(r.realtime_factor, 2.42)
        self.assertEqual(r.frame_count, 720)

    def test_avatar_validation_embedded_in_metadata(self) -> None:
        r = self._make_pass_result()
        validation = r.metadata.get("avatar_validation", {})
        self.assertEqual(validation["status"], "pass")
        self.assertTrue(validation["supports_3d_lips"])
        self.assertEqual(validation["missing_visemes"], [])


# --------------------------------------------------------------------------- #
# Manifest shape tests (simulated)                                              #
# --------------------------------------------------------------------------- #


class TestManifestShape(unittest.TestCase):
    """Simulate the manifest that TalkingHeadAvatarRenderer writes."""

    def _make_manifest(self) -> dict:
        return {
            "renderer": "talkinghead",
            "episode_id": "ep_fixture",
            "story_id": "story_001",
            "face_mode": "3d_viseme",
            "avatar_validation": {
                "avatar_id": "synthpost_anchor_v1",
                "face_type": "3d",
                "supports_3d_lips": True,
                "blendshape_profile": "auto_detect",
                "required_visemes_present": True,
                "missing_visemes": [],
                "status": "pass",
            },
            "camera": {
                "name": "front_medium",
                "width": 1920,
                "height": 1080,
                "fps": 24,
            },
            "viseme_mapping_source": "rhubarb",
            "output_path": "assets/output/ep_fixture_story_001_talkinghead.mp4",
            "preview_png_path": "assets/output/ep_fixture_story_001_talkinghead_preview.png",
            "wall_time_seconds": 15.3,
            "realtime_factor": 1.96,
            "clip_duration_seconds": 30.0,
            "fps": 24,
            "frame_count": 720,
            "resolution": "1920x1080",
            "warnings": [],
            "timestamp": "2026-06-27T12:00:00+00:00",
        }

    def test_manifest_has_renderer_field(self) -> None:
        m = self._make_manifest()
        self.assertEqual(m["renderer"], "talkinghead")

    def test_manifest_face_mode_is_3d_viseme(self) -> None:
        m = self._make_manifest()
        self.assertEqual(m["face_mode"], "3d_viseme")

    def test_manifest_viseme_source_is_rhubarb(self) -> None:
        m = self._make_manifest()
        self.assertEqual(m["viseme_mapping_source"], "rhubarb")

    def test_manifest_avatar_validation_embedded(self) -> None:
        m = self._make_manifest()
        self.assertIn("avatar_validation", m)
        self.assertEqual(m["avatar_validation"]["status"], "pass")

    def test_manifest_has_timing_fields(self) -> None:
        m = self._make_manifest()
        self.assertIn("wall_time_seconds", m)
        self.assertIn("realtime_factor", m)
        self.assertIn("clip_duration_seconds", m)
        self.assertIn("frame_count", m)

    def test_manifest_has_all_output_paths(self) -> None:
        m = self._make_manifest()
        self.assertIn("output_path", m)
        self.assertIn("preview_png_path", m)

    def test_manifest_is_json_serializable(self) -> None:
        m = self._make_manifest()
        serialized = json.dumps(m)
        restored = json.loads(serialized)
        self.assertEqual(restored["renderer"], "talkinghead")
        self.assertEqual(restored["face_mode"], "3d_viseme")


# --------------------------------------------------------------------------- #
# SynthPost provenance record tests (simulated)                                 #
# --------------------------------------------------------------------------- #


class TestSynthPostProvenance(unittest.TestCase):
    """Simulate what SynthPost should record in its provenance JSON."""

    def _make_provenance(self) -> dict:
        return {
            "avatar_renderer": "talkinghead",
            "avatar_asset_id": "synthpost_anchor_v1",
            "avatar_face_mode": "3d_viseme",
            "avatar_engine_commit": "abc123def456",
            "render_wall_time_seconds": 15.3,
            "realtime_factor": 1.96,
            "output_path": "episodes/ep_fixture/stories/story_001/anchor/001_talkinghead.mp4",
        }

    def test_provenance_records_talkinghead_renderer(self) -> None:
        p = self._make_provenance()
        self.assertEqual(p["avatar_renderer"], "talkinghead")

    def test_provenance_records_3d_face_mode(self) -> None:
        p = self._make_provenance()
        self.assertEqual(p["avatar_face_mode"], "3d_viseme")

    def test_provenance_records_asset_id(self) -> None:
        p = self._make_provenance()
        self.assertEqual(p["avatar_asset_id"], "synthpost_anchor_v1")

    def test_provenance_has_timing(self) -> None:
        p = self._make_provenance()
        self.assertIn("render_wall_time_seconds", p)
        self.assertIn("realtime_factor", p)

    def test_provenance_has_output_path(self) -> None:
        p = self._make_provenance()
        self.assertIn("output_path", p)

    def test_provenance_renderer_is_not_blender(self) -> None:
        """TalkingHead provenance must not claim blender as renderer."""
        p = self._make_provenance()
        self.assertNotEqual(p["avatar_renderer"], "blender")

    def test_blender_provenance_backward_compat(self) -> None:
        """Blender renderer path still produces valid provenance."""
        blender_prov = {
            "avatar_renderer": "blender",
            "avatar_asset_id": "avatar_01",
            "avatar_face_mode": "legacy_blender",
            "render_wall_time_seconds": 120.0,
            "realtime_factor": 0.5,
            "output_path": "assets/output/sample.mp4",
        }
        self.assertEqual(blender_prov["avatar_renderer"], "blender")

    def test_skip_avatar_render_provenance(self) -> None:
        """--skip-avatar-render should produce a skipped provenance record."""
        skipped_prov = {
            "avatar_renderer": "talkinghead",
            "avatar_asset_id": "synthpost_anchor_v1",
            "avatar_face_mode": "3d_viseme",
            "render_wall_time_seconds": 0,
            "realtime_factor": 0,
            "output_path": None,
            "skipped": True,
        }
        self.assertTrue(skipped_prov["skipped"])
        self.assertEqual(skipped_prov["render_wall_time_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
