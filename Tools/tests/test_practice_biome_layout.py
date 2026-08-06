"""Offline invariants for the deterministic 200 m hand-placement worksheet."""

import json
import math
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
LAYOUT_PATH = ROOT / "docs" / "PRACTICE_BIOME_200M_LAYOUT.json"


class PracticeBiomeLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
        cls.actors = cls.layout["primary_actors"]

    def test_primary_composition_count(self):
        counts = {}
        for actor in self.actors:
            counts[actor["role"]] = counts.get(actor["role"], 0) + 1
        self.assertEqual(counts, {"HeroLandmark": 1, "BiomeAnchor": 3, "Satellite": 15})

    def test_anchor_distances_are_25_38_55_metres(self):
        anchors = [actor for actor in self.actors if actor["role"] == "BiomeAnchor"]
        distances = []
        for index, left in enumerate(anchors):
            for right in anchors[index + 1 :]:
                dx = left["local_xy_m"][0] - right["local_xy_m"][0]
                dy = left["local_xy_m"][1] - right["local_xy_m"][1]
                distances.append(math.hypot(dx, dy))
        for actual, expected in zip(sorted(distances), [25.0, 38.0, 55.0]):
            self.assertAlmostEqual(actual, expected, delta=0.02)

    def test_colonies_are_unequal_3_5_7(self):
        colonies = {}
        for actor in self.actors:
            if actor["role"] == "Satellite":
                colonies[actor["colony"]] = colonies.get(actor["colony"], 0) + 1
        self.assertEqual(colonies, {"A1": 3, "A2": 5, "A3": 7})

    def test_patch_bounds_scales_and_corridor_clearance(self):
        radius = self.layout["patch"]["diameter_m"] / 2.0
        corridor = self.layout["traversal_corridor"]
        half_width = corridor["width_m"] / 2.0
        for actor in self.actors:
            x, y = actor["local_xy_m"]
            self.assertLess(math.hypot(x, y), radius, actor["id"])
            self.assertGreaterEqual(actor["scale"], 0.8, actor["id"])
            self.assertLessEqual(actor["scale"], 1.25, actor["id"])
            self.assertGreater(abs(y - corridor["center_y_m"]), half_width, actor["id"])

    def test_reservation_rocks_and_ground_cover(self):
        reservation = self.layout["reservation"]
        self.assertEqual(reservation["protected_radius_cm"], 10000.0)
        self.assertEqual(reservation["blend_radius_cm"], 2500.0)
        self.assertEqual(set(reservation["blocked_feature_tags"]), {"Foliage", "Rock", "POI"})
        self.assertEqual(len(self.layout["rock_clusters"]), 2)
        self.assertTrue(all(len(cluster["palette_entry_ids"]) >= 2 for cluster in self.layout["rock_clusters"]))
        self.assertEqual(len(self.layout["ground_cover_islands"]), 3)


if __name__ == "__main__":
    unittest.main()
