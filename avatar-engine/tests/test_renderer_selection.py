"""Tests: renderer selection and factory logic.

Coverage
--------
* Job renderer field drives selection
* AVATAR_ENGINE_RENDERER env var drives selection
* CLI --renderer override takes priority
* Unknown renderer name fails clearly
* Default falls back to blender
* TalkingHead fallback to Blender only with explicit env flag
* 2D face fallback only with explicit env flag
* BlenderAvatarRenderer.name == "blender"
* TalkingHeadAvatarRenderer.name == "talkinghead"
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from avatar_engine.renderer_base import AvatarJob
from avatar_engine.renderer_factory import (
    allow_2d_face_fallback,
    allow_renderer_fallback,
    get_renderer,
    resolve_renderer_name,
)

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _make_job(renderer: str = "blender", **extra) -> AvatarJob:
    raw = {"renderer": renderer, **extra}
    return AvatarJob(raw=raw)


# --------------------------------------------------------------------------- #
# Renderer name resolution                                                      #
# --------------------------------------------------------------------------- #


class TestResolveRendererName(unittest.TestCase):
    def test_talkinghead_in_job(self) -> None:
        job = _make_job("talkinghead")
        self.assertEqual(resolve_renderer_name(job), "talkinghead")

    def test_blender_in_job(self) -> None:
        job = _make_job("blender")
        self.assertEqual(resolve_renderer_name(job), "blender")

    def test_cli_override_takes_priority(self) -> None:
        job = _make_job("blender")
        result = resolve_renderer_name(job, override="talkinghead")
        self.assertEqual(result, "talkinghead")

    def test_env_var_drives_selection(self) -> None:
        job = _make_job("blender")
        with patch.dict(os.environ, {"AVATAR_ENGINE_RENDERER": "talkinghead"}):
            result = resolve_renderer_name(job)
        self.assertEqual(result, "talkinghead")

    def test_cli_override_beats_env_var(self) -> None:
        job = _make_job("blender")
        with patch.dict(os.environ, {"AVATAR_ENGINE_RENDERER": "blender"}):
            result = resolve_renderer_name(job, override="talkinghead")
        self.assertEqual(result, "talkinghead")

    def test_unknown_renderer_raises_value_error(self) -> None:
        job = _make_job("blender")
        with self.assertRaises(ValueError) as ctx:
            resolve_renderer_name(job, override="invalid_renderer")
        self.assertIn("invalid_renderer", str(ctx.exception))

    def test_unknown_renderer_in_env_raises_value_error(self) -> None:
        job = _make_job("blender")
        with patch.dict(os.environ, {"AVATAR_ENGINE_RENDERER": "godot"}):
            with self.assertRaises(ValueError):
                resolve_renderer_name(job)

    def test_default_is_blender(self) -> None:
        """A job without a renderer key defaults to blender."""
        job = AvatarJob(raw={})
        self.assertEqual(resolve_renderer_name(job), "blender")


# --------------------------------------------------------------------------- #
# Renderer factory                                                              #
# --------------------------------------------------------------------------- #


class TestGetRenderer(unittest.TestCase):
    def test_get_blender_renderer(self) -> None:
        from avatar_engine.blender_renderer import BlenderAvatarRenderer

        job = _make_job("blender")
        renderer = get_renderer(job, override="blender")
        self.assertIsInstance(renderer, BlenderAvatarRenderer)
        self.assertEqual(renderer.name, "blender")

    def test_get_talkinghead_renderer(self) -> None:
        from avatar_engine.talkinghead_renderer import TalkingHeadAvatarRenderer

        job = _make_job("talkinghead")
        renderer = get_renderer(job, override="talkinghead")
        self.assertIsInstance(renderer, TalkingHeadAvatarRenderer)
        self.assertEqual(renderer.name, "talkinghead")

    def test_renderer_name_blender(self) -> None:
        from avatar_engine.blender_renderer import BlenderAvatarRenderer

        r = BlenderAvatarRenderer()
        self.assertEqual(r.name, "blender")

    def test_renderer_name_talkinghead(self) -> None:
        from avatar_engine.talkinghead_renderer import TalkingHeadAvatarRenderer

        r = TalkingHeadAvatarRenderer()
        self.assertEqual(r.name, "talkinghead")


# --------------------------------------------------------------------------- #
# Fallback flags                                                                #
# --------------------------------------------------------------------------- #


class TestFallbackFlags(unittest.TestCase):
    def test_renderer_fallback_off_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AVATAR_ENGINE_ALLOW_RENDERER_FALLBACK", None)
            self.assertFalse(allow_renderer_fallback())

    def test_renderer_fallback_on_when_env_set(self) -> None:
        with patch.dict(os.environ, {"AVATAR_ENGINE_ALLOW_RENDERER_FALLBACK": "1"}):
            self.assertTrue(allow_renderer_fallback())

    def test_renderer_fallback_not_on_for_zero(self) -> None:
        with patch.dict(os.environ, {"AVATAR_ENGINE_ALLOW_RENDERER_FALLBACK": "0"}):
            self.assertFalse(allow_renderer_fallback())

    def test_2d_face_fallback_off_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AVATAR_ENGINE_ALLOW_2D_FACE_FALLBACK", None)
            self.assertFalse(allow_2d_face_fallback())

    def test_2d_face_fallback_on_when_env_set(self) -> None:
        with patch.dict(os.environ, {"AVATAR_ENGINE_ALLOW_2D_FACE_FALLBACK": "1"}):
            self.assertTrue(allow_2d_face_fallback())

    def test_no_implicit_talkinghead_to_blender_fallback(self) -> None:
        """Without AVATAR_ENGINE_ALLOW_RENDERER_FALLBACK, fallback is False."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AVATAR_ENGINE_ALLOW_RENDERER_FALLBACK", None)
            # Explicit assertion: no implicit fallback
            self.assertFalse(allow_renderer_fallback())

    def test_no_implicit_3d_to_2d_face_fallback(self) -> None:
        """Without AVATAR_ENGINE_ALLOW_2D_FACE_FALLBACK, 2D fallback is False."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AVATAR_ENGINE_ALLOW_2D_FACE_FALLBACK", None)
            self.assertFalse(allow_2d_face_fallback())


# --------------------------------------------------------------------------- #
# Blender renderer backward compatibility                                       #
# --------------------------------------------------------------------------- #


class TestBlenderRendererBackwardCompat(unittest.TestCase):
    def test_legacy_job_missing_renderer_field_defaults_to_blender(self) -> None:
        legacy = {
            "job_id": "legacy_001",
            "script": "Hello.",
            "character": "avatar_01",
            "fps": 30,
            "resolution": [1920, 1080],
            "output_path": "assets/output/legacy.mp4",
        }
        job = AvatarJob(raw=legacy)
        self.assertEqual(job.renderer, "blender")
        name = resolve_renderer_name(job)
        self.assertEqual(name, "blender")

    def test_blender_renderer_validate_job_fails_for_talkinghead_format(self) -> None:
        """BlenderAvatarRenderer should reject a TalkingHead-format job clearly."""
        import json

        from avatar_engine.blender_renderer import BlenderAvatarRenderer

        with (
            Path(__file__).parent / "fixtures" / "sample_talkinghead_job.json"
        ).open() as fh:
            th_job_dict = json.load(fh)
        th_job_dict["renderer"] = "blender"
        job = AvatarJob(raw=th_job_dict)
        renderer = BlenderAvatarRenderer()
        with self.assertRaises(ValueError):
            renderer.validate_job(job)


if __name__ == "__main__":
    unittest.main()
