"""Generate deterministic PCG exclusion reservations for RED's 27 planet hubs.

The authoring authority rasters control tangent-patch blend ownership. They are
not PCG masks. This tool derives a separate, auditable reservation dataset from
the same region centers, stable seeds, and hub-radius algorithm as the C++
FPlanetRegionService.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import uuid
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

try:
    from Tools.planet_patch_compositor import LAYOUT_SEED, PATCH_COUNT, region_hash
except ModuleNotFoundError:  # Direct execution from Tools/.
    from planet_patch_compositor import LAYOUT_SEED, PATCH_COUNT, region_hash


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "SourceArt" / "Planet50Km" / "AuthoringPatches" / "RED_PatchProfile.json"
DEFAULT_RASTERS = ROOT / "SourceArt" / "Planet50Km" / "AuthoringPatches" / "RED_PatchRasters.json"
DEFAULT_OUTPUT = ROOT / "docs" / "PLANET_50KM_PCG_RESERVATIONS.json"

SCHEMA = "redmmotitan.planet_pcg_reservations.v1"
GENERATOR = "Tools/generate_planet_pcg_reservations.py"
NAMESPACE = uuid.UUID("b0792c75-a7d0-52da-a0a7-f3bb830f76c4")
MIN_HUB_RADIUS_CM = 25_000.0
MAX_HUB_RADIUS_CM = 50_000.0
HARD_RADIUS_FRACTION = 0.60
BLEND_RADIUS_FRACTION = 0.40
BLOCKED_FEATURE_TAGS = ("Foliage", "Rock", "Creature", "Resource", "Water", "POI")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def _unit_length(direction: Iterable[float]) -> float:
    values = [float(component) for component in direction]
    if len(values) != 3 or not all(math.isfinite(value) for value in values):
        raise ValueError(f"Invalid center direction: {values}")
    return math.sqrt(sum(value * value for value in values))


def _count_nonzero_authority(path: Path) -> int:
    with Image.open(path) as image:
        grayscale = image.convert("L")
        return sum(1 for value in grayscale.get_flattened_data() if value != 0)


def _hub_radius_cm(region_index: int) -> float:
    alpha = float(region_hash(region_index, 2) & 0x00FFFFFF) / 16_777_215.0
    return MIN_HUB_RADIUS_CM + ((MAX_HUB_RADIUS_CM - MIN_HUB_RADIUS_CM) * alpha)


def build_document(profile_path: Path, raster_manifest_path: Path) -> dict[str, Any]:
    profile_path = profile_path.resolve()
    raster_manifest_path = raster_manifest_path.resolve()
    profile = _read_json(profile_path)
    rasters = _read_json(raster_manifest_path)

    if profile.get("schema") != "redmmotitan.tangent_macro_patches.v1":
        raise ValueError("Unexpected tangent-patch profile schema")
    if int(profile.get("layout_seed", -1)) != LAYOUT_SEED:
        raise ValueError("Patch profile layout seed does not match FPlanet50KmProfile")
    if int(profile.get("patch_count", -1)) != PATCH_COUNT:
        raise ValueError(f"Expected exactly {PATCH_COUNT} authoring patches")
    if rasters.get("schema") != "redmmotitan.tangent_patch_rasters.v1":
        raise ValueError("Unexpected tangent-patch raster schema")
    if int(rasters.get("patch_count", -1)) != PATCH_COUNT:
        raise ValueError(f"Expected exactly {PATCH_COUNT} raster records")

    profile_hash = sha256_file(profile_path)
    if rasters.get("profile_sha256") != profile_hash:
        raise ValueError("Raster manifest does not authenticate the current patch profile")

    profile_records = {int(item["patch_id"]): item for item in profile["patches"]}
    raster_records = {int(item["patch_id"]): item for item in rasters["patches"]}
    expected_ids = set(range(PATCH_COUNT))
    if set(profile_records) != expected_ids or set(raster_records) != expected_ids:
        raise ValueError("Profile and raster manifest must each contain patch IDs 0 through 26")

    reservations: list[dict[str, Any]] = []
    authority_nonzero_total = 0
    for region_index in range(PATCH_COUNT):
        patch = profile_records[region_index]
        raster = raster_records[region_index]
        expected_seed = region_hash(region_index, 0)
        if int(patch["stable_seed"]) != expected_seed:
            raise ValueError(f"Patch {region_index} stable seed differs from the region service")
        if int(raster["stable_seed"]) != expected_seed:
            raise ValueError(f"Raster {region_index} stable seed differs from the region service")
        if abs(_unit_length(patch["center_direction"]) - 1.0) > 1.0e-9:
            raise ValueError(f"Patch {region_index} center direction is not unit length")

        authority_record = raster["files"]["authority"]
        authority_path = profile_path.parent / str(authority_record["file"])
        if sha256_file(authority_path) != authority_record["sha256"]:
            raise ValueError(f"Patch {region_index} authority raster hash mismatch")
        authority_nonzero = _count_nonzero_authority(authority_path)
        authority_nonzero_total += authority_nonzero

        hub_radius = _hub_radius_cm(region_index)
        hard_radius = hub_radius * HARD_RADIUS_FRACTION
        blend_radius = hub_radius * BLEND_RADIUS_FRACTION
        reservation_id = f"R{region_index:02d}_{patch['archetype']}_MainHub"
        stable_guid = str(
            uuid.uuid5(NAMESPACE, f"{LAYOUT_SEED}:{region_index}:{expected_seed}:{reservation_id}")
        ).upper()
        reservations.append(
            {
                "reservation_id": reservation_id,
                "stable_guid": stable_guid,
                "region_index": region_index,
                "source_patch": str(patch["name"]),
                "stable_seed": expected_seed,
                "archetype": str(patch["archetype"]),
                "center_direction": [float(value) for value in patch["center_direction"]],
                "suggested_hub_radius_cm": round(hub_radius, 6),
                "protected_radius_cm": round(hard_radius, 6),
                "blend_radius_cm": round(blend_radius, 6),
                "blocked_feature_tags": list(BLOCKED_FEATURE_TAGS),
                "authority_raster": str(authority_record["file"]),
                "authority_nonzero_pixels": authority_nonzero,
                "authority_used_as_pcg_mask": False,
                "runtime_component": "URedManualPlacementProtectionComponent",
                "runtime_consumed": False,
            }
        )

    reservation_hash = canonical_sha256(reservations)
    return {
        "schema": SCHEMA,
        "purpose": "deterministic geodesic PCG exclusions for the 27 handcrafted hub footprints",
        "generated_by": GENERATOR,
        "profile_file": _display_path(profile_path),
        "profile_sha256": profile_hash,
        "raster_manifest_file": _display_path(raster_manifest_path),
        "raster_manifest_sha256": sha256_file(raster_manifest_path),
        "layout_seed": LAYOUT_SEED,
        "planet_radius_cm": float(profile["planet_radius_cm"]),
        "reservation_count": len(reservations),
        "reservation_dataset_sha256": reservation_hash,
        "blocked_feature_tags": list(BLOCKED_FEATURE_TAGS),
        "radius_contract": {
            "minimum_hub_radius_cm": MIN_HUB_RADIUS_CM,
            "maximum_hub_radius_cm": MAX_HUB_RADIUS_CM,
            "protected_fraction": HARD_RADIUS_FRACTION,
            "blend_fraction": BLEND_RADIUS_FRACTION,
            "distance_metric": "great-circle arc distance on the active planet radius",
        },
        "mask_sources": {
            "land_ocean": {
                "status": "authored",
                "source": "RED_Patch_##_Land.png and fused six-face land masks",
                "pcg_policy": "block water-classified samples and preserve shoreline clearance",
            },
            "biomes": {
                "status": "authored",
                "source": "RED_Patch_##_Biomes.png and fused six-face RGBA masks",
                "channels": ["desert", "temperate", "cold_or_mountain", "alien"],
            },
            "lake": {
                "status": "not_authored",
                "pcg_policy": "fail closed; do not infer a lake from the authority raster",
            },
            "river": {
                "status": "not_authored",
                "pcg_policy": "fail closed; do not infer a river from the authority raster",
            },
            "road": {
                "status": "not_authored",
                "pcg_policy": "future explicit spline or mask reservation required",
            },
            "authority": {
                "status": "authoring_ownership_not_pcg_boundary",
                "source": "RED_Patch_##_Authority.png",
                "manifest_semantics": str(rasters["authority_semantics"]),
                "nonzero_pixels_across_all_patches": authority_nonzero_total,
                "pcg_policy": "never substitute this blend-ownership raster for the reservation dataset",
            },
        },
        "surface_dressing": {
            "enabled": False,
            "approval_required": True,
            "policy": "remain disabled until user-approved packs and a runtime reservation consumer pass",
        },
        "integration_status": {
            "offline_dataset_ready": True,
            "runtime_reservation_consumer": False,
            "worldgen_adapter": False,
            "handplaced_structure_mask": False,
            "lake_and_river_masks": False,
        },
        "reservations": reservations,
    }


def render_document(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--rasters", type=Path, default=DEFAULT_RASTERS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write the deterministic JSON dataset")
    mode.add_argument("--check", action="store_true", help="verify the persisted dataset is current")
    args = parser.parse_args()

    rendered = render_document(build_document(args.profile, args.rasters))
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"RED_PCG_RESERVATIONS_WRITTEN path={args.output} sha256={sha256_file(args.output)}")
        return 0

    if not args.output.is_file():
        raise SystemExit(f"Reservation dataset is missing: {args.output}")
    if args.output.read_text(encoding="utf-8") != rendered:
        raise SystemExit("Reservation dataset is stale or differs from deterministic generation")
    document = json.loads(rendered)
    print(
        "RED_PCG_RESERVATIONS_CURRENT "
        f"count={document['reservation_count']} dataset={document['reservation_dataset_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
