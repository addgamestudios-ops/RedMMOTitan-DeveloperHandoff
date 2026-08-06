"""Build the R10O cap-headroom candidate while retaining R10N visuals and terrain."""

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
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "A0F4FECBAAB38CCC40D5B667706D72E8402C2312EB523AAB28CD4C1F1A26C665"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomePresentation_R10O_20260802_183909")
RESULT = DIAG / "build_r10o_cap_safe_grass_density_result.json"
PROFILE = PROJECT / r"Config\RedMMO\PPGStylizedFoliageProfiles\HomeWorld_Presentation_R10O.json"
ROLLBACK_MANIFEST = Path(r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_HomePresentation_R10O_20260802_183909_A01\pre_r10o_manifest.json")
ROLLBACK_HOME = Path(r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_HomePresentation_R10O_20260802_183909_A01\RedMMO_PPG_HomeWorld.pre_r10o.umap")

SOURCE_ROOT = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N"
SOURCE_PLANET = SOURCE_ROOT + "/DA_PPG_HomeWorld_StylizedBinding_R10N"
SOURCE_FOLIAGE = SOURCE_ROOT + "/Profiles/DA_PPG_HomeWorld_StylizedForest_R10N"
SOURCE_GENERATION = SOURCE_ROOT + "/Materials/M_PPG_Generation_SmoothSpawnGrass_R10N"
SOURCE_SURFACE = SOURCE_ROOT + "/Materials/MI_PPG_Home_PaintedLeafGround_Scaled_R10N"
SOURCE_GRASS_MESHES = [
    SOURCE_ROOT + "/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    SOURCE_ROOT + "/Meshes/SM_GrassChunk_DenseTall_B_R10N",
]
SOURCE_GRASS_MIS = [
    SOURCE_ROOT + "/Materials/MI_GrassChunks_DenseTall_A_R10N",
    SOURCE_ROOT + "/Materials/MI_GrassChunks_DenseTall_B_R10N",
]

ROOT = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O"
TARGET_PLANET = ROOT + "/DA_PPG_HomeWorld_StylizedBinding_R10O"
TARGET_FOLIAGE = ROOT + "/Profiles/DA_PPG_HomeWorld_StylizedForest_R10O"
GRASS_DENSITY = 90.0

SOURCE_HASHES = {
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\DA_PPG_HomeWorld_StylizedBinding_R10N.uasset": "C6544BF727A7F8865618C18220747F20150341139677688DB1AC7F902BE9D1EF",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Profiles\DA_PPG_HomeWorld_StylizedForest_R10N.uasset": "B05F83E98247ED2387E6BADEB5BBBF59484EFE0C512DBE9420ED8063ABFDBCD9",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\M_PPG_Generation_SmoothSpawnGrass_R10N.uasset": "43EA98C552B42A28C90C588A588E6B30C9C63ABE02E1E99D744D02E6D65A1FD0",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_PPG_Home_PaintedLeafGround_Scaled_R10N.uasset": "A6ED14A2C495A1F7527F9AA79CA3C317E7E0101E155C4926015CCCE5927E95DB",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset": "6B6410611A60F382B57BA92C35B585D4954F491434680F1B6E74080A578ECCA0",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset": "FA3994C498C80335E2077AAF8EDD41AEF5A32C0B4E3EABA1BB02E1A10F63950B",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset": "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset": "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"): "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"): "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"): "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap"): "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
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


def write_json_exclusive(path, payload):
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted(set(asset_path(item) for item in values))


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
    require(all(item["closed"] for item in records), "Provider listener active")
    return records


def load(path, class_name=None):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    if class_name:
        require(asset.get_class().get_name() == class_name, "Class mismatch: " + path)
    return asset


def duplicate(source, target, created):
    require(not unreal.EditorAssetLibrary.does_asset_exist(target), "Refusing overwrite: " + target)
    asset = unreal.EditorAssetLibrary.duplicate_asset(source, target)
    require(asset is not None, "Duplicate failed: {} -> {}".format(source, target))
    created.append(target)
    return asset


def normalized_key(name):
    return str(name).replace("_", "").replace(" ", "").lower()


def find_key(values, wanted):
    wanted = normalized_key(wanted)
    matches = [key for key in values if normalized_key(key) == wanted]
    require(len(matches) == 1, "Expected one key {} in {}".format(wanted, list(values)))
    return matches[0]


def stable_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {
            normalized_key(key): stable_value(item)
            for key, item in sorted(value.items(), key=lambda pair: normalized_key(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [stable_value(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return stable_value(to_dict())
    get_path_name = getattr(value, "get_path_name", None)
    if callable(get_path_name):
        return asset_path(value)
    return str(value)


def foliage_signature(entry, exclude=()):
    excluded = {normalized_key(item) for item in exclude}
    return {
        normalized_key(key): stable_value(value)
        for key, value in entry.to_dict().items()
        if normalized_key(key) not in excluded
    }


def mesh_bindings(entry):
    return [
        asset_path(item.get_editor_property("mesh"))
        for item in entry.get_editor_property("meshes")
    ]


def verify_rebuilt_foliage(source_entries, target_entries):
    require(len(source_entries) == 3 and len(target_entries) == 3, "Foliage entry count drift")
    for index in (0, 2):
        require(
            foliage_signature(target_entries[index]) == foliage_signature(source_entries[index]),
            "Non-grass foliage entry changed: {}".format(index),
        )

    source_grass = source_entries[1]
    target_grass = target_entries[1]
    require(abs(float(target_grass.get_editor_property("foliage_density")) - GRASS_DENSITY) <= 1.0e-5, "R10O grass density drift")
    require(int(target_grass.get_editor_property("max_slope")) == 30, "R10O grass max slope drift")
    scale = target_grass.get_editor_property("scale")
    require(
        abs(float(scale.get_editor_property("min")) - 1.0) <= 1.0e-5
        and abs(float(scale.get_editor_property("max")) - 1.55) <= 1.0e-5,
        "R10O grass scale drift",
    )
    require(mesh_bindings(target_grass) == SOURCE_GRASS_MESHES, "R10O grass mesh binding drift")
    require("blue" in str(target_grass.get_editor_property("density_vertex_color_channel")).lower(), "R10O density channel is not BLUE")
    require(bool(target_grass.get_editor_property("invert_density_vertex_color_mask")), "R10O density mask inversion drift")
    require(
        foliage_signature(target_grass, exclude=("foliage_density",))
        == foliage_signature(source_grass, exclude=("foliage_density",)),
        "R10O grass reconstruction changed a field other than density",
    )
    target_lods = list(target_grass.get_editor_property("lods"))
    source_lods = list(source_grass.get_editor_property("lods"))
    require(stable_value(target_lods) == stable_value(source_lods), "R10O grass LOD drift")


def build_foliage_and_planet(created):
    source_foliage = load(SOURCE_FOLIAGE, "FoliageData")
    source_entries = list(source_foliage.get_editor_property("foliage_list"))
    require(len(source_entries) == 3, "R10N foliage entry count drift")
    source_grass = source_entries[1]
    require(abs(float(source_grass.get_editor_property("foliage_density")) - 180.0) <= 1.0e-5, "R10N grass density drift")
    foliage = duplicate(SOURCE_FOLIAGE, TARGET_FOLIAGE, created)
    entries = list(foliage.get_editor_property("foliage_list"))
    values = source_grass.to_dict()
    density_key = find_key(values, "foliage_density")
    values[density_key] = GRASS_DENSITY
    entries[1] = unreal.FoliageList(**values)
    foliage.set_editor_property("foliage_list", entries)
    target_entries = list(foliage.get_editor_property("foliage_list"))
    verify_rebuilt_foliage(source_entries, target_entries)
    require(unreal.EditorAssetLibrary.save_loaded_asset(foliage, only_if_is_dirty=False), "R10O foliage save failed")

    source_planet = load(SOURCE_PLANET, "PlanetData")
    planet = duplicate(SOURCE_PLANET, TARGET_PLANET, created)
    require(int(planet.get_editor_property("generation_seed")) == 1337, "R10N seed drift")
    require(abs(float(planet.get_editor_property("planet_radius")) - 300000000.0) <= 0.01, "R10N radius drift")
    require(asset_path(planet.get_editor_property("generation_material")) == SOURCE_GENERATION, "Generation material drift")
    require(asset_path(planet.get_editor_property("planet_material")) == SOURCE_SURFACE, "Surface material drift")
    biomes = list(planet.get_editor_property("biome_data"))
    changed = []
    for index, biome in enumerate(biomes):
        values = biome.to_dict()
        touched = False
        for key in list(values):
            if normalized_key(key) in ("foliagedata", "forestfoliagedata") and asset_path(values[key]) == SOURCE_FOLIAGE:
                values[key] = foliage
                touched = True
        if touched:
            biomes[index] = unreal.BiomeData(**values)
            changed.append(str(biome.get_editor_property("name")))
    require(changed == ["Craters", "Hills", "Mountains"], "R10N biome foliage binding drift: {}".format(changed))
    planet.set_editor_property("biome_data", biomes)
    require(int(planet.get_editor_property("generation_seed")) == int(source_planet.get_editor_property("generation_seed")), "Seed changed")
    require(unreal.EditorAssetLibrary.save_loaded_asset(planet, only_if_is_dirty=False), "R10O PlanetData save failed")
    return foliage, planet, changed


def bind_map(planet):
    world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
    require(world is not None and not dirty_packages(), "Home map load failed/dirtied packages")
    actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
    require(len(actors) == 12, "Home actor count drift")
    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    require(len(spawners) == 1, "Expected one PPG spawner")
    spawner = spawners[0]
    require(asset_path(spawner.get_editor_property("planet_data")) == SOURCE_PLANET, "R10N PlanetData binding drift")
    require(int(spawner.get_editor_property("max_foliage_instances_per_chunk")) == 100000, "Foliage cap drift")
    spawner.set_editor_property("planet_data", planet)
    regenerate = getattr(spawner, "regenerate_planet", None)
    require(callable(regenerate), "Regenerate unavailable")
    regenerate()
    require(set(dirty_packages()).issubset({HOME_MAP}), "Unexpected dirty package before save")
    require(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level(), "Home save failed")
    require(not dirty_packages(), "Dirty packages remain")
    return {
        "actor_labels": sorted(actor.get_actor_label() for actor in actors),
        "spawner_max_foliage_instances_per_chunk": 100000,
    }


def write_profile():
    require(not PROFILE.exists(), "R10O profile no-clobber failed")
    payload = {
        "schema": "redmmo.ppg_home_presentation_profile.r10o.v1",
        "revision": "R10O_cap_headroom_candidate_dense_tall_actual_spawn_grass",
        "source_revision": "R10N",
        "ground": {
            "material": SOURCE_SURFACE,
            "uv_scale": 12.0,
            "macro_uv_scales": [1.0, 2.0],
            "normal_amount": 0.20,
        },
        "grass": {
            "foliage_data": TARGET_FOLIAGE,
            "density": GRASS_DENSITY,
            "source_density": 180.0,
            "scale": [1.0, 1.55],
            "max_slope_degrees": 30.0,
            "local_scale": 1.30,
            "local_z_scale": 1.45,
            "highlight_amount": 0.62,
            "highlight_density": 0.82,
            "highlight_gradient_contrast": 4.20,
            "meshes": SOURCE_GRASS_MESHES,
            "materials": SOURCE_GRASS_MIS,
            "cap_per_chunk": 100000,
            "density_candidate_scaling": "approximately density squared",
            "r10n_editor_generation_max_shared_records_at_density_180": 337648,
            "grass_dominated_estimate_at_density_90": 84412,
            "estimate_caveat": "Trees and rocks share the per-chunk pool; zero overflow requires fresh reload and actual PlayerStart PIE evidence.",
            "cap_was_not_increased": True,
        },
        "terrain": {
            "generation_material": SOURCE_GENERATION,
            "seed": 1337,
            "hills_details_divisor": 200.0,
            "mountain_details_divisor": 100.0,
            "broad_shape_controls_changed": False,
        },
        "vendor_assets_modified": False,
        "human_accepted": False,
    }
    write_json_exclusive(PROFILE, payload)
    return payload


def verify_preconditions():
    require(
        os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        == os.path.normcase(os.path.abspath(str(PROJECT / "RedMMO.uproject"))),
        "Active project mismatch",
    )
    require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "R10N home hash drift")
    require(ROLLBACK_MANIFEST.is_file(), "R10O rollback manifest missing")
    require(ROLLBACK_HOME.is_file() and sha256(ROLLBACK_HOME) == EXPECTED_HOME, "R10O rollback home missing or drifted")
    manifest = json.loads(ROLLBACK_MANIFEST.read_text(encoding="utf-8-sig"))
    require(
        manifest.get("schema") == "redmmo.ppg_home_presentation.r10o.rollback.v1"
        and manifest.get("source_home_sha256") == EXPECTED_HOME,
        "R10O rollback manifest drift",
    )
    require(not unreal.EditorAssetLibrary.does_directory_exist(ROOT), "R10O content root exists")
    require(not PROFILE.exists() and not RESULT.exists(), "R10O output exists")
    require(not dirty_packages(), "Editor dirty before R10O")
    for path, expected in SOURCE_HASHES.items():
        require(path.is_file() and sha256(path) == expected, "R10N source hash drift: " + str(path))
    for path, expected in PROTECTED.items():
        require(path.is_file() and sha256(path) == expected, "Protected hash drift: " + str(path))


_EXIT = {"handle": None}


def schedule_exit(delay=8.0):
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
        "schema": "redmmo.ppg_home_presentation.r10o.build.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "created_assets": [],
    }
    try:
        verify_preconditions()
        report["provider_gate"] = provider_gate()
        foliage, planet, changed = build_foliage_and_planet(report["created_assets"])
        report["map"] = bind_map(planet)
        report["profile"] = write_profile()
        report["changed_biomes"] = changed
        report["home_map_sha256_before"] = EXPECTED_HOME
        report["home_map_sha256_after"] = sha256(HOME_FILE)
        require(report["home_map_sha256_after"] != EXPECTED_HOME, "Home binding did not serialize")
        report["project_owned_hashes"] = {}
        for asset in report["created_assets"]:
            file_path = PROJECT / ("Content" + asset.removeprefix("/Game").replace("/", os.sep) + ".uasset")
            require(file_path.is_file(), "Created asset file missing: " + asset)
            report["project_owned_hashes"][asset] = sha256(file_path)
        report["profile_sha256"] = sha256(PROFILE)
        for path, expected in SOURCE_HASHES.items():
            require(sha256(path) == expected, "R10N source modified: " + str(path))
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected modified: " + str(path))
        require(not dirty_packages(), "Dirty packages remain")
        report["status"] = "PASS_STATIC_SERIALIZATION_PENDING_FRESH_RELOAD_MAPCHECK_AND_ACTUAL_PLAYERSTART_PIE"
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        schedule_exit()


main()
