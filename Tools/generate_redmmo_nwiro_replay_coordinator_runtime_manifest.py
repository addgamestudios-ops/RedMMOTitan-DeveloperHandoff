#!/usr/bin/env python3
"""Generate the fixed Python-runtime manifest for the M07 replay coordinator.

This is an offline review/build helper.  It does not execute project code,
publish either replay target, launch Unreal, or mutate the Python runtime.
The output is single-use and no-clobber so a changed runtime always requires a
new explicit review rather than an in-place authorization rewrite.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import msvcrt
import os
import stat
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any, Iterator


PROJECT_ROOT = Path(r"D:\RedMMOTitan")
PYTHON_ROOT = Path(
    r"C:\Users\user\AppData\Roaming\uv\python"
    r"\cpython-3.11.15-windows-x86_64-none"
)
PYTHON_EXE = PYTHON_ROOT / "python.exe"
OUTPUT_PATH = (
    PROJECT_ROOT
    / "Build"
    / "Automation"
    / "redmmo_nwiro_replay_python_runtime_manifest_v1.json"
)

EXPECTED_VERSION = (
    "3.11.15 (main, Jun 23 2026, 15:20:37) "
    "[MSC v.1944 64 bit (AMD64)]"
)
EXPECTED_PYTHON_EXE_SHA256 = (
    "AE7E969410D751D010C2CA03394FE5C53230FBF48CA7D368B897E455ECA14FBA"
)
EXPECTED_PYTHON_DLL_SHA256 = (
    "E1B53C741751563ECA9EAC70378DE5BE36994ADAC8C27E8EC375971579E23B50"
)

MAX_FILE_BYTES = 128 * 1024 * 1024
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001
_OPEN_EXISTING = 3
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
_FILE_ATTRIBUTE_TAG_INFO = 9
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class ManifestRefusal(RuntimeError):
    """The pinned runtime was not safe or stable enough to authorize."""


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", wintypes.DWORD),
        ("ReparseTag", wintypes.DWORD),
    ]


def _path_text(path: Path) -> str:
    return os.path.abspath(str(path)).replace("\\", "/")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


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
            raise ManifestRefusal(
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
        raise ManifestRefusal(
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
                    raise ManifestRefusal(
                        f"stream enumeration changed for {path}: "
                        f"Win32 error {error}"
                    )
                break
    finally:
        find_close(handle)
    return tuple(names)


def _locked_payload(
    path: Path,
    *,
    verify_ancestors: bool,
    verify_streams: bool,
) -> bytes:
    if verify_ancestors:
        _reject_reparse_chain(path.parent)
    before = path.stat(follow_symlinks=False)
    if (
        path.is_symlink()
        or _is_reparse(before)
        or not stat.S_ISREG(before.st_mode)
        or getattr(before, "st_nlink", 1) != 1
        or before.st_size < 0
        or before.st_size > MAX_FILE_BYTES
        or (verify_streams and _named_alternate_streams(path))
    ):
        raise ManifestRefusal(f"unsafe runtime file: {path}")

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
        raise ManifestRefusal(
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
            raise ManifestRefusal(f"attribute query failed: {path}")
        if tag.FileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise ManifestRefusal(f"runtime reparse refused: {path}")
        fd = msvcrt.open_osfhandle(
            int(handle),
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
        handle = None
        stream = os.fdopen(fd, "rb", closefd=True)
        fd = None
        opened = os.fstat(stream.fileno())
        payload = stream.read(MAX_FILE_BYTES + 1)
        after = os.fstat(stream.fileno())
        opened_identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            getattr(opened, "st_nlink", 1),
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            getattr(after, "st_nlink", 1),
        )
        if (
            opened_identity != after_identity
            or len(payload) != opened.st_size
            or len(payload) > MAX_FILE_BYTES
        ):
            raise ManifestRefusal(f"runtime file changed while read: {path}")
        return payload
    finally:
        if stream is not None:
            stream.close()
        elif fd is not None:
            os.close(fd)
        elif handle not in (None, _INVALID_HANDLE_VALUE):
            close_handle(handle)


def _walk_snapshot(
    *,
    full_safety_checks: bool,
) -> tuple[list[str], list[dict[str, Any]]]:
    directories: list[str] = []
    files: list[dict[str, Any]] = []
    folded: set[str] = set()
    for current, dir_names, file_names in os.walk(
        PYTHON_ROOT,
        topdown=True,
        followlinks=False,
    ):
        dir_names.sort(key=str.casefold)
        file_names.sort(key=str.casefold)
        current_path = Path(current)
        current_info = current_path.stat(follow_symlinks=False)
        if (
            current_path.is_symlink()
            or _is_reparse(current_info)
            or not stat.S_ISDIR(current_info.st_mode)
        ):
            raise ManifestRefusal(f"unsafe runtime directory: {current_path}")
        if current_path != PYTHON_ROOT:
            relative = current_path.relative_to(PYTHON_ROOT).as_posix()
            key = relative.casefold()
            if key in folded:
                raise ManifestRefusal(f"case-colliding runtime path: {relative}")
            folded.add(key)
            directories.append(relative)
        for name in file_names:
            path = current_path / name
            relative = path.relative_to(PYTHON_ROOT).as_posix()
            key = relative.casefold()
            if key in folded:
                raise ManifestRefusal(f"case-colliding runtime path: {relative}")
            folded.add(key)
            payload = _locked_payload(
                path,
                # os.walk already validated every visited directory once.
                verify_ancestors=False,
                # ADS enumeration is invariant metadata.  It is intentionally
                # performed in the full pass; the second pass proves that the
                # complete path/size/hash record set stayed byte-identical.
                verify_streams=full_safety_checks,
            )
            files.append(
                {
                    "path": relative,
                    "bytes": len(payload),
                    "sha256": _sha256(payload),
                }
            )
    directories.sort(key=str.casefold)
    files.sort(key=lambda row: str(row["path"]).casefold())
    return directories, files


def _runtime_report() -> dict[str, Any]:
    if os.name != "nt":
        raise ManifestRefusal("Windows is required")
    _reject_reparse_chain(PYTHON_ROOT)
    first_directories, first_files = _walk_snapshot(
        full_safety_checks=True
    )
    second_directories, second_files = _walk_snapshot(
        full_safety_checks=False
    )
    if (
        first_directories != second_directories
        or first_files != second_files
    ):
        raise ManifestRefusal("runtime tree changed across two-pass scan")

    python_row = next(
        row for row in first_files if row["path"] == "python.exe"
    )
    dll_row = next(
        row for row in first_files if row["path"] == "python311.dll"
    )
    if python_row["sha256"] != EXPECTED_PYTHON_EXE_SHA256:
        raise ManifestRefusal("python.exe hash drift")
    if dll_row["sha256"] != EXPECTED_PYTHON_DLL_SHA256:
        raise ManifestRefusal("python311.dll hash drift")

    completed = subprocess.run(
        [
            str(PYTHON_EXE),
            "-I",
            "-S",
            "-B",
            "-c",
            (
                "import json,sys;"
                "print(json.dumps({"
                "'version':sys.version,"
                "'executable':sys.executable,"
                "'base_executable':sys._base_executable,"
                "'base_prefix':sys.base_prefix,"
                "'flags':{"
                "'isolated':sys.flags.isolated,"
                "'no_site':sys.flags.no_site,"
                "'dont_write_bytecode':sys.flags.dont_write_bytecode,"
                "'safe_path':sys.flags.safe_path},"
                "'path':sys.path},sort_keys=True))"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=30,
        env={},
    )
    if completed.returncode != 0:
        raise ManifestRefusal("isolated Python attestation failed")
    attestation = json.loads(completed.stdout)
    if (
        attestation.get("version") != EXPECTED_VERSION
        or os.path.normcase(attestation.get("executable", ""))
        != os.path.normcase(str(PYTHON_EXE))
        or os.path.normcase(attestation.get("base_executable", ""))
        != os.path.normcase(str(PYTHON_EXE))
        or os.path.normcase(attestation.get("base_prefix", ""))
        != os.path.normcase(str(PYTHON_ROOT))
        or attestation.get("flags")
        != {
            "isolated": 1,
            "no_site": 1,
            "dont_write_bytecode": 1,
            "safe_path": True,
        }
    ):
        raise ManifestRefusal("isolated Python identity drift")

    total_bytes = sum(int(row["bytes"]) for row in first_files)
    topology_payload = "\n".join(
        [f"D:{path}" for path in first_directories]
        + [f"F:{row['path']}" for row in first_files]
    ).encode("utf-8")
    record_payload = b"".join(
        (
            f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n"
        ).encode("utf-8")
        for row in first_files
    )
    return {
        "schema_version": 1,
        "manifest_id": "redmmo.m07.nwiro.replay-python-runtime-v1",
        "status": "review_input_not_execution_authority",
        "runtime_root": _path_text(PYTHON_ROOT),
        "python_executable": _path_text(PYTHON_EXE),
        "required_flags": ["-I", "-S", "-B"],
        "version": EXPECTED_VERSION,
        "isolated_attestation": attestation,
        "directory_count_excluding_root": len(first_directories),
        "file_count": len(first_files),
        "total_bytes": total_bytes,
        "topology_sha256": _sha256(topology_payload),
        "record_set_sha256": _sha256(record_payload),
        "directories": first_directories,
        "files": first_files,
        "acl_policy": {
            "reject_inheritance_or_write_for_unapproved_principals": True,
            "approved_write_principals": [
                "CURRENT_USER",
                "S-1-5-18",
                "S-1-5-32-544",
            ],
            "runtime_tree_handles_retained_through_child_exit": True,
            "runtime_directory_handles_deny_write_delete_sharing": True,
        },
        "authorities": {
            "runtime_mutation_authorized": False,
            "network_authorized": False,
            "package_install_authorized": False,
            "project_code_execution_authorized": False,
            "unreal_launch_authorized": False,
        },
    }


def main() -> int:
    if OUTPUT_PATH.exists():
        raise ManifestRefusal(f"no-clobber output already exists: {OUTPUT_PATH}")
    report = _runtime_report()
    payload = _canonical(report)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    observed = OUTPUT_PATH.read_bytes()
    if observed != payload:
        raise ManifestRefusal("published runtime manifest byte drift")
    print(
        json.dumps(
            {
                "output": _path_text(OUTPUT_PATH),
                "bytes": len(payload),
                "sha256": _sha256(payload),
                "files": report["file_count"],
                "directories": report["directory_count_excluding_root"],
                "runtime_bytes": report["total_bytes"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ManifestRefusal, OSError, ValueError, KeyError) as exc:
        print(
            json.dumps(
                {"runtime_manifest": "refused", "error": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
