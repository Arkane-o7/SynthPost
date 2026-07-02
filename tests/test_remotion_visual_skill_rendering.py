from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTION_SRC = ROOT / "compositor" / "remotion_renderer" / "src"


class RemotionRenderingSurfaceTests(unittest.TestCase):
    def test_visual_skill_renderer_remains_available_for_retained_templates(
        self,
    ) -> None:
        renderer = (
            REMOTION_SRC / "components" / "visualSkills" / "VisualSkillRenderer.tsx"
        ).read_text(encoding="utf-8")
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

    def test_active_templates_use_visual_skill_renderer(self) -> None:
        split_panel = (REMOTION_SRC / "components" / "NewsVisualPanel.tsx").read_text(
            encoding="utf-8"
        )
        full_screen = (
            REMOTION_SRC / "templates" / "FullScreenNewsVisuals.tsx"
        ).read_text(encoding="utf-8")
        for source in [split_panel, full_screen]:
            self.assertIn("VisualSkillRenderer", source)

    def test_render_story_uses_manifest_visuals_and_approved_timeline_only(
        self,
    ) -> None:
        render_story = (REMOTION_SRC / "renderStory.ts").read_text(encoding="utf-8")
        self.assertIn(
            "manifest.approved_timeline ?? manifest.timeline_plan", render_story
        )
        self.assertIn("manifest.compositor_visuals", render_story)
        self.assertIn("manifest.visuals", render_story)
        self.assertNotIn("visual_compositor_bridge", render_story)
        self.assertNotIn("compositor_visuals_path", render_story)
        self.assertIn("manifest_visuals", render_story)
        self.assertIn("timeline-story", render_story)

    def test_renderer_has_layout_safety_for_long_text(self) -> None:
        renderer = (
            REMOTION_SRC / "components" / "visualSkills" / "VisualSkillRenderer.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("safeLine", renderer)
        self.assertIn("clampStyle", renderer)
        self.assertIn("WebkitLineClamp", renderer)
        self.assertIn("overflowWrap: 'anywhere'", renderer)


if __name__ == "__main__":
    unittest.main()
