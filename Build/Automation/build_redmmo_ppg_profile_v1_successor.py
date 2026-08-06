"""Create an isolated project-owned PPG ProfileV1 asset successor.

This deliberately does not load or save a map.  It duplicates the exact R17
PlanetData plus its generation, biome-mask, and surface material assets into a
project-owned authoring folder, then rebinds only the duplicate PlanetData.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1Successor_20260805_0345")
RESULT = DIAG / "build_redmmo_ppg_profile_v1_successor_result.json"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1Successor_20260805T0345Z")

SOURCE_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/SeededBiomeSurface/R17/DA_PPG_HomeWorld_SeededBiomeSurface_R17"
SOURCE_GENERATION = "/Game/RedMMO/World/PPG/HomeWorld/SmoothTerrain/R16/Materials/M_PPG_Generation_SmoothRolling_R16"
SOURCE_MASK = "/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15/Materials/M_PPG_BiomeMask_Continents_R15"
SOURCE_SURFACE = "/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15/Materials/MI_PPG_Home_BiomeSurface_R15"

TARGET_ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
TARGET_PLANET = TARGET_ROOT + "/DA_PPG_ProfileV1_PlanetData"
TARGET_GENERATION = TARGET_ROOT + "/M_PPG_ProfileV1_Generation"
TARGET_MASK = TARGET_ROOT + "/M_PPG_ProfileV1_BiomeMask"
TARGET_SURFACE = TARGET_ROOT + "/MI_PPG_ProfileV1_Surface"

SOURCE_HASHES = {
    SOURCE_PLANET: "ADFC9D79B509A9998C66229CF67E65C6E560E238141BE30F22C705075C3C6C55",
    SOURCE_GENERATION: "95756266D3BF470D1B0907257B0CA978F8755129EE2A03C88082675FD244D92E",
    SOURCE_MASK: "D8A11945E6AD4EDFF7E1B17B489CF83FA12A0C96A8E63902EBB78295E37FBB72",
    SOURCE_SURFACE: "1A8568B6F37A63B82E974915511029B28360F0C8DD6D448B66B6708566766E43",
}

PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value):
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def asset_file(path):
    require(path.startswith("/Game/"), "Unexpected project asset path: " + path)
    return PROJECT / ("Content" + path.removeprefix("/Game").replace("/", os.sep) + ".uasset")


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({asset_path(value) for value in values})


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def provider_gate():
    records = []
    for port in (5353, 8000, 8765, 11111):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.25)
        try:
            code = sock.connect_ex(("127.0.0.1", port))
        finally:
            sock.close()
        records.append({"port": port, "closed": code != 0, "connect_ex": code})
    require(all(item["closed"] for item in records), "Provider/MCP listener active")
    return records


def load(path):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    return asset


def biome_records(planet):
    return [
        {
            "name": str(item.get_editor_property("name")),
            "foliage_data": asset_path(item.get_editor_property("foliage_data")),
        }
        for item in list(planet.get_editor_property("biome_data"))
    ]


def core_record(planet):
    return {
        "class": planet.get_class().get_name(),
        "generation_seed": int(planet.get_editor_property("generation_seed")),
        "planet_radius": float(planet.get_editor_property("planet_radius")),
        "noise_height": float(planet.get_editor_property("noise_height")),
        "generate_water": bool(planet.get_editor_property("generate_water")),
        "water_material": asset_path(planet.get_editor_property("water_material")),
        "biome_cell_map": asset_path(planet.get_editor_property("biome_cell_map")),
        "biomes": biome_records(planet),
    }


def snapshot_rollback():
    require(not ROLLBACK.exists(), "Rollback no-clobber failed")
    ROLLBACK.mkdir(parents=True, exist_ok=False)
    copied = []
    for source, expected in SOURCE_HASHES.items():
        source_file = asset_file(source)
        require(source_file.is_file() and sha256(source_file) == expected, "Source hash drift: " + source)
        destination = ROLLBACK / source_file.name
        shutil.copy2(source_file, destination)
        require(sha256(destination) == expected, "Rollback copy mismatch: " + source)
        copied.append({"source": str(source_file), "sha256": expected, "rollback": str(destination)})
    manifest = {
        "schema": "redmmo.ppg_profile_v1_successor.rollback.v1",
        "captured_utc": now(),
        "targets_existed_before": False,
        "copied_sources": copied,
        "restore": "Close Unreal and delete only /Game/RedMMO/WorldAuthoring/PPG/ProfileV1; source packages and home map were never edited.",
    }
    write_json_exclusive(ROLLBACK / "manifest.json", manifest)
    return manifest


_EXIT = {"handle": None}


def schedule_exit(delay=7.0):
    started = time.monotonic()

    def tick(_delta):
        if time.monotonic() - started < delay:
            return
        handle = _EXIT.get("handle")
        if handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(handle)
            except Exception:
                pass
            _EXIT["handle"] = None
        unreal.SystemLibrary.quit_editor()

    _EXIT["handle"] = unreal.register_slate_post_tick_callback(tick)


def main():
    report = {
        "schema": "redmmo.ppg_profile_v1_successor.build.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "editor_automation_persisted_assets_no_map_change",
    }
    created = []
    try:
        require(
            os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
            == os.path.normcase(os.path.abspath(str(PROJECT_FILE))),
            "Active project mismatch",
        )
        require(not RESULT.exists(), "Result no-clobber failed")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
        report["provider_gate"] = provider_gate()
        report["protected_hashes_before"] = {}
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected hash drift: " + str(path))
            report["protected_hashes_before"][str(path)] = expected
        require(not dirty_packages(), "Dirty packages before successor build")
        for target in (TARGET_PLANET, TARGET_GENERATION, TARGET_MASK, TARGET_SURFACE):
            require(not unreal.EditorAssetLibrary.does_asset_exist(target), "Target exists: " + target)
            require(not asset_file(target).exists(), "Target file exists: " + target)

        report["rollback"] = snapshot_rollback()
        source_planet = load(SOURCE_PLANET)
        source_generation = load(SOURCE_GENERATION)
        source_mask = load(SOURCE_MASK)
        source_surface = load(SOURCE_SURFACE)
        require(source_planet.get_class().get_name() == "PlanetData", "Source PlanetData class mismatch")
        require(asset_path(source_planet.get_editor_property("generation_material")) == SOURCE_GENERATION, "R17 generation ref drift")
        require(asset_path(source_planet.get_editor_property("biome_mask_material")) == SOURCE_MASK, "R17 mask ref drift")
        require(asset_path(source_planet.get_editor_property("planet_material")) == SOURCE_SURFACE, "R17 surface ref drift")
        source_core = core_record(source_planet)

        generation = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_GENERATION, TARGET_GENERATION)
        require(generation is not None and generation.get_class() == source_generation.get_class(), "Generation duplicate failed")
        created.append(TARGET_GENERATION)
        mask = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_MASK, TARGET_MASK)
        require(mask is not None and mask.get_class() == source_mask.get_class(), "Biome-mask duplicate failed")
        created.append(TARGET_MASK)
        surface = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_SURFACE, TARGET_SURFACE)
        require(surface is not None and surface.get_class() == source_surface.get_class(), "Surface duplicate failed")
        created.append(TARGET_SURFACE)
        planet = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_PLANET, TARGET_PLANET)
        require(planet is not None and planet.get_class() == source_planet.get_class(), "PlanetData duplicate failed")
        created.append(TARGET_PLANET)

        planet.set_editor_property("generation_material", generation)
        planet.set_editor_property("biome_mask_material", mask)
        planet.set_editor_property("planet_material", surface)
        require(core_record(planet) == source_core, "Non-material PlanetData fields drifted")
        require(asset_path(planet.get_editor_property("generation_material")) == TARGET_GENERATION, "Target generation rebind failed")
        require(asset_path(planet.get_editor_property("biome_mask_material")) == TARGET_MASK, "Target mask rebind failed")
        require(asset_path(planet.get_editor_property("planet_material")) == TARGET_SURFACE, "Target surface rebind failed")

        for asset in (generation, mask, surface, planet):
            require(unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False), "Asset save failed: " + asset_path(asset))
        require(not dirty_packages(), "Dirty packages remain after saves")

        require(asset_path(source_planet.get_editor_property("generation_material")) == SOURCE_GENERATION, "Source generation ref changed")
        require(asset_path(source_planet.get_editor_property("biome_mask_material")) == SOURCE_MASK, "Source mask ref changed")
        require(asset_path(source_planet.get_editor_property("planet_material")) == SOURCE_SURFACE, "Source surface ref changed")
        source_hashes_after = {source: sha256(asset_file(source)) for source in SOURCE_HASHES}
        require(source_hashes_after == SOURCE_HASHES, "Source package hash changed")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map changed")

        target_hashes = {}
        for target in created:
            require(asset_file(target).is_file(), "Target package missing after save: " + target)
            target_hashes[target] = sha256(asset_file(target))
        protected_after = {str(path): sha256(path) for path in PROTECTED}
        require(protected_after == report["protected_hashes_before"], "Protected hashes changed")

        report.update({
            "status": "PASS_PROJECT_OWNED_PROFILE_V1_SUCCESSOR_CREATED_UNBOUND",
            "source_planet": SOURCE_PLANET,
            "source_materials": [SOURCE_GENERATION, SOURCE_MASK, SOURCE_SURFACE],
            "source_core": source_core,
            "source_hashes_after": source_hashes_after,
            "created_packages": created,
            "target_hashes": target_hashes,
            "target_bindings": {
                "generation_material": TARGET_GENERATION,
                "biome_mask_material": TARGET_MASK,
                "planet_material": TARGET_SURFACE,
            },
            "home_map_sha256_before_after": EXPECTED_HOME,
            "home_map_loaded": False,
            "home_map_saved": False,
            "profile_values_changed": False,
            "protected_hashes_after": protected_after,
            "dirty_packages": dirty_packages(),
        })
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["created_packages"] = created
        report["rollback_required"] = bool(created)
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PPG_PROFILE_V1_SUCCESSOR " + report["status"])
        schedule_exit()


main()
