from __future__ import annotations

import json
import unittest
from pathlib import Path

from pipeline.models import TimelinePlan
from pipeline.timeline.templates import TEMPLATE_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "videos" / "meridian-open-models-prototype" / "story.json"
REMOTION = ROOT / "compositor" / "remotion_renderer" / "src"


class MeridianPersistentSceneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(PROTOTYPE.read_text(encoding="utf-8"))
        self.timeline = TimelinePlan.model_validate(
            self.manifest["approved_timeline"]
        )

    def test_prototype_uses_nine_idea_scenes_for_ten_narration_segments(
        self,
    ) -> None:
        scene_ids = [segment.scene_id for segment in self.timeline.segments]
        self.assertEqual(len(self.timeline.segments), 10)
        self.assertEqual(len(set(scene_ids)), 9)
        self.assertEqual(scene_ids.count("narrator_reaction"), 2)

    def test_pose_changes_inside_one_persistent_reaction_scene(self) -> None:
        reaction = [
            segment
            for segment in self.timeline.segments
            if segment.scene_id == "narrator_reaction"
        ]
        self.assertEqual([segment.segment_id for segment in reaction], ["seg_003a", "seg_003b"])
        pose_events = [
            event
            for segment in reaction
            for event in segment.internal_events
            if event.get("type") == "change_pose"
        ]
        self.assertEqual(
            [event["payload"]["pose"] for event in pose_events],
            ["arms_crossed", "shrug"],
        )

    def test_narrator_is_sparse(self) -> None:
        visible_seconds = sum(
            segment.duration
            for segment in self.timeline.segments
            if segment.anchor.visible
        )
        self.assertLess(visible_seconds / 78, 0.25)
        self.assertAlmostEqual(visible_seconds, 17, places=3)

    def test_prototype_templates_are_meridian_scoped_and_registered(self) -> None:
        expected = {
            "meridian_torn_headline",
            "meridian_evidence_stack",
            "meridian_narrator_evidence",
            "meridian_framed_chart",
            "meridian_mechanism",
            "meridian_document_highlight",
            "meridian_narrator_tokens",
            "meridian_footage_montage",
            "meridian_sparse_thesis",
        }
        self.assertTrue(expected.issubset(TEMPLATE_REGISTRY))
        self.assertTrue(
            all(
                segment.template.template_id.startswith("meridian_")
                for segment in self.timeline.segments
            )
        )

    def test_remotion_groups_explicit_scene_ids_before_legacy_heuristics(
        self,
    ) -> None:
        story = (REMOTION / "templates" / "MeridianStory.tsx").read_text(
            encoding="utf-8"
        )
        types = (REMOTION / "types.ts").read_text(encoding="utf-8")
        self.assertIn("previous.sceneId === next.sceneId", story)
        self.assertIn("cueForScene", story)
        self.assertIn("sceneId?: string", types)
        self.assertIn("internalEvents?: MeridianInternalEvent[]", types)

    def test_editorial_primitives_keep_pins_and_marks_outside_paper_clips(
        self,
    ) -> None:
        primitives = (
            REMOTION
            / "templates"
            / "meridian"
            / "MeridianEditorialPrimitives.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("export const BoardPin", primitives)
        self.assertIn("export const CorkBoard", primitives)
        self.assertIn("export const TornPaper", primitives)
        self.assertIn("export const MarkerStroke", primitives)
        self.assertIn("export const MarkerHighlight", primitives)
        self.assertIn("export const ThreadConnector", primitives)
        self.assertIn("overflow: \"visible\"", primitives)
        self.assertIn("<BoardPin", primitives)
        self.assertIn("y = 16", primitives)
        self.assertIn("translate(-50%, -50%)", primitives)

    def test_presenter_layout_is_resolved_before_the_scene_is_drawn(self) -> None:
        story = (REMOTION / "templates" / "MeridianStory.tsx").read_text(
            encoding="utf-8"
        )
        scene = (
            REMOTION / "templates" / "meridian" / "MeridianPrototypeScene.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("presenterCue={presenterCue}", story)
        self.assertIn("isRightPlacement(presenterCue?.placement)", scene)
        self.assertIn("presenterVisible", scene)
        self.assertIn("position.left + position.width * position.pinX", scene)
        self.assertIn("y: position.top + position.pinY", scene)
        self.assertIn("end={{ x: hub.x, y: hub.y - 68 }}", scene)
        self.assertIn("const hub = presenterRight", scene)

    def test_clipping_board_uses_structured_headline_and_social_layouts(self) -> None:
        scene = (
            REMOTION / "templates" / "meridian" / "MeridianScene.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn('kind === "social"', scene)
        self.assertIn('dataText(segment, "display_name"', scene)
        self.assertIn('"headline",', scene)
        self.assertIn("<TornPaper", scene)
        self.assertIn("<MarkerHighlight", scene)
        self.assertIn("meridianClippingFontSize", scene)
        self.assertIn("WebkitLineClamp", scene)


if __name__ == "__main__":
    unittest.main()
