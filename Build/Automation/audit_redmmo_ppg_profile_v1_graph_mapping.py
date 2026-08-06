"""Read-only exact graph/control mapping audit for clean RedMMO ProfileV1.

The audit loads no map, changes no UObject property, saves no package and
refuses to claim graph-specific profile support unless an exact node/property
or uniquely named parameter exists in the project-owned successor assets.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1GraphMapping_20260805_0355_R02")
RESULT = DIAG / "audit_redmmo_ppg_profile_v1_graph_mapping_result.json"

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
PLANET = ROOT + "/DA_PPG_ProfileV1_PlanetData"
GENERATION = ROOT + "/M_PPG_ProfileV1_Generation"
MASK = ROOT + "/M_PPG_ProfileV1_BiomeMask"
SURFACE = ROOT + "/MI_PPG_ProfileV1_Surface"

EXPECTED_HASHES = {
    PLANET: "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837",
    GENERATION: "7414FB332551219CC51A3EA4B530E10AF0987252C3FFD2EB4FDBB8AF0BC0476E",
    MASK: "8AF61A4497705494BE42A7EAC3332A19FFC1661146145BC9BF2A9E15E7CFB49D",
    SURFACE: "AD32E640D9A2EF73F58360914599AAD782C65B234795623EA67E9DCCD54E49D4",
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
    getter = getattr(value, "get_path_name", None)
    if not callable(getter):
        return str(value)
    path = getter().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def asset_file(path):
    require(path.startswith("/Game/"), "Unexpected project path: " + path)
    return PROJECT / ("Content" + path.removeprefix("/Game").replace("/", os.sep) + ".uasset")


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({asset_path(value) for value in values})


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
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
    require(all(record["closed"] for record in records), "Provider/MCP listener active")
    return records


def load(path, expected_class=None):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    if expected_class:
        require(asset.get_class().get_name() == expected_class, "Class mismatch: " + path)
    return asset


def get_property(obj, name):
    try:
        value = obj.get_editor_property(name)
    except Exception:
        return None
    if hasattr(value, "get_path_name"):
        return asset_path(value)
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def node_record(node):
    record = {
        "name": node.get_name(),
        "class": node.get_class().get_name(),
        "desc": get_property(node, "desc"),
        "x": get_property(node, "material_expression_editor_x"),
        "y": get_property(node, "material_expression_editor_y"),
        "input_names": [str(item) for item in unreal.MaterialEditingLibrary.get_material_expression_input_names(node)],
        "output_names": [str(item) for item in unreal.MaterialEditingLibrary.get_material_expression_output_names(node)],
    }
    class_name = record["class"]
    properties = []
    if class_name == "MaterialExpressionPlanetNoise":
        properties = [
            "noise_type", "base_frequency", "octaves", "ridge_power",
            "erosion_mapping", "erosion_strength", "erosion_scale",
            "erosion_gully_weight", "erosion_detail", "erosion_ridge_rounding",
            "erosion_crease_rounding", "erosion_input_rounding",
            "erosion_octave_rounding", "erosion_onset",
            "erosion_ridge_map_onset", "erosion_ridge_map_octave_onset",
            "erosion_cell_scale", "erosion_normalization", "erosion_lacunarity",
            "erosion_gain", "erosion_assumed_slope", "erosion_assumed_slope_blend",
            "erosion_height_offset", "erosion_height_offset_fade_target_blend",
            "erosion_height_frequency", "erosion_height_amplitude",
            "erosion_height_octaves", "erosion_height_lacunarity", "erosion_height_gain",
        ]
    elif class_name == "MaterialExpressionPlanetElevationOutput":
        properties = [
            "biome_count", "biome_names", "biome_transition",
            "height_blend_biome_materials", "biome_material_height_blend_smoothness",
            "biome_voronoi_warp_strength", "biome_voronoi_warp_scale",
        ]
    elif class_name == "MaterialExpressionPlanetBiomeMaskOutput":
        properties = ["biome_count", "biome_names", "biome_cell_resolution", "biome_cell_seed"]
    elif class_name == "MaterialExpressionPlanetBiomeMaterialOutput":
        properties = ["biome_count", "biome_names"]
    elif class_name in ("MaterialExpressionScalarParameter", "MaterialExpressionVectorParameter"):
        properties = ["parameter_name", "default_value"]
    elif class_name in ("MaterialExpressionTextureSample", "MaterialExpressionTextureObject", "MaterialExpressionTextureSampleParameter2D"):
        properties = ["parameter_name", "texture"]
    elif class_name == "MaterialExpressionMaterialFunctionCall":
        properties = ["material_function"]
    for name in properties:
        value = get_property(node, name)
        if value is not None:
            record[name] = value
    return record


def graph_record(material):
    expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
    records = [node_record(node) for node in expressions]
    return {
        "asset": asset_path(material),
        "class": material.get_class().get_name(),
        "expression_count": len(records),
        "class_counts": dict(sorted(Counter(record["class"] for record in records).items())),
        "expressions": records,
    }


def exact_nodes(graph, class_name):
    return [record for record in graph["expressions"] if record["class"] == class_name]


def exact_parameter(graph, parameter_name):
    matches = [
        record for record in graph["expressions"]
        if record.get("parameter_name") == parameter_name
    ]
    return matches


def mapping(status, target, evidence, reason=None):
    record = {"status": status, "target": target, "evidence": evidence}
    if reason:
        record["reason"] = reason
    return record


_EXIT = {"handle": None}


def schedule_exit(delay=6.0):
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
        "schema": "redmmo.ppg_profile_v1.graph_mapping.read_only.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation_read_only",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        require(not RESULT.exists(), "Result no-clobber failed")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
        require(not dirty_packages(), "Dirty packages before audit")
        report["provider_gate"] = provider_gate()
        for path, expected_hash in EXPECTED_HASHES.items():
            require(asset_file(path).is_file() and sha256(asset_file(path)) == expected_hash, "ProfileV1 hash drift: " + path)
        for path, expected_hash in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Protected hash drift: " + str(path))

        planet = load(PLANET, "PlanetData")
        generation = load(GENERATION, "Material")
        mask = load(MASK, "Material")
        surface = load(SURFACE, "MaterialInstanceConstant")
        parent = surface.get_editor_property("parent")
        require(parent is not None and parent.get_class().get_name() == "Material", "Surface parent material missing")
        surface_parent_path = asset_path(parent)

        generation_graph = graph_record(generation)
        mask_graph = graph_record(mask)
        surface_graph = graph_record(parent)
        elevation_nodes = exact_nodes(generation_graph, "MaterialExpressionPlanetElevationOutput")
        mask_output_nodes = exact_nodes(mask_graph, "MaterialExpressionPlanetBiomeMaskOutput")
        surface_output_nodes = exact_nodes(surface_graph, "MaterialExpressionPlanetBiomeMaterialOutput")
        require(len(elevation_nodes) == 1, "Expected exactly one PlanetElevationOutput")
        require(len(mask_output_nodes) == 1, "Expected exactly one PlanetBiomeMaskOutput")
        require(len(surface_output_nodes) == 1, "Expected exactly one PlanetBiomeMaterialOutput in surface parent")
        for key in (
            "biome_transition", "biome_material_height_blend_smoothness",
            "biome_voronoi_warp_strength", "biome_voronoi_warp_scale",
        ):
            require(elevation_nodes[0].get(key) is not None, "Missing exact elevation-output property: " + key)
        for key in ("biome_cell_resolution", "biome_cell_seed"):
            require(mask_output_nodes[0].get(key) is not None, "Missing exact biome-mask-output property: " + key)

        biome_names = ["Craters", "Hills", "Mountains", "Desert", "Ocean", "Poles"]
        planet_biomes = [str(item.get_editor_property("name")) for item in list(planet.get_editor_property("biome_data"))]
        require(planet_biomes == biome_names, "PlanetData biome order drift")

        mappings = {
            "GenerationSeed": mapping("supported_exact", PLANET + ".generation_seed", {"value": int(planet.get_editor_property("generation_seed"))}),
            "BiomeCellResolution": mapping("supported_exact", MASK + "." + mask_output_nodes[0]["name"] + ".biome_cell_resolution", {"value": mask_output_nodes[0].get("biome_cell_resolution")}),
            "BiomeCellSeed": mapping("supported_exact", MASK + "." + mask_output_nodes[0]["name"] + ".biome_cell_seed", {"value": mask_output_nodes[0].get("biome_cell_seed")}),
            "BiomeTransition": mapping("supported_exact", GENERATION + "." + elevation_nodes[0]["name"] + ".biome_transition", {"value": elevation_nodes[0].get("biome_transition")}),
            "BiomeMaterialHeightBlendSmoothness": mapping("supported_exact", GENERATION + "." + elevation_nodes[0]["name"] + ".biome_material_height_blend_smoothness", {"value": elevation_nodes[0].get("biome_material_height_blend_smoothness")}),
            "BiomeVoronoiWarpStrength": mapping("supported_exact", GENERATION + "." + elevation_nodes[0]["name"] + ".biome_voronoi_warp_strength", {"value": elevation_nodes[0].get("biome_voronoi_warp_strength")}),
            "BiomeVoronoiWarpScale": mapping("supported_exact", GENERATION + "." + elevation_nodes[0]["name"] + ".biome_voronoi_warp_scale", {"value": elevation_nodes[0].get("biome_voronoi_warp_scale")}),
            "GenerateNativeRadialWater": mapping("supported_exact", PLANET + ".generate_water", {"value": bool(planet.get_editor_property("generate_water"))}),
        }

        generation_parameters = {
            record.get("parameter_name"): record
            for record in generation_graph["expressions"]
            if record.get("parameter_name")
        }
        tagged_nodes = {
            str(record.get("desc") or ""): record
            for record in generation_graph["expressions"]
            if str(record.get("desc") or "").startswith("RedProfile.")
        }
        for control in ("ContinentalNoise", "DetailNoise"):
            tag = "RedProfile." + control
            if tag in tagged_nodes and tagged_nodes[tag]["class"] == "MaterialExpressionPlanetNoise":
                mappings[control] = mapping("supported_exact", GENERATION + "." + tagged_nodes[tag]["name"], tagged_nodes[tag])
            else:
                mappings[control] = mapping(
                    "unsupported_ambiguous",
                    None,
                    {"planet_noise_node_count": len(exact_nodes(generation_graph, "MaterialExpressionPlanetNoise")), "required_tag": tag},
                    "The current graph has multiple biome-local noise nodes and no exact RedProfile tag identifying a unique world-scale control.",
                )

        relief_parameter_candidates = {
            "Craters": ["CratersHeight", "CratersOffset"],
            "Hills": ["HIllsHeight", "HillsHeight", "HillsOffset"],
            "Mountains": ["MountainsHeight", "MountainsOffset"],
            "Desert": ["DesertHeight", "DesertOffset"],
            "Ocean": ["OceanHeight", "OceanOffset"],
            "Poles": ["PolesHeight", "PolesOffset"],
        }
        relief = {}
        for biome in biome_names:
            found = [name for name in relief_parameter_candidates[biome] if name in generation_parameters]
            if len(found) >= 2:
                relief[biome] = mapping("supported_exact", [GENERATION + ".parameter." + name for name in found], {"parameters": found})
            else:
                relief[biome] = mapping(
                    "unsupported_incomplete",
                    None,
                    {"found_parameters": found, "required_height_and_bias": relief_parameter_candidates[biome]},
                    "A complete unambiguous HeightScale plus HeightBias pair is not present.",
                )
        mappings["BiomeRelief"] = relief

        role_tags = ["RedProfile.Role." + biome for biome in biome_names]
        present_role_tags = [
            tag for tag in role_tags
            if any(record.get("desc") == tag for record in surface_graph["expressions"])
        ]
        mappings["PresentationRoles"] = mapping(
            "unsupported_unowned_parent_graph",
            None,
            {"surface_instance": SURFACE, "parent": surface_parent_path, "required_tags": role_tags, "present_tags": present_role_tags},
            "ProfileV1 duplicates only the surface instance; its expression graph still lives in an R15 parent outside ProfileV1 and has no exact role tags.",
        )

        shoreline_matches = exact_parameter(generation_graph, "ShorelineFlattenThreshold")
        if len(shoreline_matches) == 1:
            mappings["ShorelineFlattenThreshold"] = mapping("supported_exact", GENERATION + "." + shoreline_matches[0]["name"], shoreline_matches[0])
        else:
            mappings["ShorelineFlattenThreshold"] = mapping(
                "unsupported_absent",
                None,
                {"exact_parameter_match_count": len(shoreline_matches)},
                "No exact ShorelineFlattenThreshold parameter exists in the duplicated generation graph.",
            )

        unsupported = []
        for name, record in mappings.items():
            if name == "BiomeRelief":
                unsupported.extend("BiomeRelief." + biome for biome, entry in record.items() if not entry["status"].startswith("supported"))
            elif not record["status"].startswith("supported"):
                unsupported.append(name)

        report.update({
            "status": "PASS_READ_ONLY_PARTIAL_MAPPING_FAIL_CLOSED",
            "planet": {
                "asset": PLANET,
                "generation_seed": int(planet.get_editor_property("generation_seed")),
                "biomes": planet_biomes,
                "generation_material": asset_path(planet.get_editor_property("generation_material")),
                "biome_mask_material": asset_path(planet.get_editor_property("biome_mask_material")),
                "surface_material": asset_path(planet.get_editor_property("planet_material")),
                "generate_water": bool(planet.get_editor_property("generate_water")),
                "water_material": asset_path(planet.get_editor_property("water_material")),
            },
            "graphs": {
                "generation": generation_graph,
                "biome_mask": mask_graph,
                "surface_instance": {"asset": SURFACE, "class": surface.get_class().get_name(), "parent": surface_parent_path},
                "surface_parent": surface_graph,
            },
            "control_mapping": mappings,
            "unsupported_controls": unsupported,
            "profile_assets_sha256_before_after": EXPECTED_HASHES,
            "home_map_sha256_before_after": EXPECTED_HOME,
            "protected_hashes_before_after": {str(path): expected_hash for path, expected_hash in PROTECTED.items()},
            "home_map_loaded": False,
            "save_called": False,
            "set_editor_property_called": False,
            "dirty_packages_after": dirty_packages(),
            "next_safe_action": "Create a second project-owned ProfileV1 surface-parent material and exact RedProfile node/parameter tags in generation and surface graphs under a new rollback; do not bind or regenerate the home map in that slice.",
        })
        require(not dirty_packages(), "Audit dirtied packages")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map changed during audit")
        for path, expected_hash in EXPECTED_HASHES.items():
            require(sha256(asset_file(path)) == expected_hash, "ProfileV1 asset changed during audit: " + path)
        for path, expected_hash in PROTECTED.items():
            require(sha256(path) == expected_hash, "Protected file changed during audit: " + str(path))
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PPG_PROFILE_V1_GRAPH_MAPPING " + report["status"])
        schedule_exit()


main()
