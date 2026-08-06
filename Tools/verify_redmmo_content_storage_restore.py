"""Verify an isolated RED MMO restore against an authenticated storage manifest.

This tool is read-only with respect to both the Unreal project and the restored
payload. It does not copy files, inspect ACLs, or establish that the restore
came from external storage. It authenticates the source manifest with a
caller-supplied SHA-256 digest, rejects unsafe filesystem topology, rehashes
every restored file, requires an exact path set, and writes one no-clobber JSON
report below the D-resident diagnostics root on supported Windows local-NTFS
systems.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import secrets
import stat
import unicodedata
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Iterable, Iterator, Mapping, Sequence


EXPECTED_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
MANIFEST_ID = "redmmo-content-project-plugins-storage-readiness"
REPORT_ID = "redmmo-content-storage-isolated-restore-verification"
PROJECT_DESCRIPTOR_NAME = "Titan.uproject"
EXPECTED_MANIFEST_STATUS = (
    "checksummed_source_inputs_ready_external_storage_unverified"
)
EXPECTED_STORAGE_VERIFICATION = {
    "external_storage_copied": False,
    "external_storage_access_control_verified": False,
    "restore_tested": False,
    "manifest_only": True,
}
EXPECTED_EXCLUDED_PLUGIN_ROOTS = (
    ".git",
    ".vs",
    "Binaries",
    "DerivedDataCache",
    "Intermediate",
    "Saved",
)
EXPECTED_SELECTION_POLICY = {
    "content_root": "Content",
    "plugins_root": "Plugins",
    "content_files": "all_regular_files_recursive",
    "plugin_files": (
        "all_regular_files_recursive_except_immediate_generated_roots"
    ),
    "excluded_plugin_top_level_directories": list(
        EXPECTED_EXCLUDED_PLUGIN_ROOTS
    ),
    "links_reparse_points_and_non_regular_files": "fail_closed",
    "concurrent_selected_input_change": "fail_closed",
    "output_policy": "external_diagnostics_atomic_no_clobber",
    "empty_directories": "not_represented",
    "ntfs_acl_owner_and_timestamp_metadata": "not_represented",
    "named_ntfs_alternate_streams": "not_represented",
}
EXPECTED_ENGINE_ASSOCIATION = "5.8"
EXPECTED_PROJECT_MODULE = "RedMMO"
ALLOWED_SCOPES = frozenset(
    {"project_descriptor", "project_content", "project_plugin"}
)
MAX_MANIFEST_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_ENTRIES = 1_000_000
MAX_INTEGER_VALUE = (1 << 63) - 1
MAX_RELATIVE_PATH_CHARACTERS = 32_767
MAX_COMPONENT_CHARACTERS = 255
SHA256_PATTERN = re.compile(r"^[0-9A-F]{64}$")
WINDOWS_LOCAL_DOS_PATH_PATTERN = re.compile(
    r"^(?:\\\\\?\\)?(?P<drive>[A-Za-z]):\\",
)
WINDOWS_RESERVED_NAMES = {
    "AUX",
    "CON",
    "NUL",
    "PRN",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
WINDOWS_FORBIDDEN_CHARACTERS = frozenset('<>"|?*')
WINDOWS_DELETE_ACCESS = 0x00010000
WINDOWS_SYNCHRONIZE_ACCESS = 0x00100000
WINDOWS_GENERIC_WRITE = 0x40000000
WINDOWS_FILE_READ_DATA = 0x0001
WINDOWS_FILE_LIST_DIRECTORY = 0x0001
WINDOWS_FILE_ADD_FILE = 0x0002
WINDOWS_FILE_ADD_SUBDIRECTORY = 0x0004
WINDOWS_FILE_TRAVERSE = 0x0020
WINDOWS_FILE_READ_ATTRIBUTES = 0x0080
WINDOWS_FILE_SHARE_READ = 0x0001
WINDOWS_FILE_SHARE_WRITE = 0x0002
WINDOWS_FILE_SHARE_DELETE = 0x0004
WINDOWS_FILE_ATTRIBUTE_DIRECTORY = 0x0010
WINDOWS_FILE_ATTRIBUTE_NORMAL = 0x0080
WINDOWS_FILE_ATTRIBUTE_TEMPORARY = 0x0100
WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
WINDOWS_OPEN_EXISTING = 3
WINDOWS_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
WINDOWS_OBJ_CASE_INSENSITIVE = 0x0040
WINDOWS_FILE_DIRECTORY_FILE = 0x00000001
WINDOWS_FILE_WRITE_THROUGH = 0x00000002
WINDOWS_FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
WINDOWS_FILE_NON_DIRECTORY_FILE = 0x00000040
WINDOWS_FILE_OPEN_REPARSE_POINT = 0x00200000
WINDOWS_FILE_OPEN = 1
WINDOWS_FILE_CREATE = 2
WINDOWS_FILE_OPEN_IF = 3
WINDOWS_FILE_RENAME_INFORMATION = 10
WINDOWS_FILE_DISPOSITION_INFO = 4
WINDOWS_FILE_ATTRIBUTE_TAG_INFO = 9
WINDOWS_FILE_ID_INFO = 18
WINDOWS_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
WINDOWS_DIRECTORY_PIN_ACCESS = (
    WINDOWS_FILE_TRAVERSE
    | WINDOWS_FILE_READ_ATTRIBUTES
    | WINDOWS_SYNCHRONIZE_ACCESS
)
WINDOWS_DIRECTORY_READ_ACCESS = (
    WINDOWS_DIRECTORY_PIN_ACCESS
    | WINDOWS_FILE_LIST_DIRECTORY
)
WINDOWS_DIRECTORY_ACCESS = (
    WINDOWS_DIRECTORY_READ_ACCESS
    | WINDOWS_FILE_ADD_FILE
    | WINDOWS_FILE_ADD_SUBDIRECTORY
)
WINDOWS_TEMP_FILE_ACCESS = (
    WINDOWS_GENERIC_WRITE
    | WINDOWS_DELETE_ACCESS
    | WINDOWS_FILE_READ_ATTRIBUTES
    | WINDOWS_SYNCHRONIZE_ACCESS
)
WINDOWS_FILE_SHARE_ALL = (
    WINDOWS_FILE_SHARE_READ
    | WINDOWS_FILE_SHARE_WRITE
    | WINDOWS_FILE_SHARE_DELETE
)
WINDOWS_MANIFEST_FILE_ACCESS = (
    WINDOWS_FILE_READ_DATA
    | WINDOWS_FILE_READ_ATTRIBUTES
    | WINDOWS_SYNCHRONIZE_ACCESS
)
_WINDOWS_API_CACHE: tuple[object, object] | None = None
EXPECTED_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "manifest_id",
        "evidence_class",
        "status",
        "project_identity",
        "selection_policy",
        "provenance",
        "scope",
        "storage_verification",
        "protected_inputs",
        "plugins",
        "entries",
        "claim_limit",
    }
)
EXPECTED_PLUGIN_KEYS = frozenset(
    {
        "plugin_id",
        "plugin_root",
        "descriptor_path",
        "friendly_name",
        "version_name",
        "created_by",
        "installed",
        "can_contain_content",
        "listed_in_project_descriptor",
        "enabled_in_project_descriptor",
        "excluded_generated_top_level_directories_present",
        "file_count",
        "bytes",
        "signature_sha256",
        "descriptor_sha256",
    }
)


class RestoreVerificationError(RuntimeError):
    """Raised when an isolated restore cannot be verified safely."""


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
class RestoredFile:
    path: Path
    relative_path: str
    metadata: FileMetadata


@dataclass(frozen=True)
class WindowsHandleMetadata:
    attributes: int
    volume_serial: int
    file_id: int
    identity_volume_serial: int
    file_id_128: bytes
    size: int
    link_count: int


@dataclass(frozen=True)
class PublicationCheckpointEvent:
    """Scalar-only private instrumentation for the recovery harness."""

    name: str
    candidate_name: str | None = None
    payload_size: int = 0
    bytes_written: int = 0
    identity_volume_serial: int | None = None
    file_id_128_hex: str | None = None


@dataclass(frozen=True)
class _PublicationCheckpointObserver:
    armed_checkpoint: str | None
    callback: Callable[[PublicationCheckpointEvent], None]


_PUBLICATION_CHECKPOINT_OBSERVER: ContextVar[
    _PublicationCheckpointObserver | None
] = ContextVar(
    "redmmo_publication_checkpoint_observer",
    default=None,
)


class _WindowsFileTime(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class _WindowsByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", _WindowsFileTime),
        ("ftLastAccessTime", _WindowsFileTime),
        ("ftLastWriteTime", _WindowsFileTime),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]


class _WindowsFileAttributeTagInformation(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", wintypes.DWORD),
        ("ReparseTag", wintypes.DWORD),
    ]


class _WindowsFileId128(ctypes.Structure):
    _fields_ = [("Identifier", ctypes.c_ubyte * 16)]


class _WindowsFileIdInformation(ctypes.Structure):
    _fields_ = [
        ("VolumeSerialNumber", ctypes.c_ulonglong),
        ("FileId", _WindowsFileId128),
    ]


class _WindowsUnicodeString(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", wintypes.LPWSTR),
    ]


class _WindowsObjectAttributes(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.ULONG),
        ("RootDirectory", wintypes.HANDLE),
        ("ObjectName", ctypes.POINTER(_WindowsUnicodeString)),
        ("Attributes", wintypes.ULONG),
        ("SecurityDescriptor", wintypes.LPVOID),
        ("SecurityQualityOfService", wintypes.LPVOID),
    ]


class _WindowsIoStatusUnion(ctypes.Union):
    _fields_ = [
        ("Status", ctypes.c_long),
        ("Pointer", wintypes.LPVOID),
    ]


class _WindowsIoStatusBlock(ctypes.Structure):
    _fields_ = [
        ("u", _WindowsIoStatusUnion),
        ("Information", ctypes.c_size_t),
    ]


class _WindowsRenameUnion(ctypes.Union):
    _fields_ = [
        ("ReplaceIfExists", wintypes.BOOLEAN),
        ("Flags", wintypes.DWORD),
    ]


class _WindowsFileRenameInformation(ctypes.Structure):
    _fields_ = [
        ("u", _WindowsRenameUnion),
        ("RootDirectory", wintypes.HANDLE),
        ("FileNameLength", wintypes.DWORD),
        ("FileName", wintypes.WCHAR * 1),
    ]


class _WindowsFileDispositionInformation(ctypes.Structure):
    _fields_ = [("DeleteFile", wintypes.BOOL)]


def _sort_key(value: str) -> tuple[str, str]:
    return value.casefold(), value


@contextmanager
def _publication_checkpoint_scope(
    callback: Callable[[PublicationCheckpointEvent], None],
    *,
    armed_checkpoint: str | None,
) -> Iterator[None]:
    """Bind one process-local observer without exposing a CLI activation path."""

    if not callable(callback):
        raise RestoreVerificationError(
            "publication checkpoint callback must be callable"
        )
    token = _PUBLICATION_CHECKPOINT_OBSERVER.set(
        _PublicationCheckpointObserver(armed_checkpoint, callback)
    )
    try:
        yield
    finally:
        _PUBLICATION_CHECKPOINT_OBSERVER.reset(token)


def _publication_checkpoint_is_armed(name: str) -> bool:
    observer = _PUBLICATION_CHECKPOINT_OBSERVER.get()
    return observer is not None and (
        observer.armed_checkpoint is None
        or observer.armed_checkpoint == name
    )


def _emit_publication_checkpoint(
    name: str,
    *,
    candidate_name: str | None = None,
    payload_size: int = 0,
    bytes_written: int = 0,
    identity: WindowsHandleMetadata | None = None,
) -> None:
    observer = _PUBLICATION_CHECKPOINT_OBSERVER.get()
    if observer is None or (
        observer.armed_checkpoint is not None
        and observer.armed_checkpoint != name
    ):
        return
    observer.callback(
        PublicationCheckpointEvent(
            name=name,
            candidate_name=candidate_name,
            payload_size=payload_size,
            bytes_written=bytes_written,
            identity_volume_serial=(
                identity.identity_volume_serial
                if identity is not None
                else None
            ),
            file_id_128_hex=(
                identity.file_id_128.hex().upper()
                if identity is not None
                else None
            ),
        )
    )


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise RestoreVerificationError(
            f"{label} must be an uppercase 64-character SHA-256 digest"
        )
    return value


def _metadata_from_stat_result(observed: os.stat_result) -> FileMetadata:
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


def _metadata(path: Path) -> FileMetadata:
    try:
        observed = path.lstat()
    except OSError as error:
        raise RestoreVerificationError(
            f"unable to inspect path metadata: {path}: {error}"
        ) from error
    return _metadata_from_stat_result(observed)


def _is_link_or_reparse(
    path: Path,
    metadata: FileMetadata | None = None,
) -> bool:
    observed = metadata or _metadata(path)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(observed.mode) or bool(
        reparse_flag and observed.attributes & reparse_flag
    )


def _is_offline_or_recall(metadata: FileMetadata) -> bool:
    offline = getattr(stat, "FILE_ATTRIBUTE_OFFLINE", 0x1000)
    recall_on_open = getattr(stat, "FILE_ATTRIBUTE_RECALL_ON_OPEN", 0x40000)
    recall_on_data_access = getattr(
        stat,
        "FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS",
        0x400000,
    )
    return bool(
        metadata.attributes
        & (offline | recall_on_open | recall_on_data_access)
    )


def _windows_drive_type(drive: str) -> int:
    try:
        get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
        get_drive_type.argtypes = [ctypes.c_wchar_p]
        get_drive_type.restype = ctypes.c_uint
        return int(get_drive_type(f"{drive.upper()}:\\"))
    except (AttributeError, OSError, TypeError, ValueError) as error:
        raise RestoreVerificationError(
            f"unable to query Windows drive type for {drive}: {error}"
        ) from error


def _windows_apis() -> tuple[object, object]:
    global _WINDOWS_API_CACHE
    if _WINDOWS_API_CACHE is not None:
        return _WINDOWS_API_CACHE
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll")
    except (AttributeError, OSError) as error:
        raise RestoreVerificationError(
            f"required Windows filesystem APIs are unavailable: {error}"
        ) from error

    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_WindowsByHandleFileInformation),
    ]
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel32.GetVolumeInformationByHandleW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    kernel32.GetVolumeInformationByHandleW.restype = wintypes.BOOL
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel32.FlushFileBuffers.restype = wintypes.BOOL
    kernel32.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.SetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    ntdll.NtCreateFile.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        ctypes.POINTER(_WindowsObjectAttributes),
        ctypes.POINTER(_WindowsIoStatusBlock),
        ctypes.c_void_p,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.LPVOID,
        wintypes.ULONG,
    ]
    ntdll.NtCreateFile.restype = ctypes.c_long
    ntdll.NtSetInformationFile.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_WindowsIoStatusBlock),
        wintypes.LPVOID,
        wintypes.ULONG,
        ctypes.c_int,
    ]
    ntdll.NtSetInformationFile.restype = ctypes.c_long
    ntdll.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
    ntdll.RtlNtStatusToDosError.restype = wintypes.ULONG

    _WINDOWS_API_CACHE = kernel32, ntdll
    return _WINDOWS_API_CACHE


def _windows_close_handle(handle: int) -> None:
    kernel32, _ = _windows_apis()
    if handle and handle != WINDOWS_INVALID_HANDLE_VALUE:
        kernel32.CloseHandle(handle)


def _windows_handle_metadata(
    handle: int,
    label: str,
) -> WindowsHandleMetadata:
    kernel32, _ = _windows_apis()
    observed = _WindowsByHandleFileInformation()
    if not kernel32.GetFileInformationByHandle(
        handle,
        ctypes.byref(observed),
    ):
        raise RestoreVerificationError(
            f"unable to query stable Windows {label} handle identity: "
            f"{ctypes.WinError(ctypes.get_last_error())}"
        )
    identity = _WindowsFileIdInformation()
    if not kernel32.GetFileInformationByHandleEx(
        handle,
        WINDOWS_FILE_ID_INFO,
        ctypes.byref(identity),
        ctypes.sizeof(identity),
    ):
        raise RestoreVerificationError(
            f"unable to query native Windows {label} 128-bit identity: "
            f"{ctypes.WinError(ctypes.get_last_error())}"
        )
    file_id = (int(observed.nFileIndexHigh) << 32) | int(
        observed.nFileIndexLow
    )
    volume_serial = int(observed.dwVolumeSerialNumber)
    identity_volume_serial = int(identity.VolumeSerialNumber)
    file_id_128 = bytes(identity.FileId.Identifier)
    if (
        volume_serial <= 0
        or file_id <= 0
        or identity_volume_serial <= 0
        or not any(file_id_128)
    ):
        raise RestoreVerificationError(
            f"stable Windows {label} handle identity is unavailable"
        )
    return WindowsHandleMetadata(
        attributes=int(observed.dwFileAttributes),
        volume_serial=volume_serial,
        file_id=file_id,
        identity_volume_serial=identity_volume_serial,
        file_id_128=file_id_128,
        size=(int(observed.nFileSizeHigh) << 32)
        | int(observed.nFileSizeLow),
        link_count=int(observed.nNumberOfLinks),
    )


def _windows_require_plain_directory_handle(
    handle: int,
    label: str,
) -> WindowsHandleMetadata:
    kernel32, _ = _windows_apis()
    tag = _WindowsFileAttributeTagInformation()
    if not kernel32.GetFileInformationByHandleEx(
        handle,
        WINDOWS_FILE_ATTRIBUTE_TAG_INFO,
        ctypes.byref(tag),
        ctypes.sizeof(tag),
    ):
        raise RestoreVerificationError(
            f"unable to query Windows {label} directory attributes: "
            f"{ctypes.WinError(ctypes.get_last_error())}"
        )
    attributes = int(tag.FileAttributes)
    if not attributes & WINDOWS_FILE_ATTRIBUTE_DIRECTORY:
        raise RestoreVerificationError(
            f"Windows {label} handle is not a directory"
        )
    if attributes & WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT:
        raise RestoreVerificationError(
            f"linked or reparse Windows {label} directory is forbidden: "
            f"tag=0x{int(tag.ReparseTag):08X}"
        )
    observed = _windows_handle_metadata(handle, label)
    if not observed.attributes & WINDOWS_FILE_ATTRIBUTE_DIRECTORY:
        raise RestoreVerificationError(
            f"Windows {label} identity is not a directory"
        )
    return observed


def _windows_require_plain_file_handle(
    handle: int,
    label: str,
) -> WindowsHandleMetadata:
    kernel32, _ = _windows_apis()
    tag = _WindowsFileAttributeTagInformation()
    if not kernel32.GetFileInformationByHandleEx(
        handle,
        WINDOWS_FILE_ATTRIBUTE_TAG_INFO,
        ctypes.byref(tag),
        ctypes.sizeof(tag),
    ):
        raise RestoreVerificationError(
            f"unable to query Windows {label} file attributes: "
            f"{ctypes.WinError(ctypes.get_last_error())}"
        )
    attributes = int(tag.FileAttributes)
    if attributes & WINDOWS_FILE_ATTRIBUTE_DIRECTORY:
        raise RestoreVerificationError(
            f"Windows {label} handle is a directory"
        )
    if attributes & WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT:
        raise RestoreVerificationError(
            f"linked or reparse Windows {label} file is forbidden: "
            f"tag=0x{int(tag.ReparseTag):08X}"
        )
    offline = getattr(stat, "FILE_ATTRIBUTE_OFFLINE", 0x1000)
    recall_on_open = getattr(stat, "FILE_ATTRIBUTE_RECALL_ON_OPEN", 0x40000)
    recall_on_data_access = getattr(
        stat,
        "FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS",
        0x400000,
    )
    if attributes & (offline | recall_on_open | recall_on_data_access):
        raise RestoreVerificationError(
            f"offline or recall-on-access Windows {label} file is forbidden"
        )
    observed = _windows_handle_metadata(handle, label)
    if observed.attributes & (
        WINDOWS_FILE_ATTRIBUTE_DIRECTORY
        | WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise RestoreVerificationError(
            f"Windows {label} identity is not a plain file"
        )
    if observed.link_count != 1:
        raise RestoreVerificationError(
            f"hard-linked Windows {label} file is forbidden: "
            f"links={observed.link_count}"
        )
    return observed


def _windows_require_ntfs(handle: int, label: str) -> None:
    kernel32, _ = _windows_apis()
    volume_name = ctypes.create_unicode_buffer(261)
    filesystem_name = ctypes.create_unicode_buffer(261)
    serial = wintypes.DWORD()
    maximum_component = wintypes.DWORD()
    filesystem_flags = wintypes.DWORD()
    if not kernel32.GetVolumeInformationByHandleW(
        handle,
        volume_name,
        len(volume_name),
        ctypes.byref(serial),
        ctypes.byref(maximum_component),
        ctypes.byref(filesystem_flags),
        filesystem_name,
        len(filesystem_name),
    ):
        raise RestoreVerificationError(
            f"unable to query Windows {label} filesystem: "
            f"{ctypes.WinError(ctypes.get_last_error())}"
        )
    if filesystem_name.value.upper() != "NTFS":
        raise RestoreVerificationError(
            f"Windows {label} requires local NTFS; observed "
            f"{filesystem_name.value or '<unknown>'}"
        )


def _validate_windows_component(component: str, label: str) -> str:
    if (
        not component
        or component in {".", ".."}
        or len(component) > MAX_COMPONENT_CHARACTERS
        or component.endswith((" ", "."))
        or any(
            ord(character) < 32
            or character in WINDOWS_FORBIDDEN_CHARACTERS
            or character in {"/", "\\", ":", "\x00"}
            for character in component
        )
    ):
        raise RestoreVerificationError(
            f"unsafe Windows {label} path component: {component!r}"
        )
    if component.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        raise RestoreVerificationError(
            f"reserved Windows {label} path component: {component!r}"
        )
    return component


def _windows_nt_error(
    status: int,
    operation: str,
) -> tuple[int, RestoreVerificationError]:
    _, ntdll = _windows_apis()
    dos_error = int(ntdll.RtlNtStatusToDosError(status))
    message = ctypes.FormatError(dos_error).strip()
    return dos_error, RestoreVerificationError(
        f"{operation} failed with NTSTATUS=0x{status & 0xFFFFFFFF:08X}, "
        f"WinError={dos_error}: {message}"
    )


def _windows_nt_create_relative(
    parent_handle: int,
    name: str,
    *,
    directory: bool,
) -> tuple[int, int]:
    _validate_windows_component(
        name,
        "directory" if directory else "temporary report",
    )
    _, ntdll = _windows_apis()
    name_storage = ctypes.create_unicode_buffer(name)
    encoded = name.encode("utf-16-le")
    counted_name = _WindowsUnicodeString(
        len(encoded),
        len(encoded) + 2,
        ctypes.cast(name_storage, wintypes.LPWSTR),
    )
    attributes = _WindowsObjectAttributes(
        ctypes.sizeof(_WindowsObjectAttributes),
        parent_handle,
        ctypes.pointer(counted_name),
        WINDOWS_OBJ_CASE_INSENSITIVE,
        None,
        None,
    )
    io_status = _WindowsIoStatusBlock()
    output = wintypes.HANDLE()
    if directory:
        access = WINDOWS_DIRECTORY_ACCESS
        file_attributes = WINDOWS_FILE_ATTRIBUTE_DIRECTORY
        disposition = WINDOWS_FILE_OPEN_IF
        options = (
            WINDOWS_FILE_DIRECTORY_FILE
            | WINDOWS_FILE_WRITE_THROUGH
            | WINDOWS_FILE_SYNCHRONOUS_IO_NONALERT
            | WINDOWS_FILE_OPEN_REPARSE_POINT
        )
    else:
        access = WINDOWS_TEMP_FILE_ACCESS
        file_attributes = WINDOWS_FILE_ATTRIBUTE_NORMAL
        disposition = WINDOWS_FILE_CREATE
        options = (
            WINDOWS_FILE_NON_DIRECTORY_FILE
            | WINDOWS_FILE_WRITE_THROUGH
            | WINDOWS_FILE_SYNCHRONOUS_IO_NONALERT
            | WINDOWS_FILE_OPEN_REPARSE_POINT
        )
    share_mode = (
        WINDOWS_FILE_SHARE_ALL
        if directory
        else 0
    )
    status = int(
        ntdll.NtCreateFile(
            ctypes.byref(output),
            access,
            ctypes.byref(attributes),
            ctypes.byref(io_status),
            None,
            file_attributes,
            share_mode,
            disposition,
            options,
            None,
            0,
        )
    )
    if status < 0:
        _, error = _windows_nt_error(
            status,
            f"handle-relative create/open for {name!r}",
        )
        raise error
    if not output.value or output.value == WINDOWS_INVALID_HANDLE_VALUE:
        raise RestoreVerificationError(
            f"handle-relative create/open returned an invalid handle: {name!r}"
        )
    return int(output.value), int(io_status.Information)


def _windows_nt_open_manifest_relative(
    parent_handle: int,
    name: str,
) -> int:
    _validate_windows_component(name, "storage manifest")
    _, ntdll = _windows_apis()
    name_storage = ctypes.create_unicode_buffer(name)
    encoded = name.encode("utf-16-le")
    counted_name = _WindowsUnicodeString(
        len(encoded),
        len(encoded) + 2,
        ctypes.cast(name_storage, wintypes.LPWSTR),
    )
    attributes = _WindowsObjectAttributes(
        ctypes.sizeof(_WindowsObjectAttributes),
        parent_handle,
        ctypes.pointer(counted_name),
        WINDOWS_OBJ_CASE_INSENSITIVE,
        None,
        None,
    )
    io_status = _WindowsIoStatusBlock()
    output = wintypes.HANDLE()
    status = int(
        ntdll.NtCreateFile(
            ctypes.byref(output),
            WINDOWS_MANIFEST_FILE_ACCESS,
            ctypes.byref(attributes),
            ctypes.byref(io_status),
            None,
            0,
            WINDOWS_FILE_SHARE_READ,
            WINDOWS_FILE_OPEN,
            WINDOWS_FILE_NON_DIRECTORY_FILE
            | WINDOWS_FILE_SYNCHRONOUS_IO_NONALERT
            | WINDOWS_FILE_OPEN_REPARSE_POINT,
            None,
            0,
        )
    )
    if status < 0:
        _, error = _windows_nt_error(
            status,
            f"stable handle-relative open for manifest {name!r}",
        )
        raise error
    if not output.value or output.value == WINDOWS_INVALID_HANDLE_VALUE:
        raise RestoreVerificationError(
            "stable handle-relative manifest open returned an invalid handle: "
            f"{name!r}"
        )
    return int(output.value)


def _windows_open_pinned_directory(
    path: Path,
    expected: FileMetadata,
    label: str,
    *,
    desired_access: int = WINDOWS_DIRECTORY_ACCESS,
    share_mode: int = WINDOWS_FILE_SHARE_ALL,
) -> tuple[int, WindowsHandleMetadata]:
    kernel32, _ = _windows_apis()
    handle = kernel32.CreateFileW(
        str(path),
        desired_access,
        share_mode,
        None,
        WINDOWS_OPEN_EXISTING,
        WINDOWS_FILE_FLAG_BACKUP_SEMANTICS
        | WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle == WINDOWS_INVALID_HANDLE_VALUE:
        raise RestoreVerificationError(
            f"unable to open pinned Windows {label} directory: {path}: "
            f"{ctypes.WinError(ctypes.get_last_error())}"
        )
    value = int(handle)
    try:
        observed = _windows_require_plain_directory_handle(value, label)
        if (observed.volume_serial, observed.file_id) != (
            expected.device,
            expected.inode,
        ):
            raise RestoreVerificationError(
                f"Windows {label} directory identity changed while pinning: "
                f"{path}"
            )
        return value, observed
    except BaseException:
        _windows_close_handle(value)
        raise


@contextmanager
def _windows_pinned_output_parent(
    output_path: Path,
    diagnostics_root: Path,
) -> Iterator[tuple[int, WindowsHandleMetadata]]:
    resolved_root = _require_plain_directory(
        diagnostics_root,
        "diagnostics root",
    )
    try:
        relative_parent = output_path.parent.relative_to(resolved_root)
    except ValueError as error:
        raise RestoreVerificationError(
            f"output parent is outside diagnostics root {resolved_root}: "
            f"{output_path.parent}"
        ) from error
    expected_root = _metadata(resolved_root)
    root_handle, root_identity = _windows_open_pinned_directory(
        resolved_root,
        expected_root,
        "diagnostics root",
    )
    handles = [root_handle]
    current_handle = root_handle
    current_identity = root_identity
    try:
        _windows_require_ntfs(root_handle, "diagnostics root")
        for component in relative_parent.parts:
            _validate_windows_component(component, "output parent")
            child_handle, _ = _windows_nt_create_relative(
                current_handle,
                component,
                directory=True,
            )
            handles.append(child_handle)
            current_handle = child_handle
            current_identity = _windows_require_plain_directory_handle(
                child_handle,
                f"output parent {component!r}",
            )
        yield current_handle, current_identity
    finally:
        for handle in reversed(handles):
            _windows_close_handle(handle)


def _windows_flush_handle(handle: int, label: str) -> None:
    kernel32, _ = _windows_apis()
    if not kernel32.FlushFileBuffers(handle):
        raise RestoreVerificationError(
            f"unable to flush Windows {label}: "
            f"{ctypes.WinError(ctypes.get_last_error())}"
        )


def _windows_write_and_flush(handle: int, payload: bytes) -> None:
    kernel32, _ = _windows_apis()
    offset = 0
    maximum_write = 16 * 1024 * 1024
    if (
        _publication_checkpoint_is_armed("mid_payload_write")
        and len(payload) > 1
    ):
        maximum_write = max(1, len(payload) // 2)
    mid_payload_emitted = False
    while offset < len(payload):
        block = payload[offset : offset + maximum_write]
        storage = ctypes.create_string_buffer(block)
        written = wintypes.DWORD()
        if not kernel32.WriteFile(
            handle,
            storage,
            len(block),
            ctypes.byref(written),
            None,
        ):
            raise RestoreVerificationError(
                "unable to write Windows report temporary file: "
                f"{ctypes.WinError(ctypes.get_last_error())}"
            )
        if written.value != len(block):
            raise RestoreVerificationError(
                "short Windows report write: "
                f"expected={len(block)} observed={written.value}"
            )
        offset += written.value
        if (
            not mid_payload_emitted
            and 0 < offset < len(payload)
        ):
            _emit_publication_checkpoint(
                "mid_payload_write",
                payload_size=len(payload),
                bytes_written=offset,
            )
            mid_payload_emitted = True
    _emit_publication_checkpoint(
        "after_payload_write_before_preflush",
        payload_size=len(payload),
        bytes_written=offset,
    )
    _windows_flush_handle(handle, "report temporary file before publication")


def _windows_publish_open_file_no_clobber(
    file_handle: int,
    parent_handle: int,
    final_name: str,
) -> None:
    _validate_windows_component(final_name, "report filename")
    _, ntdll = _windows_apis()
    encoded = final_name.encode("utf-16-le")
    raw = ctypes.create_string_buffer(
        ctypes.sizeof(_WindowsFileRenameInformation) + len(encoded) + 2
    )
    rename = _WindowsFileRenameInformation.from_buffer(raw)
    rename.u.Flags = 0
    rename.RootDirectory = parent_handle
    rename.FileNameLength = len(encoded)
    ctypes.memmove(
        ctypes.addressof(raw) + _WindowsFileRenameInformation.FileName.offset,
        encoded,
        len(encoded),
    )
    io_status = _WindowsIoStatusBlock()
    status = int(
        ntdll.NtSetInformationFile(
            file_handle,
            ctypes.byref(io_status),
            raw,
            len(raw),
            WINDOWS_FILE_RENAME_INFORMATION,
        )
    )
    if status < 0:
        dos_error, error = _windows_nt_error(
            status,
            f"handle-relative no-clobber publication for {final_name!r}",
        )
        if dos_error in {80, 183}:
            raise RestoreVerificationError(
                f"refusing to overwrite output: {final_name}"
            ) from error
        raise error
    _emit_publication_checkpoint(
        "after_rename_before_postflush",
    )
    _windows_flush_handle(file_handle, "published report file")


def _windows_delete_open_file_on_close(handle: int) -> None:
    kernel32, _ = _windows_apis()
    disposition = _WindowsFileDispositionInformation(True)
    if not kernel32.SetFileInformationByHandle(
        handle,
        WINDOWS_FILE_DISPOSITION_INFO,
        ctypes.byref(disposition),
        ctypes.sizeof(disposition),
    ):
        raise RestoreVerificationError(
            "unable to delete failed Windows report temporary file by handle: "
            f"{ctypes.WinError(ctypes.get_last_error())}"
        )


def _require_plain_directory(path: Path, label: str) -> Path:
    lexical = path.absolute()
    if os.name == "nt":
        windows_path = str(lexical).replace("/", "\\")
        local_match = WINDOWS_LOCAL_DOS_PATH_PATTERN.match(windows_path)
        if local_match is None:
            raise RestoreVerificationError(
                f"{label} must use a local DOS drive path; UNC, device, "
                f"volume-GUID, DFS, and mapped-share identity are unsupported: "
                f"{lexical}"
            )
        drive_type = _windows_drive_type(local_match.group("drive"))
        if drive_type in {0, 1, 4}:
            raise RestoreVerificationError(
                f"{label} must use an available non-network DOS drive; "
                f"observed Windows drive type {drive_type}: {lexical}"
            )
    cursor = lexical
    while True:
        if _lexists(cursor):
            ancestor = _metadata(cursor)
            if _is_link_or_reparse(cursor, ancestor):
                raise RestoreVerificationError(
                    f"linked or reparse {label} ancestor is forbidden: {cursor}"
                )
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    observed = _metadata(lexical)
    if not stat.S_ISDIR(observed.mode):
        raise RestoreVerificationError(f"{label} is not a directory: {lexical}")
    try:
        return lexical.resolve(strict=True)
    except OSError as error:
        raise RestoreVerificationError(
            f"{label} cannot be resolved: {lexical}: {error}"
        ) from error


def _require_regular_file(path: Path, root: Path, label: str) -> FileMetadata:
    observed = _metadata(path)
    if _is_link_or_reparse(path, observed):
        raise RestoreVerificationError(
            f"linked or reparse {label} is forbidden: {path}"
        )
    if not stat.S_ISREG(observed.mode):
        raise RestoreVerificationError(
            f"non-regular {label} is forbidden: {path}"
        )
    if observed.link_count != 1:
        raise RestoreVerificationError(
            f"hard-linked {label} is forbidden because alias topology is "
            f"not authenticated: {path} links={observed.link_count}"
        )
    if _is_offline_or_recall(observed):
        raise RestoreVerificationError(
            f"offline or recall-on-access {label} is forbidden: {path}"
        )
    try:
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as error:
        raise RestoreVerificationError(
            f"{label} escapes or cannot be resolved inside {root}: {path}"
        ) from error
    return observed


def _existing_path_identity(
    path: Path,
    label: str,
) -> tuple[int, int] | None:
    if not _lexists(path):
        return None
    observed = _metadata(path)
    if observed.device <= 0 or observed.inode <= 0:
        raise RestoreVerificationError(
            f"stable path identity is unavailable for {label}: {path}"
        )
    return observed.device, observed.inode


def _existing_ancestry_contains_identity(
    path: Path,
    identity: tuple[int, int],
    label: str,
) -> bool:
    cursor = path.absolute()
    while True:
        observed = _existing_path_identity(cursor, label)
        if observed == identity:
            return True
        if cursor.parent == cursor:
            return False
        cursor = cursor.parent


def _paths_overlap(first: Path, second: Path) -> bool:
    try:
        first.relative_to(second)
        return True
    except ValueError:
        pass
    try:
        second.relative_to(first)
        return True
    except ValueError:
        pass

    if os.name != "nt":
        return False

    first_identity = _existing_path_identity(first, "first overlap path")
    second_identity = _existing_path_identity(second, "second overlap path")
    if first_identity is not None and _existing_ancestry_contains_identity(
        second,
        first_identity,
        "second overlap path ancestry",
    ):
        return True
    if second_identity is not None and _existing_ancestry_contains_identity(
        first,
        second_identity,
        "first overlap path ancestry",
    ):
        return True
    return False


def validate_input_isolation(
    manifest_path: Path,
    restore_root: Path,
) -> tuple[Path, Path]:
    resolved_restore = _require_plain_directory(
        restore_root,
        "restore root",
    )
    lexical_manifest = manifest_path.absolute()
    manifest_parent = _require_plain_directory(
        lexical_manifest.parent,
        "manifest parent",
    )
    _require_regular_file(
        lexical_manifest,
        manifest_parent,
        "storage manifest",
    )
    resolved_manifest = lexical_manifest.resolve(strict=True)
    if _paths_overlap(resolved_manifest, resolved_restore):
        raise RestoreVerificationError(
            "storage manifest must remain outside the restored tree"
        )
    project_root = _require_plain_directory(
        EXPECTED_PROJECT_ROOT,
        "active Unreal project",
    )
    if _paths_overlap(resolved_restore, project_root):
        raise RestoreVerificationError(
            "restore root must be isolated from the active Unreal project"
        )
    return resolved_manifest, resolved_restore


def _validate_relative_path(relative_path: object) -> str:
    if not isinstance(relative_path, str):
        raise RestoreVerificationError("manifest entry path must be a string")
    if not relative_path or relative_path.startswith(("/", "\\")):
        raise RestoreVerificationError(
            f"invalid project-relative path: {relative_path!r}"
        )
    if "\\" in relative_path:
        raise RestoreVerificationError(
            f"backslashes are forbidden in manifest paths: {relative_path!r}"
        )
    if len(relative_path) > MAX_RELATIVE_PATH_CHARACTERS:
        raise RestoreVerificationError(
            f"project-relative path is too long: {relative_path!r}"
        )
    if unicodedata.normalize("NFC", relative_path) != relative_path:
        raise RestoreVerificationError(
            f"non-NFC project-relative path is forbidden: {relative_path!r}"
        )
    for component in relative_path.split("/"):
        if component in {"", ".", ".."}:
            raise RestoreVerificationError(
                f"unsafe project-relative path component: {relative_path!r}"
            )
        if len(component) > MAX_COMPONENT_CHARACTERS:
            raise RestoreVerificationError(
                f"project-relative path component is too long: "
                f"{relative_path!r}"
            )
        if component.endswith((" ", ".")):
            raise RestoreVerificationError(
                f"trailing dot or space is forbidden: {relative_path!r}"
            )
        if ":" in component:
            raise RestoreVerificationError(
                f"colon or alternate stream syntax is forbidden: "
                f"{relative_path!r}"
            )
        if any(
            ord(character) < 32
            or character in WINDOWS_FORBIDDEN_CHARACTERS
            for character in component
        ):
            raise RestoreVerificationError(
                f"Windows-forbidden path character is present: "
                f"{relative_path!r}"
            )
        stem = component.split(".", 1)[0].upper()
        if stem in WINDOWS_RESERVED_NAMES:
            raise RestoreVerificationError(
                f"reserved Windows path component is forbidden: "
                f"{relative_path!r}"
            )
    return relative_path


def _reject_duplicate_object_keys(
    pairs: Sequence[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RestoreVerificationError(
                f"duplicate JSON object key is forbidden: {key}"
            )
        result[key] = value
    return result


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


def _require_exact_integer(value: object, label: str) -> int:
    if (
        type(value) is not int
        or value < 0
        or value > MAX_INTEGER_VALUE
    ):
        raise RestoreVerificationError(
            f"{label} must be a nonnegative signed 64-bit integer"
        )
    return value


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise RestoreVerificationError(f"{label} must be a JSON object")
    return value


def _require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise RestoreVerificationError(f"{label} must be a JSON array")
    return value


def _require_optional_string(value: object, label: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise RestoreVerificationError(f"{label} must be a string or null")
    return value


def _require_optional_bool(value: object, label: str) -> bool | None:
    if value is not None and type(value) is not bool:
        raise RestoreVerificationError(f"{label} must be a boolean or null")
    return value


def _require_canonical_string_list(
    value: object,
    label: str,
    *,
    allowed: frozenset[str] | None = None,
) -> list[str]:
    raw = _require_list(value, label)
    if any(not isinstance(item, str) or not item for item in raw):
        raise RestoreVerificationError(
            f"{label} must contain only nonempty strings"
        )
    strings = [str(item) for item in raw]
    if strings != sorted(set(strings), key=_sort_key):
        raise RestoreVerificationError(
            f"{label} must be unique and in canonical order"
        )
    if allowed is not None and not set(strings).issubset(allowed):
        raise RestoreVerificationError(f"{label} contains an unexpected value")
    return strings


def _validate_entries(
    manifest: Mapping[str, object],
) -> list[dict[str, object]]:
    raw_entries = _require_list(manifest.get("entries"), "entries")
    if not raw_entries or len(raw_entries) > MAX_MANIFEST_ENTRIES:
        raise RestoreVerificationError(
            "entries must contain between 1 and "
            f"{MAX_MANIFEST_ENTRIES} records"
    )
    entries: list[dict[str, object]] = []
    seen: dict[str, str] = {}
    implied_directories: dict[str, str] = {}
    for index, value in enumerate(raw_entries):
        row = _require_mapping(value, f"entries[{index}]")
        if set(row) != {"path", "scope", "plugin_id", "bytes", "sha256"}:
            raise RestoreVerificationError(
                f"entries[{index}] has an unexpected schema"
            )
        relative_path = _validate_relative_path(row["path"])
        folded = relative_path.casefold()
        previous = seen.get(folded)
        if previous is not None:
            raise RestoreVerificationError(
                f"duplicate or case-insensitive path collision: "
                f"{previous} and {relative_path}"
            )
        seen[folded] = relative_path
        components = relative_path.split("/")
        for depth in range(1, len(components)):
            directory = "/".join(components[:depth])
            directory_folded = directory.casefold()
            previous_directory = implied_directories.get(directory_folded)
            if (
                previous_directory is not None
                and previous_directory != directory
            ):
                raise RestoreVerificationError(
                    "case-insensitive implied-directory collision: "
                    f"{previous_directory} and {directory}"
                )
            implied_directories[directory_folded] = directory
        scope = row["scope"]
        if not isinstance(scope, str) or scope not in ALLOWED_SCOPES:
            raise RestoreVerificationError(
                f"entries[{index}] has invalid scope: {scope!r}"
            )
        plugin_id = row["plugin_id"]
        if scope == "project_plugin":
            if not isinstance(plugin_id, str) or not plugin_id:
                raise RestoreVerificationError(
                    f"entries[{index}] plugin scope requires plugin_id"
                )
        elif plugin_id is not None:
            raise RestoreVerificationError(
                f"entries[{index}] non-plugin scope forbids plugin_id"
            )
        byte_count = _require_exact_integer(
            row["bytes"],
            f"entries[{index}].bytes",
        )
        digest = _require_sha256(
            row["sha256"],
            f"entries[{index}].sha256",
        )
        entries.append(
            {
                "path": relative_path,
                "scope": scope,
                "plugin_id": plugin_id,
                "bytes": byte_count,
                "sha256": digest,
            }
        )
    expected_order = sorted(entries, key=lambda row: _sort_key(str(row["path"])))
    if entries != expected_order:
        raise RestoreVerificationError(
            "manifest entries are not in canonical path order"
        )
    for folded_path, path in seen.items():
        if folded_path in implied_directories:
            raise RestoreVerificationError(
                f"manifest file/directory prefix conflict: {path}"
            )
    descriptor_entries = [
        row for row in entries if row["scope"] == "project_descriptor"
    ]
    if len(descriptor_entries) != 1:
        raise RestoreVerificationError(
            "manifest must contain exactly one project descriptor"
        )
    if descriptor_entries[0]["path"] != PROJECT_DESCRIPTOR_NAME:
        raise RestoreVerificationError(
            "project descriptor entry must be Titan.uproject"
        )
    for row in entries:
        path = str(row["path"])
        if row["scope"] == "project_content" and not path.startswith("Content/"):
            raise RestoreVerificationError(
                f"project content path escapes Content: {path}"
            )
        if row["scope"] == "project_plugin" and not path.startswith("Plugins/"):
            raise RestoreVerificationError(
                f"project plugin path escapes Plugins: {path}"
            )
    return entries


def _validate_plugins(
    manifest: Mapping[str, object],
    entries: Sequence[Mapping[str, object]],
) -> None:
    plugins = _require_list(manifest.get("plugins"), "plugins")
    plugin_entries: dict[str, list[Mapping[str, object]]] = {}
    for row in entries:
        plugin_id = row["plugin_id"]
        if isinstance(plugin_id, str):
            plugin_entries.setdefault(plugin_id, []).append(row)
    observed_ids: dict[str, str] = {}
    observed_roots: dict[str, str] = {}
    observed_order: list[str] = []
    excluded_roots = {
        root.casefold() for root in EXPECTED_EXCLUDED_PLUGIN_ROOTS
    }
    for index, value in enumerate(plugins):
        plugin = _require_mapping(value, f"plugins[{index}]")
        if set(plugin) != EXPECTED_PLUGIN_KEYS:
            raise RestoreVerificationError(
                f"plugins[{index}] has an unexpected schema"
            )
        plugin_id = plugin.get("plugin_id")
        plugin_root = _validate_relative_path(plugin.get("plugin_root"))
        descriptor_path = _validate_relative_path(plugin.get("descriptor_path"))
        if not isinstance(plugin_id, str) or not plugin_id:
            raise RestoreVerificationError(
                f"plugins[{index}].plugin_id must be nonempty"
            )
        observed_order.append(plugin_id)
        for label, candidate, observed in (
            ("plugin_id", plugin_id, observed_ids),
            ("plugin_root", plugin_root, observed_roots),
        ):
            folded = candidate.casefold()
            if folded in observed:
                raise RestoreVerificationError(
                    f"duplicate case-insensitive {label}: "
                    f"{observed[folded]} and {candidate}"
                )
            observed[folded] = candidate
        if not plugin_root.startswith("Plugins/") or "/" in plugin_root[8:]:
            raise RestoreVerificationError(
                f"plugin root must be an immediate Plugins child: {plugin_root}"
            )
        if not descriptor_path.startswith(plugin_root + "/"):
            raise RestoreVerificationError(
                f"plugin descriptor escapes plugin root: {descriptor_path}"
            )
        descriptor_relative = descriptor_path[len(plugin_root) + 1 :]
        descriptor_name = Path(descriptor_relative)
        if (
            "/" in descriptor_relative
            or descriptor_name.suffix.casefold() != ".uplugin"
            or descriptor_name.stem != plugin_id
        ):
            raise RestoreVerificationError(
                "plugin descriptor must be the immediate matching .uplugin "
                f"child: {plugin_id}"
            )
        for key in ("friendly_name", "version_name", "created_by"):
            _require_optional_string(
                plugin.get(key),
                f"plugins[{index}].{key}",
            )
        for key in ("installed", "can_contain_content"):
            _require_optional_bool(
                plugin.get(key),
                f"plugins[{index}].{key}",
            )
        listed = plugin.get("listed_in_project_descriptor")
        if type(listed) is not bool:
            raise RestoreVerificationError(
                "plugins["
                f"{index}].listed_in_project_descriptor must be a boolean"
            )
        enabled = plugin.get("enabled_in_project_descriptor")
        if listed:
            if type(enabled) is not bool:
                raise RestoreVerificationError(
                    "plugins["
                    f"{index}].enabled_in_project_descriptor must be a boolean "
                    "when the plugin is listed"
                )
        elif enabled is not None:
            raise RestoreVerificationError(
                "plugins["
                f"{index}].enabled_in_project_descriptor must be null when "
                "the plugin is not listed"
            )
        _require_canonical_string_list(
            plugin.get("excluded_generated_top_level_directories_present"),
            (
                "plugins["
                f"{index}].excluded_generated_top_level_directories_present"
            ),
            allowed=frozenset(EXPECTED_EXCLUDED_PLUGIN_ROOTS),
        )
        members = plugin_entries.get(plugin_id, [])
        if not members:
            raise RestoreVerificationError(
                f"plugin has no manifest entries: {plugin_id}"
            )
        if any(
            not str(member["path"]).startswith(plugin_root + "/")
            for member in members
        ):
            raise RestoreVerificationError(
                f"plugin entry escapes declared root: {plugin_id}"
            )
        for member in members:
            member_relative = str(member["path"])[len(plugin_root) + 1 :]
            member_top_level = member_relative.split("/", 1)[0]
            if member_top_level.casefold() in excluded_roots:
                raise RestoreVerificationError(
                    "plugin entry uses an excluded generated plugin root: "
                    f"{member['path']}"
                )
        if _require_exact_integer(
            plugin.get("file_count"),
            f"plugins[{index}].file_count",
        ) != len(members):
            raise RestoreVerificationError(
                f"plugin file count mismatch: {plugin_id}"
            )
        if _require_exact_integer(
            plugin.get("bytes"),
            f"plugins[{index}].bytes",
        ) != sum(int(member["bytes"]) for member in members):
            raise RestoreVerificationError(
                f"plugin byte count mismatch: {plugin_id}"
            )
        if _require_sha256(
            plugin.get("signature_sha256"),
            f"plugins[{index}].signature_sha256",
        ) != _signature(members):
            raise RestoreVerificationError(
                f"plugin signature mismatch: {plugin_id}"
            )
        descriptor = next(
            (
                member
                for member in members
                if member["path"] == descriptor_path
            ),
            None,
        )
        if descriptor is None:
            raise RestoreVerificationError(
                f"plugin descriptor entry is missing: {descriptor_path}"
            )
        if _require_sha256(
            plugin.get("descriptor_sha256"),
            f"plugins[{index}].descriptor_sha256",
        ) != descriptor["sha256"]:
            raise RestoreVerificationError(
                f"plugin descriptor hash mismatch: {plugin_id}"
            )
    if observed_order != sorted(observed_order, key=_sort_key):
        raise RestoreVerificationError(
            "manifest plugins are not in canonical plugin ID order"
        )
    if set(plugin_entries) != {
        str(plugin["plugin_id"])
        for plugin in plugins
        if isinstance(plugin, dict)
    }:
        raise RestoreVerificationError(
            "manifest plugin records do not cover the exact plugin entry set"
        )


def _validate_manifest_structure(
    manifest: Mapping[str, object],
) -> list[dict[str, object]]:
    if set(manifest) != EXPECTED_TOP_LEVEL_KEYS:
        raise RestoreVerificationError(
            "storage manifest has an unexpected top-level schema"
        )
    if (
        type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 1
    ):
        raise RestoreVerificationError("unsupported storage manifest schema")
    if manifest.get("manifest_id") != MANIFEST_ID:
        raise RestoreVerificationError("unexpected storage manifest identity")
    if manifest.get("evidence_class") != "static":
        raise RestoreVerificationError(
            "storage manifest evidence class must remain static"
        )
    if manifest.get("status") != EXPECTED_MANIFEST_STATUS:
        raise RestoreVerificationError("unexpected storage manifest status")
    storage_verification = _require_mapping(
        manifest.get("storage_verification"),
        "storage_verification",
    )
    if (
        set(storage_verification) != set(EXPECTED_STORAGE_VERIFICATION)
        or any(
            type(storage_verification[key]) is not bool
            or storage_verification[key] is not expected
            for key, expected in EXPECTED_STORAGE_VERIFICATION.items()
        )
    ):
        raise RestoreVerificationError(
            "source manifest must remain manifest-only and externally unverified"
        )
    claim_limit = manifest.get("claim_limit")
    if not isinstance(claim_limit, str) or not claim_limit.strip():
        raise RestoreVerificationError(
            "storage manifest claim_limit must be nonempty"
        )
    selection = _require_mapping(
        manifest.get("selection_policy"),
        "selection_policy",
    )
    if selection != EXPECTED_SELECTION_POLICY:
        raise RestoreVerificationError(
            "manifest selection policy does not match the verifier contract"
        )
    entries = _validate_entries(manifest)
    _validate_plugins(manifest, entries)
    provenance = _require_mapping(manifest.get("provenance"), "provenance")
    if set(provenance) != {
        "builder_path",
        "builder_sha256",
        "signature_kind",
    }:
        raise RestoreVerificationError(
            "manifest provenance has an unexpected schema"
        )
    if provenance.get("builder_path") != (
        "Tools/build_redmmo_content_storage_manifest.py"
    ):
        raise RestoreVerificationError(
            "manifest builder path is unexpected"
        )
    _require_sha256(
        provenance.get("builder_sha256"),
        "provenance.builder_sha256",
    )
    if provenance.get("signature_kind") != (
        "sha256_sorted_canonical_json_tuples_path_bytes_sha256"
    ):
        raise RestoreVerificationError(
            "manifest signature kind is unexpected"
        )

    scope = _require_mapping(manifest.get("scope"), "scope")
    if set(scope) != {
        "file_count",
        "bytes",
        "signature_sha256",
        "path_set_signature_sha256",
        "scope_file_counts",
        "project_content_file_count",
        "project_content_bytes",
        "project_content_signature_sha256",
        "project_plugin_count",
        "tree_quiescent_during_scan",
    }:
        raise RestoreVerificationError(
            "manifest scope has an unexpected schema"
        )
    if _require_exact_integer(
        scope.get("file_count"),
        "scope.file_count",
    ) != len(entries):
        raise RestoreVerificationError("manifest file count mismatch")
    if _require_exact_integer(scope.get("bytes"), "scope.bytes") != sum(
        int(row["bytes"]) for row in entries
    ):
        raise RestoreVerificationError("manifest byte count mismatch")
    if _require_sha256(
        scope.get("signature_sha256"),
        "scope.signature_sha256",
    ) != _signature(entries):
        raise RestoreVerificationError("manifest payload signature mismatch")
    if _require_sha256(
        scope.get("path_set_signature_sha256"),
        "scope.path_set_signature_sha256",
    ) != _path_signature(entries):
        raise RestoreVerificationError("manifest path-set signature mismatch")
    expected_counts = dict(
        sorted(Counter(str(row["scope"]) for row in entries).items())
    )
    raw_scope_counts = _require_mapping(
        scope.get("scope_file_counts"),
        "scope.scope_file_counts",
    )
    validated_scope_counts = {
        key: _require_exact_integer(
            value,
            f"scope.scope_file_counts.{key}",
        )
        for key, value in raw_scope_counts.items()
    }
    if validated_scope_counts != expected_counts:
        raise RestoreVerificationError("manifest scope counts mismatch")
    content_entries = [
        row for row in entries if row["scope"] == "project_content"
    ]
    if _require_exact_integer(
        scope.get("project_content_file_count"),
        "scope.project_content_file_count",
    ) != len(content_entries):
        raise RestoreVerificationError(
            "manifest project-content file count mismatch"
        )
    if _require_exact_integer(
        scope.get("project_content_bytes"),
        "scope.project_content_bytes",
    ) != sum(
        int(row["bytes"]) for row in content_entries
    ):
        raise RestoreVerificationError(
            "manifest project-content byte count mismatch"
        )
    if scope.get("project_content_signature_sha256") != _signature(
        content_entries
    ):
        raise RestoreVerificationError(
            "manifest project-content signature mismatch"
        )
    if _require_exact_integer(
        scope.get("project_plugin_count"),
        "scope.project_plugin_count",
    ) != len(manifest["plugins"]):
        raise RestoreVerificationError("manifest project-plugin count mismatch")
    if scope.get("tree_quiescent_during_scan") is not True:
        raise RestoreVerificationError(
            "manifest does not attest a quiescent source scan"
        )

    by_path = {str(row["path"]): row for row in entries}
    identity = _require_mapping(
        manifest.get("project_identity"),
        "project_identity",
    )
    if set(identity) != {
        "descriptor_path",
        "descriptor_sha256",
        "engine_association",
        "module_names",
    }:
        raise RestoreVerificationError(
            "manifest project identity has an unexpected schema"
        )
    if identity.get("descriptor_path") != PROJECT_DESCRIPTOR_NAME:
        raise RestoreVerificationError(
            "project identity descriptor path is unexpected"
        )
    if identity.get("descriptor_sha256") != by_path[PROJECT_DESCRIPTOR_NAME][
        "sha256"
    ]:
        raise RestoreVerificationError(
            "project identity descriptor hash mismatch"
        )
    if identity.get("engine_association") != EXPECTED_ENGINE_ASSOCIATION:
        raise RestoreVerificationError(
            "project identity engine association is unexpected"
        )
    module_names = _require_canonical_string_list(
        identity.get("module_names"),
        "project_identity.module_names",
    )
    if EXPECTED_PROJECT_MODULE not in module_names:
        raise RestoreVerificationError(
            f"project identity must include module {EXPECTED_PROJECT_MODULE}"
        )
    protected = _require_list(
        manifest.get("protected_inputs"),
        "protected_inputs",
    )
    protected_paths: list[str] = []
    for index, value in enumerate(protected):
        record = _require_mapping(value, f"protected_inputs[{index}]")
        if set(record) != {
            "path",
            "expected_sha256",
            "observed_sha256",
            "matches",
        }:
            raise RestoreVerificationError(
                f"protected_inputs[{index}] has an unexpected schema"
            )
        path = _validate_relative_path(record.get("path"))
        protected_paths.append(path)
        entry = by_path.get(path)
        if entry is None:
            raise RestoreVerificationError(
                f"protected input is absent from manifest entries: {path}"
            )
        expected = _require_sha256(
            record.get("expected_sha256"),
            f"protected_inputs[{index}].expected_sha256",
        )
        observed = _require_sha256(
            record.get("observed_sha256"),
            f"protected_inputs[{index}].observed_sha256",
        )
        if record.get("matches") is not True:
            raise RestoreVerificationError(
                f"protected input is not marked matching: {path}"
            )
        if expected != observed or observed != entry["sha256"]:
            raise RestoreVerificationError(
                f"protected input hash mismatch: {path}"
            )
    if protected_paths != sorted(set(protected_paths), key=_sort_key):
        raise RestoreVerificationError(
            "protected inputs must be unique and in canonical path order"
        )
    return entries


def _read_manifest_from_stable_handle(
    handle: BinaryIO,
    path: Path,
    parent: Path,
    before: FileMetadata,
    native_before: WindowsHandleMetadata | None = None,
) -> tuple[bytes, str]:
    opened = _open_file_metadata(handle, path, "storage manifest")
    if opened != before:
        raise RestoreVerificationError(
            "storage manifest identity changed between validation and "
            "stable open"
        )
    if native_before is not None:
        opened_identity = (
            opened.device,
            opened.inode,
            opened.size,
            opened.link_count,
        )
        native_identity = (
            native_before.volume_serial,
            native_before.file_id,
            native_before.size,
            native_before.link_count,
        )
        if opened_identity != native_identity:
            raise RestoreVerificationError(
                "Windows storage manifest identity is inconsistent between "
                "native and Python handles"
            )
    path_before = _require_regular_file(
        path,
        parent,
        "storage manifest",
    )
    if path_before != opened:
        raise RestoreVerificationError(
            "storage manifest path changed after its stable handle opened"
        )
    if opened.size > MAX_MANIFEST_BYTES:
        raise RestoreVerificationError(
            f"storage manifest exceeds {MAX_MANIFEST_BYTES} bytes"
        )

    digest = hashlib.sha256()
    payload = bytearray()
    while True:
        block = handle.read(4 * 1024 * 1024)
        if not block:
            break
        payload.extend(block)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise RestoreVerificationError(
                f"storage manifest exceeds {MAX_MANIFEST_BYTES} bytes"
            )
        digest.update(block)

    after_read = _open_file_metadata(handle, path, "storage manifest")
    if after_read != opened or len(payload) != opened.size:
        raise RestoreVerificationError(
            "storage manifest changed while its stable handle was read"
        )
    if native_before is not None:
        try:
            import msvcrt

            native_after = _windows_require_plain_file_handle(
                msvcrt.get_osfhandle(handle.fileno()),
                "storage manifest",
            )
        except (OSError, ValueError) as error:
            raise RestoreVerificationError(
                "unable to revalidate the native storage manifest handle: "
                f"{error}"
            ) from error
        if native_after != native_before:
            raise RestoreVerificationError(
                "Windows storage manifest handle identity changed while read"
            )
    path_after = _require_regular_file(
        path,
        parent,
        "storage manifest",
    )
    if path_after != opened:
        raise RestoreVerificationError(
            "storage manifest path changed while its stable handle was read"
        )
    return bytes(payload), digest.hexdigest().upper()


def _read_authenticated_manifest_payload(
    path: Path,
    parent: Path,
) -> tuple[bytes, str]:
    if os.name != "nt":
        before = _require_regular_file(
            path,
            parent,
            "storage manifest",
        )
        try:
            with _open_binary_read(path) as handle:
                return _read_manifest_from_stable_handle(
                    handle,
                    path,
                    parent,
                    before,
                )
        except RestoreVerificationError:
            raise
        except (OSError, ValueError) as error:
            raise RestoreVerificationError(
                f"unable to read storage manifest: {path}: {error}"
            ) from error

    expected_parent = _metadata(parent)
    parent_handle: int | None = None
    manifest_handle: int | None = None
    descriptor: int | None = None
    try:
        parent_handle, parent_identity = _windows_open_pinned_directory(
            parent,
            expected_parent,
            "manifest parent",
            desired_access=WINDOWS_DIRECTORY_PIN_ACCESS,
            share_mode=WINDOWS_FILE_SHARE_READ | WINDOWS_FILE_SHARE_WRITE,
        )
        _windows_require_ntfs(parent_handle, "manifest parent")
        before = _require_regular_file(
            path,
            parent,
            "storage manifest",
        )
        manifest_handle = _windows_nt_open_manifest_relative(
            parent_handle,
            path.name,
        )
        native_before = _windows_require_plain_file_handle(
            manifest_handle,
            "storage manifest",
        )
        _windows_require_ntfs(manifest_handle, "storage manifest")
        if (
            native_before.identity_volume_serial
            != parent_identity.identity_volume_serial
        ):
            raise RestoreVerificationError(
                "storage manifest and its pinned parent are on different "
                "Windows volumes"
            )

        import msvcrt

        descriptor = msvcrt.open_osfhandle(
            manifest_handle,
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
        manifest_handle = None
        try:
            binary_handle = os.fdopen(descriptor, "rb", closefd=True)
        except BaseException:
            os.close(descriptor)
            descriptor = None
            raise
        descriptor = None
        with binary_handle:
            result = _read_manifest_from_stable_handle(
                binary_handle,
                path,
                parent,
                before,
                native_before,
            )

        parent_after = _require_plain_directory(
            parent,
            "manifest parent",
        )
        parent_path_identity = _metadata(parent_after)
        parent_handle_identity = _windows_require_plain_directory_handle(
            parent_handle,
            "manifest parent",
        )
        if (
            (
                parent_path_identity.device,
                parent_path_identity.inode,
            )
            != (
                parent_identity.volume_serial,
                parent_identity.file_id,
            )
            or parent_handle_identity != parent_identity
        ):
            raise RestoreVerificationError(
                "Windows manifest parent identity changed while the manifest "
                "was authenticated"
            )
        return result
    except RestoreVerificationError:
        raise
    except (OSError, ValueError) as error:
        raise RestoreVerificationError(
            f"unable to read storage manifest: {path}: {error}"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if manifest_handle is not None:
            _windows_close_handle(manifest_handle)
        if parent_handle is not None:
            _windows_close_handle(parent_handle)


def _parse_authenticated_manifest_payload(
    payload: bytes,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    try:
        manifest = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                RestoreVerificationError(
                    f"non-finite JSON number is forbidden: {value}"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RestoreVerificationError(
            f"storage manifest is not canonical UTF-8 JSON: {error}"
        ) from error
    if not isinstance(manifest, dict):
        raise RestoreVerificationError(
            "storage manifest root must be a JSON object"
        )
    canonical_payload = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if payload != canonical_payload:
        raise RestoreVerificationError(
            "storage manifest is not in canonical serialized form"
        )
    entries = _validate_manifest_structure(manifest)
    return manifest, entries


def load_authenticated_manifest(
    manifest_path: Path,
    expected_manifest_sha256: str,
) -> tuple[dict[str, object], list[dict[str, object]], str]:
    expected_digest = _require_sha256(
        (
            expected_manifest_sha256.upper()
            if isinstance(expected_manifest_sha256, str)
            else expected_manifest_sha256
        ),
        "expected manifest SHA-256",
    )
    lexical_path = manifest_path.absolute()
    parent = _require_plain_directory(
        lexical_path.parent,
        "manifest parent",
    )
    payload, observed_digest = _read_authenticated_manifest_payload(
        lexical_path,
        parent,
    )
    if observed_digest != expected_digest:
        raise RestoreVerificationError(
            "storage manifest SHA-256 mismatch: "
            f"expected={expected_digest} observed={observed_digest}"
        )
    manifest, entries = _parse_authenticated_manifest_payload(payload)
    return manifest, entries, observed_digest


def _bounded_canonical_json_snapshot(
    value: object,
    label: str,
) -> bytes:
    encoder = json.JSONEncoder(
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    payload = bytearray()
    try:
        for chunk in encoder.iterencode(value):
            encoded = chunk.encode("utf-8")
            if len(payload) + len(encoded) + 1 > MAX_MANIFEST_BYTES:
                raise RestoreVerificationError(
                    f"{label} exceeds the {MAX_MANIFEST_BYTES}-byte limit"
                )
            payload.extend(encoded)
    except RestoreVerificationError:
        raise
    except (OverflowError, RuntimeError, TypeError, ValueError) as error:
        raise RestoreVerificationError(
            f"{label} is not canonical JSON data: {error}"
        ) from error
    payload.extend(b"\n")
    return bytes(payload)


def _reauthenticate_direct_restore_inputs(
    manifest: Mapping[str, object],
    entries: Sequence[Mapping[str, object]],
    manifest_sha256: str,
) -> tuple[dict[str, object], list[dict[str, object]], str]:
    if type(manifest) is not dict:
        raise RestoreVerificationError(
            "direct manifest input must be a plain JSON object"
        )
    if type(entries) is not list:
        raise RestoreVerificationError(
            "direct entries input must be a plain JSON array"
        )

    expected_digest = _require_sha256(
        (
            manifest_sha256.upper()
            if isinstance(manifest_sha256, str)
            else manifest_sha256
        ),
        "expected manifest SHA-256",
    )
    manifest_payload = _bounded_canonical_json_snapshot(
        manifest,
        "direct manifest snapshot",
    )
    observed_digest = _sha256_bytes(manifest_payload)
    if observed_digest != expected_digest:
        raise RestoreVerificationError(
            "storage manifest SHA-256 mismatch: "
            f"expected={expected_digest} observed={observed_digest}"
        )

    detached_manifest, validated_entries = (
        _parse_authenticated_manifest_payload(manifest_payload)
    )
    supplied_entries_payload = _bounded_canonical_json_snapshot(
        entries,
        "direct entries snapshot",
    )
    validated_entries_payload = _bounded_canonical_json_snapshot(
        validated_entries,
        "authenticated manifest entries",
    )
    if supplied_entries_payload != validated_entries_payload:
        raise RestoreVerificationError(
            "direct entries do not exactly match authenticated manifest "
            "entries"
        )
    return detached_manifest, validated_entries, observed_digest


def _discover_restored_tree(
    restore_root: Path,
) -> tuple[list[RestoredFile], tuple[str, ...]]:
    pending = [restore_root]
    files: list[RestoredFile] = []
    directories: list[str] = []
    while pending:
        directory = pending.pop()
        try:
            children = list(os.scandir(directory))
        except OSError as error:
            raise RestoreVerificationError(
                f"unable to enumerate restored directory: {directory}: {error}"
            ) from error
        for child in sorted(children, key=lambda item: _sort_key(item.name)):
            path = Path(child.path)
            observed = _metadata(path)
            if _is_link_or_reparse(path, observed):
                raise RestoreVerificationError(
                    f"linked or reparse restored path is forbidden: {path}"
                )
            if stat.S_ISDIR(observed.mode):
                try:
                    path.resolve(strict=True).relative_to(restore_root)
                except (OSError, ValueError) as error:
                    raise RestoreVerificationError(
                        f"restored directory escapes restore root: {path}"
                    ) from error
                directories.append(
                    _validate_relative_path(
                        path.relative_to(restore_root).as_posix()
                    )
                )
                pending.append(path)
                continue
            if not stat.S_ISREG(observed.mode):
                raise RestoreVerificationError(
                    f"non-regular restored path is forbidden: {path}"
                )
            if observed.link_count != 1:
                raise RestoreVerificationError(
                    "hard-linked restored file is forbidden because alias "
                    f"topology is not authenticated: {path} "
                    f"links={observed.link_count}"
                )
            if _is_offline_or_recall(observed):
                raise RestoreVerificationError(
                    f"offline or recall-on-access restored file is "
                    f"forbidden: {path}"
                )
            try:
                relative_path = path.relative_to(restore_root).as_posix()
            except ValueError as error:
                raise RestoreVerificationError(
                    f"restored file escapes restore root: {path}"
                ) from error
            files.append(
                RestoredFile(
                    path=path,
                    relative_path=_validate_relative_path(relative_path),
                    metadata=observed,
                )
            )
    files.sort(key=lambda item: _sort_key(item.relative_path))
    seen: dict[str, str] = {}
    identities: dict[tuple[int, int], str] = {}
    for item in files:
        folded = item.relative_path.casefold()
        previous = seen.get(folded)
        if previous is not None:
            raise RestoreVerificationError(
                "duplicate or case-insensitive restored path collision: "
                f"{previous} and {item.relative_path}"
            )
        seen[folded] = item.relative_path
        identity = (item.metadata.device, item.metadata.inode)
        previous_identity = identities.get(identity)
        if previous_identity is not None:
            raise RestoreVerificationError(
                "duplicate restored file identity is forbidden: "
                f"{previous_identity} and {item.relative_path}"
            )
        identities[identity] = item.relative_path
    directory_seen: dict[str, str] = {}
    for directory in directories:
        folded = directory.casefold()
        previous = directory_seen.get(folded)
        if previous is not None and previous != directory:
            raise RestoreVerificationError(
                "case-insensitive restored directory collision: "
                f"{previous} and {directory}"
            )
        if folded in seen:
            raise RestoreVerificationError(
                f"restored file/directory conflict: {directory}"
            )
        directory_seen[folded] = directory
    return files, tuple(sorted(directories, key=_sort_key))


def _open_binary_read(path: Path) -> BinaryIO:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        return os.fdopen(descriptor, "rb", closefd=True)
    except BaseException:
        os.close(descriptor)
        raise


def _open_file_metadata(
    handle: BinaryIO,
    path: Path,
    label: str,
) -> FileMetadata:
    try:
        observed = _metadata_from_stat_result(os.fstat(handle.fileno()))
    except (OSError, ValueError) as error:
        raise RestoreVerificationError(
            f"unable to inspect open {label} handle: {path}: {error}"
        ) from error
    if _is_link_or_reparse(path, observed):
        raise RestoreVerificationError(
            f"linked or reparse open {label} handle is forbidden: {path}"
        )
    if not stat.S_ISREG(observed.mode):
        raise RestoreVerificationError(
            f"non-regular open {label} handle is forbidden: {path}"
        )
    if observed.link_count != 1:
        raise RestoreVerificationError(
            f"hard-linked open {label} handle is forbidden: {path} "
            f"links={observed.link_count}"
        )
    if _is_offline_or_recall(observed):
        raise RestoreVerificationError(
            f"offline or recall-on-access open {label} handle is forbidden: "
            f"{path}"
        )
    if observed.inode <= 0:
        raise RestoreVerificationError(
            f"stable identity is unavailable for open {label} handle: {path}"
        )
    return observed


def _sha256_file(
    path: Path,
    expected_metadata: FileMetadata | None = None,
    root: Path | None = None,
) -> str:
    if (expected_metadata is None) != (root is None):
        raise RestoreVerificationError(
            "expected metadata and root must be supplied together"
        )
    digest = hashlib.sha256()
    bytes_read = 0
    try:
        with _open_binary_read(path) as handle:
            opened = _open_file_metadata(handle, path, "restored file")
            if expected_metadata is not None and opened != expected_metadata:
                raise RestoreVerificationError(
                    f"restored file identity changed before hashing: {path}"
                )
            if root is not None:
                path_before = _require_regular_file(
                    path,
                    root,
                    "restored file",
                )
                if path_before != opened:
                    raise RestoreVerificationError(
                        "restored file path does not name the stable open "
                        f"handle before hashing: {path}"
                    )
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(block)
                bytes_read += len(block)
            after_read = _open_file_metadata(handle, path, "restored file")
            if after_read != opened or bytes_read != opened.size:
                raise RestoreVerificationError(
                    f"restored file changed through its stable handle while "
                    f"hashing: {path}"
                )
            if root is not None:
                path_after = _require_regular_file(
                    path,
                    root,
                    "restored file",
                )
                if path_after != opened:
                    raise RestoreVerificationError(
                        "restored file path no longer names the stable open "
                        f"handle after hashing: {path}"
                    )
    except RestoreVerificationError:
        raise
    except (OSError, ValueError) as error:
        raise RestoreVerificationError(
            f"unable to hash restored file: {path}: {error}"
        ) from error
    return digest.hexdigest().upper()


def _restored_snapshot(
    files: Sequence[RestoredFile],
) -> dict[str, FileMetadata]:
    return {item.relative_path: item.metadata for item in files}


def verify_isolated_restore(
    manifest: Mapping[str, object],
    entries: Sequence[Mapping[str, object]],
    manifest_sha256: str,
    restore_root: Path,
) -> dict[str, object]:
    restore_root = _require_plain_directory(restore_root, "restore root")
    project_root = _require_plain_directory(
        EXPECTED_PROJECT_ROOT,
        "active Unreal project",
    )
    if _paths_overlap(restore_root, project_root):
        raise RestoreVerificationError(
            "restore root must be isolated from the active Unreal project"
        )
    manifest, entries, manifest_sha256 = (
        _reauthenticate_direct_restore_inputs(
            manifest,
            entries,
            manifest_sha256,
        )
    )
    discovered_before, directories_before = _discover_restored_tree(
        restore_root
    )
    before_snapshot = _restored_snapshot(discovered_before)
    expected_by_path = {str(row["path"]): row for row in entries}
    expected_directories = {
        "/".join(path.split("/")[:depth])
        for path in expected_by_path
        for depth in range(1, len(path.split("/")))
    }
    observed_directories = set(directories_before)
    missing_directories = sorted(
        expected_directories - observed_directories,
        key=_sort_key,
    )
    unexpected_directories = sorted(
        observed_directories - expected_directories,
        key=_sort_key,
    )
    if missing_directories or unexpected_directories:
        raise RestoreVerificationError(
            "restored directory set differs from manifest-implied topology: "
            f"missing={missing_directories[:5]} "
            f"unexpected={unexpected_directories[:5]}"
        )
    observed_paths = {item.relative_path for item in discovered_before}
    expected_paths = set(expected_by_path)
    missing = sorted(expected_paths - observed_paths, key=_sort_key)
    unexpected = sorted(observed_paths - expected_paths, key=_sort_key)
    if missing or unexpected:
        raise RestoreVerificationError(
            "restored path set differs from manifest: "
            f"missing={missing[:5]} unexpected={unexpected[:5]}"
        )

    observed_entries: list[dict[str, object]] = []
    for item in discovered_before:
        expected = expected_by_path[item.relative_path]
        if item.metadata.size != expected["bytes"]:
            raise RestoreVerificationError(
                f"restored byte count mismatch: {item.relative_path} "
                f"expected={expected['bytes']} observed={item.metadata.size}"
            )
        digest = _sha256_file(
            item.path,
            item.metadata,
            restore_root,
        )
        after_hash = _require_regular_file(
            item.path,
            restore_root,
            "restored file",
        )
        if after_hash != item.metadata:
            raise RestoreVerificationError(
                f"restored file changed while hashing: {item.relative_path}"
            )
        if digest != expected["sha256"]:
            raise RestoreVerificationError(
                f"restored SHA-256 mismatch: {item.relative_path} "
                f"expected={expected['sha256']} observed={digest}"
            )
        observed_entries.append(
            {
                "path": item.relative_path,
                "bytes": item.metadata.size,
                "sha256": digest,
            }
        )

    discovered_after, directories_after = _discover_restored_tree(restore_root)
    if (
        before_snapshot != _restored_snapshot(discovered_after)
        or directories_before != directories_after
    ):
        raise RestoreVerificationError(
            "restored tree changed during verification"
        )
    expected_signature = str(manifest["scope"]["signature_sha256"])
    observed_signature = _signature(observed_entries)
    expected_path_signature = str(
        manifest["scope"]["path_set_signature_sha256"]
    )
    observed_path_signature = _path_signature(observed_entries)
    if observed_signature != expected_signature:
        raise RestoreVerificationError(
            "restored aggregate signature differs from manifest"
        )
    if observed_path_signature != expected_path_signature:
        raise RestoreVerificationError(
            "restored path-set signature differs from manifest"
        )
    return {
        "schema_version": 1,
        "report_id": REPORT_ID,
        "evidence_class": "static",
        "status": "isolated_tree_matches_authenticated_manifest_acl_unverified",
        "manifest": {
            "manifest_id": manifest["manifest_id"],
            "manifest_sha256": manifest_sha256,
            "payload_signature_sha256": expected_signature,
            "path_set_signature_sha256": expected_path_signature,
            "file_count": len(entries),
            "bytes": sum(int(row["bytes"]) for row in entries),
        },
        "restore": {
            "root": str(restore_root),
            "file_count": len(observed_entries),
            "bytes": sum(int(row["bytes"]) for row in observed_entries),
            "payload_signature_sha256": observed_signature,
            "path_set_signature_sha256": observed_path_signature,
            "exact_path_set": True,
            "exact_manifest_implied_directory_set": True,
            "every_file_rehashed": True,
            "stable_opened_file_identity_hashing": True,
            "tree_quiescent_during_scan": True,
            "links_reparse_non_regular_and_hardlinks_rejected": True,
        },
        "storage_verification": {
            "manifest_authenticated_by_caller_supplied_digest": True,
            "isolated_restore_rehashed": True,
            "payload_copied_by_this_tool": False,
            "external_storage_origin_verified": False,
            "external_storage_access_control_verified": False,
        },
        "claim_limit": (
            "This report proves only that one isolated filesystem tree matched "
            "one private canonical manifest snapshot byte-for-byte when scanned. "
            "The direct API reauthenticated that snapshot against the supplied "
            "manifest SHA-256, reran the complete semantic manifest contract, "
            "and bound the separately supplied entries to the manifest before "
            "the filesystem scan. Trust still depends on the expected manifest "
            "SHA-256 being supplied from an independent trusted record. The "
            "direct API does not prove original raw-file encoding, duplicate-key "
            "history, path identity, or file origin; the CLI's stable-handle "
            "loader remains the raw manifest-file boundary. The tool does not "
            "copy payloads, "
            "identify external-storage origin, inspect ACLs, owners, timestamps, "
            "named NTFS streams, original empty-directory topology, or prove "
            "backup durability. The CLI uses stable filesystem identities at "
            "isolation-validation time to reject the tested normal and extended "
            "DOS namespace aliases, and rejects UNC, device, volume-GUID, DFS, "
            "and mapped-share paths as unsupported. Windows report publication "
            "pins one validated local-NTFS diagnostics-root handle, traverses or "
            "creates report-parent components relative to retained handles, "
            "creates and flushes one exclusive temporary-file handle, and uses "
            "that handle plus its retained parent for atomic no-clobber "
            "publication and failure cleanup. This binds only report creation "
            "and publication; broader restore-tree directory walks remain "
            "path-based. Stable opened-handle identity checks close the tested "
            "path-replacement ABA at the hash boundary, but the path-based scanner "
            "does not pin parent directories or close every privileged namespace "
            "or in-place mutation race. It is not license, dependency, Unreal load "
            "or save, build, runtime, visual, gameplay, package, Steam, or "
            "multiplayer evidence."
        ),
    }


def report_bytes(report: Mapping[str, object]) -> bytes:
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_output_path(
    output_path: Path,
    *,
    diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT,
    restore_root: Path | None = None,
) -> Path:
    lexical_root = diagnostics_root.absolute()
    lexical_output = output_path.absolute()
    if lexical_output.suffix.casefold() != ".json":
        raise RestoreVerificationError(
            f"output must use a .json suffix: {lexical_output}"
        )
    try:
        lexical_output.relative_to(lexical_root)
    except ValueError as error:
        raise RestoreVerificationError(
            f"output is restricted to diagnostics root {lexical_root}: "
            f"{lexical_output}"
        ) from error
    if _lexists(lexical_output):
        raise RestoreVerificationError(
            f"refusing to overwrite output: {lexical_output}"
        )
    cursor = lexical_output.parent
    while True:
        if _lexists(cursor) and _is_link_or_reparse(cursor):
            raise RestoreVerificationError(
                f"linked or reparse output ancestor is forbidden: {cursor}"
            )
        if cursor == lexical_root:
            break
        if cursor.parent == cursor:
            raise RestoreVerificationError(
                f"output ancestor did not reach diagnostics root: "
                f"{lexical_output}"
            )
        cursor = cursor.parent
    resolved_root = _require_plain_directory(
        lexical_root,
        "diagnostics root",
    )
    resolved_output = lexical_output.resolve()
    try:
        resolved_output.relative_to(resolved_root)
    except ValueError as error:
        raise RestoreVerificationError(
            f"resolved output escapes diagnostics root {resolved_root}: "
            f"{resolved_output}"
        ) from error
    if restore_root is not None:
        resolved_restore = _require_plain_directory(
            restore_root,
            "restore root",
        )
        if _paths_overlap(resolved_output, resolved_restore):
            raise RestoreVerificationError(
                "report output must remain outside the restored tree"
            )
    return resolved_output


def _write_report_atomic_windows(
    output_path: Path,
    payload: bytes,
    diagnostics_root: Path,
) -> None:
    _validate_windows_component(output_path.name, "report filename")
    with _windows_pinned_output_parent(
        output_path,
        diagnostics_root,
    ) as (parent_handle, parent_identity):
        temporary_handle: int | None = None
        for _ in range(16):
            candidate = (
                f".redmmo-restore-report-{secrets.token_hex(16)}.tmp"
            )
            _emit_publication_checkpoint(
                "before_temp_create",
                candidate_name=candidate,
                payload_size=len(payload),
            )
            try:
                temporary_handle, _ = _windows_nt_create_relative(
                    parent_handle,
                    candidate,
                    directory=False,
                )
                break
            except RestoreVerificationError as error:
                if "WinError=183" not in str(error):
                    raise
        if temporary_handle is None:
            raise RestoreVerificationError(
                "unable to allocate a unique Windows report temporary file"
            )

        committed = False
        try:
            opened = _windows_handle_metadata(
                temporary_handle,
                "report temporary file",
            )
            _emit_publication_checkpoint(
                "after_temp_create",
                candidate_name=candidate,
                payload_size=len(payload),
                identity=opened,
            )
            if (
                opened.attributes
                & (
                    WINDOWS_FILE_ATTRIBUTE_DIRECTORY
                    | WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
                )
                or opened.link_count != 1
                or opened.size != 0
            ):
                raise RestoreVerificationError(
                    "new Windows report temporary handle has unsafe metadata"
                )
            _windows_write_and_flush(temporary_handle, payload)
            written = _windows_handle_metadata(
                temporary_handle,
                "written report temporary file",
            )
            if (
                (
                    written.identity_volume_serial,
                    written.file_id_128,
                )
                != (
                    opened.identity_volume_serial,
                    opened.file_id_128,
                )
                or written.size != len(payload)
                or written.link_count != 1
                or written.attributes & WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise RestoreVerificationError(
                    "Windows report temporary file changed before publication"
                )
            _emit_publication_checkpoint(
                "after_preflush_before_rename",
                candidate_name=candidate,
                payload_size=len(payload),
                bytes_written=written.size,
                identity=written,
            )
            _windows_publish_open_file_no_clobber(
                temporary_handle,
                parent_handle,
                output_path.name,
            )
            _emit_publication_checkpoint(
                "after_postflush_before_final_validation",
                candidate_name=candidate,
                payload_size=len(payload),
                bytes_written=written.size,
                identity=written,
            )

            path_parent = _metadata(output_path.parent)
            if (
                not stat.S_ISDIR(path_parent.mode)
                or _is_link_or_reparse(output_path.parent, path_parent)
                or (path_parent.device, path_parent.inode)
                != (
                    parent_identity.volume_serial,
                    parent_identity.file_id,
                )
            ):
                raise RestoreVerificationError(
                    "Windows report parent path no longer names the pinned "
                    "publication directory"
                )
            published = _metadata(output_path)
            if (
                not stat.S_ISREG(published.mode)
                or _is_link_or_reparse(output_path, published)
                or published.link_count != 1
                or published.size != len(payload)
                or (published.device, published.inode)
                != (written.volume_serial, written.file_id)
            ):
                raise RestoreVerificationError(
                    "published Windows report path does not name the flushed "
                    "temporary-file identity"
                )
            _emit_publication_checkpoint(
                "after_final_validation_before_return",
                candidate_name=candidate,
                payload_size=len(payload),
                bytes_written=published.size,
                identity=written,
            )
            committed = True
        finally:
            try:
                if not committed:
                    _windows_delete_open_file_on_close(temporary_handle)
            finally:
                _windows_close_handle(temporary_handle)


def write_report_atomic(
    output_path: Path,
    payload: bytes,
    *,
    diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT,
    restore_root: Path | None = None,
) -> Path:
    validated_output = validate_output_path(
        output_path,
        diagnostics_root=diagnostics_root,
        restore_root=restore_root,
    )
    if os.name == "nt":
        _write_report_atomic_windows(
            validated_output,
            payload,
            diagnostics_root,
        )
        return validated_output

    raise RestoreVerificationError(
        "report publication requires Windows local NTFS so output creation, "
        "publication, and cleanup remain bound to one validated parent handle"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--restore-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    validate_input_isolation(
        args.manifest,
        args.restore_root,
    )
    output_path = validate_output_path(
        args.output,
        restore_root=args.restore_root,
    )
    manifest, entries, manifest_sha256 = load_authenticated_manifest(
        args.manifest,
        args.expected_manifest_sha256,
    )
    report = verify_isolated_restore(
        manifest,
        entries,
        manifest_sha256,
        args.restore_root,
    )
    output_path = validate_output_path(
        args.output,
        restore_root=args.restore_root,
    )
    output_path = write_report_atomic(
        output_path,
        report_bytes(report),
        restore_root=args.restore_root,
    )
    restored = report["restore"]
    print(
        "REDMMO_CONTENT_STORAGE_RESTORE_OK "
        f"files={restored['file_count']} "
        f"bytes={restored['bytes']} "
        f"signature={restored['payload_signature_sha256']} "
        f"output={output_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RestoreVerificationError as error:
        print(
            f"REDMMO_CONTENT_STORAGE_RESTORE_FAILED {error}",
            file=os.sys.stderr,
        )
        raise SystemExit(2)
