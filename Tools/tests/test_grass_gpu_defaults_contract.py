"""Static contracts for conservative grass GPU defaults.

These tests intentionally prove only source configuration. Runtime frame-time and
appearance still require a duplicate grass-enabled map and matched real-GPU captures.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
FOLIAGE_CPP = ROOT / "Source" / "RedMMO" / "RedFoliageField.cpp"
FOLIAGE_HEADER = ROOT / "Source" / "RedMMO" / "RedFoliageField.h"
GAME_MODE_HEADER = ROOT / "Source" / "RedMMO" / "RedGameMode.h"
PLANET_CPP = (
    ROOT
    / "Plugins"
    / "PlanetGenPinned_1_4_0_RedMMO"
    / "Source"
    / "PlanetGen"
    / "Private"
    / "PlanetGen"
    / "CLMPlanet.cpp"
)
PLANET_GRASS_HEADER = (
    ROOT
    / "Plugins"
    / "PlanetGenPinned_1_4_0_RedMMO"
    / "Source"
    / "PlanetGen"
    / "Public"
    / "Shared"
    / "PlanetGenGrassAsset.h"
)


class GrassGpuDefaultsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.foliage_cpp = FOLIAGE_CPP.read_text(encoding="utf-8")
        cls.foliage_header = FOLIAGE_HEADER.read_text(encoding="utf-8")
        cls.game_mode_header = GAME_MODE_HEADER.read_text(encoding="utf-8")
        cls.planet_cpp = PLANET_CPP.read_text(encoding="utf-8")
        cls.planet_grass_header = PLANET_GRASS_HEADER.read_text(encoding="utf-8")

    def test_dense_layers_disable_shadow_and_distance_field_cost(self) -> None:
        dense_expression = re.search(
            r"const bool bDenseGroundCover\s*=\s*"
            r"Layer == EScatterLayer::Grass\s*"
            r"\|\|\s*Layer == EScatterLayer::AlienAccent\s*"
            r"\|\|\s*Layer == EScatterLayer::SnowAccent\s*;",
            self.foliage_cpp,
        )
        self.assertIsNotNone(dense_expression)
        self.assertIn("H->SetCastShadow(!bDenseGroundCover);", self.foliage_cpp)
        self.assertIn(
            "H->bAffectDistanceFieldLighting = !bDenseGroundCover;",
            self.foliage_cpp,
        )

    def test_rocks_and_cliffs_are_not_classified_as_dense_ground_cover(self) -> None:
        expression = re.search(
            r"const bool bDenseGroundCover\s*=(.*?);",
            self.foliage_cpp,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(expression)
        self.assertNotIn("DesertRock", expression.group(1))
        self.assertNotIn("DesertCliff", expression.group(1))

    def test_existing_collision_aware_cull_ranges_are_preserved(self) -> None:
        self.assertIn(
            "H->SetCullDistances(0, bEnableCollision ? 90000 : 60000);",
            self.foliage_cpp,
        )

    def test_current_surface_dressing_remains_opt_in_and_empty_by_default(self) -> None:
        for field in (
            "GrassCount",
            "FlowerCount",
            "RockCount",
            "CliffCount",
            "SnowAccentCount",
        ):
            self.assertRegex(self.foliage_header, rf"int32 {field}\s*=\s*0\s*;")
        self.assertRegex(
            self.foliage_header,
            r"bool bSuppressAllProceduralDressing\s*=\s*true\s*;",
        )
        self.assertRegex(
            self.game_mode_header,
            r"bool bSuppressProceduralSurfaceDressing\s*=\s*true\s*;",
        )

    def test_planetgen_grass_keeps_existing_cheap_defaults(self) -> None:
        self.assertIn("bEnableGrass = false;", self.planet_cpp)
        self.assertRegex(
            self.planet_grass_header,
            r"bool bEnableCollision\s*=\s*false\s*;",
        )
        self.assertRegex(
            self.planet_grass_header,
            r"bool bCastShadow\s*=\s*false\s*;",
        )


if __name__ == "__main__":
    unittest.main()
