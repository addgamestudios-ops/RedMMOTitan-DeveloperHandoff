"""Import and verify the 27-patch fused macro-heightfield asset.

This command never loads or saves a level. It only creates or updates the
isolated data asset after authenticating the exact offline bake used by the
50 km prototype. Manifest authentication is intentionally kept independent of
the Unreal Python module so it can be covered by lightweight unit tests.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SOURCE_RELATIVE = "SourceArt/Planet50Km/MacroFacesFromPatches"
ASSET_PACKAGE = "/Game/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield"
EXPECTED_SCHEMA = "redmmotitan.macro_planet_faces.v1"
EXPECTED_RESOLUTION = 257
EXPECTED_MIN_HEIGHT_CM = -30_000.0
EXPECTED_MAX_HEIGHT_CM = 30_000.0
EXPECTED_FACE_DATASET = "AAE25CCA654D3D966C7AE3C5A00A911BA2576E67592D5B1443D9145D0BC2399A"
EXPECTED_PATCH_DATASET = "228E1CDAC65F0AFFB51101E8639AC65C57063FC4C72D74588D24A194A87504ED"
EXPECTED_HEIGHT_ENCODING = "unsigned 16-bit normalized"
EXPECTED_RAW_HEIGHT_ENCODING = "little-endian unsigned 16-bit row-major"
EXPECTED_BIOME_CHANNELS = {
    "r": "desert",
    "g": "temperate",
    "b": "cold_or_mountain",
    "a": "alien",
}

FACE_NAMES = ("PX", "NX", "PY", "NY", "PZ", "NZ")
HEIGHT_FACE_PROPERTIES = (
    "positive_x",
    "negative_x",
    "positive_y",
    "negative_y",
    "positive_z",
    "negative_z",
)
LAND_FACE_PROPERTIES = (
    "land_positive_x",
    "land_negative_x",
    "land_positive_y",
    "land_negative_y",
    "land_positive_z",
    "land_negative_z",
)
BIOME_FACE_PROPERTIES = (
    "biome_positive_x",
    "biome_negative_x",
    "biome_positive_y",
    "biome_negative_y",
    "biome_positive_z",
    "biome_negative_z",
)

# role, legacy top-level filename field, canonical filename, exact nested encoding
FACE_FILE_CONTRACTS = (
    ("height", "height_file", "RED_Height_{face}_16.png", "PNG grayscale uint16"),
    ("raw_height", "raw_height_file", "RED_Height_{face}.r16", "little-endian uint16 row-major"),
    ("land", "land_file", "RED_Land_{face}.png", "PNG L8"),
    ("biomes", "biome_file", "RED_Biomes_{face}.png", "PNG RGBA8"),
)
_SHA256_PATTERN = re.compile(r"[0-9A-F]{64}")


def sha256_file(filename: str | Path) -> str:
    """Return the generator's canonical uppercase SHA-256 for one file."""

    digest = hashlib.sha256()
    with Path(filename).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def dataset_sha256(records: Iterable[tuple[str, str]]) -> str:
    """Hash the canonical sorted filename/hash index used by the generator."""

    digest = hashlib.sha256()
    for filename, file_hash in sorted(records):
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"{label} must be an object")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise RuntimeError(f"{label} must be an uppercase 64-character SHA256")
    return value


def authenticate_face_dataset(
    source_dir: str | Path,
    manifest: Mapping[str, Any],
    *,
    expected_face_dataset: str = EXPECTED_FACE_DATASET,
    expected_patch_dataset: str = EXPECTED_PATCH_DATASET,
) -> str:
    """Authenticate the exact six-face, 24-raster dataset before Unreal import.

    The approved dataset digest alone is not enough: every nested role, filename,
    encoding declaration, and file hash is validated first. The final digest is
    then recomputed from the 24 actual file hashes with the generator's canonical
    sorted ``filename + NUL + SHA256 + newline`` algorithm.
    """

    source_root = Path(source_dir)
    expected_face_dataset = _require_sha256(
        expected_face_dataset, "expected fused-face dataset SHA256"
    )
    expected_patch_dataset = _require_sha256(
        expected_patch_dataset, "expected source-patch dataset SHA256"
    )

    if manifest.get("schema") != EXPECTED_SCHEMA:
        raise RuntimeError(f"Unexpected fused-face schema: {manifest.get('schema')}")
    if manifest.get("resolution") != EXPECTED_RESOLUTION:
        raise RuntimeError(f"Unexpected fused-face resolution: {manifest.get('resolution')}")
    if manifest.get("height_encoding") != EXPECTED_HEIGHT_ENCODING:
        raise RuntimeError("Fused-face manifest has a noncanonical height encoding")
    if manifest.get("raw_height_encoding") != EXPECTED_RAW_HEIGHT_ENCODING:
        raise RuntimeError("Fused-face manifest has a noncanonical raw-height encoding")
    if manifest.get("min_height_cm") != EXPECTED_MIN_HEIGHT_CM:
        raise RuntimeError("Fused-face manifest minimum height is not -30000 cm")
    if manifest.get("max_height_cm") != EXPECTED_MAX_HEIGHT_CM:
        raise RuntimeError("Fused-face manifest maximum height is not 30000 cm")
    if manifest.get("biome_channels") != EXPECTED_BIOME_CHANNELS:
        raise RuntimeError("Fused-face manifest has a noncanonical RGBA biome channel map")

    declared_face_dataset = _require_sha256(
        manifest.get("raster_dataset_sha256"), "fused-face raster dataset SHA256"
    )
    if declared_face_dataset != expected_face_dataset:
        raise RuntimeError(
            "Refusing to import an unapproved fused-face dataset: "
            f"{declared_face_dataset}"
        )
    declared_patch_dataset = _require_sha256(
        manifest.get("source_patch_raster_dataset_sha256"),
        "source-patch raster dataset SHA256",
    )
    if declared_patch_dataset != expected_patch_dataset:
        raise RuntimeError(
            "Refusing to import faces not derived from the approved 27-patch dataset"
        )

    coverage = _require_mapping(manifest.get("coverage_validation"), "coverage_validation")
    if coverage.get("passed") is not True:
        raise RuntimeError("Fused-face manifest does not record complete patch coverage")
    seams = _require_mapping(manifest.get("seam_validation"), "seam_validation")
    if seams.get("passed") is not True:
        raise RuntimeError("Fused-face manifest does not record passing seam validation")

    faces = manifest.get("faces")
    if not isinstance(faces, list) or len(faces) != len(FACE_NAMES):
        count = len(faces) if isinstance(faces, list) else 0
        raise RuntimeError(f"Expected six fused faces, found {count}")

    actual_hashes: list[tuple[str, str]] = []
    expected_roles = {contract[0] for contract in FACE_FILE_CONTRACTS}
    for face_index, expected_name in enumerate(FACE_NAMES):
        face = _require_mapping(faces[face_index], f"face record {face_index}")
        if face.get("face_index") != face_index or face.get("name") != expected_name:
            raise RuntimeError(f"Noncanonical fused-face order at index {face_index}")

        files = _require_mapping(face.get("files"), f"{expected_name} files")
        if set(files) != expected_roles:
            raise RuntimeError(
                f"{expected_name} nested files must contain exactly "
                f"{', '.join(sorted(expected_roles))}"
            )

        for role, top_level_key, filename_template, expected_encoding in FACE_FILE_CONTRACTS:
            expected_filename = filename_template.format(face=expected_name)
            if face.get(top_level_key) != expected_filename:
                raise RuntimeError(
                    f"{expected_name} has a noncanonical {top_level_key}: "
                    f"{face.get(top_level_key)}"
                )

            record = _require_mapping(files.get(role), f"{expected_name} {role} record")
            if set(record) != {"file", "encoding", "sha256"}:
                raise RuntimeError(
                    f"{expected_name} {role} record must contain exactly file, encoding, and sha256"
                )
            if record.get("file") != expected_filename:
                raise RuntimeError(
                    f"{expected_name} has a noncanonical nested {role} filename"
                )
            if record.get("encoding") != expected_encoding:
                raise RuntimeError(
                    f"{expected_name} {role} has a noncanonical encoding: "
                    f"{record.get('encoding')}"
                )

            expected_hash = _require_sha256(
                record.get("sha256"), f"{expected_name} {role} SHA256"
            )
            raster_path = source_root / expected_filename
            if not raster_path.is_file():
                raise RuntimeError(f"Missing fused-face raster: {expected_filename}")
            actual_hash = sha256_file(raster_path)
            if actual_hash != expected_hash:
                raise RuntimeError(
                    f"Fused-face hash mismatch for {expected_name} {role}: "
                    f"expected {expected_hash}, got {actual_hash}"
                )
            actual_hashes.append((expected_filename, actual_hash))

    if len(actual_hashes) != 24:
        raise RuntimeError(f"Expected 24 authenticated fused-face rasters, found {len(actual_hashes)}")
    actual_dataset = dataset_sha256(actual_hashes)
    if actual_dataset != declared_face_dataset:
        raise RuntimeError(
            "Fused-face dataset hash mismatch: "
            f"expected {declared_face_dataset}, got {actual_dataset}"
        )
    return actual_dataset


def verify_imported_asset(asset: object) -> tuple[int, int]:
    """Post-verify the loaded Unreal asset, including all mask arrays."""

    if asset is None:
        raise RuntimeError(f"Imported asset could not be loaded: {ASSET_PACKAGE}")
    asset_class = asset.get_class().get_name()
    if asset_class != "PlanetGenMacroHeightfieldAsset":
        raise RuntimeError(f"Imported asset has unexpected class: {asset_class}")

    resolution = int(asset.get_editor_property("resolution"))
    if resolution != EXPECTED_RESOLUTION:
        raise RuntimeError(
            f"Imported asset resolution is {resolution}, expected {EXPECTED_RESOLUTION}"
        )
    if abs(float(asset.get_editor_property("min_height_cm")) - EXPECTED_MIN_HEIGHT_CM) > 0.01:
        raise RuntimeError("Imported asset minimum height decode is not -30000 cm")
    if abs(float(asset.get_editor_property("max_height_cm")) - EXPECTED_MAX_HEIGHT_CM) > 0.01:
        raise RuntimeError("Imported asset maximum height decode is not 30000 cm")

    expected_samples = EXPECTED_RESOLUTION * EXPECTED_RESOLUTION
    property_groups = (
        ("height", HEIGHT_FACE_PROPERTIES),
        ("land", LAND_FACE_PROPERTIES),
        ("biome", BIOME_FACE_PROPERTIES),
    )
    for channel, property_names in property_groups:
        for property_name in property_names:
            sample_count = len(asset.get_editor_property(property_name))
            if sample_count != expected_samples:
                raise RuntimeError(
                    f"Imported {channel} property {property_name} has {sample_count} samples, "
                    f"expected {expected_samples}"
                )
    return resolution, expected_samples


def main() -> None:
    """Authenticate, import, and post-verify the isolated Unreal data asset."""

    import unreal

    project_dir = Path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
    )
    source_dir = project_dir / SOURCE_RELATIVE
    manifest_path = source_dir / "RED_MacroWorld.json"
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    authenticated_dataset = authenticate_face_dataset(source_dir, manifest)
    unreal.log(
        "RED_FUSED_SOURCE_AUTHENTICATED "
        f"rasters=24 dataset_sha256={authenticated_dataset}"
    )

    result = unreal.RedMMOEditorTools.import_planet_gen_macro_heightfield(
        SOURCE_RELATIVE,
        ASSET_PACKAGE,
    )
    unreal.log(f"RED_FUSED_IMPORT_RESULT {result}")
    if not str(result).startswith("OK:"):
        raise RuntimeError(f"Fused macro-heightfield import failed: {result}")

    asset = unreal.load_asset(ASSET_PACKAGE)
    resolution, expected_samples = verify_imported_asset(asset)

    asset_filename = (
        Path(
            unreal.Paths.convert_relative_path_to_full(
                unreal.Paths.project_content_dir()
            )
        )
        / "RedMMO"
        / "Environment"
        / "DA_RED_Planet50Km_FusedHeightfield.uasset"
    )
    if not asset_filename.is_file():
        raise RuntimeError(f"Imported asset package was not persisted: {asset_filename}")

    unreal.log(
        "RED_FUSED_MACRO_IMPORT_READY "
        f"asset={ASSET_PACKAGE} resolution={resolution} height_faces=6 "
        f"land_faces=6 biome_faces=6 samples_per_face={expected_samples} "
        f"asset_sha256={sha256_file(asset_filename)}"
    )


if __name__ == "__main__":
    main()
