#!/usr/bin/env python3
"""Execute the activation replay only from its reviewed private bootstrap.

This file is review material while it lives in the project tree.  It MUST NOT
be executed from here.  A separately authorized coordinator must copy these
exact bytes and the exact authenticated execution graph from same retained
read handles into the fixed private bundle, publish that bundle no-clobber,
and launch only the sealed copy with an independently pinned interpreter:

    python.exe -I -S -B <sealed launcher> <one exact mode>

The launcher has no generic module/path/code arguments.  It authenticates the
complete fixed graph before the first project compile/exec, compiles captured
bytes directly (never a pyc), verifies helper object bindings, and keeps every
source handle read-only/no-delete until the publisher entry point returns.
"""

from __future__ import annotations

import base64
import contextlib
import ctypes
import hashlib
import importlib
import json
import msvcrt
import os
import stat
import subprocess
import sys
import types
from ctypes import wintypes
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


SEALED_ROOT = Path(
    r"D:\RedMMOTitanWindowsData\Staging"
    r"\NwiroActivationReplayBootstrapV1"
)
SEALED_LAUNCHER = SEALED_ROOT / "bootstrap.py"
SEALED_AUTHORIZATION = SEALED_ROOT / "bootstrap_authorization.v1.json"

PROJECT_ROOT = Path(r"D:\RedMMOTitan")
PROJECT_PUBLISHER = (
    PROJECT_ROOT / "Tools" / "create_redmmo_nwiro_activation_replay.py"
)
PROJECT_CREATOR = (
    PROJECT_ROOT
    / "Tools"
    / "create_redmmo_nwiro_restricted_probe_candidate.py"
)
PROJECT_CONTRACT = (
    PROJECT_ROOT
    / "Tools"
    / "validate_redmmo_nwiro_restricted_probe_candidate_contract.py"
)
PROJECT_PUBLISHER_TEST = (
    PROJECT_ROOT
    / "Tools"
    / "tests"
    / "test_create_redmmo_nwiro_activation_replay.py"
)
PROJECT_REPLAY_AUTHORIZATION = (
    PROJECT_ROOT
    / "Build"
    / "Automation"
    / "redmmo_nwiro_activation_replay_execution_authorization_v1.json"
)

GRAPH: tuple[tuple[str, str, Path, str, int], ...] = (
    (
        "contract",
        "contract.py",
        PROJECT_CONTRACT,
        "A829BC5E131BA7812E1F003F2BEA3E684D6DCA2D7CFEFAFC5048502BCBBE3B02",
        53_011,
    ),
    (
        "creator",
        "creator.py",
        PROJECT_CREATOR,
        "28BCF5F28CB94C136355536D9E1386E21895BA597F857CC2E892E6CB336AC47E",
        77_039,
    ),
    (
        "publisher",
        "publisher.py",
        PROJECT_PUBLISHER,
        "C4D718666C602CB981C4603A8D621FD34BAFBEF64E93E2D48773C6921AB6D1BA",
        73_579,
    ),
    (
        "publisher_test",
        "publisher_test.py",
        PROJECT_PUBLISHER_TEST,
        "8C563D619937D4EF993B9A40AFCA780DC1BC93819A5E321BBB147150F102BDF9",
        9_971,
    ),
    (
        "replay_authorization",
        "replay_authorization.v1.json",
        PROJECT_REPLAY_AUTHORIZATION,
        "E72E8426A1F9DD35326F3259B359C6460BD584B9F0B889AFE142D0942074410A",
        7_699,
    ),
)

MODULE_NAMES = (
    "validate_redmmo_nwiro_restricted_probe_candidate_contract",
    "create_redmmo_nwiro_restricted_probe_candidate",
    "create_redmmo_nwiro_activation_replay",
)
ALLOWED_MODES = ("--publish", "--verify", "--run-replay")
EXPECTED_BUNDLE_NAMES = frozenset(
    {
        "bootstrap.py",
        "bootstrap_authorization.v1.json",
        *(sealed_name for _, sealed_name, _, _, _ in GRAPH),
    }
)
MAX_SOURCE_BYTES = 32 * 1024 * 1024

_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
_FILE_ATTRIBUTE_TAG_INFO = 9
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_ICACLS_FULL_CONTROL = 2_032_127


class BootstrapRefusal(RuntimeError):
    """The private authenticated bootstrap contract was not satisfied."""


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", wintypes.DWORD),
        ("ReparseTag", wintypes.DWORD),
    ]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _path_text(path: Path) -> str:
    return os.path.abspath(str(path)).replace("\\", "/")


def _is_reparse(info: os.stat_result) -> bool:
    return bool(
        getattr(info, "st_file_attributes", 0)
        & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _reject_reparse_chain(path: Path) -> None:
    current = Path(os.path.abspath(str(path)))
    chain: list[Path] = []
    while True:
        chain.append(current)
        if current.parent == current:
            break
        current = current.parent
    for ancestor in reversed(chain):
        info = ancestor.stat(follow_symlinks=False)
        if ancestor.is_symlink() or _is_reparse(info):
            raise BootstrapRefusal(
                f"link/reparse ancestor refused: {ancestor}"
            )


def _named_alternate_streams(path: Path) -> tuple[str, ...]:
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
    invalid = wintypes.HANDLE(-1).value
    if handle == invalid:
        error = ctypes.get_last_error()
        if error == 38:
            return ()
        raise BootstrapRefusal(
            f"stream enumeration failed for {path}: Win32 error {error}"
        )
    names: list[str] = []
    try:
        while True:
            if data.stream_name != "::$DATA":
                names.append(data.stream_name)
            if not find_next(handle, ctypes.byref(data)):
                error = ctypes.get_last_error()
                if error != 38:
                    raise BootstrapRefusal(
                        f"stream enumeration changed for {path}: "
                        f"Win32 error {error}"
                    )
                break
    finally:
        find_close(handle)
    return tuple(names)


def _get_system_directory() -> Path:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_system_directory = kernel32.GetSystemDirectoryW
    get_system_directory.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    get_system_directory.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32_768)
    length = get_system_directory(buffer, len(buffer))
    if length == 0 or length >= len(buffer):
        raise BootstrapRefusal("GetSystemDirectoryW failed")
    path = Path(buffer.value)
    _reject_reparse_chain(path)
    return path


def _get_windows_directory() -> Path:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_windows_directory = kernel32.GetWindowsDirectoryW
    get_windows_directory.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    get_windows_directory.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32_768)
    length = get_windows_directory(buffer, len(buffer))
    if length == 0 or length >= len(buffer):
        raise BootstrapRefusal("GetWindowsDirectoryW failed")
    path = Path(buffer.value)
    _reject_reparse_chain(path)
    return path


def _all_bundle_paths() -> list[Path]:
    _reject_reparse_chain(SEALED_ROOT)
    root_info = SEALED_ROOT.stat(follow_symlinks=False)
    if (
        SEALED_ROOT.is_symlink()
        or _is_reparse(root_info)
        or not stat.S_ISDIR(root_info.st_mode)
        or getattr(root_info, "st_nlink", 1) != 1
    ):
        raise BootstrapRefusal("sealed root is linked or invalid")
    entries = sorted(
        list(os.scandir(SEALED_ROOT)),
        key=lambda entry: entry.name.casefold(),
    )
    folded = [entry.name.casefold() for entry in entries]
    if len(folded) != len(set(folded)):
        raise BootstrapRefusal("case-colliding sealed entry")
    if {entry.name for entry in entries} != EXPECTED_BUNDLE_NAMES:
        raise BootstrapRefusal("sealed inventory drift")
    paths = [SEALED_ROOT]
    for entry in entries:
        path = Path(entry.path)
        info = path.stat(follow_symlinks=False)
        if (
            path.is_symlink()
            or _is_reparse(info)
            or not stat.S_ISREG(info.st_mode)
            or getattr(info, "st_nlink", 1) != 1
        ):
            raise BootstrapRefusal(f"unsafe sealed entry: {path}")
        if _named_alternate_streams(path):
            raise BootstrapRefusal(f"alternate stream refused: {path}")
        paths.append(path)
    return paths


def _require_exact_private_acl(paths: Sequence[Path]) -> str:
    system32 = _get_system_directory()
    powershell = (
        system32
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    _reject_reparse_chain(powershell)
    encoded_paths = base64.b64encode(
        json.dumps(
            [_path_text(path) for path in paths],
            separators=(",", ":"),
        ).encode("utf-8")
    ).decode("ascii")
    script = r"""
$ErrorActionPreference = 'Stop'
$paths = [Text.Encoding]::UTF8.GetString(
  [Convert]::FromBase64String('__PATHS__')
) | ConvertFrom-Json
$current = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rows = foreach ($path in $paths) {
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
[pscustomobject]@{ current_sid = $current; rows = @($rows) } |
  ConvertTo-Json -Depth 7 -Compress
""".replace("__PATHS__", encoded_paths)
    encoded_script = base64.b64encode(
        script.encode("utf-16-le")
    ).decode("ascii")
    completed = subprocess.run(
        [
            str(powershell),
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
        errors="strict",
        timeout=30,
        env={
            "SystemRoot": str(_get_windows_directory()),
            "WINDIR": str(_get_windows_directory()),
        },
    )
    if completed.returncode != 0:
        raise BootstrapRefusal("private ACL inspection failed")
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise BootstrapRefusal("private ACL report malformed") from exc
    if not isinstance(report, dict):
        raise BootstrapRefusal("private ACL report envelope malformed")
    current_sid = report.get("current_sid")
    rows = report.get("rows")
    if not isinstance(current_sid, str) or not isinstance(rows, list):
        raise BootstrapRefusal("private ACL identity malformed")
    allowed = {current_sid, "S-1-5-18", "S-1-5-32-544"}
    expected_paths = {_path_text(path).casefold() for path in paths}
    observed_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise BootstrapRefusal("private ACL row malformed")
        observed_paths.add(
            _path_text(Path(str(row.get("path")))).casefold()
        )
        if row.get("protected") is not True:
            raise BootstrapRefusal("ACL inheritance remains enabled")
        if row.get("owner") not in {current_sid, "S-1-5-32-544"}:
            raise BootstrapRefusal("private ACL owner drift")
        rules = row.get("rules")
        if not isinstance(rules, list) or len(rules) != 3:
            raise BootstrapRefusal("private ACL rule-count drift")
        rule_sids: set[str] = set()
        for rule in rules:
            if not isinstance(rule, dict):
                raise BootstrapRefusal("private ACL rule malformed")
            sid = rule.get("sid")
            if sid not in allowed or sid in rule_sids:
                raise BootstrapRefusal("private ACL principal drift")
            rule_sids.add(str(sid))
            if (
                rule.get("rights") != _ICACLS_FULL_CONTROL
                or rule.get("type") != "Allow"
                or rule.get("inherited") is not False
            ):
                raise BootstrapRefusal("private ACL permission drift")
        if rule_sids != allowed:
            raise BootstrapRefusal("private ACL allowlist incomplete")
    if observed_paths != expected_paths:
        raise BootstrapRefusal("private ACL path coverage drift")
    return current_sid


@contextlib.contextmanager
def _locked_payload(path: Path, max_bytes: int = MAX_SOURCE_BYTES) -> Iterator[bytes]:
    _reject_reparse_chain(path.parent)
    before = path.stat(follow_symlinks=False)
    if (
        path.is_symlink()
        or _is_reparse(before)
        or not stat.S_ISREG(before.st_mode)
        or getattr(before, "st_nlink", 1) != 1
        or before.st_size <= 0
        or before.st_size > max_bytes
        or _named_alternate_streams(path)
    ):
        raise BootstrapRefusal(f"unsafe locked input: {path}")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    get_info = kernel32.GetFileInformationByHandleEx
    get_info.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    get_info.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
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
        raise BootstrapRefusal(
            f"retained read open failed for {path}: "
            f"{ctypes.get_last_error()}"
        )
    fd: int | None = None
    stream = None
    try:
        tag = _FileAttributeTagInfo()
        if not get_info(
            handle,
            _FILE_ATTRIBUTE_TAG_INFO,
            ctypes.byref(tag),
            ctypes.sizeof(tag),
        ):
            raise BootstrapRefusal(f"locked attribute query failed: {path}")
        if tag.FileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise BootstrapRefusal(f"locked reparse input refused: {path}")
        fd = msvcrt.open_osfhandle(
            int(handle),
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
        handle = None
        stream = os.fdopen(fd, "rb", closefd=True)
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
            raise BootstrapRefusal(f"locked identity drift: {path}")
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
            raise BootstrapRefusal(f"locked input changed: {path}")
        if len(payload) != opened.st_size:
            raise BootstrapRefusal(f"locked input length drift: {path}")
        yield payload
    finally:
        if stream is not None:
            stream.close()
        elif fd is not None:
            os.close(fd)
        elif handle not in (None, _INVALID_HANDLE_VALUE):
            close_handle(handle)


def _canonical_json(payload: bytes, label: str) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
        value = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapRefusal(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise BootstrapRefusal(f"{label} must be a JSON object")
    canonical = (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    if payload != canonical:
        raise BootstrapRefusal(f"{label} is not canonical JSON plus LF")
    return value


def _expected_authorization(
    launcher_payload: bytes,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "authorization_id": (
            "redmmo.m07.nwiro.activation-replay-private-bootstrap-v1"
        ),
        "status": "approved_once_offline_bootstrap_only",
        "bootstrap_root": _path_text(SEALED_ROOT),
        "launcher": {
            "sealed_path": _path_text(SEALED_LAUNCHER),
            "bytes": len(launcher_payload),
            "sha256": _sha256(launcher_payload),
        },
        "graph": [
            {
                "role": role,
                "sealed_path": _path_text(SEALED_ROOT / sealed_name),
                "project_path": _path_text(project_path),
                "bytes": expected_bytes,
                "sha256": expected_sha256,
                "execute": role in {"contract", "creator", "publisher"},
            }
            for (
                role,
                sealed_name,
                project_path,
                expected_sha256,
                expected_bytes,
            ) in GRAPH
        ],
        "allowed_modes": list(ALLOWED_MODES),
        "authorities": {
            "private_bootstrap_publication_authorized": True,
            "sealed_graph_execution_authorized": True,
            "parent_replay_publication_authorized": True,
            "historical_offline_replay_authorized": True,
            "source_mutation_authorized": False,
            "build_authorized": False,
            "install_authorized": False,
            "unreal_launch_authorized": False,
            "mcp_or_network_authorized": False,
            "provider_authorized": False,
            "asset_or_map_mutation_authorized": False,
        },
        "execution": {
            "python_flags": ["-I", "-S", "-B"],
            "fixed_modes_only": True,
            "project_graph_pyc_not_read_or_written": True,
            "project_graph_loaded_only_from_authenticated_source_bytes": True,
            "sealed_and_project_copies_retained_and_byte_equal": True,
            "retained_handles_until_entrypoint_return": True,
        },
        "rollback": {
            "bootstrap_target_overwrite_authorized": False,
            "replay_target_overwrite_authorized": False,
            "recursive_cleanup_authorized": False,
            "owned_orphan_preserved_on_failure": True,
        },
    }


def _require_process_isolation(argv: Sequence[str]) -> str:
    if os.name != "nt":
        raise BootstrapRefusal("Windows is required")
    if not (
        sys.flags.isolated == 1
        and sys.flags.no_site == 1
        and sys.flags.dont_write_bytecode == 1
        and getattr(sys.flags, "safe_path", False)
    ):
        raise BootstrapRefusal("python -I -S -B is required")
    if len(argv) != 1 or argv[0] not in ALLOWED_MODES:
        raise BootstrapRefusal("one exact bootstrap mode is required")
    if os.path.normcase(os.path.abspath(__file__)) != os.path.normcase(
        os.path.abspath(str(SEALED_LAUNCHER))
    ):
        raise BootstrapRefusal("launcher is not the fixed sealed copy")
    if Path.cwd().resolve(strict=True) != SEALED_ROOT.resolve(strict=True):
        raise BootstrapRefusal("interpreter must start in the private root")
    unsafe_path_keys = {
        _path_text(PROJECT_ROOT).casefold(),
        _path_text(PROJECT_ROOT / "Tools").casefold(),
        _path_text(SEALED_ROOT).casefold(),
    }
    for entry in sys.path:
        if not entry:
            continue
        if _path_text(Path(entry)).casefold() in unsafe_path_keys:
            raise BootstrapRefusal("unsafe project/bootstrap import path")
    preloaded = [name for name in MODULE_NAMES if name in sys.modules]
    if preloaded:
        raise BootstrapRefusal(
            f"project module preloaded: {sorted(preloaded)[0]}"
        )
    return argv[0]


def _preload_stdlib() -> None:
    names = (
        "argparse",
        "base64",
        "contextlib",
        "ctypes",
        "ctypes.wintypes",
        "dataclasses",
        "datetime",
        "hashlib",
        "io",
        "json",
        "math",
        "msvcrt",
        "os",
        "pathlib",
        "re",
        "secrets",
        "stat",
        "subprocess",
        "sys",
        "types",
        "typing",
        "unicodedata",
        "unittest",
        "uuid",
    )
    for name in names:
        importlib.import_module(name)


def _exec_module(name: str, payload: bytes, project_path: Path) -> types.ModuleType:
    if name in sys.modules:
        raise BootstrapRefusal(f"module binding already exists: {name}")
    module = types.ModuleType(name)
    module.__file__ = str(project_path)
    module.__package__ = ""
    module.__cached__ = None
    sys.modules[name] = module
    try:
        code = compile(
            payload,
            str(project_path),
            "exec",
            dont_inherit=True,
        )
        exec(code, module.__dict__)
    except Exception:
        if sys.modules.get(name) is module:
            sys.modules.pop(name, None)
        raise
    return module


def _require_bindings(
    contract: types.ModuleType,
    creator: types.ModuleType,
    publisher: types.ModuleType,
) -> None:
    creator_contract_names = (
        "CandidateContractError",
        "_hash_stable_regular_file",
        "_is_reparse",
        "_named_alternate_streams",
        "_read_stable_regular_file",
        "_validate_existing_ancestor_chain",
        "authenticate_plugin_tree_two_pass",
        "canonical_json_bytes",
        "load_json_bytes_strict",
        "validate_contract_file",
        "validate_contract_schema",
    )
    for name in creator_contract_names:
        if getattr(creator, name, None) is not getattr(contract, name, None):
            raise BootstrapRefusal(
                f"creator contract-helper binding drift: {name}"
            )
    publisher_creator_names = (
        "CandidateCreationError",
        "TreeSnapshot",
        "_canonical_file_bytes",
        "_current_token_sid",
        "_lexists",
        "_move_no_clobber",
        "_scan_two_pass",
        "_write_exclusive",
        "_windows_identity",
    )
    for name in publisher_creator_names:
        if getattr(publisher, name, None) is not getattr(creator, name, None):
            raise BootstrapRefusal(
                f"publisher creator-helper binding drift: {name}"
            )
    publisher_contract_names = (
        "_is_reparse",
        "_named_alternate_streams",
        "_validate_existing_ancestor_chain",
        "load_json_bytes_strict",
    )
    for name in publisher_contract_names:
        if getattr(publisher, name, None) is not getattr(contract, name, None):
            raise BootstrapRefusal(
                f"publisher contract-helper binding drift: {name}"
            )


def _run(argv: Sequence[str]) -> int:
    mode = _require_process_isolation(argv)
    bundle_paths = _all_bundle_paths()
    current_sid = _require_exact_private_acl(
        [SEALED_ROOT.parent, *bundle_paths]
    )

    graph_by_role = {row[0]: row for row in GRAPH}
    original_sys_path = list(sys.path)
    owned_modules: list[tuple[str, types.ModuleType]] = []
    with contextlib.ExitStack() as stack:
        launcher_payload = stack.enter_context(
            _locked_payload(SEALED_LAUNCHER)
        )
        authorization_payload = stack.enter_context(
            _locked_payload(SEALED_AUTHORIZATION, 256 * 1024)
        )
        authorization = _canonical_json(
            authorization_payload,
            "bootstrap authorization",
        )
        if authorization != _expected_authorization(launcher_payload):
            raise BootstrapRefusal("bootstrap authorization drift")

        sealed_payloads: dict[str, bytes] = {}
        project_payloads: dict[str, bytes] = {}
        for (
            role,
            sealed_name,
            project_path,
            expected_sha256,
            expected_bytes,
        ) in GRAPH:
            sealed_payload = stack.enter_context(
                _locked_payload(SEALED_ROOT / sealed_name)
            )
            project_payload = stack.enter_context(
                _locked_payload(project_path)
            )
            if (
                len(sealed_payload) != expected_bytes
                or _sha256(sealed_payload) != expected_sha256
                or project_payload != sealed_payload
            ):
                raise BootstrapRefusal(
                    f"sealed/project graph drift: {role}"
                )
            sealed_payloads[role] = sealed_payload
            project_payloads[role] = project_payload

        replay_authorization = _canonical_json(
            project_payloads["replay_authorization"],
            "replay authorization",
        )
        publisher_binding = replay_authorization.get("publisher")
        test_binding = replay_authorization.get("publisher_tests")
        if (
            not isinstance(publisher_binding, dict)
            or publisher_binding.get("sha256")
            != graph_by_role["publisher"][3]
            or publisher_binding.get("bytes")
            != graph_by_role["publisher"][4]
            or not isinstance(test_binding, dict)
            or test_binding.get("sha256")
            != graph_by_role["publisher_test"][3]
            or test_binding.get("bytes")
            != graph_by_role["publisher_test"][4]
        ):
            raise BootstrapRefusal("replay authorization graph drift")

        # SystemRoot is derived from GetWindowsDirectoryW, never inherited.
        windows_directory = _get_windows_directory()
        os.environ.clear()
        os.environ.update(
            {
                "SystemRoot": str(windows_directory),
                "WINDIR": str(windows_directory),
            }
        )
        _preload_stdlib()
        try:
            # The authenticated modules resolve every project dependency from
            # the exact objects below, never by searching a filesystem path.
            sys.path[:] = []
            contract = _exec_module(
                MODULE_NAMES[0],
                sealed_payloads["contract"],
                PROJECT_CONTRACT,
            )
            owned_modules.append((MODULE_NAMES[0], contract))
            creator = _exec_module(
                MODULE_NAMES[1],
                sealed_payloads["creator"],
                PROJECT_CREATOR,
            )
            owned_modules.append((MODULE_NAMES[1], creator))
            publisher = _exec_module(
                MODULE_NAMES[2],
                sealed_payloads["publisher"],
                PROJECT_PUBLISHER,
            )
            owned_modules.append((MODULE_NAMES[2], publisher))
            sys.path[:] = original_sys_path
            _require_bindings(contract, creator, publisher)
            os.chdir(PROJECT_ROOT)
            print(
                json.dumps(
                    {
                        "bootstrap": "authenticated_private_graph",
                        "current_sid": current_sid,
                        "launcher_sha256": _sha256(launcher_payload),
                        "mode": mode,
                        "project_modules_compiled": 3,
                        "project_modules_imported_from_path": 0,
                        "retained_graph_handles": len(GRAPH) * 2 + 2,
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            result = publisher.main([mode])
            _require_bindings(contract, creator, publisher)
            return int(result)
        finally:
            sys.path[:] = original_sys_path
            for name, module in reversed(owned_modules):
                if sys.modules.get(name) is module:
                    sys.modules.pop(name, None)


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    try:
        return _run(values)
    except (
        BootstrapRefusal,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
    ) as exc:
        print(
            json.dumps(
                {"bootstrap": "refused", "error": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
