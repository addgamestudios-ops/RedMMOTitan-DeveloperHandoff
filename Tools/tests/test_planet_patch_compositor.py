"""Behavioral contract for the 27-patch planet authoring compositor.

The production implementation lives in ``Tools/planet_patch_compositor.py``.
These tests deliberately calculate region sites, tangent projection, and cube
seam directions independently so copying a defect between the implementation
and its tests cannot make the suite pass.

Run from the repository root with::

    python -m unittest Tools.tests.test_planet_patch_compositor
"""

from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = REPOSITORY_ROOT / "Tools"
COMPOSITOR_PATH = TOOLS_ROOT / "planet_patch_compositor.py"
TEST_TEMP_ROOT = REPOSITORY_ROOT / "tmp"

if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import planet_patch_compositor as compositor


PATCH_COUNT = 27
LAYOUT_SEED = 0x52454435
PLANET_RADIUS_CM = 795_774.7154594767
SURFACE_AREA_SQUARE_KM = 795.7747154594767
AUTHORED_WIDTH_CM = math.sqrt(SURFACE_AREA_SQUARE_KM / PATCH_COUNT) * 100_000.0
SUPPORT_WIDTH_CM = 800_000.0
FEATHER_FRACTION = (SUPPORT_WIDTH_CM - AUTHORED_WIDTH_CM) / (2.0 * SUPPORT_WIDTH_CM)
GOLDEN_ANGLE = 2.3999632297286533222315555066336

FACE_FRAMES = (
    ("PX", (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    ("NX", (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    ("PY", (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ("NY", (0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ("PZ", (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    ("NZ", (0.0, 0.0, -1.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),
)


def _add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(value: tuple[float, float, float], scalar: float) -> tuple[float, float, float]:
    return (value[0] * scalar, value[1] * scalar, value[2] * scalar)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        (a[1] * b[2]) - (a[2] * b[1]),
        (a[2] * b[0]) - (a[0] * b[2]),
        (a[0] * b[1]) - (a[1] * b[0]),
    )


def _length(value: tuple[float, float, float]) -> float:
    return math.sqrt(_dot(value, value))


def _normalize(value: tuple[float, float, float]) -> tuple[float, float, float]:
    magnitude = _length(value)
    if magnitude <= 0.0:
        raise ValueError("cannot normalize a zero vector in the test oracle")
    return _scale(value, 1.0 / magnitude)


def _mix32(value: int) -> int:
    """Mirror RedPlanetRegionService's uint32 avalanche hash."""

    value = (value + 0x9E3779B9) & 0xFFFFFFFF
    value = ((value ^ (value >> 16)) * 0x85EBCA6B) & 0xFFFFFFFF
    value = ((value ^ (value >> 13)) * 0xC2B2AE35) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def _region_hash(region_index: int, lane: int) -> int:
    value = (
        LAYOUT_SEED
        ^ ((region_index * 0x9E3779B9) & 0xFFFFFFFF)
        ^ ((lane * 0x85EBCA6B) & 0xFFFFFFFF)
    )
    return _mix32(value)


def _expected_patch_centers() -> list[tuple[float, float, float]]:
    phase = ((_region_hash(0, 99) & 0x00FFFFFF) / 16_777_215.0) * math.tau
    result: list[tuple[float, float, float]] = []
    for patch_id in range(PATCH_COUNT):
        fraction = (patch_id + 0.5) / PATCH_COUNT
        z = 1.0 - (2.0 * fraction)
        ring_radius = math.sqrt(max(0.0, 1.0 - (z * z)))
        longitude = phase + (GOLDEN_ANGLE * patch_id)
        result.append(
            (
                ring_radius * math.cos(longitude),
                ring_radius * math.sin(longitude),
                z,
            )
        )
    return result


def _expected_tangent_frame(
    center: tuple[float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return East, North using the project's deterministic +Z fallback rule."""

    up = _normalize(center)
    planet_north = (0.0, 0.0, 1.0)
    north = _add(planet_north, _scale(up, -_dot(planet_north, up)))
    if _dot(north, north) <= 1.0e-20:
        fallback = (1.0, 0.0, 0.0) if abs(up[0]) < 0.9 else (0.0, 1.0, 0.0)
        north = _add(fallback, _scale(up, -_dot(fallback, up)))

    north = _normalize(north)
    east = _normalize(_cross(north, up))
    north = _normalize(_cross(up, east))
    return east, north


def _exp_map_direction(
    center: tuple[float, float, float],
    local_x_cm: float,
    local_y_cm: float,
    radius_cm: float = PLANET_RADIUS_CM,
) -> tuple[float, float, float]:
    up = _normalize(center)
    east, north = _expected_tangent_frame(up)
    tangent = _add(_scale(east, local_x_cm), _scale(north, local_y_cm))
    distance_cm = _length(tangent)
    if distance_cm == 0.0:
        return up
    angle = distance_cm / radius_cm
    return _normalize(
        _add(
            _scale(up, math.cos(angle)),
            _scale(tangent, math.sin(angle) / distance_cm),
        )
    )


def _face_direction(
    normal: tuple[float, float, float],
    axis_u: tuple[float, float, float],
    axis_v: tuple[float, float, float],
    signed_u: float,
    signed_v: float,
) -> tuple[float, float, float]:
    tangent_u = math.tan(signed_u * math.pi * 0.25)
    tangent_v = math.tan(signed_v * math.pi * 0.25)
    return _normalize(
        _add(
            normal,
            _add(_scale(axis_u, tangent_u), _scale(axis_v, tangent_v)),
        )
    )


def _assert_vector_almost_equal(
    testcase: unittest.TestCase,
    actual: tuple[float, float, float] | list[float],
    expected: tuple[float, float, float],
    places: int = 12,
) -> None:
    testcase.assertEqual(len(actual), 3)
    for axis, (actual_value, expected_value) in enumerate(zip(actual, expected, strict=True)):
        testcase.assertAlmostEqual(
            float(actual_value),
            expected_value,
            places=places,
            msg=f"vector axis {axis} differs",
        )


class PlanetPatchCompositorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        cls._temporary_directory = tempfile.TemporaryDirectory(
            prefix="planet_patch_compositor_tests_",
            dir=TEST_TEMP_ROOT,
        )
        cls.temporary_root = Path(cls._temporary_directory.name)
        cls.profile_path = cls.temporary_root / "profile.json"
        compositor.build_default_profile(cls.profile_path)
        cls.profile = compositor.load_profile(cls.profile_path)
        cls.patches = cls.profile["patches"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary_directory.cleanup()

    def test_default_profile_has_exact_patch_ids_and_canonical_sites(self) -> None:
        self.assertEqual(len(self.patches), PATCH_COUNT)
        self.assertEqual([patch["patch_id"] for patch in self.patches], list(range(PATCH_COUNT)))

        expected_centers = _expected_patch_centers()
        for patch, expected_center in zip(self.patches, expected_centers, strict=True):
            _assert_vector_almost_equal(self, patch["center_direction"], expected_center)
            self.assertEqual(patch["heading_deg"], 0.0)
            self.assertAlmostEqual(patch["authored_width_cm"], AUTHORED_WIDTH_CM, places=6)
            self.assertEqual(patch["support_width_cm"], SUPPORT_WIDTH_CM)
            self.assertAlmostEqual(patch["feather_fraction"], FEATHER_FRACTION, places=15)

    def test_default_profile_serialization_is_byte_deterministic(self) -> None:
        repeated_path = self.temporary_root / "profile_repeated.json"
        compositor.build_default_profile(repeated_path)
        self.assertEqual(self.profile_path.read_bytes(), repeated_path.read_bytes())

    def test_loader_rejects_missing_or_duplicate_patch_ids(self) -> None:
        missing = copy.deepcopy(self.profile)
        missing["patches"] = missing["patches"][:-1]
        missing_path = self.temporary_root / "missing_patch.json"
        missing_path.write_text(json.dumps(missing), encoding="utf-8")
        with self.assertRaises(ValueError):
            compositor.load_profile(missing_path)

        duplicate = copy.deepcopy(self.profile)
        duplicate["patches"][-1]["patch_id"] = duplicate["patches"][-2]["patch_id"]
        duplicate_path = self.temporary_root / "duplicate_patch.json"
        duplicate_path.write_text(json.dumps(duplicate), encoding="utf-8")
        with self.assertRaises(ValueError):
            compositor.load_profile(duplicate_path)

    def test_resolution_limits_match_face_importer_contract(self) -> None:
        importer_safe = copy.deepcopy(self.profile)
        importer_safe["patch_resolution"] = 2049
        importer_safe["face_resolution"] = 2047
        self.assertEqual(compositor.validate_profile(importer_safe), [])

        oversized_face = copy.deepcopy(importer_safe)
        oversized_face["face_resolution"] = 2049
        self.assertEqual(
            compositor.validate_profile(oversized_face),
            ["face_resolution must be an odd integer in [3, 2047]"],
        )

    def test_tangent_frame_matches_region_service_and_is_deterministic(self) -> None:
        for center in (_expected_patch_centers()[0], _expected_patch_centers()[13], (0.0, 0.0, 1.0)):
            expected_east, expected_north = _expected_tangent_frame(center)
            first_east, first_north = compositor.tangent_frame(center, 0.0)
            second_east, second_north = compositor.tangent_frame(center, 0.0)
            self.assertEqual(
                (tuple(first_east), tuple(first_north)),
                (tuple(second_east), tuple(second_north)),
            )
            _assert_vector_almost_equal(self, first_east, expected_east)
            _assert_vector_almost_equal(self, first_north, expected_north)
            self.assertAlmostEqual(_dot(tuple(first_east), tuple(first_north)), 0.0, places=12)

    def test_exp_map_projection_round_trips_to_support_uv(self) -> None:
        patch = copy.deepcopy(self.patches[7])
        local_x_cm = SUPPORT_WIDTH_CM * 0.22
        local_y_cm = SUPPORT_WIDTH_CM * -0.17
        direction = _exp_map_direction(tuple(patch["center_direction"]), local_x_cm, local_y_cm)

        first = compositor.direction_to_patch_uv(direction, patch, PLANET_RADIUS_CM)
        repeated = compositor.direction_to_patch_uv(direction, patch, PLANET_RADIUS_CM)
        self.assertEqual(first, repeated)

        u, v, distance_cm, inside = first
        self.assertTrue(inside)
        self.assertAlmostEqual(u, 0.5 + (local_x_cm / SUPPORT_WIDTH_CM), places=11)
        # Raster V grows south while tangent-local +Y is north.
        self.assertAlmostEqual(v, 0.5 - (local_y_cm / SUPPORT_WIDTH_CM), places=11)
        self.assertAlmostEqual(distance_cm, math.hypot(local_x_cm, local_y_cm), places=6)

        outside_direction = _exp_map_direction(
            tuple(patch["center_direction"]),
            SUPPORT_WIDTH_CM * 0.51,
            0.0,
        )
        outside_u, outside_v, _, outside = compositor.direction_to_patch_uv(
            outside_direction,
            patch,
            PLANET_RADIUS_CM,
        )
        self.assertFalse(outside)
        self.assertGreater(outside_u, 1.0)
        self.assertAlmostEqual(outside_v, 0.5, places=11)

    def test_feather_is_cubic_symmetric_and_zero_outside_support(self) -> None:
        feather = 0.2
        self.assertEqual(compositor.feather_weight(-0.01, 0.5, feather), 0.0)
        self.assertEqual(compositor.feather_weight(0.0, 0.5, feather), 0.0)
        self.assertEqual(compositor.feather_weight(1.01, 0.5, feather), 0.0)
        self.assertEqual(compositor.feather_weight(0.5, 0.5, feather), 1.0)
        self.assertEqual(compositor.feather_weight(feather, 0.5, feather), 1.0)
        self.assertAlmostEqual(compositor.feather_weight(0.1, 0.5, feather), 0.5)
        self.assertAlmostEqual(
            compositor.feather_weight(0.05, 0.37, feather),
            compositor.feather_weight(0.95, 0.63, feather),
            places=15,
        )

    def test_overlap_weights_are_normalized_and_patch_order_independent(self) -> None:
        patch_low_id = copy.deepcopy(self.patches[3])
        patch_high_id = copy.deepcopy(self.patches[7])
        patch_high_id["center_direction"] = list(patch_low_id["center_direction"])
        patch_low_id["feather_fraction"] = 0.4
        patch_high_id["feather_fraction"] = 0.2

        # u=0.1 gives raw cubic weights 0.15625 and 0.5 respectively.
        direction = _exp_map_direction(
            tuple(patch_low_id["center_direction"]),
            -0.4 * SUPPORT_WIDTH_CM,
            0.0,
        )
        source_values = {3: 30.0, 7: 10.0}

        def sample_source(patch: dict[str, object], u: float, v: float) -> float:
            self.assertGreaterEqual(u, 0.0)
            self.assertLessEqual(u, 1.0)
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)
            return source_values[int(patch["patch_id"])]

        forward = compositor.composite_direction(
            direction,
            [patch_high_id, patch_low_id],
            sample_source,
            PLANET_RADIUS_CM,
        )
        reversed_result = compositor.composite_direction(
            direction,
            [patch_low_id, patch_high_id],
            sample_source,
            PLANET_RADIUS_CM,
        )

        self.assertEqual(forward, reversed_result)
        self.assertFalse(forward["used_fallback"])
        contributors = forward["contributors"]
        self.assertEqual([entry["patch_id"] for entry in contributors], [3, 7])
        self.assertAlmostEqual(sum(entry["normalized_weight"] for entry in contributors), 1.0, places=15)

        expected_raw = {3: 0.15625, 7: 0.5}
        for contributor in contributors:
            patch_id = contributor["patch_id"]
            self.assertAlmostEqual(contributor["raw_weight"], expected_raw[patch_id], places=12)
            self.assertAlmostEqual(
                contributor["normalized_weight"],
                expected_raw[patch_id] / sum(expected_raw.values()),
                places=12,
            )
        expected_value = ((30.0 * 0.15625) + (10.0 * 0.5)) / (0.15625 + 0.5)
        self.assertAlmostEqual(forward["value"], expected_value, places=12)

    def test_priority_authority_and_center_kernel_shape_raw_weights(self) -> None:
        low = copy.deepcopy(self.patches[3])
        high = copy.deepcopy(self.patches[7])
        high["center_direction"] = list(low["center_direction"])
        high["priority"] = 1

        result = compositor.composite_direction(
            low["center_direction"],
            [high, low],
            lambda patch, u, v: float(patch["patch_id"]),
            PLANET_RADIUS_CM,
            authority_sampler=lambda patch, u, v: 1.0 if patch["patch_id"] == 7 else 0.0,
            center_sigma_radians=0.20,
        )
        by_id = {entry["patch_id"]: entry for entry in result["contributors"]}
        # One priority stop (2x) plus full authority (2^8) gives a 512x preference.
        self.assertAlmostEqual(by_id[7]["raw_weight"] / by_id[3]["raw_weight"], 512.0)
        self.assertAlmostEqual(sum(entry["normalized_weight"] for entry in by_id.values()), 1.0)

        displaced = copy.deepcopy(high)
        displaced["priority"] = 0
        displaced["center_direction"] = list(
            _exp_map_direction(tuple(low["center_direction"]), 100_000.0, 0.0)
        )
        kernel_result = compositor.composite_direction(
            low["center_direction"],
            [low, displaced],
            lambda patch, u, v: 1.0,
            PLANET_RADIUS_CM,
            center_sigma_radians=0.20,
        )
        kernel_by_id = {entry["patch_id"]: entry for entry in kernel_result["contributors"]}
        delta = 100_000.0 / PLANET_RADIUS_CM
        expected_kernel = math.exp(-(delta * delta) / (2.0 * 0.20 * 0.20))
        self.assertAlmostEqual(kernel_by_id[7]["raw_weight"], expected_kernel, places=12)
        self.assertAlmostEqual(kernel_by_id[3]["raw_weight"], 1.0, places=12)

    def test_cube_face_boundaries_produce_identical_composite_samples(self) -> None:
        resolution = 9
        shared_directions: dict[
            tuple[int, int, int],
            list[tuple[str, tuple[float, float, float]]],
        ] = {}

        for face_name, normal, axis_u, axis_v in FACE_FRAMES:
            for y in range(resolution):
                for x in range(resolution):
                    if x not in (0, resolution - 1) and y not in (0, resolution - 1):
                        continue
                    signed_u = -1.0 + ((2.0 * x) / (resolution - 1))
                    signed_v = -1.0 + ((2.0 * y) / (resolution - 1))
                    direction = _face_direction(normal, axis_u, axis_v, signed_u, signed_v)
                    key = tuple(int(round(component * 1_000_000_000_000.0)) for component in direction)
                    shared_directions.setdefault(key, []).append((face_name, direction))

        def sample_source(patch: dict[str, object], u: float, v: float) -> float:
            return (float(patch["patch_id"]) * 0.25) + (u * 2.0) - (v * 3.0)

        comparison_count = 0
        for entries in shared_directions.values():
            if len(entries) < 2:
                continue
            reference_face, reference_direction = entries[0]
            reference = compositor.composite_direction(
                reference_direction,
                self.patches,
                sample_source,
                PLANET_RADIUS_CM,
            )
            self.assertFalse(reference["used_fallback"])
            for face_name, direction in entries[1:]:
                actual = compositor.composite_direction(
                    direction,
                    self.patches,
                    sample_source,
                    PLANET_RADIUS_CM,
                )
                self.assertFalse(actual["used_fallback"])
                self.assertAlmostEqual(
                    actual["value"],
                    reference["value"],
                    places=11,
                    msg=f"cube seam differs between {reference_face} and {face_name}",
                )
                comparison_count += 1

        # 12 edges x 7 non-corner samples, plus two repeats at each of 8 corners.
        self.assertEqual(comparison_count, 100)

    def test_default_support_has_no_positive_weight_holes(self) -> None:
        probes: list[tuple[float, float, float]] = [
            tuple(patch["center_direction"]) for patch in self.patches
        ]
        # Regression probe near the worst uncovered point for the nominal 5.429 km squares.
        probes.append((0.6426834895255048, -0.20290615864315267, -0.738774))

        probe_count = 2_048
        for index in range(probe_count):
            z = 1.0 - (2.0 * (index + 0.5) / probe_count)
            ring_radius = math.sqrt(max(0.0, 1.0 - (z * z)))
            longitude = GOLDEN_ANGLE * index
            probes.append((ring_radius * math.cos(longitude), ring_radius * math.sin(longitude), z))

        for _, normal, axis_u, axis_v in FACE_FRAMES:
            for y in range(17):
                for x in range(17):
                    probes.append(
                        _face_direction(
                            normal,
                            axis_u,
                            axis_v,
                            -1.0 + ((2.0 * x) / 16.0),
                            -1.0 + ((2.0 * y) / 16.0),
                        )
                    )

        uncovered: list[tuple[float, float, float]] = []
        minimum_weight_sum = math.inf
        for direction in probes:
            weight_sum = 0.0
            for patch in self.patches:
                u, v, _, inside = compositor.direction_to_patch_uv(
                    direction,
                    patch,
                    PLANET_RADIUS_CM,
                )
                if inside:
                    weight_sum += compositor.feather_weight(u, v, patch["feather_fraction"])
            minimum_weight_sum = min(minimum_weight_sum, weight_sum)
            if weight_sum <= 1.0e-12:
                uncovered.append(direction)
                if len(uncovered) >= 5:
                    break

        self.assertFalse(uncovered, f"authored coverage holes found at {uncovered}")
        self.assertGreater(minimum_weight_sum, 1.0e-12)

        worst_probe_result = compositor.composite_direction(
            probes[PATCH_COUNT],
            self.patches,
            lambda patch, u, v: 1.0,
            PLANET_RADIUS_CM,
        )
        self.assertFalse(worst_probe_result["used_fallback"])
        self.assertAlmostEqual(worst_probe_result["value"], 1.0, places=15)
        self.assertAlmostEqual(
            sum(entry["normalized_weight"] for entry in worst_probe_result["contributors"]),
            1.0,
            places=15,
        )

    def test_validate_cli_accepts_the_default_profile(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["TMP"] = str(self.temporary_root)
        environment["TEMP"] = str(self.temporary_root)
        completed = subprocess.run(
            [
                sys.executable,
                str(COMPOSITOR_PATH),
                "validate",
                "--profile",
                str(self.profile_path),
                "--samples",
                "4096",
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
