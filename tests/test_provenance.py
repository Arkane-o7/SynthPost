from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pipeline.manifest_summary import summarize_episode
from pipeline.provenance import artifact_record, record_episode_artifact
from pipeline.render_profiles import apply_manifest_runtime, resolve_profile
from pipeline.storage import PROJECT_ROOT, write_manifest


class ProvenanceTests(unittest.TestCase):
    def tearDown(self) -> None:
        shutil.rmtree(PROJECT_ROOT / "episodes" / "ep_unit_provenance", ignore_errors=True)

    def test_render_profile_and_test_mode_are_recorded(self) -> None:
        manifest = {"story_id": "story_001", "episode_id": "ep_test"}

        apply_manifest_runtime(manifest, render_profile="preview", test_mode=True)

        self.assertEqual(manifest["render_profile"], "preview")
        self.assertTrue(manifest["test_mode"])
        self.assertEqual(manifest["runtime"]["mode"], "TEST_MODE")
        self.assertIn("TEST_MODE", manifest["labels"])
        self.assertEqual(manifest["runtime"]["render_profile_settings"]["width"], 1280)

    def test_episode_final_mp4_provenance_is_written(self) -> None:
        episode_id = "ep_unit_provenance"
        final_path = PROJECT_ROOT / "episodes" / episode_id / "final.mp4"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(b"not a real video but hashable")

        record = artifact_record(
            path=final_path,
            stage="assembly",
            input_paths=[],
            provider="ffmpeg",
            fresh=True,
            test_mode=False,
            render_profile="production",
            command=["python3", "assembly/stitch_episode.py", episode_id],
        )
        manifest = record_episode_artifact(
            episode_id,
            "final_video",
            record,
            runtime={"render_profile": "production", "test_mode": False, "mode": "production"},
        )

        final = manifest["provenance"]["artifacts"]["final_video"]
        self.assertEqual(final["path"], f"episodes/{episode_id}/final.mp4")
        self.assertEqual(final["stage"], "assembly")
        self.assertEqual(final["render_profile"], "production")
        self.assertFalse(final["test_mode"])
        self.assertIn("sha256", final)

    def test_skipped_avatar_artifact_is_not_reported_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            episode = Path(temp_dir) / "ep_skipped_avatar"
            story_path = episode / "stories" / "story_001" / "story.json"
            story_path.parent.mkdir(parents=True)
            manifest = {
                "episode_id": "ep_skipped_avatar",
                "story_id": "story_001",
                "raw": {"headline_source": "Sparse Story", "category": "news"},
                "script": {"headline": "Sparse Story"},
                "direction": {"voice": {"engine": "kokoro"}},
                "thumbnail": {},
                "runtime": {"render_profile": "preview", "test_mode": True},
                "provenance": {
                    "artifacts": {
                        "avatar_anchor": {
                            "path": "missing-anchor.mp4",
                            "stage": "avatar",
                            "fresh": False,
                            "reused": False,
                            "skipped": True,
                            "test_mode": True,
                            "render_profile": "preview",
                        }
                    }
                },
            }
            write_manifest(story_path, manifest)

            summary = summarize_episode(episode)

        self.assertEqual(summary["avatar"]["status"], "skipped")
        self.assertEqual(summary["mode"], "TEST_MODE")
        self.assertIn("TEST_MODE artifact", " ".join(summary["warnings"]))

    def test_manifest_summary_handles_missing_optional_fields_safely(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            episode = Path(temp_dir) / "ep_sparse"
            story_path = episode / "stories" / "story_001" / "story.json"
            story_path.parent.mkdir(parents=True)
            story_path.write_text(
                json.dumps(
                    {
                        "episode_id": "ep_sparse",
                        "story_id": "story_001",
                        "raw": {"headline_source": "Sparse Story"},
                        "script": {},
                        "direction": {},
                        "visuals": [],
                        "points": [],
                        "composition": {},
                    }
                ),
                encoding="utf-8",
            )

            summary = summarize_episode(episode)

        self.assertEqual(summary["episode_id"], "ep_sparse")
        self.assertEqual(summary["headline"], "Sparse Story")
        self.assertEqual(summary["llm"]["provider"], "unknown")
        self.assertTrue(summary["warnings"])

    def test_unknown_render_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_profile("cinema")


if __name__ == "__main__":
    unittest.main()
