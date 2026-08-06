#!/usr/bin/env python3
"""Create or verify the inert Nwiro restricted-probe source skeleton.

This tool has a deliberately fixed change surface.  It may copy only the
authenticated descriptor, Resources, and Source inputs from the installed
Nwiro Integration Kit 1.0.9 tree into one project-owned D: staging root.  That
root is outside the two configured automatic Unreal plugin roots checked by
this workflow; explicit additional plugin paths are outside this claim.  The
tool never edits source bytes, builds, installs, launches Unreal, initializes
MCP, binds a network transport, or calls a tool.

The immutable parent contract is historical after creation because it requires
the candidate root to be absent.  Therefore ``--create`` authenticates that
contract before publication and also requires a separate exact-hash execution
authorization.  ``--verify`` reauthenticates both immutable inputs plus the
published candidate and its separate baseline/candidate/delta manifests.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from validate_redmmo_nwiro_restricted_probe_candidate_contract import (
    CandidateContractError,
    _hash_stable_regular_file,
    _is_reparse,
    _named_alternate_streams,
    _read_stable_regular_file,
    _validate_existing_ancestor_chain,
    authenticate_plugin_tree_two_pass,
    canonical_json_bytes,
    load_json_bytes_strict,
    validate_contract_file,
    validate_contract_schema,
)


PROJECT_ROOT = Path(r"D:\RedMMOTitan")
CONTRACT_PATH = (
    PROJECT_ROOT
    / "Build"
    / "Automation"
    / "redmmo_nwiro_restricted_probe_candidate_contract_v1.json"
)
CONTRACT_SHA256 = (
    "AD53BE2585A6B03F74C53A36EE6A30318F318ACC5F2798E664CBD37BCBEDC7DE"
)
EXECUTION_AUTH_PATH = (
    PROJECT_ROOT
    / "Build"
    / "Automation"
    / "redmmo_nwiro_candidate_skeleton_execution_authorization_v1.json"
)
CREATOR_TEST_PATH = (
    PROJECT_ROOT
    / "Tools"
    / "tests"
    / "test_create_redmmo_nwiro_restricted_probe_candidate.py"
)
SOURCE_ROOT = Path(
    r"D:\UE_5.8\Engine\Plugins\Marketplace\NWIROAIIf0b7fbfe049eV4"
)
STAGING_PARENT = Path(r"D:\RedMMOTitanWindowsData\Staging")
CANDIDATE_ROOT = STAGING_PARENT / "NwiroRestrictedProbeForkCandidateV1"
PROJECT_DESCRIPTOR = PROJECT_ROOT / "Titan.uproject"

BASELINE_MANIFEST_PATH = (
    STAGING_PARENT / "NwiroRestrictedProbeForkCandidateV1.baseline.v1.json"
)
CANDIDATE_MANIFEST_PATH = (
    STAGING_PARENT / "NwiroRestrictedProbeForkCandidateV1.candidate.v1.json"
)
DELTA_MANIFEST_PATH = (
    STAGING_PARENT / "NwiroRestrictedProbeForkCandidateV1.delta.v1.json"
)
ROLLBACK_PARENT = Path(r"D:\RedMMOTitanWindowsData\Rollback")
QUARANTINE_ROOT = (
    ROLLBACK_PARENT / "NwiroCandidateSkeletonV1FailedPublication"
)

_CANDIDATE_NAME = "NwiroRestrictedProbeForkCandidateV1"
_TRANSACTION_PREFIX = f".{_CANDIDATE_NAME}.txn."

EXPECTED_FILE_COUNT = 90
EXPECTED_DIRECTORY_COUNT = 10
EXPECTED_TOTAL_BYTES = 2_201_579
EXPECTED_RECORD_SET_SHA256 = (
    "F1D91F85B8D7BE403D3AEFAA3348CE65B4CDC6EC52F1627CB141339C39FD1D4A"
)
EXPECTED_TOPOLOGY_SHA256 = (
    "16DC68F9DDEFB5A957822EFB58A129BC11C18BFE98B8121B4E3010C1606EA3AD"
)
EXPECTED_DIRECTORIES = (
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
FORBIDDEN_CANDIDATE_ROOTS = (
    ".git",
    "Binaries",
    "Config",
    "Content",
    "Intermediate",
    "Saved",
)
PROTECTED_INPUTS = {
    PROJECT_ROOT / "Content/RedMMO/Maps/RedPlanetGen.umap": (
        "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724"
    ),
    PROJECT_ROOT / "Content/RedMMO/Maps/RedPlanetGen_50km_Test.umap": (
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D"
    ),
    PROJECT_ROOT / "Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap": (
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284"
    ),
    PROJECT_ROOT
    / "Content/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield.uasset": (
        "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562"
    ),
}

_WINDOWS_FILE_ID_INFO = 18
_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_FILE_SHARE_DELETE = 0x00000004
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_MOVEFILE_WRITE_THROUGH = 0x00000008
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_SYSTEM32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
_ICACLS = _SYSTEM32 / "icacls.exe"
_POWERSHELL = (
    Path(os.environ.get("SystemRoot", r"C:\Windows"))
    / "System32"
    / "WindowsPowerShell"
    / "v1.0"
    / "powershell.exe"
)
_RFC3339_UTC = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
_RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class CandidateCreationError(RuntimeError):
    """Fail-closed candidate creation or verification error."""


class _WindowsFileId128(ctypes.Structure):
    _fields_ = [("Identifier", ctypes.c_ubyte * 16)]


class _WindowsFileIdInformation(ctypes.Structure):
    _fields_ = [
        ("VolumeSerialNumber", ctypes.c_ulonglong),
        ("FileId", _WindowsFileId128),
    ]


@dataclass(frozen=True)
class TreeSnapshot:
    root: str
    directories: tuple[dict[str, Any], ...]
    files: tuple[dict[str, Any], ...]
    file_count: int
    directory_count_excluding_root: int
    total_bytes: int
    record_set_sha256: str
    topology_sha256: str

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "directories": list(self.directories),
            "files": list(self.files),
            "file_count": self.file_count,
            "directory_count_excluding_root": self.directory_count_excluding_root,
            "total_bytes": self.total_bytes,
            "record_set_sha256": self.record_set_sha256,
            "topology_sha256": self.topology_sha256,
        }


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _canonical_file_bytes(value: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(dict(value))


def _path_text(path: Path) -> str:
    return path.resolve(strict=False).as_posix()


def _lexists(path: Path) -> bool:
    return os.path.lexists(str(path))


def _require_windows() -> None:
    if os.name != "nt":
        raise CandidateCreationError("this fixed candidate publisher requires Windows")


def _require_fixed_layout() -> None:
    _require_windows()
    expected_candidate = (
        Path(r"D:\RedMMOTitanWindowsData\Staging")
        / "NwiroRestrictedProbeForkCandidateV1"
    )
    if CANDIDATE_ROOT != expected_candidate:
        raise CandidateCreationError("candidate root constant drift")
    manifest_paths = (
        BASELINE_MANIFEST_PATH,
        CANDIDATE_MANIFEST_PATH,
        DELTA_MANIFEST_PATH,
    )
    if any(path.parent != CANDIDATE_ROOT.parent for path in manifest_paths):
        raise CandidateCreationError("manifests must be candidate siblings")
    candidate_folded = str(CANDIDATE_ROOT).casefold()
    forbidden_discovery_roots = (
        str(PROJECT_ROOT / "Plugins").casefold(),
        str(Path(r"D:\UE_5.8\Engine\Plugins")).casefold(),
    )
    for discovery_root in forbidden_discovery_roots:
        prefix = discovery_root.rstrip("\\/") + os.sep
        if candidate_folded == discovery_root or candidate_folded.startswith(prefix):
            raise CandidateCreationError(
                "candidate root overlaps an Unreal plugin discovery root"
            )
    for manifest_path in manifest_paths:
        if _path_text(manifest_path).casefold().startswith(
            _path_text(CANDIDATE_ROOT).casefold().rstrip("/") + "/"
        ):
            raise CandidateCreationError(
                "manifests must remain outside candidate tree"
            )


def _require_strict_utc(value: Any, label: str) -> str:
    if type(value) is not str or not _RFC3339_UTC.fullmatch(value):
        raise CandidateCreationError(f"{label} is not strict UTC RFC3339")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CandidateCreationError(f"{label} is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        raise CandidateCreationError(f"{label} is not UTC")
    return value


def _reserved_namespace_names() -> set[str]:
    """Return only names reserved to this workflow in the staging parent."""

    if not STAGING_PARENT.is_dir():
        raise CandidateCreationError("staging parent is absent")
    base_folded = _CANDIDATE_NAME.casefold()
    transaction_folded = _TRANSACTION_PREFIX.casefold()
    names: set[str] = set()
    folded_names: set[str] = set()
    with os.scandir(STAGING_PARENT) as iterator:
        entries = list(iterator)
    for entry in entries:
        name = entry.name
        folded = name.casefold()
        if (
            folded == base_folded
            or folded.startswith(base_folded + ".")
            or folded.startswith(transaction_folded)
        ):
            if folded in folded_names:
                raise CandidateCreationError(
                    "case-colliding reserved staging names"
                )
            folded_names.add(folded)
            names.add(name)
    return names


def _require_reserved_namespace(expected_names: set[str]) -> None:
    observed = _reserved_namespace_names()
    if observed != expected_names:
        raise CandidateCreationError(
            "reserved staging namespace drift: "
            f"expected={sorted(expected_names)!r} observed={sorted(observed)!r}"
        )


def _execution_authorization_expected(
    *,
    authorized_utc: str,
    creator_hash: str,
    creator_bytes: int,
    creator_test_hash: str,
    creator_test_bytes: int,
    project_descriptor_hash: str,
    project_descriptor_bytes: int,
    protected_inputs: Mapping[str, str],
) -> dict[str, Any]:
    protected_records = [
        {
            "path": path,
            "bytes": Path(path).stat().st_size,
            "sha256": digest,
        }
        for path, digest in sorted(protected_inputs.items())
    ]
    return {
        "schema_version": 1,
        "authorization_id": (
            "redmmo-nwiro-candidate-skeleton-execution-authorization-v1"
        ),
        "status": "approved_once_offline_candidate_skeleton_only",
        "evidence_class": "static",
        "authorized_utc": authorized_utc,
        "approved_operation": (
            "Copy the authenticated descriptor, Resources, and Source fork "
            "input into the fixed external candidate root and publish the "
            "three fixed lineage manifests once."
        ),
        "parent_contract": {
            "path": _path_text(CONTRACT_PATH),
            "bytes": CONTRACT_PATH.stat().st_size,
            "sha256": CONTRACT_SHA256,
        },
        "creator": {
            "path": _path_text(Path(__file__)),
            "bytes": creator_bytes,
            "sha256": creator_hash,
        },
        "creator_tests": {
            "path": _path_text(CREATOR_TEST_PATH),
            "bytes": creator_test_bytes,
            "sha256": creator_test_hash,
        },
        "source_fork_input": {
            "root": _path_text(SOURCE_ROOT),
            "file_count": EXPECTED_FILE_COUNT,
            "directory_count_excluding_root": EXPECTED_DIRECTORY_COUNT,
            "total_bytes": EXPECTED_TOTAL_BYTES,
            "record_set_sha256": EXPECTED_RECORD_SET_SHA256,
            "topology_sha256": EXPECTED_TOPOLOGY_SHA256,
        },
        "project_descriptor": {
            "path": _path_text(PROJECT_DESCRIPTOR),
            "bytes": project_descriptor_bytes,
            "sha256": project_descriptor_hash,
            "mutation_authorized": False,
        },
        "protected_inputs": protected_records,
        "authorized_outputs": {
            "staging_parent": _path_text(STAGING_PARENT),
            "candidate_root": _path_text(CANDIDATE_ROOT),
            "baseline_manifest": _path_text(BASELINE_MANIFEST_PATH),
            "candidate_manifest": _path_text(CANDIDATE_MANIFEST_PATH),
            "delta_manifest": _path_text(DELTA_MANIFEST_PATH),
            "rollback_reservation": _path_text(QUARANTINE_ROOT),
            "private_transaction_parent": _path_text(STAGING_PARENT),
            "private_transaction_name_prefix": _TRANSACTION_PREFIX,
            "single_use_publication": True,
        },
        "execution": {
            "candidate_creation_authorized": True,
            "manifest_publication_authorized": True,
            "staging_parent_creation_authorized": True,
            "private_transaction_authorized": True,
            "rollback_reservation_authorized": True,
            "source_read_and_hash_authorized": True,
            "source_mutation_authorized": False,
            "vendor_plugin_mutation_authorized": False,
            "project_plugin_activation_authorized": False,
            "runtime_authorized": False,
            "build_authorized": False,
            "install_authorized": False,
            "unreal_launch_authorized": False,
            "mcp_initialize_authorized": False,
            "mcp_tools_list_authorized": False,
            "mcp_tool_call_authorized": False,
            "network_authorized": False,
            "provider_call_authorized": False,
            "asset_load_authorized": False,
            "asset_write_authorized": False,
            "map_mutation_authorized": False,
            "codex_config_mutation_authorized": False,
            "protected_input_mutation_authorized": False,
            "diagnostic_stdout_authorized": True,
        },
        "facts": {
            "source_default_off": False,
            "restricted_mode_implemented": False,
            "candidate_static_accepted": False,
            "candidate_runtime_accepted": False,
            "outside_two_checked_automatic_plugin_roots": True,
            "universal_plugin_discovery_exclusion_proven": False,
        },
        "claim_limit": (
            "One offline exact-copy skeleton publication only. This does not "
            "authorize source changes, compilation, installation, Unreal, "
            "MCP, provider access, asset work, map work, or runtime claims."
        ),
    }


def _authenticate_execution_authorization(
    *,
    project_descriptor_hash: str,
    protected_inputs: Mapping[str, str],
) -> tuple[dict[str, Any], str]:
    payload = _read_stable_regular_file(
        EXECUTION_AUTH_PATH, max_bytes=1024 * 1024
    )
    value = load_json_bytes_strict(payload, str(EXECUTION_AUTH_PATH))
    if payload != _canonical_file_bytes(value):
        raise CandidateCreationError(
            "execution authorization is not canonical JSON plus one LF"
        )
    authorized_utc = _require_strict_utc(
        value.get("authorized_utc"), "execution authorization timestamp"
    )
    creator_path = Path(__file__)
    creator_hash = _stable_sha256(creator_path)
    creator_test_hash = _stable_sha256(CREATOR_TEST_PATH)
    expected = _execution_authorization_expected(
        authorized_utc=authorized_utc,
        creator_hash=creator_hash,
        creator_bytes=creator_path.stat().st_size,
        creator_test_hash=creator_test_hash,
        creator_test_bytes=CREATOR_TEST_PATH.stat().st_size,
        project_descriptor_hash=project_descriptor_hash,
        project_descriptor_bytes=PROJECT_DESCRIPTOR.stat().st_size,
        protected_inputs=protected_inputs,
    )
    if value != expected:
        raise CandidateCreationError("execution authorization content drift")
    return value, _sha256_bytes(payload)


def _authenticate_contract_postpublication() -> dict[str, Any]:
    payload = _read_stable_regular_file(CONTRACT_PATH, max_bytes=1024 * 1024)
    if _sha256_bytes(payload) != CONTRACT_SHA256:
        raise CandidateCreationError("immutable candidate contract hash drift")
    contract = load_json_bytes_strict(payload, str(CONTRACT_PATH))
    try:
        validate_contract_schema(contract)
    except CandidateContractError as exc:
        raise CandidateCreationError(str(exc)) from exc
    return contract


def _kernel32() -> Any:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.GetFileInformationByHandleEx.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    kernel32.GetFileInformationByHandleEx.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.MoveFileExW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_ulong,
    ]
    kernel32.MoveFileExW.restype = ctypes.c_int
    return kernel32


def _current_token_sid() -> str:
    completed = subprocess.run(
        [
            str(_POWERSHELL),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "[Security.Principal.WindowsIdentity]::"
                "GetCurrent().User.Value"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    sid = completed.stdout.strip()
    if completed.returncode != 0 or not re.fullmatch(
        r"S-[0-9]+(?:-[0-9]+)+", sid
    ):
        raise CandidateCreationError("cannot resolve current process token SID")
    return sid


def _apply_private_acl(path: Path, *, is_directory: bool) -> None:
    """Replace inherited access with the exact workflow allowlist."""

    current_sid = _current_token_sid()
    access = "(OI)(CI)F" if is_directory else "F"
    command = [
        str(_ICACLS),
        str(path),
        "/inheritance:r",
        "/grant:r",
        f"*{current_sid}:{access}",
        f"*S-1-5-18:{access}",
        f"*S-1-5-32-544:{access}",
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise CandidateCreationError(
            f"private ACL application failed for {path}: "
            f"{completed.stdout} {completed.stderr}".strip()
        )


def _apply_private_directory_acl(path: Path) -> None:
    _apply_private_acl(path, is_directory=True)


def _apply_private_file_acl(path: Path) -> None:
    _apply_private_acl(path, is_directory=False)


def _require_exact_private_acl(path: Path) -> None:
    path_base64 = base64.b64encode(str(path).encode("utf-8")).decode("ascii")
    script = r"""
$TargetPath = [Text.Encoding]::UTF8.GetString(
  [Convert]::FromBase64String('__TARGET_PATH_BASE64__')
)
$ErrorActionPreference = 'Stop'
$acl = Get-Acl -LiteralPath $TargetPath
$owner = ([Security.Principal.NTAccount]$acl.Owner).Translate(
  [Security.Principal.SecurityIdentifier]
).Value
$rules = @(
  $acl.GetAccessRules(
    $true,
    $true,
    [Security.Principal.SecurityIdentifier]
  ) | ForEach-Object {
    [pscustomobject]@{
      sid = $_.IdentityReference.Value
      rights = [int64]$_.FileSystemRights
      type = $_.AccessControlType.ToString()
      inherited = [bool]$_.IsInherited
    }
  }
)
[pscustomobject]@{
  owner = $owner
  protected = [bool]$acl.AreAccessRulesProtected
  rules = $rules
} | ConvertTo-Json -Depth 5 -Compress
""".replace("__TARGET_PATH_BASE64__", path_base64)
    encoded_script = base64.b64encode(
        script.encode("utf-16-le")
    ).decode("ascii")
    completed = subprocess.run(
        [
            str(_POWERSHELL),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded_script,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise CandidateCreationError(
            f"cannot inspect private ACL for {path}: {completed.stderr.strip()}"
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CandidateCreationError(
            f"private ACL report is invalid for {path}"
        ) from exc
    current_sid = _current_token_sid()
    allowed_sids = {current_sid, "S-1-5-18", "S-1-5-32-544"}
    if report.get("protected") is not True:
        raise CandidateCreationError(f"ACL inheritance is not protected: {path}")
    if report.get("owner") not in {current_sid, "S-1-5-32-544"}:
        raise CandidateCreationError(f"unexpected private-root owner: {path}")
    rules = report.get("rules")
    if type(rules) is not list or len(rules) != 3:
        raise CandidateCreationError(f"private ACL rule count drift: {path}")
    observed_sids: set[str] = set()
    for rule in rules:
        if type(rule) is not dict or set(rule) != {
            "sid",
            "rights",
            "type",
            "inherited",
        }:
            raise CandidateCreationError(f"private ACL rule shape drift: {path}")
        sid = rule["sid"]
        if sid not in allowed_sids or sid in observed_sids:
            raise CandidateCreationError(f"private ACL principal drift: {path}")
        observed_sids.add(sid)
        if rule["type"] != "Allow" or rule["rights"] != 2_032_127:
            raise CandidateCreationError(f"private ACL permission drift: {path}")
        if rule["inherited"] is not False:
            raise CandidateCreationError(f"private ACL inheritance drift: {path}")
    if observed_sids != allowed_sids:
        raise CandidateCreationError(f"private ACL allowlist incomplete: {path}")


def _windows_identity(path: Path, *, is_directory: bool) -> tuple[str, str]:
    kernel32 = _kernel32()
    flags = _FILE_FLAG_OPEN_REPARSE_POINT
    if is_directory:
        flags |= _FILE_FLAG_BACKUP_SEMANTICS
    handle = kernel32.CreateFileW(
        str(path),
        _GENERIC_READ,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
        None,
        _OPEN_EXISTING,
        flags,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE or handle is None:
        raise CandidateCreationError(
            f"cannot open identity handle for {path}: {ctypes.get_last_error()}"
        )
    try:
        info = _WindowsFileIdInformation()
        ok = kernel32.GetFileInformationByHandleEx(
            handle,
            _WINDOWS_FILE_ID_INFO,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            raise CandidateCreationError(
                f"cannot query full file identity for {path}: "
                f"{ctypes.get_last_error()}"
            )
        file_id = bytes(info.FileId.Identifier)
        if info.VolumeSerialNumber == 0 or not any(file_id):
            raise CandidateCreationError(f"invalid full file identity for {path}")
        return (
            f"{info.VolumeSerialNumber:016X}",
            file_id.hex().upper(),
        )
    finally:
        kernel32.CloseHandle(handle)


def _record_digest(files: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        f"{row['path']}\t{row['bytes']}\t{row['sha256']}\n"
        for row in sorted(files, key=lambda item: str(item["path"]))
    ]
    return _sha256_bytes("".join(lines).encode("utf-8"))


def _topology_digest(
    directories: Sequence[Mapping[str, Any]],
    files: Sequence[Mapping[str, Any]],
) -> str:
    rows: list[tuple[str, str]] = [
        (str(row["path"]), f"D\t{row['path']}\n") for row in directories
    ]
    rows.extend(
        (
            str(row["path"]),
            f"F\t{row['path']}\t{row['bytes']}\t{row['sha256']}\n",
        )
        for row in files
    )
    return _sha256_bytes(
        "".join(value for _, value in sorted(rows)).encode("utf-8")
    )


def _validate_relative_path(relative: str) -> str:
    if unicodedata.normalize("NFC", relative) != relative:
        raise CandidateCreationError(f"non-NFC relative path: {relative!r}")
    if not relative or "\\" in relative or relative.startswith("/"):
        raise CandidateCreationError(f"noncanonical relative path: {relative!r}")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise CandidateCreationError(f"unsafe relative path: {relative!r}")
    for part in parts:
        if any(ord(character) < 32 for character in part):
            raise CandidateCreationError(
                f"control character in relative path: {relative!r}"
            )
        if any(character in '<>:"|?*' for character in part):
            raise CandidateCreationError(
                f"unsafe Windows path character: {relative!r}"
            )
        if part.endswith((" ", ".")):
            raise CandidateCreationError(
                f"unsafe Windows path component: {relative!r}"
            )
        if part.split(".", 1)[0].upper() in _RESERVED_WINDOWS_NAMES:
            raise CandidateCreationError(
                f"reserved Windows path component: {relative!r}"
            )
    return relative


def _scan_exact_tree(root: Path) -> TreeSnapshot:
    if not root.is_absolute():
        raise CandidateCreationError("tree root must be absolute")
    _validate_existing_ancestor_chain(root)
    root_info = root.stat(follow_symlinks=False)
    if root.is_symlink() or _is_reparse(root_info) or not stat.S_ISDIR(
        root_info.st_mode
    ):
        raise CandidateCreationError(f"tree root is not a plain directory: {root}")
    if _named_alternate_streams(root):
        raise CandidateCreationError(f"tree root has named streams: {root}")

    root_identity = _windows_identity(root, is_directory=True)
    stack: list[Path] = [root]
    directories: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    casefolded: set[str] = set()

    while stack:
        directory = stack.pop()
        before = directory.stat(follow_symlinks=False)
        if directory.is_symlink() or _is_reparse(before) or not stat.S_ISDIR(
            before.st_mode
        ):
            raise CandidateCreationError(f"tree directory changed: {directory}")
        before_identity = _windows_identity(directory, is_directory=True)
        if _named_alternate_streams(directory):
            raise CandidateCreationError(
                f"directory has named streams: {directory}"
            )
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda item: item.name)
        after = directory.stat(follow_symlinks=False)
        after_identity = _windows_identity(directory, is_directory=True)
        if (
            directory.is_symlink()
            or _is_reparse(after)
            or not stat.S_ISDIR(after.st_mode)
            or before_identity != after_identity
            or _named_alternate_streams(directory)
        ):
            raise CandidateCreationError(
                f"directory changed during enumeration: {directory}"
            )
        for entry in entries:
            path = Path(entry.path)
            observed = path.stat(follow_symlinks=False)
            if entry.is_symlink() or _is_reparse(observed):
                raise CandidateCreationError(f"link or reparse entry refused: {path}")
            relative = _validate_relative_path(path.relative_to(root).as_posix())
            folded = relative.casefold()
            if folded in casefolded:
                raise CandidateCreationError(
                    f"case-fold path collision in tree: {relative}"
                )
            casefolded.add(folded)
            if stat.S_ISDIR(observed.st_mode):
                volume, file_id = _windows_identity(path, is_directory=True)
                if _named_alternate_streams(path):
                    raise CandidateCreationError(
                        f"directory has named streams: {path}"
                    )
                directories.append(
                    {
                        "path": relative,
                        "attributes_hex": f"{observed.st_file_attributes:08X}",
                        "volume_serial_hex": volume,
                        "file_id_128_hex": file_id,
                        "alternate_streams": [],
                    }
                )
                stack.append(path)
                continue
            if not stat.S_ISREG(observed.st_mode):
                raise CandidateCreationError(f"non-regular tree entry: {path}")
            file_bytes, file_hash = _hash_stable_regular_file(path)
            final = path.stat(follow_symlinks=False)
            if getattr(final, "st_nlink", 1) != 1:
                raise CandidateCreationError(f"hardlinked file refused: {path}")
            volume, file_id = _windows_identity(path, is_directory=False)
            files.append(
                {
                    "path": relative,
                    "bytes": file_bytes,
                    "sha256": file_hash,
                    "attributes_hex": f"{final.st_file_attributes:08X}",
                    "volume_serial_hex": volume,
                    "file_id_128_hex": file_id,
                    "hard_link_count": int(getattr(final, "st_nlink", 1)),
                    "alternate_streams": [],
                }
            )

    directories.sort(key=lambda row: str(row["path"]))
    files.sort(key=lambda row: str(row["path"]))
    if _windows_identity(root, is_directory=True) != root_identity:
        raise CandidateCreationError("tree root identity changed during scan")
    if _named_alternate_streams(root):
        raise CandidateCreationError("tree root gained a named stream")
    snapshot = TreeSnapshot(
        root=_path_text(root),
        directories=tuple(directories),
        files=tuple(files),
        file_count=len(files),
        directory_count_excluding_root=len(directories),
        total_bytes=sum(int(row["bytes"]) for row in files),
        record_set_sha256=_record_digest(files),
        topology_sha256=_topology_digest(directories, files),
    )
    return snapshot


def _scan_two_pass(root: Path) -> TreeSnapshot:
    first = _scan_exact_tree(root)
    second = _scan_exact_tree(root)
    if first != second:
        raise CandidateCreationError(
            f"tree changed between complete observations: {root}"
        )
    return second


def _require_expected_fork_snapshot(snapshot: TreeSnapshot) -> None:
    if snapshot.file_count != EXPECTED_FILE_COUNT:
        raise CandidateCreationError("fork file count drift")
    if snapshot.directory_count_excluding_root != EXPECTED_DIRECTORY_COUNT:
        raise CandidateCreationError("fork directory count drift")
    if snapshot.total_bytes != EXPECTED_TOTAL_BYTES:
        raise CandidateCreationError("fork byte count drift")
    if snapshot.record_set_sha256 != EXPECTED_RECORD_SET_SHA256:
        raise CandidateCreationError("fork record digest drift")
    if snapshot.topology_sha256 != EXPECTED_TOPOLOGY_SHA256:
        raise CandidateCreationError("fork topology digest drift")
    actual_directories = tuple(str(row["path"]) for row in snapshot.directories)
    if actual_directories != EXPECTED_DIRECTORIES:
        raise CandidateCreationError("fork directory allowlist drift")
    paths = {str(row["path"]) for row in snapshot.files}
    if "NwiroIntegrationKit.uplugin" not in paths:
        raise CandidateCreationError("fork descriptor is absent")
    if any(
        path == root or path.startswith(root + "/")
        for path in paths
        for root in FORBIDDEN_CANDIDATE_ROOTS
    ):
        raise CandidateCreationError("forbidden generated/vendor root in fork")
    if any(
        not (
            path == "NwiroIntegrationKit.uplugin"
            or path.startswith("Resources/")
            or path.startswith("Source/")
        )
        for path in paths
    ):
        raise CandidateCreationError("unexpected fork-input file")


def _without_identity(snapshot: TreeSnapshot) -> dict[str, Any]:
    return {
        "directories": [str(row["path"]) for row in snapshot.directories],
        "files": [
            {
                "path": str(row["path"]),
                "bytes": int(row["bytes"]),
                "sha256": str(row["sha256"]),
            }
            for row in snapshot.files
        ],
        "file_count": snapshot.file_count,
        "directory_count_excluding_root": snapshot.directory_count_excluding_root,
        "total_bytes": snapshot.total_bytes,
        "record_set_sha256": snapshot.record_set_sha256,
        "topology_sha256": snapshot.topology_sha256,
    }


def _require_byte_exact_copy(
    baseline: TreeSnapshot, candidate: TreeSnapshot
) -> None:
    if _without_identity(baseline) != _without_identity(candidate):
        raise CandidateCreationError("candidate is not a byte-exact fork-input copy")


def _stable_sha256(path: Path) -> str:
    _, digest = _hash_stable_regular_file(path)
    return digest


def _authenticate_protected_inputs() -> dict[str, str]:
    observed: dict[str, str] = {}
    for path, expected in PROTECTED_INPUTS.items():
        digest = _stable_sha256(path)
        if digest != expected:
            raise CandidateCreationError(f"protected input drift: {path}")
        observed[_path_text(path)] = digest
    return observed


def _write_exclusive(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    observed = _read_stable_regular_file(path, max_bytes=max(len(payload), 1))
    if observed != payload:
        raise CandidateCreationError(f"written bytes failed readback: {path}")


def _copy_exact_tree(
    source_root: Path,
    destination_root: Path,
    baseline: TreeSnapshot,
) -> None:
    destination_root.mkdir()
    _apply_private_directory_acl(destination_root)
    _require_exact_private_acl(destination_root)
    for directory in baseline.directories:
        relative = Path(str(directory["path"]))
        (destination_root / relative).mkdir()
    source_by_path = {str(row["path"]): row for row in baseline.files}
    for relative in sorted(source_by_path):
        expected = source_by_path[relative]
        source = source_root / Path(relative)
        destination = destination_root / Path(relative)
        payload = _read_stable_regular_file(
            source, max_bytes=max(int(expected["bytes"]), 1)
        )
        if len(payload) != int(expected["bytes"]):
            raise CandidateCreationError(f"source size drift while copying: {relative}")
        if _sha256_bytes(payload) != str(expected["sha256"]):
            raise CandidateCreationError(f"source hash drift while copying: {relative}")
        _write_exclusive(destination, payload)


def _manifest_semantic_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if key not in {"captured_utc", "manifest_semantic_sha256"}
    }


def _attach_manifest_semantic_hash(value: dict[str, Any]) -> dict[str, Any]:
    value["manifest_semantic_sha256"] = _sha256_bytes(
        canonical_json_bytes(_manifest_semantic_payload(value))
    )
    return value


def _expected_manifest_claim_limit(role: str) -> str:
    if role == "candidate_source":
        return (
            "Exact offline candidate source-tree inventory only. The "
            "candidate is inert only because it is external, unbuilt, "
            "uninstalled, and outside the two configured automatic plugin "
            "roots checked by this workflow. Explicit additional plugin paths "
            "remain outside this claim."
        )
    if role == "baseline_fork_input":
        return (
            "Exact offline vendor fork-input inventory only. The installed "
            "vendor plugin and binary are outside this manifest's authority."
        )
    raise CandidateCreationError(f"unknown manifest role: {role}")


def _manifest_object(
    *,
    manifest_id: str,
    role: str,
    captured_utc: str,
    snapshot: TreeSnapshot,
    contract_hash: str,
    execution_authorization_hash: str,
    project_descriptor_hash: str,
    creator_hash: str,
    baseline_manifest_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    semantic = snapshot.semantic_payload()
    result: dict[str, Any] = {
        "schema_version": 1,
        "manifest_id": manifest_id,
        "role": role,
        "evidence_class": "static",
        "captured_utc": captured_utc,
        "contract": {
            "path": _path_text(CONTRACT_PATH),
            "sha256": contract_hash,
        },
        "execution_authorization": {
            "path": _path_text(EXECUTION_AUTH_PATH),
            "sha256": execution_authorization_hash,
        },
        "creator": {
            "path": _path_text(Path(__file__)),
            "sha256": creator_hash,
        },
        "project_descriptor": {
            "path": _path_text(PROJECT_DESCRIPTOR),
            "sha256": project_descriptor_hash,
            "changed": False,
        },
        "tree": semantic,
        "tree_semantic_sha256": _sha256_bytes(canonical_json_bytes(semantic)),
        "runtime_authorized": False,
        "build_authorized": False,
        "install_authorized": False,
        "unreal_launch_authorized": False,
        "mcp_initialize_authorized": False,
        "mcp_tool_call_authorized": False,
        "network_authorized": False,
        "provider_call_authorized": False,
        "candidate_static_accepted": False,
        "source_default_off": False,
        "restricted_mode_implemented": False,
        "inert_only_by_external_location_and_no_binary": (
            role == "candidate_source"
        ),
        "outside_two_checked_automatic_plugin_roots": (
            role == "candidate_source"
        ),
        "universal_plugin_discovery_exclusion_proven": False,
        "atomic_whole_tree_snapshot_proven": False,
        "concurrent_writer_resistance_proven": False,
        "power_loss_durability_proven": False,
        "acl_owner_timestamp_equality_claimed": False,
        "claim_limit": _expected_manifest_claim_limit(role),
    }
    if baseline_manifest_binding is not None:
        result["baseline_manifest"] = dict(baseline_manifest_binding)
    return _attach_manifest_semantic_hash(result)


def _build_exact_delta(
    *,
    captured_utc: str,
    baseline: TreeSnapshot,
    candidate: TreeSnapshot,
    baseline_manifest_sha256: str,
    candidate_manifest_sha256: str,
    baseline_manifest_semantic_sha256: str,
    candidate_manifest_semantic_sha256: str,
    baseline_manifest_bytes: int,
    candidate_manifest_bytes: int,
    execution_authorization_hash: str,
) -> dict[str, Any]:
    _require_byte_exact_copy(baseline, candidate)
    baseline_rows = {str(row["path"]): row for row in baseline.files}
    candidate_rows = {str(row["path"]): row for row in candidate.files}
    baseline_directories = {
        str(row["path"]) for row in baseline.directories
    }
    candidate_directories = {
        str(row["path"]) for row in candidate.directories
    }
    copied_exact = [
        {
            "path": path,
            "bytes": int(baseline_rows[path]["bytes"]),
            "sha256": str(baseline_rows[path]["sha256"]),
        }
        for path in sorted(baseline_rows)
    ]
    unchanged_directories = [
        {"path": path} for path in sorted(baseline_directories)
    ]
    coverage = {
        "baseline_entries": sorted(
            [f"D:{path}" for path in baseline_directories]
            + [f"F:{path}" for path in baseline_rows]
        ),
        "candidate_entries": sorted(
            [f"D:{path}" for path in candidate_directories]
            + [f"F:{path}" for path in candidate_rows]
        ),
        "classification_rows": [
            {
                "classification": "unchanged",
                "kind": "directory",
                "path": row["path"],
            }
            for row in unchanged_directories
        ]
        + [
            {
                "classification": "copied_exact",
                "kind": "file",
                "path": row["path"],
            }
            for row in copied_exact
        ],
    }
    result = {
        "schema_version": 1,
        "manifest_id": "nwiro-restricted-probe-complete-delta-v1",
        "role": "complete_delta",
        "evidence_class": "static",
        "captured_utc": captured_utc,
        "execution_authorization": {
            "path": _path_text(EXECUTION_AUTH_PATH),
            "sha256": execution_authorization_hash,
        },
        "baseline_manifest": {
            "path": _path_text(BASELINE_MANIFEST_PATH),
            "bytes": baseline_manifest_bytes,
            "raw_sha256": baseline_manifest_sha256,
            "semantic_sha256": baseline_manifest_semantic_sha256,
        },
        "candidate_manifest": {
            "path": _path_text(CANDIDATE_MANIFEST_PATH),
            "bytes": candidate_manifest_bytes,
            "raw_sha256": candidate_manifest_sha256,
            "semantic_sha256": candidate_manifest_semantic_sha256,
        },
        "baseline_record_set_sha256": baseline.record_set_sha256,
        "candidate_record_set_sha256": candidate.record_set_sha256,
        "unchanged_directories": unchanged_directories,
        "copied_exact": copied_exact,
        "modified": [],
        "renamed": [],
        "added": [],
        "omitted": [],
        "classification_counts": {
            "unchanged_directories": len(unchanged_directories),
            "copied_exact": len(copied_exact),
            "modified": 0,
            "renamed": 0,
            "added": 0,
            "omitted": 0,
        },
        "complete_path_coverage_sha256": _sha256_bytes(
            canonical_json_bytes(coverage)
        ),
        "every_baseline_entry_classified_exactly_once": True,
        "every_candidate_entry_classified_exactly_once": True,
        "candidate_is_byte_exact_copy": True,
        "exact_copy_scope": "unnamed_stream_bytes_and_file_directory_topology_only",
        "descriptor_changed": False,
        "source_changed": False,
        "resources_changed": False,
        "vendor_binaries_present": False,
        "vendor_intermediate_present": False,
        "runtime_authorized": False,
        "build_authorized": False,
        "install_authorized": False,
        "unreal_launch_authorized": False,
        "mcp_initialize_authorized": False,
        "mcp_tool_call_authorized": False,
        "network_authorized": False,
        "provider_call_authorized": False,
        "candidate_static_accepted": False,
        "source_default_off": False,
        "restricted_mode_implemented": False,
        "inert_only_by_external_location_and_no_binary": True,
        "outside_two_checked_automatic_plugin_roots": True,
        "universal_plugin_discovery_exclusion_proven": False,
        "atomic_multi_object_publication_proven": False,
        "power_loss_durability_proven": False,
        "claim_limit": (
            "Complete exact-copy lineage only. No allowlisted source mutation "
            "has been implemented or accepted."
        ),
    }
    return _attach_manifest_semantic_hash(result)


def _move_no_clobber(source: Path, destination: Path) -> None:
    if _lexists(destination):
        raise CandidateCreationError(f"publication target already exists: {destination}")
    kernel32 = _kernel32()
    ok = kernel32.MoveFileExW(
        str(source),
        str(destination),
        _MOVEFILE_WRITE_THROUGH,
    )
    if not ok:
        raise CandidateCreationError(
            f"no-clobber publication failed {source} -> {destination}: "
            f"{ctypes.get_last_error()}"
        )


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    payload = _read_stable_regular_file(path, max_bytes=16 * 1024 * 1024)
    value = load_json_bytes_strict(payload, str(path))
    if payload != _canonical_file_bytes(value):
        raise CandidateCreationError(f"manifest is not canonical JSON plus LF: {path}")
    return value, _sha256_bytes(payload)


def _validate_manifest_shape(
    value: Mapping[str, Any],
    *,
    manifest_id: str,
    role: str,
    root: Path,
    snapshot: TreeSnapshot,
    project_descriptor_hash: str,
    execution_authorization_hash: str,
) -> None:
    expected_keys = {
        "schema_version",
        "manifest_id",
        "role",
        "evidence_class",
        "captured_utc",
        "contract",
        "execution_authorization",
        "creator",
        "project_descriptor",
        "tree",
        "tree_semantic_sha256",
        "runtime_authorized",
        "build_authorized",
        "install_authorized",
        "unreal_launch_authorized",
        "mcp_initialize_authorized",
        "mcp_tool_call_authorized",
        "network_authorized",
        "provider_call_authorized",
        "candidate_static_accepted",
        "source_default_off",
        "restricted_mode_implemented",
        "inert_only_by_external_location_and_no_binary",
        "outside_two_checked_automatic_plugin_roots",
        "universal_plugin_discovery_exclusion_proven",
        "atomic_whole_tree_snapshot_proven",
        "concurrent_writer_resistance_proven",
        "power_loss_durability_proven",
        "acl_owner_timestamp_equality_claimed",
        "claim_limit",
        "manifest_semantic_sha256",
    }
    if role == "candidate_source":
        expected_keys.add("baseline_manifest")
    if set(value) != expected_keys:
        raise CandidateCreationError("manifest key set drift")
    if value.get("schema_version") != 1:
        raise CandidateCreationError("manifest schema drift")
    if value.get("manifest_id") != manifest_id or value.get("role") != role:
        raise CandidateCreationError("manifest identity drift")
    if value.get("evidence_class") != "static":
        raise CandidateCreationError("manifest evidence class drift")
    captured_utc = value.get("captured_utc")
    if type(captured_utc) is not str or not _RFC3339_UTC.fullmatch(captured_utc):
        raise CandidateCreationError("manifest timestamp is not strict UTC RFC3339")
    try:
        datetime.fromisoformat(captured_utc[:-1] + "+00:00")
    except ValueError as exc:
        raise CandidateCreationError("manifest timestamp is invalid") from exc
    if value.get("contract") != {
        "path": _path_text(CONTRACT_PATH),
        "sha256": CONTRACT_SHA256,
    }:
        raise CandidateCreationError("manifest contract binding drift")
    if value.get("execution_authorization") != {
        "path": _path_text(EXECUTION_AUTH_PATH),
        "sha256": execution_authorization_hash,
    }:
        raise CandidateCreationError(
            "manifest execution authorization binding drift"
        )
    if value.get("project_descriptor") != {
        "path": _path_text(PROJECT_DESCRIPTOR),
        "sha256": project_descriptor_hash,
        "changed": False,
    }:
        raise CandidateCreationError("manifest project descriptor binding drift")
    if value.get("claim_limit") != _expected_manifest_claim_limit(role):
        raise CandidateCreationError("manifest claim limit drift")
    if value.get("tree") != snapshot.semantic_payload():
        raise CandidateCreationError("manifest tree payload drift")
    semantic_hash = _sha256_bytes(canonical_json_bytes(snapshot.semantic_payload()))
    if value.get("tree_semantic_sha256") != semantic_hash:
        raise CandidateCreationError("manifest semantic hash drift")
    if value.get("tree", {}).get("root") != _path_text(root):
        raise CandidateCreationError("manifest root drift")
    manifest_semantic = _sha256_bytes(
        canonical_json_bytes(_manifest_semantic_payload(value))
    )
    if value.get("manifest_semantic_sha256") != manifest_semantic:
        raise CandidateCreationError("whole-manifest semantic hash drift")
    for key in (
        "runtime_authorized",
        "build_authorized",
        "install_authorized",
        "unreal_launch_authorized",
        "mcp_initialize_authorized",
        "mcp_tool_call_authorized",
        "network_authorized",
        "provider_call_authorized",
        "candidate_static_accepted",
    ):
        if value.get(key) is not False:
            raise CandidateCreationError(f"manifest authority drift: {key}")
    for key in (
        "source_default_off",
        "restricted_mode_implemented",
        "atomic_whole_tree_snapshot_proven",
        "concurrent_writer_resistance_proven",
        "power_loss_durability_proven",
        "acl_owner_timestamp_equality_claimed",
    ):
        if value.get(key) is not False:
            raise CandidateCreationError(f"manifest claim drift: {key}")
    expected_inert = role == "candidate_source"
    if (
        value.get("inert_only_by_external_location_and_no_binary")
        is not expected_inert
    ):
        raise CandidateCreationError("manifest inert-state claim drift")
    if value.get("outside_two_checked_automatic_plugin_roots") is not expected_inert:
        raise CandidateCreationError("manifest automatic-root claim drift")
    if value.get("universal_plugin_discovery_exclusion_proven") is not False:
        raise CandidateCreationError("manifest universal discovery claim drift")


def _verify_delta(
    value: Mapping[str, Any],
    *,
    baseline: TreeSnapshot,
    candidate: TreeSnapshot,
    baseline_hash: str,
    candidate_hash: str,
    baseline_semantic_hash: str,
    candidate_semantic_hash: str,
    baseline_bytes: int,
    candidate_bytes: int,
    execution_authorization_hash: str,
) -> None:
    expected = _build_exact_delta(
        captured_utc=str(value.get("captured_utc")),
        baseline=baseline,
        candidate=candidate,
        baseline_manifest_sha256=baseline_hash,
        candidate_manifest_sha256=candidate_hash,
        baseline_manifest_semantic_sha256=baseline_semantic_hash,
        candidate_manifest_semantic_sha256=candidate_semantic_hash,
        baseline_manifest_bytes=baseline_bytes,
        candidate_manifest_bytes=candidate_bytes,
        execution_authorization_hash=execution_authorization_hash,
    )
    if dict(value) != expected:
        raise CandidateCreationError("delta manifest drift")


def _verify_bundle(
    *,
    source_snapshot: TreeSnapshot,
    candidate_snapshot: TreeSnapshot,
    project_descriptor_hash: str,
    execution_authorization_hash: str,
) -> dict[str, Any]:
    baseline, baseline_hash = _load_manifest(BASELINE_MANIFEST_PATH)
    candidate, candidate_hash = _load_manifest(CANDIDATE_MANIFEST_PATH)
    delta, delta_hash = _load_manifest(DELTA_MANIFEST_PATH)
    timestamps = (
        _require_strict_utc(
            baseline.get("captured_utc"), "baseline manifest timestamp"
        ),
        _require_strict_utc(
            candidate.get("captured_utc"), "candidate manifest timestamp"
        ),
        _require_strict_utc(
            delta.get("captured_utc"), "delta manifest timestamp"
        ),
    )
    if len(set(timestamps)) != 1:
        raise CandidateCreationError("cross-manifest timestamp drift")
    _validate_manifest_shape(
        baseline,
        manifest_id="nwiro-restricted-probe-baseline-fork-input-v1",
        role="baseline_fork_input",
        root=SOURCE_ROOT,
        snapshot=source_snapshot,
        project_descriptor_hash=project_descriptor_hash,
        execution_authorization_hash=execution_authorization_hash,
    )
    _validate_manifest_shape(
        candidate,
        manifest_id="nwiro-restricted-probe-candidate-source-v1",
        role="candidate_source",
        root=CANDIDATE_ROOT,
        snapshot=candidate_snapshot,
        project_descriptor_hash=project_descriptor_hash,
        execution_authorization_hash=execution_authorization_hash,
    )
    if (
        baseline.get("project_descriptor", {}).get("sha256")
        != project_descriptor_hash
        or candidate.get("project_descriptor", {}).get("sha256")
        != project_descriptor_hash
    ):
        raise CandidateCreationError("project descriptor binding drift")
    creator_hash = _stable_sha256(Path(__file__))
    expected_creator = {"path": _path_text(Path(__file__)), "sha256": creator_hash}
    if baseline.get("creator") != expected_creator:
        raise CandidateCreationError("baseline creator binding drift")
    if candidate.get("creator") != expected_creator:
        raise CandidateCreationError("candidate creator binding drift")
    expected_baseline_binding = {
        "path": _path_text(BASELINE_MANIFEST_PATH),
        "bytes": BASELINE_MANIFEST_PATH.stat().st_size,
        "raw_sha256": baseline_hash,
        "semantic_sha256": baseline["manifest_semantic_sha256"],
    }
    if candidate.get("baseline_manifest") != expected_baseline_binding:
        raise CandidateCreationError("candidate baseline binding drift")
    _verify_delta(
        delta,
        baseline=source_snapshot,
        candidate=candidate_snapshot,
        baseline_hash=baseline_hash,
        candidate_hash=candidate_hash,
        baseline_semantic_hash=str(baseline["manifest_semantic_sha256"]),
        candidate_semantic_hash=str(candidate["manifest_semantic_sha256"]),
        baseline_bytes=BASELINE_MANIFEST_PATH.stat().st_size,
        candidate_bytes=CANDIDATE_MANIFEST_PATH.stat().st_size,
        execution_authorization_hash=execution_authorization_hash,
    )
    return {
        "baseline_manifest_sha256": baseline_hash,
        "baseline_manifest_semantic_sha256": baseline[
            "manifest_semantic_sha256"
        ],
        "candidate_manifest_sha256": candidate_hash,
        "candidate_manifest_semantic_sha256": candidate[
            "manifest_semantic_sha256"
        ],
        "delta_manifest_sha256": delta_hash,
        "delta_manifest_semantic_sha256": delta[
            "manifest_semantic_sha256"
        ],
    }


def _preflight_contract() -> dict[str, Any]:
    contract_hash = _stable_sha256(CONTRACT_PATH)
    if contract_hash != CONTRACT_SHA256:
        raise CandidateCreationError("immutable candidate contract hash drift")
    try:
        return validate_contract_file(CONTRACT_PATH)
    except CandidateContractError as exc:
        raise CandidateCreationError(str(exc)) from exc


def _fork_snapshot_from_full(snapshot: TreeSnapshot, root: Path) -> TreeSnapshot:
    directories = tuple(
        row
        for row in snapshot.directories
        if str(row["path"]) == "Resources"
        or str(row["path"]).startswith("Resources/")
        or str(row["path"]) == "Source"
        or str(row["path"]).startswith("Source/")
    )
    files = tuple(
        row
        for row in snapshot.files
        if str(row["path"]) == "NwiroIntegrationKit.uplugin"
        or str(row["path"]).startswith("Resources/")
        or str(row["path"]).startswith("Source/")
    )
    return TreeSnapshot(
        root=_path_text(root),
        directories=directories,
        files=files,
        file_count=len(files),
        directory_count_excluding_root=len(directories),
        total_bytes=sum(int(row["bytes"]) for row in files),
        record_set_sha256=_record_digest(files),
        topology_sha256=_topology_digest(directories, files),
    )


def _ensure_private_staging_parent(
    *, create_if_absent: bool
) -> tuple[str, str]:
    created = False
    if not _lexists(STAGING_PARENT):
        if not create_if_absent:
            raise CandidateCreationError("staging parent is absent")
        STAGING_PARENT.mkdir()
        created = True
    _validate_existing_ancestor_chain(STAGING_PARENT)
    parent_info = STAGING_PARENT.stat(follow_symlinks=False)
    if STAGING_PARENT.is_symlink() or _is_reparse(parent_info) or not stat.S_ISDIR(
        parent_info.st_mode
    ):
        raise CandidateCreationError("staging parent is not a plain directory")
    if _named_alternate_streams(STAGING_PARENT):
        raise CandidateCreationError("staging parent has named streams")
    if created:
        _apply_private_directory_acl(STAGING_PARENT)
    _require_exact_private_acl(STAGING_PARENT)
    return _windows_identity(STAGING_PARENT, is_directory=True)


def _create_quarantine_reservation(
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Create the one exact private rollback target before staging any bytes."""

    if not ROLLBACK_PARENT.is_dir():
        raise CandidateCreationError("rollback parent is absent")
    _validate_existing_ancestor_chain(ROLLBACK_PARENT)
    rollback_info = ROLLBACK_PARENT.stat(follow_symlinks=False)
    if (
        ROLLBACK_PARENT.is_symlink()
        or _is_reparse(rollback_info)
        or not stat.S_ISDIR(rollback_info.st_mode)
    ):
        raise CandidateCreationError("rollback parent is not a plain directory")
    if _named_alternate_streams(ROLLBACK_PARENT):
        raise CandidateCreationError("rollback parent has named streams")
    rollback_identity = _windows_identity(
        ROLLBACK_PARENT, is_directory=True
    )
    if _lexists(QUARANTINE_ROOT):
        raise CandidateCreationError(
            "fixed rollback reservation already exists; review it before retry"
        )
    QUARANTINE_ROOT.mkdir()
    _apply_private_directory_acl(QUARANTINE_ROOT)
    _require_exact_private_acl(QUARANTINE_ROOT)
    quarantine_identity = _windows_identity(
        QUARANTINE_ROOT, is_directory=True
    )
    if _windows_identity(
        ROLLBACK_PARENT, is_directory=True
    ) != rollback_identity:
        raise CandidateCreationError("rollback parent identity changed")
    return rollback_identity, quarantine_identity


def _release_empty_quarantine_reservation(
    *,
    rollback_parent_identity: tuple[str, str],
    quarantine_identity: tuple[str, str],
) -> None:
    if _windows_identity(
        ROLLBACK_PARENT, is_directory=True
    ) != rollback_parent_identity:
        raise CandidateCreationError("rollback parent identity changed")
    if _windows_identity(
        QUARANTINE_ROOT, is_directory=True
    ) != quarantine_identity:
        raise CandidateCreationError("rollback reservation identity changed")
    _require_exact_private_acl(QUARANTINE_ROOT)
    with os.scandir(QUARANTINE_ROOT) as iterator:
        if next(iterator, None) is not None:
            raise CandidateCreationError(
                "rollback reservation is unexpectedly nonempty"
            )
    QUARANTINE_ROOT.rmdir()


def _quarantine_failed_publication(
    *,
    transaction_root: Path,
    transaction_identity: tuple[str, str] | None,
    nonce: str,
    published: Sequence[tuple[Path, tuple[str, str], bool]],
    rollback_parent_identity: tuple[str, str],
    quarantine_identity: tuple[str, str],
) -> Path:
    """Move only retained current-run identities to a private rollback folder."""

    if _windows_identity(
        ROLLBACK_PARENT, is_directory=True
    ) != rollback_parent_identity:
        raise CandidateCreationError("rollback parent identity changed")
    if _windows_identity(
        QUARANTINE_ROOT, is_directory=True
    ) != quarantine_identity:
        raise CandidateCreationError("rollback reservation identity changed")
    _require_exact_private_acl(QUARANTINE_ROOT)
    with os.scandir(QUARANTINE_ROOT) as iterator:
        if next(iterator, None) is not None:
            raise CandidateCreationError(
                "rollback reservation was not empty before quarantine"
            )

    for final_path, expected_identity, is_directory in published:
        if not _lexists(final_path):
            raise CandidateCreationError(
                f"published current-run path disappeared before quarantine: "
                f"{final_path}"
            )
        if _windows_identity(
            final_path, is_directory=is_directory
        ) != expected_identity:
            raise CandidateCreationError(
                f"published identity drift; left in place for review: {final_path}"
            )
    for final_path, _, _ in published:
        _move_no_clobber(final_path, QUARANTINE_ROOT / final_path.name)
    if _lexists(transaction_root):
        expected_name = f".NwiroRestrictedProbeForkCandidateV1.txn.{nonce}"
        if (
            transaction_root.parent != STAGING_PARENT
            or transaction_root.name != expected_name
        ):
            raise CandidateCreationError(
                "refusing to quarantine unexpected transaction root"
            )
        if transaction_identity is None:
            raise CandidateCreationError(
                "transaction identity was never authenticated; left for review"
            )
        if _windows_identity(
            transaction_root, is_directory=True
        ) != transaction_identity:
            raise CandidateCreationError(
                "transaction identity drift; left for review"
            )
        _move_no_clobber(
            transaction_root, QUARANTINE_ROOT / "transaction_remainder"
        )
    return QUARANTINE_ROOT


def create_candidate() -> dict[str, Any]:
    _require_fixed_layout()
    final_paths = (
        CANDIDATE_ROOT,
        BASELINE_MANIFEST_PATH,
        CANDIDATE_MANIFEST_PATH,
        DELTA_MANIFEST_PATH,
    )
    if any(_lexists(path) for path in final_paths):
        raise CandidateCreationError(
            "a final candidate or manifest name already exists; use --verify"
        )
    contract = _preflight_contract()
    if contract.get("runtime_authorized") is not False:
        raise CandidateCreationError("parent validator returned runtime authority")
    project_descriptor_hash = _stable_sha256(PROJECT_DESCRIPTOR)
    protected_before = _authenticate_protected_inputs()
    _, execution_authorization_hash = (
        _authenticate_execution_authorization(
            project_descriptor_hash=project_descriptor_hash,
            protected_inputs=protected_before,
        )
    )
    baseline_aggregate = authenticate_plugin_tree_two_pass(SOURCE_ROOT)
    expected_aggregate = baseline_aggregate["fork_input_tree"]
    for key, expected in (
        ("file_count", EXPECTED_FILE_COUNT),
        ("directory_count_excluding_root", EXPECTED_DIRECTORY_COUNT),
        ("total_bytes", EXPECTED_TOTAL_BYTES),
        ("record_set_sha256", EXPECTED_RECORD_SET_SHA256),
        ("topology_sha256", EXPECTED_TOPOLOGY_SHA256),
    ):
        if expected_aggregate.get(key) != expected:
            raise CandidateCreationError(f"parent fork aggregate drift: {key}")

    fork_snapshot = _fork_snapshot_from_full(
        _scan_two_pass(SOURCE_ROOT), SOURCE_ROOT
    )
    _require_expected_fork_snapshot(fork_snapshot)

    staging_identity = _ensure_private_staging_parent(create_if_absent=True)
    _require_reserved_namespace(set())
    rollback_parent_identity, quarantine_identity = (
        _create_quarantine_reservation()
    )
    nonce = secrets.token_hex(16)
    transaction_root = STAGING_PARENT / (
        f".NwiroRestrictedProbeForkCandidateV1.txn.{nonce}"
    )
    candidate_temp = transaction_root / "Candidate"
    baseline_temp = transaction_root / BASELINE_MANIFEST_PATH.name
    candidate_manifest_temp = transaction_root / CANDIDATE_MANIFEST_PATH.name
    delta_temp = transaction_root / DELTA_MANIFEST_PATH.name
    published: list[tuple[Path, tuple[str, str], bool]] = []
    transaction_identity: tuple[str, str] | None = None
    try:
        transaction_root.mkdir()
        _apply_private_directory_acl(transaction_root)
        _require_exact_private_acl(transaction_root)
        _require_reserved_namespace({transaction_root.name})
        transaction_identity = _windows_identity(
            transaction_root, is_directory=True
        )
        _copy_exact_tree(SOURCE_ROOT, candidate_temp, fork_snapshot)
        candidate_snapshot = _scan_two_pass(candidate_temp)
        candidate_snapshot = TreeSnapshot(
            root=_path_text(CANDIDATE_ROOT),
            directories=candidate_snapshot.directories,
            files=candidate_snapshot.files,
            file_count=candidate_snapshot.file_count,
            directory_count_excluding_root=(
                candidate_snapshot.directory_count_excluding_root
            ),
            total_bytes=candidate_snapshot.total_bytes,
            record_set_sha256=candidate_snapshot.record_set_sha256,
            topology_sha256=candidate_snapshot.topology_sha256,
        )
        _require_expected_fork_snapshot(candidate_snapshot)
        _require_byte_exact_copy(fork_snapshot, candidate_snapshot)

        source_after_fork = _fork_snapshot_from_full(
            _scan_two_pass(SOURCE_ROOT), SOURCE_ROOT
        )
        if fork_snapshot != source_after_fork:
            raise CandidateCreationError("source fork input changed during copy")

        captured_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        creator_hash = _stable_sha256(Path(__file__))
        baseline_manifest = _manifest_object(
            manifest_id="nwiro-restricted-probe-baseline-fork-input-v1",
            role="baseline_fork_input",
            captured_utc=captured_utc,
            snapshot=fork_snapshot,
            contract_hash=CONTRACT_SHA256,
            execution_authorization_hash=execution_authorization_hash,
            project_descriptor_hash=project_descriptor_hash,
            creator_hash=creator_hash,
        )
        baseline_payload = _canonical_file_bytes(baseline_manifest)
        baseline_binding = {
            "path": _path_text(BASELINE_MANIFEST_PATH),
            "bytes": len(baseline_payload),
            "raw_sha256": _sha256_bytes(baseline_payload),
            "semantic_sha256": baseline_manifest["manifest_semantic_sha256"],
        }
        candidate_manifest = _manifest_object(
            manifest_id="nwiro-restricted-probe-candidate-source-v1",
            role="candidate_source",
            captured_utc=captured_utc,
            snapshot=candidate_snapshot,
            contract_hash=CONTRACT_SHA256,
            execution_authorization_hash=execution_authorization_hash,
            project_descriptor_hash=project_descriptor_hash,
            creator_hash=creator_hash,
            baseline_manifest_binding=baseline_binding,
        )
        candidate_payload = _canonical_file_bytes(candidate_manifest)
        delta_manifest = _build_exact_delta(
            captured_utc=captured_utc,
            baseline=fork_snapshot,
            candidate=candidate_snapshot,
            baseline_manifest_sha256=_sha256_bytes(baseline_payload),
            candidate_manifest_sha256=_sha256_bytes(candidate_payload),
            baseline_manifest_semantic_sha256=baseline_manifest[
                "manifest_semantic_sha256"
            ],
            candidate_manifest_semantic_sha256=candidate_manifest[
                "manifest_semantic_sha256"
            ],
            baseline_manifest_bytes=len(baseline_payload),
            candidate_manifest_bytes=len(candidate_payload),
            execution_authorization_hash=execution_authorization_hash,
        )
        delta_payload = _canonical_file_bytes(delta_manifest)
        _write_exclusive(baseline_temp, baseline_payload)
        _write_exclusive(candidate_manifest_temp, candidate_payload)
        _write_exclusive(delta_temp, delta_payload)
        for manifest_temp in (
            baseline_temp,
            candidate_manifest_temp,
            delta_temp,
        ):
            _apply_private_file_acl(manifest_temp)
            _require_exact_private_acl(manifest_temp)

        if _stable_sha256(PROJECT_DESCRIPTOR) != project_descriptor_hash:
            raise CandidateCreationError("project descriptor changed during slice")
        if _authenticate_protected_inputs() != protected_before:
            raise CandidateCreationError("protected input changed during slice")
        if _windows_identity(
            STAGING_PARENT, is_directory=True
        ) != staging_identity:
            raise CandidateCreationError("staging parent identity changed")
        if _windows_identity(
            transaction_root, is_directory=True
        ) != transaction_identity:
            raise CandidateCreationError("transaction root identity changed")
        if _named_alternate_streams(transaction_root):
            raise CandidateCreationError("transaction root gained named streams")

        baseline_identity = _windows_identity(
            baseline_temp, is_directory=False
        )
        _move_no_clobber(baseline_temp, BASELINE_MANIFEST_PATH)
        published.append((BASELINE_MANIFEST_PATH, baseline_identity, False))

        candidate_manifest_identity = _windows_identity(
            candidate_manifest_temp, is_directory=False
        )
        _move_no_clobber(
            candidate_manifest_temp, CANDIDATE_MANIFEST_PATH
        )
        published.append(
            (CANDIDATE_MANIFEST_PATH, candidate_manifest_identity, False)
        )

        candidate_identity = _windows_identity(
            candidate_temp, is_directory=True
        )
        _move_no_clobber(candidate_temp, CANDIDATE_ROOT)
        published.append((CANDIDATE_ROOT, candidate_identity, True))

        # Delta publication is the commit boundary.  Until this succeeds the
        # candidate is published-but-uncommitted and will be quarantined.
        delta_identity = _windows_identity(delta_temp, is_directory=False)
        _move_no_clobber(delta_temp, DELTA_MANIFEST_PATH)
        published.append((DELTA_MANIFEST_PATH, delta_identity, False))
        transaction_root.rmdir()
        transaction_identity = None
        result = verify_candidate()
        _release_empty_quarantine_reservation(
            rollback_parent_identity=rollback_parent_identity,
            quarantine_identity=quarantine_identity,
        )
        return result
    except Exception as exc:
        try:
            quarantine = _quarantine_failed_publication(
                transaction_root=transaction_root,
                transaction_identity=transaction_identity,
                nonce=nonce,
                published=published,
                rollback_parent_identity=rollback_parent_identity,
                quarantine_identity=quarantine_identity,
            )
        except Exception as quarantine_exc:
            raise CandidateCreationError(
                f"{exc}; quarantine failed closed: {quarantine_exc}"
            ) from exc
        raise CandidateCreationError(
            f"{exc}; current-run state quarantined at {quarantine}"
        ) from exc


def verify_candidate() -> dict[str, Any]:
    _require_fixed_layout()
    _ensure_private_staging_parent(create_if_absent=False)
    required_paths = (
        CANDIDATE_ROOT,
        BASELINE_MANIFEST_PATH,
        CANDIDATE_MANIFEST_PATH,
        DELTA_MANIFEST_PATH,
    )
    if not CANDIDATE_ROOT.is_dir() or any(
        not path.is_file() for path in required_paths[1:]
    ):
        raise CandidateCreationError("candidate or committed manifest is absent")
    _require_reserved_namespace({path.name for path in required_paths})
    _authenticate_contract_postpublication()
    _require_exact_private_acl(CANDIDATE_ROOT)
    for manifest_path in required_paths[1:]:
        _require_exact_private_acl(manifest_path)
    project_descriptor_hash = _stable_sha256(PROJECT_DESCRIPTOR)
    protected = _authenticate_protected_inputs()
    _, execution_authorization_hash = (
        _authenticate_execution_authorization(
            project_descriptor_hash=project_descriptor_hash,
            protected_inputs=protected,
        )
    )
    source_snapshot = _fork_snapshot_from_full(
        _scan_two_pass(SOURCE_ROOT), SOURCE_ROOT
    )
    candidate_snapshot = _scan_two_pass(CANDIDATE_ROOT)
    _require_expected_fork_snapshot(source_snapshot)
    _require_expected_fork_snapshot(candidate_snapshot)
    _require_byte_exact_copy(source_snapshot, candidate_snapshot)
    manifest_hashes = _verify_bundle(
        source_snapshot=source_snapshot,
        candidate_snapshot=candidate_snapshot,
        project_descriptor_hash=project_descriptor_hash,
        execution_authorization_hash=execution_authorization_hash,
    )
    _authenticate_contract_postpublication()
    _, final_execution_authorization_hash = (
        _authenticate_execution_authorization(
            project_descriptor_hash=project_descriptor_hash,
            protected_inputs=protected,
        )
    )
    if final_execution_authorization_hash != execution_authorization_hash:
        raise CandidateCreationError(
            "execution authorization changed during verification"
        )
    if _authenticate_protected_inputs() != protected:
        raise CandidateCreationError("protected input changed during verification")
    return {
        "status": "inert_exact_copy_candidate_skeleton_verified",
        "evidence_class": "static",
        "candidate_root": _path_text(CANDIDATE_ROOT),
        "manifest_paths": [
            _path_text(BASELINE_MANIFEST_PATH),
            _path_text(CANDIDATE_MANIFEST_PATH),
            _path_text(DELTA_MANIFEST_PATH),
        ],
        "file_count": candidate_snapshot.file_count,
        "directory_count_excluding_root": (
            candidate_snapshot.directory_count_excluding_root
        ),
        "total_bytes": candidate_snapshot.total_bytes,
        "record_set_sha256": candidate_snapshot.record_set_sha256,
        "topology_sha256": candidate_snapshot.topology_sha256,
        "manifest_hashes": manifest_hashes,
        "execution_authorization": {
            "path": _path_text(EXECUTION_AUTH_PATH),
            "sha256": execution_authorization_hash,
        },
        "project_descriptor_sha256": project_descriptor_hash,
        "protected_inputs": protected,
        "outside_two_checked_automatic_plugin_roots": True,
        "universal_plugin_discovery_exclusion_proven": False,
        "activation_state": (
            "not_built_not_installed_not_configured_"
            "explicit_additional_paths_unproven"
        ),
        "source_default_off": False,
        "inert_only_by_external_location_and_no_binary": True,
        "restricted_mode_implemented": False,
        "candidate_static_accepted": False,
        "runtime_authorized": False,
        "build_authorized": False,
        "install_authorized": False,
        "unreal_launch_authorized": False,
        "mcp_initialize_authorized": False,
        "mcp_tool_call_authorized": False,
        "network_authorized": False,
        "provider_call_authorized": False,
        "atomic_whole_tree_snapshot_proven": False,
        "concurrent_writer_resistance_proven": False,
        "power_loss_durability_proven": False,
        "claim_limit": (
            "Static exact-copy skeleton and lineage evidence only; no source "
            "controls, build, plugin activation, MCP, provider, asset, map, "
            "visual, gameplay, performance, or runtime result is accepted."
        ),
    }


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or verify the fixed inert Nwiro source skeleton."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--create",
        action="store_true",
        help="Create the fixed absent candidate and manifest roots once.",
    )
    mode.add_argument(
        "--verify",
        action="store_true",
        help="Read-only verification of the fixed published roots.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = create_candidate() if args.create else verify_candidate()
    except (CandidateCreationError, CandidateContractError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed_closed",
                    "error": str(exc),
                    "runtime_authorized": False,
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
