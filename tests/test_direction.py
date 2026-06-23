from __future__ import annotations

import json
import shutil
import unittest

from pipeline.direction.avatar import camera_cuts_for, camera_for_template, native_segment_export, template_requires_avatar
from pipeline.storage import PROJECT_ROOT


class DirectionTemplateTests(unittest.TestCase):
    def tearDown(self) -> None:
        shutil.rmtree(PROJECT_ROOT / "episodes" / "ep_unit_direction", ignore_errors=True)

    def test_full_screen_anchor_uses_landscape_intro(self) -> None:
        self.assertEqual(camera_for_template("full_screen_anchor"), "landscape_intro")
        self.assertEqual(camera_for_template("news-full-screen-anchor"), "landscape_intro")
        self.assertEqual(camera_cuts_for(20, "opening_anchor")[0]["camera"], "landscape_intro")

    def test_split_main_uses_portrait_main(self) -> None:
        self.assertEqual(camera_for_template("split_main"), "portrait_main")
        self.assertEqual(camera_cuts_for(20, "split_main")[0]["camera"], "portrait_main")

    def test_full_screen_news_visuals_skips_avatar(self) -> None:
        self.assertFalse(template_requires_avatar("FullScreenNewsVisuals"))
        self.assertFalse(template_requires_avatar("full-screen-news-visuals"))
        self.assertTrue(template_requires_avatar("split_main"))

    def test_native_segment_export_reads_avatar_engine_manifest(self) -> None:
        anchor_path = PROJECT_ROOT / "episodes" / "ep_unit_direction" / "stories" / "story_001" / "anchor.mp4"
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
        self.assertEqual(export["path"], segment_path)
        self.assertEqual(export["export_mode"], "native_segments")


if __name__ == "__main__":
    unittest.main()
