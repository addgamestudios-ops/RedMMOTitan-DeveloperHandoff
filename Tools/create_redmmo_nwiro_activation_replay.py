#!/usr/bin/env python3
"""Publish, verify, and execute the authenticated NWIRO activation replay.

The replay is an external, unbuilt source tree for the previously reviewed
activation/ownership revision.  It is reconstructed from 87 byte-identical
files in the advanced candidate plus the three authenticated pre-lifecycle
rollback files.  This tool never swaps the live candidate, builds or installs
the plugin, launches Unreal, binds a transport, initializes MCP, calls a
provider, or reads/writes a game asset.

Publication is fixed-path, private, and no-clobber.  The historical tests are
left byte-identical: the replay command changes only their in-memory candidate
root for one fresh Python process.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import ctypes
import dataclasses
import hashlib
import io
import json
import msvcrt
import os
import re
import stat
import subprocess
import sys
import types
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from create_redmmo_nwiro_restricted_probe_candidate import (
    CandidateCreationError,
    TreeSnapshot,
    _canonical_file_bytes,
    _current_token_sid,
    _lexists,
    _move_no_clobber,
    _scan_two_pass,
    _write_exclusive,
    _windows_identity,
)
from validate_redmmo_nwiro_restricted_probe_candidate_contract import (
    _is_reparse,
    _named_alternate_streams,
    _validate_existing_ancestor_chain,
    load_json_bytes_strict,
)


PROJECT_ROOT = Path(r"D:\RedMMOTitan")
STAGING_PARENT = Path(r"D:\RedMMOTitanWindowsData\Staging")
CURRENT_CANDIDATE_ROOT = (
    STAGING_PARENT / "NwiroRestrictedProbeForkCandidateV1"
)
LIFECYCLE_ROLLBACK_ROOT = Path(
    r"D:\RedMMOTitanWindowsData\Rollback"
    r"\NwiroRestrictedProbeLifecycle_20260725_1223Z"
)
OUTPUT_ROOT = STAGING_PARENT / "NwiroRestrictedProbeActivationReplayV1"
OUTPUT_TREE = OUTPUT_ROOT / "tree"
OUTPUT_MANIFEST = OUTPUT_ROOT / "replay.v1.json"
AUTHORIZATION_PATH = (
    PROJECT_ROOT
    / "Build"
    / "Automation"
    / "redmmo_nwiro_activation_replay_execution_authorization_v1.json"
)
PUBLISHER_TEST_PATH = (
    PROJECT_ROOT
    / "Tools"
    / "tests"
    / "test_create_redmmo_nwiro_activation_replay.py"
)

PARENT_EVIDENCE = (
    PROJECT_ROOT
    / "ProjectKnowledge"
    / "evidence"
    / "2026-07-25-m07-nwiro-activation-ownership-source-static.yaml"
)
LIFECYCLE_EVIDENCE = (
    PROJECT_ROOT
    / "ProjectKnowledge"
    / "evidence"
    / "2026-07-25-m07-nwiro-lifecycle-session-source-static.yaml"
)
PARENT_MANIFEST = (
    STAGING_PARENT
    / "NwiroRestrictedProbeActivationOwnershipEvidenceV1"
    / "candidate.v1.json"
)
PARENT_DELTA = (
    STAGING_PARENT
    / "NwiroRestrictedProbeActivationOwnershipEvidenceV1"
    / "delta.v1.json"
)
LIFECYCLE_MANIFEST = (
    STAGING_PARENT
    / "NwiroRestrictedProbeLifecycleEvidenceV1"
    / "candidate.v1.json"
)
LIFECYCLE_DELTA = (
    STAGING_PARENT
    / "NwiroRestrictedProbeLifecycleEvidenceV1"
    / "delta.v1.json"
)

HISTORICAL_SOURCE_TEST = (
    PROJECT_ROOT
    / "Tools"
    / "tests"
    / "test_redmmo_nwiro_activation_ownership_source.py"
)
HISTORICAL_MANIFEST_TEST = (
    PROJECT_ROOT
    / "Tools"
    / "tests"
    / "test_generate_redmmo_nwiro_activation_ownership_manifests.py"
)
HISTORICAL_GENERATOR = (
    PROJECT_ROOT
    / "Tools"
    / "generate_redmmo_nwiro_activation_ownership_manifests.py"
)
AUDIT_HELPER = (
    PROJECT_ROOT / "Tools" / "audit_nwiro_restricted_probe_source.py"
)
SCAN_HELPER = (
    PROJECT_ROOT
    / "Tools"
    / "create_redmmo_nwiro_restricted_probe_candidate.py"
)
CONTRACT_HELPER = (
    PROJECT_ROOT
    / "Tools"
    / "validate_redmmo_nwiro_restricted_probe_candidate_contract.py"
)
TOOLS_PACKAGE_INIT = PROJECT_ROOT / "Tools" / "__init__.py"
TOOLS_TESTS_PACKAGE_INIT = PROJECT_ROOT / "Tools" / "tests" / "__init__.py"
ACTIVATION_AUTHORIZATION = (
    PROJECT_ROOT
    / "Build"
    / "Automation"
    / "redmmo_nwiro_activation_ownership_execution_authorization_v1.json"
)
ACTIVATION_ROLLBACK_ROOT = Path(
    r"D:\RedMMOTitanWindowsData\Rollback"
    r"\NwiroRestrictedProbeActivationOwnership_20260725_1130Z"
)
HISTORICAL_BASELINE_MANIFEST = (
    STAGING_PARENT / "NwiroRestrictedProbeForkCandidateV1.baseline.v1.json"
)
HISTORICAL_CANDIDATE_MANIFEST = (
    STAGING_PARENT / "NwiroRestrictedProbeForkCandidateV1.candidate.v1.json"
)
HISTORICAL_DELTA_MANIFEST = (
    STAGING_PARENT / "NwiroRestrictedProbeForkCandidateV1.delta.v1.json"
)

PARENT_EVIDENCE_SHA256 = (
    "6CEE59968A6E442671E8C79468C1F7A58CE73C2041EFBA39268E9444711CD947"
)
LIFECYCLE_EVIDENCE_SHA256 = (
    "7FDE78F5F104E597BF7EB74A6B2A015B9D1C552AA392BBFA82B84095B4C137F6"
)
PARENT_MANIFEST_SHA256 = (
    "6DB05AD5720F53B47FC592B714830EAEA450F0BB22269264145413B364219CB5"
)
PARENT_DELTA_SHA256 = (
    "647E8ED20CBBCEDDAD925CD6B72E2FC42949FE7C44E9E5143F26F0A3FF24579A"
)
LIFECYCLE_MANIFEST_SHA256 = (
    "AE9126B0A744456A31E356F3C6147CAAE7D6E1297655B4C8F62C1B525FC16211"
)
LIFECYCLE_DELTA_SHA256 = (
    "B0B8B314210586707F87840EB9342D5B9447B8B9D25F5627A7F5393A862D1A3F"
)
HISTORICAL_SOURCE_TEST_SHA256 = (
    "DA540889BC1C9B75A287CABF1B1E194A5141234BFE5DAE3D79D16A8A29E5D25A"
)
HISTORICAL_MANIFEST_TEST_SHA256 = (
    "D8DFEE58A10D225F64DE43340875C2FE6AC2096A33F5DAE9D8AD0E15E92B2D18"
)
HISTORICAL_GENERATOR_SHA256 = (
    "7A648D576E9D410031B5560DE0F0C5825FBECE63E32C463D8C9B94F48D271B37"
)
AUDIT_HELPER_SHA256 = (
    "2E8B3B669630B125BB0C427C6F52CDC2DF7F24392D1728374342808C635CEAC1"
)
SCAN_HELPER_SHA256 = (
    "28BCF5F28CB94C136355536D9E1386E21895BA597F857CC2E892E6CB336AC47E"
)
CONTRACT_HELPER_SHA256 = (
    "A829BC5E131BA7812E1F003F2BEA3E684D6DCA2D7CFEFAFC5048502BCBBE3B02"
)
TOOLS_PACKAGE_INIT_SHA256 = (
    "834ABA85E3729E442006B10D5699A06EE4D31F544AD9E2FC2BF09C0986DC4734"
)
TOOLS_TESTS_PACKAGE_INIT_SHA256 = (
    "CBA3B9695D5C392D562422E56F67697FC786E3A9F3198701C68C5E1B6321D0AA"
)
ACTIVATION_AUTHORIZATION_SHA256 = (
    "4FA858EA6FF7EE70EE8B9FB5C5234B647851421E96B90B3BB3C80F6EC934BB42"
)
ACTIVATION_ROLLBACK_FILES = {
    "NwiroIntegrationKit.uplugin": (
        1_212,
        "D6CCBFA2F08D478F0C53C67E0D8FCD5FF275C57948425D55D560309AD1C60B2E",
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp": (
        199_619,
        "34C1BB2E81A7FFF742D043EC8E983783C047BA9C5ABBA4BE9CDB4806AD7CD8D7",
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h": (
        3_417,
        "CB310B6A8857AD8824F5899C13C263FEE5EF5558F3F7BCE9E8EA0198B7272498",
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIntegrationKit.cpp": (
        4_688,
        "0AF1C0174BB2AF09A9555D6E6EBB471E0F9C1FF43B3E1537A0EFA415C0AA2BCF",
    ),
    "Source/NwiroIntegrationKit/Public/NwiroIK.h": (
        444,
        "B6769D41894A85FAE704B565F46D6545BEDD5E77BD59756ECAC3665508912C74",
    ),
}

HISTORICAL_MODULES = {
    "Tools.tests.test_redmmo_nwiro_activation_ownership_source": (
        HISTORICAL_SOURCE_TEST,
        HISTORICAL_SOURCE_TEST_SHA256,
    ),
    "Tools.tests.test_generate_redmmo_nwiro_activation_ownership_manifests": (
        HISTORICAL_MANIFEST_TEST,
        HISTORICAL_MANIFEST_TEST_SHA256,
    ),
    "Tools.generate_redmmo_nwiro_activation_ownership_manifests": (
        HISTORICAL_GENERATOR,
        HISTORICAL_GENERATOR_SHA256,
    ),
    "Tools.audit_nwiro_restricted_probe_source": (
        AUDIT_HELPER,
        AUDIT_HELPER_SHA256,
    ),
}
HISTORICAL_PACKAGE_MODULES = {
    "Tools": (TOOLS_PACKAGE_INIT, TOOLS_PACKAGE_INIT_SHA256),
    "Tools.tests": (
        TOOLS_TESTS_PACKAGE_INIT,
        TOOLS_TESTS_PACKAGE_INIT_SHA256,
    ),
}

EXPECTED_PARENT_FILE_COUNT = 90
EXPECTED_PARENT_DIRECTORY_COUNT = 10
EXPECTED_PARENT_TOTAL_BYTES = 2_207_742
EXPECTED_PARENT_RECORD_SET_SHA256 = (
    "761CB39071366A680D1CE0B2900FEC1103B64206D05E67904661CD3EE215CE11"
)
EXPECTED_PARENT_TOPOLOGY_SHA256 = (
    "7A2C6EE72ACA073C16D79DC01E6E8CB63A76DF8C9CD9291FA5D6413BF1137D18"
)
EXPECTED_CURRENT_TOTAL_BYTES = 2_228_379
EXPECTED_CURRENT_RECORD_SET_SHA256 = (
    "4857CA12853867F77C7B81F1133A7E9DB6A8078DDC804AB6D92631791BE9C761"
)
EXPECTED_CURRENT_TOPOLOGY_SHA256 = (
    "8788A05E64243D692AD4764421645E68D02951D33DD9C86ED546F0F40A88D6D5"
)
EXPECTED_ROLLBACK_TOTAL_BYTES = 502_342
EXPECTED_ROLLBACK_RECORD_SET_SHA256 = (
    "40E0475151AA1D4CC997144EF750A334EC10DA415DDF9A307DCB752C019C37C5"
)
EXPECTED_ROLLBACK_TOPOLOGY_SHA256 = (
    "193930B580609ADEECBACD201083EA104283F18528F68DB565EB5901C689CD7B"
)

OVERLAY_SOURCES = {
    "Source/NwiroIntegrationKit/Private/NwiroIKBridge.cpp": {
        "rollback_name": "NwiroIKBridge.cpp",
        "bytes": 293_840,
        "sha256": (
            "80C8A3194148C86D1F4E1D479133BB2B76A627698F2E35DC4D6CE822E5FC1AA1"
        ),
    },
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp": {
        "rollback_name": "NwiroIKMCPServer.cpp",
        "bytes": 204_464,
        "sha256": (
            "AA3FD57690EB52EEADCC473DA5C15C0F6A555199A06C9EEA4EF18258ECE20099"
        ),
    },
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h": {
        "rollback_name": "NwiroIKMCPServer.h",
        "bytes": 4_038,
        "sha256": (
            "E6161EFD3E4F34DE037D329766A61D792ECC572FDCF8D83592AE99277F4AF747"
        ),
    },
}

PROTECTED_INPUTS = {
    PROJECT_ROOT / "Content/RedMMO/Maps/RedPlanetGen.umap": (
        "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724"
    ),
    PROJECT_ROOT / "Content/RedMMO/Maps/RedPlanetGen_50km_Test.umap": (
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D"
    ),
    PROJECT_ROOT
    / "Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap": (
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284"
    ),
    PROJECT_ROOT
    / "Content/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield.uasset": (
        "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562"
    ),
}

SOURCE_TEST_METHODS = (
    "test_both_activation_authority_functions_are_literal_false_only",
    "test_candidate_contains_no_binary_or_compiled_output",
    "test_descriptor_is_explicitly_default_off",
    "test_direct_jsonrpc_and_http_entrypoints_fail_before_parsing",
    "test_historical_baseline_and_current_delta_are_exactly_bounded",
    "test_module_checks_activation_and_server_gate_before_ui",
    "test_no_external_activation_input_is_present_in_changed_sources",
    "test_ownership_reference_model_allows_exactly_one_process",
    "test_production_activation_authority_is_hard_off",
    "test_restart_config_and_dispatch_bypasses_are_callee_gated",
    "test_reviewed_control_flow_functions_match_exact_normalized_revision",
    "test_runtime_readiness_remains_hard_false",
    "test_start_acquires_owner_before_every_listener_side_effect",
    "test_stop_releases_owner_even_when_listener_never_started",
    "test_system_wide_mutex_is_fixed_retained_and_nonblocking",
    "test_teardown_disables_admission_before_releasing_owner",
)
MANIFEST_TEST_METHODS = (
    "test_delta_binds_candidate_raw_bytes",
    "test_documents_are_canonical_and_deterministic",
    "test_documents_bind_exact_five_file_delta_and_inert_claims",
    "test_invalid_timestamp_fails_before_scanning",
    "test_publish_refuses_either_existing_fixed_output",
    "test_publish_refuses_orphan_transaction_namespace",
)

_TRANSACTION_PREFIX = ".NwiroRestrictedProbeActivationReplayV1.txn."
_RFC3339_UTC = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
_FORBIDDEN_BINARY_SUFFIXES = {".dll", ".exe", ".lib", ".obj", ".pdb"}
_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
_FILE_ATTRIBUTE_TAG_INFO = 9
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_SYSTEM32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
_ICACLS = _SYSTEM32 / "icacls.exe"
_POWERSHELL = (
    _SYSTEM32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"
)


class ActivationReplayError(RuntimeError):
    """Raised when replay publication or verification must refuse closed."""


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", ctypes.c_ulong),
        ("ReparseTag", ctypes.c_ulong),
    ]


class _WindowsFileId128(ctypes.Structure):
    _fields_ = [("Identifier", ctypes.c_ubyte * 16)]


class _WindowsFileIdInformation(ctypes.Structure):
    _fields_ = [
        ("VolumeSerialNumber", ctypes.c_ulonglong),
        ("FileId", _WindowsFileId128),
    ]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _path_text(path: Path) -> str:
    return os.path.abspath(str(path)).replace("\\", "/")


def _stable_payload(path: Path, max_bytes: int = 32 * 1024 * 1024) -> bytes:
    """Read a regular NTFS file while denying new write/delete opens."""

    _validate_existing_ancestor_chain(path.parent)
    if path.is_symlink():
        raise ActivationReplayError(f"symlink refused: {path}")
    before = path.stat(follow_symlinks=False)
    if _is_reparse(before):
        raise ActivationReplayError(f"reparse point refused: {path}")
    if not stat.S_ISREG(before.st_mode):
        raise ActivationReplayError(f"regular file required: {path}")
    if getattr(before, "st_nlink", 1) != 1:
        raise ActivationReplayError(f"hard-linked source refused: {path}")
    if before.st_size <= 0 or before.st_size > max_bytes:
        raise ActivationReplayError(f"source size outside bound: {path}")
    if _named_alternate_streams(path):
        raise ActivationReplayError(f"named alternate stream refused: {path}")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    get_info = kernel32.GetFileInformationByHandleEx
    get_info.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    get_info.restype = ctypes.c_int
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int

    handle = create_file(
        str(path),
        _GENERIC_READ,
        _FILE_SHARE_READ,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_SEQUENTIAL_SCAN,
        None,
    )
    if handle in (None, _INVALID_HANDLE_VALUE):
        raise ActivationReplayError(
            f"locked source open failed for {path}: {ctypes.get_last_error()}"
        )
    fd: int | None = None
    try:
        tag = _FileAttributeTagInfo()
        if not get_info(
            handle,
            _FILE_ATTRIBUTE_TAG_INFO,
            ctypes.byref(tag),
            ctypes.sizeof(tag),
        ):
            raise ActivationReplayError(
                f"source attribute query failed for {path}: "
                f"{ctypes.get_last_error()}"
            )
        if tag.FileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise ActivationReplayError(f"opened source is reparse point: {path}")
        fd = msvcrt.open_osfhandle(
            int(handle),
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
        handle = None
        with os.fdopen(fd, "rb", closefd=True) as stream:
            fd = None
            opened = os.fstat(stream.fileno())
            if (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                getattr(opened, "st_nlink", 1),
            ) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
                getattr(before, "st_nlink", 1),
            ):
                raise ActivationReplayError(
                    f"source identity changed before locked read: {path}"
                )
            payload = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
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
                raise ActivationReplayError(
                    f"source changed during locked read: {path}"
                )
    finally:
        if fd is not None:
            os.close(fd)
        if handle not in (None, _INVALID_HANDLE_VALUE):
            close_handle(handle)

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
        raise ActivationReplayError(
            f"source pathname changed after locked read: {path}"
        )
    if len(payload) != before.st_size:
        raise ActivationReplayError(f"source length changed: {path}")
    if _named_alternate_streams(path):
        raise ActivationReplayError(
            f"named alternate stream appeared after read: {path}"
        )
    return payload


def _authenticated_bytes(path: Path, expected_sha256: str) -> bytes:
    payload = _stable_payload(path)
    observed = _sha256(payload)
    if observed != expected_sha256:
        raise ActivationReplayError(
            f"authenticated input drift: {path} ({observed})"
        )
    return payload


def _open_held_read_lock(path: Path) -> tuple[int, tuple[str, str]]:
    """Open one retained source handle that denies new write/delete opens."""

    _validate_existing_ancestor_chain(path.parent)
    if path.is_symlink():
        raise ActivationReplayError(f"symlink refused before lock: {path}")
    before = path.stat(follow_symlinks=False)
    if (
        _is_reparse(before)
        or not stat.S_ISREG(before.st_mode)
        or getattr(before, "st_nlink", 1) != 1
        or _named_alternate_streams(path)
    ):
        raise ActivationReplayError(f"unsafe file refused before lock: {path}")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    get_info = kernel32.GetFileInformationByHandleEx
    get_info.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    get_info.restype = ctypes.c_int
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    handle = create_file(
        str(path),
        _GENERIC_READ,
        _FILE_SHARE_READ,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_SEQUENTIAL_SCAN,
        None,
    )
    if handle in (None, _INVALID_HANDLE_VALUE):
        raise ActivationReplayError(
            f"retained read lock failed for {path}: {ctypes.get_last_error()}"
        )
    try:
        tag = _FileAttributeTagInfo()
        if not get_info(
            handle,
            _FILE_ATTRIBUTE_TAG_INFO,
            ctypes.byref(tag),
            ctypes.sizeof(tag),
        ):
            raise ActivationReplayError(
                f"retained lock attribute query failed for {path}"
            )
        if tag.FileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise ActivationReplayError(
                f"retained lock opened reparse point: {path}"
            )
        identity = _WindowsFileIdInformation()
        if not get_info(
            handle,
            18,
            ctypes.byref(identity),
            ctypes.sizeof(identity),
        ):
            raise ActivationReplayError(
                f"retained lock identity query failed for {path}"
            )
        observed = (
            f"{identity.VolumeSerialNumber:016X}",
            bytes(identity.FileId.Identifier).hex().upper(),
        )
        if observed != _windows_identity(path, is_directory=False):
            raise ActivationReplayError(
                f"retained lock pathname identity mismatch: {path}"
            )
        return int(handle), observed
    except Exception:
        close_handle(handle)
        raise


@contextlib.contextmanager
def _held_read_locks(paths: Sequence[Path]):
    """Retain exact read-only share handles across historical assertions."""

    unique: dict[str, Path] = {}
    for path in paths:
        key = _path_text(path).casefold()
        if key in unique:
            raise ActivationReplayError(f"duplicate held-lock path: {path}")
        unique[key] = path
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    handles: list[int] = []
    try:
        for path in sorted(unique.values(), key=_path_text):
            handle, _ = _open_held_read_lock(path)
            handles.append(handle)
        yield
    finally:
        for handle in reversed(handles):
            close_handle(handle)


def _authenticated_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    payload = _authenticated_bytes(path, expected_sha256)
    value = load_json_bytes_strict(payload, str(path))
    if not isinstance(value, dict):
        raise ActivationReplayError(f"JSON object required: {path}")
    if payload != _canonical_file_bytes(value):
        raise ActivationReplayError(f"canonical JSON plus LF required: {path}")
    return value


def _semantic_hash(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("manifest_semantic_sha256", None)
    return _sha256(_canonical_file_bytes(payload))


def _with_semantic_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["manifest_semantic_sha256"] = _semantic_hash(result)
    return result


def _strict_utc(value: Any, label: str) -> str:
    if type(value) is not str or not _RFC3339_UTC.fullmatch(value):
        raise ActivationReplayError(f"{label} is not strict UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ActivationReplayError(f"{label} is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        raise ActivationReplayError(f"{label} is not UTC")
    return value


def _file_binding(path: Path, sha256: str) -> dict[str, Any]:
    payload = _authenticated_bytes(path, sha256)
    return {
        "path": _path_text(path),
        "bytes": len(payload),
        "sha256": sha256,
    }


def _expected_authorization(authorized_utc: str) -> dict[str, Any]:
    publisher_hash = _sha256(_stable_payload(Path(__file__)))
    publisher_test_hash = _sha256(_stable_payload(PUBLISHER_TEST_PATH))
    protected = [
        _file_binding(path, digest)
        for path, digest in sorted(
            PROTECTED_INPUTS.items(),
            key=lambda item: _path_text(item[0]),
        )
    ]
    return {
        "schema_version": 1,
        "authorization_id": (
            "redmmo.m07.nwiro.activation-parent-replay-publication-v1"
        ),
        "status": "approved_once_offline_parent_replay_only",
        "evidence_class": "static",
        "authorized_utc": authorized_utc,
        "approved_operation": (
            "Publish one fixed private no-clobber external source replay of "
            "the authenticated parent activation revision and execute only "
            "its unchanged historical offline assertions through in-memory "
            "path isolation."
        ),
        "publisher": _file_binding(Path(__file__), publisher_hash),
        "publisher_tests": _file_binding(
            PUBLISHER_TEST_PATH, publisher_test_hash
        ),
        "authenticated_inputs": [
            _file_binding(PARENT_EVIDENCE, PARENT_EVIDENCE_SHA256),
            _file_binding(LIFECYCLE_EVIDENCE, LIFECYCLE_EVIDENCE_SHA256),
            _file_binding(PARENT_MANIFEST, PARENT_MANIFEST_SHA256),
            _file_binding(PARENT_DELTA, PARENT_DELTA_SHA256),
            _file_binding(LIFECYCLE_MANIFEST, LIFECYCLE_MANIFEST_SHA256),
            _file_binding(LIFECYCLE_DELTA, LIFECYCLE_DELTA_SHA256),
            _file_binding(
                HISTORICAL_SOURCE_TEST,
                HISTORICAL_SOURCE_TEST_SHA256,
            ),
            _file_binding(
                HISTORICAL_MANIFEST_TEST,
                HISTORICAL_MANIFEST_TEST_SHA256,
            ),
            _file_binding(
                HISTORICAL_GENERATOR,
                HISTORICAL_GENERATOR_SHA256,
            ),
            _file_binding(AUDIT_HELPER, AUDIT_HELPER_SHA256),
            _file_binding(SCAN_HELPER, SCAN_HELPER_SHA256),
            _file_binding(CONTRACT_HELPER, CONTRACT_HELPER_SHA256),
            _file_binding(
                TOOLS_PACKAGE_INIT,
                TOOLS_PACKAGE_INIT_SHA256,
            ),
            _file_binding(
                TOOLS_TESTS_PACKAGE_INIT,
                TOOLS_TESTS_PACKAGE_INIT_SHA256,
            ),
            _file_binding(
                ACTIVATION_AUTHORIZATION,
                ACTIVATION_AUTHORIZATION_SHA256,
            ),
            *[
                _file_binding(
                    ACTIVATION_ROLLBACK_ROOT / Path(relative),
                    digest,
                )
                for relative, (_, digest) in sorted(
                    ACTIVATION_ROLLBACK_FILES.items()
                )
            ],
        ],
        "source_roots": {
            "advanced_candidate": {
                "root": _path_text(CURRENT_CANDIDATE_ROOT),
                "file_count": 90,
                "directory_count_excluding_root": 10,
                "total_bytes": EXPECTED_CURRENT_TOTAL_BYTES,
                "record_set_sha256": EXPECTED_CURRENT_RECORD_SET_SHA256,
                "topology_sha256": EXPECTED_CURRENT_TOPOLOGY_SHA256,
                "mutation_authorized": False,
            },
            "lifecycle_rollback": {
                "root": _path_text(LIFECYCLE_ROLLBACK_ROOT),
                "file_count": 3,
                "directory_count_excluding_root": 0,
                "total_bytes": EXPECTED_ROLLBACK_TOTAL_BYTES,
                "record_set_sha256": EXPECTED_ROLLBACK_RECORD_SET_SHA256,
                "topology_sha256": EXPECTED_ROLLBACK_TOPOLOGY_SHA256,
                "mutation_authorized": False,
            },
        },
        "replay_target": {
            "bundle_root": _path_text(OUTPUT_ROOT),
            "tree_root": _path_text(OUTPUT_TREE),
            "manifest": _path_text(OUTPUT_MANIFEST),
            "file_count": EXPECTED_PARENT_FILE_COUNT,
            "directory_count_excluding_root": (
                EXPECTED_PARENT_DIRECTORY_COUNT
            ),
            "total_bytes": EXPECTED_PARENT_TOTAL_BYTES,
            "record_set_sha256": EXPECTED_PARENT_RECORD_SET_SHA256,
            "topology_sha256": EXPECTED_PARENT_TOPOLOGY_SHA256,
            "single_use_no_clobber": True,
            "private_acl_required": True,
        },
        "protected_inputs": protected,
        "authorities": {
            "replay_publication_authorized": True,
            "private_transaction_authorized": True,
            "historical_offline_assertion_replay_authorized": True,
            "source_mutation_authorized": False,
            "live_candidate_swap_authorized": False,
            "junction_or_link_authorized": False,
            "build_authorized": False,
            "install_authorized": False,
            "unreal_launch_authorized": False,
            "mcp_initialize_authorized": False,
            "mcp_tool_call_authorized": False,
            "network_authorized": False,
            "provider_call_authorized": False,
            "asset_load_authorized": False,
            "asset_or_map_mutation_authorized": False,
            "vendor_plugin_mutation_authorized": False,
            "codex_config_mutation_authorized": False,
            "runtime_acceptance_claim_authorized": False,
            "static_candidate_acceptance_claim_authorized": False,
        },
        "rollback": {
            "existing_target_overwrite_authorized": False,
            "run_owned_orphan_transaction_preserved_on_failure": True,
            "recursive_cleanup_authorized": False,
        },
    }


def _authenticate_authorization() -> tuple[dict[str, Any], str]:
    payload = _stable_payload(AUTHORIZATION_PATH)
    value = load_json_bytes_strict(payload, str(AUTHORIZATION_PATH))
    if not isinstance(value, dict):
        raise ActivationReplayError("authorization must be a JSON object")
    if payload != _canonical_file_bytes(value):
        raise ActivationReplayError("authorization must be canonical JSON plus LF")
    authorized_utc = _strict_utc(
        value.get("authorized_utc"), "authorization timestamp"
    )
    expected = _expected_authorization(authorized_utc)
    if value != expected:
        raise ActivationReplayError("execution authorization shape or bytes drift")
    return value, _sha256(payload)


def _records(snapshot: TreeSnapshot) -> dict[str, dict[str, Any]]:
    return {str(record["path"]): dict(record) for record in snapshot.files}


def _parent_records(parent: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    tree = parent.get("tree")
    if not isinstance(tree, dict) or not isinstance(tree.get("files"), list):
        raise ActivationReplayError("parent manifest tree is malformed")
    records: dict[str, dict[str, Any]] = {}
    for raw in tree["files"]:
        if not isinstance(raw, dict):
            raise ActivationReplayError("parent file record is malformed")
        relative = raw.get("path")
        if not isinstance(relative, str) or relative in records:
            raise ActivationReplayError("duplicate or malformed parent path")
        records[relative] = dict(raw)
    return records


def _require_snapshot(
    snapshot: TreeSnapshot,
    *,
    file_count: int,
    directory_count: int,
    total_bytes: int,
    record_set_sha256: str,
    topology_sha256: str,
    label: str,
) -> None:
    observed = (
        snapshot.file_count,
        snapshot.directory_count_excluding_root,
        snapshot.total_bytes,
        snapshot.record_set_sha256,
        snapshot.topology_sha256,
    )
    expected = (
        file_count,
        directory_count,
        total_bytes,
        record_set_sha256,
        topology_sha256,
    )
    if observed != expected:
        raise ActivationReplayError(f"{label} snapshot drift: {observed!r}")


def _require_parent_logical_tree(
    snapshot: TreeSnapshot,
    parent: Mapping[str, Any],
) -> None:
    _require_snapshot(
        snapshot,
        file_count=EXPECTED_PARENT_FILE_COUNT,
        directory_count=EXPECTED_PARENT_DIRECTORY_COUNT,
        total_bytes=EXPECTED_PARENT_TOTAL_BYTES,
        record_set_sha256=EXPECTED_PARENT_RECORD_SET_SHA256,
        topology_sha256=EXPECTED_PARENT_TOPOLOGY_SHA256,
        label="replay",
    )
    tree = parent["tree"]
    expected_directories = tuple(
        str(record["path"]) for record in tree["directories"]
    )
    actual_directories = tuple(
        str(record["path"]) for record in snapshot.directories
    )
    if expected_directories != actual_directories:
        raise ActivationReplayError("replay directory topology drift")
    expected_files = {
        str(record["path"]): (
            int(record["bytes"]),
            str(record["sha256"]),
        )
        for record in tree["files"]
    }
    actual_files = {
        str(record["path"]): (
            int(record["bytes"]),
            str(record["sha256"]),
        )
        for record in snapshot.files
    }
    if expected_files != actual_files:
        raise ActivationReplayError("replay logical file inventory drift")
    for record in snapshot.files:
        relative = str(record["path"])
        if (
            Path(relative).suffix.casefold() in _FORBIDDEN_BINARY_SUFFIXES
            or any(
                part.casefold() in {"binaries", "intermediate"}
                for part in Path(relative).parts
            )
            or int(record.get("hard_link_count", 0)) != 1
            or record.get("alternate_streams") != []
        ):
            raise ActivationReplayError(
                f"forbidden replay file property: {relative}"
            )
    for record in snapshot.directories:
        if record.get("alternate_streams") != []:
            raise ActivationReplayError(
                f"directory alternate stream refused: {record['path']}"
            )


def _authenticate_inputs() -> dict[str, Any]:
    authorization, authorization_hash = _authenticate_authorization()
    _authenticated_bytes(PARENT_EVIDENCE, PARENT_EVIDENCE_SHA256)
    _authenticated_bytes(LIFECYCLE_EVIDENCE, LIFECYCLE_EVIDENCE_SHA256)
    parent = _authenticated_json(PARENT_MANIFEST, PARENT_MANIFEST_SHA256)
    _authenticated_json(PARENT_DELTA, PARENT_DELTA_SHA256)
    lifecycle = _authenticated_json(
        LIFECYCLE_MANIFEST, LIFECYCLE_MANIFEST_SHA256
    )
    lifecycle_delta = _authenticated_json(
        LIFECYCLE_DELTA, LIFECYCLE_DELTA_SHA256
    )
    for path, expected in (
        (HISTORICAL_SOURCE_TEST, HISTORICAL_SOURCE_TEST_SHA256),
        (HISTORICAL_MANIFEST_TEST, HISTORICAL_MANIFEST_TEST_SHA256),
        (HISTORICAL_GENERATOR, HISTORICAL_GENERATOR_SHA256),
        (AUDIT_HELPER, AUDIT_HELPER_SHA256),
        (SCAN_HELPER, SCAN_HELPER_SHA256),
        (CONTRACT_HELPER, CONTRACT_HELPER_SHA256),
        (TOOLS_PACKAGE_INIT, TOOLS_PACKAGE_INIT_SHA256),
        (TOOLS_TESTS_PACKAGE_INIT, TOOLS_TESTS_PACKAGE_INIT_SHA256),
        (ACTIVATION_AUTHORIZATION, ACTIVATION_AUTHORIZATION_SHA256),
    ):
        _authenticated_bytes(path, expected)
    activation_authorization_payload = _authenticated_bytes(
        ACTIVATION_AUTHORIZATION,
        ACTIVATION_AUTHORIZATION_SHA256,
    )
    activation_authorization = load_json_bytes_strict(
        activation_authorization_payload,
        str(ACTIVATION_AUTHORIZATION),
    )
    if not isinstance(activation_authorization, dict):
        raise ActivationReplayError(
            "activation authorization must be a JSON object"
        )
    if activation_authorization.get("rollback_root") != _path_text(
        ACTIVATION_ROLLBACK_ROOT
    ):
        raise ActivationReplayError("activation rollback-root binding drift")
    rollback_paths: set[str] = set()
    for relative, (expected_bytes, expected_hash) in sorted(
        ACTIVATION_ROLLBACK_FILES.items()
    ):
        path = ACTIVATION_ROLLBACK_ROOT / Path(relative)
        payload = _authenticated_bytes(
            path, expected_hash
        )
        if len(payload) != expected_bytes:
            raise ActivationReplayError(
                f"activation rollback length drift: {relative}"
            )
        rollback_paths.add(relative)
    observed_activation_rollback = _scan_two_pass(ACTIVATION_ROLLBACK_ROOT)
    if set(_records(observed_activation_rollback)) != rollback_paths:
        raise ActivationReplayError("activation rollback path-set drift")
    for path, expected in PROTECTED_INPUTS.items():
        _authenticated_bytes(path, expected)

    current = _scan_two_pass(CURRENT_CANDIDATE_ROOT)
    _require_snapshot(
        current,
        file_count=90,
        directory_count=10,
        total_bytes=EXPECTED_CURRENT_TOTAL_BYTES,
        record_set_sha256=EXPECTED_CURRENT_RECORD_SET_SHA256,
        topology_sha256=EXPECTED_CURRENT_TOPOLOGY_SHA256,
        label="advanced candidate",
    )
    rollback = _scan_two_pass(LIFECYCLE_ROLLBACK_ROOT)
    _require_snapshot(
        rollback,
        file_count=3,
        directory_count=0,
        total_bytes=EXPECTED_ROLLBACK_TOTAL_BYTES,
        record_set_sha256=EXPECTED_ROLLBACK_RECORD_SET_SHA256,
        topology_sha256=EXPECTED_ROLLBACK_TOPOLOGY_SHA256,
        label="lifecycle rollback",
    )
    parent_records = _parent_records(parent)
    current_records = _records(current)
    rollback_records = _records(rollback)
    if set(parent_records) != set(current_records):
        raise ActivationReplayError("parent/current path set drift")
    if set(rollback_records) != {
        str(value["rollback_name"]) for value in OVERLAY_SOURCES.values()
    }:
        raise ActivationReplayError("rollback path set drift")
    changed = {
        relative
        for relative in parent_records
        if (
            int(parent_records[relative]["bytes"]),
            str(parent_records[relative]["sha256"]),
        )
        != (
            int(current_records[relative]["bytes"]),
            str(current_records[relative]["sha256"]),
        )
    }
    if changed != set(OVERLAY_SOURCES):
        raise ActivationReplayError("parent/current three-file delta drift")
    for relative, expected in OVERLAY_SOURCES.items():
        parent_record = parent_records[relative]
        rollback_record = rollback_records[str(expected["rollback_name"])]
        if (
            int(parent_record["bytes"]),
            str(parent_record["sha256"]),
        ) != (
            int(expected["bytes"]),
            str(expected["sha256"]),
        ) or (
            int(rollback_record["bytes"]),
            str(rollback_record["sha256"]),
        ) != (
            int(expected["bytes"]),
            str(expected["sha256"]),
        ):
            raise ActivationReplayError(f"overlay source drift: {relative}")

    lifecycle_records = {
        str(record["path"]): record
        for record in lifecycle["tree"]["files"]
    }
    if {
        str(record["path"]) for record in lifecycle_delta["modified"]
    } != set(OVERLAY_SOURCES):
        raise ActivationReplayError("lifecycle delta path set drift")
    for relative in OVERLAY_SOURCES:
        if (
            lifecycle_records[relative]["sha256"]
            != current_records[relative]["sha256"]
        ):
            raise ActivationReplayError(
                f"current lifecycle record drift: {relative}"
            )
    return {
        "authorization": authorization,
        "authorization_hash": authorization_hash,
        "parent": parent,
        "current": current,
        "rollback": rollback,
    }


def _reserved_orphans() -> list[Path]:
    if not STAGING_PARENT.is_dir():
        raise ActivationReplayError("staging parent is absent")
    return sorted(
        (
            path
            for path in STAGING_PARENT.iterdir()
            if path.name.casefold().startswith(_TRANSACTION_PREFIX.casefold())
        ),
        key=lambda path: path.name.casefold(),
    )


def _apply_private_acl(path: Path, sid: str) -> None:
    access = "(OI)(CI)F" if path.is_dir() else "F"
    completed = subprocess.run(
        [
            str(_ICACLS),
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"*{sid}:{access}",
            f"*S-1-5-18:{access}",
            f"*S-1-5-32-544:{access}",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise ActivationReplayError(
            f"private ACL application failed for {path}: "
            f"{completed.stdout} {completed.stderr}".strip()
        )


def _all_paths(root: Path) -> list[Path]:
    """Enumerate without following a symlink, junction, or other reparse."""

    root_info = root.stat(follow_symlinks=False)
    if root.is_symlink() or _is_reparse(root_info) or not root.is_dir():
        raise ActivationReplayError("replay bundle root is linked or invalid")
    paths: list[Path] = [root]

    def visit(directory: Path) -> None:
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name.casefold())
        folded: set[str] = set()
        for entry in entries:
            key = entry.name.casefold()
            if key in folded:
                raise ActivationReplayError(
                    f"case-colliding replay entry: {entry.path}"
                )
            folded.add(key)
            path = Path(entry.path)
            info = path.stat(follow_symlinks=False)
            if path.is_symlink() or _is_reparse(info):
                raise ActivationReplayError(
                    f"linked/reparse replay entry refused: {path}"
                )
            if stat.S_ISDIR(info.st_mode):
                paths.append(path)
                visit(path)
            elif stat.S_ISREG(info.st_mode):
                paths.append(path)
            else:
                raise ActivationReplayError(
                    f"non-file replay entry refused: {path}"
                )

    visit(root)
    return paths


def _path_identities(root: Path) -> dict[str, tuple[bool, tuple[str, str]]]:
    result: dict[str, tuple[bool, tuple[str, str]]] = {}
    for path in _all_paths(root):
        key = _path_text(path).casefold()
        is_directory = path.is_dir()
        result[key] = (
            is_directory,
            _windows_identity(path, is_directory=is_directory),
        )
    return result


def _seal_private_acl(root: Path) -> None:
    sid = _current_token_sid()
    paths = _all_paths(root)
    identities = _path_identities(root)
    for path in sorted(
        paths,
        key=lambda value: (
            0 if value.is_file() else 1,
            -len(value.parts),
            _path_text(value),
        ),
    ):
        key = _path_text(path).casefold()
        expected_is_directory, expected_identity = identities[key]
        if (
            path.is_dir() != expected_is_directory
            or _windows_identity(
                path, is_directory=expected_is_directory
            )
            != expected_identity
        ):
            raise ActivationReplayError(
                f"ACL target identity changed before application: {path}"
            )
        _apply_private_acl(path, sid)
    if _path_identities(root) != identities:
        raise ActivationReplayError("ACL target identity changed during sealing")
    _require_private_acl_tree(root, sid)


def _require_private_acl_tree(root: Path, current_sid: str | None = None) -> None:
    if current_sid is None:
        current_sid = _current_token_sid()
    before_identities = _path_identities(root)
    exact_paths = [
        path
        for path, _ in sorted(
            (
                (key, value)
                for key, value in before_identities.items()
            ),
            key=lambda item: item[0],
        )
    ]
    paths_base64 = base64.b64encode(
        json.dumps(exact_paths, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    script = r"""
$Paths = @(
  [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String('__PATHS_BASE64__')
  ) | ConvertFrom-Json
)
$ErrorActionPreference = 'Stop'
$rows = foreach ($path in $Paths) {
  $item = Get-Item -LiteralPath ([string]$path) -Force
  $acl = Get-Acl -LiteralPath $item.FullName
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
    path = $item.FullName
    owner = $owner
    protected = [bool]$acl.AreAccessRulesProtected
    rules = @($rules)
  }
}
@($rows) | ConvertTo-Json -Depth 7 -Compress
""".replace("__PATHS_BASE64__", paths_base64)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    completed = subprocess.run(
        [
            str(_POWERSHELL),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise ActivationReplayError(
            f"private ACL inspection failed: {completed.stderr.strip()}"
        )
    try:
        rows = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ActivationReplayError("private ACL report is invalid") from exc
    if not isinstance(rows, list):
        raise ActivationReplayError("private ACL report must be a list")
    expected_paths = set(before_identities)
    observed_paths: set[str] = set()
    allowed = {current_sid, "S-1-5-18", "S-1-5-32-544"}
    for row in rows:
        if not isinstance(row, dict):
            raise ActivationReplayError("private ACL row is malformed")
        observed_paths.add(_path_text(Path(str(row.get("path")))).casefold())
        if row.get("protected") is not True:
            raise ActivationReplayError("ACL inheritance remains enabled")
        if row.get("owner") not in {current_sid, "S-1-5-32-544"}:
            raise ActivationReplayError("private ACL owner drift")
        rules = row.get("rules")
        if not isinstance(rules, list) or len(rules) != 3:
            raise ActivationReplayError("private ACL rule-count drift")
        rule_sids: set[str] = set()
        for rule in rules:
            if not isinstance(rule, dict):
                raise ActivationReplayError("private ACL rule malformed")
            sid = rule.get("sid")
            if sid not in allowed or sid in rule_sids:
                raise ActivationReplayError("private ACL principal drift")
            rule_sids.add(str(sid))
            if (
                rule.get("rights") != 2_032_127
                or rule.get("type") != "Allow"
                or rule.get("inherited") is not False
            ):
                raise ActivationReplayError("private ACL permission drift")
        if rule_sids != allowed:
            raise ActivationReplayError("private ACL allowlist incomplete")
    if observed_paths != expected_paths:
        raise ActivationReplayError("private ACL path coverage drift")
    if _path_identities(root) != before_identities:
        raise ActivationReplayError(
            "private ACL path identity changed during inspection"
        )


def _copy_parent_tree(
    destination_tree: Path,
    parent: Mapping[str, Any],
) -> TreeSnapshot:
    destination_tree.mkdir()
    tree = parent["tree"]
    directories = sorted(
        (str(record["path"]) for record in tree["directories"]),
        key=lambda relative: (len(Path(relative).parts), relative),
    )
    for relative in directories:
        (destination_tree / Path(relative)).mkdir()
    for relative, expected in sorted(_parent_records(parent).items()):
        if relative in OVERLAY_SOURCES:
            source = (
                LIFECYCLE_ROLLBACK_ROOT
                / str(OVERLAY_SOURCES[relative]["rollback_name"])
            )
        else:
            source = CURRENT_CANDIDATE_ROOT / Path(relative)
        payload = _stable_payload(
            source, max_bytes=max(int(expected["bytes"]), 1)
        )
        if (
            len(payload) != int(expected["bytes"])
            or _sha256(payload) != str(expected["sha256"])
        ):
            raise ActivationReplayError(
                f"selected source bytes drift: {relative}"
            )
        _write_exclusive(destination_tree / Path(relative), payload)
    snapshot = _scan_two_pass(destination_tree)
    _require_parent_logical_tree(snapshot, parent)
    return snapshot


def _manifest_document(
    *,
    captured_utc: str,
    authorization_hash: str,
    snapshot: TreeSnapshot,
) -> dict[str, Any]:
    _strict_utc(captured_utc, "capture timestamp")
    return _with_semantic_hash(
        {
            "schema_version": 1,
            "manifest_id": "nwiro-activation-parent-replay-v1",
            "role": "historical_static_replay_only",
            "evidence_class": "static",
            "captured_utc": captured_utc,
            "authorization": {
                "path": _path_text(AUTHORIZATION_PATH),
                "raw_sha256": authorization_hash,
            },
            "lineage": {
                "parent_activation_evidence": {
                    "path": _path_text(PARENT_EVIDENCE),
                    "raw_sha256": PARENT_EVIDENCE_SHA256,
                },
                "parent_candidate_manifest": {
                    "path": _path_text(PARENT_MANIFEST),
                    "raw_sha256": PARENT_MANIFEST_SHA256,
                },
                "parent_delta_manifest": {
                    "path": _path_text(PARENT_DELTA),
                    "raw_sha256": PARENT_DELTA_SHA256,
                },
                "lifecycle_evidence": {
                    "path": _path_text(LIFECYCLE_EVIDENCE),
                    "raw_sha256": LIFECYCLE_EVIDENCE_SHA256,
                },
                "lifecycle_candidate_manifest": {
                    "path": _path_text(LIFECYCLE_MANIFEST),
                    "raw_sha256": LIFECYCLE_MANIFEST_SHA256,
                },
                "lifecycle_delta_manifest": {
                    "path": _path_text(LIFECYCLE_DELTA),
                    "raw_sha256": LIFECYCLE_DELTA_SHA256,
                },
            },
            "reconstruction": {
                "parent_equal_files_from_advanced_candidate": 87,
                "pre_lifecycle_files_from_authenticated_rollback": 3,
                "overlay_paths": sorted(OVERLAY_SOURCES),
                "live_candidate_swapped": False,
                "publisher_created_link": False,
                "source_ancestor_path_atomicity_proven": False,
                "historical_physical_identity_recreated": False,
            },
            "tree": snapshot.semantic_payload(),
            "tree_semantic_sha256": _sha256(
                _canonical_file_bytes(snapshot.semantic_payload())
            ),
            "historical_source_assertion_count": len(SOURCE_TEST_METHODS),
            "historical_manifest_assertion_count": len(MANIFEST_TEST_METHODS),
            "candidate_static_accepted": False,
            "runtime_authorized": False,
            "build_authorized": False,
            "install_authorized": False,
            "unreal_launch_authorized": False,
            "mcp_initialize_authorized": False,
            "mcp_tool_call_authorized": False,
            "network_authorized": False,
            "provider_call_authorized": False,
            "asset_or_map_mutation_authorized": False,
            "power_loss_durability_proven": False,
            "claim_limit": (
                "Exact authenticated historical source bytes and logical tree "
                "only. Source-ancestor pathname atomicity and historical "
                "physical identities are not proven. This is not the current "
                "candidate, source acceptance, a build, an installation, a "
                "loaded plugin, MCP, provider, Unreal, asset, map, visual, "
                "gameplay, or runtime evidence."
            ),
        }
    )


def _verify_manifest(
    manifest: Mapping[str, Any],
    snapshot: TreeSnapshot,
    authorization_hash: str,
) -> None:
    captured_utc = _strict_utc(
        manifest.get("captured_utc"),
        "manifest capture timestamp",
    )
    expected = _manifest_document(
        captured_utc=captured_utc,
        authorization_hash=authorization_hash,
        snapshot=snapshot,
    )
    if dict(manifest) != expected:
        raise ActivationReplayError(
            "replay manifest differs from the exact reconstructed document"
        )


def _ensure_distinct_physical_tree(
    replay: TreeSnapshot,
    current: TreeSnapshot,
    replay_tree_root: Path,
) -> None:
    replay_records = _records(replay)
    current_records = _records(current)
    for relative in replay_records:
        left = replay_records[relative]
        right = current_records[relative]
        if (
            left["volume_serial_hex"],
            left["file_id_128_hex"],
        ) == (
            right["volume_serial_hex"],
            right["file_id_128_hex"],
        ):
            raise ActivationReplayError(
                f"replay aliases live candidate file identity: {relative}"
            )
    if _windows_identity(
        replay_tree_root,
        is_directory=True,
    ) == _windows_identity(CURRENT_CANDIDATE_ROOT, is_directory=True):
        raise ActivationReplayError("replay aliases live candidate root")


def _verify_bundle_at(
    *,
    bundle_root: Path,
    tree_root: Path,
    manifest_path: Path,
    boundary: Mapping[str, Any],
) -> tuple[TreeSnapshot, bytes]:
    """Verify a transaction or committed bundle against the final namespace."""

    _require_private_acl_tree(bundle_root)
    physical = _scan_two_pass(tree_root)
    _require_parent_logical_tree(physical, boundary["parent"])
    _ensure_distinct_physical_tree(
        physical,
        boundary["current"],
        tree_root,
    )
    logical = dataclasses.replace(physical, root=_path_text(OUTPUT_TREE))
    manifest_payload = _stable_payload(manifest_path, 4 * 1024 * 1024)
    manifest = load_json_bytes_strict(manifest_payload, str(manifest_path))
    if not isinstance(manifest, dict):
        raise ActivationReplayError("replay manifest must be a JSON object")
    if manifest_payload != _canonical_file_bytes(manifest):
        raise ActivationReplayError("replay manifest is not canonical")
    _verify_manifest(
        manifest,
        logical,
        boundary["authorization_hash"],
    )
    return physical, manifest_payload


def publish() -> dict[str, Any]:
    """Publish the fixed replay bundle once without deleting on failure."""

    if _lexists(OUTPUT_ROOT):
        raise ActivationReplayError(f"replay target exists: {OUTPUT_ROOT}")
    orphans = _reserved_orphans()
    if orphans:
        raise ActivationReplayError(
            f"orphan replay transaction blocks publication: {orphans[0]}"
        )
    boundary = _authenticate_inputs()
    transaction = STAGING_PARENT / f"{_TRANSACTION_PREFIX}{uuid.uuid4().hex}"
    if _lexists(transaction):
        raise ActivationReplayError("transaction name collision")
    transaction.mkdir()
    _apply_private_acl(transaction, _current_token_sid())
    transaction_tree = transaction / "tree"
    before_current = boundary["current"]
    before_rollback = boundary["rollback"]
    transaction_snapshot = _copy_parent_tree(
        transaction_tree, boundary["parent"]
    )
    final_snapshot = dataclasses.replace(
        transaction_snapshot, root=_path_text(OUTPUT_TREE)
    )
    captured_utc = (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    manifest = _manifest_document(
        captured_utc=captured_utc,
        authorization_hash=boundary["authorization_hash"],
        snapshot=final_snapshot,
    )
    _write_exclusive(
        transaction / "replay.v1.json",
        _canonical_file_bytes(manifest),
    )
    _seal_private_acl(transaction)
    if _scan_two_pass(CURRENT_CANDIDATE_ROOT) != before_current:
        raise ActivationReplayError("advanced candidate changed during publication")
    if _scan_two_pass(LIFECYCLE_ROLLBACK_ROOT) != before_rollback:
        raise ActivationReplayError("lifecycle rollback changed during publication")
    transaction_identity = _windows_identity(
        transaction,
        is_directory=True,
    )
    transaction_verified, transaction_manifest_payload = _verify_bundle_at(
        bundle_root=transaction,
        tree_root=transaction_tree,
        manifest_path=transaction / "replay.v1.json",
        boundary=boundary,
    )
    _move_no_clobber(transaction, OUTPUT_ROOT)
    if _windows_identity(OUTPUT_ROOT, is_directory=True) != transaction_identity:
        raise ActivationReplayError(
            "published bundle identity differs from verified transaction"
        )
    committed = _scan_two_pass(OUTPUT_TREE)
    if dataclasses.replace(
        committed,
        root=transaction_verified.root,
    ) != transaction_verified:
        raise ActivationReplayError(
            "published tree differs from verified transaction"
        )
    if (
        _stable_payload(OUTPUT_MANIFEST, 4 * 1024 * 1024)
        != transaction_manifest_payload
    ):
        raise ActivationReplayError(
            "published manifest differs from verified transaction"
        )
    result = verify()
    result["published"] = True
    return result


def verify() -> dict[str, Any]:
    """Verify the fixed replay, its private ACL, and all source lineage."""

    if not OUTPUT_ROOT.is_dir() or not OUTPUT_TREE.is_dir():
        raise ActivationReplayError("replay bundle is absent")
    if _reserved_orphans():
        raise ActivationReplayError("orphan replay transaction exists")
    boundary = _authenticate_inputs()
    replay, manifest_payload = _verify_bundle_at(
        bundle_root=OUTPUT_ROOT,
        tree_root=OUTPUT_TREE,
        manifest_path=OUTPUT_MANIFEST,
        boundary=boundary,
    )
    manifest = load_json_bytes_strict(
        manifest_payload,
        str(OUTPUT_MANIFEST),
    )
    return {
        "result": "verified",
        "published": False,
        "bundle_root": _path_text(OUTPUT_ROOT),
        "tree_root": _path_text(OUTPUT_TREE),
        "tree_file_count": replay.file_count,
        "tree_directory_count": replay.directory_count_excluding_root,
        "tree_total_bytes": replay.total_bytes,
        "tree_record_set_sha256": replay.record_set_sha256,
        "tree_topology_sha256": replay.topology_sha256,
        "manifest_raw_sha256": _sha256(manifest_payload),
        "manifest_semantic_sha256": manifest[
            "manifest_semantic_sha256"
        ],
        "private_acl_verified": True,
        "live_candidate_unchanged": True,
        "protected_inputs_unchanged": True,
        "runtime_authorized": False,
    }


def _method_names(case: type[unittest.TestCase]) -> tuple[str, ...]:
    return tuple(unittest.TestLoader().getTestCaseNames(case))


def _require_fresh_historical_modules() -> None:
    exact_names = set(HISTORICAL_PACKAGE_MODULES) | set(HISTORICAL_MODULES)
    preloaded = sorted(name for name in exact_names if name in sys.modules)
    if preloaded:
        raise ActivationReplayError(
            "historical replay requires a fresh interpreter; preloaded module: "
            f"{preloaded[0]}"
        )


def _exec_authenticated_module(
    name: str,
    path: Path,
    expected_sha256: str,
    *,
    is_package: bool = False,
) -> Any:
    """Compile exact authenticated source bytes without consulting a pyc."""

    payload = _authenticated_bytes(path, expected_sha256)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = name if is_package else name.rpartition(".")[0]
    if is_package:
        module.__path__ = [str(path.parent)]
    sys.modules[name] = module
    try:
        code = compile(
            payload,
            str(path),
            "exec",
            dont_inherit=True,
        )
        exec(code, module.__dict__)
    except Exception:
        if sys.modules.get(name) is module:
            sys.modules.pop(name, None)
        raise
    return module


def _require_module_binding(
    name: str,
    module: Any,
    path: Path,
    expected_sha256: str,
) -> None:
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        raise ActivationReplayError(f"historical module lacks __file__: {name}")
    if Path(module_file).resolve(strict=True) != path.resolve(strict=True):
        raise ActivationReplayError(f"historical module path drift: {name}")
    _authenticated_bytes(path, expected_sha256)


@contextlib.contextmanager
def _fresh_historical_imports():
    """Execute authenticated source modules from retained exact files."""

    if Path.cwd().resolve(strict=True) != PROJECT_ROOT.resolve(strict=True):
        raise ActivationReplayError(
            "historical replay must run from the exact project root"
        )
    _require_fresh_historical_modules()
    original_sys_path = list(sys.path)
    project_key = _path_text(PROJECT_ROOT).casefold()
    tools_key = _path_text(_TOOLS_DIR).casefold()
    sanitized: list[str] = [str(PROJECT_ROOT)]
    for entry in original_sys_path:
        if not entry:
            continue
        key = _path_text(Path(entry)).casefold()
        if key in {project_key, tools_key}:
            continue
        sanitized.append(entry)
    imported: dict[str, Any] = {}
    try:
        sys.path[:] = sanitized
        for name, (path, digest) in HISTORICAL_PACKAGE_MODULES.items():
            imported[name] = _exec_authenticated_module(
                name,
                path,
                digest,
                is_package=True,
            )
        load_order = (
            "Tools.audit_nwiro_restricted_probe_source",
            "Tools.generate_redmmo_nwiro_activation_ownership_manifests",
            "Tools.tests.test_redmmo_nwiro_activation_ownership_source",
            "Tools.tests.test_generate_redmmo_nwiro_activation_ownership_manifests",
        )
        for name in load_order:
            path, digest = HISTORICAL_MODULES[name]
            imported[name] = _exec_authenticated_module(
                name,
                path,
                digest,
            )
            parent_name, _, child_name = name.rpartition(".")
            parent = imported.get(parent_name)
            if parent is not None:
                setattr(parent, child_name, imported[name])
        for name, (path, digest) in HISTORICAL_MODULES.items():
            _require_module_binding(name, imported[name], path, digest)
        for name, (path, digest) in HISTORICAL_PACKAGE_MODULES.items():
            _require_module_binding(name, imported[name], path, digest)
        source_test = imported[
            "Tools.tests.test_redmmo_nwiro_activation_ownership_source"
        ]
        manifest_test = imported[
            "Tools.tests.test_generate_redmmo_nwiro_activation_ownership_manifests"
        ]
        generator = imported[
            "Tools.generate_redmmo_nwiro_activation_ownership_manifests"
        ]
        if getattr(manifest_test, "sut", None) is not generator:
            raise ActivationReplayError(
                "historical manifest test is not bound to exact generator"
            )
        audit = imported["Tools.audit_nwiro_restricted_probe_source"]
        if (
            getattr(source_test, "_extract_function", None)
            is not getattr(audit, "_extract_function", None)
            or getattr(source_test, "_mask_cpp_noncode", None)
            is not getattr(audit, "_mask_cpp_noncode", None)
        ):
            raise ActivationReplayError(
                "historical source test helper binding drift"
            )
        scan_module = sys.modules.get(
            "create_redmmo_nwiro_restricted_probe_candidate"
        )
        contract_module = sys.modules.get(
            "validate_redmmo_nwiro_restricted_probe_candidate_contract"
        )
        if scan_module is None or contract_module is None:
            raise ActivationReplayError("publisher helper module missing")
        _require_module_binding(
            scan_module.__name__,
            scan_module,
            SCAN_HELPER,
            SCAN_HELPER_SHA256,
        )
        _require_module_binding(
            contract_module.__name__,
            contract_module,
            CONTRACT_HELPER,
            CONTRACT_HELPER_SHA256,
        )
        if getattr(generator, "_scan_two_pass", None) is not getattr(
            scan_module,
            "_scan_two_pass",
            None,
        ):
            raise ActivationReplayError(
                "historical generator scan-helper binding drift"
            )
        yield source_test, manifest_test, generator
    finally:
        try:
            for name, module in imported.items():
                if name in HISTORICAL_MODULES:
                    path, digest = HISTORICAL_MODULES[name]
                else:
                    path, digest = HISTORICAL_PACKAGE_MODULES[name]
                _require_module_binding(name, module, path, digest)
        finally:
            sys.path[:] = original_sys_path
            for name, module in reversed(tuple(imported.items())):
                if sys.modules.get(name) is module:
                    sys.modules.pop(name, None)


def _historical_lock_paths() -> list[Path]:
    fixed = [
        OUTPUT_MANIFEST,
        AUTHORIZATION_PATH,
        PARENT_EVIDENCE,
        LIFECYCLE_EVIDENCE,
        PARENT_MANIFEST,
        PARENT_DELTA,
        LIFECYCLE_MANIFEST,
        LIFECYCLE_DELTA,
        HISTORICAL_SOURCE_TEST,
        HISTORICAL_MANIFEST_TEST,
        HISTORICAL_GENERATOR,
        AUDIT_HELPER,
        SCAN_HELPER,
        CONTRACT_HELPER,
        TOOLS_PACKAGE_INIT,
        TOOLS_TESTS_PACKAGE_INIT,
        ACTIVATION_AUTHORIZATION,
        *PROTECTED_INPUTS,
        *[
            ACTIVATION_ROLLBACK_ROOT / Path(relative)
            for relative in sorted(ACTIVATION_ROLLBACK_FILES)
        ],
        HISTORICAL_BASELINE_MANIFEST,
        HISTORICAL_CANDIDATE_MANIFEST,
        HISTORICAL_DELTA_MANIFEST,
    ]
    fixed.extend(path for path in _all_paths(OUTPUT_TREE) if path.is_file())
    unique: dict[str, Path] = {}
    for path in fixed:
        unique.setdefault(_path_text(path).casefold(), path)
    return list(unique.values())


def run_historical_replay() -> dict[str, Any]:
    """Run the unchanged 16+6 historical assertions against the replay."""

    verify()
    post_verified: dict[str, Any] | None = None
    proxy_counts = {"candidate": 0, "rollback": 0}
    module_source_paths = [
        path
        for path, _ in (
            *HISTORICAL_PACKAGE_MODULES.values(),
            *HISTORICAL_MODULES.values(),
        )
    ]
    with _held_read_locks(
        module_source_paths
    ), _fresh_historical_imports() as (
        source_test,
        manifest_test,
        generator,
    ):
        source_case = source_test.NwiroActivationOwnershipSourceTests
        manifest_case = manifest_test.NwiroActivationOwnershipManifestTests
        if _method_names(source_case) != SOURCE_TEST_METHODS:
            raise ActivationReplayError("historical source test method drift")
        if _method_names(manifest_case) != MANIFEST_TEST_METHODS:
            raise ActivationReplayError("historical manifest test method drift")

        with _held_read_locks(_historical_lock_paths()):
            verify()
            before_current = _scan_two_pass(CURRENT_CANDIDATE_ROOT)
            before_rollback = _scan_two_pass(LIFECYCLE_ROLLBACK_ROOT)
            before_replay = _scan_two_pass(OUTPUT_TREE)
            original_source_root = source_test.CANDIDATE_ROOT
            original_scan = generator._scan_two_pass
            generator_candidate = generator.CANDIDATE_ROOT
            generator_rollback = Path(
                generator._read_authenticated_json(
                    generator.AUTHORIZATION,
                    generator.AUTHORIZATION_SHA256,
                )["rollback_root"]
            )

            def exact_scan_proxy(path: Path) -> TreeSnapshot:
                candidate = _path_text(Path(path)).casefold()
                if candidate == _path_text(generator_candidate).casefold():
                    proxy_counts["candidate"] += 1
                    observed = _scan_two_pass(OUTPUT_TREE)
                    _require_parent_logical_tree(
                        observed,
                        _authenticated_json(
                            PARENT_MANIFEST,
                            PARENT_MANIFEST_SHA256,
                        ),
                    )
                    return dataclasses.replace(
                        observed,
                        root=generator_candidate.as_posix(),
                    )
                if candidate == _path_text(generator_rollback).casefold():
                    proxy_counts["rollback"] += 1
                    return original_scan(generator_rollback)
                raise ActivationReplayError(
                    f"historical scan proxy refused unexpected path: {path}"
                )

            suite = unittest.TestSuite()
            for method in SOURCE_TEST_METHODS:
                suite.addTest(source_case(method))
            for method in MANIFEST_TEST_METHODS:
                suite.addTest(manifest_case(method))
            stream = io.StringIO()
            try:
                source_test.CANDIDATE_ROOT = OUTPUT_TREE
                generator._scan_two_pass = exact_scan_proxy
                result = unittest.TextTestRunner(
                    stream=stream,
                    verbosity=2,
                    failfast=False,
                ).run(suite)
            finally:
                source_test.CANDIDATE_ROOT = original_source_root
                generator._scan_two_pass = original_scan

            output = stream.getvalue()
            sys.stdout.write(output)
            if source_test.CANDIDATE_ROOT != original_source_root:
                raise ActivationReplayError(
                    "historical source root was not restored"
                )
            if generator._scan_two_pass is not original_scan:
                raise ActivationReplayError(
                    "historical scan function was not restored"
                )
            if proxy_counts != {"candidate": 4, "rollback": 4}:
                raise ActivationReplayError(
                    f"historical scan proxy call-count drift: {proxy_counts}"
                )
            if _scan_two_pass(CURRENT_CANDIDATE_ROOT) != before_current:
                raise ActivationReplayError(
                    "advanced candidate changed during replay"
                )
            if _scan_two_pass(LIFECYCLE_ROLLBACK_ROOT) != before_rollback:
                raise ActivationReplayError(
                    "lifecycle rollback changed during replay"
                )
            if _scan_two_pass(OUTPUT_TREE) != before_replay:
                raise ActivationReplayError(
                    "replay tree changed during assertions"
                )
            if (
                result.testsRun != 22
                or result.failures
                or result.errors
                or result.skipped
                or result.expectedFailures
                or result.unexpectedSuccesses
            ):
                raise ActivationReplayError(
                    "historical replay did not pass exactly 22/22"
                )
            post_verified = verify()
    if post_verified is None:
        raise ActivationReplayError("historical replay postflight was not reached")
    return {
        **post_verified,
        "result": "historical_replay_passed",
        "historical_tests_run": result.testsRun,
        "historical_tests_passed": result.testsRun,
        "historical_tests_failed": 0,
        "historical_tests_errored": 0,
        "historical_tests_skipped": 0,
        "in_memory_root_override_restored": True,
        "scan_proxy_restored": True,
        "fresh_authenticated_imports_verified": True,
        "held_read_locks_used": True,
        "scan_proxy_candidate_calls": proxy_counts["candidate"],
        "scan_proxy_rollback_calls": proxy_counts["rollback"],
        "full_postflight_verified": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--publish", action="store_true")
    group.add_argument("--verify", action="store_true")
    group.add_argument("--run-replay", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.publish:
            report = publish()
        elif args.verify:
            report = verify()
        else:
            report = run_historical_replay()
    except (
        ActivationReplayError,
        CandidateCreationError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        print(
            json.dumps(
                {"result": "refused", "error": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
