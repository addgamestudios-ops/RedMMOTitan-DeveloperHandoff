"""Generate RED tangent authoring rasters and bake seam-safe cube faces.

The 27 square rasters are editable source art, not gameplay or streaming
boundaries.  They are sampled from the original analytic RED blockout, then
read back from disk and composited into the six complete PlanetGen cube faces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

import numpy as np
from PIL import Image

try:  # Support both ``python Tools/foo.py`` and ``import Tools.foo``.
    from . import generate_planet_macro_faces as macro_faces
    from . import planet_patch_compositor as compositor
except ImportError:
    import generate_planet_macro_faces as macro_faces
    import planet_patch_compositor as compositor


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUTHORING_ROOT = REPOSITORY_ROOT / "SourceArt" / "Planet50Km" / "AuthoringPatches"
MACRO_FACE_ROOT = REPOSITORY_ROOT / "SourceArt" / "Planet50Km" / "MacroFacesFromPatches"
DEFAULT_PROFILE_PATH = AUTHORING_ROOT / "RED_PatchProfile.json"

DEFAULT_PATCH_RESOLUTION = 257
DEFAULT_FACE_RESOLUTION = 257
PATCH_MANIFEST_NAME = "RED_PatchRasters.json"
FACE_MANIFEST_NAME = "RED_MacroWorld.json"
PATCH_MANIFEST_SCHEMA = "redmmotitan.tangent_patch_rasters.v1"
FACE_MANIFEST_SCHEMA = "redmmotitan.macro_planet_faces.v1"
REVISION_BACKUP_DIRECTORY = "RevisionBackups"
UINT8_MAX = 255.0
UINT16_MAX = 65535.0
_INSIDE_TOLERANCE = 1.0e-12
_WEIGHT_EPSILON = 1.0e-15


def _validate_resolution(resolution: int, label: str, maximum: int = 2049) -> int:
    if isinstance(resolution, bool) or not isinstance(resolution, (int, np.integer)):
        raise ValueError(f"{label} must be an odd integer in [3, {maximum}]")
    value = int(resolution)
    if value < 3 or value > maximum or value % 2 == 0:
        raise ValueError(f"{label} must be an odd integer in [3, {maximum}]")
    return value


def _require_output_scope(path: Path, allowed_root: Path, label: str) -> Path:
    resolved = path.resolve()
    root = allowed_root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay under {root}") from exc
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _dataset_sha256(records: Iterable[tuple[str, str]]) -> str:
    """Hash a deterministic filename/hash index rather than path metadata."""
    digest = hashlib.sha256()
    for filename, file_hash in sorted(records):
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_bytes(value)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _profile_display_path(profile_path: Path) -> str:
    try:
        return profile_path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return profile_path.name


def _height_limits(profile: dict[str, Any]) -> tuple[float, float]:
    minimum = float(profile["height_min_cm"])
    maximum = float(profile["height_max_cm"])
    if not math.isfinite(minimum) or not math.isfinite(maximum) or maximum <= minimum:
        raise ValueError("profile height range must be finite and ordered")
    return minimum, maximum


def encode_height(height_cm: np.ndarray, profile: dict[str, Any]) -> np.ndarray:
    minimum, maximum = _height_limits(profile)
    normalized = np.clip((height_cm - minimum) / (maximum - minimum), 0.0, 1.0)
    return np.rint(normalized * UINT16_MAX).astype(np.uint16)


def decode_height(encoded: np.ndarray, profile: dict[str, Any]) -> np.ndarray:
    minimum, maximum = _height_limits(profile)
    return minimum + (np.asarray(encoded, dtype=np.float64) / UINT16_MAX) * (maximum - minimum)


def _height_png_name(patch: dict[str, Any]) -> str:
    raw_name = Path(str(patch["height_file"]))
    return f"{raw_name.stem}_16.png"


def _patch_file_specs(patch: dict[str, Any]) -> tuple[tuple[str, str, str], ...]:
    """Return the canonical role/name/encoding contract for one source patch."""
    return (
        ("height_raw", str(patch["height_file"]), "little-endian uint16 row-major"),
        ("height_png", _height_png_name(patch), "PNG grayscale uint16"),
        ("land", str(patch["land_file"]), "PNG L8"),
        ("biomes", str(patch["biome_file"]), "PNG RGBA8"),
        (
            "authority",
            str(patch["authority_mask_file"]),
            "PNG L8 protected authoring ownership",
        ),
    )


def _expected_patch_filenames(profile: dict[str, Any]) -> list[str]:
    filenames: list[str] = []
    for expected_id, patch in enumerate(
        sorted(profile["patches"], key=lambda item: int(item["patch_id"]))
    ):
        if int(patch["patch_id"]) != expected_id:
            raise ValueError("patch IDs must be ordered 0..26")
        for _, filename, _ in _patch_file_specs(patch):
            if Path(filename).name != filename:
                raise ValueError(
                    f"patch {expected_id} raster filenames must be plain basenames"
                )
            filenames.append(filename)
    if len(filenames) != compositor.PATCH_COUNT * 5 or len(set(filenames)) != len(
        filenames
    ):
        raise ValueError("profile patch raster filenames must be globally unique")
    return filenames


def _patch_directions(
    patch: dict[str, Any], resolution: int, radius_cm: float
) -> np.ndarray:
    """Vectorized equivalent of compositor.patch_uv_to_direction."""
    coordinate = np.linspace(0.0, 1.0, resolution, dtype=np.float64)
    u, v = np.meshgrid(coordinate, coordinate)
    support_width = float(patch["support_width_cm"])
    local_x = (u - 0.5) * support_width
    local_y = (0.5 - v) * support_width

    up = np.asarray(patch["center_direction"], dtype=np.float64)
    up /= np.linalg.norm(up)
    axis_x, axis_y = compositor.tangent_frame(
        up, float(patch.get("heading_deg", 0.0))
    )
    tangent = local_x[..., None] * axis_x + local_y[..., None] * axis_y
    arc_length = np.linalg.norm(tangent, axis=-1)
    safe_length = np.where(arc_length > 1.0e-12, arc_length, 1.0)
    angle = arc_length / float(radius_cm)
    direction = (
        up * np.cos(angle)[..., None]
        + (tangent / safe_length[..., None]) * np.sin(angle)[..., None]
    )
    direction[arc_length <= 1.0e-12] = up
    return direction / np.linalg.norm(direction, axis=-1, keepdims=True)


def _blank_authority(resolution: int) -> np.ndarray:
    """The analytic blockout claims no protected handcrafted ownership."""
    return np.zeros((resolution, resolution), dtype=np.uint8)


def _save_height_pair(output: Path, raw_name: str, png_name: str, encoded: np.ndarray) -> None:
    encoded.astype("<u2", copy=False).tofile(output / raw_name)
    Image.fromarray(encoded).save(output / png_name, format="PNG")


def _save_l8(path: Path, values: np.ndarray) -> None:
    Image.fromarray(np.asarray(values, dtype=np.uint8), mode="L").save(path, format="PNG")


def _save_rgba8(path: Path, values: np.ndarray) -> None:
    Image.fromarray(np.asarray(values, dtype=np.uint8), mode="RGBA").save(path, format="PNG")


def _build_patch_manifest(
    profile: dict[str, Any],
    output: Path,
    resolution: int,
    profile_path: Path,
    *,
    purpose: str,
    source_mode: str,
    extra_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Index the exact persisted raster bytes using the canonical per-patch roles."""
    raster_hashes: list[tuple[str, str]] = []
    patch_records: list[dict[str, Any]] = []
    patches = sorted(profile["patches"], key=lambda item: int(item["patch_id"]))
    if len(patches) != compositor.PATCH_COUNT:
        raise ValueError(f"profile must contain exactly {compositor.PATCH_COUNT} patches")
    for expected_id, patch in enumerate(patches):
        patch_id = int(patch["patch_id"])
        if patch_id != expected_id:
            raise ValueError("patch IDs must be ordered 0..26")
        files: dict[str, dict[str, Any]] = {}
        for role, filename, encoding in _patch_file_specs(patch):
            if Path(filename).name != filename:
                raise ValueError(
                    f"patch {patch_id} raster filenames must be plain basenames"
                )
            file_hash = _sha256(output / filename)
            raster_hashes.append((filename, file_hash))
            files[role] = {
                "file": filename,
                "encoding": encoding,
                "sha256": file_hash,
            }
        patch_records.append(
            {
                "patch_id": patch_id,
                "name": patch["name"],
                "stable_seed": int(patch["stable_seed"]),
                "files": files,
            }
        )

    manifest: dict[str, Any] = {
        "schema": PATCH_MANIFEST_SCHEMA,
        "purpose": purpose,
        "source_mode": source_mode,
        "profile_file": _profile_display_path(Path(profile_path)),
        "profile_sha256": _sha256(Path(profile_path)),
        "patch_count": len(patch_records),
        "resolution": resolution,
        "raster_orientation": "U east; V south; row 0 is local-north support edge",
        "height_min_cm": float(profile["height_min_cm"]),
        "height_max_cm": float(profile["height_max_cm"]),
        "sea_height_cm": float(profile["sea_height_cm"]),
        "authority_semantics": (
            "protected handcrafted blend ownership; this is not a collision, streaming, "
            "or PCG reservation boundary"
        ),
        "raster_dataset_sha256": _dataset_sha256(raster_hashes),
        "patches": patch_records,
    }
    if extra_provenance:
        manifest["provenance"] = extra_provenance
    _write_json(output / PATCH_MANIFEST_NAME, manifest)
    return manifest


def generate_patch_rasters(
    profile: dict[str, Any],
    output: Path = AUTHORING_ROOT,
    resolution: int = DEFAULT_PATCH_RESOLUTION,
    profile_path: Path = DEFAULT_PROFILE_PATH,
) -> dict[str, Any]:
    """Write exactly one height/land/biome/authority source set per patch."""
    resolution = _validate_resolution(resolution, "patch resolution")
    output = _require_output_scope(Path(output), AUTHORING_ROOT, "patch output")
    output.mkdir(parents=True, exist_ok=True)
    radius_cm = float(profile["planet_radius_cm"])
    sea_height_cm = float(profile["sea_height_cm"])
    patches = sorted(profile["patches"], key=lambda item: int(item["patch_id"]))
    if len(patches) != compositor.PATCH_COUNT:
        raise ValueError(f"profile must contain exactly {compositor.PATCH_COUNT} patches")

    for expected_id, patch in enumerate(patches):
        patch_id = int(patch["patch_id"])
        if patch_id != expected_id:
            raise ValueError("patch IDs must be ordered 0..26")

        directions = _patch_directions(patch, resolution, radius_cm)
        height_cm, biome_masks = macro_faces.evaluate_world(directions)
        encoded_height = encode_height(height_cm, profile)
        land = np.where(height_cm >= sea_height_cm, 255, 0).astype(np.uint8)
        biomes = np.rint(np.clip(biome_masks, 0.0, 1.0) * UINT8_MAX).astype(np.uint8)
        authority = _blank_authority(resolution)

        specs = _patch_file_specs(patch)
        names = {role: filename for role, filename, _ in specs}
        if any(Path(name).name != name for name in names.values()):
            raise ValueError(f"patch {patch_id} raster filenames must be plain basenames")

        _save_height_pair(
            output, names["height_raw"], names["height_png"], encoded_height
        )
        _save_l8(output / names["land"], land)
        _save_rgba8(output / names["biomes"], biomes)
        _save_l8(output / names["authority"], authority)

    return _build_patch_manifest(
        profile,
        output,
        resolution,
        Path(profile_path),
        purpose="quantized tangent-local source art sampled from the original RED analytic blockout",
        source_mode="analytic_blockout",
    )


def _read_png(path: Path, expected_mode: str, expected_shape: tuple[int, ...]) -> np.ndarray:
    with Image.open(path) as image:
        image.load()
        if image.mode != expected_mode:
            raise ValueError(f"{path.name} must be {expected_mode}, got {image.mode}")
        values = np.asarray(image).copy()
    if values.shape != expected_shape:
        raise ValueError(f"{path.name} must have shape {expected_shape}, got {values.shape}")
    return values


def _read_height_png(path: Path, expected_shape: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as image:
        image.load()
        if image.mode not in ("I;16", "I;16L"):
            raise ValueError(f"{path.name} must be grayscale uint16, got {image.mode}")
        values = np.asarray(image, dtype=np.uint16).copy()
    if values.shape != expected_shape:
        raise ValueError(f"{path.name} must have shape {expected_shape}, got {values.shape}")
    return values


def load_patch_rasters(
    profile: dict[str, Any], output: Path, resolution: int
) -> list[dict[str, Any]]:
    """Load and strictly validate the quantized files used by the face bake."""
    resolution = _validate_resolution(resolution, "patch resolution")
    output = _require_output_scope(Path(output), AUTHORING_ROOT, "patch output")
    expected_pixels = resolution * resolution
    loaded: list[dict[str, Any]] = []
    for patch in sorted(profile["patches"], key=lambda item: int(item["patch_id"])):
        raw_path = output / str(patch["height_file"])
        raw_height = np.fromfile(raw_path, dtype="<u2")
        if raw_height.size != expected_pixels:
            raise ValueError(
                f"{raw_path.name} must contain {expected_pixels} uint16 samples, got {raw_height.size}"
            )
        raw_height = raw_height.astype(np.uint16, copy=False).reshape((resolution, resolution))

        png_path = output / _height_png_name(patch)
        png_height = _read_height_png(png_path, (resolution, resolution))
        if png_height.shape != raw_height.shape or not np.array_equal(png_height, raw_height):
            raise ValueError(f"{png_path.name} does not match authoritative {raw_path.name}")

        loaded.append(
            {
                "patch": patch,
                "height": raw_height,
                "land": _read_png(
                    output / str(patch["land_file"]), "L", (resolution, resolution)
                ),
                "biomes": _read_png(
                    output / str(patch["biome_file"]),
                    "RGBA",
                    (resolution, resolution, 4),
                ),
                "authority": _read_png(
                    output / str(patch["authority_mask_file"]),
                    "L",
                    (resolution, resolution),
                ),
            }
        )
    if len(loaded) != compositor.PATCH_COUNT:
        raise ValueError(f"expected {compositor.PATCH_COUNT} loaded patches, got {len(loaded)}")
    return loaded


def _load_patch_manifest_contract(
    profile: dict[str, Any],
    output: Path,
    profile_path: Path,
    expected_resolution: int | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate manifest structure without requiring unaccepted edits to match hashes."""
    manifest_path = output / PATCH_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read source patch manifest {manifest_path}: {exc}") from exc
    if manifest.get("schema") != PATCH_MANIFEST_SCHEMA:
        raise ValueError(f"{PATCH_MANIFEST_NAME} has an unsupported schema")
    if manifest.get("patch_count") != compositor.PATCH_COUNT:
        raise ValueError(f"{PATCH_MANIFEST_NAME} must describe exactly 27 patches")
    resolution = _validate_resolution(manifest.get("resolution"), "manifest patch resolution")
    if expected_resolution is not None and resolution != expected_resolution:
        raise ValueError(
            f"{PATCH_MANIFEST_NAME} resolution {resolution} does not match {expected_resolution}"
        )
    current_profile_hash = _sha256(profile_path)
    if manifest.get("profile_sha256") != current_profile_hash:
        raise ValueError(f"{PATCH_MANIFEST_NAME} does not match the current profile bytes")

    declared_hashes: dict[str, str] = {}
    records = manifest.get("patches")
    patches = sorted(profile["patches"], key=lambda item: int(item["patch_id"]))
    if not isinstance(records, list) or len(records) != compositor.PATCH_COUNT:
        raise ValueError(f"{PATCH_MANIFEST_NAME} has malformed patch records")
    if len(patches) != compositor.PATCH_COUNT:
        raise ValueError(f"profile must contain exactly {compositor.PATCH_COUNT} patches")
    for expected_id, (record, patch) in enumerate(zip(records, patches, strict=True)):
        if not isinstance(record, dict) or record.get("patch_id") != expected_id:
            raise ValueError(f"{PATCH_MANIFEST_NAME} patch records must be ordered 0..26")
        if int(patch["patch_id"]) != expected_id:
            raise ValueError("profile patch IDs must be ordered 0..26")
        if record.get("name") != patch["name"] or record.get("stable_seed") != int(
            patch["stable_seed"]
        ):
            raise ValueError(
                f"{PATCH_MANIFEST_NAME} patch {expected_id} identity does not match the profile"
            )
        files = record.get("files")
        canonical_specs = _patch_file_specs(patch)
        if not isinstance(files, dict) or set(files) != {
            role for role, _, _ in canonical_specs
        }:
            raise ValueError(f"{PATCH_MANIFEST_NAME} patch {expected_id} has malformed files")
        for role, canonical_filename, canonical_encoding in canonical_specs:
            entry = files.get(role)
            if not isinstance(entry, dict):
                raise ValueError(
                    f"{PATCH_MANIFEST_NAME} patch {expected_id} is missing {role}"
                )
            filename = entry.get("file")
            encoding = entry.get("encoding")
            file_hash = entry.get("sha256")
            if (
                filename != canonical_filename
                or encoding != canonical_encoding
                or not isinstance(file_hash, str)
                or len(file_hash) != 64
                or any(character not in "0123456789abcdefABCDEF" for character in file_hash)
                or filename in declared_hashes
            ):
                raise ValueError(
                    f"{PATCH_MANIFEST_NAME} patch {expected_id} has noncanonical {role} provenance"
                )
            declared_hashes[filename] = file_hash.upper()

    expected_names = set(_expected_patch_filenames(profile))
    if set(declared_hashes) != expected_names:
        raise ValueError(f"{PATCH_MANIFEST_NAME} raster filenames do not match the profile")
    declared_dataset_hash = _dataset_sha256(declared_hashes.items())
    if manifest.get("raster_dataset_sha256") != declared_dataset_hash:
        raise ValueError(
            f"{PATCH_MANIFEST_NAME} declared dataset hash does not match its file index"
        )
    return manifest, declared_hashes


def _validate_patch_manifest_inputs(
    profile: dict[str, Any], output: Path, resolution: int, profile_path: Path
) -> dict[str, str]:
    """Prove that the manifest describes the exact raster bytes to be baked."""
    manifest, declared_hashes = _load_patch_manifest_contract(
        profile, output, profile_path, resolution
    )

    actual_hashes: list[tuple[str, str]] = []
    for filename in sorted(declared_hashes):
        actual_hash = _sha256(output / filename)
        if actual_hash != declared_hashes[filename]:
            raise ValueError(f"source raster hash mismatch: {filename}")
        actual_hashes.append((filename, actual_hash))
    dataset_hash = _dataset_sha256(actual_hashes)
    if manifest.get("raster_dataset_sha256") != dataset_hash:
        raise ValueError(f"{PATCH_MANIFEST_NAME} dataset hash does not match its rasters")
    return {
        "manifest_sha256": _sha256(output / PATCH_MANIFEST_NAME),
        "raster_dataset_sha256": dataset_hash,
    }


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".restore", dir=destination.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        shutil.copy2(source, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _validate_revision_backup(
    backup: Path, expected_label: str | None = None
) -> tuple[dict[str, Any], dict[str, str]]:
    metadata_path = backup / "REVISION.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read revision backup {backup}: {exc}") from exc
    if metadata.get("schema") != "redmmotitan.authoring_revision_backup.v1":
        raise RuntimeError(f"unsupported revision backup schema in {backup}")
    label = metadata.get("label")
    if not isinstance(label, str) or not label:
        raise RuntimeError(f"revision backup has an invalid label in {backup}")
    if expected_label is not None and label != expected_label:
        raise RuntimeError(
            f"revision backup {backup.name} has label {label}, expected {expected_label}"
        )
    records = metadata.get("files")
    if not isinstance(records, list):
        raise RuntimeError(f"revision backup has malformed file records in {backup}")
    hashes: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError(f"revision backup has malformed file records in {backup}")
        filename = record.get("file")
        expected_hash = record.get("sha256")
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or filename in hashes
            or not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or any(
                character not in "0123456789abcdefABCDEF"
                for character in expected_hash
            )
        ):
            raise RuntimeError(f"revision backup has malformed provenance in {backup}")
        source = backup / filename
        actual_hash = _sha256(source)
        if actual_hash != expected_hash.upper():
            raise RuntimeError(f"revision backup hash mismatch: {source}")
        hashes[filename] = actual_hash
    dataset_hash = _dataset_sha256(hashes.items())
    if metadata.get("snapshot_dataset_sha256") != dataset_hash:
        raise RuntimeError(f"revision backup dataset hash mismatch in {backup}")
    if backup.name != f"{label}_{dataset_hash}":
        raise RuntimeError(f"revision backup directory name is not content-addressed: {backup}")
    return metadata, hashes


def _create_revision_backup(
    root: Path, filenames: Iterable[str], label: str
) -> Path:
    """Create a content-addressed pre-transaction snapshot under the source tree."""
    root = Path(root).resolve()
    ordered = sorted(set(filenames))
    hashes: list[tuple[str, str]] = []
    for filename in ordered:
        if Path(filename).name != filename:
            raise ValueError("revision backup only accepts plain filenames")
        source = root / filename
        if not source.is_file():
            raise ValueError(f"cannot snapshot missing file: {source}")
        hashes.append((filename, _sha256(source)))
    snapshot_hash = _dataset_sha256(hashes)
    backup_root = root / REVISION_BACKUP_DIRECTORY
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_root = backup_root.resolve()
    try:
        backup_root.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"revision backup directory escapes source root: {backup_root}") from exc
    destination = backup_root / f"{label}_{snapshot_hash}"
    if destination.exists():
        _, existing_hashes = _validate_revision_backup(destination, label)
        if existing_hashes != dict(hashes):
            raise RuntimeError(f"revision backup collision for {destination}")
        return destination

    staging = Path(
        tempfile.mkdtemp(prefix=f".{label}_{snapshot_hash}.", dir=backup_root)
    )
    try:
        for filename, _ in hashes:
            shutil.copy2(root / filename, staging / filename)
        _write_json(
            staging / "REVISION.json",
            {
                "schema": "redmmotitan.authoring_revision_backup.v1",
                "label": label,
                "snapshot_dataset_sha256": snapshot_hash,
                "files": [
                    {"file": filename, "sha256": file_hash}
                    for filename, file_hash in hashes
                ],
            },
        )
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination


def _restore_revision_backup(root: Path, backup: Path) -> set[str]:
    metadata, _ = _validate_revision_backup(backup)
    restored: set[str] = set()
    for record in metadata.get("files", []):
        filename = record.get("file")
        expected_hash = record.get("sha256")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise RuntimeError(f"malformed revision filename in {backup}")
        source = backup / filename
        _atomic_copy(source, Path(root) / filename)
        restored.add(filename)
    return restored


def _rollback_files(destination: Path, backup: Path, filenames: Iterable[str]) -> None:
    restored = _restore_revision_backup(destination, backup)
    for filename in filenames:
        if filename not in restored:
            (destination / filename).unlink(missing_ok=True)


def _publish_staged_files(
    staging: Path,
    destination: Path,
    filenames: Iterable[str],
    commit_marker: str,
    backup: Path,
) -> None:
    """Publish derived files first and the manifest commit marker last, with rollback."""
    ordered = sorted(set(filenames))
    if commit_marker in ordered:
        ordered.remove(commit_marker)
    try:
        for filename in ordered:
            source = staging / filename
            if not source.is_file():
                raise RuntimeError(f"staged file is missing: {source}")
            os.replace(source, destination / filename)
        marker_source = staging / commit_marker
        if not marker_source.is_file():
            raise RuntimeError(f"staged commit marker is missing: {marker_source}")
        os.replace(marker_source, destination / commit_marker)
    except Exception:
        _rollback_files(destination, backup, [*ordered, commit_marker])
        raise


def _read_raw_height(path: Path, resolution: int) -> np.ndarray:
    expected_pixels = resolution * resolution
    values = np.fromfile(path, dtype="<u2")
    if values.size != expected_pixels:
        raise ValueError(
            f"{path.name} must contain {expected_pixels} uint16 samples, got {values.size}"
        )
    return values.astype(np.uint16, copy=False).reshape((resolution, resolution))


def accept_authored_edits(
    profile: dict[str, Any],
    output: Path = AUTHORING_ROOT,
    profile_path: Path = DEFAULT_PROFILE_PATH,
    resolution: int | None = None,
    height_source: str = "auto",
) -> dict[str, Any]:
    """Accept validated manual PNG/mask edits without regenerating analytic sources.

    ``auto`` accepts a changed height PNG when the derived R16 is unchanged. A raw-only
    edit or conflicting pair fails closed unless the caller explicitly selects ``png``
    or ``r16``. All unique source bytes are snapshotted before derived companions or the
    manifest are replaced.
    """
    output = _require_output_scope(Path(output), AUTHORING_ROOT, "patch output")
    profile_path = Path(profile_path).resolve()
    if height_source not in {"auto", "png", "r16"}:
        raise ValueError("height source must be one of: auto, png, r16")
    parent_manifest, declared_hashes = _load_patch_manifest_contract(
        profile, output, profile_path, resolution
    )
    manifest_resolution = _validate_resolution(
        parent_manifest["resolution"], "manifest patch resolution"
    )
    filenames = _expected_patch_filenames(profile)
    parent_manifest_path = output / PATCH_MANIFEST_NAME
    parent_manifest_hash = _sha256(parent_manifest_path)
    initial_hashes = {filename: _sha256(output / filename) for filename in filenames}

    height_decisions: list[dict[str, Any]] = []
    normalized_heights: dict[int, tuple[str, np.ndarray]] = {}
    patches = sorted(profile["patches"], key=lambda item: int(item["patch_id"]))
    for patch in patches:
        patch_id = int(patch["patch_id"])
        raw_name = str(patch["height_file"])
        png_name = _height_png_name(patch)
        raw_height = _read_raw_height(output / raw_name, manifest_resolution)
        png_height = _read_height_png(
            output / png_name, (manifest_resolution, manifest_resolution)
        )
        # Validate every authoritative mask before creating any stage or backup.
        _read_png(
            output / str(patch["land_file"]),
            "L",
            (manifest_resolution, manifest_resolution),
        )
        _read_png(
            output / str(patch["biome_file"]),
            "RGBA",
            (manifest_resolution, manifest_resolution, 4),
        )
        _read_png(
            output / str(patch["authority_mask_file"]),
            "L",
            (manifest_resolution, manifest_resolution),
        )

        if np.array_equal(raw_height, png_height):
            continue
        raw_changed = initial_hashes[raw_name] != declared_hashes[raw_name]
        png_changed = initial_hashes[png_name] != declared_hashes[png_name]
        selected_source = height_source
        if selected_source == "auto":
            if png_changed and not raw_changed:
                selected_source = "png"
            else:
                raise ValueError(
                    f"patch {patch_id} height R16/PNG conflict; preserve both files and rerun "
                    "accept-edits with --height-source png or --height-source r16"
                )
        canonical = png_height if selected_source == "png" else raw_height
        normalized_heights[patch_id] = (selected_source, canonical)
        height_decisions.append(
            {
                "patch_id": patch_id,
                "source": selected_source,
                "raw_changed_from_parent": raw_changed,
                "png_changed_from_parent": png_changed,
            }
        )

    has_file_edits = any(
        initial_hashes[filename] != declared_hashes[filename] for filename in filenames
    )
    if not has_file_edits and not normalized_heights:
        _validate_patch_manifest_inputs(
            profile, output, manifest_resolution, profile_path
        )
        load_patch_rasters(profile, output, manifest_resolution)
        return parent_manifest

    backup = _create_revision_backup(
        output, [*filenames, PATCH_MANIFEST_NAME], "PRE_ACCEPT"
    )
    with tempfile.TemporaryDirectory(prefix=".accept_stage_", dir=output) as stage_name:
        staging = Path(stage_name)
        for filename in filenames:
            shutil.copy2(output / filename, staging / filename)
        for patch in patches:
            patch_id = int(patch["patch_id"])
            decision = normalized_heights.get(patch_id)
            if decision is None:
                continue
            selected_source, canonical = decision
            raw_name = str(patch["height_file"])
            png_name = _height_png_name(patch)
            if selected_source == "png":
                canonical.astype("<u2", copy=False).tofile(staging / raw_name)
            else:
                Image.fromarray(canonical).save(staging / png_name, format="PNG")

        # Validate normalized modes and equality before constructing accepted provenance.
        load_patch_rasters(profile, staging, manifest_resolution)
        staged_hashes = {filename: _sha256(staging / filename) for filename in filenames}
        changes = [
            {
                "file": filename,
                "parent_sha256": declared_hashes[filename],
                "accepted_sha256": staged_hashes[filename],
            }
            for filename in sorted(filenames)
            if staged_hashes[filename] != declared_hashes[filename]
        ]
        manifest = _build_patch_manifest(
            profile,
            staging,
            manifest_resolution,
            profile_path,
            purpose="accepted editable tangent-local source art for the RED fused planet",
            source_mode="accepted_authored_edits",
            extra_provenance={
                "parent_manifest_sha256": parent_manifest_hash,
                "parent_raster_dataset_sha256": parent_manifest[
                    "raster_dataset_sha256"
                ],
                "pre_accept_snapshot": backup.relative_to(REPOSITORY_ROOT).as_posix(),
                "height_conflict_policy": height_source,
                "height_resolutions": height_decisions,
                "changed_files": changes,
            },
        )
        _validate_patch_manifest_inputs(
            profile, staging, manifest_resolution, profile_path
        )

        # Detect edits made while validation/staging was running.
        for filename, initial_hash in initial_hashes.items():
            if _sha256(output / filename) != initial_hash:
                raise RuntimeError(f"source changed during accept-edits: {filename}")
        if _sha256(parent_manifest_path) != parent_manifest_hash:
            raise RuntimeError("source manifest changed during accept-edits")

        publish_names = [
            filename
            for filename in filenames
            if staged_hashes[filename] != initial_hashes[filename]
        ]
        _publish_staged_files(
            staging,
            output,
            [*publish_names, PATCH_MANIFEST_NAME],
            PATCH_MANIFEST_NAME,
            backup,
        )

    try:
        _validate_patch_manifest_inputs(
            profile, output, manifest_resolution, profile_path
        )
        load_patch_rasters(profile, output, manifest_resolution)
    except Exception:
        _rollback_files(output, backup, [*filenames, PATCH_MANIFEST_NAME])
        raise
    return manifest


def snapshot_accepted_sources(
    profile: dict[str, Any],
    output: Path = AUTHORING_ROOT,
    profile_path: Path = DEFAULT_PROFILE_PATH,
) -> Path:
    """Capture a content-addressed approved baseline before manual painting starts."""
    output = _require_output_scope(Path(output), AUTHORING_ROOT, "patch output")
    profile_path = Path(profile_path).resolve()
    manifest, _ = _load_patch_manifest_contract(profile, output, profile_path)
    resolution = _validate_resolution(
        manifest["resolution"], "manifest patch resolution"
    )
    _validate_patch_manifest_inputs(profile, output, resolution, profile_path)
    load_patch_rasters(profile, output, resolution)
    return _create_revision_backup(
        output,
        [*_expected_patch_filenames(profile), PATCH_MANIFEST_NAME],
        "APPROVED_SOURCE",
    )


def inspect_approved_source_snapshot(
    profile: dict[str, Any],
    snapshot: Path,
    output: Path = AUTHORING_ROOT,
    profile_path: Path = DEFAULT_PROFILE_PATH,
) -> tuple[Path, dict[str, Any], int]:
    """Authenticate a complete content-addressed snapshot without mutating live sources."""
    output = _require_output_scope(Path(output), AUTHORING_ROOT, "patch output")
    profile_path = Path(profile_path).resolve()
    backup_root = output / REVISION_BACKUP_DIRECTORY
    if not backup_root.is_dir():
        raise ValueError(f"revision backup directory does not exist: {backup_root}")
    backup_root = backup_root.resolve()
    try:
        backup_root.relative_to(output)
    except ValueError as exc:
        raise ValueError(f"revision backup directory escapes source root: {backup_root}") from exc
    candidate = Path(snapshot)
    if not candidate.is_absolute():
        candidate = backup_root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(backup_root)
    except ValueError as exc:
        raise ValueError(f"snapshot must stay under {backup_root}") from exc
    if not candidate.is_dir():
        raise ValueError(f"source snapshot does not exist: {candidate}")

    expected_artifacts = [*_expected_patch_filenames(profile), PATCH_MANIFEST_NAME]
    _, snapshot_hashes = _validate_revision_backup(candidate, "APPROVED_SOURCE")
    if set(snapshot_hashes) != set(expected_artifacts):
        raise ValueError("source snapshot does not contain the complete canonical patch set")
    snapshot_manifest, _ = _load_patch_manifest_contract(
        profile, candidate, profile_path
    )
    resolution = _validate_resolution(
        snapshot_manifest["resolution"], "snapshot patch resolution"
    )
    _validate_patch_manifest_inputs(profile, candidate, resolution, profile_path)
    load_patch_rasters(profile, candidate, resolution)
    return candidate, snapshot_manifest, resolution


def restore_source_snapshot(
    profile: dict[str, Any],
    snapshot: Path,
    output: Path = AUTHORING_ROOT,
    profile_path: Path = DEFAULT_PROFILE_PATH,
    *,
    transaction_backup: Path | None = None,
    transaction_baseline: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Restore one approved source snapshot with a pre-restore rollback transaction."""
    output = _require_output_scope(Path(output), AUTHORING_ROOT, "patch output")
    profile_path = Path(profile_path).resolve()
    candidate, snapshot_manifest, resolution = inspect_approved_source_snapshot(
        profile, snapshot, output, profile_path
    )
    expected_artifacts = [*_expected_patch_filenames(profile), PATCH_MANIFEST_NAME]
    output.mkdir(parents=True, exist_ok=True)
    if (transaction_backup is None) != (transaction_baseline is None):
        raise ValueError(
            "transaction_backup and transaction_baseline must be provided together"
        )
    if transaction_backup is None:
        existing = [
            filename for filename in expected_artifacts if (output / filename).is_file()
        ]
        initial_state = {
            filename: _sha256(output / filename)
            if (output / filename).is_file()
            else None
            for filename in expected_artifacts
        }
        current_backup = _create_revision_backup(output, existing, "PRE_RESTORE")
    else:
        current_backup = Path(transaction_backup).resolve()
        backup_root = (output / REVISION_BACKUP_DIRECTORY).resolve()
        try:
            current_backup.relative_to(backup_root)
        except ValueError as exc:
            raise ValueError(
                f"transaction backup must stay under {backup_root}"
            ) from exc
        initial_state = dict(transaction_baseline or {})
        if set(initial_state) != set(expected_artifacts):
            raise ValueError("transaction baseline does not describe the complete source set")
        _, backup_hashes = _validate_revision_backup(current_backup, "PRE_RESTORE")
        expected_backup_hashes = {
            filename: file_hash
            for filename, file_hash in initial_state.items()
            if file_hash is not None
        }
        if backup_hashes != expected_backup_hashes:
            raise ValueError("transaction backup does not match its supplied source baseline")
    for filename, initial_hash in initial_state.items():
        path = output / filename
        current_hash = _sha256(path) if path.is_file() else None
        if current_hash != initial_hash:
            raise RuntimeError(f"source changed while creating pre-restore backup: {filename}")
    with tempfile.TemporaryDirectory(prefix=".restore_stage_", dir=output) as stage_name:
        staging = Path(stage_name)
        for filename in expected_artifacts:
            shutil.copy2(candidate / filename, staging / filename)
        _validate_patch_manifest_inputs(profile, staging, resolution, profile_path)
        load_patch_rasters(profile, staging, resolution)
        for filename, initial_hash in initial_state.items():
            path = output / filename
            current_hash = _sha256(path) if path.is_file() else None
            if current_hash != initial_hash:
                raise RuntimeError(f"source changed during restore-snapshot: {filename}")
        _publish_staged_files(
            staging,
            output,
            expected_artifacts,
            PATCH_MANIFEST_NAME,
            current_backup,
        )

    try:
        _validate_patch_manifest_inputs(profile, output, resolution, profile_path)
        load_patch_rasters(profile, output, resolution)
    except Exception:
        _rollback_files(output, current_backup, expected_artifacts)
        raise
    return snapshot_manifest


def _project_directions(
    directions: np.ndarray, patch: dict[str, Any], radius_cm: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized equivalent of compositor.direction_to_patch_uv."""
    up = np.asarray(patch["center_direction"], dtype=np.float64)
    up /= np.linalg.norm(up)
    axis_x, axis_y = compositor.tangent_frame(
        up, float(patch.get("heading_deg", 0.0))
    )
    dots = np.clip(np.sum(directions * up, axis=-1), -1.0, 1.0)
    angle = np.arccos(dots)
    tangent = directions - dots[..., None] * up
    tangent_length = np.linalg.norm(tangent, axis=-1)
    safe_length = np.where(tangent_length > 1.0e-15, tangent_length, 1.0)
    tangent_direction = tangent / safe_length[..., None]
    tangent_direction[tangent_length <= 1.0e-15] = axis_x
    arc_length = angle * radius_cm
    local_x = np.sum(tangent_direction * axis_x, axis=-1) * arc_length
    local_y = np.sum(tangent_direction * axis_y, axis=-1) * arc_length
    support_width = float(patch["support_width_cm"])
    u = 0.5 + local_x / support_width
    v = 0.5 - local_y / support_width
    inside = (
        (u >= -_INSIDE_TOLERANCE)
        & (u <= 1.0 + _INSIDE_TOLERANCE)
        & (v >= -_INSIDE_TOLERANCE)
        & (v <= 1.0 + _INSIDE_TOLERANCE)
    )
    return u, v, angle, inside


def _edge_feather_weights(
    u: np.ndarray, v: np.ndarray, inside: np.ndarray, feather_fraction: float
) -> np.ndarray:
    """Vectorized compositor.feather_weight with identical cubic smoothstep."""
    feather = max(1.0e-12, min(0.5, float(feather_fraction)))
    edge_distance = np.minimum.reduce((u, 1.0 - u, v, 1.0 - v))
    alpha = np.clip(edge_distance / feather, 0.0, 1.0)
    return np.where(inside, alpha * alpha * (3.0 - 2.0 * alpha), 0.0)


def _sample_bilinear(
    raster: np.ndarray, u: np.ndarray, v: np.ndarray, active: np.ndarray
) -> np.ndarray:
    """Sample only active pixels and return float64 values in active order."""
    resolution = raster.shape[0]
    grid_x = np.clip(u[active], 0.0, 1.0) * (resolution - 1)
    grid_y = np.clip(v[active], 0.0, 1.0) * (resolution - 1)
    x0 = np.floor(grid_x).astype(np.intp)
    y0 = np.floor(grid_y).astype(np.intp)
    x1 = np.minimum(x0 + 1, resolution - 1)
    y1 = np.minimum(y0 + 1, resolution - 1)
    fraction_x = grid_x - x0
    fraction_y = grid_y - y0

    c00 = np.asarray(raster[y0, x0], dtype=np.float64)
    c10 = np.asarray(raster[y0, x1], dtype=np.float64)
    c01 = np.asarray(raster[y1, x0], dtype=np.float64)
    c11 = np.asarray(raster[y1, x1], dtype=np.float64)
    if raster.ndim == 3:
        fraction_x = fraction_x[:, None]
        fraction_y = fraction_y[:, None]
    row0 = c00 + (c10 - c00) * fraction_x
    row1 = c01 + (c11 - c01) * fraction_x
    return row0 + (row1 - row0) * fraction_y


def _bake_face(
    directions: np.ndarray,
    patch_rasters: list[dict[str, Any]],
    profile: dict[str, Any],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    resolution = directions.shape[0]
    pixel_count = resolution * resolution
    radius_cm = float(profile["planet_radius_cm"])
    weights = np.zeros(pixel_count, dtype=np.float64)
    height_total = np.zeros(pixel_count, dtype=np.float64)
    land_total = np.zeros(pixel_count, dtype=np.float64)
    biome_total = np.zeros((pixel_count, 4), dtype=np.float64)
    contributor_count = np.zeros(pixel_count, dtype=np.uint8)
    flat_directions = directions.reshape((pixel_count, 3))

    # Normalize the angular center kernel against the nearest eligible patch at
    # each sample.  This keeps its strongest contribution at one without
    # changing the edge-feather coverage contract.
    minimum_eligible_delta_squared = np.full(pixel_count, np.inf, dtype=np.float64)
    for source in patch_rasters:
        patch = source["patch"]
        u, v, angular_delta, inside = _project_directions(
            flat_directions, patch, radius_cm
        )
        edge_weight = _edge_feather_weights(
            u, v, inside, float(patch["feather_fraction"])
        )
        eligible = edge_weight > 0.0
        minimum_eligible_delta_squared[eligible] = np.minimum(
            minimum_eligible_delta_squared[eligible],
            np.square(angular_delta[eligible]),
        )

    for source in patch_rasters:
        patch = source["patch"]
        u, v, angular_delta, inside = _project_directions(flat_directions, patch, radius_cm)
        edge_weight = _edge_feather_weights(
            u, v, inside, float(patch["feather_fraction"])
        )
        eligible = edge_weight > 0.0
        if not np.any(eligible):
            continue
        sampled_authority = _sample_bilinear(source["authority"], u, v, eligible)
        authority01 = sampled_authority / UINT8_MAX
        sigma = float(profile["center_sigma_radians"])
        center_exponent = -(
            np.square(angular_delta[eligible])
            - minimum_eligible_delta_squared[eligible]
        ) / (2.0 * sigma * sigma)
        center_kernel = np.exp(center_exponent)
        priority = max(-8, min(8, int(patch.get("priority", 0))))
        ownership_gain = np.exp2(priority + (8.0 * authority01))
        raw_weight = edge_weight[eligible] * center_kernel * ownership_gain
        eligible_indices = np.flatnonzero(eligible)
        positive = raw_weight > 0.0
        if not np.any(positive):
            continue
        active_indices = eligible_indices[positive]
        active = np.zeros_like(eligible)
        active[active_indices] = True
        weight = raw_weight[positive]

        height_sample = _sample_bilinear(source["height"], u, v, active)
        height_cm = decode_height(height_sample, profile)
        height_cm = (
            height_cm * float(patch.get("height_scale", 1.0))
            + float(patch.get("height_bias_cm", 0.0))
        )
        land_sample = _sample_bilinear(source["land"], u, v, active)
        biome_sample = _sample_bilinear(source["biomes"], u, v, active)

        weights[active_indices] += weight
        height_total[active_indices] += height_cm * weight
        land_total[active_indices] += land_sample * weight
        biome_total[active_indices] += biome_sample * weight[:, None]
        contributor_count[active_indices] += 1

    uncovered = weights <= _WEIGHT_EPSILON
    uncovered_count = int(np.count_nonzero(uncovered))
    if uncovered_count:
        first_indices = np.flatnonzero(uncovered)[:8]
        first_coordinates = [
            [int(index % resolution), int(index // resolution)] for index in first_indices
        ]
        raise RuntimeError(
            f"patch bake has {uncovered_count} uncovered face samples; first={first_coordinates}"
        )

    height_cm = (height_total / weights).reshape((resolution, resolution))
    land = np.clip(np.rint(land_total / weights), 0.0, UINT8_MAX).astype(
        np.uint8
    ).reshape((resolution, resolution))
    biomes = np.clip(
        np.rint(biome_total / weights[:, None]), 0.0, UINT8_MAX
    ).astype(np.uint8).reshape((resolution, resolution, 4))
    result = {
        "height": encode_height(height_cm, profile),
        "land": land,
        "biomes": biomes,
    }
    metrics = {
        "uncovered_samples": uncovered_count,
        "minimum_raw_weight_sum": float(np.min(weights)),
        "maximum_raw_weight_sum": float(np.max(weights)),
        "minimum_contributors": int(np.min(contributor_count)),
        "maximum_contributors": int(np.max(contributor_count)),
    }
    return result, metrics


def _border_key(
    normal: tuple[int, int, int],
    axis_u: tuple[int, int, int],
    axis_v: tuple[int, int, int],
    x: int,
    y: int,
    resolution: int,
) -> tuple[int, int, int]:
    """Match FPlanetMacroHeightmap::FuseSharedBorders' exact topology key."""
    span = resolution - 1
    scaled_u = (2 * x) - span
    scaled_v = (2 * y) - span
    return tuple(
        (normal[axis] * span)
        + (axis_u[axis] * scaled_u)
        + (axis_v[axis] * scaled_v)
        for axis in range(3)
    )


def _make_canonical_face_directions(
    resolution: int,
) -> list[tuple[str, tuple[int, int, int], tuple[int, int, int], tuple[int, int, int], np.ndarray]]:
    """Reuse one float64 direction for every duplicated cube edge/corner sample."""
    canonical_boundaries: dict[tuple[int, int, int], np.ndarray] = {}
    result = []
    for name, normal, axis_u, axis_v in macro_faces.FACE_FRAMES:
        directions = macro_faces.make_face_directions(resolution, normal, axis_u, axis_v)
        for y in range(resolution):
            for x in range(resolution):
                if x not in (0, resolution - 1) and y not in (0, resolution - 1):
                    continue
                key = _border_key(normal, axis_u, axis_v, x, y, resolution)
                canonical = canonical_boundaries.get(key)
                if canonical is None:
                    canonical_boundaries[key] = directions[y, x].copy()
                else:
                    directions[y, x] = canonical
        result.append((name, normal, axis_u, axis_v, directions))
    return result


def _validate_encoded_seams(
    faces: list[dict[str, Any]], resolution: int
) -> dict[str, Any]:
    boundary_samples: dict[
        tuple[int, int, int], tuple[int, int, tuple[int, int, int, int]]
    ] = {}
    occurrence_counts: dict[tuple[int, int, int], int] = {}
    comparisons = 0
    max_height_delta = 0
    max_land_delta = 0
    max_biome_delta = 0

    for face in faces:
        for y in range(resolution):
            for x in range(resolution):
                if x not in (0, resolution - 1) and y not in (0, resolution - 1):
                    continue
                key = _border_key(
                    face["normal"], face["axis_u"], face["axis_v"], x, y, resolution
                )
                value = (
                    int(face["rasters"]["height"][y, x]),
                    int(face["rasters"]["land"][y, x]),
                    tuple(int(item) for item in face["rasters"]["biomes"][y, x]),
                )
                occurrence_counts[key] = occurrence_counts.get(key, 0) + 1
                previous = boundary_samples.get(key)
                if previous is None:
                    boundary_samples[key] = value
                    continue
                comparisons += 1
                max_height_delta = max(max_height_delta, abs(previous[0] - value[0]))
                max_land_delta = max(max_land_delta, abs(previous[1] - value[1]))
                max_biome_delta = max(
                    max_biome_delta,
                    max(abs(a - b) for a, b in zip(previous[2], value[2], strict=True)),
                )

    expected_comparisons = (12 * resolution) - 8
    bad_occurrences = [count for count in occurrence_counts.values() if count not in (2, 3)]
    passed = (
        comparisons == expected_comparisons
        and not bad_occurrences
        and max_height_delta == 0
        and max_land_delta == 0
        and max_biome_delta == 0
    )
    result = {
        "shared_boundary_comparisons": comparisons,
        "expected_shared_boundary_comparisons": expected_comparisons,
        "unique_boundary_samples": len(boundary_samples),
        "max_height_delta_u16": max_height_delta,
        "max_land_delta_u8": max_land_delta,
        "max_biome_delta_u8": max_biome_delta,
        "passed": passed,
    }
    if not passed:
        raise RuntimeError(f"encoded cube-face seam validation failed: {result}")
    return result


def _stage_baked_face_artifacts(
    profile: dict[str, Any],
    baked_faces: list[dict[str, Any]],
    coverage_records: list[dict[str, Any]],
    face_resolution: int,
    staging: Path,
    patch_output: Path,
    patch_resolution: int,
    patch_provenance: dict[str, str],
    profile_path: Path,
    profile_sha256: str,
) -> tuple[dict[str, Any], list[str]]:
    """Encode and validate a complete face revision before publishing any file."""
    file_hashes: list[tuple[str, str]] = []
    face_records: list[dict[str, Any]] = []
    artifact_names: list[str] = []
    for face in baked_faces:
        name = face["name"]
        raw_name = f"RED_Height_{name}.r16"
        height_png = f"RED_Height_{name}_16.png"
        land_name = f"RED_Land_{name}.png"
        biome_name = f"RED_Biomes_{name}.png"
        _save_height_pair(staging, raw_name, height_png, face["rasters"]["height"])
        _save_l8(staging / land_name, face["rasters"]["land"])
        _save_rgba8(staging / biome_name, face["rasters"]["biomes"])

        files: dict[str, dict[str, Any]] = {}
        for role, filename, encoding in (
            ("height", height_png, "PNG grayscale uint16"),
            ("raw_height", raw_name, "little-endian uint16 row-major"),
            ("land", land_name, "PNG L8"),
            ("biomes", biome_name, "PNG RGBA8"),
        ):
            file_hash = _sha256(staging / filename)
            artifact_names.append(filename)
            file_hashes.append((filename, file_hash))
            files[role] = {"file": filename, "encoding": encoding, "sha256": file_hash}
        face_records.append(
            {
                "face_index": face["face_index"],
                "name": name,
                "normal": face["normal"],
                "axis_u": face["axis_u"],
                "axis_v": face["axis_v"],
                "height_file": height_png,
                "raw_height_file": raw_name,
                "land_file": land_name,
                "biome_file": biome_name,
                "files": files,
            }
        )

    persisted_faces: list[dict[str, Any]] = []
    expected_pixels = face_resolution * face_resolution
    for face in baked_faces:
        name = face["name"]
        raw_path = staging / f"RED_Height_{name}.r16"
        raw_height = np.fromfile(raw_path, dtype="<u2")
        if raw_height.size != expected_pixels:
            raise RuntimeError(
                f"{raw_path.name} contains {raw_height.size} samples, expected {expected_pixels}"
            )
        raw_height = raw_height.astype(np.uint16, copy=False).reshape(
            (face_resolution, face_resolution)
        )
        png_height = _read_height_png(
            staging / f"RED_Height_{name}_16.png",
            (face_resolution, face_resolution),
        )
        if not np.array_equal(raw_height, png_height):
            raise RuntimeError(f"RED_Height_{name}_16.png does not match {raw_path.name}")
        persisted_faces.append(
            {
                "normal": face["normal"],
                "axis_u": face["axis_u"],
                "axis_v": face["axis_v"],
                "rasters": {
                    "height": raw_height,
                    "land": _read_png(
                        staging / f"RED_Land_{name}.png",
                        "L",
                        (face_resolution, face_resolution),
                    ),
                    "biomes": _read_png(
                        staging / f"RED_Biomes_{name}.png",
                        "RGBA",
                        (face_resolution, face_resolution, 4),
                    ),
                },
            }
        )
    seam_validation = _validate_encoded_seams(persisted_faces, face_resolution)
    seam_validation["validated_from_persisted_files"] = True

    coverage = {
        "face_sample_count": 6 * face_resolution * face_resolution,
        "uncovered_samples": sum(item["uncovered_samples"] for item in coverage_records),
        "minimum_raw_weight_sum": min(
            item["minimum_raw_weight_sum"] for item in coverage_records
        ),
        "maximum_raw_weight_sum": max(
            item["maximum_raw_weight_sum"] for item in coverage_records
        ),
        "minimum_contributors": min(item["minimum_contributors"] for item in coverage_records),
        "maximum_contributors": max(item["maximum_contributors"] for item in coverage_records),
        "passed": all(item["uncovered_samples"] == 0 for item in coverage_records),
        "faces": coverage_records,
    }
    if not coverage["passed"]:
        raise RuntimeError(f"cube-face coverage validation failed: {coverage}")

    patch_manifest_path = patch_output / PATCH_MANIFEST_NAME
    manifest = {
        "schema": FACE_MANIFEST_SCHEMA,
        "purpose": "PlanetGen-compatible cube faces baked only from the 27 quantized source patches",
        "profile_file": _profile_display_path(Path(profile_path)),
        "profile_sha256": profile_sha256,
        "source_patch_manifest": _profile_display_path(patch_manifest_path),
        "source_patch_manifest_sha256": patch_provenance["manifest_sha256"],
        "source_patch_raster_dataset_sha256": patch_provenance[
            "raster_dataset_sha256"
        ],
        "source_patch_resolution": patch_resolution,
        "resolution": face_resolution,
        "height_encoding": "unsigned 16-bit normalized",
        "raw_height_encoding": "little-endian unsigned 16-bit row-major",
        "min_height_cm": float(profile["height_min_cm"]),
        "max_height_cm": float(profile["height_max_cm"]),
        "sea_height_cm": float(profile["sea_height_cm"]),
        "projection": "cube face with tan(uv*pi/4), matching PlanetGen chunk projection",
        "blend": "normalized square-edge smoothstep * angular center kernel * 2^(priority + 8*authority01), stable patch_id accumulation",
        "biome_channels": {
            "r": "desert",
            "g": "temperate",
            "b": "cold_or_mountain",
            "a": "alien",
        },
        "coverage_validation": coverage,
        "seam_validation": seam_validation,
        "raster_dataset_sha256": _dataset_sha256(file_hashes),
        "faces": face_records,
    }
    _write_json(staging / FACE_MANIFEST_NAME, manifest)
    artifact_names.append(FACE_MANIFEST_NAME)
    return manifest, artifact_names


def _validate_face_manifest_outputs(output: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != FACE_MANIFEST_SCHEMA:
        raise RuntimeError("published face manifest has an unsupported schema")
    if not manifest.get("coverage_validation", {}).get("passed"):
        raise RuntimeError("published face manifest reports incomplete coverage")
    if not manifest.get("seam_validation", {}).get("passed"):
        raise RuntimeError("published face manifest reports a seam failure")
    hashes: list[tuple[str, str]] = []
    for expected_index, record in enumerate(manifest.get("faces", [])):
        if record.get("face_index") != expected_index:
            raise RuntimeError("published face records are not in canonical order")
        for entry in record.get("files", {}).values():
            filename = entry.get("file")
            expected_hash = entry.get("sha256")
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise RuntimeError("published face manifest has a malformed filename")
            actual_hash = _sha256(output / filename)
            if actual_hash != expected_hash:
                raise RuntimeError(f"published face hash mismatch: {filename}")
            hashes.append((filename, actual_hash))
    if len(hashes) != 24 or _dataset_sha256(hashes) != manifest.get(
        "raster_dataset_sha256"
    ):
        raise RuntimeError("published face dataset hash is invalid")


def _assert_bake_source_revision(
    patch_output: Path,
    profile_path: Path,
    expected_profile_hash: str,
    expected_manifest_hash: str,
    expected_raster_hashes: dict[str, str],
) -> None:
    if _sha256(profile_path) != expected_profile_hash:
        raise RuntimeError("planet patch profile changed during face bake")
    if _sha256(patch_output / PATCH_MANIFEST_NAME) != expected_manifest_hash:
        raise RuntimeError("source patch manifest changed during face bake")
    for filename, expected_hash in expected_raster_hashes.items():
        if _sha256(patch_output / filename) != expected_hash:
            raise RuntimeError(f"source raster changed during face bake: {filename}")


def bake_macro_faces(
    profile: dict[str, Any],
    patch_output: Path = AUTHORING_ROOT,
    output: Path = MACRO_FACE_ROOT,
    patch_resolution: int = DEFAULT_PATCH_RESOLUTION,
    face_resolution: int = DEFAULT_FACE_RESOLUTION,
    profile_path: Path = DEFAULT_PROFILE_PATH,
) -> dict[str, Any]:
    """Bake the on-disk patch rasters into six PlanetGen-compatible faces."""
    patch_resolution = _validate_resolution(patch_resolution, "patch resolution")
    face_resolution = _validate_resolution(face_resolution, "face resolution", maximum=2047)
    patch_output = _require_output_scope(Path(patch_output), AUTHORING_ROOT, "patch output")
    output = _require_output_scope(Path(output), MACRO_FACE_ROOT, "macro-face output")
    profile_path = Path(profile_path).resolve()
    profile_hash_before_load = _sha256(profile_path)
    pinned_profile = compositor.load_profile(profile_path)
    profile_hash_after_load = _sha256(profile_path)
    if profile_hash_before_load != profile_hash_after_load:
        raise RuntimeError("planet patch profile changed while it was being loaded")
    if profile != pinned_profile:
        raise ValueError("in-memory planet patch profile does not match profile_path")
    profile = pinned_profile
    profile_hash = profile_hash_after_load
    source_manifest_hash = _sha256(patch_output / PATCH_MANIFEST_NAME)
    _, source_raster_hashes = _load_patch_manifest_contract(
        profile, patch_output, profile_path, patch_resolution
    )
    if _sha256(patch_output / PATCH_MANIFEST_NAME) != source_manifest_hash:
        raise RuntimeError("source patch manifest changed while it was being loaded")
    patch_provenance = _validate_patch_manifest_inputs(
        profile, patch_output, patch_resolution, profile_path
    )
    if patch_provenance["manifest_sha256"] != source_manifest_hash:
        raise RuntimeError("source patch manifest changed during face-bake validation")
    patch_rasters = load_patch_rasters(profile, patch_output, patch_resolution)
    _assert_bake_source_revision(
        patch_output,
        profile_path,
        profile_hash,
        source_manifest_hash,
        source_raster_hashes,
    )
    output.mkdir(parents=True, exist_ok=True)

    baked_faces: list[dict[str, Any]] = []
    coverage_records: list[dict[str, Any]] = []
    for index, (name, normal, axis_u, axis_v, directions) in enumerate(
        _make_canonical_face_directions(face_resolution)
    ):
        rasters, coverage = _bake_face(directions, patch_rasters, profile)
        coverage_records.append({"face": name, **coverage})
        baked_faces.append(
            {
                "face_index": index,
                "name": name,
                "normal": normal,
                "axis_u": axis_u,
                "axis_v": axis_v,
                "rasters": rasters,
            }
        )

    # Refuse to persist a known-bad face set, then repeat the same validation
    # from the encoded files below so the manifest proves disk artifacts.
    _validate_encoded_seams(baked_faces, face_resolution)
    _assert_bake_source_revision(
        patch_output,
        profile_path,
        profile_hash,
        source_manifest_hash,
        source_raster_hashes,
    )
    staging = Path(tempfile.mkdtemp(prefix=".face_stage_", dir=output))
    try:
        manifest, artifact_names = _stage_baked_face_artifacts(
            profile,
            baked_faces,
            coverage_records,
            face_resolution,
            staging,
            patch_output,
            patch_resolution,
            patch_provenance,
            profile_path,
            profile_hash,
        )
        # Compare published JSON semantics, not Python tuple/list implementation details.
        manifest = json.loads((staging / FACE_MANIFEST_NAME).read_text(encoding="utf-8"))
        existing = [filename for filename in artifact_names if (output / filename).is_file()]
        initial_state = {
            filename: _sha256(output / filename) if (output / filename).is_file() else None
            for filename in artifact_names
        }
        backup = _create_revision_backup(output, existing, "PRE_FACE_BAKE")
        _assert_bake_source_revision(
            patch_output,
            profile_path,
            profile_hash,
            source_manifest_hash,
            source_raster_hashes,
        )
        for filename, initial_hash in initial_state.items():
            path = output / filename
            current_hash = _sha256(path) if path.is_file() else None
            if current_hash != initial_hash:
                raise RuntimeError(f"face output changed during bake: {filename}")
        _publish_staged_files(
            staging,
            output,
            artifact_names,
            FACE_MANIFEST_NAME,
            backup,
        )
        try:
            published_manifest = json.loads(
                (output / FACE_MANIFEST_NAME).read_text(encoding="utf-8")
            )
            if published_manifest != manifest:
                raise RuntimeError("published face manifest differs from its staged revision")
            _validate_face_manifest_outputs(output, published_manifest)
        except Exception:
            restored = _restore_revision_backup(output, backup)
            for filename in artifact_names:
                if filename not in restored:
                    (output / filename).unlink(missing_ok=True)
            raise
        return published_manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _existing_face_resolution(output: Path) -> int | None:
    manifest_path = Path(output) / FACE_MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read existing face manifest {manifest_path}: {exc}") from exc
    if manifest.get("schema") != FACE_MANIFEST_SCHEMA:
        raise ValueError(f"{FACE_MANIFEST_NAME} has an unsupported schema")
    return _validate_resolution(
        manifest.get("resolution"), "existing face resolution", maximum=2047
    )


def _acceptance_from_manifests(
    patch_manifest: dict[str, Any], face_manifest: dict[str, Any]
) -> dict[str, Any]:
    return {
        "patch_count": patch_manifest["patch_count"],
        "patch_resolution": patch_manifest["resolution"],
        "face_count": len(face_manifest["faces"]),
        "face_resolution": face_manifest["resolution"],
        "uncovered_samples": face_manifest["coverage_validation"]["uncovered_samples"],
        "seam_validation": face_manifest["seam_validation"],
        "patch_dataset_sha256": patch_manifest["raster_dataset_sha256"],
        "face_dataset_sha256": face_manifest["raster_dataset_sha256"],
    }


def _resolve_face_bake_request(
    profile: dict[str, Any], face_output: Path, face_resolution: int | None
) -> tuple[Path, int]:
    """Resolve and validate face-only bake inputs before a source transaction."""
    resolved_face_output = _require_output_scope(
        Path(face_output), MACRO_FACE_ROOT, "macro-face output"
    )
    resolved_face_resolution = face_resolution
    if resolved_face_resolution is None:
        resolved_face_resolution = _existing_face_resolution(resolved_face_output)
    if resolved_face_resolution is None:
        resolved_face_resolution = int(
            profile.get("face_resolution", DEFAULT_FACE_RESOLUTION)
        )
    return resolved_face_output, _validate_resolution(
        resolved_face_resolution, "face resolution", maximum=2047
    )


def _source_artifact_names(profile: dict[str, Any]) -> list[str]:
    return [*_expected_patch_filenames(profile), PATCH_MANIFEST_NAME]


def _source_state(output: Path, artifact_names: Iterable[str]) -> dict[str, str | None]:
    return {
        filename: _sha256(output / filename)
        if (output / filename).is_file()
        else None
        for filename in artifact_names
    }


def _source_state_from_patch_manifest(
    profile: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, str | None]:
    """Build the exact expected commit state without sampling mutable live files."""
    expected_names = set(_expected_patch_filenames(profile))
    raster_hashes: dict[str, str] = {}
    records = manifest.get("patches")
    if not isinstance(records, list):
        raise RuntimeError("accepted source manifest has malformed patch records")
    for record in records:
        files = record.get("files") if isinstance(record, dict) else None
        if not isinstance(files, dict):
            raise RuntimeError("accepted source manifest has malformed file records")
        for entry in files.values():
            filename = entry.get("file") if isinstance(entry, dict) else None
            file_hash = entry.get("sha256") if isinstance(entry, dict) else None
            if (
                not isinstance(filename, str)
                or filename in raster_hashes
                or not isinstance(file_hash, str)
                or len(file_hash) != 64
            ):
                raise RuntimeError("accepted source manifest has malformed file provenance")
            raster_hashes[filename] = file_hash.upper()
    if set(raster_hashes) != expected_names:
        raise RuntimeError("accepted source manifest does not describe the canonical rasters")
    return {
        **raster_hashes,
        PATCH_MANIFEST_NAME: hashlib.sha256(_json_bytes(manifest)).hexdigest().upper(),
    }


def _capture_live_source_backup(
    profile: dict[str, Any], output: Path, label: str
) -> tuple[Path, list[str], dict[str, str | None]]:
    """Capture a consistent live source baseline without accepting later edits."""
    output = _require_output_scope(Path(output), AUTHORING_ROOT, "patch output")
    output.mkdir(parents=True, exist_ok=True)
    artifact_names = _source_artifact_names(profile)
    baseline = _source_state(output, artifact_names)
    existing = [name for name, file_hash in baseline.items() if file_hash is not None]
    backup = _create_revision_backup(output, existing, label)
    if _source_state(output, artifact_names) != baseline:
        raise RuntimeError(f"source changed while creating {label} backup")
    return backup, artifact_names, baseline


def _resolve_recorded_source_backup(
    output: Path,
    manifest: dict[str, Any],
    artifact_names: Iterable[str],
    provenance_key: str,
    expected_label: str,
) -> Path:
    provenance = manifest.get("provenance")
    reference = provenance.get(provenance_key) if isinstance(provenance, dict) else None
    if not isinstance(reference, str) or not reference:
        raise RuntimeError(f"accepted source manifest is missing {provenance_key}")
    candidate = Path(reference)
    if not candidate.is_absolute():
        candidate = REPOSITORY_ROOT / candidate
    candidate = candidate.resolve()
    backup_root = (Path(output) / REVISION_BACKUP_DIRECTORY).resolve()
    try:
        candidate.relative_to(backup_root)
    except ValueError as exc:
        raise RuntimeError(
            f"recorded source backup must stay under {backup_root}: {candidate}"
        ) from exc
    _, hashes = _validate_revision_backup(candidate, expected_label)
    if set(hashes) != set(artifact_names):
        raise RuntimeError("recorded source backup is not a complete source revision")
    return candidate


def _rollback_source_transaction(
    output: Path,
    backup: Path,
    artifact_names: Iterable[str],
    baseline: dict[str, str | None],
    committed: dict[str, str | None],
) -> None:
    """Rollback only our exact commit, preserving any concurrent editor save."""
    artifact_names = list(artifact_names)
    current = _source_state(output, artifact_names)
    if current == baseline:
        return
    if current != committed:
        raise RuntimeError(
            "source changed after the transaction commit; preserving the newer live files "
            "instead of overwriting them during rollback"
        )
    _rollback_files(output, backup, artifact_names)
    if _source_state(output, artifact_names) != baseline:
        raise RuntimeError("source rollback did not restore the exact pre-transaction revision")


def _preflight_bake_request(
    profile_path: Path,
    patch_output: Path,
    face_output: Path,
    patch_resolution: int | None,
    face_resolution: int | None,
) -> tuple[
    dict[str, Any],
    Path,
    Path,
    Path,
    dict[str, Any],
    int,
    int,
]:
    """Resolve every path and resolution that could otherwise fail after a source edit."""
    resolved_profile_path = Path(profile_path).resolve()
    profile = compositor.load_profile(resolved_profile_path)
    resolved_patch_output = _require_output_scope(
        Path(patch_output), AUTHORING_ROOT, "patch output"
    )
    resolved_face_output, resolved_face_resolution = _resolve_face_bake_request(
        profile, Path(face_output), face_resolution
    )
    patch_manifest, _ = _load_patch_manifest_contract(
        profile,
        resolved_patch_output,
        resolved_profile_path,
        patch_resolution,
    )
    resolved_patch_resolution = _validate_resolution(
        patch_manifest["resolution"], "manifest patch resolution"
    )
    return (
        profile,
        resolved_profile_path,
        resolved_patch_output,
        resolved_face_output,
        patch_manifest,
        resolved_patch_resolution,
        resolved_face_resolution,
    )


def accept_edits_and_bake(
    profile_path: Path = DEFAULT_PROFILE_PATH,
    patch_output: Path = AUTHORING_ROOT,
    face_output: Path = MACRO_FACE_ROOT,
    patch_resolution: int | None = None,
    face_resolution: int | None = None,
    height_source: str = "auto",
) -> dict[str, Any]:
    """Preflight, accept source edits, and bake faces as one rollback-safe command."""
    (
        profile,
        profile_path,
        patch_output,
        face_output,
        _,
        resolved_patch_resolution,
        resolved_face_resolution,
    ) = _preflight_bake_request(
        profile_path,
        patch_output,
        face_output,
        patch_resolution,
        face_resolution,
    )
    manifest_path = patch_output / PATCH_MANIFEST_NAME
    manifest_hash_before = _sha256(manifest_path)
    accepted_manifest = accept_authored_edits(
        profile,
        patch_output,
        profile_path,
        resolved_patch_resolution,
        height_source,
    )
    manifest_changed = _sha256(manifest_path) != manifest_hash_before
    artifact_names = _source_artifact_names(profile)
    backup: Path | None = None
    baseline: dict[str, str | None] | None = None
    committed = _source_state_from_patch_manifest(profile, accepted_manifest)
    if manifest_changed:
        backup = _resolve_recorded_source_backup(
            patch_output,
            accepted_manifest,
            artifact_names,
            "pre_accept_snapshot",
            "PRE_ACCEPT",
        )
        _, backup_hashes = _validate_revision_backup(backup, "PRE_ACCEPT")
        baseline = {name: backup_hashes.get(name) for name in artifact_names}
    try:
        face_manifest = bake_macro_faces(
            profile,
            patch_output,
            face_output,
            resolved_patch_resolution,
            resolved_face_resolution,
            profile_path,
        )
    except Exception as bake_error:
        if backup is not None and baseline is not None:
            try:
                _rollback_source_transaction(
                    patch_output,
                    backup,
                    artifact_names,
                    baseline,
                    committed,
                )
            except Exception as rollback_error:
                raise RuntimeError(
                    f"face bake failed ({bake_error}); source rollback also failed: "
                    f"{rollback_error}"
                ) from bake_error
        raise
    return _acceptance_from_manifests(accepted_manifest, face_manifest)


def restore_snapshot_and_bake(
    profile_path: Path,
    snapshot: Path,
    patch_output: Path = AUTHORING_ROOT,
    face_output: Path = MACRO_FACE_ROOT,
    patch_resolution: int | None = None,
    face_resolution: int | None = None,
) -> dict[str, Any]:
    """Authenticate, restore, and bake one approved snapshot as one transaction."""
    profile_path = Path(profile_path).resolve()
    profile = compositor.load_profile(profile_path)
    patch_output = _require_output_scope(
        Path(patch_output), AUTHORING_ROOT, "patch output"
    )
    face_output, resolved_face_resolution = _resolve_face_bake_request(
        profile, Path(face_output), face_resolution
    )
    _, snapshot_manifest, restored_resolution = inspect_approved_source_snapshot(
        profile,
        snapshot,
        patch_output,
        profile_path,
    )
    if patch_resolution is not None and patch_resolution != restored_resolution:
        raise ValueError(
            f"restored snapshot resolution {restored_resolution} does not match "
            f"--patch-resolution {patch_resolution}"
        )

    backup, artifact_names, baseline = _capture_live_source_backup(
        profile, patch_output, "PRE_RESTORE"
    )
    snapshot_candidate, _, _ = inspect_approved_source_snapshot(
        profile,
        snapshot,
        patch_output,
        profile_path,
    )
    committed = _source_state(snapshot_candidate, artifact_names)
    try:
        restored_manifest = restore_source_snapshot(
            profile,
            snapshot_candidate,
            patch_output,
            profile_path,
            transaction_backup=backup,
            transaction_baseline=baseline,
        )
        face_manifest = bake_macro_faces(
            profile,
            patch_output,
            face_output,
            restored_resolution,
            resolved_face_resolution,
            profile_path,
        )
    except Exception as bake_error:
        try:
            _rollback_source_transaction(
                patch_output,
                backup,
                artifact_names,
                baseline,
                committed,
            )
        except Exception as rollback_error:
            raise RuntimeError(
                f"snapshot restore/bake failed ({bake_error}); source rollback also failed: "
                f"{rollback_error}"
            ) from bake_error
        raise
    return _acceptance_from_manifests(restored_manifest, face_manifest)


def bake_existing(
    profile_path: Path = DEFAULT_PROFILE_PATH,
    patch_output: Path = AUTHORING_ROOT,
    face_output: Path = MACRO_FACE_ROOT,
    patch_resolution: int | None = None,
    face_resolution: int | None = None,
) -> dict[str, Any]:
    """Strictly bake already-accepted rasters without writing any source patch byte."""
    (
        profile,
        profile_path,
        patch_output,
        face_output,
        patch_manifest,
        resolved_patch_resolution,
        resolved_face_resolution,
    ) = _preflight_bake_request(
        profile_path,
        patch_output,
        face_output,
        patch_resolution,
        face_resolution,
    )
    face_manifest = bake_macro_faces(
        profile,
        patch_output,
        face_output,
        resolved_patch_resolution,
        resolved_face_resolution,
        profile_path,
    )
    return _acceptance_from_manifests(patch_manifest, face_manifest)


def initialize_blockout(
    profile_path: Path = DEFAULT_PROFILE_PATH,
    patch_output: Path = AUTHORING_ROOT,
    face_output: Path = MACRO_FACE_ROOT,
    patch_resolution: int | None = None,
    face_resolution: int | None = None,
    *,
    force_overwrite_existing_sources: bool = False,
) -> dict[str, Any]:
    """Explicitly initialize the analytic blockout using staged, rollback-safe writes."""
    profile_path = Path(profile_path).resolve()
    profile = compositor.load_profile(profile_path)
    patch_output = _require_output_scope(
        Path(patch_output), AUTHORING_ROOT, "patch output"
    )
    face_output = _require_output_scope(
        Path(face_output), MACRO_FACE_ROOT, "macro-face output"
    )
    patch_output.mkdir(parents=True, exist_ok=True)
    face_output.mkdir(parents=True, exist_ok=True)
    resolved_patch_resolution = _validate_resolution(
        patch_resolution
        if patch_resolution is not None
        else int(profile.get("patch_resolution", DEFAULT_PATCH_RESOLUTION)),
        "patch resolution",
    )
    resolved_face_resolution = _validate_resolution(
        face_resolution
        if face_resolution is not None
        else int(profile.get("face_resolution", DEFAULT_FACE_RESOLUTION)),
        "face resolution",
        maximum=2047,
    )
    filenames = _expected_patch_filenames(profile)
    artifact_names = [*filenames, PATCH_MANIFEST_NAME]
    existing = [filename for filename in artifact_names if (patch_output / filename).exists()]
    if existing and not force_overwrite_existing_sources:
        raise ValueError(
            f"initialize-blockout refuses to overwrite {len(existing)} existing source artifacts; "
            "use bake-existing, accept-edits, or explicitly pass "
            "--force-overwrite-existing-sources"
        )
    initial_state = {
        filename: _sha256(patch_output / filename)
        if (patch_output / filename).is_file()
        else None
        for filename in artifact_names
    }
    backup = _create_revision_backup(patch_output, existing, "PRE_INITIALIZE")
    with tempfile.TemporaryDirectory(prefix=".initialize_stage_", dir=patch_output) as stage_name:
        staging = Path(stage_name)
        patch_manifest = generate_patch_rasters(
            profile,
            staging,
            resolved_patch_resolution,
            profile_path,
        )
        _validate_patch_manifest_inputs(
            profile, staging, resolved_patch_resolution, profile_path
        )
        load_patch_rasters(profile, staging, resolved_patch_resolution)
        for filename, initial_hash in initial_state.items():
            path = patch_output / filename
            current_hash = _sha256(path) if path.is_file() else None
            if current_hash != initial_hash:
                raise RuntimeError(f"source changed during initialize-blockout: {filename}")
        _publish_staged_files(
            staging,
            patch_output,
            artifact_names,
            PATCH_MANIFEST_NAME,
            backup,
        )

    try:
        _validate_patch_manifest_inputs(
            profile, patch_output, resolved_patch_resolution, profile_path
        )
        load_patch_rasters(profile, patch_output, resolved_patch_resolution)
        face_manifest = bake_macro_faces(
            profile,
            patch_output,
            face_output,
            resolved_patch_resolution,
            resolved_face_resolution,
            profile_path,
        )
    except Exception:
        _rollback_files(patch_output, backup, artifact_names)
        raise
    return _acceptance_from_manifests(patch_manifest, face_manifest)


def generate(
    profile_path: Path = DEFAULT_PROFILE_PATH,
    patch_output: Path = AUTHORING_ROOT,
    face_output: Path = MACRO_FACE_ROOT,
    patch_resolution: int | None = None,
    face_resolution: int | None = None,
    *,
    force_overwrite_existing_sources: bool = False,
) -> dict[str, Any]:
    """Compatibility wrapper for explicit, fail-closed blockout initialization."""
    return initialize_blockout(
        profile_path,
        patch_output,
        face_output,
        patch_resolution,
        face_resolution,
        force_overwrite_existing_sources=force_overwrite_existing_sources,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Safely initialize, accept edits to, or bake the 27 RED tangent source maps "
            "into six seam-safe cube faces."
        )
    )
    parser.add_argument(
        "command",
        choices=(
            "bake-existing",
            "accept-edits",
            "initialize-blockout",
            "snapshot-sources",
            "restore-snapshot",
        ),
        help=(
            "bake-existing never writes source maps; accept-edits validates and records "
            "manual edits; initialize-blockout is the only analytic source generator; "
            "snapshot/restore manage content-addressed source rollback points"
        ),
    )
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE_PATH)
    parser.add_argument("--patch-output", type=Path, default=AUTHORING_ROOT)
    parser.add_argument("--face-output", type=Path, default=MACRO_FACE_ROOT)
    parser.add_argument(
        "--resolution",
        type=int,
        help="set both patch and face resolution (individual options take precedence)",
    )
    parser.add_argument("--patch-resolution", type=int)
    parser.add_argument("--face-resolution", type=int)
    parser.add_argument(
        "--height-source",
        choices=("auto", "png", "r16"),
        default="auto",
        help=(
            "accept-edits conflict policy; auto accepts a changed PNG only and otherwise "
            "fails closed"
        ),
    )
    parser.add_argument(
        "--force-overwrite-existing-sources",
        action="store_true",
        help="required to let initialize-blockout replace any existing source artifact",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="snapshot directory name/path required by restore-snapshot",
    )
    args = parser.parse_args()

    patch_resolution = (
        args.patch_resolution
        if args.patch_resolution is not None
        else args.resolution
        if args.resolution is not None
        else None
    )
    face_resolution = (
        args.face_resolution
        if args.face_resolution is not None
        else args.resolution
        if args.resolution is not None
        else None
    )
    try:
        if args.command not in {"accept-edits"} and args.height_source != "auto":
            raise ValueError("--height-source is valid only for accept-edits")
        if args.command != "initialize-blockout" and args.force_overwrite_existing_sources:
            raise ValueError(
                "--force-overwrite-existing-sources is valid only for initialize-blockout"
            )
        if args.command != "restore-snapshot" and args.snapshot is not None:
            raise ValueError("--snapshot is valid only for restore-snapshot")
        if args.command == "initialize-blockout":
            acceptance = initialize_blockout(
                args.profile,
                args.patch_output,
                args.face_output,
                patch_resolution,
                face_resolution,
                force_overwrite_existing_sources=args.force_overwrite_existing_sources,
            )
        elif args.command == "accept-edits":
            acceptance = accept_edits_and_bake(
                args.profile,
                args.patch_output,
                args.face_output,
                patch_resolution,
                face_resolution,
                args.height_source,
            )
        elif args.command == "snapshot-sources":
            profile_path = Path(args.profile).resolve()
            profile = compositor.load_profile(profile_path)
            snapshot_path = snapshot_accepted_sources(
                profile, Path(args.patch_output), profile_path
            )
            print(
                "RED_PATCH_SNAPSHOT_READY "
                f"path={snapshot_path.relative_to(REPOSITORY_ROOT).as_posix()}"
            )
            return
        elif args.command == "restore-snapshot":
            if args.snapshot is None:
                raise ValueError("restore-snapshot requires --snapshot")
            acceptance = restore_snapshot_and_bake(
                args.profile,
                args.snapshot,
                args.patch_output,
                args.face_output,
                patch_resolution,
                face_resolution,
            )
        else:
            acceptance = bake_existing(
                args.profile,
                args.patch_output,
                args.face_output,
                patch_resolution,
                face_resolution,
            )
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"RED_PATCH_BAKE_FAILED {exc}") from exc

    print(
        "RED_PATCH_BAKE_READY "
        f"mode={args.command} "
        f"patches={acceptance['patch_count']} "
        f"patch_resolution={acceptance['patch_resolution']} "
        f"faces={acceptance['face_count']} "
        f"face_resolution={acceptance['face_resolution']} "
        f"uncovered={acceptance['uncovered_samples']} "
        f"seams={acceptance['seam_validation']['shared_boundary_comparisons']} "
        f"patch_sha256={acceptance['patch_dataset_sha256']} "
        f"face_sha256={acceptance['face_dataset_sha256']}"
    )


if __name__ == "__main__":
    main()
