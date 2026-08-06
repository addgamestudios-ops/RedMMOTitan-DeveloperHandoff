"""Deterministic tangent-square authoring patches for RED's 50 km planet.

The player experiences one continuous sphere.  These 27 squares are source-art
coordinates only: they overlap, feather, and bake into the six complete PlanetGen
cube faces.  They are never collision, streaming, or gameplay borders.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np


PROFILE_SCHEMA = "redmmotitan.tangent_macro_patches.v1"
PATCH_COUNT = 27
LAYOUT_SEED = 0x52454435  # RedPlanet::FPlanet50KmProfile::LayoutSeed ("RED5")
PLANET_CIRCUMFERENCE_CM = 5_000_000.0
PLANET_RADIUS_CM = 795_774.7154594767
PLANET_SURFACE_AREA_KM2 = 795.7747154594767
AUTHORED_WIDTH_CM = math.sqrt(PLANET_SURFACE_AREA_KM2 / PATCH_COUNT) * 100_000.0

# A 500k-direction audit of the RED spherical-Fibonacci layout requires about
# 731,816 cm for complete square support.  An 8000 m padded source square keeps a
# useful positive feather overlap beyond that sampled bound while the editable
# 5429 m core still represents one twenty-seventh of the planet's surface area.
SUPPORT_WIDTH_CM = 800_000.0
FEATHER_FRACTION = (SUPPORT_WIDTH_CM - AUTHORED_WIDTH_CM) / (2.0 * SUPPORT_WIDTH_CM)

TWO_PI = 2.0 * math.pi
GOLDEN_ANGLE = 2.3999632297286533222315555066336
_DIRECTION_EPSILON_SQUARED = 1.0e-20

REGION_ARCHETYPES = (
    "CoralCanopyCoast",
    "EmberMagentaRift",
    "FungalCathedral",
    "MonolithicPillarCavern",
    "VerdantSkyPlateau",
    "PortalOasis",
    "CliffsideSpaceport",
)


def _unit(value: Sequence[float]) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float64)
    length = float(np.linalg.norm(vector))
    if not math.isfinite(length) or length * length <= _DIRECTION_EPSILON_SQUARED:
        return np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    return vector / length


def _mix32(value: int) -> int:
    value = (int(value) + 0x9E3779B9) & 0xFFFFFFFF
    value = ((value ^ (value >> 16)) * 0x85EBCA6B) & 0xFFFFFFFF
    value = ((value ^ (value >> 13)) * 0xC2B2AE35) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def region_hash(region_index: int, lane: int) -> int:
    value = (
        LAYOUT_SEED
        ^ ((int(region_index) * 0x9E3779B9) & 0xFFFFFFFF)
        ^ ((int(lane) * 0x85EBCA6B) & 0xFFFFFFFF)
    )
    return _mix32(value)


def _unit_float(region_index: int, lane: int) -> float:
    return float(region_hash(region_index, lane) & 0x00FFFFFF) / 16_777_215.0


def default_region_centers(count: int = PATCH_COUNT) -> list[list[float]]:
    """Match FPlanetRegionService's half-step spherical-Fibonacci sites exactly."""
    if count <= 0:
        raise ValueError("count must be positive")
    phase_radians = _unit_float(0, 99) * TWO_PI
    centers: list[list[float]] = []
    for patch_id in range(count):
        fraction = (float(patch_id) + 0.5) / float(count)
        z = 1.0 - (2.0 * fraction)
        ring_radius = math.sqrt(max(0.0, 1.0 - (z * z)))
        longitude = phase_radians + (GOLDEN_ANGLE * patch_id)
        centers.append(
            [ring_radius * math.cos(longitude), ring_radius * math.sin(longitude), z]
        )
    return centers


def tangent_frame(
    center: Sequence[float], heading_deg: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """Return map-local +X/east and +Y/north axes, matching the C++ frame."""
    up = _unit(center)
    north_axis = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    north = north_axis - (up * float(np.dot(north_axis, up)))
    if float(np.dot(north, north)) <= _DIRECTION_EPSILON_SQUARED:
        fallback = (
            np.asarray((1.0, 0.0, 0.0), dtype=np.float64)
            if abs(float(up[0])) < 0.9
            else np.asarray((0.0, 1.0, 0.0), dtype=np.float64)
        )
        north = fallback - (up * float(np.dot(fallback, up)))
    north = _unit(north)
    east = _unit(np.cross(north, up))
    north = _unit(np.cross(up, east))

    heading = math.radians(float(heading_deg))
    cosine = math.cos(heading)
    sine = math.sin(heading)
    local_x = (east * cosine) - (north * sine)
    local_y = (east * sine) + (north * cosine)
    return _unit(local_x), _unit(local_y)


def exp_map_direction(
    center: Sequence[float],
    local_x_cm: float,
    local_y_cm: float,
    radius_cm: float = PLANET_RADIUS_CM,
    heading_deg: float = 0.0,
) -> np.ndarray:
    up = _unit(center)
    axis_x, axis_y = tangent_frame(up, heading_deg)
    tangent = (axis_x * float(local_x_cm)) + (axis_y * float(local_y_cm))
    arc_length = float(np.linalg.norm(tangent))
    if arc_length <= 1.0e-12 or radius_cm <= 1.0e-12:
        return up
    angle = arc_length / float(radius_cm)
    return _unit((up * math.cos(angle)) + ((tangent / arc_length) * math.sin(angle)))


def log_map_offset_cm(
    center: Sequence[float],
    direction: Sequence[float],
    radius_cm: float = PLANET_RADIUS_CM,
    heading_deg: float = 0.0,
) -> tuple[float, float, float]:
    """Return map-local X/Y arc offsets plus great-circle distance."""
    up = _unit(center)
    target = _unit(direction)
    axis_x, axis_y = tangent_frame(up, heading_deg)
    dot = float(np.clip(np.dot(up, target), -1.0, 1.0))
    angle = math.acos(dot)
    if angle <= 1.0e-12 or radius_cm <= 1.0e-12:
        return 0.0, 0.0, 0.0
    tangent = target - (up * dot)
    tangent_length = float(np.linalg.norm(tangent))
    tangent_direction = axis_x if tangent_length <= 1.0e-12 else tangent / tangent_length
    arc_length = angle * float(radius_cm)
    return (
        float(np.dot(tangent_direction, axis_x)) * arc_length,
        float(np.dot(tangent_direction, axis_y)) * arc_length,
        arc_length,
    )


def direction_to_patch_uv(
    direction: Sequence[float],
    patch: dict[str, Any],
    radius_cm: float = PLANET_RADIUS_CM,
) -> tuple[float, float, float, bool]:
    """Map a sphere direction to the patch's padded source raster.

    Raster row 0 is the local-north edge, hence V decreases as local north grows.
    """
    support_width = float(patch["support_width_cm"])
    x_cm, y_cm, distance_cm = log_map_offset_cm(
        patch["center_direction"],
        direction,
        radius_cm,
        float(patch.get("heading_deg", 0.0)),
    )
    u = 0.5 + (x_cm / support_width)
    v = 0.5 - (y_cm / support_width)
    tolerance = 1.0e-12
    inside = -tolerance <= u <= 1.0 + tolerance and -tolerance <= v <= 1.0 + tolerance
    return u, v, distance_cm, inside


def patch_uv_to_direction(
    patch: dict[str, Any],
    u: float,
    v: float,
    radius_cm: float = PLANET_RADIUS_CM,
) -> np.ndarray:
    support_width = float(patch["support_width_cm"])
    return exp_map_direction(
        patch["center_direction"],
        (float(u) - 0.5) * support_width,
        (0.5 - float(v)) * support_width,
        radius_cm,
        float(patch.get("heading_deg", 0.0)),
    )


def feather_weight(u: float, v: float, feather_fraction: float) -> float:
    if not (math.isfinite(u) and math.isfinite(v) and math.isfinite(feather_fraction)):
        return 0.0
    if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
        return 0.0
    feather = max(1.0e-12, min(0.5, float(feather_fraction)))
    edge_distance = min(float(u), 1.0 - float(u), float(v), 1.0 - float(v))
    if edge_distance >= feather:
        return 1.0
    alpha = max(0.0, min(1.0, edge_distance / feather))
    return alpha * alpha * (3.0 - (2.0 * alpha))


def _weighted_add(total: Any, sample: Any, weight: float) -> Any:
    weighted = np.asarray(sample, dtype=np.float64) * float(weight)
    return weighted if total is None else total + weighted


def composite_direction(
    direction: Sequence[float],
    patches: Iterable[dict[str, Any]],
    source_sampler: Callable[[dict[str, Any], float, float], Any],
    radius_cm: float = PLANET_RADIUS_CM,
    fallback_sampler: Callable[[Sequence[float]], Any] | None = None,
    authority_sampler: Callable[[dict[str, Any], float, float], float] | None = None,
    center_sigma_radians: float | None = None,
) -> dict[str, Any]:
    """Blend every overlapping square with normalized, order-independent weights."""
    candidates: list[tuple[dict[str, Any], float, float, float, float, float]] = []
    for patch in sorted(patches, key=lambda item: int(item["patch_id"])):
        u, v, distance_cm, inside = direction_to_patch_uv(direction, patch, radius_cm)
        if not inside:
            continue
        edge_weight = feather_weight(u, v, float(patch["feather_fraction"]))
        if edge_weight <= 0.0:
            continue
        authority = 0.0 if authority_sampler is None else float(authority_sampler(patch, u, v))
        authority = max(0.0, min(1.0, authority)) if math.isfinite(authority) else 0.0
        candidates.append((patch, u, v, distance_cm / float(radius_cm), edge_weight, authority))

    nearest_delta = min((item[3] for item in candidates), default=0.0)
    sigma = None
    if center_sigma_radians is not None:
        candidate_sigma = float(center_sigma_radians)
        if math.isfinite(candidate_sigma) and candidate_sigma > 0.0:
            sigma = candidate_sigma

    weighted_candidates: list[tuple[dict[str, Any], float, float, float, float]] = []
    for patch, u, v, delta, edge_weight, authority in candidates:
        center_weight = 1.0
        if sigma is not None:
            center_weight = math.exp(
                -((delta * delta) - (nearest_delta * nearest_delta)) / (2.0 * sigma * sigma)
            )
        priority = max(-8, min(8, int(patch.get("priority", 0))))
        raw_weight = edge_weight * center_weight * math.pow(2.0, priority + (8.0 * authority))
        weighted_candidates.append((patch, u, v, raw_weight, authority))

    weight_sum = math.fsum(item[3] for item in weighted_candidates)
    if weight_sum <= 1.0e-15:
        value = fallback_sampler(direction) if fallback_sampler is not None else None
        return {"value": value, "contributors": [], "used_fallback": True}

    total: Any = None
    contributors: list[dict[str, Any]] = []
    for patch, u, v, raw_weight, authority in weighted_candidates:
        normalized_weight = raw_weight / weight_sum
        sample = source_sampler(patch, u, v)
        total = _weighted_add(total, sample, normalized_weight)
        contributors.append(
            {
                "patch_id": int(patch["patch_id"]),
                "u": u,
                "v": v,
                "raw_weight": raw_weight,
                "normalized_weight": normalized_weight,
                "authority": authority,
            }
        )

    value_array = np.asarray(total)
    value: Any = float(value_array) if value_array.ndim == 0 else value_array
    return {"value": value, "contributors": contributors, "used_fallback": False}


def build_default_profile(
    output_path: str | Path | None = None,
    count: int = PATCH_COUNT,
    radius_cm: float = PLANET_RADIUS_CM,
) -> dict[str, Any]:
    if count != PATCH_COUNT:
        raise ValueError(f"RED's current authoring contract requires exactly {PATCH_COUNT} patches")
    centers = default_region_centers(count)
    archetype_offset = LAYOUT_SEED % len(REGION_ARCHETYPES)
    patches: list[dict[str, Any]] = []
    for patch_id, center in enumerate(centers):
        name = f"RED_Patch_{patch_id:02d}"
        patches.append(
            {
                "patch_id": patch_id,
                "name": name,
                "stable_seed": region_hash(patch_id, 0),
                "center_direction": center,
                "heading_deg": 0.0,
                "authored_width_cm": AUTHORED_WIDTH_CM,
                "support_width_cm": SUPPORT_WIDTH_CM,
                "feather_fraction": FEATHER_FRACTION,
                "priority": 0,
                "archetype": REGION_ARCHETYPES[(patch_id + archetype_offset) % len(REGION_ARCHETYPES)],
                "height_file": f"{name}_Height.r16",
                "land_file": f"{name}_Land.png",
                "biome_file": f"{name}_Biomes.png",
                "authority_mask_file": f"{name}_Authority.png",
                "height_scale": 1.0,
                "height_bias_cm": 0.0,
            }
        )

    profile: dict[str, Any] = {
        "schema": PROFILE_SCHEMA,
        "purpose": "27 overlapping tangent-local source maps; never gameplay boundaries",
        "layout_seed": LAYOUT_SEED,
        "planet_circumference_cm": PLANET_CIRCUMFERENCE_CM,
        "planet_radius_cm": float(radius_cm),
        "patch_count": count,
        "patch_resolution": 513,
        "face_resolution": 513,
        "average_authoring_area_km2": PLANET_SURFACE_AREA_KM2 / count,
        "authored_width_cm": AUTHORED_WIDTH_CM,
        "support_width_cm": SUPPORT_WIDTH_CM,
        "feather_cm": (SUPPORT_WIDTH_CM - AUTHORED_WIDTH_CM) * 0.5,
        "height_min_cm": -30_000.0,
        "height_max_cm": 30_000.0,
        "sea_height_cm": 0.0,
        "center_sigma_radians": 0.20,
        "projection": "spherical exponential/log map in deterministic RED tangent frame",
        "raster_orientation": "U east; V south; row 0 is local-north support edge",
        "blend": "normalized smoothstep edge feather; stable patch_id accumulation",
        "patches": patches,
    }
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return profile


def validate_profile(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if profile.get("schema") != PROFILE_SCHEMA:
        errors.append(f"schema must be {PROFILE_SCHEMA}")
    for resolution_field, maximum in (
        ("patch_resolution", 2049),
        ("face_resolution", 2047),
    ):
        value = profile.get(resolution_field)
        if not isinstance(value, int) or value < 3 or value > maximum or value % 2 == 0:
            errors.append(
                f"{resolution_field} must be an odd integer in [3, {maximum}]"
            )
    try:
        radius_cm = float(profile["planet_radius_cm"])
        height_min_cm = float(profile["height_min_cm"])
        height_max_cm = float(profile["height_max_cm"])
        sea_height_cm = float(profile["sea_height_cm"])
        center_sigma = float(profile["center_sigma_radians"])
    except (KeyError, TypeError, ValueError):
        errors.append("profile has malformed radius, height range, sea height, or center sigma")
    else:
        if not math.isfinite(radius_cm) or radius_cm <= 0.0:
            errors.append("planet_radius_cm must be finite and positive")
        if not all(math.isfinite(value) for value in (height_min_cm, height_max_cm, sea_height_cm)):
            errors.append("height range and sea height must be finite")
        elif height_max_cm <= height_min_cm or not height_min_cm <= sea_height_cm <= height_max_cm:
            errors.append("height range must be ordered and contain sea_height_cm")
        if not math.isfinite(center_sigma) or center_sigma <= 0.0:
            errors.append("center_sigma_radians must be finite and positive")
    patches = profile.get("patches")
    if not isinstance(patches, list) or len(patches) != PATCH_COUNT:
        errors.append(f"profile must contain exactly {PATCH_COUNT} patches")
        return errors
    ids = [patch.get("patch_id") for patch in patches if isinstance(patch, dict)]
    if ids != list(range(PATCH_COUNT)):
        errors.append("patch IDs must be unique and ordered 0..26")
    canonical_centers = default_region_centers(PATCH_COUNT)
    for patch in patches:
        if not isinstance(patch, dict):
            errors.append("every patch must be an object")
            continue
        try:
            center = np.asarray(patch["center_direction"], dtype=np.float64)
            patch_id = int(patch["patch_id"])
            authored = float(patch["authored_width_cm"])
            support = float(patch["support_width_cm"])
            feather = float(patch["feather_fraction"])
            heading = float(patch["heading_deg"])
            priority = int(patch["priority"])
            stable_seed = int(patch["stable_seed"])
            height_scale = float(patch["height_scale"])
            height_bias_cm = float(patch["height_bias_cm"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"patch {patch.get('patch_id')} has malformed geometry fields")
            continue
        if center.shape != (3,) or not np.all(np.isfinite(center)) or abs(float(np.linalg.norm(center)) - 1.0) > 1.0e-9:
            errors.append(f"patch {patch_id} center must be a finite unit vector")
        elif patch_id < 0 or patch_id >= PATCH_COUNT or not np.allclose(
            center, canonical_centers[patch_id], rtol=0.0, atol=1.0e-12
        ):
            errors.append(f"patch {patch_id} center does not match FPlanetRegionService")
        expected_feather = (support - authored) / (2.0 * support) if support > 0.0 else -1.0
        if not all(math.isfinite(value) for value in (authored, support, feather, heading, height_scale, height_bias_cm)):
            errors.append(f"patch {patch_id} geometry and height transforms must be finite")
        elif authored <= 0.0 or support <= authored:
            errors.append(f"patch {patch_id} support must exceed authored width")
        elif abs(feather - expected_feather) > 1.0e-9:
            errors.append(f"patch {patch_id} feather does not preserve authored core")
        if priority < -8 or priority > 8:
            errors.append(f"patch {patch_id} priority must be in [-8, 8]")
        if stable_seed != region_hash(patch_id, 0):
            errors.append(f"patch {patch_id} stable seed does not match FPlanetRegionService")
        expected_files = {
            "height_file": f"RED_Patch_{patch_id:02d}_Height.r16",
            "land_file": f"RED_Patch_{patch_id:02d}_Land.png",
            "biome_file": f"RED_Patch_{patch_id:02d}_Biomes.png",
            "authority_mask_file": f"RED_Patch_{patch_id:02d}_Authority.png",
        }
        for field, expected_name in expected_files.items():
            if patch.get(field) != expected_name:
                errors.append(f"patch {patch_id} {field} must be {expected_name}")
    return errors


def load_profile(path: str | Path) -> dict[str, Any]:
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = validate_profile(profile)
    if errors:
        raise ValueError("; ".join(errors))
    return profile


def coverage_audit(profile: dict[str, Any], sample_count: int = 100_000) -> dict[str, Any]:
    """Deterministically measure worst square support and feather coverage."""
    patches = profile["patches"]
    indices = np.arange(sample_count, dtype=np.float64)
    fraction = (indices + 0.5) / float(sample_count)
    z = 1.0 - (2.0 * fraction)
    ring = np.sqrt(np.maximum(0.0, 1.0 - (z * z)))
    phase = _unit_float(0, 99) * TWO_PI
    longitude = phase + (GOLDEN_ANGLE * indices)
    directions = np.stack((ring * np.cos(longitude), ring * np.sin(longitude), z), axis=-1)

    radius_cm = float(profile["planet_radius_cm"])
    best_weights = np.zeros(sample_count, dtype=np.float64)
    nearest_square_half_extent = np.full(sample_count, np.inf, dtype=np.float64)
    for patch in patches:
        up = _unit(patch["center_direction"])
        axis_x, axis_y = tangent_frame(up, float(patch.get("heading_deg", 0.0)))
        dots = np.clip(directions @ up, -1.0, 1.0)
        angles = np.arccos(dots)
        tangents = directions - (dots[:, None] * up)
        tangent_lengths = np.linalg.norm(tangents, axis=-1)
        safe_lengths = np.where(tangent_lengths > 1.0e-15, tangent_lengths, 1.0)
        tangent_directions = tangents / safe_lengths[:, None]
        tangent_directions[tangent_lengths <= 1.0e-15] = axis_x
        arc_lengths = angles * radius_cm
        x_cm = (tangent_directions @ axis_x) * arc_lengths
        y_cm = (tangent_directions @ axis_y) * arc_lengths
        half_extent = np.maximum(np.abs(x_cm), np.abs(y_cm))
        nearest_square_half_extent = np.minimum(nearest_square_half_extent, half_extent)

        support = float(patch["support_width_cm"])
        u = 0.5 + (x_cm / support)
        v = 0.5 - (y_cm / support)
        inside = (u >= 0.0) & (u <= 1.0) & (v >= 0.0) & (v <= 1.0)
        edge_distance = np.minimum.reduce((u, 1.0 - u, v, 1.0 - v))
        feather = max(1.0e-12, min(0.5, float(patch["feather_fraction"])))
        alpha = np.clip(edge_distance / feather, 0.0, 1.0)
        weights = np.where(inside, alpha * alpha * (3.0 - (2.0 * alpha)), 0.0)
        best_weights = np.maximum(best_weights, weights)

    uncovered = int(np.count_nonzero(best_weights <= 0.0))
    minimum_best_weight = float(np.min(best_weights))
    max_required_full_width_cm = float(np.max(nearest_square_half_extent) * 2.0)
    return {
        "sample_count": sample_count,
        "uncovered_samples": uncovered,
        "minimum_best_weight": minimum_best_weight,
        "max_required_full_width_cm": max_required_full_width_cm,
        "passed": uncovered == 0 and minimum_best_weight > 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create-profile")
    create_parser.add_argument(
        "--output",
        type=Path,
        default=Path("SourceArt/Planet50Km/AuthoringPatches/RED_PatchProfile.json"),
    )
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--profile", type=Path, required=True)
    validate_parser.add_argument("--samples", type=int, default=100_000)
    args = parser.parse_args()

    if args.command == "create-profile":
        profile = build_default_profile(args.output.resolve())
        print(
            f"RED_PATCH_PROFILE_READY output={args.output.resolve()} "
            f"patches={len(profile['patches'])}"
        )
        return

    profile = load_profile(args.profile.resolve())
    audit = coverage_audit(profile, max(1, int(args.samples)))
    print(json.dumps(audit, indent=2))
    if not audit["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
