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
            self.assertIn(f'"{skill_type}"', renderer)
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
        self.assertIn(
            "visualSkillType: visualRef.visual_skill_type ?? visualRef.skill_type",
            render_story,
        )
        self.assertIn("visualSkill: visualRef.visual_skill", render_story)
        self.assertIn("skillPlaceholder: visualRef.skill_placeholder", render_story)

    def test_timeline_story_uses_retained_template_surfaces(self) -> None:
        timeline_story = (REMOTION_SRC / "templates" / "TimelineStory.tsx").read_text(
            encoding="utf-8"
        )
        for token in [
            "AnchorPanel",
            "NewsVisualPanel",
            "LowerThird",
            "RetainedSplitSegment",
            "RetainedFullScreenVisualSegment",
            "RetainedFullScreenAnchorSegment",
            "timelineHeadlineItems",
        ]:
            self.assertIn(token, timeline_story)
        self.assertIn('template === "split_anchor_visual"', timeline_story)
        self.assertIn('template === "fullscreen_news_visual"', timeline_story)
        self.assertIn(
            'template === "fullscreen_anchor" || template === "fallback_anchor"',
            timeline_story,
        )

    def test_timeline_story_uses_sequence_relative_frames(self) -> None:
        timeline_story = (REMOTION_SRC / "templates" / "TimelineStory.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("const localFrame = frame;", timeline_story)
        self.assertNotIn("frame - Math.round(segment.start * fps)", timeline_story)
        self.assertIn("const endFrame = Math.round(segment.end * fps);", timeline_story)
        self.assertIn(
            "durationInFrames={Math.max(1, endFrame - startFrame)}", timeline_story
        )

    def test_retained_templates_scale_1080p_design_canvas_to_preview_profile(
        self,
    ) -> None:
        design_canvas = (REMOTION_SRC / "components" / "DesignCanvas.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("width / layout.width", design_canvas)
        self.assertIn("height / layout.height", design_canvas)
        for template in [
            "TimelineStory.tsx",
            "SplitMain.tsx",
            "FullScreenAnchor.tsx",
            "FullScreenNewsVisuals.tsx",
        ]:
            source = (REMOTION_SRC / "templates" / template).read_text(encoding="utf-8")
            self.assertIn("DesignCanvas", source)

    def test_lower_third_matches_original_wordmark_and_static_bug_text(self) -> None:
        logo_bug = (REMOTION_SRC / "components" / "LogoBug.tsx").read_text(
            encoding="utf-8"
        )
        lower_third = (REMOTION_SRC / "components" / "LowerThird.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("Synthpost", logo_bug)
        self.assertNotIn("<Img", logo_bug)
        self.assertIn("SYNTHPOST", lower_third)
        self.assertNotIn("sourceMeta", lower_third)

    def test_timeline_lower_thirds_use_intra_segment_spoken_cues(self) -> None:
        timeline_story = (
            REMOTION_SRC / "templates" / "TimelineStory.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("segment.overlays.data?.headline_cues", timeline_story)
        self.assertIn("headlineItems={timelineHeadlineItems(segments)}", timeline_story)
        self.assertIn('<DesignCanvas background="transparent">', timeline_story)
        self.assertEqual(timeline_story.count("<LowerThird"), 1)

    def test_news_visuals_use_original_source_label_overlay_without_tiny_duplicate_attribution(
        self,
    ) -> None:
        news_panel = (REMOTION_SRC / "components" / "NewsVisualPanel.tsx").read_text(
            encoding="utf-8"
        )
        timeline_story = (REMOTION_SRC / "templates" / "TimelineStory.tsx").read_text(
            encoding="utf-8"
        )
        fullscreen = (
            REMOTION_SRC / "templates" / "FullScreenNewsVisuals.tsx"
        ).read_text(encoding="utf-8")
        visual_skills = (
            REMOTION_SRC / "components" / "visualSkills" / "VisualSkillRenderer.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("SourceLabel", news_panel)
        self.assertIn("SourceLabel", fullscreen)
        self.assertIn("<SourceLabel", timeline_story)
        relative_visual = timeline_story.split("const relativeSegmentVisual", 1)[
            1
        ].split("const segmentHeadlineItems", 1)[0]
        self.assertNotIn("segment.overlays.attribution", relative_visual)
        self.assertNotIn("<AttributionStrip visual={visual} />", visual_skills)
        self.assertNotIn("const AttributionStrip", visual_skills)

    def test_approved_video_trim_reaches_remotion_video_layer(self) -> None:
        render_story = (REMOTION_SRC / "renderStory.ts").read_text(encoding="utf-8")
        visual_layer = (REMOTION_SRC / "components" / "VisualMediaLayer.tsx").read_text(
            encoding="utf-8"
        )
        types = (REMOTION_SRC / "types.ts").read_text(encoding="utf-8")
        self.assertIn(
            "trimStart: Number.isFinite(trimStart) ? trimStart : undefined",
            render_story,
        )
        self.assertIn(
            "trimEnd: Number.isFinite(trimEnd) ? trimEnd : undefined", render_story
        )
        self.assertIn("trimStart?: number", types)
        self.assertIn("trimEnd?: number", types)
        self.assertIn("startFrom={startFrom || undefined}", visual_layer)
        self.assertIn("endAt={endAt}", visual_layer)

    def test_renderer_has_layout_safety_for_long_text(self) -> None:
        renderer = (
            REMOTION_SRC / "components" / "visualSkills" / "VisualSkillRenderer.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("safeLine", renderer)
        self.assertIn("clampStyle", renderer)
        self.assertIn("WebkitLineClamp", renderer)
        self.assertIn('overflowWrap: "anywhere"', renderer)


if __name__ == "__main__":
    unittest.main()
