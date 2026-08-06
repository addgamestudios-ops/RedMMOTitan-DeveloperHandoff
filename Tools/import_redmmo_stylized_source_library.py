"""Plan and import the approved local stylized texture source into Unreal.

The source tree at ``D:/styled assets`` is immutable. Normal Python creates or
validates a content-authenticated, no-clobber JSON plan. Unreal's
PythonScriptCommandlet consumes one explicitly selected, bounded category batch
and creates project-owned Texture2D packages below
``/Game/RedMMO/ArtLibrary/StylizedSource``.

This module intentionally does not delete, move, or overwrite source files or
existing Unreal assets. Existing assets are accepted only when their source
identity, import metadata, and texture settings match the selected plan.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat as stat_module
import sys
import tempfile
import unicodedata
from typing import Any, Iterable, Mapping, Sequence


PLAN_SCHEMA = "redmmotitan.stylized_source_import.v2"
STAGE_SCHEMA = "redmmotitan.stylized_source_stage.v1"
STATE_SCHEMA = "redmmotitan.stylized_source_import_state.v3"
ASSET_METADATA_SCHEMA = "redmmotitan.stylized_source_texture.v2"
DEFAULT_SOURCE_ROOT = Path(r"D:\styled assets")
DEFAULT_DESTINATION_ROOT = "/Game/RedMMO/ArtLibrary/StylizedSource"
DEFAULT_DIAGNOSTICS_ROOT = Path(
    r"D:\RedMMOTitanWindowsData\AssetImports\StylizedSource"
)
EXPECTED_PROJECT_FILE = Path(r"D:\RedMMOTitan\Titan_AssetImport.uproject")
EXPECTED_ENGINE_PREFIX = "5.8"
LICENSE_APPROVAL_STATUS = "approved_by_explicit_user_conversion_instruction"
LICENSE_APPROVAL_BASIS = (
    "The user explicitly instructed conversion of the supplied D:/styled assets "
    "source tree on 2026-07-24."
)
SOURCE_PROVENANCE = "user_supplied_local_source_tree"
ALLOWED_SOURCE_SUFFIXES = frozenset({".png", ".dds"})
CORE_ENVIRONMENT_CATEGORIES = (
    "Stylized_Crystal",
    "Stylized_Foliage",
    "Stylized_Grass",
    "Stylized_Ground",
    "Stylized_Lava",
    "Stylized_Rock",
    "Stylized_Sand",
    "Stylized_SnowIce",
    "Stylized_Terrain",
    "Stylized_Trees",
    "Stylized_Water",
)
MAX_SEGMENT_LENGTH = 56
MAX_OBJECT_PATH_LENGTH = 220
MAX_UNREAL_BATCH = 64
MAX_STAGED_IMAGE_PIXELS = 268_435_456
STAGE_MANIFEST_FILENAME = "stage_manifest.json"
STAGED_DDS_DIRECTORY = "staged_dds"
DIRECT_PNG_REPRESENTATION = "direct_png"
DDS_PNG_REPRESENTATION = "dds_to_png_pillow_rgba"
_VALID_SEGMENT = re.compile(r"[^A-Za-z0-9_]+")
_MULTIPLE_UNDERSCORES = re.compile(r"_+")
_SHA256 = re.compile(r"^[0-9A-F]{64}$")
_NORMAL_TERMINALS = frozenset(
    {"normal", "normaluncompressed", "dxtnormal", "norm", "nrm", "nor", "n"}
)
_MASK_TERMINALS = frozenset(
    {
        "rough",
        "roughness",
        "metal",
        "metallic",
        "orm",
        "rma",
        "mra",
        "arm",
        "ao",
        "occlusion",
        "ambientocclusion",
        "occlusionroughnessmetallic",
        "mask",
        "height",
        "displacement",
        "spec",
        "specular",
        "gloss",
        "opacity",
        "alpha",
    }
)

METADATA_TAGS = {
    "schema": "RedMMOTitan_StylizedSource_Schema",
    "stable_source_id": "RedMMOTitan_StylizedSource_Id",
    "relative_path": "RedMMOTitan_StylizedSource_RelativePath",
    "source_path": "RedMMOTitan_StylizedSource_SourcePath",
    "source_sha256": "RedMMOTitan_StylizedSource_SHA256",
    "source_provenance": "RedMMOTitan_StylizedSource_Provenance",
    "import_representation": "RedMMOTitan_StylizedSource_ImportRepresentation",
    "import_payload_sha256": "RedMMOTitan_StylizedSource_ImportPayloadSHA256",
    "semantic": "RedMMOTitan_StylizedSource_Semantic",
    "plan_sha256": "RedMMOTitan_StylizedSource_PlanSHA256",
    "settings_sha256": "RedMMOTitan_StylizedSource_SettingsSHA256",
}


@dataclass(frozen=True)
class ImportRecord:
    index: int
    stable_source_id: str
    relative_path: str
    category: str
    source_size: int
    source_mtime_ns: int
    source_sha256: str
    source_suffix: str
    semantic: str
    destination_path: str
    destination_name: str
    object_path: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _short_hash(value: str, length: int = 10) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length].upper()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _canonical_path_text(path: str | Path, *, strict: bool) -> str:
    return Path(path).resolve(strict=strict).as_posix()


def _paths_equal(first: str | Path, second: str | Path) -> bool:
    first_text = os.path.normcase(str(Path(first).resolve(strict=False)))
    second_text = os.path.normcase(str(Path(second).resolve(strict=False)))
    return first_text == second_text


def _lstat(path: Path, label: str) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as exc:
        raise RuntimeError(f"Cannot inspect {label}: {path}: {exc}") from exc


def _is_link_or_reparse(path: Path) -> bool:
    metadata = _lstat(path, "filesystem entry")
    reparse_flag = getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = int(getattr(metadata, "st_file_attributes", 0))
    return stat_module.S_ISLNK(metadata.st_mode) or bool(
        file_attributes & reparse_flag
    )


def _reject_link_or_reparse(path: Path, label: str) -> os.stat_result:
    metadata = _lstat(path, label)
    reparse_flag = getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = int(getattr(metadata, "st_file_attributes", 0))
    if stat_module.S_ISLNK(metadata.st_mode) or file_attributes & reparse_flag:
        raise RuntimeError(f"{label} cannot be a link or reparse point: {path}")
    return metadata


def sanitize_segment(value: str, *, fallback: str = "Asset") -> str:
    """Return one Unreal-safe package segment with deterministic truncation."""

    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = _VALID_SEGMENT.sub("_", ascii_value)
    cleaned = _MULTIPLE_UNDERSCORES.sub("_", cleaned).strip("_")
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = f"N_{cleaned}"
    if len(cleaned) > MAX_SEGMENT_LENGTH:
        suffix = _short_hash(cleaned, 8)
        cleaned = f"{cleaned[: MAX_SEGMENT_LENGTH - 9]}_{suffix}"
    return cleaned


def classify_texture_semantic(filename: str) -> str:
    """Classify by the terminal export suffix, with color taking precedence."""

    stem = Path(filename).stem.casefold()
    terminal = re.split(r"[_\-. ]+", stem)[-1]
    if terminal in _NORMAL_TERMINALS:
        return "normal"
    if terminal in _MASK_TERMINALS:
        return "mask"
    return "color"


def _resolve_source_root(
    source_root: str | Path,
    *,
    require_default_identity: bool = False,
) -> Path:
    supplied = Path(source_root)
    metadata = _reject_link_or_reparse(supplied, "Stylized source root")
    if not stat_module.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"Stylized source root is not a directory: {supplied}")
    root = supplied.resolve(strict=True)
    if require_default_identity and not _paths_equal(root, DEFAULT_SOURCE_ROOT):
        raise RuntimeError(
            "Stylized source root must be exactly "
            f"{_canonical_path_text(DEFAULT_SOURCE_ROOT, strict=True)}"
        )
    return root


def _walk_error(error: OSError) -> None:
    raise RuntimeError(f"Cannot walk approved stylized source tree: {error}") from error


def _sort_names(values: Iterable[str]) -> list[str]:
    return sorted(values, key=lambda value: (value.casefold(), value))


def iter_source_files(source_root: str | Path) -> Iterable[Path]:
    """Yield eligible regular files and fail closed on links or walk errors."""

    root = _resolve_source_root(source_root)
    for current_text, directory_names, file_names in os.walk(
        root,
        topdown=True,
        followlinks=False,
        onerror=_walk_error,
    ):
        current = Path(current_text)
        _reject_link_or_reparse(current, "Source directory")

        accepted_directories: list[str] = []
        for directory_name in _sort_names(directory_names):
            directory = current / directory_name
            metadata = _reject_link_or_reparse(directory, "Source directory")
            if not stat_module.S_ISDIR(metadata.st_mode):
                raise RuntimeError(f"Source directory entry is not a directory: {directory}")
            if directory_name.casefold() == "__macosx":
                continue
            accepted_directories.append(directory_name)
        directory_names[:] = accepted_directories

        for file_name in _sort_names(file_names):
            source_path = current / file_name
            metadata = _reject_link_or_reparse(source_path, "Source file")
            if not stat_module.S_ISREG(metadata.st_mode):
                raise RuntimeError(f"Source entry is not a regular file: {source_path}")
            if file_name.startswith("._"):
                continue
            if source_path.suffix.casefold() not in ALLOWED_SOURCE_SUFFIXES:
                continue
            resolved = source_path.resolve(strict=True)
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise RuntimeError(
                    f"Source file escapes the approved root: {source_path}"
                ) from exc
            yield resolved


def _parse_relative_path(relative_path: str) -> PurePosixPath:
    if not isinstance(relative_path, str) or not relative_path:
        raise RuntimeError("Planned relative_path must be a non-empty string")
    if "\\" in relative_path:
        raise RuntimeError(f"Planned relative_path is not canonical: {relative_path}")
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or relative.as_posix() != relative_path
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeError(f"Unsafe planned relative_path: {relative_path}")
    return relative


def _resolve_source_file(root: Path, relative_path: str) -> Path:
    relative = _parse_relative_path(relative_path)
    current = root
    for part in relative.parts:
        current = current / part
        _reject_link_or_reparse(current, "Planned source component")
    metadata = _lstat(current, "Planned source file")
    if not stat_module.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"Planned source is not a regular file: {relative_path}")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            f"Planned source escapes the approved root: {relative_path}"
        ) from exc
    return resolved


def _stable_source_id(relative_path: str) -> str:
    return f"RED-STYLIZED-{_short_hash(relative_path.casefold(), 24)}"


def _candidate_destination(
    relative: PurePosixPath,
    destination_root: str,
) -> tuple[str, str, str, str]:
    if len(relative.parts) < 2:
        raise RuntimeError(
            f"Every source texture must be inside a category directory: {relative}"
        )
    category = sanitize_segment(relative.parts[0], fallback="Uncategorized")
    parent = sanitize_segment(relative.parent.name, fallback="Textures")
    destination_name = sanitize_segment(relative.stem, fallback="Texture")
    destination_path = f"{destination_root}/{category}/{parent}"
    object_path = f"{destination_path}/{destination_name}"
    if len(object_path) > MAX_OBJECT_PATH_LENGTH:
        parent = f"LongPath_{_short_hash(relative.parent.as_posix(), 12)}"
        destination_path = f"{destination_root}/{category}/{parent}"
        object_path = f"{destination_path}/{destination_name}"
    if len(object_path) > MAX_OBJECT_PATH_LENGTH:
        destination_name = f"Texture_{_short_hash(relative.as_posix(), 16)}"
        object_path = f"{destination_path}/{destination_name}"
    return category, destination_path, destination_name, object_path


def _license_approval(source_root_text: str) -> dict[str, Any]:
    return {
        "approved": True,
        "status": LICENSE_APPROVAL_STATUS,
        "basis": LICENSE_APPROVAL_BASIS,
        "provenance": SOURCE_PROVENANCE,
        "source_root": source_root_text,
    }


def _dataset_digest(records: Sequence[ImportRecord]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(
            (
                f"{record.stable_source_id}\0{record.relative_path}\0"
                f"{record.source_size}\0{record.source_sha256}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest().upper()


def _plan_digest(
    records: Sequence[ImportRecord],
    *,
    source_root_text: str,
    destination_root: str,
    dataset_sha256: str,
) -> str:
    identity = {
        "schema": PLAN_SCHEMA,
        "source_root": source_root_text,
        "source_policy": "immutable",
        "destination_root": destination_root,
        "diagnostics_root": _canonical_path_text(
            DEFAULT_DIAGNOSTICS_ROOT, strict=False
        ),
        "project_file": _canonical_path_text(EXPECTED_PROJECT_FILE, strict=False),
        "expected_engine_version_prefix": EXPECTED_ENGINE_PREFIX,
        "license_approval": _license_approval(source_root_text),
        "dataset_sha256": dataset_sha256,
        "records": [asdict(record) for record in records],
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def build_import_plan(
    source_root: str | Path = DEFAULT_SOURCE_ROOT,
    destination_root: str = DEFAULT_DESTINATION_ROOT,
    *,
    enforce_default_identity: bool = True,
) -> dict[str, Any]:
    """Build a deterministic, content-authenticated plan."""

    root = _resolve_source_root(
        source_root,
        require_default_identity=enforce_default_identity,
    )
    if destination_root.endswith("/"):
        raise RuntimeError("Stylized destination root must not have a trailing slash")
    if enforce_default_identity and destination_root != DEFAULT_DESTINATION_ROOT:
        raise RuntimeError(
            f"Stylized destination root must be exactly {DEFAULT_DESTINATION_ROOT}"
        )
    if not destination_root.startswith("/Game/RedMMO/"):
        raise RuntimeError(
            "Stylized imports must stay inside a project-owned /Game/RedMMO namespace"
        )

    staged: list[dict[str, Any]] = []
    collisions: dict[str, list[int]] = defaultdict(list)
    relative_paths: set[str] = set()
    for source_path in iter_source_files(root):
        relative_text = source_path.relative_to(root).as_posix()
        folded_relative = relative_text.casefold()
        if folded_relative in relative_paths:
            raise RuntimeError(f"Case-insensitive source collision: {relative_text}")
        relative_paths.add(folded_relative)
        relative = PurePosixPath(relative_text)
        category, destination_path, destination_name, object_path = (
            _candidate_destination(relative, destination_root)
        )
        metadata = _lstat(source_path, "Source texture")
        staged.append(
            {
                "stable_source_id": _stable_source_id(relative_text),
                "relative_path": relative_text,
                "category": category,
                "source_size": metadata.st_size,
                "source_mtime_ns": metadata.st_mtime_ns,
                "source_sha256": sha256_file(source_path),
                "source_suffix": source_path.suffix.casefold(),
                "semantic": classify_texture_semantic(source_path.name),
                "destination_path": destination_path,
                "destination_name": destination_name,
                "object_path": object_path,
            }
        )
        collisions[object_path.casefold()].append(len(staged) - 1)

    for duplicate_indices in collisions.values():
        if len(duplicate_indices) < 2:
            continue
        for staged_index in duplicate_indices:
            entry = staged[staged_index]
            suffix = _short_hash(entry["relative_path"], 10)
            entry["destination_name"] = f"{entry['destination_name']}_{suffix}"
            entry["object_path"] = (
                f"{entry['destination_path']}/{entry['destination_name']}"
            )

    records = [
        ImportRecord(index=index, **entry) for index, entry in enumerate(staged)
    ]
    object_paths = [record.object_path.casefold() for record in records]
    if len(object_paths) != len(set(object_paths)):
        raise RuntimeError("Collision suffixing did not produce unique object paths")

    category_counts: dict[str, int] = defaultdict(int)
    semantic_counts: dict[str, int] = defaultdict(int)
    source_bytes = 0
    for record in records:
        category_counts[record.category] += 1
        semantic_counts[record.semantic] += 1
        source_bytes += record.source_size

    source_root_text = root.as_posix()
    dataset_sha256 = _dataset_digest(records)
    plan_sha256 = _plan_digest(
        records,
        source_root_text=source_root_text,
        destination_root=destination_root,
        dataset_sha256=dataset_sha256,
    )
    return {
        "schema": PLAN_SCHEMA,
        "generated_at_utc": utc_now(),
        "source_root": source_root_text,
        "source_policy": "immutable",
        "source_provenance": SOURCE_PROVENANCE,
        "destination_root": destination_root,
        "diagnostics_root": _canonical_path_text(
            DEFAULT_DIAGNOSTICS_ROOT, strict=False
        ),
        "project_file": _canonical_path_text(EXPECTED_PROJECT_FILE, strict=False),
        "expected_engine_version_prefix": EXPECTED_ENGINE_PREFIX,
        "license_approval": _license_approval(source_root_text),
        "record_count": len(records),
        "source_bytes": source_bytes,
        "category_counts": dict(sorted(category_counts.items())),
        "semantic_counts": dict(sorted(semantic_counts.items())),
        "dataset_sha256": dataset_sha256,
        "plan_sha256": plan_sha256,
        "records": [asdict(record) for record in records],
    }


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"{label} must be an object")
    return value


def _validate_record_types(record: ImportRecord, label: str) -> None:
    string_fields = (
        "stable_source_id",
        "relative_path",
        "category",
        "source_sha256",
        "source_suffix",
        "semantic",
        "destination_path",
        "destination_name",
        "object_path",
    )
    for field_name in string_fields:
        if not isinstance(getattr(record, field_name), str):
            raise RuntimeError(f"{label}.{field_name} must be a string")
    if type(record.index) is not int:
        raise RuntimeError(f"{label}.index must be an integer")
    if type(record.source_size) is not int or record.source_size < 0:
        raise RuntimeError(f"{label}.source_size must be a non-negative integer")
    if type(record.source_mtime_ns) is not int or record.source_mtime_ns < 0:
        raise RuntimeError(f"{label}.source_mtime_ns must be a non-negative integer")


def _summary_counts(
    records: Sequence[ImportRecord],
) -> tuple[int, dict[str, int], dict[str, int]]:
    source_bytes = 0
    category_counts: dict[str, int] = defaultdict(int)
    semantic_counts: dict[str, int] = defaultdict(int)
    for record in records:
        source_bytes += record.source_size
        category_counts[record.category] += 1
        semantic_counts[record.semantic] += 1
    return (
        source_bytes,
        dict(sorted(category_counts.items())),
        dict(sorted(semantic_counts.items())),
    )


def validate_import_plan(
    plan: Mapping[str, Any],
    *,
    verify_source_metadata: bool = True,
    verify_source_hashes: bool = True,
    expected_source_root: str | Path | None = DEFAULT_SOURCE_ROOT,
    expected_destination_root: str | None = DEFAULT_DESTINATION_ROOT,
) -> list[ImportRecord]:
    """Validate identity, provenance, paths, mapping, summaries, and content."""

    if plan.get("schema") != PLAN_SCHEMA:
        raise RuntimeError(f"Unexpected stylized import schema: {plan.get('schema')}")
    source_root_raw = plan.get("source_root")
    if not isinstance(source_root_raw, str):
        raise RuntimeError("Stylized import source_root must be a string")
    root = _resolve_source_root(source_root_raw)
    source_root_text = root.as_posix()
    if source_root_raw != source_root_text:
        raise RuntimeError("Stylized import source_root is not canonical")
    if expected_source_root is not None and not _paths_equal(root, expected_source_root):
        raise RuntimeError(
            "Plan source root identity mismatch: "
            f"expected {_canonical_path_text(expected_source_root, strict=True)}, "
            f"got {source_root_text}"
        )

    destination_root = plan.get("destination_root")
    if not isinstance(destination_root, str):
        raise RuntimeError("Stylized import destination_root must be a string")
    if expected_destination_root is not None and destination_root != expected_destination_root:
        raise RuntimeError(
            "Plan destination root identity mismatch: "
            f"expected {expected_destination_root}, got {destination_root}"
        )
    if not destination_root.startswith("/Game/RedMMO/") or destination_root.endswith(
        "/"
    ):
        raise RuntimeError("Plan destination is outside the project-owned namespace")

    expected_identity = {
        "source_policy": "immutable",
        "source_provenance": SOURCE_PROVENANCE,
        "diagnostics_root": _canonical_path_text(
            DEFAULT_DIAGNOSTICS_ROOT, strict=False
        ),
        "project_file": _canonical_path_text(EXPECTED_PROJECT_FILE, strict=False),
        "expected_engine_version_prefix": EXPECTED_ENGINE_PREFIX,
    }
    for key, expected_value in expected_identity.items():
        if plan.get(key) != expected_value:
            raise RuntimeError(
                f"Plan identity field {key} mismatch: "
                f"expected {expected_value!r}, got {plan.get(key)!r}"
            )
    approval = _require_mapping(plan.get("license_approval"), "license_approval")
    if dict(approval) != _license_approval(source_root_text):
        raise RuntimeError("Plan license approval or source provenance is invalid")

    raw_records = plan.get("records")
    if not isinstance(raw_records, list):
        raise RuntimeError("Stylized import records must be an array")

    records: list[ImportRecord] = []
    source_paths: set[str] = set()
    object_paths: set[str] = set()
    base_candidates: list[tuple[str, str, str, str]] = []
    source_files: list[Path] = []
    collision_groups: dict[str, list[int]] = defaultdict(list)
    for expected_index, raw_record in enumerate(raw_records):
        record_map = _require_mapping(raw_record, f"record {expected_index}")
        try:
            record = ImportRecord(**record_map)
        except TypeError as exc:
            raise RuntimeError(f"Malformed import record {expected_index}") from exc
        _validate_record_types(record, f"record {expected_index}")
        if record.index != expected_index:
            raise RuntimeError(
                f"Import record index mismatch: expected {expected_index}, got {record.index}"
            )
        relative = _parse_relative_path(record.relative_path)
        folded_relative = record.relative_path.casefold()
        if folded_relative in source_paths:
            raise RuntimeError(
                f"Duplicate case-insensitive source path: {record.relative_path}"
            )
        source_paths.add(folded_relative)
        if record.stable_source_id != _stable_source_id(record.relative_path):
            raise RuntimeError(
                f"Stable source identity mismatch: {record.relative_path}"
            )
        if not _SHA256.fullmatch(record.source_sha256):
            raise RuntimeError(f"Invalid source SHA256: {record.relative_path}")
        if record.source_suffix not in ALLOWED_SOURCE_SUFFIXES:
            raise RuntimeError(f"Unsupported planned suffix: {record.source_suffix}")
        if record.semantic != classify_texture_semantic(relative.name):
            raise RuntimeError(
                f"Texture semantic does not match terminal suffix: {record.relative_path}"
            )

        candidate = _candidate_destination(relative, destination_root)
        category, destination_path, _, base_object_path = candidate
        if record.category != category or record.destination_path != destination_path:
            raise RuntimeError(
                f"Record destination mapping is inconsistent: {record.object_path}"
            )
        base_candidates.append(candidate)
        collision_groups[base_object_path.casefold()].append(expected_index)
        if record.object_path != f"{record.destination_path}/{record.destination_name}":
            raise RuntimeError(f"Record object path is inconsistent: {record.object_path}")
        if len(record.object_path) > MAX_OBJECT_PATH_LENGTH:
            raise RuntimeError(f"Record object path is too long: {record.object_path}")
        folded_object_path = record.object_path.casefold()
        if folded_object_path in object_paths:
            raise RuntimeError(f"Duplicate object path in plan: {record.object_path}")
        object_paths.add(folded_object_path)

        source_path = _resolve_source_file(root, record.relative_path)
        if source_path.suffix.casefold() != record.source_suffix:
            raise RuntimeError(f"Source suffix changed: {record.relative_path}")
        metadata = _lstat(source_path, "Planned source texture")
        if verify_source_metadata:
            if metadata.st_size != record.source_size:
                raise RuntimeError(
                    f"Source size changed after planning: {record.relative_path}"
                )
            if metadata.st_mtime_ns != record.source_mtime_ns:
                raise RuntimeError(
                    f"Source timestamp changed after planning: {record.relative_path}"
                )
        if verify_source_hashes and sha256_file(source_path) != record.source_sha256:
            raise RuntimeError(
                f"Source SHA256 changed after planning: {record.relative_path}"
            )
        source_files.append(source_path)
        records.append(record)

    for indices in collision_groups.values():
        for index in indices:
            record = records[index]
            _, expected_path, base_name, _ = base_candidates[index]
            expected_name = (
                f"{base_name}_{_short_hash(record.relative_path, 10)}"
                if len(indices) > 1
                else base_name
            )
            expected_object = f"{expected_path}/{expected_name}"
            if (
                record.destination_name != expected_name
                or record.object_path != expected_object
            ):
                raise RuntimeError(
                    f"Deterministic destination mismatch: {record.relative_path}"
                )

    if plan.get("record_count") != len(records):
        raise RuntimeError("Plan record_count does not match its records array")
    source_bytes, category_counts, semantic_counts = _summary_counts(records)
    if plan.get("source_bytes") != source_bytes:
        raise RuntimeError("Plan source_bytes does not match its records")
    if plan.get("category_counts") != category_counts:
        raise RuntimeError("Plan category_counts does not match its records")
    if plan.get("semantic_counts") != semantic_counts:
        raise RuntimeError("Plan semantic_counts does not match its records")
    dataset_sha256 = _dataset_digest(records)
    if plan.get("dataset_sha256") != dataset_sha256:
        raise RuntimeError("Stylized source dataset digest mismatch")
    plan_sha256 = _plan_digest(
        records,
        source_root_text=source_root_text,
        destination_root=destination_root,
        dataset_sha256=dataset_sha256,
    )
    if plan.get("plan_sha256") != plan_sha256:
        raise RuntimeError("Stylized import plan digest mismatch")
    return records


def select_import_records(
    records: Sequence[ImportRecord],
    categories: Sequence[str],
    start: int,
    limit: int,
) -> tuple[tuple[str, ...], list[ImportRecord]]:
    """Return one exact, bounded category selection shared by both stages."""

    normalized_categories = tuple(categories)
    if (
        not normalized_categories
        or any(
            not isinstance(category, str) or not category.strip()
            for category in normalized_categories
        )
        or any(category != category.strip() for category in normalized_categories)
        or len(normalized_categories) != len(set(normalized_categories))
    ):
        raise RuntimeError("Import categories must be non-empty, trimmed, and unique")
    if type(start) is not int or start < 0:
        raise RuntimeError("Import batch start must be a non-negative integer")
    if type(limit) is not int or limit < 1 or limit > MAX_UNREAL_BATCH:
        raise RuntimeError(
            f"Import batch requires 1 <= limit <= {MAX_UNREAL_BATCH}"
        )

    available_categories = {record.category for record in records}
    unknown_categories = sorted(
        set(normalized_categories) - available_categories
    )
    if unknown_categories:
        raise RuntimeError(
            "Unknown stylized import categories: " + ", ".join(unknown_categories)
        )
    filtered = [
        record
        for record in records
        if record.category in normalized_categories
    ]
    selected = filtered[start : start + limit]
    if not selected:
        raise RuntimeError(
            f"Import selection is empty: filtered={len(filtered)} "
            f"start={start} limit={limit}"
        )
    return normalized_categories, selected


def _validate_diagnostics_path(
    path: str | Path,
    *,
    must_exist: bool,
) -> Path:
    allowed_root = DEFAULT_DIAGNOSTICS_ROOT.resolve(strict=False)
    candidate_supplied = Path(path)
    if candidate_supplied.exists() or candidate_supplied.is_symlink():
        _reject_link_or_reparse(candidate_supplied, "Diagnostics file")
    candidate = candidate_supplied.resolve(strict=must_exist)
    try:
        relative = candidate.relative_to(allowed_root)
    except ValueError as exc:
        raise RuntimeError(
            f"Diagnostics file must be below {allowed_root}: {candidate}"
        ) from exc
    if not relative.parts or candidate.suffix.casefold() != ".json":
        raise RuntimeError("Diagnostics path must be a child JSON file")

    if allowed_root.exists():
        _reject_link_or_reparse(allowed_root, "Diagnostics root")
    current = allowed_root
    for part in relative.parts[:-1]:
        current = current / part
        if current.exists() or current.is_symlink():
            metadata = _reject_link_or_reparse(current, "Diagnostics directory")
            if not stat_module.S_ISDIR(metadata.st_mode):
                raise RuntimeError(
                    f"Diagnostics parent is not a directory: {current}"
                )
    return candidate


def write_json_no_clobber(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Publish JSON via a same-directory temporary and non-overwriting rename."""

    output = Path(path)
    if output.exists() or output.is_symlink():
        raise RuntimeError(f"Refusing to overwrite diagnostics file: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_text = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    temporary = Path(temporary_text)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if output.exists() or output.is_symlink():
            raise RuntimeError(f"Refusing to overwrite diagnostics file: {output}")
        os.rename(temporary, output)
    finally:
        if temporary.exists():
            os.remove(temporary)


def _load_plan(
    path: str | Path,
    *,
    require_diagnostics_boundary: bool = True,
    verify_source_metadata: bool = True,
    verify_source_hashes: bool = True,
) -> tuple[dict[str, Any], list[ImportRecord]]:
    plan_path = (
        _validate_diagnostics_path(path, must_exist=True)
        if require_diagnostics_boundary
        else Path(path).resolve(strict=True)
    )
    with plan_path.open("r", encoding="utf-8") as handle:
        plan = json.load(handle)
    if not isinstance(plan, dict):
        raise RuntimeError("Stylized import plan root must be an object")
    return plan, validate_import_plan(
        plan,
        verify_source_metadata=verify_source_metadata,
        verify_source_hashes=verify_source_hashes,
        expected_source_root=DEFAULT_SOURCE_ROOT,
        expected_destination_root=DEFAULT_DESTINATION_ROOT,
    )


def _validate_diagnostics_directory(
    path: str | Path,
    *,
    must_exist: bool,
) -> Path:
    allowed_root = DEFAULT_DIAGNOSTICS_ROOT.resolve(strict=False)
    supplied = Path(path)
    if supplied.exists() or supplied.is_symlink():
        metadata = _reject_link_or_reparse(supplied, "Diagnostics directory")
        if not stat_module.S_ISDIR(metadata.st_mode):
            raise RuntimeError(f"Diagnostics path is not a directory: {supplied}")
    candidate = supplied.resolve(strict=must_exist)
    try:
        relative = candidate.relative_to(allowed_root)
    except ValueError as exc:
        raise RuntimeError(
            f"Diagnostics directory must be below {allowed_root}: {candidate}"
        ) from exc
    if not relative.parts:
        raise RuntimeError("Diagnostics directory must be a strict child")

    if allowed_root.exists():
        _reject_link_or_reparse(allowed_root, "Diagnostics root")
    current = allowed_root
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            metadata = _reject_link_or_reparse(
                current, "Diagnostics directory component"
            )
            if not stat_module.S_ISDIR(metadata.st_mode):
                raise RuntimeError(
                    f"Diagnostics component is not a directory: {current}"
                )
    return candidate


def _stage_dds_as_png(source_path: Path, destination: Path) -> str:
    """Decode one immutable DDS to a no-clobber RGBA PNG payload."""

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required to stage DDS textures for Unreal"
        ) from exc

    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"Refusing to overwrite staged texture: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _reject_link_or_reparse(destination.parent, "Staged DDS directory")

    file_descriptor, temporary_text = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp.png",
        dir=destination.parent,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_text)
    try:
        try:
            with Image.open(source_path) as image:
                width, height = image.size
                if width < 1 or height < 1:
                    raise RuntimeError(
                        f"DDS has invalid dimensions: {source_path}"
                    )
                if width * height > MAX_STAGED_IMAGE_PIXELS:
                    raise RuntimeError(
                        f"DDS exceeds the staging pixel gate: {source_path}"
                    )
                converted = image.convert("RGBA")
                converted.save(
                    temporary,
                    format="PNG",
                    compress_level=6,
                    optimize=False,
                )
        except (UnidentifiedImageError, OSError) as exc:
            raise RuntimeError(f"Cannot decode DDS texture: {source_path}") from exc

        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        if destination.exists() or destination.is_symlink():
            raise RuntimeError(
                f"Refusing to overwrite staged texture: {destination}"
            )
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            os.remove(temporary)
    return sha256_file(destination)


def stage_import_batch(
    plan_path: str | Path,
    categories: Sequence[str],
    start: int,
    limit: int,
    output_directory: str | Path,
) -> dict[str, Any]:
    """Prepare authenticated import payloads for one bounded batch."""

    resolved_plan = _validate_diagnostics_path(plan_path, must_exist=True)
    plan_file_sha256 = sha256_file(resolved_plan)
    plan, records = _load_plan(
        resolved_plan,
        verify_source_metadata=False,
        verify_source_hashes=False,
    )
    requested_categories, selected = select_import_records(
        records,
        categories,
        start,
        limit,
    )
    source_root = _resolve_source_root(
        plan["source_root"], require_default_identity=True
    )
    output = _validate_diagnostics_directory(
        output_directory,
        must_exist=True,
    )
    manifest_path = output / STAGE_MANIFEST_FILENAME
    if manifest_path.exists() or manifest_path.is_symlink():
        raise RuntimeError(f"Stage manifest must be fresh: {manifest_path}")

    needs_dds = any(record.source_suffix == ".dds" for record in selected)
    staged_directory = output / STAGED_DDS_DIRECTORY
    if needs_dds:
        if staged_directory.exists() or staged_directory.is_symlink():
            raise RuntimeError(
                f"Staged DDS directory must be fresh: {staged_directory}"
            )
        staged_directory.mkdir()

    entries: list[dict[str, Any]] = []
    for record in selected:
        source_path = _resolve_source_file(source_root, record.relative_path)
        metadata = _lstat(source_path, "Selected source texture")
        if (
            metadata.st_size != record.source_size
            or metadata.st_mtime_ns != record.source_mtime_ns
            or sha256_file(source_path) != record.source_sha256
        ):
            raise RuntimeError(
                f"Selected source changed after planning: {record.relative_path}"
            )

        if record.source_suffix == ".png":
            import_path = source_path
            representation = DIRECT_PNG_REPRESENTATION
            payload_sha256 = record.source_sha256
        elif record.source_suffix == ".dds":
            import_path = (
                staged_directory
                / f"{record.index:06d}_{record.stable_source_id}.png"
            )
            representation = DDS_PNG_REPRESENTATION
            payload_sha256 = _stage_dds_as_png(source_path, import_path)
        else:
            raise RuntimeError(
                f"Unsupported staging suffix: {record.source_suffix}"
            )

        entries.append(
            {
                "index": record.index,
                "stable_source_id": record.stable_source_id,
                "relative_path": record.relative_path,
                "source_sha256": record.source_sha256,
                "source_suffix": record.source_suffix,
                "representation": representation,
                "import_path": import_path.resolve(strict=True).as_posix(),
                "import_payload_sha256": payload_sha256,
            }
        )

    manifest = {
        "schema": STAGE_SCHEMA,
        "created_at_utc": utc_now(),
        "plan_path": resolved_plan.as_posix(),
        "plan_file_sha256": plan_file_sha256,
        "plan_sha256": plan["plan_sha256"],
        "dataset_sha256": plan["dataset_sha256"],
        "categories": list(requested_categories),
        "batch_start": start,
        "batch_limit": limit,
        "result_count": len(entries),
        "staged_dds_count": sum(
            entry["representation"] == DDS_PNG_REPRESENTATION
            for entry in entries
        ),
        "records": entries,
    }
    write_json_no_clobber(manifest_path, manifest)
    return manifest


def _load_stage_manifest(
    manifest_path: str | Path,
    *,
    expected_manifest_file_sha256: str,
    plan_path: Path,
    plan_file_sha256: str,
    plan: Mapping[str, Any],
    categories: Sequence[str],
    start: int,
    limit: int,
    selected: Sequence[ImportRecord],
    selected_sources: Mapping[int, Path],
) -> tuple[Path, dict[int, tuple[Path, str, str]]]:
    resolved_manifest = _validate_diagnostics_path(
        manifest_path,
        must_exist=True,
    )
    if not _SHA256.fullmatch(expected_manifest_file_sha256):
        raise RuntimeError("Stage manifest file SHA256 is required")
    if sha256_file(resolved_manifest) != expected_manifest_file_sha256:
        raise RuntimeError("Stage manifest file SHA256 mismatch")
    with resolved_manifest.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict) or manifest.get("schema") != STAGE_SCHEMA:
        raise RuntimeError("Unexpected stylized stage manifest schema")

    expected_identity = {
        "plan_path": plan_path.as_posix(),
        "plan_file_sha256": plan_file_sha256,
        "plan_sha256": plan["plan_sha256"],
        "dataset_sha256": plan["dataset_sha256"],
        "categories": list(categories),
        "batch_start": start,
        "batch_limit": limit,
        "result_count": len(selected),
    }
    for key, expected in expected_identity.items():
        if manifest.get(key) != expected:
            raise RuntimeError(f"Stage manifest identity mismatch: {key}")

    raw_entries = manifest.get("records")
    if not isinstance(raw_entries, list) or len(raw_entries) != len(selected):
        raise RuntimeError("Stage manifest records do not match the selection")
    staged_root = (resolved_manifest.parent / STAGED_DDS_DIRECTORY).resolve(
        strict=False
    )
    imports: dict[int, tuple[Path, str, str]] = {}
    for record, raw_entry in zip(selected, raw_entries):
        entry = _require_mapping(raw_entry, f"stage record {record.index}")
        expected_record_identity = {
            "index": record.index,
            "stable_source_id": record.stable_source_id,
            "relative_path": record.relative_path,
            "source_sha256": record.source_sha256,
            "source_suffix": record.source_suffix,
        }
        for key, expected in expected_record_identity.items():
            if entry.get(key) != expected:
                raise RuntimeError(
                    f"Stage record identity mismatch: {record.relative_path} {key}"
                )

        import_path_raw = entry.get("import_path")
        payload_sha256 = entry.get("import_payload_sha256")
        representation = entry.get("representation")
        if not isinstance(import_path_raw, str) or not _SHA256.fullmatch(
            str(payload_sha256)
        ):
            raise RuntimeError(
                f"Stage import payload is malformed: {record.relative_path}"
            )
        import_path = Path(import_path_raw).resolve(strict=True)
        _reject_link_or_reparse(import_path, "Stage import payload")
        if record.source_suffix == ".png":
            if (
                representation != DIRECT_PNG_REPRESENTATION
                or not _paths_equal(import_path, selected_sources[record.index])
                or payload_sha256 != record.source_sha256
            ):
                raise RuntimeError(
                    f"Direct PNG stage identity mismatch: {record.relative_path}"
                )
        elif record.source_suffix == ".dds":
            try:
                import_path.relative_to(staged_root)
            except ValueError as exc:
                raise RuntimeError(
                    f"Staged DDS escaped its output directory: {record.relative_path}"
                ) from exc
            if (
                representation != DDS_PNG_REPRESENTATION
                or import_path.suffix.casefold() != ".png"
            ):
                raise RuntimeError(
                    f"Staged DDS representation mismatch: {record.relative_path}"
                )
        else:
            raise RuntimeError(
                f"Unsupported stage record suffix: {record.source_suffix}"
            )
        if sha256_file(import_path) != payload_sha256:
            raise RuntimeError(
                f"Stage import payload SHA256 mismatch: {record.relative_path}"
            )
        imports[record.index] = (
            import_path,
            str(representation),
            str(payload_sha256),
        )
    return resolved_manifest, imports


def _settings_identity(semantic: str) -> dict[str, Any]:
    if semantic not in {"color", "normal", "mask"}:
        raise RuntimeError(f"Unsupported texture semantic: {semantic}")
    return {
        "lod_group": "TEXTUREGROUP_WORLD",
        "srgb": semantic == "color",
        "compression_settings": {
            "color": "TC_DEFAULT",
            "normal": "TC_NORMALMAP",
            "mask": "TC_MASKS",
        }[semantic],
    }


def _settings_digest(semantic: str) -> str:
    encoded = json.dumps(
        _settings_identity(semantic),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _expected_metadata(
    record: ImportRecord,
    *,
    source_path: Path,
    plan_sha256: str,
    import_representation: str,
    import_payload_sha256: str,
) -> dict[str, str]:
    return {
        METADATA_TAGS["schema"]: ASSET_METADATA_SCHEMA,
        METADATA_TAGS["stable_source_id"]: record.stable_source_id,
        METADATA_TAGS["relative_path"]: record.relative_path,
        METADATA_TAGS["source_path"]: source_path.as_posix(),
        METADATA_TAGS["source_sha256"]: record.source_sha256,
        METADATA_TAGS["source_provenance"]: SOURCE_PROVENANCE,
        METADATA_TAGS["import_representation"]: import_representation,
        METADATA_TAGS["import_payload_sha256"]: import_payload_sha256,
        METADATA_TAGS["semantic"]: record.semantic,
        METADATA_TAGS["plan_sha256"]: plan_sha256,
        METADATA_TAGS["settings_sha256"]: _settings_digest(record.semantic),
    }


def _texture_setting_values(
    unreal_module: Any,
    semantic: str,
) -> tuple[object, bool, object]:
    if semantic == "normal":
        compression = unreal_module.TextureCompressionSettings.TC_NORMALMAP
    elif semantic == "mask":
        compression = unreal_module.TextureCompressionSettings.TC_MASKS
    elif semantic == "color":
        compression = unreal_module.TextureCompressionSettings.TC_DEFAULT
    else:
        raise RuntimeError(f"Unsupported texture semantic: {semantic}")
    return (
        unreal_module.TextureGroup.TEXTUREGROUP_WORLD,
        semantic == "color",
        compression,
    )


def _require_texture2d(asset: object, object_path: str) -> None:
    class_name = asset.get_class().get_name()
    if class_name != "Texture2D":
        raise RuntimeError(
            f"Asset at {object_path} must be exactly Texture2D, got {class_name}"
        )


def _set_texture_properties(unreal_module: Any, asset: object, semantic: str) -> None:
    _require_texture2d(asset, "new import")
    lod_group, srgb, compression = _texture_setting_values(
        unreal_module, semantic
    )
    asset.set_editor_property("lod_group", lod_group)
    asset.set_editor_property("srgb", srgb)
    asset.set_editor_property("compression_settings", compression)


def _set_asset_metadata(
    unreal_module: Any,
    asset: object,
    expected: Mapping[str, str],
) -> None:
    for tag_name, value in expected.items():
        unreal_module.EditorAssetLibrary.set_metadata_tag(asset, tag_name, value)


def _first_import_filename(asset: object) -> str:
    try:
        import_data = asset.get_editor_property("asset_import_data")
    except Exception as exc:
        raise RuntimeError("Texture2D has no readable asset_import_data") from exc
    if import_data is None or not hasattr(import_data, "get_first_filename"):
        raise RuntimeError("Texture2D asset_import_data cannot report its source")
    filename = str(import_data.get_first_filename() or "").strip()
    if not filename:
        raise RuntimeError("Texture2D asset_import_data has no source filename")
    return filename


def _verify_texture_asset(
    unreal_module: Any,
    asset: object,
    record: ImportRecord,
    *,
    source_path: Path,
    plan_sha256: str,
    import_representation: str,
    import_payload_sha256: str,
) -> None:
    _require_texture2d(asset, record.object_path)
    expected_metadata = _expected_metadata(
        record,
        source_path=source_path,
        plan_sha256=plan_sha256,
        import_representation=import_representation,
        import_payload_sha256=import_payload_sha256,
    )
    for tag_name, expected_value in expected_metadata.items():
        actual_value = unreal_module.EditorAssetLibrary.get_metadata_tag(
            asset, tag_name
        )
        if actual_value != expected_value:
            raise RuntimeError(
                "Existing or imported asset metadata is unverified: "
                f"{record.object_path} tag={tag_name}"
            )

    expected_lod, expected_srgb, expected_compression = _texture_setting_values(
        unreal_module, record.semantic
    )
    actual_settings = (
        asset.get_editor_property("lod_group"),
        bool(asset.get_editor_property("srgb")),
        asset.get_editor_property("compression_settings"),
    )
    if actual_settings != (
        expected_lod,
        expected_srgb,
        expected_compression,
    ):
        raise RuntimeError(
            f"Texture settings are unverified: {record.object_path}"
        )
    imported_source = Path(_first_import_filename(asset)).resolve(strict=True)
    _reject_link_or_reparse(imported_source, "Texture import source")
    if import_representation == DIRECT_PNG_REPRESENTATION:
        if (
            not _paths_equal(imported_source, source_path)
            or import_payload_sha256 != record.source_sha256
        ):
            raise RuntimeError(
                f"Texture import source identity is unverified: {record.object_path}"
            )
    elif import_representation == DDS_PNG_REPRESENTATION:
        diagnostics_root = DEFAULT_DIAGNOSTICS_ROOT.resolve(strict=True)
        try:
            imported_source.relative_to(diagnostics_root)
        except ValueError as exc:
            raise RuntimeError(
                f"Staged texture import source escaped diagnostics: {record.object_path}"
            ) from exc
        if (
            imported_source.suffix.casefold() != ".png"
            or sha256_file(imported_source) != import_payload_sha256
        ):
            raise RuntimeError(
                f"Staged texture import payload is unverified: {record.object_path}"
            )
    else:
        raise RuntimeError(
            f"Texture import representation is unverified: {record.object_path}"
        )


def _normalize_imported_object_path(value: object) -> str:
    text = str(value).strip()
    if "'" in text:
        parts = text.split("'")
        if len(parts) >= 3:
            text = parts[-2]
    return text.split(".", 1)[0]


def _state_payload(
    *,
    plan_path: Path,
    plan_file_sha256: str,
    stage_manifest_path: Path,
    stage_manifest_file_sha256: str,
    plan: Mapping[str, Any],
    start: int,
    limit: int,
    categories: Sequence[str],
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "completed_at_utc": utc_now(),
        "plan_path": plan_path.as_posix(),
        "plan_file_sha256": plan_file_sha256,
        "stage_manifest_path": stage_manifest_path.as_posix(),
        "stage_manifest_file_sha256": stage_manifest_file_sha256,
        "plan_sha256": plan["plan_sha256"],
        "dataset_sha256": plan["dataset_sha256"],
        "source_provenance": SOURCE_PROVENANCE,
        "license_approval_status": LICENSE_APPROVAL_STATUS,
        "batch_start": start,
        "batch_limit": limit,
        "categories": list(categories),
        "result_count": len(results),
        "results": list(results),
    }


def _validate_runtime_identity(unreal_module: Any) -> None:
    engine_version = str(unreal_module.SystemLibrary.get_engine_version())
    if not engine_version.startswith(EXPECTED_ENGINE_PREFIX):
        raise RuntimeError(
            f"Unreal engine identity mismatch: expected {EXPECTED_ENGINE_PREFIX}, "
            f"got {engine_version}"
        )
    project_text = str(unreal_module.Paths.get_project_file_path())
    if hasattr(unreal_module.Paths, "convert_relative_path_to_full"):
        project_text = str(
            unreal_module.Paths.convert_relative_path_to_full(project_text)
        )
    project_path = Path(project_text).resolve(strict=True)
    if not _paths_equal(project_path, EXPECTED_PROJECT_FILE):
        raise RuntimeError(
            f"Unreal project identity mismatch: expected {EXPECTED_PROJECT_FILE}, "
            f"got {project_path}"
        )


def run_unreal_import() -> None:
    """Consume one bounded, authenticated plan batch in Unreal."""

    import unreal

    _validate_runtime_identity(unreal)
    plan_raw = os.environ.get("RED_STYLIZED_IMPORT_PLAN", "").strip()
    if not plan_raw:
        raise RuntimeError("RED_STYLIZED_IMPORT_PLAN is required")
    plan_path = _validate_diagnostics_path(plan_raw, must_exist=True)
    expected_plan_file_sha256 = os.environ.get(
        "RED_STYLIZED_IMPORT_PLAN_FILE_SHA256", ""
    ).strip().upper()
    if not _SHA256.fullmatch(expected_plan_file_sha256):
        raise RuntimeError("RED_STYLIZED_IMPORT_PLAN_FILE_SHA256 is required")
    actual_plan_file_sha256 = sha256_file(plan_path)
    if actual_plan_file_sha256 != expected_plan_file_sha256:
        raise RuntimeError("Stylized import plan file SHA256 mismatch")

    # The authenticated plan contains every file hash. Runtime performs the
    # complete structural validation but re-reads content only for this bounded
    # selection; the offline verify-plan command remains a full-corpus check.
    plan, records = _load_plan(
        plan_path,
        verify_source_metadata=False,
        verify_source_hashes=False,
    )
    source_root = _resolve_source_root(
        plan["source_root"], require_default_identity=True
    )

    category_raw = os.environ.get("RED_STYLIZED_IMPORT_CATEGORIES", "").strip()
    if not category_raw:
        raise RuntimeError("RED_STYLIZED_IMPORT_CATEGORIES is required")
    start = int(os.environ.get("RED_STYLIZED_IMPORT_START", "0"))
    limit = int(os.environ.get("RED_STYLIZED_IMPORT_LIMIT", "64"))
    requested_categories, selected = select_import_records(
        records,
        tuple(category_raw.split(",")),
        start,
        limit,
    )
    filtered_count = sum(
        record.category in requested_categories for record in records
    )

    state_raw = os.environ.get("RED_STYLIZED_IMPORT_STATE", "").strip()
    if not state_raw:
        raise RuntimeError("RED_STYLIZED_IMPORT_STATE is required")
    state_path = _validate_diagnostics_path(state_raw, must_exist=False)
    if state_path.exists() or state_path.is_symlink():
        raise RuntimeError(f"Import state must be fresh: {state_path}")

    selected_sources: dict[int, Path] = {}
    for record in selected:
        source_path = _resolve_source_file(source_root, record.relative_path)
        metadata = _lstat(source_path, "Selected source texture")
        if (
            metadata.st_size != record.source_size
            or metadata.st_mtime_ns != record.source_mtime_ns
            or sha256_file(source_path) != record.source_sha256
        ):
            raise RuntimeError(
                f"Selected source changed after plan validation: {record.relative_path}"
            )
        selected_sources[record.index] = source_path

    stage_manifest_raw = os.environ.get(
        "RED_STYLIZED_IMPORT_STAGE_MANIFEST", ""
    ).strip()
    if not stage_manifest_raw:
        raise RuntimeError("RED_STYLIZED_IMPORT_STAGE_MANIFEST is required")
    stage_manifest_file_sha256 = os.environ.get(
        "RED_STYLIZED_IMPORT_STAGE_MANIFEST_FILE_SHA256", ""
    ).strip().upper()
    stage_manifest_path, selected_imports = _load_stage_manifest(
        stage_manifest_raw,
        expected_manifest_file_sha256=stage_manifest_file_sha256,
        plan_path=plan_path,
        plan_file_sha256=actual_plan_file_sha256,
        plan=plan,
        categories=requested_categories,
        start=start,
        limit=limit,
        selected=selected,
        selected_sources=selected_sources,
    )

    results: list[dict[str, Any]] = []
    unreal.log_warning(
        "RED_STYLIZED_IMPORT_BEGIN "
        f"plan={plan['plan_sha256']} dataset={plan['dataset_sha256']} "
        f"filtered={filtered_count} start={start} limit={limit} "
        f"selected={len(selected)}"
    )

    new_records: list[ImportRecord] = []
    for record in selected:
        source_path = selected_sources[record.index]
        (
            _,
            import_representation,
            import_payload_sha256,
        ) = selected_imports[record.index]
        if unreal.EditorAssetLibrary.does_asset_exist(record.object_path):
            existing = unreal.EditorAssetLibrary.load_asset(record.object_path)
            if existing is None:
                raise RuntimeError(
                    f"Existing asset cannot be loaded: {record.object_path}"
                )
            _verify_texture_asset(
                unreal,
                existing,
                record,
                source_path=source_path,
                plan_sha256=plan["plan_sha256"],
                import_representation=import_representation,
                import_payload_sha256=import_payload_sha256,
            )
            results.append(
                {
                    "index": record.index,
                    "stable_source_id": record.stable_source_id,
                    "relative_path": record.relative_path,
                    "source_sha256": record.source_sha256,
                    "import_representation": import_representation,
                    "import_payload_sha256": import_payload_sha256,
                    "object_path": record.object_path,
                    "status": "verified_existing_texture",
                    "class": "Texture2D",
                    "semantic": record.semantic,
                }
            )
        else:
            new_records.append(record)

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    for chunk_start in range(0, len(new_records), 16):
        chunk = new_records[chunk_start : chunk_start + 16]
        tasks: list[object] = []
        for record in chunk:
            import_path, _, _ = selected_imports[record.index]
            unreal.EditorAssetLibrary.make_directory(record.destination_path)
            task = unreal.AssetImportTask()
            task.set_editor_property("filename", str(import_path))
            task.set_editor_property("destination_path", record.destination_path)
            task.set_editor_property("destination_name", record.destination_name)
            task.set_editor_property("automated", True)
            task.set_editor_property("replace_existing", False)
            task.set_editor_property("replace_existing_settings", False)
            task.set_editor_property("save", False)
            tasks.append(task)

        asset_tools.import_asset_tasks(tasks)
        for record, task in zip(chunk, tasks):
            imported_paths = [
                _normalize_imported_object_path(value)
                for value in list(
                    task.get_editor_property("imported_object_paths") or []
                )
            ]
            if imported_paths != [record.object_path]:
                raise RuntimeError(
                    "Unreal import output does not exactly match the plan: "
                    f"expected {record.object_path}, got {imported_paths}"
                )
            asset = unreal.EditorAssetLibrary.load_asset(record.object_path)
            if asset is None:
                raise RuntimeError(
                    f"Imported Texture2D cannot be loaded: {record.object_path}"
                )
            source_path = selected_sources[record.index]
            (
                _,
                import_representation,
                import_payload_sha256,
            ) = selected_imports[record.index]
            _set_texture_properties(unreal, asset, record.semantic)
            _set_asset_metadata(
                unreal,
                asset,
                _expected_metadata(
                    record,
                    source_path=source_path,
                    plan_sha256=plan["plan_sha256"],
                    import_representation=import_representation,
                    import_payload_sha256=import_payload_sha256,
                ),
            )
            if not unreal.EditorAssetLibrary.save_asset(
                record.object_path, only_if_is_dirty=False
            ):
                raise RuntimeError(f"Failed to save imported asset: {record.object_path}")
            _verify_texture_asset(
                unreal,
                asset,
                record,
                source_path=source_path,
                plan_sha256=plan["plan_sha256"],
                import_representation=import_representation,
                import_payload_sha256=import_payload_sha256,
            )
            results.append(
                {
                    "index": record.index,
                    "stable_source_id": record.stable_source_id,
                    "relative_path": record.relative_path,
                    "source_sha256": record.source_sha256,
                    "import_representation": import_representation,
                    "import_payload_sha256": import_payload_sha256,
                    "object_path": record.object_path,
                    "status": "imported",
                    "class": "Texture2D",
                    "semantic": record.semantic,
                }
            )
            unreal.log(
                "RED_STYLIZED_IMPORT_ASSET "
                f"index={record.index} semantic={record.semantic} "
                f"asset={record.object_path}"
            )

    results.sort(key=lambda item: int(item["index"]))
    imported_count = sum(item["status"] == "imported" for item in results)
    existing_count = sum(
        item["status"] == "verified_existing_texture" for item in results
    )
    write_json_no_clobber(
        state_path,
        _state_payload(
            plan_path=plan_path,
            plan_file_sha256=actual_plan_file_sha256,
            stage_manifest_path=stage_manifest_path,
            stage_manifest_file_sha256=stage_manifest_file_sha256,
            plan=plan,
            start=start,
            limit=limit,
            categories=requested_categories,
            results=results,
        ),
    )
    unreal.log_warning(
        "RED_STYLIZED_IMPORT_COMPLETE "
        f"selected={len(selected)} imported={imported_count} "
        f"verified_existing={existing_count} state={state_path}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Create a deterministic plan")
    plan_parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    plan_parser.add_argument(
        "--destination-root", default=DEFAULT_DESTINATION_ROOT
    )
    plan_parser.add_argument("--output", required=True)

    verify_parser = subparsers.add_parser(
        "verify-plan", help="Validate an existing plan"
    )
    verify_parser.add_argument("--plan", required=True)

    stage_parser = subparsers.add_parser(
        "stage-batch",
        help="Prepare authenticated PNG payloads for one bounded batch",
    )
    stage_parser.add_argument("--plan", required=True)
    stage_parser.add_argument("--categories", required=True)
    stage_parser.add_argument("--start", type=int, default=0)
    stage_parser.add_argument("--limit", type=int, default=64)
    stage_parser.add_argument("--output-directory", required=True)
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "plan":
        output = _validate_diagnostics_path(args.output, must_exist=False)
        plan = build_import_plan(
            args.source_root,
            args.destination_root,
            enforce_default_identity=True,
        )
        write_json_no_clobber(output, plan)
        print(
            "RED_STYLIZED_PLAN_READY "
            f"records={plan['record_count']} bytes={plan['source_bytes']} "
            f"dataset={plan['dataset_sha256']} sha256={plan['plan_sha256']} "
            f"output={output}"
        )
        return 0
    if args.command == "verify-plan":
        plan_path = _validate_diagnostics_path(args.plan, must_exist=True)
        plan, records = _load_plan(plan_path)
        print(
            "RED_STYLIZED_PLAN_VALID "
            f"records={len(records)} dataset={plan['dataset_sha256']} "
            f"sha256={plan['plan_sha256']}"
        )
        return 0
    if args.command == "stage-batch":
        categories = tuple(args.categories.split(","))
        manifest = stage_import_batch(
            args.plan,
            categories,
            args.start,
            args.limit,
            args.output_directory,
        )
        manifest_path = (
            Path(args.output_directory).resolve(strict=True)
            / STAGE_MANIFEST_FILENAME
        )
        print(
            "RED_STYLIZED_STAGE_READY "
            f"records={manifest['result_count']} "
            f"dds={manifest['staged_dds_count']} "
            f"sha256={sha256_file(manifest_path)} "
            f"manifest={manifest_path}"
        )
        return 0
    raise RuntimeError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    if os.environ.get("RED_STYLIZED_IMPORT_PLAN"):
        run_unreal_import()
    else:
        sys.exit(cli())
