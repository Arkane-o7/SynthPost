from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from avatar_engine.quality_gate import (
    QUALITY_GATE_VERSION,
    canonical_job_sha256,
    validate_quality_gate_job,
)


ROOT = Path(__file__).resolve().parents[1]
JOB_PATH = ROOT / "jobs" / "synthpost_anchor_v1_quality_gate.json"


class TestAvatarQualityGate(unittest.TestCase):
    def test_committed_job_is_valid_and_deterministic(self) -> None:
        raw = json.loads(JOB_PATH.read_text(encoding="utf-8"))
        self.assertEqual(validate_quality_gate_job(raw), [])
        self.assertEqual(raw["quality_gate"]["version"], QUALITY_GATE_VERSION)
        self.assertEqual(canonical_job_sha256(raw), canonical_job_sha256(dict(raw)))

    def test_missing_blink_is_rejected(self) -> None:
        raw = json.loads(JOB_PATH.read_text(encoding="utf-8"))
        raw["performance"]["blink_events"] = []
        self.assertTrue(any("exactly one" in error for error in validate_quality_gate_job(raw)))

    def test_duration_outside_contract_is_rejected(self) -> None:
        raw = json.loads(JOB_PATH.read_text(encoding="utf-8"))
        raw["camera"]["duration_seconds"] = 6
        self.assertTrue(any("between 8 and 12" in error for error in validate_quality_gate_job(raw)))

    def test_candidate_job_keeps_source_immutable(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "run_avatar_quality_gate", ROOT / "scripts" / "run_avatar_quality_gate.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source = json.loads(JOB_PATH.read_text(encoding="utf-8"))
        original = json.loads(json.dumps(source))
        candidate = module.build_candidate_job(
            source,
            candidate="candidate_b_threejs",
            run_id="run_2",
            renderer="rocketbox",
            quality_profile="studio_v2",
            tone_mapping="agx",
        )
        self.assertEqual(source, original)
        self.assertEqual(candidate["render"]["quality_profile"], "studio_v2")
        self.assertEqual(candidate["render"]["tone_mapping"], "agx")
        self.assertIn("candidate_b_threejs/run_2", candidate["render"]["output_path"])
        self.assertEqual(
            candidate["quality_gate"]["source_job_sha256"], canonical_job_sha256(source)
        )


class TestAvatarInspector(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location(
            "inspect_avatar_asset", ROOT / "scripts" / "inspect_avatar_asset.py"
        )
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_bad_glb_fails_without_modifying_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.glb"
            path.write_bytes(b"not a glb")
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                self.module.load_glb_json(path)
            self.assertEqual(path.read_bytes(), before)

    def test_live_avatar_reports_expected_dense_face_rig(self) -> None:
        glb = ROOT / "assets" / "avatars" / "synthpost_anchor_v1" / "anchor.glb"
        textures = glb.parent / "textures"
        if not glb.exists():
            self.skipTest("ignored local avatar asset is unavailable")
        report = self.module.inspect_avatar(glb, textures)
        self.assertGreaterEqual(report["counts"]["unique_morph_targets"], 100)
        self.assertGreaterEqual(report["counts"]["bones"], 90)
        self.assertGreater(report["source_textures"]["missing_from_glb_count"], 0)
