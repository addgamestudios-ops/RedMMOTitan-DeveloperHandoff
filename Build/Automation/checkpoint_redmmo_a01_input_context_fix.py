"""Offline no-clobber rollback checkpoint for the A01 input-context correction."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path


SOURCE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Source\RedMMO\Private\RedPlayerCharacter.cpp")
SOURCE_SHA256 = "F775F25934C2C58510A03A8037A66FC03A0704F8EE105C087E23FA637E32420F"
HOME_MAP = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap")
HOME_MAP_SHA256 = "1310D92641AC25DAEA4DF289A8B2C16A46F3F0D4AECB7FB9F4616FE5CEAD5209"
ROLLBACK_ROOT = Path(r"D:\RedMMOTitanWindowsData\Rollback")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def blocked_processes() -> list[str]:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { $_.Name -match "
         "'UnrealEditor|ShaderCompileWorker|UnrealBuildTool|AutomationTool' } | "
         "ForEach-Object { \"$($_.ProcessId):$($_.Name)\" }"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.parent / ("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main() -> None:
    require(not blocked_processes(), "Unreal/build process is active")
    require(SOURCE.is_file() and sha256(SOURCE) == SOURCE_SHA256, "Source preimage drift")
    require(HOME_MAP.is_file() and sha256(HOME_MAP) == HOME_MAP_SHA256, "Home-map preimage drift")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_dir = ROLLBACK_ROOT / ("RedMMO_A01_InputContextFix_" + stamp)
    staging_dir = ROLLBACK_ROOT / (".RedMMO_A01_InputContextFix_" + stamp + "." + uuid.uuid4().hex)
    require(not final_dir.exists() and not staging_dir.exists(), "Rollback target collision")
    staging_dir.mkdir(parents=False)
    copy = staging_dir / SOURCE.name
    shutil.copy2(SOURCE, copy)
    require(sha256(copy) == SOURCE_SHA256, "Rollback source-copy hash mismatch")
    manifest = {
        "schema": "redmmo.a01.input_context_fix.checkpoint.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "authorized_scope": "Project-owned RedPlayerCharacter input-context reliability correction only",
        "source": {"path": str(SOURCE), "sha256": SOURCE_SHA256, "bytes": SOURCE.stat().st_size},
        "copy": {"path": SOURCE.name, "sha256": SOURCE_SHA256, "bytes": copy.stat().st_size},
        "home_map": {"path": str(HOME_MAP), "sha256": HOME_MAP_SHA256},
        "unreal_or_build_processes": [],
    }
    atomic_json(staging_dir / "manifest.json", manifest)
    os.replace(staging_dir, final_dir)
    require(sha256(final_dir / SOURCE.name) == SOURCE_SHA256, "Final rollback-copy hash mismatch")
    print(json.dumps({
        "status": "PASS",
        "checkpoint": str(final_dir / "manifest.json"),
        "checkpoint_sha256": sha256(final_dir / "manifest.json"),
        "source_sha256": SOURCE_SHA256,
        "home_map_sha256": HOME_MAP_SHA256,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
