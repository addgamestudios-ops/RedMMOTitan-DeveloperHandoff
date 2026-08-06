import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTER = ROOT / "docs" / "ALIEN_ASSET_GAP_REGISTER.json"


class AlienAssetGapRegisterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(REGISTER.read_text(encoding="utf-8"))
        cls.families = cls.data["families"]

    def test_schema_and_unique_ids(self):
        self.assertEqual(self.data["schema_version"], 1)
        ids = [family["id"] for family in self.families]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 8)

    def test_required_classification_fields(self):
        required = {
            "id",
            "title",
            "decision",
            "generation_allowed",
            "coverage",
            "biome_roles",
            "placement_role",
            "scale_tier",
            "candidate_assets",
            "silhouette_requirement",
            "material_requirement",
            "variant_requirement",
            "next_action",
            "gates",
        }
        valid_decisions = set(self.data["decisions"])
        for family in self.families:
            self.assertTrue(required.issubset(family), family["id"])
            self.assertIn(family["decision"], valid_decisions)
            self.assertTrue(family["biome_roles"])
            self.assertTrue(family["silhouette_requirement"])
            self.assertTrue(family["material_requirement"])

    def test_all_intake_gates_are_present_and_valid(self):
        required_gates = {
            "duplicate_pack_audit",
            "visual_audition",
            "license",
            "topology",
            "lod_hlod",
            "collision",
            "pivot",
            "scale",
            "materials",
            "wind",
            "nanite",
            "performance",
            "hand_placement",
            "pcg",
        }
        valid_states = set(self.data["gate_states"])
        for family in self.families:
            self.assertEqual(set(family["gates"]), required_gates, family["id"])
            self.assertTrue(set(family["gates"].values()).issubset(valid_states))

    def test_generation_is_locked_until_visible_review(self):
        generation = [
            family for family in self.families
            if family["decision"] == "generation_candidate"
        ]
        self.assertEqual(
            {family["id"] for family in generation},
            {
                "coral_umbrella_tree",
                "fungal_cathedral_tree",
                "floating_balloon_spore_life",
            },
        )
        for family in self.families:
            self.assertFalse(family["generation_allowed"], family["id"])
            self.assertEqual(family["gates"]["visual_audition"], "pending")
        for family in generation:
            self.assertEqual(family["candidate_assets"], [])

    def test_installed_coverage_cannot_route_to_generation(self):
        installed = [
            family for family in self.families
            if family["decision"] == "installed_review_first"
        ]
        self.assertGreaterEqual(len(installed), 3)
        for family in installed:
            self.assertTrue(family["candidate_assets"], family["id"])
            self.assertFalse(family["generation_allowed"])
            self.assertEqual(family["gates"]["duplicate_pack_audit"], "pass")

    def test_promotion_record_covers_runtime_and_provenance(self):
        fields = set(self.data["promotion_record_fields"])
        required = {
            "tool_model_version",
            "prompt_seed_date",
            "license_evidence",
            "dimensions_cm",
            "collision_policy",
            "radial_snap_result",
            "nanite_lod_hlod_policy",
            "wind_and_wpo_bounds",
            "performance_evidence",
            "neutral_noon_capture",
            "saturated_dusk_capture",
            "hand_placement_status",
            "pcg_status",
        }
        self.assertTrue(required.issubset(fields))


if __name__ == "__main__":
    unittest.main()
