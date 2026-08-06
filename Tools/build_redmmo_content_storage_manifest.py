"""Build a deterministic checksum manifest for RED MMO project content.

The manifest covers the active project descriptor, every regular file below
``Content``, and every source input below each project-local plugin. Plugin
``.git``, ``.vs``, ``Binaries``, ``DerivedDataCache``, ``Intermediate``, and
``Saved`` trees are deliberately excluded and enumerated in the report.

This tool is read-only with respect to the Unreal project. It writes one
no-clobber JSON report below the D-resident diagnostics root and does not create,
load, save, move, rename, or modify Unreal packages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


EXPECTED_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
PROJECT_DESCRIPTOR_NAME = "Titan.uproject"
CONTENT_ROOT_NAME = "Content"
PLUGINS_ROOT_NAME = "Plugins"
MANIFEST_ID = "redmmo-content-project-plugins-storage-readiness"
PROTECTED_INPUT_HASHES = {
    "Content/RedMMO/Maps/RedPlanetGen.umap": (
        "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724"
    ),
    "Content/RedMMO/Maps/RedPlanetGen_50km_Test.umap": (
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D"
    ),
    "Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap": (
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284"
    ),
    "Content/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield.uasset": (
        "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562"
    ),
}
WINDOWS_RESERVED_NAMES = {
    "AUX",
    "CON",
    "NUL",
    "PRN",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

# These are compiler/editor products, not source inputs. The exclusion applies
# only to an immediate child of a local plugin root so a similarly named folder
# inside Source/ThirdParty cannot be dropped accidentally.
EXCLUDED_PLUGIN_TOP_LEVEL_DIRECTORIES = frozenset(
    {
        ".git",
        ".vs",
        "Binaries",
        "DerivedDataCache",
        "Intermediate",
        "Saved",
    }
)


class StorageManifestError(RuntimeError):
    """Raised when a complete, trustworthy manifest cannot be produced."""


@dataclass(frozen=True)
class FileMetadata:
    size: int
    mtime_ns: int
    ctime_ns: int
    device: int
    inode: int
    mode: int
    attributes: int
    link_count: int


@dataclass(frozen=True)
class InventoryFile:
    path: Path
    relative_path: str
    scope: str
    plugin_id: str | None
    metadata: FileMetadata


def _sort_key(value: str) -> tuple[str, str]:
    return value.casefold(), value


def _metadata(path: Path) -> FileMetadata:
    try:
        observed = path.lstat()
    except OSError as error:
        raise StorageManifestError(
            f"unable to inspect path metadata: {path}: {error}"
        ) from error
    return FileMetadata(
        size=observed.st_size,
        mtime_ns=observed.st_mtime_ns,
        ctime_ns=observed.st_ctime_ns,
        device=observed.st_dev,
        inode=observed.st_ino,
        mode=observed.st_mode,
        attributes=getattr(observed, "st_file_attributes", 0),
        link_count=observed.st_nlink,
    )


def _is_link_or_reparse(path: Path, metadata: FileMetadata | None = None) -> bool:
    observed = metadata or _metadata(path)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(observed.mode) or bool(
        reparse_flag and observed.attributes & reparse_flag
    )


def _require_directory(path: Path, project_root: Path) -> None:
    observed = _metadata(path)
    if _is_link_or_reparse(path, observed):
        raise StorageManifestError(f"linked or reparse directory is forbidden: {path}")
    if not stat.S_ISDIR(observed.mode):
        raise StorageManifestError(f"required directory is missing: {path}")
    _require_within_project(path, project_root)


def _validate_project_root(project_root: Path) -> Path:
    lexical_root = project_root.absolute()
    observed = _metadata(lexical_root)
    if _is_link_or_reparse(lexical_root, observed):
        raise StorageManifestError(
            f"linked or reparse project root is forbidden: {lexical_root}"
        )
    if not stat.S_ISDIR(observed.mode):
        raise StorageManifestError(
            f"project root is not a directory: {lexical_root}"
        )
    try:
        return lexical_root.resolve(strict=True)
    except OSError as error:
        raise StorageManifestError(
            f"project root cannot be resolved: {lexical_root}: {error}"
        ) from error


def _require_within_project(path: Path, project_root: Path) -> None:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(project_root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise StorageManifestError(
            f"path escapes or cannot be resolved inside project root: {path}"
        ) from error


def _require_regular_file(path: Path, project_root: Path) -> FileMetadata:
    observed = _metadata(path)
    if _is_link_or_reparse(path, observed):
        raise StorageManifestError(f"linked or reparse file is forbidden: {path}")
    if not stat.S_ISREG(observed.mode):
        raise StorageManifestError(f"non-regular file is forbidden: {path}")
    if observed.link_count != 1:
        raise StorageManifestError(
            f"hard-linked input is forbidden because alias topology is not stored: "
            f"{path} links={observed.link_count}"
        )
    _require_within_project(path, project_root)
    return observed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise StorageManifestError(f"unable to read input file {path}: {error}") from error
    return digest.hexdigest().upper()


def _walk_regular_files(root: Path, project_root: Path) -> list[Path]:
    """Return a complete deterministic file list, rejecting every reparse."""

    _require_directory(root, project_root)
    files: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            children = sorted(
                (Path(entry.path) for entry in os.scandir(directory)),
                key=lambda path: _sort_key(path.name),
            )
        except OSError as error:
            raise StorageManifestError(
                f"unable to enumerate input directory {directory}: {error}"
            ) from error
        child_directories: list[Path] = []
        for child in children:
            observed = _metadata(child)
            if _is_link_or_reparse(child, observed):
                raise StorageManifestError(
                    f"linked or reparse input blocks complete storage inventory: {child}"
                )
            if stat.S_ISDIR(observed.mode):
                _require_within_project(child, project_root)
                child_directories.append(child)
            elif stat.S_ISREG(observed.mode):
                _require_within_project(child, project_root)
                files.append(child)
            else:
                raise StorageManifestError(
                    f"non-regular input blocks complete storage inventory: {child}"
                )
        pending.extend(reversed(child_directories))
    return sorted(files, key=lambda path: _sort_key(path.as_posix()))


def _read_json_object(path: Path, project_root: Path) -> dict[str, object]:
    _require_regular_file(path, project_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StorageManifestError(f"invalid JSON descriptor {path}: {error}") from error
    if not isinstance(payload, dict):
        raise StorageManifestError(f"JSON descriptor must contain an object: {path}")
    return payload


def _project_plugin_states(
    project_descriptor: Mapping[str, object],
) -> dict[str, bool]:
    plugin_rows = project_descriptor.get("Plugins", [])
    if not isinstance(plugin_rows, list):
        raise StorageManifestError("project descriptor Plugins field must be a list")
    states: dict[str, bool] = {}
    for row in plugin_rows:
        if not isinstance(row, dict):
            raise StorageManifestError("project descriptor plugin row must be an object")
        name = row.get("Name")
        enabled = row.get("Enabled")
        if not isinstance(name, str) or not name:
            raise StorageManifestError("project descriptor plugin Name is invalid")
        if not isinstance(enabled, bool):
            raise StorageManifestError(
                f"project descriptor plugin Enabled is invalid: {name}"
            )
        folded = name.casefold()
        if folded in (existing.casefold() for existing in states):
            raise StorageManifestError(
                f"duplicate project descriptor plugin name: {name}"
            )
        states[name] = enabled
    return states


def _plugin_descriptor(plugin_root: Path, project_root: Path) -> Path:
    try:
        descriptors = [
            child
            for child in plugin_root.iterdir()
            if child.is_file() and child.suffix.casefold() == ".uplugin"
        ]
    except OSError as error:
        raise StorageManifestError(
            f"unable to enumerate plugin descriptor: {plugin_root}: {error}"
        ) from error
    descriptors = sorted(descriptors, key=lambda path: _sort_key(path.name))
    if len(descriptors) != 1:
        raise StorageManifestError(
            f"plugin root must contain exactly one .uplugin descriptor: "
            f"{plugin_root} observed={len(descriptors)}"
        )
    _require_regular_file(descriptors[0], project_root)
    return descriptors[0]


def _plugin_input_files(
    plugin_root: Path,
    project_root: Path,
) -> tuple[list[Path], list[str]]:
    _require_directory(plugin_root, project_root)
    try:
        children = sorted(plugin_root.iterdir(), key=lambda path: _sort_key(path.name))
    except OSError as error:
        raise StorageManifestError(
            f"unable to enumerate plugin root {plugin_root}: {error}"
        ) from error

    files: list[Path] = []
    excluded_present: list[str] = []
    excluded_folded = {
        value.casefold() for value in EXCLUDED_PLUGIN_TOP_LEVEL_DIRECTORIES
    }
    for child in children:
        observed = _metadata(child)
        if _is_link_or_reparse(child, observed):
            raise StorageManifestError(
                f"linked or reparse plugin input is forbidden: {child}"
            )
        if child.name.casefold() in excluded_folded:
            if stat.S_ISDIR(observed.mode):
                excluded_present.append(child.name)
                continue
            raise StorageManifestError(
                f"generated plugin exclusion name is not a directory: {child}"
            )
        if stat.S_ISDIR(observed.mode):
            files.extend(_walk_regular_files(child, project_root))
        elif stat.S_ISREG(observed.mode):
            _require_within_project(child, project_root)
            files.append(child)
        else:
            raise StorageManifestError(f"non-regular plugin input is forbidden: {child}")
    return (
        sorted(files, key=lambda path: _sort_key(path.as_posix())),
        sorted(excluded_present, key=_sort_key),
    )


def _validate_relative_path(relative_path: str) -> None:
    if not relative_path or relative_path.startswith(("/", "\\")):
        raise StorageManifestError(f"invalid project-relative path: {relative_path!r}")
    if unicodedata.normalize("NFC", relative_path) != relative_path:
        raise StorageManifestError(
            f"non-NFC project-relative path is forbidden: {relative_path!r}"
        )
    for component in relative_path.split("/"):
        if component in {"", ".", ".."}:
            raise StorageManifestError(
                f"unsafe project-relative path component: {relative_path!r}"
            )
        if ":" in component or any(ord(character) < 32 for character in component):
            raise StorageManifestError(
                f"ADS or control-character path component is forbidden: "
                f"{relative_path!r}"
            )
        if component.endswith((" ", ".")):
            raise StorageManifestError(
                f"trailing space or dot path component is forbidden: "
                f"{relative_path!r}"
            )
        reserved_stem = component.split(".", 1)[0].upper()
        if reserved_stem in WINDOWS_RESERVED_NAMES:
            raise StorageManifestError(
                f"reserved Windows path component is forbidden: {relative_path!r}"
            )


def _ensure_casefold_unique(inventory: Sequence[InventoryFile]) -> None:
    seen: dict[str, str] = {}
    for item in inventory:
        _validate_relative_path(item.relative_path)
        folded = item.relative_path.casefold()
        previous = seen.get(folded)
        if previous is not None and previous != item.relative_path:
            raise StorageManifestError(
                f"case-insensitive path collision: {previous} and {item.relative_path}"
            )
        if previous is not None:
            raise StorageManifestError(f"duplicate inventory path: {item.relative_path}")
        seen[folded] = item.relative_path


def _discover_inventory(
    project_root: Path,
) -> tuple[list[InventoryFile], list[dict[str, object]], dict[str, object]]:
    project_root = _validate_project_root(project_root)
    _require_directory(project_root, project_root)
    descriptor = project_root / PROJECT_DESCRIPTOR_NAME
    content_root = project_root / CONTENT_ROOT_NAME
    plugins_root = project_root / PLUGINS_ROOT_NAME
    project_payload = _read_json_object(descriptor, project_root)
    plugin_states = _project_plugin_states(project_payload)
    plugin_states_folded = {
        name.casefold(): (name, enabled) for name, enabled in plugin_states.items()
    }
    _require_directory(content_root, project_root)
    _require_directory(plugins_root, project_root)

    pending: list[tuple[Path, str, str | None]] = [
        (descriptor, "project_descriptor", None)
    ]
    pending.extend(
        (path, "project_content", None)
        for path in _walk_regular_files(content_root, project_root)
    )

    plugin_records: list[dict[str, object]] = []
    try:
        plugin_root_children = sorted(
            plugins_root.iterdir(),
            key=lambda path: _sort_key(path.name),
        )
    except OSError as error:
        raise StorageManifestError(
            f"unable to enumerate local plugins: {plugins_root}: {error}"
        ) from error
    plugin_roots: list[Path] = []
    for child in plugin_root_children:
        observed = _metadata(child)
        if _is_link_or_reparse(child, observed):
            raise StorageManifestError(
                f"linked or reparse direct Plugins child is forbidden: {child}"
            )
        if not stat.S_ISDIR(observed.mode):
            raise StorageManifestError(
                f"unexpected non-directory entry under Plugins: {child}"
            )
        plugin_roots.append(child)
    if not plugin_roots:
        raise StorageManifestError("no project-local plugins were found")

    seen_plugin_ids: set[str] = set()
    for plugin_root in plugin_roots:
        _require_directory(plugin_root, project_root)
        plugin_descriptor = _plugin_descriptor(plugin_root, project_root)
        plugin_payload = _read_json_object(plugin_descriptor, project_root)
        plugin_id = plugin_descriptor.stem
        folded_id = plugin_id.casefold()
        if folded_id in seen_plugin_ids:
            raise StorageManifestError(f"duplicate local plugin ID: {plugin_id}")
        seen_plugin_ids.add(folded_id)
        files, excluded_present = _plugin_input_files(plugin_root, project_root)
        if plugin_descriptor not in files:
            raise StorageManifestError(
                f"plugin descriptor is missing from selected input files: {plugin_descriptor}"
            )
        nested_descriptors = [
            path for path in files if path.suffix.casefold() == ".uplugin"
        ]
        if nested_descriptors != [plugin_descriptor]:
            raise StorageManifestError(
                f"nested or ambiguous plugin descriptors are forbidden: "
                f"{plugin_root} observed={len(nested_descriptors)}"
            )
        pending.extend((path, "project_plugin", plugin_id) for path in files)
        configured = plugin_states_folded.get(folded_id)
        plugin_records.append(
            {
                "plugin_id": plugin_id,
                "plugin_root": plugin_root.relative_to(project_root).as_posix(),
                "descriptor_path": plugin_descriptor.relative_to(
                    project_root
                ).as_posix(),
                "friendly_name": plugin_payload.get("FriendlyName"),
                "version_name": plugin_payload.get("VersionName"),
                "created_by": plugin_payload.get("CreatedBy"),
                "installed": plugin_payload.get("Installed"),
                "can_contain_content": plugin_payload.get("CanContainContent"),
                "listed_in_project_descriptor": configured is not None,
                "enabled_in_project_descriptor": configured[1] if configured else None,
                "excluded_generated_top_level_directories_present": excluded_present,
            }
        )

    inventory: list[InventoryFile] = []
    for path, scope, plugin_id in pending:
        observed = _require_regular_file(path, project_root)
        inventory.append(
            InventoryFile(
                path=path,
                relative_path=path.relative_to(project_root).as_posix(),
                scope=scope,
                plugin_id=plugin_id,
                metadata=observed,
            )
        )
    inventory.sort(key=lambda item: _sort_key(item.relative_path))
    _ensure_casefold_unique(inventory)
    return inventory, plugin_records, project_payload


def _inventory_snapshot(
    inventory: Sequence[InventoryFile],
) -> dict[str, FileMetadata]:
    return {item.relative_path: item.metadata for item in inventory}


def _signature(entries: Sequence[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda row: _sort_key(str(row["path"]))):
        canonical = json.dumps(
            [entry["path"], entry["bytes"], entry["sha256"]],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest.update(canonical.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def _path_signature(entries: Sequence[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda row: _sort_key(str(row["path"]))):
        digest.update(
            json.dumps(
                entry["path"],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest().upper()


def build_storage_manifest(
    project_root: Path,
    *,
    protected_hashes: Mapping[str, str] = PROTECTED_INPUT_HASHES,
) -> dict[str, object]:
    project_root = _validate_project_root(project_root)
    inventory_before, plugin_records, project_payload = _discover_inventory(
        project_root
    )
    before_snapshot = _inventory_snapshot(inventory_before)

    entries: list[dict[str, object]] = []
    for item in inventory_before:
        digest = sha256_file(item.path)
        after_hash = _require_regular_file(item.path, project_root)
        if after_hash != item.metadata:
            raise StorageManifestError(
                f"input changed while it was being hashed: {item.relative_path}"
            )
        entries.append(
            {
                "path": item.relative_path,
                "scope": item.scope,
                "plugin_id": item.plugin_id,
                "bytes": item.metadata.size,
                "sha256": digest,
            }
        )

    inventory_after, plugins_after, project_payload_after = _discover_inventory(
        project_root
    )
    if before_snapshot != _inventory_snapshot(inventory_after):
        raise StorageManifestError(
            "selected Content or project-plugin inputs changed during inventory"
        )
    if plugin_records != plugins_after or project_payload != project_payload_after:
        raise StorageManifestError(
            "project or plugin descriptor state changed during inventory"
        )

    entries.sort(key=lambda row: _sort_key(str(row["path"])))
    entries_by_path = {str(row["path"]): row for row in entries}
    protected_records: list[dict[str, object]] = []
    for relative_path, expected_hash in sorted(
        protected_hashes.items(), key=lambda item: _sort_key(item[0])
    ):
        record = entries_by_path.get(relative_path)
        if record is None:
            raise StorageManifestError(
                f"protected input is missing from storage inventory: {relative_path}"
            )
        observed_hash = str(record["sha256"])
        if observed_hash != expected_hash:
            raise StorageManifestError(
                f"protected input hash mismatch: {relative_path} "
                f"expected={expected_hash} observed={observed_hash}"
            )
        protected_records.append(
            {
                "path": relative_path,
                "expected_sha256": expected_hash,
                "observed_sha256": observed_hash,
                "matches": True,
            }
        )
    content_entries = [row for row in entries if row["scope"] == "project_content"]
    descriptor_entries = [
        row for row in entries if row["scope"] == "project_descriptor"
    ]
    if len(descriptor_entries) != 1:
        raise StorageManifestError("project descriptor inventory is incomplete")
    plugin_entries_by_id: dict[str, list[dict[str, object]]] = {}
    for row in entries:
        plugin_id = row.get("plugin_id")
        if isinstance(plugin_id, str):
            plugin_entries_by_id.setdefault(plugin_id, []).append(row)

    for plugin in plugin_records:
        plugin_id = str(plugin["plugin_id"])
        members = plugin_entries_by_id.get(plugin_id, [])
        if not members:
            raise StorageManifestError(f"plugin input inventory is empty: {plugin_id}")
        plugin["file_count"] = len(members)
        plugin["bytes"] = sum(int(row["bytes"]) for row in members)
        plugin["signature_sha256"] = _signature(members)
        descriptor_row = next(
            (
                row
                for row in members
                if row["path"] == plugin["descriptor_path"]
            ),
            None,
        )
        if descriptor_row is None:
            raise StorageManifestError(
                f"plugin descriptor entry is missing: {plugin['descriptor_path']}"
            )
        plugin["descriptor_sha256"] = descriptor_row["sha256"]

    scope_counts = Counter(str(row["scope"]) for row in entries)
    builder_path = Path(__file__)
    project_modules = project_payload.get("Modules")
    if not isinstance(project_modules, list):
        raise StorageManifestError("project descriptor Modules field must be a list")

    return {
        "schema_version": 1,
        "manifest_id": MANIFEST_ID,
        "evidence_class": "static",
        "status": "checksummed_source_inputs_ready_external_storage_unverified",
        "project_identity": {
            "descriptor_path": PROJECT_DESCRIPTOR_NAME,
            "descriptor_sha256": descriptor_entries[0]["sha256"],
            "engine_association": project_payload.get("EngineAssociation"),
            "module_names": sorted(
                str(row.get("Name"))
                for row in project_modules
                if isinstance(row, dict) and isinstance(row.get("Name"), str)
            ),
        },
        "selection_policy": {
            "content_root": CONTENT_ROOT_NAME,
            "plugins_root": PLUGINS_ROOT_NAME,
            "content_files": "all_regular_files_recursive",
            "plugin_files": (
                "all_regular_files_recursive_except_immediate_generated_roots"
            ),
            "excluded_plugin_top_level_directories": sorted(
                EXCLUDED_PLUGIN_TOP_LEVEL_DIRECTORIES,
                key=_sort_key,
            ),
            "links_reparse_points_and_non_regular_files": "fail_closed",
            "concurrent_selected_input_change": "fail_closed",
            "output_policy": "external_diagnostics_atomic_no_clobber",
            "empty_directories": "not_represented",
            "ntfs_acl_owner_and_timestamp_metadata": "not_represented",
            "named_ntfs_alternate_streams": "not_represented",
        },
        "provenance": {
            "builder_path": "Tools/build_redmmo_content_storage_manifest.py",
            "builder_sha256": sha256_file(builder_path),
            "signature_kind": (
                "sha256_sorted_canonical_json_tuples_path_bytes_sha256"
            ),
        },
        "scope": {
            "file_count": len(entries),
            "bytes": sum(int(row["bytes"]) for row in entries),
            "signature_sha256": _signature(entries),
            "path_set_signature_sha256": _path_signature(entries),
            "scope_file_counts": dict(sorted(scope_counts.items())),
            "project_content_file_count": len(content_entries),
            "project_content_bytes": sum(
                int(row["bytes"]) for row in content_entries
            ),
            "project_content_signature_sha256": _signature(content_entries),
            "project_plugin_count": len(plugin_records),
            "tree_quiescent_during_scan": True,
        },
        "storage_verification": {
            "external_storage_copied": False,
            "external_storage_access_control_verified": False,
            "restore_tested": False,
            "manifest_only": True,
        },
        "protected_inputs": protected_records,
        "plugins": sorted(
            plugin_records, key=lambda row: _sort_key(str(row["plugin_id"]))
        ),
        "entries": entries,
        "claim_limit": (
            "This static manifest authenticates selected project source inputs for "
            "storage readiness only. Plugin .git, .vs, Binaries, DerivedDataCache, "
            "Intermediate, and Saved trees, plus empty directories, named NTFS "
            "streams, ACLs, owners, and timestamps are not represented. It is not "
            "an external backup, "
            "access-control audit, restore test, license approval, dependency proof, "
            "Unreal load or save, build, runtime, visual, gameplay, package, Steam, "
            "or multiplayer evidence."
        ),
    }


def manifest_bytes(manifest: Mapping[str, object]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_output_path(
    output_path: Path,
    *,
    diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT,
) -> Path:
    lexical_root = diagnostics_root.absolute()
    lexical_output = output_path.absolute()
    if lexical_output.suffix.casefold() != ".json":
        raise StorageManifestError(
            f"output must use a .json suffix: {lexical_output}"
        )
    try:
        lexical_output.relative_to(lexical_root)
    except ValueError as error:
        raise StorageManifestError(
            f"output is restricted to diagnostics root {lexical_root}: "
            f"{lexical_output}"
        ) from error
    if lexical_output.exists():
        raise StorageManifestError(f"refusing to overwrite output: {lexical_output}")

    cursor = lexical_output.parent
    while True:
        if cursor.exists() and _is_link_or_reparse(cursor):
            raise StorageManifestError(
                f"linked or reparse output ancestor is forbidden: {cursor}"
            )
        if cursor == lexical_root:
            break
        if cursor.parent == cursor:
            raise StorageManifestError(
                f"output ancestor did not reach diagnostics root: {lexical_output}"
            )
        cursor = cursor.parent

    resolved_root = lexical_root.resolve(strict=True)
    resolved_output = lexical_output.resolve()
    try:
        resolved_output.relative_to(resolved_root)
    except ValueError as error:
        raise StorageManifestError(
            f"resolved output escapes diagnostics root {resolved_root}: "
            f"{resolved_output}"
        ) from error
    return resolved_output


def write_manifest_atomic(output_path: Path, payload: bytes) -> None:
    if output_path.exists():
        raise StorageManifestError(f"refusing to overwrite output: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(temporary_name, output_path)
    finally:
        temporary_path = Path(temporary_name)
        if temporary_path.exists():
            temporary_path.unlink()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=EXPECTED_PROJECT_ROOT,
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = _validate_project_root(args.project_root)
    if project_root != EXPECTED_PROJECT_ROOT:
        raise StorageManifestError(
            f"expected project root {EXPECTED_PROJECT_ROOT}, observed {project_root}"
        )
    output_path = validate_output_path(args.output)
    manifest = build_storage_manifest(project_root)
    output_path = validate_output_path(args.output)
    write_manifest_atomic(output_path, manifest_bytes(manifest))
    scope = manifest["scope"]
    print(
        "REDMMO_CONTENT_STORAGE_MANIFEST_OK "
        f"files={scope['file_count']} "
        f"bytes={scope['bytes']} "
        f"plugins={scope['project_plugin_count']} "
        f"signature={scope['signature_sha256']} "
        f"output={output_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (StorageManifestError, json.JSONDecodeError) as error:
        print(f"REDMMO_CONTENT_STORAGE_MANIFEST_FAILED {error}", file=os.sys.stderr)
        raise SystemExit(2)
