from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from avatar_engine.blender_cc_renderer import (
    BlenderCCAvatarRenderer,
    build_blender_driver_job,
)
from avatar_engine.blender_render_profiles import resolve_blender_render_settings
from avatar_engine.motion_library import browser_motion_library, load_motion_library
from avatar_engine.renderer_base import AvatarJob
from avatar_engine.viseme_mapping import convert_rhubarb_json_to_talkinghead


ROOT = Path(__file__).resolve().parents[1]


class TestBlenderCCRenderer(unittest.TestCase):
    def test_missing_asset_error_is_explicit(self) -> None:
        raw = json.loads((ROOT / "jobs" / "synthpost_anchor_v1_quality_gate.json").read_text())
        raw["avatar"]["asset_path"] = "assets/avatars/missing.glb"
        with self.assertRaises(FileNotFoundError) as context:
            BlenderCCAvatarRenderer().validate_job(AvatarJob(raw=raw))
        self.assertIn("missing.glb", str(context.exception))

    def test_modern_job_conversion_preserves_fixed_contract(self) -> None:
        raw = json.loads((ROOT / "jobs" / "synthpost_anchor_v1_quality_gate.json").read_text())
        raw["renderer"] = "blender_cc"
        job = AvatarJob(raw=raw)
        metadata_path = ROOT / job.avatar_metadata_path
        metadata = json.loads(metadata_path.read_text())
        rhubarb = json.loads((ROOT / job.viseme_path).read_text())
        visemes, vtimes, vdurations = convert_rhubarb_json_to_talkinghead(rhubarb)
        converted = build_blender_driver_job(
            root=ROOT,
            job=job,
            metadata_path=metadata_path,
            metadata=metadata,
            output_dir=ROOT / "assets" / "output" / "test",
            scene_path=ROOT / "assets" / "output" / "test" / "scene.blend",
            diagnostics_path=ROOT / "assets" / "output" / "test" / "diagnostics.json",
            visemes=visemes,
            vtimes=vtimes,
            vdurations=vdurations,
        )
        self.assertEqual(converted["camera"], raw["camera"])
        self.assertEqual(converted["duration_seconds"], 8.0)
        self.assertEqual(converted["performance"]["seed"], 48291)
        self.assertEqual(len(converted["precomputed_visemes"]["visemes"]), len(rhubarb["mouthCues"]))
        self.assertNotIn("avatar_template.blend", converted["scene_path"])
        self.assertEqual(converted["render_settings"]["profile"], "master")
        self.assertEqual(converted["render_settings"]["samples"], 64)

    def test_production_profile_uses_measured_32_sample_default(self) -> None:
        settings = resolve_blender_render_settings({}, quality_gate=False)
        self.assertEqual(settings["profile"], "production")
        self.assertEqual(settings["samples"], 32)
        self.assertEqual(settings["frame_format"], "JPEG")
        self.assertFalse(settings["retain_frames"])

    def test_transparent_presenter_pass_forces_png(self) -> None:
        settings = resolve_blender_render_settings(
            {
                "blender_profile": "production",
                "presenter_pass": {
                    "transparent": True,
                    "crop": [0.25, 0.0, 0.75, 1.0],
                },
            }
        )
        self.assertEqual(settings["frame_format"], "PNG")
        self.assertEqual(settings["presenter_pass"]["crop"], [0.25, 0.0, 0.75, 1.0])

    def test_sparse_render_windows_are_validated_and_preserved(self) -> None:
        settings = resolve_blender_render_settings(
            {
                "render_windows": [
                    {"source_start": 0.0, "source_end": 2.0},
                    {"source_start": 7.0, "source_end": 9.5},
                ]
            }
        )
        self.assertEqual(len(settings["render_windows"]), 2)
        self.assertEqual(settings["render_windows"][1]["source_start"], 7.0)

        with self.assertRaisesRegex(ValueError, "ordered and non-overlapping"):
            resolve_blender_render_settings(
                {
                    "render_windows": [
                        {"source_start": 4.0, "source_end": 6.0},
                        {"source_start": 5.0, "source_end": 7.0},
                    ]
                }
            )

    def test_motion_manifest_resolves_browser_clip_urls(self) -> None:
        metadata = json.loads(
            (ROOT / "assets" / "avatars" / "synthpost_anchor_v1" / "avatar.json").read_text()
        )
        library = load_motion_library(ROOT, metadata)
        self.assertIsNotNone(library)
        assert library is not None
        browser = browser_motion_library(library)
        assert browser is not None
        self.assertEqual(browser["default_idle"], "IDLE_Neutral")
        self.assertIn("EXPLAIN_Right_Small", browser["clips"])


class TestBlenderPerformanceImporter(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location(
            "performance_importer", ROOT / "blender" / "performance_importer.py"
        )
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_viseme_fade_is_deterministic(self) -> None:
        first = self.module.active_viseme(50, ["PP"], [0], [100])
        second = self.module.active_viseme(50, ["PP"], [0], [100])
        self.assertEqual(first, second)
        self.assertEqual(first, ("PP", 1.0))

    def test_fixed_blink_matches_control_period(self) -> None:
        self.assertGreater(self.module.blink_strength(3375), 0.0)
        self.assertEqual(self.module.blink_strength(1000), 0.0)

    def test_authored_blink_replaces_fixed_period(self) -> None:
        events = [{"time": 1.0, "duration": 0.2, "strength": 0.8}]
        self.assertAlmostEqual(self.module.scheduled_blink_strength(1.1, events), 0.8)
        self.assertEqual(self.module.scheduled_blink_strength(2.0, events), 0.0)

    def test_expression_preset_has_faded_authored_weight(self) -> None:
        events = [{"start": 0.0, "end": 2.0, "preset": "attentive", "weight": 0.5}]
        weights = self.module.expression_weights(1.0, events)
        self.assertGreater(weights["Brow_Raise_Inner_L"], 0.0)
        self.assertLessEqual(weights["Brow_Raise_Inner_L"], 0.09)
