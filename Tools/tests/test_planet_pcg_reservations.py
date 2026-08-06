import json
import math
import tempfile
import unittest
from pathlib import Path

from Tools import generate_planet_pcg_reservations as generator
from Tools.planet_patch_compositor import PATCH_COUNT, region_hash


ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "SourceArt" / "Planet50Km" / "AuthoringPatches" / "RED_PatchProfile.json"
RASTERS = ROOT / "SourceArt" / "Planet50Km" / "AuthoringPatches" / "RED_PatchRasters.json"
PERSISTED = ROOT / "docs" / "PLANET_50KM_PCG_RESERVATIONS.json"
COMPONENT_CPP = (
    ROOT
    / "Source"
    / "RedMMO"
    / "WorldAuthoring"
    / "RedManualPlacementProtectionComponent.cpp"
)
COMPONENT_HEADER = COMPONENT_CPP.with_suffix(".h")


class PlanetPcgReservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = generator.build_document(PROFILE, RASTERS)
        cls.profile = json.loads(PROFILE.read_text(encoding="utf-8"))

    def test_exactly_27_unique_profile_aligned_reservations(self):
        reservations = self.document["reservations"]
        self.assertEqual(len(reservations), PATCH_COUNT)
        self.assertEqual(
            [reservation["region_index"] for reservation in reservations],
            list(range(PATCH_COUNT)),
        )
        self.assertEqual(
            len({reservation["reservation_id"] for reservation in reservations}),
            PATCH_COUNT,
        )
        self.assertEqual(
            len({reservation["stable_guid"] for reservation in reservations}),
            PATCH_COUNT,
        )
        for patch, reservation in zip(self.profile["patches"], reservations):
            self.assertEqual(reservation["source_patch"], patch["name"])
            self.assertEqual(reservation["stable_seed"], patch["stable_seed"])
            self.assertEqual(reservation["stable_seed"], region_hash(patch["patch_id"], 0))
            for actual, expected in zip(reservation["center_direction"], patch["center_direction"]):
                self.assertAlmostEqual(actual, expected, places=14)

    def test_radius_contract_matches_cpp_lane_two_algorithm(self):
        for reservation in self.document["reservations"]:
            region_index = reservation["region_index"]
            alpha = float(region_hash(region_index, 2) & 0x00FFFFFF) / 16_777_215.0
            expected_hub = 25_000.0 + (25_000.0 * alpha)
            self.assertAlmostEqual(reservation["suggested_hub_radius_cm"], expected_hub, places=5)
            self.assertAlmostEqual(reservation["protected_radius_cm"], expected_hub * 0.60, places=5)
            self.assertAlmostEqual(reservation["blend_radius_cm"], expected_hub * 0.40, places=5)
            self.assertAlmostEqual(
                reservation["protected_radius_cm"] + reservation["blend_radius_cm"],
                reservation["suggested_hub_radius_cm"],
                places=5,
            )

    def test_every_hub_blocks_all_required_feature_classes(self):
        expected = ["Foliage", "Rock", "Creature", "Resource", "Water", "POI"]
        self.assertEqual(self.document["blocked_feature_tags"], expected)
        for reservation in self.document["reservations"]:
            self.assertEqual(reservation["blocked_feature_tags"], expected)
            self.assertFalse(reservation["runtime_consumed"])
        component_source = COMPONENT_CPP.read_text(encoding="utf-8-sig")
        for tag in expected:
            self.assertIn(f'TEXT("{tag}")', component_source)

    def test_runtime_component_exposes_fail_closed_feature_query(self):
        header_source = COMPONENT_HEADER.read_text(encoding="utf-8-sig")
        component_source = COMPONENT_CPP.read_text(encoding="utf-8-sig")
        self.assertIn("BlocksFeatureAtWorldPoint", header_source)
        self.assertIn("GetFeatureProtectionWeight", header_source)
        self.assertIn("FeatureTag.IsNone()", component_source)
        self.assertIn("BlockedFeatureTags.Contains(FeatureTag)", component_source)
        self.assertIn("return GetProtectionWeight(WorldPoint);", component_source)

    def test_authority_rasters_are_not_misrepresented_as_pcg_masks(self):
        authority = self.document["mask_sources"]["authority"]
        self.assertEqual(authority["status"], "authoring_ownership_not_pcg_boundary")
        self.assertEqual(authority["nonzero_pixels_across_all_patches"], 0)
        for reservation in self.document["reservations"]:
            self.assertFalse(reservation["authority_used_as_pcg_mask"])
            self.assertEqual(reservation["authority_nonzero_pixels"], 0)

    def test_missing_lake_river_road_and_runtime_consumers_remain_fail_closed(self):
        for mask_name in ("lake", "river", "road"):
            self.assertEqual(self.document["mask_sources"][mask_name]["status"], "not_authored")
        integration = self.document["integration_status"]
        self.assertTrue(integration["offline_dataset_ready"])
        self.assertFalse(integration["runtime_reservation_consumer"])
        self.assertFalse(integration["worldgen_adapter"])
        self.assertFalse(integration["handplaced_structure_mask"])
        self.assertFalse(integration["lake_and_river_masks"])
        self.assertFalse(self.document["surface_dressing"]["enabled"])

    def test_generation_and_dataset_hash_are_order_stable(self):
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        rasters = json.loads(RASTERS.read_text(encoding="utf-8"))
        profile["patches"].reverse()
        rasters["patches"].reverse()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_path = root / "RED_PatchProfile.json"
            raster_path = root / "RED_PatchRasters.json"
            profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
            rasters["profile_sha256"] = generator.sha256_file(profile_path)
            raster_path.write_text(json.dumps(rasters, indent=2) + "\n", encoding="utf-8")
            # Authority files are authenticated relative to the profile directory.
            source_dir = PROFILE.parent
            for record in rasters["patches"]:
                name = record["files"]["authority"]["file"]
                (root / name).write_bytes((source_dir / name).read_bytes())
            reordered = generator.build_document(profile_path, raster_path)
        self.assertEqual(reordered["reservations"], self.document["reservations"])
        self.assertEqual(
            reordered["reservation_dataset_sha256"],
            self.document["reservation_dataset_sha256"],
        )

    def test_persisted_dataset_is_current(self):
        self.assertTrue(PERSISTED.is_file())
        self.assertEqual(
            PERSISTED.read_text(encoding="utf-8"),
            generator.render_document(self.document),
        )
        declared = self.document["reservation_dataset_sha256"]
        self.assertEqual(declared, generator.canonical_sha256(self.document["reservations"]))


if __name__ == "__main__":
    unittest.main()
