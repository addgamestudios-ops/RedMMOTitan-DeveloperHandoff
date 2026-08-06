"""Create the fail-closed rollback point for the clean Red MMO R11 flight slice."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO"
HOME_MAP = os.path.join(PROJECT, r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap")
ENGINE_CONFIG = os.path.join(PROJECT, r"Config\DefaultEngine.ini")
EXPECTED_HOME_SHA = "C489B6000B359A7B52FBE7FD50A72A76232020DBC9A015DFC61CA2FB1120C46F"
TARGET_FILES = [
    os.path.join(PROJECT, r"Content\RedMMO\Gameplay\Input\IMC_RedPlanet_R11.uasset"),
    os.path.join(PROJECT, r"Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset"),
    os.path.join(PROJECT, r"Content\RedMMO\Gameplay\Player\GM_RedPlanet_R11.uasset"),
]
PROTECTED = {
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap":
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap":
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap":
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap":
        "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> None:
    if sha256(HOME_MAP) != EXPECTED_HOME_SHA:
        raise RuntimeError("Current clean Red home map hash drift; refusing checkpoint")
    existing_targets = [path for path in TARGET_FILES if os.path.exists(path)]
    if existing_targets:
        raise RuntimeError(f"R11 target assets already exist: {existing_targets}")
    protected_actual = {path: sha256(path) for path in PROTECTED}
    protected_drift = {
        path: {"expected": PROTECTED[path], "actual": actual}
        for path, actual in protected_actual.items()
        if actual != PROTECTED[path]
    }
    if protected_drift:
        raise RuntimeError(f"Protected checkpoint drift: {protected_drift}")

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    rollback = os.path.join(
        r"D:\RedMMOTitanWindowsData\Rollback", f"RedMMO_PPG_Flight_R11_{stamp}"
    )
    os.makedirs(rollback, exist_ok=False)
    rollback_map = os.path.join(rollback, "RedMMO_PPG_HomeWorld.pre_r11.umap")
    rollback_config = os.path.join(rollback, "DefaultEngine.pre_r11.ini")
    shutil.copy2(HOME_MAP, rollback_map)
    shutil.copy2(ENGINE_CONFIG, rollback_config)

    git_status = subprocess.run(
        ["git", "status", "--porcelain=v2", "--untracked-files=all"],
        cwd=r"D:\RedMMOTitan",
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    git_status_file = os.path.join(rollback, "redmmotitan_git_status_porcelain_v2.txt")
    with open(git_status_file, "w", encoding="utf-8") as handle:
        handle.write(git_status)

    manifest = {
        "schema": "redmmo.ppg_flight.r11.rollback.v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project": PROJECT,
        "home_map": HOME_MAP,
        "home_sha256": EXPECTED_HOME_SHA,
        "rollback_home_map": rollback_map,
        "default_engine_config": ENGINE_CONFIG,
        "default_engine_sha256": sha256(ENGINE_CONFIG),
        "rollback_default_engine_config": rollback_config,
        "protected_hashes": protected_actual,
        "targets_required_absent": TARGET_FILES,
        "git_status_snapshot": git_status_file,
        "rollback_method": (
            "Close Unreal; restore rollback_home_map over home_map and "
            "rollback_default_engine_config over default_engine_config; remove only the "
            "three exact R11 target assets listed in targets_required_absent."
        ),
    }
    manifest_path = os.path.join(rollback, "pre_r11_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(manifest_path)


if __name__ == "__main__":
    main()
