"""Create the map-only rollback point for the clean RedMMO A01 home bind.

This is an offline, no-clobber checkpoint creator.  It authenticates the
successful same-process asset-build report, its fresh-process serialized
readback, all eighteen project-owned A01 packages, the source ship, the six
protected checkpoints, and the exact current home-map preimage.  The final
rollback directory contains exactly a map copy and one manifest.

Run this script only while Unreal/build processes are closed.  It deliberately
does not launch Unreal and does not edit the project or repository.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT_ROOT / "RedMMO.uproject"
PROJECT_SHA256 = "54E664A24FA5E9129C022740EE624F84389F1825AA9A4AE07D5E99DD783F382E"
HOME_MAP = PROJECT_ROOT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HOME_MAP_SHA256 = "1821ED915E924085A2D6B3E1A85984A0F207C116EFF32AC974E8F0B7CD217F87"

BUILD_REPORT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_TrooperAssets_A01_20260803T044000Z\build_report.json"
)
BUILD_REPORT_SHA256 = "21E20052DDAF86EA419AD0A00C9BEB3BB11EC2A34F3517608633E1D6202D19F1"
FRESH_REPORT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_TrooperAssets_A01_Fresh_20260803T044200Z\fresh_report.json"
)
FRESH_REPORT_SHA256 = "18346B265845444825332E9A946BFE0AF57E3115D4A86E35499B10D01DDFD571"

SOURCE_SHIP = (
    PROJECT_ROOT / r"Content\RedMMO\Ships\BP_RedModularStarSparrow.uasset"
)
SOURCE_SHIP_SHA256 = "A8A6E128C2A08AE95A745B3A70C47A372339F314C67C6CE37539A25B67DC78C9"

PROTECTED_FILES = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen.umap"):
        "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Environment\DA_RED_Planet50Km_FusedHeightfield.uasset"):
        "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"):
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap"):
        "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}

ROOT = "/Game/RedMMO/Gameplay/Trooper/A01"
EXPECTED_PACKAGES = (
    ROOT + "/Input/IA_RedMove",
    ROOT + "/Input/IA_RedLook",
    ROOT + "/Input/IA_RedJump",
    ROOT + "/Input/IA_RedSprint",
    ROOT + "/Input/IA_RedFire",
    ROOT + "/Input/IA_RedADS",
    ROOT + "/Input/IA_RedInteract",
    ROOT + "/Input/IMC_RedTrooper_A01",
    ROOT + "/Input/IA_RedShipMove",
    ROOT + "/Input/IA_RedShipLook",
    ROOT + "/Input/IA_RedShipRoll",
    ROOT + "/Input/IA_RedShipBoost",
    ROOT + "/Input/IA_RedShipExit",
    ROOT + "/Input/IMC_RedShip_A01",
    ROOT + "/Combat/BP_RedBolt_Trooper_A01",
    ROOT + "/Player/BP_RedTrooperPlayer_A01",
    ROOT + "/Ship/BP_RedModularStarSparrow_Trooper_A01",
    ROOT + "/Player/GM_RedTrooperPPG_A01",
)

ROLLBACK_ROOT = Path(r"D:\RedMMOTitanWindowsData\Rollback")
FINAL_PREFIX = "RedMMO_HomeGameplayBind_A01_"
MAP_COPY_NAME = "RedMMO_PPG_HomeWorld.umap.pre_bind_a01"
MANIFEST_NAME = "manifest.json"
BLOCKED_PROCESS_NAMES = {
    "unrealeditor.exe",
    "unrealeditor-cmd.exe",
    "shadercompileworker.exe",
    "unrealbuildtool.exe",
    "automationtool.exe",
}


class CheckpointError(RuntimeError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise CheckpointError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_json(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    require(path.is_file(), f"{label} is missing: {path}")
    actual = sha256(path)
    require(
        actual == expected_sha256,
        f"{label} hash drift: expected={expected_sha256} actual={actual}",
    )
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    require(isinstance(value, dict), f"{label} is not a JSON object")
    return value


def package_file(package: str) -> Path:
    require(package.startswith("/Game/"), f"Unsafe package path: {package}")
    relative = package[len("/Game/") :].replace("/", os.sep) + ".uasset"
    result = (PROJECT_ROOT / "Content" / relative).resolve(strict=False)
    content = (PROJECT_ROOT / "Content").resolve(strict=True)
    require(
        os.path.commonpath([str(result), str(content)]) == str(content),
        f"Package escaped project Content: {package}",
    )
    return result


def all_false(mapping: Any) -> bool:
    return isinstance(mapping, dict) and set(mapping) == {"5353", "8000", "8765"} and not any(
        bool(value) for value in mapping.values()
    )


def empty_dirty(value: Any) -> bool:
    return isinstance(value, dict) and value.get("content") == [] and value.get("maps") == []


def verify_reports_and_assets() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    build = load_json(BUILD_REPORT, BUILD_REPORT_SHA256, "A01 build report")
    fresh = load_json(FRESH_REPORT, FRESH_REPORT_SHA256, "A01 fresh report")
    expected = set(EXPECTED_PACKAGES)

    require(build.get("schema_version") == 1, "A01 build-report schema drift")
    require(
        build.get("status") == "pass_created_compiled_saved_same_process_readback",
        "A01 build report did not pass",
    )
    require(build.get("target_count") == 18, "A01 build target count drift")
    require(set(build.get("created_assets", [])) == expected, "A01 created-asset set drift")
    saved_entries = build.get("saved_assets")
    require(isinstance(saved_entries, list) and len(saved_entries) == 18, "A01 saved-asset record count drift")
    require(all(isinstance(item, dict) for item in saved_entries), "Malformed A01 saved-asset record")
    require({item.get("package") for item in saved_entries} == expected, "A01 saved-asset set drift")
    saved_by_package = {item["package"]: item for item in saved_entries}
    require(build.get("map_mutation_authorized") is False, "A01 build authorized a map mutation")
    require(build.get("map_saved") is False, "A01 build saved a map")
    require(build.get("config_saved") is False, "A01 build saved config")
    require(build.get("vendor_assets_modified") is False, "A01 build modified vendor content")
    require(empty_dirty(build.get("dirty_packages_after")), "A01 build left dirty packages")
    require(build.get("home_map_sha256_after") == HOME_MAP_SHA256, "A01 build home-map evidence drift")
    require(build.get("source_ship_sha256_after") == SOURCE_SHIP_SHA256, "A01 build source-ship evidence drift")
    require(build.get("preflight", {}).get("source_ship_sha256") == SOURCE_SHIP_SHA256, "A01 build preflight source-ship drift")
    require(build.get("preflight", {}).get("protected_hashes") == {str(path): value for path, value in PROTECTED_FILES.items()}, "A01 build preflight protected set drift")
    require(build.get("protected_hashes_after") == {str(path): value for path, value in PROTECTED_FILES.items()}, "A01 build protected-after set drift")
    require(all_false(build.get("provider_ports_listening_after")), "A01 build provider evidence drift")

    require(fresh.get("schema_version") == 1, "A01 fresh-report schema drift")
    require(
        fresh.get("status") == "pass_fresh_process_serialized_readback",
        "A01 fresh report did not pass",
    )
    require(fresh.get("build_report", {}).get("sha256") == BUILD_REPORT_SHA256, "Fresh report references a different build")
    require(fresh.get("home_map_sha256_after") == HOME_MAP_SHA256, "Fresh home-map evidence drift")
    require(fresh.get("source_ship_sha256_after") == SOURCE_SHIP_SHA256, "Fresh source-ship evidence drift")
    require(fresh.get("protected_hashes") == {str(path): value for path, value in PROTECTED_FILES.items()}, "Fresh protected set drift")
    require(all_false(fresh.get("provider_ports_listening")), "Fresh provider evidence drift")
    require(empty_dirty(fresh.get("dirty_packages_after")), "Fresh verifier left dirty packages")
    require(fresh.get("pie_active") is False and fresh.get("pie_world_count") == 0, "Fresh verifier PIE gate drift")
    require(fresh.get("project_map_loaded") is False, "Fresh verifier loaded a project map")
    require(fresh.get("loaded_world_package") == "/Engine/Maps/Entry", "Fresh verifier world drift")
    require(fresh.get("map_saved") is False and fresh.get("assets_saved") is False, "Fresh verifier wrote content")

    entries = fresh.get("files")
    require(isinstance(entries, list) and len(entries) == 18, "Fresh report file count drift")
    require({item.get("package") for item in entries if isinstance(item, dict)} == expected, "Fresh package set drift")
    verified_assets: list[dict[str, Any]] = []
    for item in entries:
        require(isinstance(item, dict), "Malformed fresh asset record")
        package = item.get("package")
        expected_file = package_file(package)
        reported_file = Path(str(item.get("file", ""))).resolve(strict=False)
        require(reported_file == expected_file, f"Fresh file path mismatch for {package}")
        require(expected_file.is_file(), f"A01 package file is missing: {expected_file}")
        expected_hash = str(item.get("sha256", "")).upper()
        require(len(expected_hash) == 64, f"Malformed A01 package hash: {package}")
        actual_hash = sha256(expected_file)
        require(actual_hash == expected_hash, f"A01 package hash drift: {package}")
        saved = saved_by_package[package]
        require(Path(str(saved.get("file", ""))).resolve(strict=False) == expected_file, f"Build saved-file path mismatch for {package}")
        require(str(saved.get("sha256", "")).upper() == expected_hash, f"Build/fresh hash mismatch for {package}")
        require(int(saved.get("bytes", -1)) == expected_file.stat().st_size, f"Build saved-byte count mismatch for {package}")
        verified_assets.append(
            {
                "package": package,
                "file": str(expected_file),
                "bytes": expected_file.stat().st_size,
                "sha256": actual_hash,
            }
        )
    verified_assets.sort(key=lambda item: item["package"])
    return build, fresh, verified_assets


def verify_hashes(records: dict[Path, str], label: str) -> dict[str, str]:
    output: dict[str, str] = {}
    for path, expected in records.items():
        require(path.is_file(), f"{label} is missing: {path}")
        actual = sha256(path)
        require(actual == expected, f"{label} hash drift: {path} expected={expected} actual={actual}")
        output[str(path)] = actual
    return output


def active_blocked_processes() -> list[dict[str, Any]]:
    result = subprocess.run(
        ["tasklist.exe", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    matches: list[dict[str, Any]] = []
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) < 2:
            continue
        name = row[0].strip().lower()
        if name in BLOCKED_PROCESS_NAMES:
            try:
                pid = int(row[1])
            except ValueError:
                pid = None
            matches.append({"name": row[0], "pid": pid})
    return matches


def write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def copy_exclusive(source: Path, target: Path) -> None:
    with source.open("rb") as input_stream, target.open("xb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
        output_stream.flush()
        os.fsync(output_stream.fileno())
    shutil.copystat(source, target, follow_symlinks=False)


def main() -> None:
    require(PROJECT_FILE.is_file() and sha256(PROJECT_FILE) == PROJECT_SHA256, "RedMMO project descriptor drift")
    require(HOME_MAP.is_file() and sha256(HOME_MAP) == HOME_MAP_SHA256, "Home-map preimage drift")
    require(SOURCE_SHIP.is_file() and sha256(SOURCE_SHIP) == SOURCE_SHIP_SHA256, "Source ship drift")
    blocked = active_blocked_processes()
    require(not blocked, f"Unreal/build process is active: {blocked}")

    _build, _fresh, assets = verify_reports_and_assets()
    protected = verify_hashes(PROTECTED_FILES, "protected checkpoint")
    require(not active_blocked_processes(), "Unreal/build process started during checkpoint preflight")

    created = datetime.now(timezone.utc)
    stamp = created.strftime("%Y%m%dT%H%M%SZ")
    final_dir = ROLLBACK_ROOT / (FINAL_PREFIX + stamp)
    require(not final_dir.exists(), f"Rollback target already exists: {final_dir}")
    ROLLBACK_ROOT.mkdir(parents=True, exist_ok=True)
    staging_dir = ROLLBACK_ROOT / ("." + FINAL_PREFIX + stamp + "." + uuid.uuid4().hex + ".staging")
    require(not staging_dir.exists(), f"Rollback staging collision: {staging_dir}")

    try:
        staging_dir.mkdir(parents=False, exist_ok=False)
        staging_copy = staging_dir / MAP_COPY_NAME
        staging_manifest = staging_dir / MANIFEST_NAME
        copy_exclusive(HOME_MAP, staging_copy)
        require(sha256(staging_copy) == HOME_MAP_SHA256, "Rollback map-copy hash mismatch")

        final_copy = final_dir / MAP_COPY_NAME
        final_manifest = final_dir / MANIFEST_NAME
        manifest = {
            "schema": "redmmo.home_gameplay_bind.a01.rollback.v1",
            "status": "PASS_READY_FOR_MAP_BIND",
            "created_utc": created.isoformat(),
            "authorized_scope": (
                "Set only RedMMO_PPG_HomeWorld WorldSettings.default_game_mode to "
                "/Game/RedMMO/Gameplay/Trooper/A01/Player/GM_RedTrooperPPG_A01_C "
                "and remove exactly the single RedMMO_R12_ParkedStarSparrow_VisualOnly actor."
            ),
            "home_map": str(HOME_MAP),
            "home_map_sha256": HOME_MAP_SHA256,
            "rollback_map_copy": str(final_copy),
            "rollback_map_copy_sha256": HOME_MAP_SHA256,
            "evidence": {
                "build_report": {"path": str(BUILD_REPORT), "sha256": BUILD_REPORT_SHA256},
                "fresh_report": {"path": str(FRESH_REPORT), "sha256": FRESH_REPORT_SHA256},
            },
            "project": {"path": str(PROJECT_FILE), "sha256": PROJECT_SHA256},
            "source_ship": {"path": str(SOURCE_SHIP), "sha256": SOURCE_SHIP_SHA256},
            "protected_hashes": protected,
            "a01_assets": assets,
            "expected_map_contract_before": {
                "actor_count": 12,
                "unique_ppg_spawner_class": "PlanetSpawnerBP_C",
                "ppg_planet_data": "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/DA_PPG_HomeWorld_StylizedBinding_R10O",
                "old_visual_ship_label": "RedMMO_R12_ParkedStarSparrow_VisualOnly",
            },
            "rollback_instructions": (
                "Close Unreal and all Unreal/build helpers. Verify the destination is exactly home_map, "
                "then copy rollback_map_copy over home_map and verify rollback_map_copy_sha256. "
                "No other project file is part of this map-only rollback."
            ),
        }
        write_json_exclusive(staging_manifest, manifest)
        require(
            sorted(path.name for path in staging_dir.iterdir())
            == sorted([MANIFEST_NAME, MAP_COPY_NAME]),
            "Rollback staging contains unexpected files",
        )
        require(not active_blocked_processes(), "Unreal/build process started during checkpoint copy")
        os.rename(staging_dir, final_dir)
        require(final_copy.is_file() and sha256(final_copy) == HOME_MAP_SHA256, "Published rollback copy drift")
        require(final_manifest.is_file(), "Published rollback manifest is missing")
        require(
            sorted(path.name for path in final_dir.iterdir())
            == sorted([MANIFEST_NAME, MAP_COPY_NAME]),
            "Published rollback contains unexpected files",
        )
        print(str(final_manifest))
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise


if __name__ == "__main__":
    main()
