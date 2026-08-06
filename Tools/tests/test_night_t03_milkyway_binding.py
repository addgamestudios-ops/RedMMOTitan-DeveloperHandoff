import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "Source" / "RedMMO" / "RedSpaceScenery.h"
SOURCE = ROOT / "Source" / "RedMMO" / "RedSpaceScenery.cpp"


class NightT03MilkyWayBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = HEADER.read_text(encoding="utf-8-sig")
        cls.source = SOURCE.read_text(encoding="utf-8-sig")

    def test_has_current_world_direction_material_and_explicit_mesh_inputs(self):
        self.assertIn("NightT03MilkyWayMaterial", self.header)
        self.assertIn("NightT03BasicSphereMesh", self.header)
        self.assertIn("NightT03SkySphereMesh", self.header)
        self.assertIn(
            "/Game/RedMMO/Environment/Tests/"
            "M_RedStar_T03MilkyWayWorldDir.M_RedStar_T03MilkyWayWorldDir",
            self.source,
        )
        self.assertNotIn(
            "/Game/RedMMO/Environment/Tests/"
            "M_RedStar_T03MilkyWay.M_RedStar_T03MilkyWay",
            self.source,
        )
        self.assertIn("/Engine/BasicShapes/Sphere.Sphere", self.source)
        self.assertIn(
            "/Engine/EngineSky/SM_SkySphere.SM_SkySphere", self.source
        )

    def test_selection_is_scoped_to_night_t03(self):
        request_match = re.search(
            r"const bool bRequestNightT03MilkyWaySky\s*=\s*(.*?);",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(request_match)
        request_expression = " ".join(request_match.group(1).split())
        self.assertEqual(
            request_expression,
            "bNightStarTuningTest && NightT03MilkyWayMaterial != nullptr "
            "&& NightT03BasicSphereMesh != nullptr",
        )

        selection_block = self.source.split(
            "if (bRequestNightT03MilkyWaySky)", 1
        )[1].split("UMaterialInterface* StarDomeParent", 1)[0]
        self.assertIn(
            "AnalyticStarDome->SetStaticMesh(NightT03BasicSphereMesh.Get())",
            selection_block,
        )
        self.assertNotIn("NightT03SkySphereMesh.Get()", selection_block)

        self.assertIn(
            "bAnalyticStarDomeReady = bUsingNightT03MilkyWaySky", self.source
        )
        self.assertIn(
            "AnalyticStarDome->GetStaticMesh() == NightT03BasicSphereMesh.Get()",
            self.source,
        )

    def test_runtime_controls_match_material_parameters(self):
        self.assertIn('TEXT("Visibility"), StarVisibility', self.source)
        self.assertIn(
            '(bUsingNightT03MilkyWaySky ? 12.f : 64.f) * StarExposureCompensation',
            self.source,
        )
        self.assertIn('TEXT("milkyway-dome")', self.source)

    def test_sky_radius_is_derived_from_mesh_bounds(self):
        self.assertRegex(
            self.source,
            r"constexpr double TargetStarDomeRadiusCm\s*=\s*10000000\.0;",
        )
        self.assertIn(
            "NightT03BasicSphereMesh->GetBounds().SphereRadius", self.source
        )
        self.assertIn(
            "TargetStarDomeRadiusCm / SourceStarDomeRadiusCm", self.source
        )


if __name__ == "__main__":
    unittest.main()
