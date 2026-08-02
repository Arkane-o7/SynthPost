from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATERIALS = (
    ROOT
    / "compositor"
    / "remotion_renderer"
    / "public"
    / "meridian"
    / "materials"
)
PRIMITIVES = (
    ROOT
    / "compositor"
    / "remotion_renderer"
    / "src"
    / "templates"
    / "meridian"
    / "MeridianEditorialPrimitives.tsx"
)


class MeridianMaterialSystemTests(unittest.TestCase):
    def test_original_material_assets_are_present_and_nontrivial(self) -> None:
        for name in (
            "editorial-desk-wide.webp",
            "paper-crumpled-ivory.webp",
            "cork-natural.webp",
        ):
            asset = MATERIALS / name
            self.assertTrue(asset.is_file(), name)
            self.assertGreater(asset.stat().st_size, 100_000, name)

    def test_material_surfaces_are_remotion_driven(self) -> None:
        source = PRIMITIVES.read_text(encoding="utf-8")
        self.assertIn("export const MeridianDeskSurface", source)
        self.assertIn("export const CrumpledPaperTexture", source)
        self.assertIn("export const CorkBoard", source)
        self.assertIn("useCurrentFrame", source)


if __name__ == "__main__":
    unittest.main()
