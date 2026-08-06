"""Finalize the rollback-backed R15 continent/biome successor in clean RedMMO.

The Unreal/Epic MCP stage creates and edits the project-owned assets.  This
single-editor finalizer exists only for the two PPG UFUNCTION calls that the
official MCP toolsets do not expose: rebuild_planet_pipeline and
regenerate_planet.
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
EXPECTED_HOME = "C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0"

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912")
RESULT = DIAG / "finalize_r15_continent_biome_r05_result.json"
PROFILE = PROJECT / r"Config\RedMMO\PPGContinentBiomeProfiles\HomeWorld_ContinentBiome_R15.json"
CHECKPOINT = Path(r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_ContinentBiome_R15_20260802_211912_A01\pre_r15_manifest.json")
STAGE_RESULT = DIAG / "stage_r15_continent_biome_assets_via_epic_mcp_result.json"

SOURCE_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/DA_PPG_HomeWorld_StylizedBinding_R10O"
SOURCE_FOLIAGE = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/Profiles/DA_PPG_HomeWorld_StylizedForest_R10O"
ROOT = "/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15"
TARGET_PLANET = ROOT + "/DA_PPG_HomeWorld_ContinentBiome_R15"
TARGET_GENERATION = ROOT + "/Materials/M_PPG_Generation_Continents_R15"
TARGET_MASK = ROOT + "/Materials/M_PPG_BiomeMask_Continents_R15"
TARGET_SURFACE_PARENT = ROOT + "/Materials/M_PPG_Home_BiomeSurface_R15"
TARGET_SURFACE_MI = ROOT + "/Materials/MI_PPG_Home_BiomeSurface_R15"
TARGET_CELL_MAP = ROOT + "/DA_PPG_HomeWorld_ContinentBiome_R15_PPG_BiomeCells"
TARGETS = [TARGET_PLANET, TARGET_GENERATION, TARGET_MASK, TARGET_SURFACE_PARENT, TARGET_SURFACE_MI]

EXPECTED_STAGE_HASHES = {
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15\DA_PPG_HomeWorld_ContinentBiome_R15.uasset": "B54D5551DF34DB3F07F6A87F1A1DFE3EEF6321E33CA121FA7BC09736B880C850",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15\Materials\M_PPG_Generation_Continents_R15.uasset": "ABA8639EA06F30CCAFB35244E96A375F9433D0FB60014B2766195CD4C8B25048",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15\Materials\M_PPG_BiomeMask_Continents_R15.uasset": "262688D1F71CC00025124923A0368C9906AB3A766C7E8757389BF835FD6DE1B9",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15\Materials\M_PPG_Home_BiomeSurface_R15.uasset": "D2B6DBE3BF6ABBD4DE0C9BA277C682BED2813DDBBB0A48D2308340D25524D653",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15\Materials\MI_PPG_Home_BiomeSurface_R15.uasset": "656D2CA24C5736D6EC27A5B8A8F8240AD6401F64A79931306D944A164B679A8A",
}

SOURCE_HASHES = {
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\DA_PPG_HomeWorld_StylizedBinding_R10O.uasset": "7C6835CA50EBB06B4C94AA6D1E8B0419B1E0ACF09A44D5CEA5B670FBD5865C5A",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\Profiles\DA_PPG_HomeWorld_StylizedForest_R10O.uasset": "4D7B577684CF74CBF56BCB6AF8A6867DAD130C8BACF022CF461D86A53833E18F",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\M_PPG_Generation_SmoothSpawnGrass_R10N.uasset": "43EA98C552B42A28C90C588A588E6B30C9C63ABE02E1E99D744D02E6D65A1FD0",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10L\Materials\M_PPG_Home_PaintedLeafGround_R10L.uasset": "D199781D994392066DBE91F94201A9E9989A73CE7DFCB92D66640FF39FD97AA1",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_PPG_Home_PaintedLeafGround_Scaled_R10N.uasset": "A6ED14A2C495A1F7527F9AA79CA3C317E7E0101E155C4926015CCCE5927E95DB",
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
    getter = getattr(value, "get_path_name", None)
    if not callable(getter):
        return str(value)
    path = getter().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def write_json_exclusive(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted(set(asset_path(value) for value in values))


def provider_gate():
    records = []
    for port in (5353, 8000, 8765):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.25)
        try:
            code = sock.connect_ex(("127.0.0.1", port))
        finally:
            sock.close()
        records.append({"port": port, "closed": code != 0, "connect_ex": code})
    require(all(item["closed"] for item in records), "AI/provider listener active")
    return records


def load(path, class_name=None):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    if class_name:
        require(asset.get_class().get_name() == class_name, "Class mismatch: " + path)
    return asset


def expression_map(material):
    return {node.get_name(): node for node in unreal.MaterialEditingLibrary.get_material_expressions(material)}


def verify_material_controls(generation, mask, surface):
    generation_nodes = expression_map(generation)
    expected_scalars = {
        "MountainDetails": 180.0,
        "MountainsHeight": 0.85,
        "HillsDetails": 320.0,
        "HIllsHeight": 2.25,
    }
    scalar_values = {}
    for node in generation_nodes.values():
        if node.get_class().get_name() != "MaterialExpressionScalarParameter":
            continue
        name = str(node.get_editor_property("parameter_name"))
        if name in expected_scalars:
            scalar_values[name] = float(node.get_editor_property("default_value"))
    require(set(scalar_values) == set(expected_scalars), "Generation scalar signature drift")
    for name, expected in expected_scalars.items():
        require(abs(scalar_values[name] - expected) <= 0.0001, "Generation scalar drift: " + name)

    elevation = generation_nodes.get("MaterialExpressionPlanetElevationOutput_0")
    require(elevation is not None, "Missing generation elevation output")
    warp_strength = float(elevation.get_editor_property("biome_voronoi_warp_strength"))
    warp_scale = float(elevation.get_editor_property("biome_voronoi_warp_scale"))
    require(abs(warp_strength - 0.55) <= 0.0001 and abs(warp_scale - 18.0) <= 0.0001, "Generation warp drift")

    mask_nodes = expression_map(mask)
    output = mask_nodes.get("MaterialExpressionPlanetBiomeMaskOutput_0")
    broad = mask_nodes.get("MaterialExpressionPlanetNoise_3")
    require(output is not None and broad is not None, "Biome-mask graph signature drift")
    require(int(output.get_editor_property("biome_cell_resolution")) == 32, "Biome-cell resolution drift")
    require(int(output.get_editor_property("biome_cell_seed")) == 1234, "Biome-cell seed drift")
    noise_type_text = str(broad.get_editor_property("noise_type"))
    noise_type_key = "".join(character for character in noise_type_text.lower() if character.isalnum())
    require("fbme" in noise_type_key, "Broad noise type drift: " + noise_type_text)
    require(abs(float(broad.get_editor_property("base_frequency")) - 0.75) <= 0.0001, "Broad noise frequency drift")
    require(int(broad.get_editor_property("octaves")) == 3, "Broad noise octaves drift")

    surface_nodes = expression_map(surface)
    expected_textures = {
        "MaterialExpressionTextureSample_3": "/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_BC",
        "MaterialExpressionTextureSample_4": "/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_N",
        "MaterialExpressionTextureObject_0": "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_Painterly_01_BC",
        "MaterialExpressionTextureObject_3": "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_SurfaceDirectional_N",
        "MaterialExpressionTextureSample_10": "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_Painterly_01_BC",
        "MaterialExpressionTextureSample_11": "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_SurfaceDirectional_N",
    }
    actual_textures = {}
    for node_name, expected in expected_textures.items():
        require(node_name in surface_nodes, "Missing surface node: " + node_name)
        actual = asset_path(surface_nodes[node_name].get_editor_property("texture"))
        require(actual == expected, "Surface texture drift on {}: {}".format(node_name, actual))
        actual_textures[node_name] = actual
    return {
        "generation_scalars": scalar_values,
        "warp": {"strength": warp_strength, "scale": warp_scale},
        "biome_cells": {"resolution": 32, "seed": 1234},
        "broad_noise": {"node": broad.get_name(), "base_frequency": 0.75, "octaves": 3},
        "surface_textures": actual_textures,
    }


def verify_planet_identity(planet):
    require(int(planet.get_editor_property("generation_seed")) == 1337, "Seed drift")
    require(abs(float(planet.get_editor_property("planet_radius")) - 300000000.0) <= 0.01, "Radius drift")
    require(abs(float(planet.get_editor_property("noise_height")) - 600000.0) <= 0.01, "Noise height drift")
    require(asset_path(planet.get_editor_property("generation_material")) == TARGET_GENERATION, "Generation binding drift")
    require(asset_path(planet.get_editor_property("biome_mask_material")) == TARGET_MASK, "Biome-mask binding drift")
    require(asset_path(planet.get_editor_property("planet_material")) == TARGET_SURFACE_MI, "Surface binding drift")
    require(bool(planet.get_editor_property("generate_water")), "Native spherical water disabled")
    require(asset_path(planet.get_editor_property("water_material")) == "/PPG/Water/Materials/M_PlanetaryOceanWater", "Native water material drift")


def biome_record(planet):
    records = []
    for biome in list(planet.get_editor_property("biome_data")):
        records.append({
            "name": str(biome.get_editor_property("name")),
            "foliage_data": asset_path(biome.get_editor_property("foliage_data")),
        })
    require([item["name"] for item in records] == ["Craters", "Hills", "Mountains", "Desert", "Ocean", "Poles"], "Biome order drift")
    for item in records[:3]:
        require(item["foliage_data"] == SOURCE_FOLIAGE, "Seeded stylized foliage binding drift in " + item["name"])
    return records


def verify_preconditions():
    active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
    expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
    require(active == expected, "Active project mismatch")
    require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
    require(CHECKPOINT.is_file(), "R15 checkpoint missing")
    require(STAGE_RESULT.is_file(), "Direct MCP stage result missing")
    stage = json.loads(STAGE_RESULT.read_text(encoding="utf-8-sig"))
    require(stage.get("status") == "PASS_DIRECT_MCP_ASSET_STAGE", "Direct MCP asset stage did not pass")
    require(stage.get("home_map_sha256_unchanged") == EXPECTED_HOME, "MCP stage home-map evidence drift")
    require(not RESULT.exists() and not PROFILE.exists(), "R15 finalizer no-clobber output exists")
    if unreal.EditorAssetLibrary.does_asset_exist(TARGET_CELL_MAP):
        retry_cell_file = PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15\DA_PPG_HomeWorld_ContinentBiome_R15_PPG_BiomeCells.uasset"
        require(
            retry_cell_file.is_file()
            and sha256(retry_cell_file) == "C4F2C76CC80F4AF24E2A63CF225C98B2B28418C32C9C87F329978EF00A08FCC1",
            "Unexpected pre-existing R15 biome-cell output",
        )
    require(not dirty_packages(), "Editor dirty before R15 finalizer")
    for path, expected_hash in EXPECTED_STAGE_HASHES.items():
        require(path.is_file() and sha256(path) == expected_hash, "R15 staged asset drift: " + str(path))
    for path, expected_hash in SOURCE_HASHES.items():
        require(path.is_file() and sha256(path) == expected_hash, "R15 source drift: " + str(path))
    for path, expected_hash in PROTECTED.items():
        require(path.is_file() and sha256(path) == expected_hash, "Protected hash drift: " + str(path))
    return stage


def rebuild_pipeline():
    planet = load(TARGET_PLANET, "PlanetData")
    generation = load(TARGET_GENERATION, "Material")
    mask = load(TARGET_MASK, "Material")
    surface = load(TARGET_SURFACE_PARENT, "Material")
    load(TARGET_SURFACE_MI, "MaterialInstanceConstant")
    verify_planet_identity(planet)
    controls = verify_material_controls(generation, mask, surface)
    biomes_before = biome_record(planet)

    rebuild = getattr(planet, "rebuild_planet_pipeline", None)
    require(callable(rebuild), "PPG rebuild_planet_pipeline unavailable")
    rebuild()

    require(unreal.EditorAssetLibrary.does_asset_exist(TARGET_CELL_MAP), "PPG biome-cell output was not created")
    cell_map = load(TARGET_CELL_MAP, "Texture2D")
    require(asset_path(planet.get_editor_property("biome_cell_map")) == TARGET_CELL_MAP, "PlanetData biome-cell map binding drift")
    cell_width = int(cell_map.blueprint_get_size_x())
    cell_height = int(cell_map.blueprint_get_size_y())
    require(cell_width == 192 and cell_height == 32, "Generated biome-cell texture dimensions drift")
    verify_planet_identity(planet)
    biomes_after = biome_record(planet)
    require(biomes_after == biomes_before, "Biome names or foliage bindings changed during pipeline rebuild")

    for asset in (generation, mask, surface, load(TARGET_SURFACE_MI), planet, cell_map):
        require(unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False), "Could not save " + asset_path(asset))
    require(not dirty_packages(), "Dirty packages remain after pipeline rebuild")
    return planet, {
        "controls": controls,
        "biomes": biomes_after,
        "cell_map": TARGET_CELL_MAP,
        "cell_map_dimensions": [cell_width, cell_height],
    }


def bind_home_map(planet):
    world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
    require(world is not None and not dirty_packages(), "Home map load failed or dirtied packages")
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = list(subsystem.get_all_level_actors())
    require(len(actors) == 13, "Home actor count drift before R15 bind: " + str(len(actors)))
    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    require(len(spawners) == 1, "Expected one PlanetSpawnerBP_C")
    spawner = spawners[0]
    require(asset_path(spawner.get_editor_property("planet_data")) == SOURCE_PLANET, "Source PlanetData binding drift")
    require(int(spawner.get_editor_property("max_foliage_instances_per_chunk")) == 100000, "Foliage-cap drift")

    legacy = [actor for actor in actors if actor.get_actor_label() == "RedMMO_StylizedPilot_OasisWater_R06"]
    require(len(legacy) == 1, "Expected one exact legacy R06 water actor")
    legacy_class = legacy[0].get_class().get_name()
    require(subsystem.destroy_actor(legacy[0]), "Could not remove exact legacy R06 water actor")

    spawner.set_editor_property("planet_data", planet)
    regenerate = getattr(spawner, "regenerate_planet", None)
    require(callable(regenerate), "PPG regenerate_planet unavailable")
    regenerate()
    require(asset_path(spawner.get_editor_property("planet_data")) == TARGET_PLANET, "R15 PlanetData did not bind")
    require(set(dirty_packages()).issubset({HOME_MAP}), "Unexpected dirty package before home-map save: " + str(dirty_packages()))
    require(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level(), "Home-map save failed")
    require(not dirty_packages(), "Dirty packages remain after home-map save")

    actors_after = list(subsystem.get_all_level_actors())
    require(len(actors_after) == 12, "Home actor count drift after legacy-water removal")
    require(not any(actor.get_actor_label() == "RedMMO_StylizedPilot_OasisWater_R06" for actor in actors_after), "Legacy water actor persisted")
    return {
        "actor_count_before": len(actors),
        "actor_count_after": len(actors_after),
        "removed_actor": "RedMMO_StylizedPilot_OasisWater_R06",
        "removed_actor_class": legacy_class,
        "spawner_label": spawner.get_actor_label(),
        "spawner_planet_data": asset_path(spawner.get_editor_property("planet_data")),
        "max_foliage_instances_per_chunk": int(spawner.get_editor_property("max_foliage_instances_per_chunk")),
    }


def write_profile(rebuild_record, map_record):
    payload = {
        "schema": "redmmo.ppg_home_continent_biome_profile.r15.v1",
        "revision": "R15_continent_scale_biomes_smoother_relief",
        "source_revision": "R10O",
        "seed": 1337,
        "planet_radius_cm": 300000000.0,
        "generation": {
            "material": TARGET_GENERATION,
            "mountain_details_divisor": 180.0,
            "mountains_height": 0.85,
            "hills_details_divisor": 320.0,
            "hills_height": 2.25,
            "biome_voronoi_warp_strength": 0.55,
            "biome_voronoi_warp_scale": 18.0,
        },
        "macro_biomes": {
            "material": TARGET_MASK,
            "cell_resolution": 32,
            "cell_seed": 1234,
            "broad_noise_frequency": 0.75,
            "broad_noise_octaves": 3,
            "generated_cell_map": TARGET_CELL_MAP,
        },
        "surface": {
            "material_instance": TARGET_SURFACE_MI,
            "desert_base_color": "/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_BC",
            "desert_normal": "/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_N",
            "rock_base_color": "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_Painterly_01_BC",
            "rock_normal": "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_SurfaceDirectional_N",
            "packed_ord_channels_preserved_from_verified_parent": True,
        },
        "foliage": {
            "preserved_seeded_binding": SOURCE_FOLIAGE,
            "preserved_r10o_distribution_and_cap": True,
            "max_instances_per_chunk": map_record["max_foliage_instances_per_chunk"],
        },
        "water": {
            "owner": "PPG native spherical ocean",
            "material": "/PPG/Water/Materials/M_PlanetaryOceanWater",
            "oasis_promoted": False,
            "reason": "The full Oasis water closure is not proven for a spherical PPG body; the rejected rectangular R06 plane was removed.",
        },
        "pipeline": rebuild_record,
        "human_visual_accepted": False,
        "vendor_assets_modified": False,
    }
    write_json_exclusive(PROFILE, payload)
    return payload


_EXIT = {"handle": None}


def schedule_exit(delay=10.0):
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
        "schema": "redmmo.ppg_home_continent_biome.r15.finalizer.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "home_map_sha256_before": EXPECTED_HOME,
        "direct_interface_boundary": {
            "asset_duplication_and_property_edits": "official Epic ModelContextProtocol",
            "ppg_rebuild_and_regenerate": "single guarded Unreal Python finalizer because the MCP toolsets expose no PPG UFUNCTION invocation",
        },
    }
    try:
        report["mcp_stage"] = verify_preconditions()
        report["provider_gate"] = provider_gate()
        planet, report["pipeline"] = rebuild_pipeline()
        report["map"] = bind_home_map(planet)
        report["profile"] = write_profile(report["pipeline"], report["map"])
        report["home_map_sha256_after"] = sha256(HOME_FILE)
        require(report["home_map_sha256_after"] != EXPECTED_HOME, "R15 home-map binding did not serialize")
        report["project_owned_hashes"] = {}
        for asset in TARGETS + [TARGET_CELL_MAP]:
            file_path = PROJECT / ("Content" + asset.removeprefix("/Game").replace("/", os.sep) + ".uasset")
            require(file_path.is_file(), "R15 output file missing: " + asset)
            report["project_owned_hashes"][asset] = sha256(file_path)
        report["profile_sha256"] = sha256(PROFILE)
        for path, expected_hash in SOURCE_HASHES.items():
            require(sha256(path) == expected_hash, "R15 source modified: " + str(path))
        for path, expected_hash in PROTECTED.items():
            require(sha256(path) == expected_hash, "Protected file modified: " + str(path))
        require(not dirty_packages(), "Dirty packages remain at finalizer boundary")
        report["status"] = "PASS_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_GPU"
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        schedule_exit()


main()
