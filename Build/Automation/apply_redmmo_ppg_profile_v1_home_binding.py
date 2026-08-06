"""Bind the verified unbound ProfileV1 PlanetData to the clean RedMMO home map.

The transaction may change only the PlanetSpawner PlanetData reference in the
existing home map. It does not call generation, start PIE, alter ProfileV1,
change gameplay actors, or save any other package.
"""

from __future__ import annotations

import hashlib
import json
import os
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
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"
ROLLBACK_FILE = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1HomeBinding_20260805T0627Z\RedMMO_PPG_HomeWorld.pre_profile_v1_binding.umap")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1HomeBinding_20260805_0627")
RESULT = DIAG / "apply_redmmo_ppg_profile_v1_home_binding_result.json"

SOURCE_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/SeededBiomeSurface/R17/DA_PPG_HomeWorld_SeededBiomeSurface_R17"
TARGET_ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
TARGET_PLANET = TARGET_ROOT + "/DA_PPG_ProfileV1_PlanetData"
TARGET_GENERATION = TARGET_ROOT + "/M_PPG_ProfileV1_Generation"
TARGET_MASK = TARGET_ROOT + "/M_PPG_ProfileV1_BiomeMask"
TARGET_SURFACE = TARGET_ROOT + "/MI_PPG_ProfileV1_Surface"

EXPECTED_FILES = {
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\SeededBiomeSurface\R17\DA_PPG_HomeWorld_SeededBiomeSurface_R17.uasset":
        "ADFC9D79B509A9998C66229CF67E65C6E560E238141BE30F22C705075C3C6C55",
    PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset":
        "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837",
    PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_Generation.uasset":
        "5165A27F0423735256EEE768739CE9547FEF7849BCA05540AAD63DF5BA1D96E3",
    PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_BiomeMask.uasset":
        "6A4EA303452559810E4FF805FE86AD7057D9807069B3585A8CC9489279BFA66D",
    PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_SurfaceParent.uasset":
        "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768",
    PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\MI_PPG_ProfileV1_Surface.uasset":
        "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66",
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


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({asset_path(value) for value in values})


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
    require(all(record["closed"] for record in records), "Provider/MCP listener active")
    return records


def load(path, class_name=None):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    if class_name:
        require(asset.get_class().get_name() == class_name, "Class mismatch: " + path)
    return asset


def biome_records(planet):
    return [
        {
            "name": str(item.get_editor_property("name")),
            "foliage_data": asset_path(item.get_editor_property("foliage_data")),
        }
        for item in list(planet.get_editor_property("biome_data"))
    ]


def actor_snapshot(actor):
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return {
        "class": actor.get_class().get_name(),
        "path": actor.get_path_name(),
        "location": [float(location.x), float(location.y), float(location.z)],
        "rotation": [float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
        "scale": [float(scale.x), float(scale.y), float(scale.z)],
    }


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


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
        "schema": "redmmo.ppg_profile_v1.home_binding.apply.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        require(not RESULT.exists(), "Result no-clobber failed")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map preimage hash drift")
        require(ROLLBACK_FILE.is_file() and sha256(ROLLBACK_FILE) == EXPECTED_HOME, "Rollback preimage mismatch")
        require(not dirty_packages(), "Dirty packages before binding")
        report["provider_gate"] = provider_gate()
        for path, expected_hash in EXPECTED_FILES.items():
            require(path.is_file() and sha256(path) == expected_hash, "Authenticated input hash drift: " + str(path))
        for path, expected_hash in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Protected hash drift: " + str(path))

        source = load(SOURCE_PLANET, "PlanetData")
        target = load(TARGET_PLANET, "PlanetData")
        require(int(target.get_editor_property("generation_seed")) == 1337, "ProfileV1 seed drift")
        require(abs(float(target.get_editor_property("planet_radius")) - 300000000.0) <= 0.01,
                "ProfileV1 radius drift")
        require(abs(float(target.get_editor_property("noise_height")) - 600000.0) <= 0.01,
                "ProfileV1 noise-height drift")
        require(asset_path(target.get_editor_property("generation_material")) == TARGET_GENERATION,
                "ProfileV1 generation binding drift")
        require(asset_path(target.get_editor_property("biome_mask_material")) == TARGET_MASK,
                "ProfileV1 biome-mask binding drift")
        require(asset_path(target.get_editor_property("planet_material")) == TARGET_SURFACE,
                "ProfileV1 surface binding drift")
        require(bool(target.get_editor_property("generate_water")), "ProfileV1 native water disabled")
        require(asset_path(target.get_editor_property("water_material")) == "/PPG/Water/Materials/M_PlanetaryOceanWater",
                "ProfileV1 native water material drift")
        source_biomes = biome_records(source)
        target_biomes = biome_records(target)
        require(target_biomes == source_biomes, "ProfileV1 biome names or foliage bindings differ from R17")
        require([item["name"] for item in target_biomes] == ["Craters", "Hills", "Mountains", "Desert", "Ocean", "Poles"],
                "ProfileV1 biome order drift")

        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None and not dirty_packages(), "Home map load failed or dirtied packages")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        require(len(actors) == 11, "Home actor count drift")
        snapshots_before = [actor_snapshot(actor) for actor in actors]
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "Expected exactly one PlanetSpawnerBP_C")
        spawner = spawners[0]
        require(asset_path(spawner.get_editor_property("planet_data")) == SOURCE_PLANET,
                "Current R17 home binding drift")
        require(int(spawner.get_editor_property("max_foliage_instances_per_chunk")) == 100000,
                "Foliage cap drift")
        world_settings = world.get_world_settings()
        require(asset_path(world_settings.get_editor_property("default_game_mode")) ==
                "/Game/RedMMO/Gameplay/Trooper/A01/Player/GM_RedTrooperPPG_A01",
                "A01 GameMode drift")

        spawner.set_editor_property("planet_data", target)
        require(asset_path(spawner.get_editor_property("planet_data")) == TARGET_PLANET,
                "ProfileV1 binding assignment failed")
        dirty_before_save = dirty_packages()
        require(set(dirty_before_save).issubset({HOME_MAP}),
                "Unexpected dirty package before home save: " + repr(dirty_before_save))
        require(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level(),
                "ProfileV1 home-map save failed")
        require(not dirty_packages(), "Dirty packages remain after binding save")

        actors_after = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        require([actor_snapshot(actor) for actor in actors_after] == snapshots_before,
                "Actor identity or transform drift during binding")
        new_hash = sha256(HOME_FILE)
        require(new_hash != EXPECTED_HOME, "Home map hash did not change")
        for path, expected_hash in EXPECTED_FILES.items():
            require(sha256(path) == expected_hash, "Input package changed: " + str(path))
        for path, expected_hash in PROTECTED.items():
            require(sha256(path) == expected_hash, "Protected package changed: " + str(path))

        report.update({
            "status": "PASS_PROFILE_V1_BOUND_TO_HOME_PENDING_FRESH_RELOAD_MAPCHECK_RUNTIME_VISUAL",
            "home_map": HOME_MAP,
            "home_map_sha256_before": EXPECTED_HOME,
            "home_map_sha256_after": new_hash,
            "rollback_file": str(ROLLBACK_FILE),
            "source_planet_data": SOURCE_PLANET,
            "target_planet_data": TARGET_PLANET,
            "generation_seed": 1337,
            "planet_radius_cm": 300000000.0,
            "noise_height_cm": 600000.0,
            "biomes": target_biomes,
            "native_water_preserved": True,
            "actor_count_before_after": len(actors),
            "actor_identity_transforms_preserved": True,
            "max_foliage_instances_per_chunk": 100000,
            "a01_game_mode_preserved": True,
            "map_saved": True,
            "profile_packages_saved": False,
            "regeneration_called": False,
            "pie_started": False,
            "dirty_packages_after": dirty_packages(),
            "next_safe_action": "Separate fresh-process reload plus MapCheck; only if that passes, run bounded real-D3D12 generation/gameplay/visual acceptance and retain rollback if rejected.",
        })
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["home_hash_observed"] = sha256(HOME_FILE) if HOME_FILE.is_file() else None
        report["rollback_required"] = report["home_hash_observed"] not in (None, EXPECTED_HOME)
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PPG_PROFILE_V1_HOME_BINDING " + report["status"])
        schedule_exit()


main()
