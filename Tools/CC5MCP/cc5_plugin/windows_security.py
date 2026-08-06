"""Windows-only storage and ACL checks for the local CC5 bridge.

This module is deliberately Python 3.8 and standard-library compatible so the
same checks run in both the external MCP process and Character Creator.
"""

import ctypes
import os
import stat
from pathlib import Path
from ctypes import wintypes


FIXED_STORAGE_ROOT = Path(r"D:\RedMMOTitanWindowsData\CC5MCPBridge")
_FILE_ATTRIBUTE_REPARSE_POINT = getattr(
    stat,
    "FILE_ATTRIBUTE_REPARSE_POINT",
    0x400,
)
_SE_FILE_OBJECT = 1
_OWNER_SECURITY_INFORMATION = 0x00000001
_DACL_SECURITY_INFORMATION = 0x00000004
_SE_DACL_PROTECTED = 0x1000
_ACL_SIZE_INFORMATION_CLASS = 2
_ACCESS_ALLOWED_ACE_TYPE = 0
_ACCESS_DENIED_ACE_TYPE = 1
_TOKEN_QUERY = 0x0008
_TOKEN_USER_CLASS = 1
_DRIVE_FIXED = 3
_MOVEFILE_WRITE_THROUGH = 0x00000008
_ERROR_FILE_EXISTS = 80
_ERROR_ALREADY_EXISTS = 183


class WindowsSecurityError(Exception):
    pass


def _windows_apis():
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetDriveTypeW.restype = wintypes.UINT
    kernel32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    kernel32.GetVolumeInformationW.restype = wintypes.BOOL
    kernel32.MoveFileExW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
    ]
    kernel32.MoveFileExW.restype = wintypes.BOOL
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi32.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ushort),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetSecurityDescriptorControl.restype = wintypes.BOOL
    advapi32.GetAclInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_int,
    ]
    advapi32.GetAclInformation.restype = wintypes.BOOL
    advapi32.GetAce.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetAce.restype = wintypes.BOOL
    return advapi32, kernel32


def _normal(value):
    text = os.path.normcase(os.path.normpath(str(value)))
    if text.startswith("\\\\?\\unc\\"):
        text = "\\\\" + text[8:]
    elif text.startswith("\\\\?\\"):
        text = text[4:]
    return text


def _lexical_absolute(value):
    if not isinstance(value, (str, os.PathLike)):
        raise WindowsSecurityError("Path must be text.")
    text = os.fspath(value)
    if not text or text.startswith(("\\\\", "//", "\\\\?\\", "\\\\.\\")):
        raise WindowsSecurityError("UNC and device paths are not permitted.")
    path = Path(text)
    if not path.is_absolute():
        raise WindowsSecurityError("Path must be absolute.")
    return Path(os.path.abspath(text))


def _is_below(path, root, allow_equal=False):
    try:
        common = Path(os.path.commonpath([str(path), str(root)]))
    except ValueError:
        return False
    if _normal(common) != _normal(root):
        return False
    return allow_equal or _normal(path) != _normal(root)


def _existing_components(path, root):
    relative = path.relative_to(root)
    current = root
    yield current
    for part in relative.parts:
        current = current / part
        if current.exists():
            yield current
        else:
            break


def _has_reparse_attribute(path):
    try:
        attributes = getattr(os.lstat(str(path)), "st_file_attributes", 0)
    except OSError as exc:
        raise WindowsSecurityError("Could not inspect bridge storage.") from exc
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


def secure_storage_path(
    value,
    *,
    storage_root=FIXED_STORAGE_ROOT,
    label="storage path",
    allow_root=False
):
    """Return an absolute child while refusing every existing reparse point."""

    root = _lexical_absolute(storage_root)
    path = _lexical_absolute(value)
    if not _is_below(path, root, allow_equal=allow_root):
        raise WindowsSecurityError("%s is outside the fixed bridge root." % label)
    if _normal(Path(os.path.realpath(str(root)))) != _normal(root):
        raise WindowsSecurityError("The fixed bridge root is a reparse path.")
    for component in _existing_components(path, root):
        if _has_reparse_attribute(component):
            raise WindowsSecurityError("%s contains a reparse point." % label)
    if _normal(Path(os.path.realpath(str(path)))) != _normal(path):
        raise WindowsSecurityError("%s resolves through a reparse point." % label)
    return path


def secure_child(
    value,
    root,
    *,
    storage_root=FIXED_STORAGE_ROOT,
    label="storage child"
):
    secured_root = secure_storage_path(
        root,
        storage_root=storage_root,
        label="%s root" % label,
        allow_root=True,
    )
    secured_path = secure_storage_path(
        value,
        storage_root=storage_root,
        label=label,
        allow_root=False,
    )
    if not _is_below(secured_path, secured_root):
        raise WindowsSecurityError("%s is outside its configured root." % label)
    return secured_path


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Sid", ctypes.c_void_p),
        ("Attributes", wintypes.DWORD),
    ]


class _TOKEN_USER(ctypes.Structure):
    _fields_ = [("User", _SID_AND_ATTRIBUTES)]


class _ACL_SIZE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("AceCount", wintypes.DWORD),
        ("AclBytesInUse", wintypes.DWORD),
        ("AclBytesFree", wintypes.DWORD),
    ]


class _ACE_HEADER(ctypes.Structure):
    _fields_ = [
        ("AceType", ctypes.c_ubyte),
        ("AceFlags", ctypes.c_ubyte),
        ("AceSize", ctypes.c_ushort),
    ]


def _sid_text(advapi32, kernel32, sid):
    if not sid:
        raise WindowsSecurityError("A required Windows SID is missing.")
    output = wintypes.LPWSTR()
    if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(output)):
        raise WindowsSecurityError("Could not convert a Windows SID.")
    try:
        return str(output.value)
    finally:
        kernel32.LocalFree(ctypes.cast(output, ctypes.c_void_p))


def _current_user_sid(advapi32, kernel32):
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(),
        _TOKEN_QUERY,
        ctypes.byref(token),
    ):
        raise WindowsSecurityError("Could not inspect the current Windows token.")
    try:
        required = wintypes.DWORD()
        advapi32.GetTokenInformation(
            token,
            _TOKEN_USER_CLASS,
            None,
            0,
            ctypes.byref(required),
        )
        if not required.value:
            raise WindowsSecurityError("Windows returned no token-user data.")
        buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token,
            _TOKEN_USER_CLASS,
            buffer,
            required.value,
            ctypes.byref(required),
        ):
            raise WindowsSecurityError("Could not read the current Windows user SID.")
        token_user = ctypes.cast(buffer, ctypes.POINTER(_TOKEN_USER)).contents
        return _sid_text(advapi32, kernel32, token_user.User.Sid)
    finally:
        kernel32.CloseHandle(token)


def require_private_windows_acl(path, *, require_protected=False, single_link=False):
    """Fail unless only this user, SYSTEM, and Administrators have allow ACEs."""

    if os.name != "nt":
        raise WindowsSecurityError("The CC5 bridge requires Windows ACL support.")
    checked = Path(path)
    if not checked.exists():
        raise WindowsSecurityError("Required private bridge storage is missing.")
    if _has_reparse_attribute(checked):
        raise WindowsSecurityError("Private bridge storage cannot be a reparse point.")
    if single_link and checked.is_file() and os.stat(str(checked)).st_nlink != 1:
        raise WindowsSecurityError("The bridge config must have exactly one hard link.")

    advapi32, kernel32 = _windows_apis()
    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    security_descriptor = ctypes.c_void_p()
    result = advapi32.GetNamedSecurityInfoW(
        str(checked),
        _SE_FILE_OBJECT,
        _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(security_descriptor),
    )
    if result != 0 or not security_descriptor:
        raise WindowsSecurityError("Could not read the bridge storage ACL.")
    try:
        current_sid = _current_user_sid(advapi32, kernel32)
        owner_sid = _sid_text(advapi32, kernel32, owner)
        if owner_sid.lower() != current_sid.lower():
            raise WindowsSecurityError(
                "Private bridge storage must be owned by the current Windows user."
            )
        if not dacl:
            raise WindowsSecurityError("Private bridge storage has a null DACL.")

        control = ctypes.c_ushort()
        revision = wintypes.DWORD()
        if not advapi32.GetSecurityDescriptorControl(
            security_descriptor,
            ctypes.byref(control),
            ctypes.byref(revision),
        ):
            raise WindowsSecurityError("Could not inspect ACL inheritance control.")
        if require_protected and not (control.value & _SE_DACL_PROTECTED):
            raise WindowsSecurityError(
                "The bridge root ACL must have inheritance disabled."
            )

        info = _ACL_SIZE_INFORMATION()
        if not advapi32.GetAclInformation(
            dacl,
            ctypes.byref(info),
            ctypes.sizeof(info),
            _ACL_SIZE_INFORMATION_CLASS,
        ):
            raise WindowsSecurityError("Could not enumerate the bridge DACL.")
        allowed_sids = {
            current_sid.lower(),
            "s-1-5-18",
            "s-1-5-32-544",
        }
        current_user_allowed = False
        for index in range(info.AceCount):
            ace = ctypes.c_void_p()
            if not advapi32.GetAce(dacl, index, ctypes.byref(ace)):
                raise WindowsSecurityError("Could not inspect a bridge DACL entry.")
            header = ctypes.cast(ace, ctypes.POINTER(_ACE_HEADER)).contents
            if header.AceType == _ACCESS_DENIED_ACE_TYPE:
                continue
            if header.AceType != _ACCESS_ALLOWED_ACE_TYPE or header.AceSize < 12:
                raise WindowsSecurityError(
                    "Private bridge storage has an unsupported allow ACE."
                )
            sid_pointer = ctypes.c_void_p(ace.value + 8)
            sid = _sid_text(advapi32, kernel32, sid_pointer).lower()
            if sid not in allowed_sids:
                raise WindowsSecurityError(
                    "Private bridge storage grants access to another principal."
                )
            if sid == current_sid.lower():
                current_user_allowed = True
        if not current_user_allowed:
            raise WindowsSecurityError(
                "Private bridge storage does not grant the current user access."
            )
    finally:
        kernel32.LocalFree(security_descriptor)
    return checked


def require_fixed_ntfs_storage(path):
    if os.name != "nt":
        raise WindowsSecurityError("The CC5 bridge requires Windows storage.")
    checked = _lexical_absolute(path)
    drive = checked.drive + "\\"
    _, kernel32 = _windows_apis()
    if kernel32.GetDriveTypeW(drive) != _DRIVE_FIXED:
        raise WindowsSecurityError("Bridge storage must be on a fixed local drive.")
    filesystem = ctypes.create_unicode_buffer(64)
    if not kernel32.GetVolumeInformationW(
        drive,
        None,
        0,
        None,
        None,
        None,
        filesystem,
        len(filesystem),
    ):
        raise WindowsSecurityError("Could not inspect the bridge filesystem.")
    if filesystem.value.upper() != "NTFS":
        raise WindowsSecurityError("Bridge storage must use NTFS.")
    return checked


def publish_file_no_replace(source, target):
    """Move one private NTFS file without ever replacing the destination."""

    if os.name != "nt":
        raise WindowsSecurityError("No-clobber publication requires Windows.")
    _, kernel32 = _windows_apis()
    if kernel32.MoveFileExW(
        str(source),
        str(target),
        _MOVEFILE_WRITE_THROUGH,
    ):
        return
    error = ctypes.get_last_error()
    if error in (_ERROR_FILE_EXISTS, _ERROR_ALREADY_EXISTS):
        raise FileExistsError(str(target))
    raise WindowsSecurityError(
        "Windows could not publish the project snapshot without replacement."
    )
