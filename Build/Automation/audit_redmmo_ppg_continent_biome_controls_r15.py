"""Read-only inventory of the clean Red PPG home-world continent and biome controls."""

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
EXPECTED_HOME = os.environ.get(
    "REDMMO_EXPECTED_HOME_SHA256",
    "C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0",
).upper()
RESULT = Path(os.environ.get(
    "REDMMO_BIOME_AUDIT_RESULT",
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiomeControls_R15_20260802\audit_redmmo_ppg_continent_biome_controls_r15_result.json",
))
DIAG = RESULT.parent

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


def provider_gate():
    records = []
    for port in (5353, 8000, 8765):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.25)
        try:
            closed = sock.connect_ex(("127.0.0.1", port)) != 0
        finally:
            sock.close()
        records.append({"port": port, "closed": closed})
    require(all(item["closed"] for item in records), "Provider listener active")
    return records


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted(set(asset_path(item) for item in values))


def safe_property(obj, name):
    try:
        value = obj.get_editor_property(name)
    except Exception:
        return None
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    getter = getattr(value, "get_path_name", None)
    if callable(getter):
        return asset_path(value)
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:
            return str(value)
    return str(value)


def expression_record(node):
    record = {
        "class": node.get_class().get_name(),
        "name": node.get_name(),
    }
    for prop in (
        "desc",
        "parameter_name",
        "default_value",
        "texture",
        "material_function",
        "function_input",
        "const_a",
        "const_b",
        "constant",
        "period",
    ):
        value = safe_property(node, prop)
        if value is not None and value != "":
            record[prop] = value
    for prop in ("material_expression_editor_x", "material_expression_editor_y"):
        value = safe_property(node, prop)
        if value is not None:
            record[prop] = value
    return record


def material_record(material):
    class_name = material.get_class().get_name()
    if class_name != "Material":
        return {
            "asset": asset_path(material),
            "class": class_name,
            "parent": safe_property(material, "parent"),
            "expression_count": None,
            "parameters": [],
            "expressions": [],
            "note": "Material instances have no editable expression graph; parent recorded read-only.",
        }
    expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
    records = [expression_record(node) for node in expressions]
    parameters = [
        item
        for item in records
        if item["class"] in (
            "MaterialExpressionScalarParameter",
            "MaterialExpressionVectorParameter",
            "MaterialExpressionTextureSampleParameter2D",
            "MaterialExpressionStaticBoolParameter",
            "MaterialExpressionCurveAtlasRowParameter",
        )
    ]
    return {
        "asset": asset_path(material),
        "class": class_name,
        "expression_count": len(records),
        "parameters": sorted(parameters, key=lambda item: (str(item.get("parameter_name", "")), item["name"])),
        "expressions": sorted(records, key=lambda item: (int(item.get("material_expression_editor_y", 0)), int(item.get("material_expression_editor_x", 0)), item["name"])),
    }


def load(path):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    return asset


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


_EXIT = {"handle": None}


def schedule_exit(delay=4.0):
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
        "schema": "redmmo.ppg_continent_biome_controls.r15.read_only.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "map": HOME_MAP,
        "evidence_class": "static_runtime_read_only",
        "write_contract": {
            "save_map_or_asset": False,
            "set_editor_property": False,
            "regenerate_planet": False,
            "provider_call": False,
        },
    }
    try:
        require(
            os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
            == os.path.normcase(os.path.abspath(str(PROJECT_FILE))),
            "Active project mismatch",
        )
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
        require(not RESULT.exists(), "Result no-clobber failed")
        report["provider_gate"] = provider_gate()
        report["protected_hashes_before"] = {str(path): sha256(path) for path in PROTECTED}
        require(report["protected_hashes_before"] == {str(path): value for path, value in PROTECTED.items()}, "Protected hash drift")
        require(not dirty_packages(), "Dirty packages before audit")

        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None, "Home map load failed")
        require(not dirty_packages(), "Map load dirtied packages")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "Expected exactly one PlanetSpawnerBP_C")
        spawner = spawners[0]
        planet = spawner.get_editor_property("planet_data")
        require(planet is not None and planet.get_class().get_name() == "PlanetData", "PlanetData missing")

        generation = planet.get_editor_property("generation_material")
        biome_mask = planet.get_editor_property("biome_mask_material")
        surface = planet.get_editor_property("planet_material")
        require(generation is not None and biome_mask is not None and surface is not None, "Planet material binding missing")

        biomes = []
        for index, biome in enumerate(list(planet.get_editor_property("biome_data"))):
            biomes.append({
                "index": index,
                "name": str(biome.get_editor_property("name")),
                "foliage_data": asset_path(biome.get_editor_property("foliage_data")),
                "forest_foliage_data": asset_path(safe_property(biome, "forest_foliage_data")),
            })

        report["home_map_sha256_before"] = sha256(HOME_FILE)
        report["actors"] = {
            "count": len(actors),
            "labels": sorted(actor.get_actor_label() for actor in actors),
            "spawner_label": spawner.get_actor_label(),
        }
        report["spawner"] = {
            prop: safe_property(spawner, prop)
            for prop in (
                "planet_data",
                "chunk_quality",
                "generate_collisions",
                "generate_foliage",
                "global_foliage_density_scale",
                "max_foliage_instances_per_chunk",
                "max_recursion_water_tessellation",
                "far_water_tessellation",
                "generate_water_skirts",
                "water_skirt_length_scale",
            )
        }
        report["planet_data"] = {
            prop: safe_property(planet, prop)
            for prop in (
                "planet_radius",
                "noise_height",
                "generation_seed",
                "min_recursion_level",
                "max_recursion_level",
                "planet_position_scale",
                "generation_material",
                "biome_mask_material",
                "planet_material",
                "biome_cell_resolution",
                "biome_cell_seed",
                "biome_transition",
                "height_blend_biome_materials",
                "biome_material_height_blend_smoothness",
                "biome_voronoi_warp_strength",
                "biome_voronoi_warp_scale",
                "generate_water",
                "water_material",
                "far_water_material",
                "recursion_level_for_material_change",
            )
        }
        report["biomes"] = biomes
        report["materials"] = {
            "generation": material_record(generation),
            "biome_mask": material_record(biome_mask),
            "surface": material_record(surface),
        }
        report["dirty_packages_after"] = dirty_packages()
        require(not report["dirty_packages_after"], "Audit dirtied packages")
        report["home_map_sha256_after"] = sha256(HOME_FILE)
        require(report["home_map_sha256_after"] == EXPECTED_HOME, "Home map changed")
        report["protected_hashes_after"] = {str(path): sha256(path) for path in PROTECTED}
        require(report["protected_hashes_after"] == report["protected_hashes_before"], "Protected hashes changed")
        report["status"] = "PASS_READ_ONLY_CONTROL_INVENTORY"
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        schedule_exit()


main()
