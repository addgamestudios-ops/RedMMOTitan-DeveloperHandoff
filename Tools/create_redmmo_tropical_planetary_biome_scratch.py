"""Create one authenticated RedMMO Tropical planetary-biome scratch clone.

This transaction deliberately does not edit the source project or vendor pack.
It copies the exact functional RedMMO project scope into a fresh staging
directory, adds only the 51 packages authenticated by the pinned UE 5.8 Asset
Registry closure, verifies every byte, and atomically renames the staging
directory to the explicitly requested scratch destination.

The destination is restricted to ``D:\RedMMOTitanWindowsData\Scratch`` and the
immutable manifest/status records are restricted to
``D:\RedMMOTitanWindowsData\Diagnostics``.  A failure never deletes a partial
clone.  It retains that clone and publishes a failure status so cleanup remains
an explicit, separately reviewed action.

This is a filesystem staging transaction only.  It does not launch Unreal,
load or save a package, create a map, enable a provider, or establish visual,
gameplay, migration, performance, or production-integration evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


EXPECTED_PROJECT_ROOT = Path(r"D:\RedMMOTitan")
SCRATCH_ROOT = Path(r"D:\RedMMOTitanWindowsData\Scratch")
DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
TROPICAL_CONTENT_ROOT = Path(
    r"D:\RedMMOTitanWindowsData\UserUnrealProjects"
    r"\StylizedNatureTropicalIs\Content"
)
CLOSURE_PATH = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\M07_TropicalPlanetBiome_20260725_203801Z"
    r"\tropical_planetary_biome_closure.json"
)
CLOSURE_SHA256 = (
    "88EDBB32281812F40C3A36B380835B5DAC4263DB488E189BBF74D69749DC7CF2"
)
TROPICAL_PACK_ID = "fab.934c1286-7388-4aa5-a300-e0a7cdf65675"
TROPICAL_PACKAGE_PREFIX = PurePosixPath("Zenscape_Island")
PROJECT_DESCRIPTOR = "Titan.uproject"
PROJECT_DIRECTORY_SCOPES = (
    "Config",
    "Source",
    "Content",
    "Plugins",
    "Binaries",
    "Build",
)
EXPECTED_CLOSURE_GROUP_COUNTS = {
    "core": 38,
    "coral_optional": 8,
    "cloud_conditional": 5,
}
EXPECTED_SEED_COUNT = 16
EXPECTED_UNION_COUNT = 51
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
# These sentinels bind this tool to the already-reviewed project identity rule:
# SHA-256(pack_id + "\n" + path-relative-to-pack-root), first 24 hex digits.
KNOWN_STABLE_ID_SENTINELS = {
    "Model/Tree/SM_CoconutTree_01.uasset": (
        "RED-FAB-ASSET-020D6DAAE70219B6F907C75B"
    ),
    "Model/Plants/SM_Plant_01.uasset": (
        "RED-FAB-ASSET-71C6AF42FBE6C8C807395EC0"
    ),
    "Model/Plants/SM_Coral_01.uasset": (
        "RED-FAB-ASSET-3897AB32061911E704F9DEB4"
    ),
}
COPY_BLOCK_BYTES = 4 * 1024 * 1024
STAGING_LEAF_PREFIX = ".tbv1a-p-"
STAGING_NONCE_HEX_LENGTH = 8
WINDOWS_LEGACY_MAX_PATH_CHARS = 259


class ScratchCloneRefusal(RuntimeError):
    """Raised when the transaction cannot prove a no-clobber exact copy."""


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
class AuthenticatedFile:
    source_path: Path
    destination_relative_path: str
    source_kind: str
    source_scope: str
    source_relative_path: str
    bytes: int
    sha256: str
    metadata: FileMetadata

    def manifest_row(self) -> dict[str, object]:
        return {
            "bytes": self.bytes,
            "destination_relative_path": self.destination_relative_path,
            "sha256": self.sha256,
            "source_kind": self.source_kind,
            "source_path": self.source_path.as_posix(),
            "source_relative_path": self.source_relative_path,
            "source_scope": self.source_scope,
        }


@dataclass
class TransactionState:
    transaction_id: str
    destination: Path
    diagnostics_dir: Path
    staging_path: Path
    started_utc: str
    status_sequence: int = 0
    diagnostics_created: bool = False
    staging_created: bool = False
    destination_finalized: bool = False


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _sort_key(value: str) -> tuple[str, str]:
    return value.casefold(), value


def _staging_leaf(transaction_id: str) -> str:
    """Keep the private staging path short while evidence retains the full ID."""

    nonce = transaction_id.rsplit("-", 1)[-1]
    if (
        len(nonce) != STAGING_NONCE_HEX_LENGTH
        or any(character not in "0123456789ABCDEF" for character in nonce)
    ):
        raise ScratchCloneRefusal(
            "transaction ID must end in exactly eight uppercase hex digits"
        )
    return STAGING_LEAF_PREFIX + nonce


def _metadata(path: Path) -> FileMetadata:
    try:
        observed = path.lstat()
    except OSError as error:
        raise ScratchCloneRefusal(
            f"unable to inspect filesystem object {path}: {error}"
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


def _is_reparse(metadata: FileMetadata) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.mode) or bool(
        metadata.attributes & reparse_flag
    )


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _require_d_drive(path: Path, label: str) -> None:
    if path.drive.casefold() != "d:" or path.anchor.startswith("\\\\"):
        raise ScratchCloneRefusal(f"{label} must be a local D: path: {path}")


def _reject_existing_reparse_chain(path: Path, label: str) -> None:
    """Reject every existing path component without following missing leaves."""

    lexical = _absolute_lexical(path)
    components: list[Path] = []
    cursor = lexical
    while True:
        if _lexists(cursor):
            components.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    for component in reversed(components):
        observed = _metadata(component)
        if _is_reparse(observed):
            raise ScratchCloneRefusal(
                f"{label} path chain contains a link/reparse point: {component}"
            )


def _resolved_within(path: Path, root: Path, label: str) -> Path:
    lexical_path = _absolute_lexical(path)
    lexical_root = _absolute_lexical(root)
    _reject_existing_reparse_chain(lexical_root, f"{label} root")
    _reject_existing_reparse_chain(lexical_path, label)
    try:
        resolved_root = lexical_root.resolve(strict=True)
        resolved_path = lexical_path.resolve(strict=False)
        resolved_path.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise ScratchCloneRefusal(
            f"{label} escapes or cannot resolve beneath {lexical_root}: "
            f"{lexical_path}"
        ) from error
    if resolved_path == resolved_root:
        raise ScratchCloneRefusal(
            f"{label} must name a child of {resolved_root}, not the root itself"
        )
    return resolved_path


def _paths_overlap(left: Path, right: Path) -> bool:
    left_resolved = left.resolve(strict=False)
    right_resolved = right.resolve(strict=False)
    try:
        left_resolved.relative_to(right_resolved)
        return True
    except ValueError:
        pass
    try:
        right_resolved.relative_to(left_resolved)
        return True
    except ValueError:
        return False


def _require_directory(path: Path, label: str) -> FileMetadata:
    observed = _metadata(path)
    if _is_reparse(observed):
        raise ScratchCloneRefusal(f"{label} cannot be linked/reparse: {path}")
    if not stat.S_ISDIR(observed.mode):
        raise ScratchCloneRefusal(f"{label} is not a directory: {path}")
    return observed


def _require_regular_file(path: Path, label: str) -> FileMetadata:
    observed = _metadata(path)
    if _is_reparse(observed):
        raise ScratchCloneRefusal(f"{label} cannot be linked/reparse: {path}")
    if not stat.S_ISREG(observed.mode):
        raise ScratchCloneRefusal(f"{label} is not a regular file: {path}")
    return observed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(COPY_BLOCK_BYTES), b""):
                digest.update(block)
    except OSError as error:
        raise ScratchCloneRefusal(f"unable to hash {path}: {error}") from error
    return digest.hexdigest().upper()


def _hash_regular_file_stable(
    path: Path,
    label: str,
) -> tuple[FileMetadata, str]:
    before = _require_regular_file(path, label)
    digest = _sha256_file(path)
    after = _require_regular_file(path, label)
    if before != after:
        raise ScratchCloneRefusal(
            f"{label} changed while it was authenticated: {path}"
        )
    if after.size < 0:
        raise ScratchCloneRefusal(f"{label} reports an invalid size: {path}")
    return after, digest


def _strict_json_pairs(
    pairs: Sequence[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ScratchCloneRefusal(f"duplicate JSON member refused: {key!r}")
        result[key] = value
    return result


def _load_strict_json(path: Path) -> tuple[dict[str, object], bytes]:
    _require_regular_file(path, "closure JSON")
    try:
        payload = path.read_bytes()
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_json_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ScratchCloneRefusal(
                    f"non-finite JSON constant refused: {value}"
                )
            ),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScratchCloneRefusal(f"invalid closure JSON {path}: {error}") from error
    if not isinstance(parsed, dict):
        raise ScratchCloneRefusal("closure JSON must contain one object")
    return parsed, payload


def _plain_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ScratchCloneRefusal(f"{label} must be an object")
    return value


def _plain_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ScratchCloneRefusal(f"{label} must be an array")
    return value


def _required_string(row: Mapping[str, object], key: str, label: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ScratchCloneRefusal(f"{label}.{key} must be a nonempty string")
    return value


def _required_integer(row: Mapping[str, object], key: str, label: str) -> int:
    value = row.get(key)
    if type(value) is not int or value < 0:
        raise ScratchCloneRefusal(f"{label}.{key} must be a nonnegative integer")
    return value


def _validate_sha256(value: str, label: str) -> str:
    if len(value) != 64 or any(character not in "0123456789ABCDEF" for character in value):
        raise ScratchCloneRefusal(f"{label} must be uppercase SHA-256")
    return value


def _safe_posix_relative(raw: str, label: str) -> str:
    if "\\" in raw or ":" in raw or "\x00" in raw:
        raise ScratchCloneRefusal(f"unsafe {label}: {raw!r}")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise ScratchCloneRefusal(f"unsafe {label}: {raw!r}")
    return relative.as_posix()


def _stable_asset_id(relative_source_path: str) -> str:
    identity = f"{TROPICAL_PACK_ID}\n{relative_source_path}".encode("utf-8")
    return (
        "RED-FAB-ASSET-"
        + hashlib.sha256(identity).hexdigest()[:24].upper()
    )


def _validate_stable_id_rule() -> None:
    for relative_path, expected in KNOWN_STABLE_ID_SENTINELS.items():
        observed = _stable_asset_id(relative_path)
        if observed != expected:
            raise ScratchCloneRefusal(
                "stable-ID rule no longer matches the reviewed crosspack "
                f"identity for {relative_path}: {observed} != {expected}"
            )


def _pack_relative_path(relative_content_path: str) -> str:
    relative = PurePosixPath(
        _safe_posix_relative(relative_content_path, "relative_content_path")
    )
    try:
        pack_relative = relative.relative_to(TROPICAL_PACKAGE_PREFIX)
    except ValueError as error:
        raise ScratchCloneRefusal(
            "closure package is outside Zenscape_Island: "
            f"{relative_content_path}"
        ) from error
    if pack_relative.suffix.casefold() != ".uasset":
        raise ScratchCloneRefusal(
            f"closure package is not one .uasset: {relative_content_path}"
        )
    return pack_relative.as_posix()


def _closure_package_from_relative(relative_content_path: str) -> str:
    relative = PurePosixPath(relative_content_path)
    return "/Game/" + relative.with_suffix("").as_posix()


def _validate_closure() -> tuple[
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    metadata_before = _require_regular_file(CLOSURE_PATH, "closure JSON")
    closure, payload = _load_strict_json(CLOSURE_PATH)
    metadata_after = _require_regular_file(CLOSURE_PATH, "closure JSON")
    if metadata_before != metadata_after:
        raise ScratchCloneRefusal("closure JSON changed while it was read")
    observed_closure_sha = hashlib.sha256(payload).hexdigest().upper()
    if observed_closure_sha != CLOSURE_SHA256:
        raise ScratchCloneRefusal(
            "closure JSON byte identity changed: "
            f"{observed_closure_sha} != {CLOSURE_SHA256}"
        )
    if closure.get("schema_version") != 1:
        raise ScratchCloneRefusal("closure schema_version must be exact integer 1")
    if closure.get("probe") != "tropical_planetary_biome_ue58_asset_registry_closure":
        raise ScratchCloneRefusal("closure probe identity is not authoritative")
    if closure.get("pack_root") != "/Game/Zenscape_Island":
        raise ScratchCloneRefusal("closure pack_root must be /Game/Zenscape_Island")
    if closure.get("dirty_before") != {"content": [], "maps": []}:
        raise ScratchCloneRefusal("closure dirty_before proof is not empty")
    if closure.get("dirty_after") != {"content": [], "maps": []}:
        raise ScratchCloneRefusal("closure dirty_after proof is not empty")
    if closure.get("saved_packages") != 0 or closure.get("mutation_calls") != 0:
        raise ScratchCloneRefusal("closure contains a save or mutation record")

    group_rows = _plain_list(closure.get("groups"), "closure.groups")
    if len(group_rows) != len(EXPECTED_CLOSURE_GROUP_COUNTS):
        raise ScratchCloneRefusal("closure must contain exactly three reviewed groups")

    package_by_name: dict[str, dict[str, object]] = {}
    package_casefolds: set[str] = set()
    group_manifests: list[dict[str, object]] = []
    seed_group_membership: dict[str, str] = {}

    for group_index, raw_group in enumerate(group_rows):
        group = _plain_mapping(raw_group, f"closure.groups[{group_index}]")
        group_name = _required_string(
            group, "group", f"closure.groups[{group_index}]"
        )
        if group_name not in EXPECTED_CLOSURE_GROUP_COUNTS:
            raise ScratchCloneRefusal(f"unexpected closure group: {group_name}")
        if any(
            record["group"] == group_name
            for record in group_manifests
        ):
            raise ScratchCloneRefusal(f"duplicate closure group: {group_name}")
        if group.get("eligible_for_staging") is not True:
            raise ScratchCloneRefusal(
                f"closure group is not eligible_for_staging: {group_name}"
            )
        if group.get("missing_external_game_leaves") != []:
            raise ScratchCloneRefusal(
                f"closure group has missing external Game leaves: {group_name}"
            )
        rows = _plain_list(
            group.get("closure_packages"),
            f"closure group {group_name}.closure_packages",
        )
        expected_count = EXPECTED_CLOSURE_GROUP_COUNTS[group_name]
        if len(rows) != expected_count or group.get("closure_count") != expected_count:
            raise ScratchCloneRefusal(
                f"closure group {group_name} count changed: {len(rows)}"
            )
        group_package_names: list[str] = []
        for package_index, raw_package in enumerate(rows):
            package = _plain_mapping(
                raw_package,
                f"closure group {group_name}.closure_packages[{package_index}]",
            )
            label = f"closure package {group_name}[{package_index}]"
            package_name = _required_string(package, "package_name", label)
            relative_content_path = _required_string(
                package, "relative_content_path", label
            )
            relative_content_path = _safe_posix_relative(
                relative_content_path, f"{label}.relative_content_path"
            )
            relative_source_path = _pack_relative_path(relative_content_path)
            if package_name != _closure_package_from_relative(relative_content_path):
                raise ScratchCloneRefusal(
                    f"{label} package/path identity mismatch: {package_name}"
                )
            if not package_name.startswith("/Game/Zenscape_Island/"):
                raise ScratchCloneRefusal(
                    f"{label} escapes Tropical package root: {package_name}"
                )
            folded = package_name.casefold()
            if folded in package_casefolds:
                raise ScratchCloneRefusal(
                    f"duplicate/case-colliding union package: {package_name}"
                )
            package_casefolds.add(folded)
            package_bytes = _required_integer(package, "bytes", label)
            package_sha = _validate_sha256(
                _required_string(package, "sha256", label),
                f"{label}.sha256",
            )
            assets = _plain_list(package.get("assets"), f"{label}.assets")
            if not assets:
                raise ScratchCloneRefusal(f"{label} has no Asset Registry assets")
            normalized_assets: list[dict[str, str]] = []
            for asset_index, raw_asset in enumerate(assets):
                asset = _plain_mapping(
                    raw_asset, f"{label}.assets[{asset_index}]"
                )
                normalized_assets.append(
                    {
                        "class": _required_string(
                            asset, "class", f"{label}.assets[{asset_index}]"
                        ),
                        "object_path": _required_string(
                            asset, "object_path", f"{label}.assets[{asset_index}]"
                        ),
                    }
                )
            normalized = {
                "assets": normalized_assets,
                "bytes": package_bytes,
                "group": group_name,
                "package_name": package_name,
                "relative_content_path": relative_content_path,
                "relative_source_path": relative_source_path,
                "sha256": package_sha,
                "stable_asset_id": _stable_asset_id(relative_source_path),
            }
            package_by_name[package_name] = normalized
            group_package_names.append(package_name)

        seeds = _plain_list(group.get("seeds"), f"closure group {group_name}.seeds")
        normalized_seeds: list[str] = []
        for seed_index, seed in enumerate(seeds):
            if not isinstance(seed, str) or seed not in package_by_name:
                raise ScratchCloneRefusal(
                    f"closure group {group_name} seed[{seed_index}] is not "
                    "one package in its authenticated closure"
                )
            if seed not in group_package_names:
                raise ScratchCloneRefusal(
                    f"closure group {group_name} seed is outside its group: {seed}"
                )
            if seed in seed_group_membership:
                raise ScratchCloneRefusal(f"seed repeated across groups: {seed}")
            seed_group_membership[seed] = group_name
            normalized_seeds.append(seed)
        group_manifests.append(
            {
                "closure_count": expected_count,
                "closure_packages": sorted(group_package_names, key=_sort_key),
                "group": group_name,
                "seed_packages": normalized_seeds,
            }
        )

    if set(EXPECTED_CLOSURE_GROUP_COUNTS) != {
        str(group["group"]) for group in group_manifests
    }:
        raise ScratchCloneRefusal("closure group set changed")
    if len(package_by_name) != EXPECTED_UNION_COUNT:
        raise ScratchCloneRefusal(
            f"closure union must contain exactly {EXPECTED_UNION_COUNT} packages"
        )

    seed_rows = _plain_list(closure.get("seed_records"), "closure.seed_records")
    if len(seed_rows) != EXPECTED_SEED_COUNT:
        raise ScratchCloneRefusal(
            f"closure must contain exactly {EXPECTED_SEED_COUNT} seed records"
        )
    seed_record_by_package: dict[str, dict[str, object]] = {}
    for seed_index, raw_seed in enumerate(seed_rows):
        seed = _plain_mapping(raw_seed, f"closure.seed_records[{seed_index}]")
        label = f"closure.seed_records[{seed_index}]"
        package_name = _required_string(seed, "package_name", label)
        if package_name in seed_record_by_package:
            raise ScratchCloneRefusal(f"duplicate seed record: {package_name}")
        package = package_by_name.get(package_name)
        if package is None or package_name not in seed_group_membership:
            raise ScratchCloneRefusal(
                f"seed record does not map to one group seed: {package_name}"
            )
        seed_bytes = _required_integer(seed, "bytes", label)
        seed_sha = _validate_sha256(
            _required_string(seed, "sha256", label), f"{label}.sha256"
        )
        seed_class = _required_string(seed, "class", label)
        if seed_bytes != package["bytes"] or seed_sha != package["sha256"]:
            raise ScratchCloneRefusal(
                f"seed/package identity mismatch: {package_name}"
            )
        if seed_class not in {
            str(asset["class"]) for asset in package["assets"]  # type: ignore[index]
        }:
            raise ScratchCloneRefusal(
                f"seed class is absent from Asset Registry record: {package_name}"
            )
        normalized_seed = {
            "bytes": seed_bytes,
            "class": seed_class,
            "group": seed_group_membership[package_name],
            "package_name": package_name,
            "relative_content_path": package["relative_content_path"],
            "relative_source_path": package["relative_source_path"],
            "sha256": seed_sha,
            "stable_asset_id": package["stable_asset_id"],
        }
        seed_record_by_package[package_name] = normalized_seed

    if set(seed_record_by_package) != set(seed_group_membership):
        raise ScratchCloneRefusal(
            "closure seed records do not exactly match the three group seed lists"
        )

    seed_group_manifests: list[dict[str, object]] = []
    for group in group_manifests:
        seed_group_manifests.append(
            {
                "group": group["group"],
                "seed_count": len(group["seed_packages"]),  # type: ignore[arg-type]
                "seeds": [
                    seed_record_by_package[str(package_name)]
                    for package_name in group["seed_packages"]  # type: ignore[union-attr]
                ],
            }
        )

    packages = sorted(
        package_by_name.values(),
        key=lambda row: _sort_key(str(row["package_name"])),
    )
    return closure, packages, seed_group_manifests


def _walk_tree(
    root: Path,
    *,
    relative_base: Path,
) -> tuple[list[str], list[Path]]:
    """Enumerate a complete tree without following any linked/reparse entry."""

    _require_directory(root, f"source directory {root}")
    directories: list[str] = []
    files: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(
                (Path(entry.path) for entry in os.scandir(directory)),
                key=lambda child: _sort_key(child.name),
            )
        except OSError as error:
            raise ScratchCloneRefusal(
                f"unable to enumerate source directory {directory}: {error}"
            ) from error
        child_directories: list[Path] = []
        for child in entries:
            observed = _metadata(child)
            if _is_reparse(observed):
                raise ScratchCloneRefusal(
                    f"linked/reparse source entry refused: {child}"
                )
            try:
                relative = child.relative_to(relative_base).as_posix()
            except ValueError as error:
                raise ScratchCloneRefusal(
                    f"source entry escapes inventory root: {child}"
                ) from error
            _safe_posix_relative(relative, "project relative path")
            if stat.S_ISDIR(observed.mode):
                directories.append(relative)
                child_directories.append(child)
            elif stat.S_ISREG(observed.mode):
                files.append(child)
            else:
                raise ScratchCloneRefusal(
                    f"non-regular source entry refused: {child}"
                )
        pending.extend(reversed(child_directories))
    return (
        sorted(directories, key=_sort_key),
        sorted(files, key=lambda path: _sort_key(path.as_posix())),
    )


def _authenticate_project() -> tuple[list[str], list[AuthenticatedFile]]:
    expected_root = EXPECTED_PROJECT_ROOT.resolve(strict=True)
    actual_tool_root = Path(__file__).resolve(strict=True).parents[1]
    if actual_tool_root != expected_root:
        raise ScratchCloneRefusal(
            f"tool must run from the canonical project: {actual_tool_root}"
        )
    _require_directory(expected_root, "canonical RedMMO project root")

    descriptor_path = expected_root / PROJECT_DESCRIPTOR
    descriptor_metadata, descriptor_sha = _hash_regular_file_stable(
        descriptor_path, "project descriptor"
    )
    records = [
        AuthenticatedFile(
            source_path=descriptor_path,
            destination_relative_path=PROJECT_DESCRIPTOR,
            source_kind="redmmo_project",
            source_scope="project_descriptor",
            source_relative_path=PROJECT_DESCRIPTOR,
            bytes=descriptor_metadata.size,
            sha256=descriptor_sha,
            metadata=descriptor_metadata,
        )
    ]
    directories: list[str] = []

    for scope in PROJECT_DIRECTORY_SCOPES:
        scope_root = expected_root / scope
        scope_directories, scope_files = _walk_tree(
            scope_root, relative_base=expected_root
        )
        directories.append(scope)
        directories.extend(scope_directories)
        for index, source_path in enumerate(scope_files):
            relative = source_path.relative_to(expected_root).as_posix()
            metadata, digest = _hash_regular_file_stable(
                source_path, f"project scope {scope} file"
            )
            records.append(
                AuthenticatedFile(
                    source_path=source_path,
                    destination_relative_path=relative,
                    source_kind="redmmo_project",
                    source_scope=scope,
                    source_relative_path=relative,
                    bytes=metadata.size,
                    sha256=digest,
                    metadata=metadata,
                )
            )
            if (index + 1) % 500 == 0:
                _emit_progress(
                    "project_authentication",
                    scope=scope,
                    files=index + 1,
                )

    folded_paths: dict[str, str] = {}
    for record in records:
        folded = record.destination_relative_path.casefold()
        previous = folded_paths.get(folded)
        if previous is not None:
            raise ScratchCloneRefusal(
                "project has duplicate/case-colliding paths: "
                f"{previous} and {record.destination_relative_path}"
            )
        folded_paths[folded] = record.destination_relative_path

    tropical_prefix = "content/zenscape_island"
    tropical_project_entries = [
        value
        for folded, value in folded_paths.items()
        if folded == tropical_prefix or folded.startswith(tropical_prefix + "/")
    ]
    tropical_project_directories = [
        value
        for value in directories
        if value.casefold() == tropical_prefix
        or value.casefold().startswith(tropical_prefix + "/")
    ]
    if tropical_project_entries or tropical_project_directories:
        raise ScratchCloneRefusal(
            "canonical RedMMO project already contains Content/Zenscape_Island; "
            "the exact 51-package vendor add would not be isolated/no-clobber"
        )

    records_by_relative = {
        record.destination_relative_path: record for record in records
    }
    for relative, expected_sha in PROTECTED_INPUT_HASHES.items():
        protected = records_by_relative.get(relative)
        if protected is None or protected.sha256 != expected_sha:
            observed = protected.sha256 if protected else "MISSING"
            raise ScratchCloneRefusal(
                f"protected input identity changed: {relative}: "
                f"{observed} != {expected_sha}"
            )

    unique_directories = sorted(set(directories), key=_sort_key)
    return unique_directories, sorted(
        records, key=lambda record: _sort_key(record.destination_relative_path)
    )


def _authenticate_vendor_packages(
    package_rows: Sequence[Mapping[str, object]],
) -> tuple[list[str], list[AuthenticatedFile]]:
    _require_directory(TROPICAL_CONTENT_ROOT, "Tropical Content root")
    records: list[AuthenticatedFile] = []
    directories: set[str] = set()
    for package in package_rows:
        relative_content_path = str(package["relative_content_path"])
        source_path = TROPICAL_CONTENT_ROOT.joinpath(
            *PurePosixPath(relative_content_path).parts
        )
        metadata, digest = _hash_regular_file_stable(
            source_path, "Tropical closure package"
        )
        expected_bytes = int(package["bytes"])
        expected_sha = str(package["sha256"])
        if metadata.size != expected_bytes or digest != expected_sha:
            raise ScratchCloneRefusal(
                "Tropical source package differs from authoritative closure: "
                f"{relative_content_path}: bytes={metadata.size}, sha={digest}"
            )
        destination_relative = (
            PurePosixPath("Content") / PurePosixPath(relative_content_path)
        ).as_posix()
        parent = PurePosixPath(destination_relative).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
        records.append(
            AuthenticatedFile(
                source_path=source_path,
                destination_relative_path=destination_relative,
                source_kind="tropical_vendor_closure",
                source_scope=str(package["group"]),
                source_relative_path=str(package["relative_source_path"]),
                bytes=metadata.size,
                sha256=digest,
                metadata=metadata,
            )
        )
    if len(records) != EXPECTED_UNION_COUNT:
        raise ScratchCloneRefusal("vendor record count changed after authentication")
    return sorted(directories, key=_sort_key), sorted(
        records, key=lambda record: _sort_key(record.destination_relative_path)
    )


def _verify_no_destination_collisions(
    project_records: Sequence[AuthenticatedFile],
    vendor_records: Sequence[AuthenticatedFile],
) -> None:
    observed: dict[str, str] = {}
    for record in [*project_records, *vendor_records]:
        folded = record.destination_relative_path.casefold()
        previous = observed.get(folded)
        if previous is not None:
            raise ScratchCloneRefusal(
                "destination collision in transaction plan: "
                f"{previous} and {record.destination_relative_path}"
            )
        observed[folded] = record.destination_relative_path


def _require_legacy_path_capacity(
    root: Path,
    relative_directories: Sequence[str],
    records: Sequence[AuthenticatedFile],
    label: str,
) -> None:
    relative_paths = [
        *relative_directories,
        *(record.destination_relative_path for record in records),
    ]
    for relative in relative_paths:
        safe_relative = _safe_posix_relative(relative, f"{label} relative path")
        physical_path = root.joinpath(*PurePosixPath(safe_relative).parts)
        if len(os.fspath(physical_path)) > WINDOWS_LEGACY_MAX_PATH_CHARS:
            raise ScratchCloneRefusal(
                f"{label} exceeds the legacy-safe Windows path limit: "
                f"{physical_path}"
            )


def _same_file_identity(
    before: FileMetadata,
    after: FileMetadata,
) -> bool:
    return before == after


def _verify_source_records(
    records: Sequence[AuthenticatedFile],
    *,
    phase: str,
) -> None:
    for index, record in enumerate(records):
        metadata, digest = _hash_regular_file_stable(
            record.source_path, f"{phase} source"
        )
        if (
            not _same_file_identity(record.metadata, metadata)
            or metadata.size != record.bytes
            or digest != record.sha256
        ):
            raise ScratchCloneRefusal(
                f"{phase} source changed: {record.source_path}"
            )
        if (index + 1) % 500 == 0:
            _emit_progress(phase, files=index + 1)


def _mkdir_no_clobber(path: Path, label: str) -> None:
    if _lexists(path):
        raise ScratchCloneRefusal(f"{label} already exists: {path}")
    try:
        os.mkdir(path)
    except OSError as error:
        raise ScratchCloneRefusal(f"unable to create {label} {path}: {error}") from error
    observed = _require_directory(path, label)
    if _is_reparse(observed):
        raise ScratchCloneRefusal(f"new {label} became reparse: {path}")


def _create_private_stage_directories(
    staging_root: Path,
    relative_directories: Sequence[str],
) -> None:
    _mkdir_no_clobber(staging_root, "transaction staging root")
    for relative in sorted(
        set(relative_directories),
        key=lambda value: (len(PurePosixPath(value).parts), *_sort_key(value)),
    ):
        safe_relative = _safe_posix_relative(relative, "destination directory")
        destination = staging_root.joinpath(*PurePosixPath(safe_relative).parts)
        _mkdir_no_clobber(destination, "staging directory")


def _copy_verified(
    record: AuthenticatedFile,
    staging_root: Path,
) -> None:
    source_before = _require_regular_file(record.source_path, "copy source")
    if source_before != record.metadata:
        raise ScratchCloneRefusal(
            f"copy source changed after preflight: {record.source_path}"
        )
    destination = staging_root.joinpath(
        *PurePosixPath(record.destination_relative_path).parts
    )
    if _lexists(destination):
        raise ScratchCloneRefusal(
            f"copy destination collision refused: {destination}"
        )
    _require_directory(destination.parent, "copy destination parent")
    try:
        shutil.copy2(record.source_path, destination, follow_symlinks=False)
    except OSError as error:
        raise ScratchCloneRefusal(
            f"copy failed {record.source_path} -> {destination}: {error}"
        ) from error
    destination_metadata, destination_sha = _hash_regular_file_stable(
        destination, "copied destination"
    )
    if (
        destination_metadata.size != record.bytes
        or destination_sha != record.sha256
    ):
        raise ScratchCloneRefusal(
            f"copied destination verification failed: {destination}"
        )
    source_after = _require_regular_file(record.source_path, "copy source")
    if source_after != source_before:
        raise ScratchCloneRefusal(
            f"copy source changed during copy: {record.source_path}"
        )


def _inventory_destination(
    root: Path,
) -> tuple[list[str], dict[str, tuple[int, str]]]:
    directories, files = _walk_tree(root, relative_base=root)
    records: dict[str, tuple[int, str]] = {}
    for index, path in enumerate(files):
        relative = path.relative_to(root).as_posix()
        folded = relative.casefold()
        if folded in records:
            raise ScratchCloneRefusal(
                f"case-colliding destination file: {relative}"
            )
        metadata, digest = _hash_regular_file_stable(
            path, "destination verification file"
        )
        records[folded] = (metadata.size, digest)
        if (index + 1) % 500 == 0:
            _emit_progress("destination_verification", files=index + 1)
    return directories, records


def _verify_destination_tree(
    root: Path,
    expected_directories: Sequence[str],
    expected_records: Sequence[AuthenticatedFile],
) -> None:
    actual_directories, actual_files = _inventory_destination(root)
    expected_directory_set = {
        directory.casefold() for directory in expected_directories
    }
    actual_directory_set = {
        directory.casefold() for directory in actual_directories
    }
    if actual_directory_set != expected_directory_set:
        missing = sorted(expected_directory_set - actual_directory_set)
        extra = sorted(actual_directory_set - expected_directory_set)
        raise ScratchCloneRefusal(
            "destination directory set mismatch: "
            f"missing={missing[:20]}, extra={extra[:20]}"
        )
    expected_files = {
        record.destination_relative_path.casefold(): (record.bytes, record.sha256)
        for record in expected_records
    }
    if actual_files != expected_files:
        missing = sorted(set(expected_files) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected_files))
        mismatched = sorted(
            key
            for key in set(actual_files) & set(expected_files)
            if actual_files[key] != expected_files[key]
        )
        raise ScratchCloneRefusal(
            "destination file set/content mismatch: "
            f"missing={missing[:20]}, extra={extra[:20]}, "
            f"mismatched={mismatched[:20]}"
        )


def _json_bytes(document: Mapping[str, object]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _publish_bytes_no_clobber(path: Path, payload: bytes) -> None:
    if _lexists(path):
        raise ScratchCloneRefusal(f"publication collision refused: {path}")
    _require_directory(path.parent, "publication parent")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise ScratchCloneRefusal(
            f"unable to create no-clobber publication {path}: {error}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        raise
    metadata, digest = _hash_regular_file_stable(path, "published evidence file")
    if metadata.size != len(payload) or digest != hashlib.sha256(payload).hexdigest().upper():
        raise ScratchCloneRefusal(f"publication verification failed: {path}")


def _status_filename(sequence: int, phase: str) -> str:
    safe_phase = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in phase
    )
    return f"status-{sequence:03d}-{safe_phase}.json"


def _publish_status(
    state: TransactionState,
    phase: str,
    *,
    outcome: str = "in_progress",
    details: Mapping[str, object] | None = None,
) -> Path:
    path = state.diagnostics_dir / _status_filename(
        state.status_sequence, phase
    )
    document: dict[str, object] = {
        "destination": state.destination.as_posix(),
        "destination_finalized": state.destination_finalized,
        "outcome": outcome,
        "phase": phase,
        "schema_version": 1,
        "staging_created": state.staging_created,
        "staging_path": state.staging_path.as_posix(),
        "timestamp_utc": _utc_now(),
        "transaction_id": state.transaction_id,
    }
    if details:
        document["details"] = dict(details)
    _publish_bytes_no_clobber(path, _json_bytes(document))
    state.status_sequence += 1
    return path


def _emit_progress(phase: str, **details: object) -> None:
    print(
        json.dumps(
            {"event": "progress", "phase": phase, **details},
            sort_keys=True,
        ),
        flush=True,
    )


def _validate_transaction_paths(
    destination_arg: Path,
    diagnostics_arg: Path,
    transaction_id: str,
) -> TransactionState:
    project_root = EXPECTED_PROJECT_ROOT.resolve(strict=True)
    scratch_root = SCRATCH_ROOT.resolve(strict=True)
    diagnostics_root = DIAGNOSTICS_ROOT.resolve(strict=True)
    tropical_root = TROPICAL_CONTENT_ROOT.resolve(strict=True)
    closure_path = CLOSURE_PATH.resolve(strict=True)
    for path, label in (
        (project_root, "project root"),
        (scratch_root, "scratch root"),
        (diagnostics_root, "diagnostics root"),
        (tropical_root, "Tropical Content root"),
        (closure_path, "closure path"),
    ):
        _require_d_drive(path, label)
        _reject_existing_reparse_chain(path, label)

    destination = _resolved_within(destination_arg, scratch_root, "destination")
    diagnostics_dir = _resolved_within(
        diagnostics_arg, diagnostics_root, "diagnostics directory"
    )
    _require_d_drive(destination, "destination")
    _require_d_drive(diagnostics_dir, "diagnostics directory")
    if _lexists(destination):
        raise ScratchCloneRefusal(
            f"destination must be fresh and absent: {destination}"
        )
    if _lexists(diagnostics_dir):
        raise ScratchCloneRefusal(
            f"diagnostics directory must be fresh and absent: {diagnostics_dir}"
        )
    _require_directory(destination.parent, "destination parent")
    _require_directory(diagnostics_dir.parent, "diagnostics parent")
    staging_path = destination.parent / _staging_leaf(transaction_id)
    if _lexists(staging_path):
        raise ScratchCloneRefusal(
            f"transaction staging path collision: {staging_path}"
        )
    _reject_existing_reparse_chain(staging_path, "transaction staging path")

    protected_roots = (
        project_root,
        tropical_root,
        closure_path.parent,
    )
    for protected in protected_roots:
        if _paths_overlap(destination, protected):
            raise ScratchCloneRefusal(
                f"destination overlaps protected source {protected}"
            )
        if _paths_overlap(diagnostics_dir, protected):
            raise ScratchCloneRefusal(
                f"diagnostics directory overlaps protected source {protected}"
            )
    if _paths_overlap(destination, diagnostics_dir):
        raise ScratchCloneRefusal(
            "destination and diagnostics directory must be disjoint"
        )
    return TransactionState(
        transaction_id=transaction_id,
        destination=destination,
        diagnostics_dir=diagnostics_dir,
        staging_path=staging_path,
        started_utc=_utc_now(),
    )


def _protected_manifest_rows(
    project_records: Sequence[AuthenticatedFile],
) -> list[dict[str, object]]:
    by_path = {
        record.destination_relative_path: record for record in project_records
    }
    return [
        {
            "bytes": by_path[path].bytes,
            "relative_path": path,
            "sha256": by_path[path].sha256,
        }
        for path in sorted(PROTECTED_INPUT_HASHES, key=_sort_key)
    ]


def _build_manifest(
    state: TransactionState,
    closure: Mapping[str, object],
    package_rows: Sequence[Mapping[str, object]],
    seed_groups: Sequence[Mapping[str, object]],
    project_directories: Sequence[str],
    project_records: Sequence[AuthenticatedFile],
    vendor_directories: Sequence[str],
    vendor_records: Sequence[AuthenticatedFile],
) -> dict[str, object]:
    tool_path = Path(__file__).resolve(strict=True)
    tool_metadata, tool_sha = _hash_regular_file_stable(tool_path, "clone tool")
    all_records = [*project_records, *vendor_records]
    completed_utc = _utc_now()
    return {
        "schema_version": 1,
        "transaction": {
            "completed_utc": completed_utc,
            "destination": state.destination.as_posix(),
            "diagnostics_directory": state.diagnostics_dir.as_posix(),
            "outcome": "succeeded",
            "publication": "same_volume_staging_then_no_replace_directory_rename",
            "source_mutation": False,
            "started_utc": state.started_utc,
            "transaction_id": state.transaction_id,
        },
        "tool": {
            "bytes": tool_metadata.size,
            "path": tool_path.as_posix(),
            "sha256": tool_sha,
        },
        "redmmo_source": {
            "directory_scopes": list(PROJECT_DIRECTORY_SCOPES),
            "directories": list(project_directories),
            "file_count": len(project_records),
            "files": [record.manifest_row() for record in project_records],
            "project_descriptor": PROJECT_DESCRIPTOR,
            "root": EXPECTED_PROJECT_ROOT.as_posix(),
            "total_bytes": sum(record.bytes for record in project_records),
        },
        "protected_inputs": _protected_manifest_rows(project_records),
        "tropical_closure": {
            "closure_file": CLOSURE_PATH.as_posix(),
            "closure_sha256": CLOSURE_SHA256,
            "engine_version": closure.get("engine_version"),
            "group_counts": dict(EXPECTED_CLOSURE_GROUP_COUNTS),
            "pack_id": TROPICAL_PACK_ID,
            "pack_root": closure.get("pack_root"),
            "package_count": len(package_rows),
            "packages": [dict(row) for row in package_rows],
            "probe": closure.get("probe"),
            "seed_count": sum(
                int(group["seed_count"]) for group in seed_groups
            ),
            "seed_groups": [dict(group) for group in seed_groups],
            "source_content_root": TROPICAL_CONTENT_ROOT.as_posix(),
        },
        "tropical_copy": {
            "directories": list(vendor_directories),
            "file_count": len(vendor_records),
            "files": [record.manifest_row() for record in vendor_records],
            "total_bytes": sum(record.bytes for record in vendor_records),
        },
        "result": {
            "directory_count": len(
                {directory.casefold() for directory in [
                    *project_directories,
                    *vendor_directories,
                ]}
            ),
            "file_count": len(all_records),
            "total_bytes": sum(record.bytes for record in all_records),
            "verified_all_copied_files": True,
            "verified_exact_file_set": True,
            "verified_source_unchanged_through_postcopy_check": True,
        },
        "boundaries": {
            "asset_registry_closure_is_ue58_authoritative": True,
            "cloud_group_is_conditional_not_automatically_applied": True,
            "copied_scope_only": [
                PROJECT_DESCRIPTOR,
                *PROJECT_DIRECTORY_SCOPES,
                "exact_51_package_tropical_union",
            ],
            "empty_directories_preserved": True,
            "provider_use": False,
            "source_acl_owner_ads_not_replicated_or_attested": True,
            "unreal_launched": False,
            "unreal_packages_loaded_or_saved": False,
            "vendor_demo_maps_copied": False,
        },
        "claim_limit": (
            "This manifest proves one no-clobber byte-exact filesystem scratch "
            "clone of the selected RedMMO functional scope plus the pinned "
            "51-package Tropical dependency union. It does not prove Unreal "
            "loadability, serialization, map authoring, material correctness, "
            "planetary placement, clouds, water, collision, performance, "
            "surface-to-orbit behavior, gameplay, visual acceptance, provider "
            "readiness, production migration, ACL/owner/alternate-stream "
            "preservation, or package licensing."
        ),
    }


def _run_transaction(state: TransactionState) -> Path:
    _mkdir_no_clobber(state.diagnostics_dir, "transaction diagnostics directory")
    state.diagnostics_created = True
    _publish_status(state, "initialized")

    _validate_stable_id_rule()
    closure, package_rows, seed_groups = _validate_closure()
    _publish_status(
        state,
        "closure_authenticated",
        details={
            "closure_sha256": CLOSURE_SHA256,
            "package_count": len(package_rows),
            "seed_count": sum(int(group["seed_count"]) for group in seed_groups),
        },
    )

    project_directories, project_records = _authenticate_project()
    vendor_directories, vendor_records = _authenticate_vendor_packages(package_rows)
    _verify_no_destination_collisions(project_records, vendor_records)
    _publish_status(
        state,
        "sources_authenticated",
        details={
            "project_file_count": len(project_records),
            "project_total_bytes": sum(row.bytes for row in project_records),
            "tropical_file_count": len(vendor_records),
            "tropical_total_bytes": sum(row.bytes for row in vendor_records),
        },
    )

    expected_directories = sorted(
        {
            *project_directories,
            *vendor_directories,
        },
        key=_sort_key,
    )
    all_records = sorted(
        [*project_records, *vendor_records],
        key=lambda row: _sort_key(row.destination_relative_path),
    )
    _require_legacy_path_capacity(
        state.staging_path,
        expected_directories,
        all_records,
        "transaction staging path",
    )
    _require_legacy_path_capacity(
        state.destination,
        expected_directories,
        all_records,
        "final destination path",
    )
    _create_private_stage_directories(state.staging_path, expected_directories)
    state.staging_created = True
    _publish_status(state, "staging_created")

    copied_bytes = 0
    for index, record in enumerate(all_records):
        _copy_verified(record, state.staging_path)
        copied_bytes += record.bytes
        if (index + 1) % 250 == 0 or index + 1 == len(all_records):
            _emit_progress(
                "copy",
                files=index + 1,
                total_files=len(all_records),
                bytes=copied_bytes,
            )
    _publish_status(
        state,
        "copy_complete",
        details={"bytes": copied_bytes, "files": len(all_records)},
    )

    _verify_source_records(project_records, phase="project_postcopy_authentication")
    _verify_source_records(vendor_records, phase="vendor_postcopy_authentication")
    if _sha256_file(CLOSURE_PATH) != CLOSURE_SHA256:
        raise ScratchCloneRefusal("closure JSON changed during transaction")
    _verify_destination_tree(
        state.staging_path, expected_directories, all_records
    )
    _publish_status(state, "staging_verified")

    if _lexists(state.destination):
        raise ScratchCloneRefusal(
            f"destination appeared before finalization: {state.destination}"
        )
    try:
        os.rename(state.staging_path, state.destination)
    except OSError as error:
        raise ScratchCloneRefusal(
            f"no-replace destination finalization failed: {error}"
        ) from error
    state.destination_finalized = True
    _verify_destination_tree(
        state.destination, expected_directories, all_records
    )

    manifest = _build_manifest(
        state,
        closure,
        package_rows,
        seed_groups,
        project_directories,
        project_records,
        vendor_directories,
        vendor_records,
    )
    manifest_path = state.diagnostics_dir / "transaction_manifest.json"
    manifest_payload = _json_bytes(manifest)
    _publish_bytes_no_clobber(manifest_path, manifest_payload)
    manifest_sha = hashlib.sha256(manifest_payload).hexdigest().upper()
    _publish_status(
        state,
        "completed",
        outcome="succeeded",
        details={
            "manifest": manifest_path.as_posix(),
            "manifest_sha256": manifest_sha,
        },
    )
    print(
        json.dumps(
            {
                "destination": state.destination.as_posix(),
                "manifest": manifest_path.as_posix(),
                "manifest_sha256": manifest_sha,
                "outcome": "succeeded",
                "transaction_id": state.transaction_id,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return manifest_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination",
        type=Path,
        required=True,
        help=(
            "Fresh absent child path below "
            "D:\\RedMMOTitanWindowsData\\Scratch"
        ),
    )
    parser.add_argument(
        "--diagnostics-dir",
        type=Path,
        required=True,
        help=(
            "Fresh absent child directory below "
            "D:\\RedMMOTitanWindowsData\\Diagnostics"
        ),
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transaction_id = (
        f"M07-TROPICAL-PLANET-BIOME-{timestamp}-{uuid.uuid4().hex[:8].upper()}"
    )
    state: TransactionState | None = None
    try:
        state = _validate_transaction_paths(
            args.destination,
            args.diagnostics_dir,
            transaction_id,
        )
        _run_transaction(state)
        return 0
    except ScratchCloneRefusal as error:
        if state is not None and state.diagnostics_created:
            try:
                _publish_status(
                    state,
                    "failed",
                    outcome="failed",
                    details={
                        "error": str(error),
                        "partial_retained": (
                            state.staging_created or state.destination_finalized
                        ),
                        "manual_cleanup_required": (
                            state.staging_created or state.destination_finalized
                        ),
                    },
                )
            except Exception as status_error:  # noqa: BLE001
                print(
                    f"unable to publish failure status: {status_error}",
                    file=sys.stderr,
                    flush=True,
                )
        print(f"REFUSED: {error}", file=sys.stderr, flush=True)
        return 2
    except Exception as error:  # noqa: BLE001
        if state is not None and state.diagnostics_created:
            try:
                _publish_status(
                    state,
                    "failed-unexpected",
                    outcome="failed",
                    details={
                        "error": f"{type(error).__name__}: {error}",
                        "partial_retained": (
                            state.staging_created or state.destination_finalized
                        ),
                        "manual_cleanup_required": (
                            state.staging_created or state.destination_finalized
                        ),
                    },
                )
            except Exception as status_error:  # noqa: BLE001
                print(
                    f"unable to publish unexpected-failure status: {status_error}",
                    file=sys.stderr,
                    flush=True,
                )
        print(
            f"UNEXPECTED FAILURE: {type(error).__name__}: {error}",
            file=sys.stderr,
            flush=True,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
