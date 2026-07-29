from __future__ import annotations

import json
import unittest
from pathlib import Path

from pipeline.models import TimelinePlan


ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "videos" / "meridian-private-credit-prototype" / "story.json"


class MeridianPrivateCreditPrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(STORY.read_text(encoding="utf-8"))
        cls.timeline = TimelinePlan.model_validate(
            cls.manifest["approved_timeline"]
        )

    def test_episode_exercises_corrected_meridian_template_library(self) -> None:
        templates = {
            segment.template.template_id for segment in self.timeline.segments
        }
        self.assertEqual(
            templates,
            {
                "meridian_clipping_board",
                "meridian_data_board",
                "meridian_narrator_evidence",
                "meridian_mechanism",
                "meridian_document_highlight",
                "meridian_narrator_tokens",
                "meridian_footage_montage",
                "meridian_sparse_thesis",
            },
        )

    def test_presenter_is_sparse_and_uses_opposite_side_layouts(self) -> None:
        visible = [
            segment for segment in self.timeline.segments if segment.anchor.visible
        ]
        self.assertEqual(len(visible), 2)
        for segment in visible:
            cue = segment.overlays.data["meridian_presenter"]
            self.assertEqual(cue["placement"], "lower_right")
            self.assertLessEqual(cue["width"], 1210)

    def test_social_clipping_has_bounded_structured_fields(self) -> None:
        social = next(
            segment
            for segment in self.timeline.segments
            if segment.overlays.data.get("clipping_kind") == "social"
        )
        data = social.overlays.data
        self.assertLessEqual(len(data["post"]), 175)
        self.assertLessEqual(len(data["context"]), 100)
        self.assertTrue(data["display_name"])
        self.assertTrue(data["handle"].startswith("@"))

    def test_voice_identity_remains_the_meridian_profile(self) -> None:
        narration = self.manifest["narration"]
        self.assertEqual(narration["provider"], "dots_tts")
        self.assertEqual(narration["voice_id"], "meridian_narrator")
        self.assertEqual(narration["model"], "dots.tts-soar-mlx-int4")


if __name__ == "__main__":
    unittest.main()
