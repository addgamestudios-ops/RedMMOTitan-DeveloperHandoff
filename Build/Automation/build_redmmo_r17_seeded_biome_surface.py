"""Create and bind the R17 seeded-biome surface successor in clean RedMMO.

R17 reuses the proven R15 six-biome mask/surface graph but keeps the accepted
R16 smooth terrain generator.  It changes one project-owned PlanetData package
and the home-map PlanetSpawner binding only; seed, radius, native water,
foliage data, gameplay assets, vendor assets, and protected production maps are
asserted unchanged.
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
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "3EBFB65273119A7C6F49B94BB85509E053B5FB4DA96474DFD02B845A179529BF"

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_SeededBiomeSurface_R17_20260804_1907")
RESULT = DIAG / "build_r17_seeded_biome_surface_result.json"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_SeededBiomeSurface_R17_20260804_1907_A01")
ROLLBACK_HOME = ROLLBACK / "RedMMO_PPG_HomeWorld.pre_r17.umap"
ROLLBACK_MANIFEST = ROLLBACK / "pre_r17_manifest.json"

R15_ROOT = "/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15"
SOURCE_R15_PLANET = R15_ROOT + "/DA_PPG_HomeWorld_ContinentBiome_R15"
SOURCE_R15_MASK = R15_ROOT + "/Materials/M_PPG_BiomeMask_Continents_R15"
SOURCE_R15_SURFACE = R15_ROOT + "/Materials/MI_PPG_Home_BiomeSurface_R15"
SOURCE_R15_CELL_MAP = R15_ROOT + "/DA_PPG_HomeWorld_ContinentBiome_R15_PPG_BiomeCells"

R16_ROOT = "/Game/RedMMO/World/PPG/HomeWorld/SmoothTerrain/R16"
SOURCE_R16_PLANET = R16_ROOT + "/DA_PPG_HomeWorld_SmoothTerrain_R16"
SOURCE_R16_GENERATION = R16_ROOT + "/Materials/M_PPG_Generation_SmoothRolling_R16"

R17_ROOT = "/Game/RedMMO/World/PPG/HomeWorld/SeededBiomeSurface/R17"
TARGET_PLANET = R17_ROOT + "/DA_PPG_HomeWorld_SeededBiomeSurface_R17"

SOURCE_HASHES = {
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15\DA_PPG_HomeWorld_ContinentBiome_R15.uasset":
        "47924E95B2CF2A730065709E4BF7861A33B2C3D1A0872E8E9124AD8C500FD4D0",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15\DA_PPG_HomeWorld_ContinentBiome_R15_PPG_BiomeCells.uasset":
        "123F39A471D29FBDDB096E842F2620A4460FD77F43613DA1A045644F560E2162",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15\Materials\M_PPG_BiomeMask_Continents_R15.uasset":
        "D8A11945E6AD4EDFF7E1B17B489CF83FA12A0C96A8E63902EBB78295E37FBB72",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15\Materials\MI_PPG_Home_BiomeSurface_R15.uasset":
        "1A8568B6F37A63B82E974915511029B28360F0C8DD6D448B66B6708566766E43",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\SmoothTerrain\R16\DA_PPG_HomeWorld_SmoothTerrain_R16.uasset":
        "CB1C0168965F0EE10868E0E1A004494CDEEBCED8D88752B0FEF4344CE1F0F234",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\SmoothTerrain\R16\Materials\M_PPG_Generation_SmoothRolling_R16.uasset":
        "95756266D3BF470D1B0907257B0CA978F8755129EE2A03C88082675FD244D92E",
}

PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"):
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
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


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({asset_path(value) for value in values})


def provider_gate():
    records = []
    for port in (5353, 8000, 8765):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.25)
        try:
            code = sock.connect_ex(("127.0.0.1", port))
        finally:
            sock.close()
        records.append({"port": port, "closed": code != 0})
    require(all(record["closed"] for record in records), "Provider listener active")
    return records


def load(path, class_name=None):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    if class_name:
        require(asset.get_class().get_name() == class_name, "Class mismatch: " + path)
    return asset


def biome_records(planet):
    records = []
    for item in list(planet.get_editor_property("biome_data")):
        records.append({
            "name": str(item.get_editor_property("name")),
            "foliage_data": asset_path(item.get_editor_property("foliage_data")),
        })
    return records


def snapshot_rollback():
    require(not ROLLBACK.exists(), "Rollback no-clobber failed")
    ROLLBACK.mkdir(parents=True, exist_ok=False)
    shutil.copy2(HOME_FILE, ROLLBACK_HOME)
    require(sha256(ROLLBACK_HOME) == EXPECTED_HOME, "Rollback map copy mismatch")
    manifest = {
        "schema": "redmmo.ppg_seeded_biome_surface.r17.rollback.v1",
        "captured_utc": now(),
        "home_map": str(HOME_FILE),
        "home_map_sha256": EXPECTED_HOME,
        "rollback_map": str(ROLLBACK_HOME),
        "rollback_map_sha256": sha256(ROLLBACK_HOME),
        "target_planet": TARGET_PLANET,
        "target_existed_before": False,
        "restore": "Close Unreal, restore rollback_map over home_map, delete the R17 target package, then fresh reload and MapCheck.",
    }
    write_json_exclusive(ROLLBACK_MANIFEST, manifest)
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
        "schema": "redmmo.ppg_seeded_biome_surface.r17.build.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "editor_automation_persisted",
    }
    target_created = False
    try:
        require(
            os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
            == os.path.normcase(os.path.abspath(str(PROJECT_FILE))),
            "Active project mismatch",
        )
        require(not RESULT.exists(), "Result no-clobber failed")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
        require(not unreal.EditorAssetLibrary.does_asset_exist(TARGET_PLANET), "R17 target already exists")
        require(not asset_file(TARGET_PLANET).exists(), "R17 target file already exists")
        report["provider_gate"] = provider_gate()
        for path, expected in SOURCE_HASHES.items():
            require(path.is_file() and sha256(path) == expected, "Source hash drift: " + str(path))
        report["source_hashes"] = {str(path): sha256(path) for path in SOURCE_HASHES}
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected hash drift: " + str(path))
        report["protected_hashes_before"] = {str(path): sha256(path) for path in PROTECTED}
        require(not dirty_packages(), "Dirty packages before R17 build")
        report["rollback"] = snapshot_rollback()

        source_r15 = load(SOURCE_R15_PLANET, "PlanetData")
        source_r16 = load(SOURCE_R16_PLANET, "PlanetData")
        generation_r16 = load(SOURCE_R16_GENERATION, "Material")
        mask_r15 = load(SOURCE_R15_MASK, "Material")
        surface_r15 = load(SOURCE_R15_SURFACE, "MaterialInstanceConstant")
        cell_r15 = load(SOURCE_R15_CELL_MAP, "Texture2D")
        target = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_R15_PLANET, TARGET_PLANET)
        require(target is not None and target.get_class().get_name() == "PlanetData", "R17 duplicate failed")
        target_created = True
        target.set_editor_property("generation_material", generation_r16)

        require(int(target.get_editor_property("generation_seed")) == 1337, "R17 seed drift")
        require(abs(float(target.get_editor_property("planet_radius")) - 300000000.0) <= 0.01, "R17 radius drift")
        require(abs(float(target.get_editor_property("noise_height")) - 600000.0) <= 0.01, "R17 noise-height drift")
        require(asset_path(target.get_editor_property("generation_material")) == SOURCE_R16_GENERATION, "R17 generation binding failed")
        require(asset_path(target.get_editor_property("biome_mask_material")) == SOURCE_R15_MASK, "R17 mask binding drift")
        require(asset_path(target.get_editor_property("planet_material")) == SOURCE_R15_SURFACE, "R17 surface binding drift")
        require(asset_path(target.get_editor_property("biome_cell_map")) == SOURCE_R15_CELL_MAP, "R17 cell-map binding drift")
        require(bool(target.get_editor_property("generate_water")), "R17 native water disabled")
        require(asset_path(target.get_editor_property("water_material")) == "/PPG/Water/Materials/M_PlanetaryOceanWater", "R17 water binding drift")
        expected_biomes = biome_records(source_r16)
        actual_biomes = biome_records(target)
        require(actual_biomes == expected_biomes, "R17 biome names/foliage differ from R16")
        require([item["name"] for item in actual_biomes] == ["Craters", "Hills", "Mountains", "Desert", "Ocean", "Poles"], "R17 biome order drift")
        require(unreal.EditorAssetLibrary.save_loaded_asset(target, only_if_is_dirty=False), "R17 PlanetData save failed")

        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None and not dirty_packages(), "Home map load failed/dirtied packages")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        require(len(actors) == 11, "Home actor count drift")
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "Expected one PlanetSpawnerBP_C")
        spawner = spawners[0]
        require(asset_path(spawner.get_editor_property("planet_data")) == SOURCE_R16_PLANET, "Current R16 binding drift")
        require(int(spawner.get_editor_property("max_foliage_instances_per_chunk")) == 100000, "Foliage cap drift")
        spawner.set_editor_property("planet_data", target)
        require(set(dirty_packages()).issubset({HOME_MAP}), "Unexpected dirty package before map save")
        require(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level(), "R17 home-map save failed")
        require(not dirty_packages(), "Dirty packages remain after R17 save")

        report.update({
            "status": "PASS_PERSISTED_R17_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_GPU",
            "home_map_sha256_before": EXPECTED_HOME,
            "home_map_sha256_after": sha256(HOME_FILE),
            "target_planet": TARGET_PLANET,
            "target_planet_sha256": sha256(asset_file(TARGET_PLANET)),
            "generation_material": SOURCE_R16_GENERATION,
            "biome_mask_material": SOURCE_R15_MASK,
            "surface_material": SOURCE_R15_SURFACE,
            "biome_cell_map": SOURCE_R15_CELL_MAP,
            "biomes": actual_biomes,
            "map_actor_count": len(actors),
            "seed": 1337,
            "native_water_preserved": True,
            "approved_foliage_bindings_preserved": True,
            "map_saved": True,
            "created_packages": [TARGET_PLANET],
            "dirty_packages": dirty_packages(),
        })
        report["protected_hashes_after"] = {str(path): sha256(path) for path in PROTECTED}
        require(report["protected_hashes_after"] == report["protected_hashes_before"], "Protected hashes changed")
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["target_created"] = target_created
        report["rollback_required_if_home_hash_changed"] = HOME_FILE.is_file() and sha256(HOME_FILE) != EXPECTED_HOME
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_R17_SEEDED_BIOME_SURFACE " + report["status"])
        schedule_exit()


main()
