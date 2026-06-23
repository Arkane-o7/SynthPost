from __future__ import annotations

import unittest

from pipeline.direction.avatar import camera_cuts_for, camera_for_template, template_requires_avatar


class DirectionTemplateTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
