"""Validate the immutable, non-executable NWIRO candidate-source contract.

This module is deliberately read-only and cannot report runtime readiness. It
authenticates the current blocked Integration Kit baseline, its complete
106-file installation and exact 90-file fork input, the parent offline
contracts, and the required absence of the future staging candidate. It opens
no socket, launches no process, imports no Unreal module, and writes no report.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import re
import stat
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    PROJECT_ROOT
    / "Build/Automation/redmmo_nwiro_restricted_probe_candidate_contract_v1.json"
)
EXPECTED_CONTRACT_SHA256 = (
    "AD53BE2585A6B03F74C53A36EE6A30318F318ACC5F2798E664CBD37BCBEDC7DE"
)
MAX_JSON_BYTES = 256 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_INSTALLED_FILE_BYTES = 160 * 1024 * 1024
MAX_INSTALLED_TREE_BYTES = 192 * 1024 * 1024
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
SHA_RE = re.compile(r"^[0-9A-F]{64}$")
D_PATH_RE = re.compile(r"^D:/[^\\]+$")
EXPECTED_TREE_DIGEST_ALGORITHM = (
    "ordinal UTF-8 no-BOM LF-final records: "
    "file=<relative_path>\\t<decimal_bytes>\\t<UPPERCASE_SHA256>\\n; "
    "topology path-ordered directory=D\\t<relative_path>\\n and "
    "file=F\\t<relative_path>\\t<decimal_bytes>\\t<UPPERCASE_SHA256>\\n"
)
EXPECTED_TOP_LEVEL_COUNTS: dict[str, int] = {
    "Binaries": 5,
    "Intermediate": 11,
    "NwiroIntegrationKit.uplugin": 1,
    "Resources": 2,
    "Source": 87,
}

EXPECTED_PARENT_INPUTS: tuple[tuple[str, str, int, str], ...] = (
    (
        "metadata_dry_run_contract",
        "D:/RedMMOTitan/Build/Automation/redmmo_nwiro_metadata_dry_run_contract_v1.json",
        14804,
        "B388D2869D0B13A798A1128705B650EC3CCE071DC5BD8441184C359BBE7D9E68",
    ),
    (
        "offline_predispatch_firewall",
        "D:/RedMMOTitan/Tools/redmmo_nwiro_predispatch_firewall.py",
        18844,
        "5C6F4A33EE71E4660CA87DDB67EF08743D8811652BBEC23E1408D012FA018DE2",
    ),
    (
        "blocked_baseline_auditor",
        "D:/RedMMOTitan/Tools/audit_nwiro_restricted_probe_source.py",
        18258,
        "2E8B3B669630B125BB0C427C6F52CDC2DF7F24392D1728374342808C635CEAC1",
    ),
    (
        "blocked_baseline_auditor_tests",
        "D:/RedMMOTitan/Tools/tests/test_audit_nwiro_restricted_probe_source.py",
        7244,
        "9E7F5D6028AB2C7C868B2AAAA60025272A7F5E35444EEA1B704FC904542A3256",
    ),
    (
        "blocked_baseline_evidence",
        "D:/RedMMOTitan/ProjectKnowledge/evidence/2026-07-25-m07-nwiro-restricted-probe-baseline-source-audit-static.yaml",
        8316,
        "54E2C21AEEEE94AC4B4AE8F7C5703FFAA9DC009922AC64509ECBCAB2778F28D4",
    ),
)

EXPECTED_CONTROL_IDS: tuple[str, ...] = (
    "mode_default_off",
    "trusted_in_process_activation_only",
    "process_wide_single_owner_lock",
    "one_in_flight_request",
    "nonce_generation_and_phase_bound",
    "exact_initialize_then_initialized_sequence",
    "singleton_literal_tools_list",
    "exact_find_assets_definition_digest",
    "process_jsonrpc_gate_dominates_dispatch",
    "dispatch_tool_gate_dominates_impl",
    "exact_query_arguments_no_coercion_or_extras",
    "exact_single_identity_response_filtered_before_publication",
    "raw_http_routes_suppressed",
    "fallback_ports_and_restart_suppressed",
    "acp_connect_and_message_suppressed",
    "dynamic_and_provider_registry_suppressed",
    "provider_secrets_and_network_egress_suppressed",
    "bridge_events_and_permission_ui_suppressed",
    "headless_and_bridge_null_fail_closed",
    "client_config_publication_suppressed",
    "asset_load_save_import_and_map_mutation_suppressed",
    "teardown_invalidates_owner_nonce_generation_and_pending_work",
)

EXPECTED_CHANGED_FILES: tuple[str, ...] = (
    "Private/NwiroIntegrationKit.cpp",
    "Private/NwiroIKBridge.cpp",
    "Private/NwiroIKBridge.h",
    "Private/NwiroIKMCPServer.cpp",
    "Private/NwiroIKMCPServer.h",
)
EXPECTED_NEW_FILES: tuple[str, ...] = (
    "Private/NwiroIKRestrictedProbePolicy.cpp",
    "Private/NwiroIKRestrictedProbePolicy.h",
)
EXPECTED_SOURCE_EXTENSION_COUNTS: dict[str, int] = {
    "": 1,
    ".c": 2,
    ".cpp": 38,
    ".cs": 1,
    ".h": 43,
    ".inl": 2,
}
EXPECTED_FORK_INPUT_DIRECTORIES: tuple[str, ...] = (
    "Resources",
    "Source",
    "Source/NwiroIntegrationKit",
    "Source/NwiroIntegrationKit/Private",
    "Source/NwiroIntegrationKit/Private/ContentPipeline",
    "Source/NwiroIntegrationKit/Private/Integration",
    "Source/NwiroIntegrationKit/Private/Tests",
    "Source/NwiroIntegrationKit/Public",
    "Source/ThirdParty",
    "Source/ThirdParty/miniz",
)
EXPECTED_FORBIDDEN_CANDIDATE_ROOTS: tuple[str, ...] = (
    ".git",
    "Binaries",
    "Config",
    "Content",
    "Intermediate",
    "Saved",
)
EXPECTED_ARGUMENTS: dict[str, Any] = {
    "searchTerm": "T_Sand_basecolor",
    "classFilter": "Texture2D",
    "path": "/Game/Zenscape_Savanna/Landscape/Texture",
    "maxResults": 2,
}
EXPECTED_IDENTITY: dict[str, str] = {
    "name": "T_Sand_basecolor",
    "path": (
        "/Game/Zenscape_Savanna/Landscape/Texture/"
        "T_Sand_basecolor.T_Sand_basecolor"
    ),
    "class": "Texture2D",
}


class CandidateContractError(RuntimeError):
    """The candidate contract or one authenticated input failed closed."""


def runtime_authorized() -> bool:
    """This contract version cannot grant runtime authority."""

    return False


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise CandidateContractError(f"nonfinite JSON constant: {value}")


def _validate_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise CandidateContractError(f"nonfinite number at {path}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_finite(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_finite(item, f"{path}.{key}")


def load_json_bytes_strict(payload: bytes, label: str) -> dict[str, Any]:
    if not payload or len(payload) > MAX_JSON_BYTES:
        raise CandidateContractError(f"{label} size is outside the allowed range")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CandidateContractError(f"{label} is not UTF-8: {error}") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, CandidateContractError) as error:
        raise CandidateContractError(f"{label} is invalid JSON: {error}") from error
    if type(value) is not dict:
        raise CandidateContractError(f"{label} root must be an object")
    _validate_finite(value)
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _require_exact_keys(
    value: dict[str, Any], expected: set[str], label: str
) -> None:
    actual = set(value)
    if actual != expected:
        raise CandidateContractError(
            f"{label} keys mismatch: expected {sorted(expected)}, got {sorted(actual)}"
        )


def _require_plain_bool(value: Any, expected: bool, label: str) -> None:
    if type(value) is not bool or value is not expected:
        raise CandidateContractError(f"{label} must be exact boolean {expected}")


def _require_plain_int(value: Any, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        raise CandidateContractError(f"{label} must be exact integer {expected}")


def _require_string(value: Any, expected: str, label: str) -> None:
    if type(value) is not str or value != expected:
        raise CandidateContractError(f"{label} must equal {expected!r}")


def _require_sha(value: Any, label: str) -> str:
    if type(value) is not str or SHA_RE.fullmatch(value) is None:
        raise CandidateContractError(f"{label} must be uppercase SHA-256")
    return value


def _require_d_path(value: Any, expected: str, label: str) -> Path:
    _require_string(value, expected, label)
    if D_PATH_RE.fullmatch(value) is None or ".." in value.split("/"):
        raise CandidateContractError(f"{label} must be a canonical absolute D path")
    return Path(value)


def _is_reparse(stat_result: os.stat_result) -> bool:
    return bool(
        getattr(stat_result, "st_file_attributes", 0)
        & FILE_ATTRIBUTE_REPARSE_POINT
    )


def _read_stable_regular_file(path: Path, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    _validate_existing_ancestor_chain(path.parent)
    if path.is_symlink():
        raise CandidateContractError(f"symlink refused: {path}")
    before = path.stat(follow_symlinks=False)
    if _is_reparse(before):
        raise CandidateContractError(f"reparse point refused: {path}")
    if not stat.S_ISREG(before.st_mode):
        raise CandidateContractError(f"not a regular file: {path}")
    if getattr(before, "st_nlink", 1) != 1:
        raise CandidateContractError(f"hard-linked file refused: {path}")
    if before.st_size <= 0 or before.st_size > max_bytes:
        raise CandidateContractError(f"file size outside bounds: {path}")
    streams_before = _named_alternate_streams(path)
    if streams_before:
        raise CandidateContractError(
            f"named alternate data stream refused for {path}: {streams_before}"
        )

    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise CandidateContractError(f"file identity changed before read: {path}")
        payload = handle.read(max_bytes + 1)
        after = os.fstat(handle.fileno())

    if len(payload) > max_bytes or len(payload) != before.st_size:
        raise CandidateContractError(f"file length changed during read: {path}")
    if (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    ):
        raise CandidateContractError(f"file changed during read: {path}")
    current = path.stat(follow_symlinks=False)
    if (
        path.is_symlink()
        or _is_reparse(current)
        or not stat.S_ISREG(current.st_mode)
        or (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
            getattr(current, "st_nlink", 1),
        )
        != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            getattr(before, "st_nlink", 1),
        )
    ):
        raise CandidateContractError(f"pathname identity changed after read: {path}")
    streams_after = _named_alternate_streams(path)
    if streams_after:
        raise CandidateContractError(
            f"named alternate data stream appeared for {path}: {streams_after}"
        )
    return payload


def _validate_existing_ancestor_chain(path: Path) -> None:
    resolved_parts: list[Path] = []
    current = path
    while not current.exists():
        if current.is_symlink():
            raise CandidateContractError(
                f"candidate ancestor symlink refused: {current}"
            )
        try:
            missing_info = current.stat(follow_symlinks=False)
        except FileNotFoundError:
            missing_info = None
        if missing_info is not None and _is_reparse(missing_info):
            raise CandidateContractError(
                f"candidate ancestor reparse point refused: {current}"
            )
        parent = current.parent
        if parent == current:
            raise CandidateContractError(f"no existing ancestor for {path}")
        current = parent
    while True:
        resolved_parts.append(current)
        if current.parent == current:
            break
        current = current.parent
    for ancestor in reversed(resolved_parts):
        info = ancestor.stat(follow_symlinks=False)
        if ancestor.is_symlink() or _is_reparse(info):
            raise CandidateContractError(
                f"candidate ancestor link/reparse refused: {ancestor}"
            )


def _named_alternate_streams(path: Path) -> tuple[str, ...]:
    """Return named NTFS streams, excluding the normal unnamed data stream."""

    if os.name != "nt":
        raise CandidateContractError("NTFS stream authentication requires Windows")

    class Win32FindStreamData(ctypes.Structure):
        _fields_ = [
            ("stream_size", ctypes.c_longlong),
            ("stream_name", wintypes.WCHAR * 296),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    find_first = kernel32.FindFirstStreamW
    find_first.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(Win32FindStreamData),
        wintypes.DWORD,
    ]
    find_first.restype = wintypes.HANDLE
    find_next = kernel32.FindNextStreamW
    find_next.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(Win32FindStreamData),
    ]
    find_next.restype = wintypes.BOOL
    find_close = kernel32.FindClose
    find_close.argtypes = [wintypes.HANDLE]
    find_close.restype = wintypes.BOOL

    data = Win32FindStreamData()
    handle = find_first(str(path), 0, ctypes.byref(data), 0)
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        error = ctypes.get_last_error()
        if error == 38:  # ERROR_HANDLE_EOF: no streams, including directories.
            return ()
        raise CandidateContractError(
            f"cannot enumerate alternate streams for {path}: Win32 error {error}"
        )
    streams: list[str] = []
    try:
        while True:
            name = data.stream_name
            if name != "::$DATA":
                streams.append(name)
            if not find_next(handle, ctypes.byref(data)):
                error = ctypes.get_last_error()
                if error != 38:  # ERROR_HANDLE_EOF
                    raise CandidateContractError(
                        f"alternate stream enumeration failed for {path}: "
                        f"Win32 error {error}"
                    )
                break
    finally:
        find_close(handle)
    return tuple(streams)


def _hash_stable_regular_file(
    path: Path, max_bytes: int = MAX_INSTALLED_FILE_BYTES
) -> tuple[int, str]:
    """Hash a single-link regular file through one authenticated open handle."""

    if path.is_symlink():
        raise CandidateContractError(f"symlink refused: {path}")
    before = path.stat(follow_symlinks=False)
    if _is_reparse(before):
        raise CandidateContractError(f"reparse point refused: {path}")
    if not stat.S_ISREG(before.st_mode):
        raise CandidateContractError(f"not a regular file: {path}")
    if getattr(before, "st_nlink", 1) != 1:
        raise CandidateContractError(f"hard-linked file refused: {path}")
    if before.st_size <= 0 or before.st_size > max_bytes:
        raise CandidateContractError(f"file size outside bounds: {path}")
    streams = _named_alternate_streams(path)
    if streams:
        raise CandidateContractError(
            f"named alternate data stream refused for {path}: {streams}"
        )

    digest = hashlib.sha256()
    read_bytes = 0
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise CandidateContractError(f"file identity changed before read: {path}")
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            read_bytes += len(chunk)
            if read_bytes > max_bytes:
                raise CandidateContractError(f"file exceeds byte ceiling: {path}")
            digest.update(chunk)
        after = os.fstat(handle.fileno())

    if read_bytes != before.st_size:
        raise CandidateContractError(f"file length changed during read: {path}")
    if (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        getattr(after, "st_nlink", 1),
    ) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
        getattr(opened, "st_nlink", 1),
    ):
        raise CandidateContractError(f"file changed during read: {path}")
    current = path.stat(follow_symlinks=False)
    if (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
        getattr(current, "st_nlink", 1),
    ) != (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        getattr(before, "st_nlink", 1),
    ):
        raise CandidateContractError(f"pathname identity changed after read: {path}")
    streams_after = _named_alternate_streams(path)
    if streams_after:
        raise CandidateContractError(
            f"named alternate data stream appeared for {path}: {streams_after}"
        )
    return read_bytes, digest.hexdigest().upper()


def _is_fork_input_file(relative: str) -> bool:
    return (
        relative == "NwiroIntegrationKit.uplugin"
        or relative.startswith("Resources/")
        or relative.startswith("Source/")
    )


def _is_fork_input_directory(relative: str) -> bool:
    return (
        relative == "Resources"
        or relative.startswith("Resources/")
        or relative == "Source"
        or relative.startswith("Source/")
    )


def _record_digest(records: list[dict[str, Any]]) -> str:
    lines = [
        f"{record['path']}\t{record['bytes']}\t{record['sha256']}\n"
        for record in sorted(records, key=lambda record: record["path"])
    ]
    return _sha256("".join(lines).encode("utf-8"))


def _topology_digest(
    directories: list[str], records: list[dict[str, Any]]
) -> str:
    entries: list[tuple[str, str]] = [
        (relative, f"D\t{relative}\n") for relative in directories
    ]
    entries.extend(
        (
            record["path"],
            (
                f"F\t{record['path']}\t{record['bytes']}\t"
                f"{record['sha256']}\n"
            ),
        )
        for record in records
    )
    return _sha256("".join(line for _, line in sorted(entries)).encode("utf-8"))


def _enumerate_topology(root: Path) -> list[tuple[str, str]]:
    """Re-enumerate names and kinds to detect additions/removals after hashing."""

    root_info = root.stat(follow_symlinks=False)
    stack = [(root, (root_info.st_dev, root_info.st_ino))]
    entries_found: list[tuple[str, str]] = []
    while stack:
        directory, expected_identity = stack.pop()
        directory_info = directory.stat(follow_symlinks=False)
        if (
            directory.is_symlink()
            or _is_reparse(directory_info)
            or not stat.S_ISDIR(directory_info.st_mode)
            or (directory_info.st_dev, directory_info.st_ino) != expected_identity
        ):
            raise CandidateContractError(
                f"tree directory identity changed: {directory}"
            )
        directory_streams = _named_alternate_streams(directory)
        if directory_streams:
            raise CandidateContractError(
                f"directory alternate data stream refused for {directory}: "
                f"{directory_streams}"
            )
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name, reverse=True)
        directory_after = directory.stat(follow_symlinks=False)
        if (
            directory.is_symlink()
            or _is_reparse(directory_after)
            or not stat.S_ISDIR(directory_after.st_mode)
            or (directory_after.st_dev, directory_after.st_ino)
            != expected_identity
            or _named_alternate_streams(directory)
        ):
            raise CandidateContractError(
                f"tree directory changed during enumeration: {directory}"
            )
        for entry in entries:
            path = Path(entry.path)
            info = path.stat(follow_symlinks=False)
            if entry.is_symlink() or _is_reparse(info):
                raise CandidateContractError(f"tree link/reparse refused: {path}")
            relative = path.relative_to(root).as_posix()
            if stat.S_ISDIR(info.st_mode):
                entries_found.append((relative, "directory"))
                stack.append((path, (info.st_dev, info.st_ino)))
            elif stat.S_ISREG(info.st_mode):
                entries_found.append((relative, "file"))
            else:
                raise CandidateContractError(f"non-regular tree entry: {path}")
    return sorted(entries_found)


def build_plugin_tree_manifests(root: Path) -> dict[str, dict[str, Any]]:
    """Authenticate complete installation and exact source-fork input trees."""

    if not root.is_absolute():
        raise CandidateContractError("plugin root must be absolute")
    _validate_existing_ancestor_chain(root)
    root_info = root.stat(follow_symlinks=False)
    if root.is_symlink() or _is_reparse(root_info) or not stat.S_ISDIR(root_info.st_mode):
        raise CandidateContractError("plugin root must be a normal directory")

    root_identity = (root_info.st_dev, root_info.st_ino)
    root_streams = _named_alternate_streams(root)
    if root_streams:
        raise CandidateContractError(
            f"plugin root alternate data stream refused: {root_streams}"
        )
    stack = [(root, root_identity)]
    records: list[dict[str, Any]] = []
    directories: list[str] = []
    seen_paths: set[str] = set()
    seen_directories: set[tuple[int, int]] = set()
    total_bytes = 0

    while stack:
        directory, expected_identity = stack.pop()
        directory_info = directory.stat(follow_symlinks=False)
        if (
            directory.is_symlink()
            or _is_reparse(directory_info)
            or not stat.S_ISDIR(directory_info.st_mode)
            or (directory_info.st_dev, directory_info.st_ino) != expected_identity
        ):
            raise CandidateContractError(
                f"tree directory identity changed: {directory}"
            )
        directory_streams = _named_alternate_streams(directory)
        if directory_streams:
            raise CandidateContractError(
                f"directory alternate data stream refused for {directory}: "
                f"{directory_streams}"
            )
        identity = (directory_info.st_dev, directory_info.st_ino)
        if identity in seen_directories:
            raise CandidateContractError(f"directory identity repeated: {directory}")
        seen_directories.add(identity)
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name, reverse=True)
        directory_after = directory.stat(follow_symlinks=False)
        if (
            directory.is_symlink()
            or _is_reparse(directory_after)
            or not stat.S_ISDIR(directory_after.st_mode)
            or (directory_after.st_dev, directory_after.st_ino)
            != expected_identity
            or _named_alternate_streams(directory)
        ):
            raise CandidateContractError(
                f"tree directory changed during enumeration: {directory}"
            )
        for entry in entries:
            path = Path(entry.path)
            entry_info = path.stat(follow_symlinks=False)
            if entry.is_symlink() or _is_reparse(entry_info):
                raise CandidateContractError(f"tree link/reparse refused: {path}")
            relative = path.relative_to(root).as_posix()
            if not relative or "\\" in relative or relative.startswith("../"):
                raise CandidateContractError(f"unsafe tree path: {relative}")
            folded = relative.casefold()
            if folded in seen_paths:
                raise CandidateContractError(f"case-colliding tree path: {relative}")
            seen_paths.add(folded)
            if stat.S_ISDIR(entry_info.st_mode):
                directories.append(relative)
                stack.append((path, (entry_info.st_dev, entry_info.st_ino)))
                continue
            if not stat.S_ISREG(entry_info.st_mode):
                raise CandidateContractError(f"non-regular tree entry: {path}")
            file_bytes, file_hash = _hash_stable_regular_file(path)
            total_bytes += file_bytes
            if total_bytes > MAX_INSTALLED_TREE_BYTES:
                raise CandidateContractError("installed tree exceeds byte ceiling")
            records.append(
                {
                    "path": relative,
                    "bytes": file_bytes,
                    "sha256": file_hash,
                }
            )

    records.sort(key=lambda record: record["path"])
    directories.sort()
    initial_topology = sorted(
        [(relative, "directory") for relative in directories]
        + [(record["path"], "file") for record in records]
    )
    if _enumerate_topology(root) != initial_topology:
        raise CandidateContractError("tree topology changed during authentication")

    fork_records = [
        record for record in records if _is_fork_input_file(record["path"])
    ]
    fork_directories = [
        relative for relative in directories if _is_fork_input_directory(relative)
    ]
    source_records = [
        record for record in records if record["path"].startswith("Source/")
    ]
    source_extensions: dict[str, int] = {}
    for record in source_records:
        extension = Path(record["path"]).suffix.lower()
        source_extensions[extension] = source_extensions.get(extension, 0) + 1
    top_level_counts: dict[str, int] = {}
    for record in records:
        top_level = record["path"].split("/", 1)[0]
        top_level_counts[top_level] = top_level_counts.get(top_level, 0) + 1
    return {
        "installed_tree_inventory": {
            "file_count": len(records),
            "directory_count_excluding_root": len(directories),
            "total_bytes": total_bytes,
            "record_set_sha256": _record_digest(records),
            "topology_sha256": _topology_digest(directories, records),
            "top_level_file_counts": dict(sorted(top_level_counts.items())),
        },
        "fork_input_tree": {
            "file_count": len(fork_records),
            "directory_count_excluding_root": len(fork_directories),
            "total_bytes": sum(record["bytes"] for record in fork_records),
            "record_set_sha256": _record_digest(fork_records),
            "topology_sha256": _topology_digest(fork_directories, fork_records),
            "included_directories": fork_directories,
            "source_file_count": len(source_records),
            "source_total_bytes": sum(
                record["bytes"] for record in source_records
            ),
            "source_record_set_sha256": _record_digest(source_records),
            "source_extension_counts": dict(sorted(source_extensions.items())),
        },
    }


def authenticate_plugin_tree_two_pass(
    root: Path,
) -> dict[str, dict[str, Any]]:
    """Require two consecutive complete observations to match byte-for-byte.

    This detects ordinary drift across the two passes. It deliberately does not
    claim an atomic whole-tree snapshot or protection from a concurrent writer
    that changes the tree after the second observation.
    """

    first = build_plugin_tree_manifests(root)
    second = build_plugin_tree_manifests(root)
    if first != second:
        raise CandidateContractError(
            "plugin tree changed between consecutive complete observations"
        )
    return second


def validate_contract_schema(contract: dict[str, Any]) -> None:
    _require_exact_keys(
        contract,
        {
            "schema_version",
            "contract_id",
            "status",
            "evidence_class",
            "execution",
            "parent_inputs",
            "baseline",
            "candidate",
            "allowed_change_surface",
            "required_controls",
            "probe_contract",
            "acceptance_gates",
            "claim_limit",
            "next_safe_action",
        },
        "contract",
    )
    _require_plain_int(contract["schema_version"], 1, "schema_version")
    _require_string(
        contract["contract_id"],
        "redmmo-nwiro-restricted-probe-candidate-v1",
        "contract_id",
    )
    _require_string(
        contract["status"],
        "candidate_contract_only_source_absent_runtime_forbidden",
        "status",
    )
    _require_string(contract["evidence_class"], "static", "evidence_class")

    execution = contract["execution"]
    if type(execution) is not dict:
        raise CandidateContractError("execution must be an object")
    execution_keys = {
        "runtime_authorized",
        "candidate_creation_authorized",
        "vendor_plugin_mutation_authorized",
        "project_plugin_activation_authorized",
        "unreal_launch_authorized",
        "build_authorized",
        "mcp_initialize_authorized",
        "mcp_tools_list_authorized",
        "mcp_tool_call_authorized",
        "network_authorized",
        "provider_call_authorized",
        "asset_load_authorized",
        "asset_write_authorized",
        "map_mutation_authorized",
        "codex_config_mutation_authorized",
        "diagnostic_stdout_authorized",
        "local_read_only_authentication_authorized",
    }
    _require_exact_keys(execution, execution_keys, "execution")
    for key in execution_keys:
        expected = key in {
            "diagnostic_stdout_authorized",
            "local_read_only_authentication_authorized",
        }
        _require_plain_bool(execution[key], expected, f"execution.{key}")

    inputs = contract["parent_inputs"]
    if type(inputs) is not list or len(inputs) != len(EXPECTED_PARENT_INPUTS):
        raise CandidateContractError("parent_inputs must have the exact reviewed set")
    for index, expected in enumerate(EXPECTED_PARENT_INPUTS):
        item = inputs[index]
        if type(item) is not dict:
            raise CandidateContractError(f"parent_inputs[{index}] must be an object")
        _require_exact_keys(item, {"id", "path", "bytes", "sha256"}, f"parent[{index}]")
        expected_id, expected_path, expected_bytes, expected_sha = expected
        _require_string(item["id"], expected_id, f"parent[{index}].id")
        _require_d_path(item["path"], expected_path, f"parent[{index}].path")
        _require_plain_int(item["bytes"], expected_bytes, f"parent[{index}].bytes")
        _require_string(item["sha256"], expected_sha, f"parent[{index}].sha256")

    baseline = contract["baseline"]
    if type(baseline) is not dict:
        raise CandidateContractError("baseline must be an object")
    _require_exact_keys(
        baseline,
        {
            "plugin_name",
            "plugin_version",
            "plugin_root",
            "descriptor",
            "observed_binary",
            "tree_digest_algorithm",
            "installed_tree_inventory",
            "fork_input_tree",
        },
        "baseline",
    )
    _require_string(baseline["plugin_name"], "Nwiro Integration Kit", "plugin_name")
    _require_string(baseline["plugin_version"], "1.0.9", "plugin_version")
    _require_d_path(
        baseline["plugin_root"],
        "D:/UE_5.8/Engine/Plugins/Marketplace/NWIROAIIf0b7fbfe049eV4",
        "baseline.plugin_root",
    )
    descriptor = baseline["descriptor"]
    _require_exact_keys(descriptor, {"path", "bytes", "sha256"}, "descriptor")
    _require_d_path(
        descriptor["path"],
        "D:/UE_5.8/Engine/Plugins/Marketplace/NWIROAIIf0b7fbfe049eV4/NwiroIntegrationKit.uplugin",
        "descriptor.path",
    )
    _require_plain_int(descriptor["bytes"], 1212, "descriptor.bytes")
    _require_string(
        descriptor["sha256"],
        "D6CCBFA2F08D478F0C53C67E0D8FCD5FF275C57948425D55D560309AD1C60B2E",
        "descriptor.sha256",
    )
    binary = baseline["observed_binary"]
    _require_exact_keys(
        binary,
        {
            "path",
            "bytes",
            "sha256",
            "candidate_binary_attestation",
            "loaded_module_attestation",
        },
        "observed_binary",
    )
    _require_d_path(
        binary["path"],
        "D:/UE_5.8/Engine/Plugins/Marketplace/NWIROAIIf0b7fbfe049eV4/Binaries/Win64/UnrealEditor-NwiroIntegrationKit.dll",
        "observed_binary.path",
    )
    _require_plain_int(binary["bytes"], 3491840, "observed_binary.bytes")
    _require_string(
        binary["sha256"],
        "6C72757C068FAD28174C9A2F2F4960C6FA69C908E993E854AC94454540A43C0C",
        "observed_binary.sha256",
    )
    _require_plain_bool(
        binary["candidate_binary_attestation"],
        False,
        "candidate_binary_attestation",
    )
    _require_plain_bool(
        binary["loaded_module_attestation"], False, "loaded_module_attestation"
    )

    _require_string(
        baseline["tree_digest_algorithm"],
        EXPECTED_TREE_DIGEST_ALGORITHM,
        "tree_digest_algorithm",
    )

    installed_tree = baseline["installed_tree_inventory"]
    _require_exact_keys(
        installed_tree,
        {
            "root",
            "file_count",
            "directory_count_excluding_root",
            "total_bytes",
            "record_set_sha256",
            "topology_sha256",
            "top_level_file_counts",
            "extra_file_policy",
            "missing_file_policy",
            "case_collision_policy",
            "symlink_policy",
            "reparse_point_policy",
            "hardlink_policy",
            "file_and_directory_alternate_data_stream_policy",
            "per_file_stable_handle_reauthentication_required",
            "two_consecutive_complete_passes_required",
            "whole_tree_snapshot_stability_proven",
            "concurrent_mutation_resistance_proven",
        },
        "installed_tree_inventory",
    )
    _require_d_path(
        installed_tree["root"],
        "D:/UE_5.8/Engine/Plugins/Marketplace/NWIROAIIf0b7fbfe049eV4",
        "installed_tree_inventory.root",
    )
    _require_plain_int(
        installed_tree["file_count"], 106, "installed_tree_inventory.file_count"
    )
    _require_plain_int(
        installed_tree["directory_count_excluding_root"],
        29,
        "installed_tree_inventory.directory_count_excluding_root",
    )
    _require_plain_int(
        installed_tree["total_bytes"],
        130151566,
        "installed_tree_inventory.total_bytes",
    )
    _require_string(
        installed_tree["record_set_sha256"],
        "DF5067FAEB002FCC10F52D212AB9C8133973D28070EB4D5C969A4205F0A833F0",
        "installed_tree_inventory.record_set_sha256",
    )
    _require_string(
        installed_tree["topology_sha256"],
        "6CC8D966C1D40CB319082823BB51FB8B420132A64FDDC8BA01562786B0A4B11C",
        "installed_tree_inventory.topology_sha256",
    )
    if installed_tree["top_level_file_counts"] != EXPECTED_TOP_LEVEL_COUNTS:
        raise CandidateContractError("installed tree top-level counts changed")
    for policy in (
        "extra_file_policy",
        "missing_file_policy",
        "case_collision_policy",
        "symlink_policy",
        "reparse_point_policy",
        "hardlink_policy",
        "file_and_directory_alternate_data_stream_policy",
    ):
        _require_string(
            installed_tree[policy],
            "deny",
            f"installed_tree_inventory.{policy}",
        )
    _require_plain_bool(
        installed_tree["per_file_stable_handle_reauthentication_required"],
        True,
        "installed_tree_inventory.per_file_stable_handle_reauthentication_required",
    )
    _require_plain_bool(
        installed_tree["two_consecutive_complete_passes_required"],
        True,
        "installed_tree_inventory.two_consecutive_complete_passes_required",
    )
    for key in (
        "whole_tree_snapshot_stability_proven",
        "concurrent_mutation_resistance_proven",
    ):
        _require_plain_bool(installed_tree[key], False, f"installed_tree.{key}")

    fork_tree = baseline["fork_input_tree"]
    _require_exact_keys(
        fork_tree,
        {
            "root",
            "included_roots",
            "included_directories",
            "file_count",
            "directory_count_excluding_root",
            "total_bytes",
            "record_set_sha256",
            "topology_sha256",
            "source_file_count",
            "source_total_bytes",
            "source_record_set_sha256",
            "source_extension_counts",
            "source_third_party_miniz_required",
            "resources_required",
            "descriptor_required",
            "vendor_binaries_allowed_in_candidate_lineage",
            "vendor_intermediate_allowed_in_candidate_lineage",
            "extra_file_policy",
            "missing_file_policy",
            "case_collision_policy",
            "symlink_policy",
            "reparse_point_policy",
            "hardlink_policy",
            "file_and_directory_alternate_data_stream_policy",
            "per_file_stable_handle_reauthentication_required",
            "two_consecutive_complete_passes_required",
            "whole_tree_snapshot_stability_proven",
            "concurrent_mutation_resistance_proven",
        },
        "fork_input_tree",
    )
    _require_d_path(
        fork_tree["root"],
        "D:/UE_5.8/Engine/Plugins/Marketplace/NWIROAIIf0b7fbfe049eV4",
        "fork_input_tree.root",
    )
    if fork_tree["included_roots"] != [
        "NwiroIntegrationKit.uplugin",
        "Resources",
        "Source",
    ]:
        raise CandidateContractError("fork input roots changed")
    if tuple(fork_tree["included_directories"]) != EXPECTED_FORK_INPUT_DIRECTORIES:
        raise CandidateContractError("fork input directory allowlist changed")
    for key, expected in (
        ("file_count", 90),
        ("directory_count_excluding_root", 10),
        ("total_bytes", 2201579),
        ("source_file_count", 87),
        ("source_total_bytes", 2153385),
    ):
        _require_plain_int(fork_tree[key], expected, f"fork_input_tree.{key}")
    for key, expected in (
        (
            "record_set_sha256",
            "F1D91F85B8D7BE403D3AEFAA3348CE65B4CDC6EC52F1627CB141339C39FD1D4A",
        ),
        (
            "topology_sha256",
            "16DC68F9DDEFB5A957822EFB58A129BC11C18BFE98B8121B4E3010C1606EA3AD",
        ),
        (
            "source_record_set_sha256",
            "2F77617A4BB84E662E73BD9EF6F09FD5880B19E81A7E030B7C43F16440402670",
        ),
    ):
        _require_string(fork_tree[key], expected, f"fork_input_tree.{key}")
    if fork_tree["source_extension_counts"] != EXPECTED_SOURCE_EXTENSION_COUNTS:
        raise CandidateContractError("fork source extension counts changed")
    for key in (
        "source_third_party_miniz_required",
        "resources_required",
        "descriptor_required",
        "per_file_stable_handle_reauthentication_required",
        "two_consecutive_complete_passes_required",
    ):
        _require_plain_bool(fork_tree[key], True, f"fork_input_tree.{key}")
    for key in (
        "whole_tree_snapshot_stability_proven",
        "concurrent_mutation_resistance_proven",
    ):
        _require_plain_bool(fork_tree[key], False, f"fork_input_tree.{key}")
    for key in (
        "vendor_binaries_allowed_in_candidate_lineage",
        "vendor_intermediate_allowed_in_candidate_lineage",
    ):
        _require_plain_bool(fork_tree[key], False, f"fork_input_tree.{key}")
    for policy in (
        "extra_file_policy",
        "missing_file_policy",
        "case_collision_policy",
        "symlink_policy",
        "reparse_point_policy",
        "hardlink_policy",
        "file_and_directory_alternate_data_stream_policy",
    ):
        _require_string(fork_tree[policy], "deny", f"fork_input_tree.{policy}")

    candidate = contract["candidate"]
    _require_exact_keys(
        candidate,
        {
            "candidate_id",
            "staging_root",
            "staging_root_required_absent",
            "candidate_source_present",
            "candidate_manifest_present",
            "fork_skeleton_present",
            "project_plugin_enabled",
            "vendor_plugin_modified",
            "candidate_binary_present",
            "candidate_binary_attested",
            "candidate_static_accepted",
            "candidate_runtime_accepted",
            "activation_plan_status",
        },
        "candidate",
    )
    _require_string(
        candidate["candidate_id"],
        "nwiro-restricted-probe-fork-candidate-v1",
        "candidate_id",
    )
    _require_d_path(
        candidate["staging_root"],
        "D:/RedMMOTitanWindowsData/Staging/NwiroRestrictedProbeForkCandidateV1",
        "candidate.staging_root",
    )
    for key in (
        "staging_root_required_absent",
        "candidate_source_present",
        "candidate_manifest_present",
        "fork_skeleton_present",
        "project_plugin_enabled",
        "vendor_plugin_modified",
        "candidate_binary_present",
        "candidate_binary_attested",
        "candidate_static_accepted",
        "candidate_runtime_accepted",
    ):
        _require_plain_bool(
            candidate[key], key == "staging_root_required_absent", f"candidate.{key}"
        )
    _require_string(
        candidate["activation_plan_status"],
        "not_designed_not_authorized",
        "activation_plan_status",
    )

    changes = contract["allowed_change_surface"]
    _require_exact_keys(
        changes,
        {
            "baseline_files_allowed_to_change_in_candidate",
            "new_candidate_files_allowed",
            "path_base",
            "all_other_baseline_source_files_must_match",
            "file_deletion_allowed",
            "file_rename_allowed",
            "path_case_change_allowed",
            "descriptor_change_allowed",
            "build_rules_change_allowed",
            "binary_or_generated_file_in_source_tree_allowed",
            "candidate_prebuild_forbidden_roots",
        },
        "allowed_change_surface",
    )
    if tuple(changes["baseline_files_allowed_to_change_in_candidate"]) != (
        EXPECTED_CHANGED_FILES
    ):
        raise CandidateContractError("candidate changed-file allowlist changed")
    if tuple(changes["new_candidate_files_allowed"]) != EXPECTED_NEW_FILES:
        raise CandidateContractError("candidate new-file allowlist changed")
    _require_string(
        changes["path_base"],
        "Source/NwiroIntegrationKit",
        "allowed_change_surface.path_base",
    )
    if tuple(changes["candidate_prebuild_forbidden_roots"]) != (
        EXPECTED_FORBIDDEN_CANDIDATE_ROOTS
    ):
        raise CandidateContractError("candidate forbidden-root policy changed")
    _require_plain_bool(
        changes["all_other_baseline_source_files_must_match"],
        True,
        "all_other_baseline_source_files_must_match",
    )
    for key in (
        "file_deletion_allowed",
        "file_rename_allowed",
        "path_case_change_allowed",
        "descriptor_change_allowed",
        "build_rules_change_allowed",
        "binary_or_generated_file_in_source_tree_allowed",
    ):
        _require_plain_bool(changes[key], False, f"allowed_change_surface.{key}")

    controls = contract["required_controls"]
    if type(controls) is not list or len(controls) != len(EXPECTED_CONTROL_IDS):
        raise CandidateContractError("required_controls must have exact length")
    for index, control_id in enumerate(EXPECTED_CONTROL_IDS):
        control = controls[index]
        _require_exact_keys(
            control, {"id", "required", "implemented", "accepted"}, f"control[{index}]"
        )
        _require_string(control["id"], control_id, f"control[{index}].id")
        _require_plain_bool(control["required"], True, f"control[{index}].required")
        _require_plain_bool(
            control["implemented"], False, f"control[{index}].implemented"
        )
        _require_plain_bool(
            control["accepted"], False, f"control[{index}].accepted"
        )

    probe = contract["probe_contract"]
    _require_exact_keys(
        probe,
        {
            "stable_candidate_id",
            "tool_name",
            "observed_vendor_tool_definition_sha256",
            "additional_tools_allowed",
            "additional_arguments_allowed",
            "argument_coercion_allowed",
            "arguments",
            "expected_single_identity",
            "extra_response_fields_allowed",
            "vendor_or_derived_bytes_may_leave_process",
            "all_source_packs_allow_usage_with_ai",
        },
        "probe_contract",
    )
    _require_string(
        probe["stable_candidate_id"],
        "RED-FAB-ASSET-8021792003EC13E7D10DBB1B",
        "stable_candidate_id",
    )
    _require_string(probe["tool_name"], "find_assets", "tool_name")
    _require_string(
        probe["observed_vendor_tool_definition_sha256"],
        "58DCD431CFCB943C9C2B8215F7FF8D69B43450A5CB4959377D47BFBFEE4C70C2",
        "observed_vendor_tool_definition_sha256",
    )
    for key in (
        "additional_tools_allowed",
        "additional_arguments_allowed",
        "argument_coercion_allowed",
        "extra_response_fields_allowed",
        "vendor_or_derived_bytes_may_leave_process",
        "all_source_packs_allow_usage_with_ai",
    ):
        _require_plain_bool(probe[key], False, f"probe_contract.{key}")
    if probe["arguments"] != EXPECTED_ARGUMENTS:
        raise CandidateContractError("probe arguments changed")
    if probe["expected_single_identity"] != EXPECTED_IDENTITY:
        raise CandidateContractError("probe expected identity changed")

    gates = contract["acceptance_gates"]
    expected_gate_values = {
        "contract_artifact_static_validated": True,
        "complete_installed_tree_two_pass_observation_matched": True,
        "complete_fork_input_tree_two_pass_observation_matched": True,
        "candidate_source_manifest_authenticated": False,
        "candidate_semantic_mutation_tests_passed": False,
        "candidate_independent_source_review_passed": False,
        "candidate_build_passed": False,
        "candidate_binary_authenticated": False,
        "candidate_installed": False,
        "candidate_module_loaded": False,
        "candidate_live_probe_passed": False,
        "rights_review_passed": False,
        "asset_registry_closure_passed": False,
        "migration_passed": False,
        "map_authoring_passed": False,
        "real_gpu_visual_passed": False,
    }
    _require_exact_keys(gates, set(expected_gate_values), "acceptance_gates")
    for key, expected in expected_gate_values.items():
        _require_plain_bool(gates[key], expected, f"acceptance_gates.{key}")
    if type(contract["claim_limit"]) is not str or not contract["claim_limit"]:
        raise CandidateContractError("claim_limit must be nonempty")
    if type(contract["next_safe_action"]) is not str or not contract["next_safe_action"]:
        raise CandidateContractError("next_safe_action must be nonempty")


def _authenticate_record(record: dict[str, Any], label: str) -> dict[str, Any]:
    path = Path(record["path"])
    payload = _read_stable_regular_file(path)
    actual_hash = _sha256(payload)
    if len(payload) != record["bytes"] or actual_hash != record["sha256"]:
        raise CandidateContractError(f"{label} bytes or hash changed")
    return {
        "id": record.get("id", label),
        "path": path.as_posix(),
        "bytes": len(payload),
        "sha256": actual_hash,
    }


def validate_contract_file(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    if path.resolve(strict=True) != DEFAULT_CONTRACT.resolve(strict=True):
        raise CandidateContractError("only the canonical contract path is accepted")
    payload = _read_stable_regular_file(path, MAX_JSON_BYTES)
    contract_hash = _sha256(payload)
    if contract_hash != EXPECTED_CONTRACT_SHA256:
        raise CandidateContractError(
            f"contract hash drift: {contract_hash} != {EXPECTED_CONTRACT_SHA256}"
        )
    contract = load_json_bytes_strict(payload, "candidate contract")
    validate_contract_schema(contract)

    authenticated_inputs = [
        _authenticate_record(record, f"parent_inputs[{index}]")
        for index, record in enumerate(contract["parent_inputs"])
    ]
    descriptor = _authenticate_record(
        contract["baseline"]["descriptor"], "baseline descriptor"
    )
    observed_binary = _authenticate_record(
        contract["baseline"]["observed_binary"], "observed baseline binary"
    )

    plugin_root = Path(contract["baseline"]["plugin_root"])
    manifests = authenticate_plugin_tree_two_pass(plugin_root)
    installed_contract = contract["baseline"]["installed_tree_inventory"]
    expected_installed = {
        key: installed_contract[key]
        for key in (
            "file_count",
            "directory_count_excluding_root",
            "total_bytes",
            "record_set_sha256",
            "topology_sha256",
            "top_level_file_counts",
        )
    }
    if manifests["installed_tree_inventory"] != expected_installed:
        raise CandidateContractError(
            "complete installed tree changed: "
            f"{manifests['installed_tree_inventory']} != {expected_installed}"
        )
    fork_contract = contract["baseline"]["fork_input_tree"]
    expected_fork = {
        key: fork_contract[key]
        for key in (
            "file_count",
            "directory_count_excluding_root",
            "total_bytes",
            "record_set_sha256",
            "topology_sha256",
            "included_directories",
            "source_file_count",
            "source_total_bytes",
            "source_record_set_sha256",
            "source_extension_counts",
        )
    }
    if manifests["fork_input_tree"] != expected_fork:
        raise CandidateContractError(
            "fork input tree changed: "
            f"{manifests['fork_input_tree']} != {expected_fork}"
        )

    candidate_root = Path(contract["candidate"]["staging_root"])
    _validate_existing_ancestor_chain(candidate_root)
    if candidate_root.exists() or candidate_root.is_symlink():
        raise CandidateContractError(
            f"candidate root must remain absent in contract-only v1: {candidate_root}"
        )

    return {
        "schema_version": 1,
        "contract_id": contract["contract_id"],
        "status": contract["status"],
        "evidence_class": "static",
        "contract_sha256": contract_hash,
        "parent_input_count": len(authenticated_inputs),
        "baseline_descriptor": descriptor,
        "observed_baseline_binary": observed_binary,
        "installed_tree_inventory": manifests["installed_tree_inventory"],
        "fork_input_tree": manifests["fork_input_tree"],
        "candidate_root": candidate_root.as_posix(),
        "candidate_root_absent": True,
        "required_control_count": len(contract["required_controls"]),
        "complete_observation_passes": 2,
        "whole_tree_snapshot_stability_proven": False,
        "concurrent_mutation_resistance_proven": False,
        "candidate_static_accepted": False,
        "runtime_authorized": False,
        "next_safe_action": contract["next_safe_action"],
    }


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = validate_contract_file(args.contract)
    except (OSError, CandidateContractError) as error:
        print(f"NWIRO candidate contract error: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True).encode("ascii")
        + b"\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
