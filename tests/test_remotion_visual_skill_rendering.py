from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
REMOTION_SRC = ROOT / "compositor" / "remotion_renderer" / "src"


class RemotionVisualSkillRenderingTests(unittest.TestCase):
    def test_visual_skill_renderer_declares_all_supported_skill_treatments(self) -> None:
        renderer = (REMOTION_SRC / "components" / "visualSkills" / "VisualSkillRenderer.tsx").read_text(
            encoding="utf-8"
        )
        for skill_type in [
            "map",
            "chart",
            "timeline",
            "document_callout",
            "quote_card",
            "data_callout",
            "context_card",
            "entity_card",
            "source_card",
            "broll_clip",
            "still_image",
        ]:
            self.assertIn(f"'{skill_type}'", renderer)
        self.assertIn("export const supportedVisualSkillTypes", renderer)
        self.assertIn("return {type, spec: objectValue(skill.spec), placeholder}", renderer)

    def test_active_templates_use_visual_skill_renderer(self) -> None:
        split_panel = (REMOTION_SRC / "components" / "NewsVisualPanel.tsx").read_text(encoding="utf-8")
        full_screen = (REMOTION_SRC / "templates" / "FullScreenNewsVisuals.tsx").read_text(encoding="utf-8")
        for source in [split_panel, full_screen]:
            self.assertIn("VisualSkillRenderer", source)
            self.assertNotIn("<VisualMediaLayer", source)

    def test_render_story_prefers_compositor_visuals_and_preserves_metadata(self) -> None:
        render_story = (REMOTION_SRC / "renderStory.ts").read_text(encoding="utf-8")
        self.assertRegex(
            render_story,
            re.compile(
                r"readCompositorVisualRecords\(manifest\).*manifest\.compositor_visuals.*manifest\.visuals",
                re.DOTALL,
            ),
        )
        self.assertIn("bridge.compositor_visuals_path", render_story)
        self.assertIn("payload.visuals", render_story)
        for field in [
            "candidateId",
            "planId",
            "sectionId",
            "sectionType",
            "visualRole",
            "sourceUrl",
            "sourceDomain",
            "provider",
            "license",
            "attributionText",
            "rightsCategory",
            "manualReviewFlag",
            "fallbackStatus",
            "warnings",
            "visualSkillType",
            "visualSkill",
            "skillPlaceholder",
            "renderSafetyStatus",
        ]:
            self.assertIn(field, render_story)

    def test_renderer_exposes_attribution_first_party_and_review_only_behavior(self) -> None:
        renderer = (REMOTION_SRC / "components" / "visualSkills" / "VisualSkillRenderer.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("visualAttributionText", renderer)
        self.assertIn("SynthPost generated visual", renderer)
        self.assertIn("renderSafetyStatus !== 'review_only'", renderer)
        self.assertIn("Review Only", renderer)
        self.assertIn("floating?: boolean", renderer)
        self.assertIn("renderSafetyStatus", renderer)
        self.assertIn("context_card", renderer)

    def test_renderer_has_layout_safety_for_long_text(self) -> None:
        renderer = (REMOTION_SRC / "components" / "visualSkills" / "VisualSkillRenderer.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("safeLine", renderer)
        self.assertIn("clampStyle", renderer)
        self.assertIn("WebkitLineClamp", renderer)
        self.assertIn("overflowWrap: 'anywhere'", renderer)
        self.assertIn("Verified location context", renderer)


if __name__ == "__main__":
    unittest.main()
