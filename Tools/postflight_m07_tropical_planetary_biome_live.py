"""Read-only postflight verifier for the M07 Tropical live scratch run.

This script authenticates evidence emitted by
``validate_m07_tropical_planetary_biome_stage_live.py``.  It never imports
Unreal, opens or writes a package, controls a process, or changes project
content.  Its only output is one no-clobber JSON report in the supplied run
directory.

The ``real_gpu_visual`` evidence class is awarded only when all hard gates
pass, including exact screenshot structure, D3D12/SM6/RTX 3080 log evidence,
the expected RED markers, and all pinned file identities.  Warning-only
MM_Sun, RVT, and foliage findings remain visible without being promoted to
hard failures.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
import re
import stat
import struct
import sys
import time
import zlib
from pathlib import Path
from typing import Any, Sequence


DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
EXPECTED_PROJECT_ROOT = Path(
    r"D:\RedMMOTitanWindowsData\Scratch\TropBiomeV1A"
)
EXPECTED_PRODUCTION_ROOT = Path(r"D:\RedMMOTitan")
EXPECTED_EDITOR_EXE = Path(
    r"D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
)
EXPECTED_LIVE_VALIDATOR = Path(
    r"D:\RedMMOTitan\Tools\validate_m07_tropical_planetary_biome_stage_live.py"
)
EXPECTED_LIVE_VALIDATOR_SHA256 = (
    "28D4501073A74C36FCAD7A4E75A1F0561F55F898757C5AF12C1D9FF96BFA8503"
)

LIVE_AUDIT_FILENAME = "live_validation_audit.json"
POSTFLIGHT_FILENAME = "postflight_validation.json"
BACKUP_FILENAME = (
    "pre_snap_RedPlanetGen_50km_FusedPrototype_"
    "M07_TropicalBiomeStage_V1_FBB0EED0191099B99.umap"
)
SCREENSHOT_FILENAMES = (
    "M07_TropicalBiomeStage_ground.png",
    "M07_TropicalBiomeStage_curvature.png",
    "M07_TropicalBiomeStage_horizon.png",
)
SCREENSHOT_VIEW_NAMES = ("ground", "curvature", "horizon")
EXPECTED_SCREENSHOT_WIDTH = 1920
EXPECTED_SCREENSHOT_HEIGHT = 1080

DESTINATION_MAP = (
    "/Game/RedMMO/Maps/Tests/"
    "RedPlanetGen_50km_FusedPrototype_M07_TropicalBiomeStage_V1"
)
DESTINATION_MAP_RELATIVE = Path(
    "Content",
    "RedMMO",
    "Maps",
    "Tests",
    "RedPlanetGen_50km_FusedPrototype_M07_TropicalBiomeStage_V1.umap",
)
EXPECTED_PRE_SNAP_MAP_SHA256 = (
    "FBB0EED0191099B99833CA829834BA08DB5786204ED27A04BA38F053B4F1B491"
)
EXPECTED_PRE_SNAP_MAP_BYTES = 12_497_095
EXPECTED_AUTHORING_AUDIT_SHA256 = (
    "1A1A0A98030D1A7BC6AE1F2617805E9E1080D367051266BFCFF04335CA446ADA"
)

PROTECTED_PROJECT_FILES = {
    Path("Content/RedMMO/Maps/RedPlanetGen.umap"):
        "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724",
    Path("Content/RedMMO/Maps/RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path("Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path("Content/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield.uasset"):
        "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562",
}

VENDOR_ROOT_FILES = {
    Path("Content/Zenscape_Island/Model/Rocks/SM_Cliff_01.uasset"):
        (316_046, "49A14C32F6F36AF8853337D9714754E318D6AAA7A312AC548090256F17E9EE1D"),
    Path("Content/Zenscape_Island/Model/Tree/SM_CoconutTree_01.uasset"):
        (152_377, "925C3DA342358836CEB7F6EAC0933D2B2742459C0F39CB1FFA8D5EA9E4FE82F9"),
    Path("Content/Zenscape_Island/Model/Plants/SM_Plant_01.uasset"):
        (56_344, "B169632CBB5B73C27616143437B9FD046542260EC60E901E08326453CD46FD7E"),
    Path("Content/Zenscape_Island/Model/Plants/SM_Coral_01.uasset"):
        (23_931, "D3889034815975E9819CF9439FB657E0D04E139A0EF95555EFA6DE9F8C877CEA"),
    Path("Content/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_BaseColor.uasset"):
        (4_915_934, "912E9BFFC157BD7FD785520815300EBD08BFA64DA934322E91123DFA31E6D705"),
    Path(
        "Content/Zenscape_Island/Texture/Landscape/"
        "T_Sand_Stylized_Normalsand_04_normal_dx_2k.uasset"
    ):
        (4_442_298, "7EC9E59A8DE4599BFBC0CA8C14A203CFF15B62D29CEF6032688C8F1AF4B53581"),
    Path("Content/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_Height.uasset"):
        (5_191_408, "AB49F8B8DE2F94A05B2169BA62C7A5F69AA335DD1B07944E8550B3C26641C146"),
    Path("Content/Zenscape_Island/Texture/Landscape/T_Sand_AO.uasset"):
        (5_614_332, "4FC402A81C84CC833E3B51D9CD7811EA0D44E3D7B49C90000163B5E0D8F9E5A5"),
    Path("Content/Zenscape_Island/Texture/Water/Water/T_DetailWater01_Normal.uasset"):
        (166_301, "EF46E4D6C3E7C64477FBCCEF86F40C72C20EF12F1811B871BA60BCB5D01403EC"),
    Path("Content/Zenscape_Island/Texture/Water/Water/T_StylizedWater_Ocean_DP.uasset"):
        (1_140_452, "9962892A7370EEEBF03E589321820A277DE8700465FD5598F2508CF7A344A565"),
    Path("Content/Zenscape_Island/Texture/Water/Water/T_StylizedWater_Ocean_N.uasset"):
        (1_231_099, "6AADF08B60B432594159A304695E3226E6537C152BD9CEB7C766DEE58C227D32"),
}

REQUIRED_DISABLED_PLUGINS = (
    "AndroidFileServer",
    "AIAssistant",
    "EditorTelemetry",
    "ModelContextProtocol",
    "Nwiro",
    "NwiroIntegrationKit",
    "OnlineSubsystemSteam",
    "SteamIntegrationKit",
    "SteamSockets",
    "UnrealAIIntegrationPlatform",
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IHDR = b"IHDR"

HARD_LOG_PATTERNS = {
    "fatal": re.compile(
        r"\bFatal error\b|LogWindows:\s*Error:.*\b(?:fatal|critical)\b|"
        r"LowLevelFatalError",
        re.IGNORECASE,
    ),
    "assert": re.compile(
        r"\bAssertion failed\b|\bcheckf?\s+failed\b|"
        r"\bensure(?:Always)?\s+condition\s+failed\b",
        re.IGNORECASE,
    ),
    "out_of_memory": re.compile(
        r"\bOut of memory\b|\bRan out of memory\b|"
        r"\bOOM\b.*\b(?:fatal|error|crash)\b",
        re.IGNORECASE,
    ),
    "gpu_loss": re.compile(
        r"\bGPU Crashed\b|\bGPU crash\b|\bGPU device removed\b|"
        r"DXGI_ERROR_DEVICE_(?:REMOVED|HUNG|RESET)|"
        r"\bD3D device (?:being )?lost\b",
        re.IGNORECASE,
    ),
}

WARNING_LOG_PATTERNS = {
    "mm_sun": re.compile(r"\bMM_Sun\b", re.IGNORECASE),
    "rvt": re.compile(
        r"\bRVT\b|Runtime Virtual Texture|virtual texture.*(?:warning|error)|"
        r"(?:warning|error).*virtual texture",
        re.IGNORECASE,
    ),
    "foliage": re.compile(
        r"foliage.*(?:warning|error|instance base cache)|"
        r"(?:warning|error|instance base cache).*foliage",
        re.IGNORECASE,
    ),
}

# Fail closed on final RHI selection. These are the exact UE log grammars
# accepted by this verifier: the explicit selection form, the historical
# support-and-use form present in retained real-GPU logs, and the D3D12 RHI
# creation form. End anchoring prevents capability text or a later negation on
# the same line from masquerading as the selected runtime binding.
D3D12_SM6_FINAL_SELECTED_PATTERN = re.compile(
    r"(?:"
    r"LogRHI:\s*(?:Display:\s*)?"
    r"(?:"
    r"RHI\s+Selected:\s*D3D12\s+with\s+Feature\s+Level\s+SM6"
    r"|"
    r"RHI\s+D3D12\s+with\s+Feature\s+Level\s+SM6\s+"
    r"is\s+supported\s+and\s+will\s+be\s+used"
    r")"
    r"|"
    r"LogD3D12RHI:\s*(?:Display:\s*)?"
    r"Creating\s+D3D12\s+RHI\s+with\s+Max\s+Feature\s+Level\s+SM6"
    r")"
    r"\.?\s*$",
    re.IGNORECASE,
)
SELECTED_NON_SM6_PATTERN = re.compile(
    r"(?:LogRHI|LogD3D12RHI)[^\r\n]*"
    r"(?=[^\r\n]*\bD3D12\b)"
    r"(?=[^\r\n]*\bSM[0-5]\b)"
    r"(?=[^\r\n]*(?:RHI\s+Selected|Selected\s+RHI|"
    r"will\s+be\s+used|Creating\s+D3D12\s+RHI))",
    re.IGNORECASE,
)
D3D12_ADAPTER_ENUM_PATTERN = re.compile(
    r"LogD3D12RHI[^\r\n]*\bFound\s+D3D12\s+adapter\s+(\d+)\s*:\s*(.+)",
    re.IGNORECASE,
)
D3D12_CHOSEN_ID_PATTERN = re.compile(
    r"LogD3D12RHI[^\r\n]*\bChosen\s+D3D12\s+Adapter\s+Id\s*=\s*(\d+)\b",
    re.IGNORECASE,
)
COMPETING_BACKEND_PATTERN = re.compile(
    r"(?:"
    r"(?:RHI|backend|renderer)\s+(?:Selected|Active|Current)"
    r"\s*(?::|=|is)?\s*"
    r"(?:D3D11|DX11|Vulkan|OpenGL|NullRHI|Metal)\b"
    r"|"
    r"(?:Selected|Active|Current)\s+(?:RHI|backend|renderer)"
    r"\s*(?::|=|is)?\s*"
    r"(?:D3D11|DX11|Vulkan|OpenGL|NullRHI|Metal)\b"
    r"|"
    r"(?:D3D11|DX11|Vulkan|OpenGL|NullRHI|Metal)"
    r"(?:\s+RHI)?\s+"
    r"(?:"
    r"(?:is\s+)?(?:now\s+)?(?:the\s+)?active(?:\s+RHI)?"
    r"|(?:is\s+)?selected"
    r"|will\s+be\s+used"
    r"|(?:is\s+)?running"
    r"|(?:has\s+)?started"
    r"|(?:has\s+been\s+)?(?:activated|initialized|launched)"
    r")\b"
    r"|"
    r"(?:RHI\s+)?(?:D3D11|DX11|Vulkan|OpenGL|NullRHI|Metal)"
    r"[^\r\n]{0,96}\bis\s+supported\s+and\s+will\s+be\s+used\b"
    r"|"
    r"(?:Using|Creating|Starting|Started|Initializing|Initialized|"
    r"Launching|Launched|Activating|Activated)\s+(?:the\s+)?"
    r"(?:(?:RHI|backend|renderer)\s*(?::|=)\s*)?"
    r"(?:D3D11|DX11|Vulkan|OpenGL|NullRHI|Metal)"
    r"(?:\s+RHI)?\b"
    r"|"
    r"(?:Switch(?:ing|ed)?|Set(?:ting)?|Chang(?:ing|ed))\s+"
    r"(?:the\s+)?(?:RHI|backend|renderer)\s+to\s+"
    r"(?:D3D11|DX11|Vulkan|OpenGL|NullRHI|Metal)\b"
    r")",
    re.IGNORECASE,
)
COMPETING_ADAPTER_PATTERN = re.compile(
    r"(?:LogD3D12RHI|LogRHI)[^\r\n]*"
    r"(?:chosen|selected|using|active)[^\r\n]*"
    r"\b(?:AMD|Radeon|Intel|Arc|UHD|Iris|Microsoft\s+Basic|"
    r"RTX\s+(?!3080\b)\d+)\b",
    re.IGNORECASE,
)
RHI_REJECTION_PATTERN = re.compile(
    r"(?:\bD3D12\b|\bSM6\b|\bPCD3D_SM6\b|\bRTX\s+3080\b)"
    r"[^\r\n]*"
    r"(?:fallback|falling\s+back|unsupported|not\s+supported|rejected|"
    r"failed|disabled|unavailable|cannot|could\s+not|device\s+removed|"
    r"not\s+(?:currently\s+)?(?:the\s+)?(?:selected|current)|"
    r"unselected|inactive|"
    r"not\s+(?:currently\s+)?(?:the\s+)?active|"
    r"no\s+longer\s+(?:the\s+)?(?:active|selected|current)|"
    r"not\s+in\s+use|will\s+not\s+be\s+used)|"
    r"(?:fallback|falling\s+back|unsupported|not\s+supported|rejected|"
    r"failed|disabled|unavailable|cannot|could\s+not|device\s+removed|"
    r"not\s+(?:currently\s+)?(?:the\s+)?(?:selected|current)|"
    r"unselected|inactive|"
    r"not\s+(?:currently\s+)?(?:the\s+)?active|no\s+active|"
    r"no\s+longer\s+(?:the\s+)?(?:active|selected|current)|"
    r"not\s+in\s+use|will\s+not\s+be\s+used)"
    r"[^\r\n]*(?:\bD3D12\b|\bSM6\b|\bPCD3D_SM6\b|\bRTX\s+3080\b)",
    re.IGNORECASE,
)
ACTIVE_OR_SELECTED_RHI_NOT_D3D12_PATTERN = re.compile(
    r"(?:"
    r"(?:active|selected|current)\s+(?:RHI|backend|renderer)"
    r"\s*(?::|=|is)\s*not\s+D3D12\b"
    r"|"
    r"D3D12(?:\s+RHI)?\s+is\s+not\s+(?:the\s+)?"
    r"(?:active|selected|current)(?:\s+RHI)?\b"
    r"|"
    r"no\s+D3D12(?:\s+RHI)?\s+(?:is\s+)?active\b"
    r")",
    re.IGNORECASE,
)
RTX_3080_NEGATIVE_PATTERN = re.compile(
    r"\b(?:NVIDIA\s+)?(?:GeForce\s+)?RTX\s+3080\b"
    r"[^\r\n]*(?:not\s+selected|unselected|inactive|"
    r"not\s+(?:the\s+)?active(?:\s+(?:adapter|device))?|rejected|"
    r"disabled|not\s+in\s+use|enumerated\s+only)|"
    r"(?:no\s+active|not\s+selected|unselected|inactive|"
    r"not\s+(?:the\s+)?active(?:\s+(?:adapter|device))?|"
    r"rejected|disabled|not\s+in\s+use|enumerated\s+only)[^\r\n]*"
    r"\b(?:NVIDIA\s+)?(?:GeForce\s+)?RTX\s+3080\b",
    re.IGNORECASE,
)

REQUIRED_RED_MARKERS = (
    "RED_M07_TROPICAL_LIVE_VALIDATION_STARTED",
    "RED_M07_TROPICAL_NATIVE_SNAP_VERIFIED",
    "RED_M07_TROPICAL_HIGHRESSHOT_ISSUED view=ground",
    "RED_M07_TROPICAL_HIGHRESSHOT_FILE_VERIFIED view=ground",
    "RED_M07_TROPICAL_HIGHRESSHOT_ISSUED view=curvature",
    "RED_M07_TROPICAL_HIGHRESSHOT_FILE_VERIFIED view=curvature",
    "RED_M07_TROPICAL_HIGHRESSHOT_ISSUED view=horizon",
    "RED_M07_TROPICAL_HIGHRESSHOT_FILE_VERIFIED view=horizon",
    "RED_M07_TROPICAL_LIVE_VALIDATION_READY",
)

NONCLAIMS = {
    "PIE_or_gameplay_accepted": False,
    "water_accepted": False,
    "cloud_accepted": False,
    "collision_feel_accepted": False,
    "performance_accepted": False,
    "orbit_accepted": False,
    "surface_to_orbit_accepted": False,
    "production_integration_accepted": False,
}


class PostflightError(RuntimeError):
    """A fail-closed postflight contract violation."""


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _is_under(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((_norm(path), _norm(root))) == _norm(root)
    except ValueError:
        return False


def _assert_no_reparse_points(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if not current.exists():
            continue
        info = os.lstat(current)
        attributes = int(getattr(info, "st_file_attributes", 0))
        if current.is_symlink() or (
            attributes
            & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
        ):
            raise PostflightError(
                f"reparse point is forbidden in postflight path: {current}"
            )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _file_record(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PostflightError(f"required file is missing: {path}")
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _read_stable_bytes(
    path: Path, *, attempts: int = 10, delay_seconds: float = 0.05
) -> tuple[bytes, dict[str, Any]]:
    """Read a live-owned file only across a stable size/mtime observation."""

    if not path.is_file():
        raise PostflightError(f"required file is missing: {path}")
    for attempt in range(attempts):
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
        if (
            before.st_size == after.st_size == len(payload)
            and before.st_mtime_ns == after.st_mtime_ns
        ):
            return payload, {
                "path": str(path),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest().upper(),
                "stable_read_attempt": attempt + 1,
            }
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
    raise PostflightError(
        f"file did not remain stable during bounded read: {path}"
    )


def _authenticate_file(
    path: Path,
    *,
    expected_bytes: int | None,
    expected_sha256: str,
    label: str,
) -> dict[str, Any]:
    record = _file_record(path)
    if expected_bytes is not None and record["bytes"] != expected_bytes:
        raise PostflightError(
            f"{label} byte length drifted: expected={expected_bytes} "
            f"actual={record['bytes']} path={path}"
        )
    if record["sha256"] != expected_sha256.upper():
        raise PostflightError(
            f"{label} hash drifted: expected={expected_sha256.upper()} "
            f"actual={record['sha256']} path={path}"
        )
    return record


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload_bytes, record = _read_stable_bytes(path)
    try:
        payload = json.loads(payload_bytes.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PostflightError(f"{label} is not valid UTF-8 JSON: {path}: {exc}")
    if not isinstance(payload, dict):
        raise PostflightError(f"{label} JSON root must be an object: {path}")
    return payload, record


def parse_png_ihdr(path: Path) -> dict[str, Any]:
    """Validate and fully decode a non-interlaced PNG using only stdlib."""

    payload, record = _read_stable_bytes(path)
    if not payload:
        raise PostflightError(f"PNG is empty: {path}")
    if len(payload) > 128 * 1024 * 1024:
        raise PostflightError(f"PNG exceeds the 128 MiB evidence limit: {path}")
    if len(payload) < 33:
        raise PostflightError(f"PNG is too short to contain an IHDR: {path}")
    if payload[:8] != PNG_SIGNATURE:
        raise PostflightError(f"PNG magic is invalid: {path}")

    offset = len(PNG_SIGNATURE)
    chunks: list[dict[str, Any]] = []
    compressed_parts: list[bytes] = []
    ihdr: bytes | None = None
    saw_idat = False
    idat_finished = False
    saw_iend = False
    saw_plte = False
    while offset < len(payload):
        if len(payload) - offset < 12:
            raise PostflightError(f"PNG has a truncated chunk header: {path}")
        chunk_length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + chunk_length
        crc_end = data_end + 4
        if data_end < data_start or crc_end > len(payload):
            raise PostflightError(
                f"PNG chunk is truncated or length-overflows the file: {path}"
            )
        chunk_data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(chunk_data, actual_crc) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            printable = chunk_type.decode("ascii", errors="replace")
            raise PostflightError(
                f"PNG chunk CRC is invalid: type={printable} path={path}"
            )
        try:
            printable_type = chunk_type.decode("ascii", errors="strict")
        except UnicodeError as exc:
            raise PostflightError(f"PNG chunk type is not ASCII: {path}: {exc}")
        chunks.append(
            {
                "type": printable_type,
                "bytes": chunk_length,
                "crc32": f"{actual_crc:08X}",
            }
        )
        if len(chunks) == 1:
            if chunk_type != PNG_IHDR or chunk_length != 13:
                raise PostflightError(
                    f"PNG first chunk is not an exact 13-byte IHDR: {path}"
                )
            ihdr = chunk_data
        elif chunk_type == PNG_IHDR:
            raise PostflightError(f"PNG contains a duplicate IHDR: {path}")

        known_critical = {b"IHDR", b"PLTE", b"IDAT", b"IEND"}
        if chunk_type[:1].isupper() and chunk_type not in known_critical:
            raise PostflightError(
                f"PNG contains an unsupported critical chunk "
                f"{printable_type}: {path}"
            )
        if chunk_type == b"PLTE":
            if saw_idat or saw_iend:
                raise PostflightError(f"PNG PLTE ordering is invalid: {path}")
            if saw_plte or not chunk_data or len(chunk_data) % 3:
                raise PostflightError(f"PNG PLTE structure is invalid: {path}")
            saw_plte = True
        elif chunk_type == b"IDAT":
            if saw_iend or idat_finished:
                raise PostflightError(f"PNG IDAT ordering is invalid: {path}")
            saw_idat = True
            compressed_parts.append(chunk_data)
        elif saw_idat and chunk_type != b"IEND":
            idat_finished = True
        if chunk_type == b"IEND":
            if chunk_length != 0 or not saw_idat:
                raise PostflightError(f"PNG IEND/IDAT contract is invalid: {path}")
            saw_iend = True
            offset = crc_end
            if offset != len(payload):
                raise PostflightError(f"PNG has trailing bytes after IEND: {path}")
            break
        offset = crc_end

    if ihdr is None or not saw_idat or not saw_iend:
        raise PostflightError(f"PNG lacks required IHDR/IDAT/IEND chunks: {path}")
    width, height = struct.unpack(">II", ihdr[:8])
    bit_depth = int(ihdr[8])
    color_type = int(ihdr[9])
    compression = int(ihdr[10])
    filter_method = int(ihdr[11])
    interlace = int(ihdr[12])
    if width != EXPECTED_SCREENSHOT_WIDTH or height != EXPECTED_SCREENSHOT_HEIGHT:
        raise PostflightError(
            f"PNG dimensions drifted: expected="
            f"{EXPECTED_SCREENSHOT_WIDTH}x{EXPECTED_SCREENSHOT_HEIGHT} "
            f"actual={width}x{height} path={path}"
        )
    if compression != 0 or filter_method != 0:
        raise PostflightError(f"PNG IHDR methods are invalid: {path}")
    if interlace != 0:
        raise PostflightError(
            f"interlaced PNG screenshots are not accepted by this decoder: {path}"
        )

    legal_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    if color_type not in legal_depths or bit_depth not in legal_depths[color_type]:
        raise PostflightError(
            f"PNG IHDR bit-depth/color-type combination is invalid: {path}"
        )
    if color_type == 3 and not saw_plte:
        raise PostflightError(f"indexed PNG is missing PLTE: {path}")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    bits_per_pixel = channels * bit_depth
    row_bytes = (width * bits_per_pixel + 7) // 8
    filter_bytes_per_pixel = max(1, (bits_per_pixel + 7) // 8)
    expected_decoded_bytes = height * (row_bytes + 1)
    compressed = b"".join(compressed_parts)
    if not compressed:
        raise PostflightError(f"PNG IDAT stream is empty: {path}")
    decoder = zlib.decompressobj()
    try:
        decoded = decoder.decompress(compressed, expected_decoded_bytes + 1)
    except zlib.error as exc:
        raise PostflightError(f"PNG IDAT zlib decode failed: {path}: {exc}")
    if (
        len(decoded) > expected_decoded_bytes
        or decoder.unconsumed_tail
        or not decoder.eof
        or decoder.unused_data
    ):
        raise PostflightError(
            f"PNG IDAT stream is overlong, incomplete, or has trailing data: {path}"
        )
    try:
        decoded += decoder.flush()
    except zlib.error as exc:
        raise PostflightError(f"PNG IDAT flush failed: {path}: {exc}")
    if len(decoded) != expected_decoded_bytes:
        raise PostflightError(
            f"PNG decoded scanline length drifted: "
            f"expected={expected_decoded_bytes} actual={len(decoded)} path={path}"
        )

    reconstructed = bytearray(height * row_bytes)
    previous = bytearray(row_bytes)
    source_offset = 0
    destination_offset = 0
    filter_counts = {str(index): 0 for index in range(5)}
    for _row in range(height):
        filter_type = int(decoded[source_offset])
        source_offset += 1
        if filter_type not in range(5):
            raise PostflightError(
                f"PNG scanline uses invalid filter {filter_type}: {path}"
            )
        filter_counts[str(filter_type)] += 1
        filtered = decoded[source_offset : source_offset + row_bytes]
        source_offset += row_bytes
        current = bytearray(row_bytes)
        for index, value in enumerate(filtered):
            left = (
                current[index - filter_bytes_per_pixel]
                if index >= filter_bytes_per_pixel
                else 0
            )
            above = previous[index]
            upper_left = (
                previous[index - filter_bytes_per_pixel]
                if index >= filter_bytes_per_pixel
                else 0
            )
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            else:
                p = left + above - upper_left
                pa = abs(p - left)
                pb = abs(p - above)
                pc = abs(p - upper_left)
                predictor = left if pa <= pb and pa <= pc else (
                    above if pb <= pc else upper_left
                )
            current[index] = (value + predictor) & 0xFF
        reconstructed[
            destination_offset : destination_offset + row_bytes
        ] = current
        destination_offset += row_bytes
        previous = current

    if source_offset != len(decoded) or destination_offset != len(reconstructed):
        raise PostflightError(f"PNG scanline decode did not consume exactly: {path}")

    record.update(
        {
            "png_magic": "89504E470D0A1A0A",
            "ihdr_length": 13,
            "width": width,
            "height": height,
            "bit_depth": bit_depth,
            "color_type": color_type,
            "compression_method": compression,
            "filter_method": filter_method,
            "interlace_method": interlace,
            "chunk_count": len(chunks),
            "chunks": chunks,
            "idat_compressed_bytes": len(compressed),
            "decoded_scanline_bytes": len(decoded),
            "decoded_pixel_bytes": len(reconstructed),
            "decoded_pixel_sha256": hashlib.sha256(reconstructed).hexdigest().upper(),
            "filter_counts": filter_counts,
            "full_png_crc_and_pixel_decode_verified": True,
        }
    )
    return record


def scan_unreal_log(text: str) -> dict[str, Any]:
    """Classify required runtime evidence, hard failures, and soft warnings."""

    lines = text.splitlines()

    def matching_lines(pattern: re.Pattern[str]) -> list[dict[str, Any]]:
        return [
            {"line": index, "text": line}
            for index, line in enumerate(lines, start=1)
            if pattern.search(line)
        ]

    hard_findings = {
        name: matching_lines(pattern)
        for name, pattern in HARD_LOG_PATTERNS.items()
    }
    warning_findings = {
        name: matching_lines(pattern)
        for name, pattern in WARNING_LOG_PATTERNS.items()
    }
    canonical_d3d12_sm6_lines = matching_lines(
        D3D12_SM6_FINAL_SELECTED_PATTERN
    )
    selected_lines = {
        "d3d12": canonical_d3d12_sm6_lines,
        "sm6": canonical_d3d12_sm6_lines,
    }
    rejected_lines = matching_lines(RHI_REJECTION_PATTERN)
    selected_non_sm6_lines = matching_lines(SELECTED_NON_SM6_PATTERN)
    competing_backend_lines = matching_lines(COMPETING_BACKEND_PATTERN)
    inactive_d3d12_lines = matching_lines(
        ACTIVE_OR_SELECTED_RHI_NOT_D3D12_PATTERN
    )
    competing_adapter_lines = matching_lines(COMPETING_ADAPTER_PATTERN)
    rtx_3080_negative_lines = matching_lines(RTX_3080_NEGATIVE_PATTERN)
    enumerated_adapters: list[dict[str, Any]] = []
    chosen_adapter_ids: list[int] = []
    for index, line in enumerate(lines, start=1):
        adapter_match = D3D12_ADAPTER_ENUM_PATTERN.search(line)
        if adapter_match:
            description = adapter_match.group(2)
            enumerated_adapters.append(
                {
                    "line": index,
                    "adapter_id": int(adapter_match.group(1)),
                    "description": description,
                    "is_rtx_3080": bool(
                        re.search(
                            r"\b(?:NVIDIA\s+)?(?:GeForce\s+)?RTX\s+3080\b",
                            description,
                            re.IGNORECASE,
                        )
                    ),
                }
            )
        chosen_match = D3D12_CHOSEN_ID_PATTERN.search(line)
        if chosen_match:
            chosen_adapter_ids.append(int(chosen_match.group(1)))
    unique_chosen_ids = sorted(set(chosen_adapter_ids))
    rtx_3080_adapter_ids = sorted(
        {
            int(record["adapter_id"])
            for record in enumerated_adapters
            if record["is_rtx_3080"]
        }
    )
    chosen_id_bound_to_rtx_3080 = (
        len(unique_chosen_ids) == 1
        and unique_chosen_ids[0] in rtx_3080_adapter_ids
    )
    chosen_id_has_competing_binding = bool(unique_chosen_ids) and (
        len(unique_chosen_ids) != 1
        or not chosen_id_bound_to_rtx_3080
    )
    rtx_3080_selected = chosen_id_bound_to_rtx_3080
    rhi = {
        "d3d12": bool(selected_lines["d3d12"]),
        "sm6": bool(selected_lines["sm6"]),
        "rtx_3080": rtx_3080_selected,
        "positive_selected_lines": selected_lines,
        "canonical_d3d12_sm6_final_selected_lines":
            canonical_d3d12_sm6_lines,
        "enumerated_d3d12_adapters": enumerated_adapters,
        "chosen_d3d12_adapter_ids": unique_chosen_ids,
        "rtx_3080_adapter_ids": rtx_3080_adapter_ids,
        "chosen_id_bound_to_rtx_3080": chosen_id_bound_to_rtx_3080,
        "competing_selected_backend_lines": competing_backend_lines,
        "inactive_or_unselected_d3d12_lines": inactive_d3d12_lines,
        "competing_selected_adapter_lines": competing_adapter_lines,
        "rtx_3080_negative_or_inactive_lines": rtx_3080_negative_lines,
        "chosen_id_has_competing_binding": chosen_id_has_competing_binding,
        "fallback_or_rejection_lines": rejected_lines,
        "selected_non_sm6_lines": selected_non_sm6_lines,
        "positive_binding_passed": (
            bool(canonical_d3d12_sm6_lines)
            and rtx_3080_selected
            and not rejected_lines
            and not selected_non_sm6_lines
            and not competing_backend_lines
            and not inactive_d3d12_lines
            and not competing_adapter_lines
            and not rtx_3080_negative_lines
            and not chosen_id_has_competing_binding
        ),
    }
    markers = {
        marker: any(marker in line for line in lines)
        for marker in REQUIRED_RED_MARKERS
    }
    destination_map_present = DESTINATION_MAP in text

    required_disable = ",".join(REQUIRED_DISABLED_PLUGINS)
    disable_token = f"-DisablePlugins={required_disable}"
    provider_disable_lines = [
        {"line": index, "text": line}
        for index, line in enumerate(lines, start=1)
        if disable_token.casefold() in line.casefold()
    ]

    provider_names = tuple(
        sorted(REQUIRED_DISABLED_PLUGINS, key=len, reverse=True)
    )
    explicitly_disabled_mentions: list[dict[str, Any]] = []
    unapproved_provider_mentions: list[dict[str, Any]] = []
    provider_activation_findings: list[dict[str, Any]] = []
    provider_nonactivation_mentions: list[dict[str, Any]] = []
    runtime_activation_pattern = re.compile(
        r"\b(?:mount(?:s|ing|ed)?|load(?:s|ing|ed)?|"
        r"initiali[sz](?:e[sd]?|ing)|start(?:s|ing|ed)?|"
        r"launch(?:es|ing|ed)?|online|live|"
        r"listen(?:s|ing|ed)?|connect(?:s|ing|ed)?|"
        r"bind(?:s|ing)?|bound|"
        r"serv(?:e[sd]?|ing)|register(?:s|ing|ed)?|"
        r"enable(?:s|d|ing)?|activate(?:s|d|ing)?|"
        r"active|ready|running)\b|"
        r"\baccept(?:s|ing|ed)?\s+(?:client\s+)?connections?\b|"
        r"\bconnections?\s+accepted\b",
        re.IGNORECASE,
    )
    benign_metadata_activity_pattern = re.compile(
        r"\b(?:load(?:ing|ed)?|read(?:ing)?|pars(?:ing|ed))\s+"
        r"(?:the\s+)?(?:project\s+|plugin\s+)?descriptor\b|"
        r"\b(?:project|plugin)\s+descriptor\s+(?:was\s+)?"
        r"(?:loaded|read|parsed)\b",
        re.IGNORECASE,
    )
    negative_disabled_state_pattern = re.compile(
        r"\b(?:is\s+)?not\s+(?:currently\s+)?disabled\b|"
        r"\bisn['\u2019]?t\s+disabled\b|"
        r"\bdisabled(?:\s+plugin)?(?:\s+(?:status|setting))?\s*"
        r"(?:=|:|\?)\s*"
        r"(?:false|0|no|off)\b|"
        r"\bdisabled\s+is\s+false\b",
        re.IGNORECASE,
    )
    disable_policy_violation_pattern = re.compile(
        r"\b(?:skip(?:ping|ped)?|bypass(?:ing|ed)?|ignor(?:ing|ed))\b"
        r"[^\r\n]*\bprovider[-\s]+disable[-\s]+enforcement\b",
        re.IGNORECASE,
    )
    safe_disabled_state_pattern = re.compile(
        r"\b(?:is|was|remains)\s+disabled\b|"
        r"\bskip(?:ping|ped)?\s+(?:the\s+)?disabled\s+plugin\b|"
        r"\bdisabled\s+plugin\s+(?:was\s+)?skip(?:ping|ped)?\b|"
        r"\b(?:is|was|remains|has\s+been)\s+not\s+(?:currently\s+)?"
        r"(?:loaded|mounted|started|initiali[sz]ed|registered|"
        r"enabled|active|ready|running|listening|connected|bound|serving|"
        r"online|live|launched|accepting\s+(?:client\s+)?connections?)\b|"
        r"\bnot\s+(?:currently\s+)?"
        r"(?:active|ready|running|listening|connected|bound|serving|"
        r"online|live|accepting\s+(?:client\s+)?connections?)\b|"
        r"\boffline\b|"
        r"\bwill\s+not\s+"
        r"(?:load|mount|start|initiali[sz]e|register|enable|activate|launch|"
        r"listen|connect|bind|serve|run|accept\s+(?:client\s+)?connections?)\b",
        re.IGNORECASE,
    )
    negative_runtime_state_pattern = re.compile(
        r"\b(?:is|was|remains|has\s+been)\s+not\s+(?:currently\s+)?"
        r"(?:loaded|mounted|started|initiali[sz]ed|registered|"
        r"enabled|active|ready|running|listening|connected|bound|serving|"
        r"online|live|launched|accepting\s+(?:client\s+)?connections?)\b|"
        r"\bnot\s+(?:currently\s+)?"
        r"(?:active|ready|running|listening|connected|bound|serving|"
        r"online|live|accepting\s+(?:client\s+)?connections?)\b|"
        r"\boffline\b|"
        r"\bwill\s+not\s+"
        r"(?:load|mount|start|initiali[sz]e|register|enable|activate|launch|"
        r"listen|connect|bind|serve|run|accept\s+(?:client\s+)?connections?)\b",
        re.IGNORECASE,
    )
    for index, line in enumerate(lines, start=1):
        contains_disable_token = (
            disable_token.casefold() in line.casefold()
        )
        semantic_line = (
            re.sub(
                re.escape(disable_token),
                "",
                line,
                flags=re.IGNORECASE,
            )
            if contains_disable_token
            else line
        )
        mentioned = [
            name
            for name in provider_names
            if name.casefold() in semantic_line.casefold()
        ]
        if not mentioned:
            continue
        entry = {"line": index, "plugins": mentioned, "text": line}
        negative_disabled_state = negative_disabled_state_pattern.search(
            semantic_line
        )
        disable_policy_violation = disable_policy_violation_pattern.search(
            semantic_line
        )
        runtime_probe = negative_runtime_state_pattern.sub(
            "", semantic_line
        )
        runtime_probe = benign_metadata_activity_pattern.sub(
            "", runtime_probe
        )
        runtime_probe = re.sub(
            r"\b(?:https?|com\.epicgames\.launcher)://\S+",
            "",
            runtime_probe,
            flags=re.IGNORECASE,
        )
        positive_runtime_state = runtime_activation_pattern.search(
            runtime_probe
        )
        if (
            negative_disabled_state
            or disable_policy_violation
            or positive_runtime_state
        ):
            unapproved_provider_mentions.append(entry)
            if positive_runtime_state:
                provider_activation_findings.append(entry)
            continue
        if contains_disable_token:
            continue
        if safe_disabled_state_pattern.search(line):
            explicitly_disabled_mentions.append(entry)
            continue
        provider_nonactivation_mentions.append(entry)

    return {
        "line_count": len(lines),
        "rhi": rhi,
        "destination_map_present": destination_map_present,
        "required_markers": markers,
        "provider_off": {
            "exact_disable_token": disable_token,
            "exact_disable_line_count": len(provider_disable_lines),
            "exact_disable_lines": provider_disable_lines,
            "explicitly_disabled_or_skipped_mentions":
                explicitly_disabled_mentions,
            "unapproved_mentions": unapproved_provider_mentions,
            "activation_findings": provider_activation_findings,
            "nonactivation_mentions": provider_nonactivation_mentions,
        },
        "hard_findings": hard_findings,
        "warning_findings": warning_findings,
    }


def _option_values(command_line: str, name: str) -> list[str]:
    boundary = r"""[\s"']"""
    pattern = re.compile(
        rf"""(?:^|{boundary})-{re.escape(name)}="""
        rf"""(?:"([^"]*)"|'([^']*)'|([^"'\s]+))(?=$|{boundary})""",
        re.IGNORECASE,
    )
    return [
        next(group for group in match.groups() if group is not None)
        for match in pattern.finditer(command_line)
    ]


def _flag_count(command_line: str, flag: str) -> int:
    boundary = r"""[\s"']"""
    return len(
        re.findall(
            rf"""(?:^|{boundary})-{re.escape(flag)}(?=$|{boundary})""",
            command_line,
            flags=re.IGNORECASE,
        )
    )


def _exact_token_count(command_line: str, token: str) -> int:
    normalized = command_line.replace("\\", "/")
    normalized_token = token.replace("\\", "/")
    boundary = r"""[\s"']"""
    return len(
        re.findall(
            rf"""(?:^|{boundary}){re.escape(normalized_token)}(?=$|{boundary})""",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _parse_utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise PostflightError(f"{label} UTC timestamp is missing")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PostflightError(f"{label} UTC timestamp is invalid: {value}: {exc}")
    if parsed.tzinfo is None:
        raise PostflightError(f"{label} UTC timestamp lacks timezone: {value}")
    return parsed.astimezone(dt.timezone.utc)


def _audit_file_matches(
    record: Any,
    actual: dict[str, Any],
    *,
    label: str,
) -> None:
    if not isinstance(record, dict):
        raise PostflightError(f"{label} audit record is missing")
    if (
        int(record.get("bytes", -1)) != actual["bytes"]
        or str(record.get("sha256", "")).upper() != actual["sha256"]
    ):
        raise PostflightError(
            f"{label} does not match the authenticated current file"
        )
    record_path = record.get("path")
    if not isinstance(record_path, str) or _norm(Path(record_path)) != _norm(
        Path(actual["path"])
    ):
        raise PostflightError(
            f"{label} path does not match the authenticated current file"
        )


def _query_editor_process(editor_pid: int) -> dict[str, Any]:
    if editor_pid <= 0:
        raise PostflightError("--editor-pid must be a positive integer")
    if os.name != "nt":
        raise PostflightError("live editor PID authentication requires Windows")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    open_process.restype = ctypes.c_void_p
    query_image = kernel32.QueryFullProcessImageNameW
    query_image.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_wchar),
        ctypes.POINTER(ctypes.c_uint32),
    )
    query_image.restype = ctypes.c_int
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    close_handle.restype = ctypes.c_int

    class FileTime(ctypes.Structure):
        _fields_ = (
            ("low", ctypes.c_uint32),
            ("high", ctypes.c_uint32),
        )

    get_process_times = kernel32.GetProcessTimes
    get_process_times.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
    )
    get_process_times.restype = ctypes.c_int

    process_query_information = 0x0400
    process_vm_read = 0x0010
    handle = open_process(
        process_query_information | process_vm_read, 0, int(editor_pid)
    )
    if not handle:
        error = ctypes.get_last_error()
        raise PostflightError(
            f"editor PID is not queryable/alive: pid={editor_pid} winerror={error}"
        )
    try:
        capacity = ctypes.c_uint32(32_768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if not query_image(handle, 0, buffer, ctypes.byref(capacity)):
            error = ctypes.get_last_error()
            raise PostflightError(
                f"could not query editor image: pid={editor_pid} winerror={error}"
            )
        image_path = Path(buffer.value)

        creation = FileTime()
        exit_time = FileTime()
        kernel_time = FileTime()
        user_time = FileTime()
        if not get_process_times(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            error = ctypes.get_last_error()
            raise PostflightError(
                f"could not query editor creation time: "
                f"pid={editor_pid} winerror={error}"
            )

        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        nt_query = ntdll.NtQueryInformationProcess
        nt_query.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        )
        nt_query.restype = ctypes.c_long
        command_line_information = 60
        required = ctypes.c_uint32(0)
        nt_query(
            handle,
            command_line_information,
            None,
            0,
            ctypes.byref(required),
        )
        if required.value < ctypes.sizeof(ctypes.c_void_p) * 2:
            raise PostflightError(
                f"could not size editor command line: pid={editor_pid}"
            )
        command_buffer = ctypes.create_string_buffer(required.value)
        status = nt_query(
            handle,
            command_line_information,
            command_buffer,
            required.value,
            ctypes.byref(required),
        )
        if status != 0:
            raise PostflightError(
                f"could not query editor command line: "
                f"pid={editor_pid} ntstatus=0x{status & 0xFFFFFFFF:08X}"
            )

        class UnicodeString(ctypes.Structure):
            _fields_ = (
                ("length", ctypes.c_uint16),
                ("maximum_length", ctypes.c_uint16),
                ("buffer", ctypes.c_void_p),
            )

        unicode_string = UnicodeString.from_buffer(command_buffer)
        if (
            unicode_string.length <= 0
            or unicode_string.length % 2
            or not unicode_string.buffer
        ):
            raise PostflightError(
                f"editor command-line UNICODE_STRING is invalid: pid={editor_pid}"
            )
        command_line = ctypes.wstring_at(
            unicode_string.buffer, unicode_string.length // 2
        )
    finally:
        close_handle(handle)
    if _norm(image_path) != _norm(EXPECTED_EDITOR_EXE):
        raise PostflightError(
            f"--editor-pid is not the exact UE 5.8 UnrealEditor.exe: "
            f"pid={editor_pid} expected={EXPECTED_EDITOR_EXE} actual={image_path}"
        )

    filetime_ticks = (int(creation.high) << 32) | int(creation.low)
    creation_unix_seconds = filetime_ticks / 10_000_000 - 11_644_473_600
    creation_utc = dt.datetime.fromtimestamp(
        creation_unix_seconds, tz=dt.timezone.utc
    )
    return {
        "pid": editor_pid,
        "alive_at_postflight": True,
        "image_path": str(image_path),
        "creation_utc": creation_utc.isoformat(),
        "command_line": command_line,
        "command_line_sha256": hashlib.sha256(
            command_line.encode("utf-8")
        ).hexdigest().upper(),
    }


def _validate_editor_identity_binding(
    *,
    process: dict[str, Any],
    audit: dict[str, Any],
    project_root: Path,
    run_dir: Path,
) -> dict[str, Any]:
    current = str(process.get("command_line", ""))
    audit_command_record = audit.get("command_line")
    if not isinstance(audit_command_record, dict):
        raise PostflightError("live audit command-line record is missing")
    audited = str(audit_command_record.get("command_line", ""))
    project_file = project_root / "Titan.uproject"
    expected_disable = ",".join(REQUIRED_DISABLED_PLUGINS)
    expected_abs_log = run_dir / "UnrealEditor.log"
    normalized_project = str(project_file).replace("\\", "/")

    def project_tokens(command_line: str) -> list[str]:
        return [
            token.replace("\\", "/")
            for token in re.findall(
                r"""(?:^|[\s"'])([^\s"']+\.uproject)(?=$|[\s"'])""",
                command_line,
                flags=re.IGNORECASE,
            )
        ]

    def validate_one(
        command_line: str,
        label: str,
        *,
        require_project_token: bool,
    ) -> list[str]:
        observed_project_tokens = project_tokens(command_line)
        if require_project_token and (
            len(observed_project_tokens) != 1
            or observed_project_tokens[0].casefold()
            != normalized_project.casefold()
        ):
            raise PostflightError(
                f"{label} must contain only the exact scratch project once: "
                f"{observed_project_tokens}"
            )
        if not require_project_token and (
            len(observed_project_tokens) > 1
            or any(
                token.casefold() != normalized_project.casefold()
                for token in observed_project_tokens
            )
        ):
            raise PostflightError(
                f"{label} has an unexpected or duplicate project token: "
                f"{observed_project_tokens}"
            )
        if _exact_token_count(command_line, DESTINATION_MAP) != 1:
            raise PostflightError(
                f"{label} does not contain the exact staging map once"
            )
        abs_log_values = _option_values(command_line, "AbsLog")
        if (
            len(abs_log_values) != 1
            or _norm(Path(abs_log_values[0])) != _norm(expected_abs_log)
        ):
            raise PostflightError(
                f"{label} exact AbsLog binding drifted"
            )
        validator_values = _option_values(command_line, "ExecutePythonScript")
        if (
            len(validator_values) != 1
            or _norm(Path(validator_values[0]))
            != _norm(EXPECTED_LIVE_VALIDATOR)
        ):
            raise PostflightError(
                f"{label} exact live-validator script binding drifted"
            )
        if _option_values(command_line, "DisablePlugins") != [expected_disable]:
            raise PostflightError(
                f"{label} exact provider-off option drifted"
            )
        if _flag_count(command_line, "d3d12") != 1:
            raise PostflightError(f"{label} lacks one exact -d3d12 flag")
        if _flag_count(command_line, "sm6") != 1:
            raise PostflightError(f"{label} lacks one exact -sm6 flag")
        forbidden = ("nullrhi", "d3d11", "dx11", "vulkan", "opengl", "game", "server")
        observed = [
            flag for flag in forbidden if _flag_count(command_line, flag)
        ]
        if observed:
            raise PostflightError(
                f"{label} has forbidden RHI/runtime flags: {observed}"
            )
        return observed_project_tokens

    current_project_tokens = validate_one(
        current,
        "live editor process command line",
        require_project_token=True,
    )
    audited_project_tokens = validate_one(
        audited,
        "live audit command line",
        require_project_token=False,
    )
    project_binding = audit_command_record.get("project_binding")
    if not isinstance(project_binding, dict):
        raise PostflightError("live audit project_binding record is missing")
    binding_path = Path(str(project_binding.get("path", "")))
    binding_tokens = project_binding.get(
        "in_process_command_line_project_tokens"
    )
    if (
        _norm(binding_path) != _norm(project_file)
        or project_binding.get("authority")
        != "unreal.Paths.get_project_file_path"
        or not isinstance(binding_tokens, list)
        or [str(token).replace("\\", "/") for token in binding_tokens]
        != audited_project_tokens
    ):
        raise PostflightError(
            "live audit project_binding does not match the exact active "
            "scratch project and in-process command line"
        )
    current_abs_log = _option_values(current, "AbsLog")[0]
    audited_abs_log = _option_values(audited, "AbsLog")[0]
    if _norm(Path(current_abs_log)) != _norm(Path(audited_abs_log)):
        raise PostflightError(
            "live editor and audit AbsLog identities differ"
        )

    creation = _parse_utc(process.get("creation_utc"), "editor creation")
    captured = _parse_utc(audit.get("captured_utc"), "live audit captured")
    completed = _parse_utc(audit.get("completed_utc"), "live audit completed")
    if not creation <= captured <= completed:
        raise PostflightError(
            "editor creation/live audit timestamp ordering is invalid"
        )
    startup_delay = (captured - creation).total_seconds()
    if startup_delay > 4 * 60 * 60:
        raise PostflightError(
            f"live audit was not created by the current editor session: "
            f"startup_delay_seconds={startup_delay:.3f}"
        )
    now = dt.datetime.now(dt.timezone.utc)
    postflight_delay = (now - completed).total_seconds()
    if postflight_delay < -300 or postflight_delay > 4 * 60 * 60:
        raise PostflightError(
            f"live audit is not temporally bound to this postflight: "
            f"postflight_delay_seconds={postflight_delay:.3f}"
        )
    return {
        **process,
        "exact_project_map_abslog_validator_provider_binding": True,
        "win32_process_project_tokens": current_project_tokens,
        "audit_in_process_project_tokens": audited_project_tokens,
        "audit_project_binding": project_binding,
        "audit_timestamp_binding": True,
        "audit_capture_delay_after_process_creation_seconds": startup_delay,
        "postflight_delay_after_audit_completion_seconds": postflight_delay,
    }


def _listener_records(value: Any, label: str) -> set[tuple[int, str, int]]:
    if not isinstance(value, list):
        raise PostflightError(f"{label} must be an array")
    output: set[tuple[int, str, int]] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise PostflightError(f"{label}[{index}] must be an object")
        try:
            pid = int(item["pid"])
            address = str(item.get("address", item.get("local_address", "")))
            port = int(item.get("port", item.get("local_port")))
        except (KeyError, TypeError, ValueError) as exc:
            raise PostflightError(
                f"{label}[{index}] is not a pid/address/port listener: {exc}"
            )
        output.add((pid, address, port))
    return output


def _validate_launcher_evidence(
    path: Path, process: dict[str, Any]
) -> dict[str, Any]:
    payload, record = _load_json(path, "launcher evidence")
    editor_pid = int(process["pid"])
    evidence_pid = payload.get("editor_pid", payload.get("launched_pid"))
    editor_object = payload.get("editor")
    if editor_object is not None and not isinstance(editor_object, dict):
        raise PostflightError("launcher evidence editor field must be an object")
    editor_object = editor_object if isinstance(editor_object, dict) else {}
    if evidence_pid is None:
        evidence_pid = editor_object.get("pid")
    if int(evidence_pid or -1) != editor_pid:
        raise PostflightError(
            "launcher evidence editor PID does not match --editor-pid"
        )
    evidence_creation = payload.get(
        "editor_creation_utc", editor_object.get("creation_utc")
    )
    launcher_creation = _parse_utc(
        evidence_creation, "launcher editor creation"
    )
    live_creation = _parse_utc(
        process.get("creation_utc"), "live editor creation"
    )
    if abs((launcher_creation - live_creation).total_seconds()) > 1.0:
        raise PostflightError(
            "launcher evidence editor creation time does not match live PID"
        )
    evidence_image = payload.get(
        "editor_image_path", editor_object.get("image_path")
    )
    if (
        not isinstance(evidence_image, str)
        or _norm(Path(evidence_image)) != _norm(Path(process["image_path"]))
    ):
        raise PostflightError(
            "launcher evidence editor image does not match live PID"
        )
    evidence_command_line = payload.get(
        "editor_command_line", editor_object.get("command_line")
    )
    evidence_command_hash = payload.get(
        "editor_command_line_sha256",
        editor_object.get("command_line_sha256"),
    )
    if isinstance(evidence_command_line, str):
        computed = hashlib.sha256(
            evidence_command_line.encode("utf-8")
        ).hexdigest().upper()
        if evidence_command_line != process["command_line"]:
            raise PostflightError(
                "launcher evidence command line does not match live PID"
            )
        if evidence_command_hash is not None and str(
            evidence_command_hash
        ).upper() != computed:
            raise PostflightError(
                "launcher evidence command-line hash is internally inconsistent"
            )
    elif (
        not isinstance(evidence_command_hash, str)
        or evidence_command_hash.upper() != process["command_line_sha256"]
    ):
        raise PostflightError(
            "launcher evidence lacks a matching editor command line/hash"
        )
    network = payload.get("network")
    if network is not None and not isinstance(network, dict):
        raise PostflightError("launcher evidence network field must be an object")
    container = network if isinstance(network, dict) else payload

    before = None
    after = None
    for key in ("listeners_before", "baseline_listeners", "before_listeners"):
        if key in container:
            before = container[key]
            break
    for key in ("listeners_after", "post_launch_listeners", "after_listeners"):
        if key in container:
            after = container[key]
            break
    if before is None or after is None:
        raise PostflightError(
            "supplied launcher evidence lacks before/after listener arrays"
        )
    before_set = _listener_records(before, "launcher listeners before")
    after_set = _listener_records(after, "launcher listeners after")
    new_editor_owned = sorted(
        entry
        for entry in (after_set - before_set)
        if entry[0] == editor_pid
    )
    if new_editor_owned:
        raise PostflightError(
            f"launcher evidence found new editor-owned listeners: "
            f"{new_editor_owned}"
        )
    return {
        "file": record,
        "editor_pid": editor_pid,
        "editor_creation_utc": process["creation_utc"],
        "editor_image_path": process["image_path"],
        "editor_command_line_sha256": process["command_line_sha256"],
        "editor_identity_bound": True,
        "before_listener_count": len(before_set),
        "after_listener_count": len(after_set),
        "new_editor_owned_listeners": [],
        "passed": True,
    }


def _validate_roots(
    run_dir: Path, project_root: Path, production_root: Path
) -> None:
    for path, label in (
        (run_dir, "run directory"),
        (project_root, "scratch project root"),
        (production_root, "production root"),
    ):
        if not path.is_absolute() or not path.is_dir():
            raise PostflightError(f"{label} must be an existing absolute directory: {path}")
        _assert_no_reparse_points(path)
    if _norm(project_root) != _norm(EXPECTED_PROJECT_ROOT):
        raise PostflightError(
            f"--project-root must be exactly {EXPECTED_PROJECT_ROOT}: {project_root}"
        )
    if _norm(production_root) != _norm(EXPECTED_PRODUCTION_ROOT):
        raise PostflightError(
            f"--production-root must be exactly {EXPECTED_PRODUCTION_ROOT}: "
            f"{production_root}"
        )
    if not _is_under(run_dir, DIAGNOSTICS_ROOT) or _norm(run_dir) == _norm(
        DIAGNOSTICS_ROOT
    ):
        raise PostflightError(
            f"--run-dir must be a per-run child of {DIAGNOSTICS_ROOT}: {run_dir}"
        )
    if _is_under(run_dir, project_root) or _is_under(run_dir, production_root):
        raise PostflightError(
            "--run-dir must remain external to production and scratch projects"
        )


def _validate_live_audit(
    audit: dict[str, Any],
    *,
    project_root: Path,
    run_dir: Path,
) -> None:
    if (
        audit.get("result") != "passed_pending_screenshot_pixel_inspection"
        or audit.get("operation")
        != "tropical_planetary_biome_live_snap_visual_validation_v1"
    ):
        raise PostflightError(
            "live audit is not the exact "
            "passed_pending_screenshot_pixel_inspection "
            "M07 operation"
        )
    if _norm(Path(str(audit.get("project_root", "")))) != _norm(project_root):
        raise PostflightError("live audit scratch project binding drifted")
    if audit.get("map") != DESTINATION_MAP:
        raise PostflightError("live audit destination map binding drifted")
    authoring = audit.get("authoring_audit")
    if (
        not isinstance(authoring, dict)
        or str(authoring.get("sha256", "")).upper()
        != EXPECTED_AUTHORING_AUDIT_SHA256
        or authoring.get("authenticated_operation")
        != "tropical_planetary_biome_scratch_stage_v1"
        or authoring.get("authenticated_result") != "passed"
    ):
        raise PostflightError(
            "live audit does not retain the exact authenticated authoring audit"
        )
    if (
        audit.get("scratch_only") is not True
        or audit.get("PIE_started") is not False
        or audit.get("providers_used") is not False
        or audit.get("water_or_cloud_assets_applied") is not False
    ):
        raise PostflightError("live audit safety/claim boundary drifted")
    claims = audit.get("claims")
    if not isinstance(claims, dict):
        raise PostflightError("live audit claims object is missing")
    required_claims = {
        "scratch_map_native_snap_saved": True,
        "managed_actors_snapped": 17,
        "captured_managed_state_delta_exact": True,
        "managed_state_delta": (
            "native transform snap plus exact pending-to-complete tag transition"
        ),
        "screenshot_commands_issued": 3,
        "screenshot_files_verified": True,
        "screenshot_pixels_inspected": False,
        "real_gpu_pixels_verified": False,
        "PIE_or_gameplay_accepted": False,
        "water_integrated": False,
        "cloud_integrated": False,
        "performance_accepted": False,
        "surface_to_orbit_accepted": False,
        "production_integration_accepted": False,
    }
    for key, expected in required_claims.items():
        if claims.get(key) != expected:
            raise PostflightError(
                f"live audit claim drifted: {key} expected={expected!r} "
                f"actual={claims.get(key)!r}"
            )
    snap = audit.get("snap")
    if (
        not isinstance(snap, dict)
        or snap.get("captured_managed_state_delta_exact") is not True
        or snap.get("captured_managed_state_delta")
        != (
            "native location/rotation snap plus exact "
            "PendingNativePlanetSnap-to-NativePlanetSnapComplete replacement"
        )
    ):
        raise PostflightError(
            "live audit exact captured managed-state delta drifted"
        )
    captures = audit.get("viewport_captures")
    if not isinstance(captures, list) or len(captures) != 3:
        raise PostflightError("live audit must record exactly three viewport captures")
    observed_names = tuple(str(item.get("name", "")) for item in captures)
    if observed_names != SCREENSHOT_VIEW_NAMES:
        raise PostflightError(
            f"live audit viewport order drifted: {observed_names}"
        )
    for capture, filename in zip(captures, SCREENSHOT_FILENAMES):
        expected_path = run_dir / filename
        if (
            capture.get("high_res_shot_issued") is not True
            or _norm(Path(str(capture.get("expected_screenshot_path", ""))))
            != _norm(expected_path)
            or capture.get("screenshot_existence")
            != "verified_exact_nonempty_stable_file"
            or capture.get("screenshot_pixels_inspected") is not False
            or capture.get("pixel_review") != "pending_external_inspection"
        ):
            raise PostflightError(
                f"live audit screenshot request drifted: {filename}"
            )
        screenshot_file = capture.get("screenshot_file")
        if not isinstance(screenshot_file, dict):
            raise PostflightError(
                f"live audit screenshot-file record is missing: {filename}"
            )


def _authenticate_project_files(
    *,
    project_root: Path,
    production_root: Path,
    audit: dict[str, Any],
) -> dict[str, Any]:
    files_before = audit.get("files_before")
    files_after = audit.get("files_after")
    if not isinstance(files_before, dict) or not isinstance(files_after, dict):
        raise PostflightError("live audit files_before/files_after are missing")

    protected: dict[str, Any] = {"scratch": {}, "production": {}}
    expected_protected_keys = {
        str(relative).replace("\\", "/")
        for relative in PROTECTED_PROJECT_FILES
    }
    for phase_name, phase in (
        ("files_before", files_before),
        ("files_after", files_after),
    ):
        for section in ("protected", "canonical_protected"):
            records = phase.get(section)
            if not isinstance(records, dict) or set(records) != expected_protected_keys:
                raise PostflightError(
                    f"live audit {phase_name}.{section} is not the exact "
                    "four-file protected set"
                )
    for relative, expected_hash in PROTECTED_PROJECT_FILES.items():
        key = str(relative).replace("\\", "/")
        scratch = _authenticate_file(
            project_root / relative,
            expected_bytes=None,
            expected_sha256=expected_hash,
            label=f"protected scratch file {key}",
        )
        production = _authenticate_file(
            production_root / relative,
            expected_bytes=None,
            expected_sha256=expected_hash,
            label=f"protected production file {key}",
        )
        _audit_file_matches(
            files_before.get("protected", {}).get(key),
            scratch,
            label=f"live audit protected-before {key}",
        )
        _audit_file_matches(
            files_after.get("protected", {}).get(key),
            scratch,
            label=f"live audit protected-after {key}",
        )
        _audit_file_matches(
            files_before.get("canonical_protected", {}).get(key),
            production,
            label=f"live audit canonical-protected-before {key}",
        )
        _audit_file_matches(
            files_after.get("canonical_protected", {}).get(key),
            production,
            label=f"live audit canonical-protected-after {key}",
        )
        protected["scratch"][key] = scratch
        protected["production"][key] = production

    vendor_before = files_before.get("vendor")
    vendor_after = files_after.get("vendor")
    if not isinstance(vendor_before, dict) or not isinstance(vendor_after, dict):
        raise PostflightError("live audit vendor records are missing")
    expected_vendor_keys = {
        str(relative).replace("\\", "/") for relative in VENDOR_ROOT_FILES
    }
    if set(vendor_before) != expected_vendor_keys or set(vendor_after) != expected_vendor_keys:
        raise PostflightError(
            "live audit reviewed vendor-root set differs from the exact allowlist"
        )
    vendor: dict[str, Any] = {}
    for relative, (expected_bytes, expected_hash) in VENDOR_ROOT_FILES.items():
        key = str(relative).replace("\\", "/")
        actual = _authenticate_file(
            project_root / relative,
            expected_bytes=expected_bytes,
            expected_sha256=expected_hash,
            label=f"reviewed Tropical root {key}",
        )
        _audit_file_matches(
            vendor_before[key], actual, label=f"live audit vendor-before {key}"
        )
        _audit_file_matches(
            vendor_after[key], actual, label=f"live audit vendor-after {key}"
        )
        vendor[key] = actual
    return {"protected": protected, "vendor": vendor}


def _authenticate_map_and_backup(
    *,
    run_dir: Path,
    project_root: Path,
    audit: dict[str, Any],
) -> dict[str, Any]:
    backup = _authenticate_file(
        run_dir / BACKUP_FILENAME,
        expected_bytes=EXPECTED_PRE_SNAP_MAP_BYTES,
        expected_sha256=EXPECTED_PRE_SNAP_MAP_SHA256,
        label="retained pre-snap rollback map",
    )
    _audit_file_matches(
        audit.get("pre_snap_backup", {}).get("backup"),
        backup,
        label="live audit pre-snap backup",
    )
    current_map = _file_record(project_root / DESTINATION_MAP_RELATIVE)
    if current_map["sha256"] == EXPECTED_PRE_SNAP_MAP_SHA256:
        raise PostflightError(
            "scratch staging map did not change from the authenticated pre-snap map"
        )
    snap = audit.get("snap")
    if not isinstance(snap, dict):
        raise PostflightError("live audit snap record is missing")
    _audit_file_matches(
        snap.get("post_save_map"),
        current_map,
        label="live audit/current post-snap map",
    )
    return {
        "retained_pre_snap_backup": backup,
        "current_post_snap_map": current_map,
        "hashes_are_distinct": True,
    }


def _authenticate_screenshots(
    run_dir: Path, audit: dict[str, Any]
) -> list[dict[str, Any]]:
    observed_pngs = {
        path.name
        for path in run_dir.iterdir()
        if path.is_file() and path.suffix.casefold() == ".png"
    }
    expected_pngs = set(SCREENSHOT_FILENAMES)
    if observed_pngs != expected_pngs:
        raise PostflightError(
            "run directory PNG set must be exactly the three named captures: "
            f"expected={sorted(expected_pngs)} actual={sorted(observed_pngs)}"
        )
    captures = audit["viewport_captures"]
    output: list[dict[str, Any]] = []
    hashes: set[str] = set()
    pixel_hashes: set[str] = set()
    for capture, view_name, filename in zip(
        captures, SCREENSHOT_VIEW_NAMES, SCREENSHOT_FILENAMES
    ):
        record = parse_png_ihdr(run_dir / filename)
        _audit_file_matches(
            capture.get("screenshot_file"),
            record,
            label=f"live audit verified screenshot {view_name}",
        )
        record["view"] = view_name
        record["high_res_shot_command"] = capture.get("high_res_shot_command")
        if record["sha256"] in hashes:
            raise PostflightError(
                f"screenshot pixel-file hashes are not distinct: {filename}"
            )
        if record["decoded_pixel_sha256"] in pixel_hashes:
            raise PostflightError(
                f"screenshot decoded pixels are not distinct: {filename}"
            )
        hashes.add(record["sha256"])
        pixel_hashes.add(record["decoded_pixel_sha256"])
        output.append(record)
    if len(output) != 3 or len(hashes) != 3 or len(pixel_hashes) != 3:
        raise PostflightError(
            "exactly three file-distinct and pixel-distinct screenshots are required"
        )
    return output


def _validate_log(
    *, run_dir: Path, audit: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    command_line_record = audit.get("command_line")
    if not isinstance(command_line_record, dict):
        raise PostflightError("live audit command-line record is missing")
    command_line = str(command_line_record.get("command_line", ""))
    abs_logs = _option_values(command_line, "AbsLog")
    if len(abs_logs) != 1:
        raise PostflightError(
            f"live command line must contain exactly one -AbsLog: {abs_logs}"
        )
    log_path = Path(abs_logs[0])
    if (
        not log_path.is_absolute()
        or _norm(log_path.parent) != _norm(run_dir)
        or log_path.name.casefold() != "unrealeditor.log"
    ):
        raise PostflightError(
            f"exact AbsLog must be an immediate child of run dir: {log_path}"
        )
    _assert_no_reparse_points(log_path)
    log_bytes, log_record = _read_stable_bytes(log_path)
    try:
        text = log_bytes.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise PostflightError(f"exact AbsLog is not valid UTF-8 text: {exc}")
    scan = scan_unreal_log(text)
    hard: list[dict[str, Any]] = []
    for category, findings in scan["hard_findings"].items():
        hard.extend(
            {"category": category, **finding} for finding in findings
        )
    if not scan["rhi"]["positive_binding_passed"]:
        hard.append(
            {
                "category": "rhi_identity",
                "text": (
                    "required positive selected D3D12/SM6/RTX 3080 binding "
                    "is missing or contradicted by fallback/rejection evidence"
                ),
                "rhi": scan["rhi"],
            }
        )
    if not scan["destination_map_present"]:
        hard.append(
            {
                "category": "destination_map",
                "text": f"destination map marker missing: {DESTINATION_MAP}",
            }
        )
    missing_markers = [
        marker
        for marker, present in scan["required_markers"].items()
        if not present
    ]
    if missing_markers:
        hard.append(
            {
                "category": "red_markers",
                "text": f"required RED markers missing: {missing_markers}",
            }
        )
    provider = scan["provider_off"]
    if provider["exact_disable_line_count"] < 1:
        hard.append(
            {
                "category": "provider_off",
                "text": "exact provider/telemetry/Steam disable option is "
                "absent from the exact AbsLog",
            }
        )
    if provider["unapproved_mentions"]:
        hard.extend(
            {
                "category": (
                    "provider_activation"
                    if finding in provider["activation_findings"]
                    else "provider_unapproved_mention"
                ),
                **finding,
            }
            for finding in provider["unapproved_mentions"]
        )
    scan["file"] = log_record
    scan["hard_gate_findings"] = hard
    return scan, hard


def _write_no_clobber_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _warning_summary(log_scan: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for category, findings in log_scan["warning_findings"].items():
        warnings.extend(
            {"category": category, **finding} for finding in findings
        )
    warnings.extend(
        {"category": "provider_explicitly_disabled_or_skipped", **finding}
        for finding in log_scan["provider_off"][
            "explicitly_disabled_or_skipped_mentions"
        ]
    )
    warnings.extend(
        {"category": "provider_nonactivation_metadata", **finding}
        for finding in log_scan["provider_off"]["nonactivation_mentions"]
    )
    return warnings


def _run(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    run_dir = Path(args.run_dir)
    project_root = Path(args.project_root)
    production_root = Path(args.production_root)
    _validate_roots(run_dir, project_root, production_root)

    output_path = run_dir / POSTFLIGHT_FILENAME
    if output_path.exists():
        raise PostflightError(f"postflight output is no-clobber: {output_path}")

    audit_path = run_dir / LIVE_AUDIT_FILENAME
    audit, audit_record = _load_json(audit_path, "live validation audit")
    _validate_live_audit(
        audit, project_root=project_root, run_dir=run_dir
    )
    validator_source = _authenticate_file(
        EXPECTED_LIVE_VALIDATOR,
        expected_bytes=None,
        expected_sha256=EXPECTED_LIVE_VALIDATOR_SHA256,
        label="reviewed M07 live validator source",
    )
    process = _validate_editor_identity_binding(
        process=_query_editor_process(args.editor_pid),
        audit=audit,
        project_root=project_root,
        run_dir=run_dir,
    )
    map_and_backup = _authenticate_map_and_backup(
        run_dir=run_dir, project_root=project_root, audit=audit
    )
    project_files = _authenticate_project_files(
        project_root=project_root,
        production_root=production_root,
        audit=audit,
    )
    screenshots = _authenticate_screenshots(run_dir, audit)
    log_scan, hard_findings = _validate_log(run_dir=run_dir, audit=audit)

    launcher = None
    if args.launcher_evidence is not None:
        launcher_path = Path(args.launcher_evidence)
        if (
            not launcher_path.is_absolute()
            or _norm(launcher_path.parent) != _norm(run_dir)
        ):
            raise PostflightError(
                "--launcher-evidence must be an immediate child of --run-dir"
            )
        _assert_no_reparse_points(launcher_path)
        launcher = _validate_launcher_evidence(launcher_path, process)

    warnings = _warning_summary(log_scan)
    passed = not hard_findings
    report: dict[str, Any] = {
        "schema_version": 1,
        "module": "M07",
        "operation": "tropical_planetary_biome_live_postflight_v1",
        "captured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "result": "passed" if passed else "failed",
        "evidence_class": "real_gpu_visual" if passed else "static",
        "read_only": True,
        "project_root": str(project_root),
        "production_root": str(production_root),
        "run_dir": str(run_dir),
        "map": DESTINATION_MAP,
        "live_audit": audit_record,
        "live_validator_source": validator_source,
        "editor_process": process,
        "map_and_rollback": map_and_backup,
        "authenticated_project_files": project_files,
        "screenshots": screenshots,
        "screenshot_gate": {
            "count": len(screenshots),
            "distinct_sha256_count": len(
                {record["sha256"] for record in screenshots}
            ),
            "distinct_decoded_pixel_sha256_count": len(
                {record["decoded_pixel_sha256"] for record in screenshots}
            ),
            "exact_resolution": "1920x1080",
            "full_crc_and_pixel_decode_verified": True,
            "passed": True,
        },
        "unreal_log": log_scan,
        "launcher_network_evidence": launcher,
        "hard_failures": hard_findings,
        "warnings": warnings,
        "nonclaims": NONCLAIMS,
        "claim_limit": (
            "Real-GPU editor pixels for three named M07 staging viewpoints only. "
            "No PIE/gameplay, water, cloud, collision feel, performance, "
            "surface-to-orbit, or production-integration acceptance is claimed."
        ),
    }
    return report, passed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only postflight for the M07 Tropical live scratch run."
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--editor-pid", required=True, type=int)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--production-root", required=True)
    parser.add_argument(
        "--launcher-evidence",
        help=(
            "Optional absolute JSON path containing matching editor_pid plus "
            "before/after listener arrays."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_dir = Path(args.run_dir)
    output_path = run_dir / POSTFLIGHT_FILENAME
    try:
        report, passed = _run(args)
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "module": "M07",
            "operation": "tropical_planetary_biome_live_postflight_v1",
            "captured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "result": "failed",
            "evidence_class": "static",
            "read_only": True,
            "hard_failures": [
                {
                    "category": "postflight_contract",
                    "type": type(exc).__name__,
                    "text": str(exc),
                }
            ],
            "warnings": [],
            "nonclaims": NONCLAIMS,
        }
        try:
            failure_target_is_safe = (
                run_dir.is_absolute()
                and run_dir.is_dir()
                and _is_under(run_dir, DIAGNOSTICS_ROOT)
                and _norm(run_dir) != _norm(DIAGNOSTICS_ROOT)
            )
            if failure_target_is_safe:
                _assert_no_reparse_points(run_dir)
            if failure_target_is_safe and not output_path.exists():
                _write_no_clobber_json(output_path, failure)
        except Exception as write_exc:
            print(
                f"postflight failed and failure report could not be written: "
                f"{write_exc}",
                file=sys.stderr,
            )
        print(f"postflight failed: {exc}", file=sys.stderr)
        return 1

    _write_no_clobber_json(output_path, report)
    print(
        json.dumps(
            {
                "result": report["result"],
                "evidence_class": report["evidence_class"],
                "output": str(output_path),
                "warnings": len(report["warnings"]),
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
