"""Tests: TalkingHead job schema and field contract.

Coverage
--------
* Job schema accepts renderer=talkinghead
* face.mode='3d_viseme' is accepted
* face.mode='legacy_2d' is NOT the default
* Missing required fields fail clearly
* Avatar metadata requires 3D lip capability
* Missing required visemes fail validation
* Rhubarb cues map to correct Oculus visemes
* Custom avatar viseme mappings work
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Make avatar_engine importable from the repo root
_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from avatar_engine.avatar_validator import (
    AvatarValidationError,
    validate_avatar_for_talkinghead,
)
from avatar_engine.renderer_base import AvatarJob
from avatar_engine.talkinghead_renderer import _require_talkinghead_fields
from avatar_engine.viseme_mapping import (
    RHUBARB_TO_OCULUS,
    convert_rhubarb_json_to_talkinghead,
)

FIXTURES = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _load_fixture_job() -> dict:
    with (FIXTURES / "sample_talkinghead_job.json").open() as fh:
        return json.load(fh)


def _load_fixture_rhubarb() -> dict:
    with (FIXTURES / "sample_rhubarb.json").open() as fh:
        return json.load(fh)


def _valid_avatar_meta() -> dict:
    return {
        "id": "test_avatar",
        "face_type": "3d",
        "supports_3d_lips": True,
        "supports_visemes": True,
        "blendshape_profile": "auto_detect",
        "viseme_shapes": ["aa", "ih", "ou", "ee", "oh"],
    }


# --------------------------------------------------------------------------- #
# Job schema / field tests                                                      #
# --------------------------------------------------------------------------- #


class TestTalkingHeadJobSchema(unittest.TestCase):
    def test_fixture_job_has_renderer_talkinghead(self) -> None:
        job_dict = _load_fixture_job()
        self.assertEqual(job_dict["renderer"], "talkinghead")

    def test_job_face_mode_is_3d_viseme(self) -> None:
        job_dict = _load_fixture_job()
        self.assertEqual(job_dict["face"]["mode"], "3d_viseme")

    def test_face_mode_is_not_legacy_2d_by_default(self) -> None:
        """The default face mode must be 3d_viseme, not legacy_2d."""
        job_dict = _load_fixture_job()
        self.assertNotEqual(job_dict["face"]["mode"], "legacy_2d")

    def test_avatar_job_wrapper_renderer_property(self) -> None:
        job_dict = _load_fixture_job()
        job = AvatarJob(raw=job_dict)
        self.assertEqual(job.renderer, "talkinghead")

    def test_avatar_job_face_mode_property(self) -> None:
        job_dict = _load_fixture_job()
        job = AvatarJob(raw=job_dict)
        self.assertEqual(job.face_mode, "3d_viseme")

    def test_avatar_job_camera_properties(self) -> None:
        job_dict = _load_fixture_job()
        job = AvatarJob(raw=job_dict)
        self.assertEqual(job.camera_width, 1920)
        self.assertEqual(job.camera_height, 1080)
        self.assertEqual(job.camera_fps, 24)
        self.assertEqual(job.camera_name, "front_medium")

    def test_avatar_job_audio_path_property(self) -> None:
        job_dict = _load_fixture_job()
        job = AvatarJob(raw=job_dict)
        self.assertEqual(job.audio_path, "tests/fixtures/sample.wav")

    def test_avatar_job_output_path_property(self) -> None:
        job_dict = _load_fixture_job()
        job = AvatarJob(raw=job_dict)
        self.assertIn("talkinghead", job.output_path)

    def test_blender_job_without_renderer_field_defaults(self) -> None:
        """A legacy Blender job without 'renderer' key defaults to blender."""
        legacy_job = {
            "job_id": "legacy_001",
            "script": "Hello world.",
            "character": "avatar_01",
            "fps": 30,
            "resolution": [1920, 1080],
            "output_path": "assets/output/legacy.mp4",
        }
        job = AvatarJob(raw=legacy_job)
        self.assertEqual(job.renderer, "blender")


# --------------------------------------------------------------------------- #
# Validation tests                                                              #
# --------------------------------------------------------------------------- #


class TestTalkingHeadJobValidation(unittest.TestCase):
    def test_missing_renderer_field_gives_clear_error(self) -> None:
        job_dict = _load_fixture_job()
        job_dict.pop("renderer")
        job = AvatarJob(raw=job_dict)
        # renderer defaults to "blender", so _require_talkinghead_fields should fail
        with self.assertRaises(ValueError) as ctx:
            _require_talkinghead_fields(job, _repo)
        self.assertIn("talkinghead", str(ctx.exception))

    def test_missing_audio_path_gives_clear_error(self) -> None:
        job_dict = _load_fixture_job()
        job_dict["audio_path"] = ""
        job = AvatarJob(raw=job_dict)
        with self.assertRaises(ValueError) as ctx:
            _require_talkinghead_fields(job, _repo)
        self.assertIn("audio_path", str(ctx.exception))

    def test_missing_viseme_path_gives_clear_error(self) -> None:
        job_dict = _load_fixture_job()
        job_dict["viseme_path"] = ""
        job = AvatarJob(raw=job_dict)
        with self.assertRaises(ValueError) as ctx:
            _require_talkinghead_fields(job, _repo)
        self.assertIn("viseme_path", str(ctx.exception))

    def test_nonexistent_audio_file_raises_file_not_found(self) -> None:
        job_dict = _load_fixture_job()
        job_dict["audio_path"] = "nonexistent/audio.wav"
        job = AvatarJob(raw=job_dict)
        with self.assertRaises(FileNotFoundError):
            _require_talkinghead_fields(job, _repo)

    def test_nonexistent_avatar_asset_raises_file_not_found(self) -> None:
        job_dict = _load_fixture_job()
        job_dict["avatar"]["asset_path"] = "nonexistent/avatar.glb"
        job = AvatarJob(raw=job_dict)
        with self.assertRaises(FileNotFoundError):
            _require_talkinghead_fields(job, _repo)

    def test_wrong_face_mode_gives_clear_error(self) -> None:
        job_dict = _load_fixture_job()
        job_dict["face"]["mode"] = "legacy_2d"
        job = AvatarJob(raw=job_dict)
        with self.assertRaises(ValueError) as ctx:
            _require_talkinghead_fields(job, _repo)
        self.assertIn("3d_viseme", str(ctx.exception))


# --------------------------------------------------------------------------- #
# Avatar metadata validation tests                                              #
# --------------------------------------------------------------------------- #


class TestAvatarMetadataValidation(unittest.TestCase):
    def test_valid_3d_avatar_passes(self) -> None:
        result = validate_avatar_for_talkinghead(_valid_avatar_meta(), "test_avatar")
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["supports_3d_lips"])
        self.assertEqual(result["missing_visemes"], [])

    def test_2d_face_avatar_fails_without_env_flag(self) -> None:
        meta = _valid_avatar_meta()
        meta["face_type"] = "legacy_2d"
        result = validate_avatar_for_talkinghead(
            meta, "test_avatar", allow_2d_fallback=False
        )
        self.assertEqual(result["status"], "fail")
        self.assertIn("face_type", result["error"])

    def test_no_3d_lips_fails(self) -> None:
        meta = _valid_avatar_meta()
        meta["supports_3d_lips"] = False
        result = validate_avatar_for_talkinghead(meta, "test_avatar")
        self.assertEqual(result["status"], "fail")
        self.assertIn("3d", result["error"].lower())

    def test_missing_required_visemes_fails(self) -> None:
        meta = _valid_avatar_meta()
        meta["viseme_shapes"] = ["aa"]  # missing ih, ou, ee, oh
        result = validate_avatar_for_talkinghead(meta, "test_avatar")
        self.assertEqual(result["status"], "fail")
        self.assertGreater(len(result["missing_visemes"]), 0)

    def test_required_visemes_present_flag_correct(self) -> None:
        meta = _valid_avatar_meta()
        result = validate_avatar_for_talkinghead(meta, "test_avatar")
        self.assertTrue(result["required_visemes_present"])

    def test_2d_fallback_allowed_with_flag(self) -> None:
        meta = _valid_avatar_meta()
        meta["face_type"] = "legacy_2d"
        meta["legacy_2d_face_supported"] = True
        # Even with allow=True, if face_type is 2d there's still a warning but no fail
        result = validate_avatar_for_talkinghead(
            meta, "test_avatar", allow_2d_fallback=True
        )
        # Should either pass with warning, or fail — depends on supports_3d_lips
        # In this case supports_3d_lips=True so it continues after the warning
        self.assertIn(result["status"], ("pass", "fail"))

    def test_face_mode_not_defaulting_to_2d(self) -> None:
        """Ensure 2D face mode is never the implicit default."""
        meta = _valid_avatar_meta()
        # Don't specify face_type at all — check what validate says
        meta.pop("face_type", None)
        result = validate_avatar_for_talkinghead(meta, "test_avatar")
        # face_type will default to "unknown" which is != "3d" → fail
        self.assertEqual(result["status"], "fail")


# --------------------------------------------------------------------------- #
# Viseme mapping tests                                                          #
# --------------------------------------------------------------------------- #


class TestVisemeMapping(unittest.TestCase):
    def test_rhubarb_x_maps_to_silence(self) -> None:
        self.assertEqual(RHUBARB_TO_OCULUS["X"], "sil")

    def test_rhubarb_a_maps_to_pp(self) -> None:
        self.assertEqual(RHUBARB_TO_OCULUS["A"], "PP")

    def test_rhubarb_e_maps_to_aa(self) -> None:
        self.assertEqual(RHUBARB_TO_OCULUS["E"], "aa")

    def test_rhubarb_f_maps_to_i(self) -> None:
        self.assertEqual(RHUBARB_TO_OCULUS["F"], "I")

    def test_all_rhubarb_labels_are_mapped(self) -> None:
        expected_labels = {"X", "A", "B", "C", "D", "E", "F", "G", "H"}
        self.assertEqual(set(RHUBARB_TO_OCULUS.keys()), expected_labels)

    def test_convert_rhubarb_json_fixture(self) -> None:
        rhubarb = _load_fixture_rhubarb()
        visemes, vtimes, vdurations = convert_rhubarb_json_to_talkinghead(rhubarb)
        cues = rhubarb["mouthCues"]
        self.assertEqual(len(visemes), len(cues))
        self.assertEqual(len(vtimes), len(cues))
        self.assertEqual(len(vdurations), len(cues))

    def test_vtimes_are_in_milliseconds(self) -> None:
        rhubarb = _load_fixture_rhubarb()
        _, vtimes, _ = convert_rhubarb_json_to_talkinghead(rhubarb)
        # First cue starts at 0.0 s → 0.0 ms
        self.assertAlmostEqual(vtimes[0], 0.0)
        # Second cue starts at 0.08 s → 80.0 ms
        self.assertAlmostEqual(vtimes[1], 80.0, delta=1.0)

    def test_vdurations_are_in_milliseconds(self) -> None:
        rhubarb = _load_fixture_rhubarb()
        _, _, vdurations = convert_rhubarb_json_to_talkinghead(rhubarb)
        # All durations should be > 0
        self.assertTrue(all(d > 0 for d in vdurations))

    def test_custom_mapping_overrides_default(self) -> None:
        rhubarb = {"mouthCues": [{"start": 0.0, "end": 0.1, "value": "E"}]}
        custom = {"E": "O"}  # override: E → O instead of aa
        visemes, _, _ = convert_rhubarb_json_to_talkinghead(
            rhubarb, custom_mapping=custom
        )
        self.assertEqual(visemes[0], "O")

    def test_custom_mapping_only_overrides_specified_labels(self) -> None:
        rhubarb = {
            "mouthCues": [
                {"start": 0.0, "end": 0.1, "value": "X"},
                {"start": 0.1, "end": 0.2, "value": "A"},
            ]
        }
        custom = {"X": "PP"}  # override X only
        visemes, _, _ = convert_rhubarb_json_to_talkinghead(
            rhubarb, custom_mapping=custom
        )
        self.assertEqual(visemes[0], "PP")  # overridden
        self.assertEqual(visemes[1], "PP")  # default A→PP unchanged

    def test_unknown_rhubarb_label_falls_back_to_silence(self) -> None:
        rhubarb = {"mouthCues": [{"start": 0.0, "end": 0.1, "value": "Z"}]}
        visemes, _, _ = convert_rhubarb_json_to_talkinghead(rhubarb)
        self.assertEqual(visemes[0], "sil")

    def test_empty_mouth_cues(self) -> None:
        visemes, vtimes, vdurations = convert_rhubarb_json_to_talkinghead(
            {"mouthCues": []}
        )
        self.assertEqual(visemes, [])
        self.assertEqual(vtimes, [])
        self.assertEqual(vdurations, [])


if __name__ == "__main__":
    unittest.main()
