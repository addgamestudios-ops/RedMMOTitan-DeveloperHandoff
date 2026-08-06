import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "Source" / "RedMMO" / "WorldAuthoring" / "RedStylizedPlanetPresentationAdapter.h"
SOURCE = ROOT / "Source" / "RedMMO" / "WorldAuthoring" / "RedStylizedPlanetPresentationAdapter.cpp"
CPP_TESTS = (
    ROOT
    / "Source"
    / "RedMMO"
    / "WorldAuthoring"
    / "RedStylizedPlanetPresentationAdapterTests.cpp"
)


class StylizedPlanetPresentationAdapterSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.cpp_tests = CPP_TESTS.read_text(encoding="utf-8")

    def test_active_project_uses_pinned_planetgen_not_ppg(self):
        project = json.loads((ROOT / "Titan.uproject").read_text(encoding="utf-8"))
        plugins = {entry["Name"]: entry.get("Enabled", False) for entry in project["Plugins"]}
        self.assertTrue(plugins.get("PlanetGen"))
        self.assertFalse(plugins.get("PPG", False))

        descriptor = json.loads(
            (
                ROOT
                / "Plugins"
                / "PlanetGenPinned_1_4_0_RedMMO"
                / "PlanetGen.uplugin"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(descriptor["VersionName"], "1.4.0-redmmo-50km-phase1")
        self.assertEqual(descriptor["EngineVersion"], "5.8.0")

    def test_adapter_is_query_only_and_project_owned(self):
        self.assertIn("EvaluateFromSignals", self.header)
        self.assertIn("EvaluateAtWorldPoint", self.header)
        self.assertIn("URedWorldAssetPalette", self.header)
        self.assertIn("URedPlanetHubReservationRegistry", self.source)

        forbidden_mutations = (
            "PreviewPlanet(",
            "ClearPlanet(",
            "InitializeTerrain(",
            "SetMaterial(",
            "BuildWaterSphere(",
            "bEnableWater =",
            "SeaLevel =",
            "GravityRadius =",
            "DOREPLIFETIME",
            "Modify(",
        )
        for token in forbidden_mutations:
            self.assertNotIn(token, self.source)

    def test_authenticated_hub_features_are_queried(self):
        self.assertIn('TEXT("Foliage")', self.source)
        self.assertIn('TEXT("Rock")', self.source)
        self.assertIn('TEXT("Water")', self.source)
        self.assertIn("ProceduralWaterDecorationWeight", self.header)
        self.assertIn("global water material remains selected independently", self.header)

    def test_deferred_automation_contract_covers_mapping_and_fail_closed_blend(self):
        self.assertIn("StylizedPlanetPresentation.Mapping", self.cpp_tests)
        self.assertIn("StylizedPlanetPresentation.HubBlend", self.cpp_tests)
        self.assertIn("Invalid protection fails closed", self.cpp_tests)
        self.assertIn("Only approved foliage hook is exposed", self.cpp_tests)


if __name__ == "__main__":
    unittest.main()
