"""Read-only R10O versus ProfileV1 PPG foliage eligibility comparison.

This runs on /Engine/Maps/Entry in one fresh provider-off RedMMO editor.  It
loads only project-owned data/material assets, inventories the exact foliage
dispatch inputs and the full graph ancestry feeding Planet Vertex Color Output,
then exits without loading/saving the home map or regenerating the planet.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import traceback
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
RESULT = Path(os.environ["REDMMO_PROFILE_V1_FOLIAGE_ELIGIBILITY_RESULT"])

R10O_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/DA_PPG_HomeWorld_StylizedBinding_R10O"
R10N_GENERATION = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/M_PPG_Generation_SmoothSpawnGrass_R10N"
R10O_FOLIAGE = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/Profiles/DA_PPG_HomeWorld_StylizedForest_R10O"
R16_GENERATION = "/Game/RedMMO/World/PPG/HomeWorld/SmoothTerrain/R16/Materials/M_PPG_Generation_SmoothRolling_R16"
R17_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/SeededBiomeSurface/R17/DA_PPG_HomeWorld_SeededBiomeSurface_R17"
PROFILE_PLANET = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
PROFILE_GENERATION = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_Generation"

EXPECTED = {
    HOME_FILE: "83C78D0ACB599F01E8D3834FB62D58D6B6AA75466F6549F03BFEC4DF908E3336",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\DA_PPG_HomeWorld_StylizedBinding_R10O.uasset":
        "7C6835CA50EBB06B4C94AA6D1E8B0419B1E0ACF09A44D5CEA5B670FBD5865C5A",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\Profiles\DA_PPG_HomeWorld_StylizedForest_R10O.uasset":
        "4D7B577684CF74CBF56BCB6AF8A6867DAD130C8BACF022CF461D86A53833E18F",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\M_PPG_Generation_SmoothSpawnGrass_R10N.uasset":
        "43EA98C552B42A28C90C588A588E6B30C9C63ABE02E1E99D744D02E6D65A1FD0",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\SmoothTerrain\R16\Materials\M_PPG_Generation_SmoothRolling_R16.uasset":
        "95756266D3BF470D1B0907257B0CA978F8755129EE2A03C88082675FD244D92E",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\SeededBiomeSurface\R17\DA_PPG_HomeWorld_SeededBiomeSurface_R17.uasset":
        "ADFC9D79B509A9998C66229CF67E65C6E560E238141BE30F22C705075C3C6C55",
    PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset":
        "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837",
    PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_Generation.uasset":
        "5165A27F0423735256EEE768739CE9547FEF7849BCA05540AAD63DF5BA1D96E3",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value):
    if value is None:
        return None
    path = str(value.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def dirty_packages():
    content = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    maps = list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({asset_path(value) for value in content + maps})


def provider_gate():
    records = []
    for port in (5353, 8000, 8765, 11111):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            code = probe.connect_ex(("127.0.0.1", port))
        finally:
            probe.close()
        records.append({"port": port, "closed": code != 0, "connect_ex": code})
    require(all(item["closed"] for item in records), "Provider/MCP listener active")
    return records


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=False)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, default=str)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(path, class_name):
    value = unreal.EditorAssetLibrary.load_asset(path)
    require(value is not None, "Missing asset: " + path)
    require(value.get_class().get_name() == class_name, "Class mismatch: " + path)
    return value


def normalized_key(value):
    return str(value).replace("_", "").lower()


def struct_value(record, names):
    wanted = {normalized_key(value) for value in names}
    for key, value in record.to_dict().items():
        if normalized_key(key) in wanted:
            return value
    return None


def editor_property_or(value, name, default=None):
    try:
        return value.get_editor_property(name)
    except Exception:
        return default


def node_record(node):
    result = {
        "name": node.get_name(),
        "class": node.get_class().get_name(),
        "desc": str(editor_property_or(node, "desc", "")),
    }
    if node.get_class().get_name() == "MaterialExpressionScalarParameter":
        result["parameter_name"] = str(node.get_editor_property("parameter_name"))
        result["default_value"] = float(node.get_editor_property("default_value"))
    return result


def graph(material_path):
    material = load(material_path, "Material")
    expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
    by_name = {node.get_name(): node for node in expressions}
    incoming = {}
    all_edges = []
    for target in expressions:
        names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(target)]
        sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, target))
        require(len(names) == len(sources), "Input/source cardinality drift: " + target.get_name())
        for input_name, source in zip(names, sources):
            if source is None:
                continue
            edge = {"source": source.get_name(), "target": target.get_name(), "input": input_name}
            all_edges.append(edge)
            incoming.setdefault(target.get_name(), []).append(edge)

    outputs = [node for node in expressions if node.get_class().get_name() == "MaterialExpressionPlanetVertexColorOutput"]
    require(len(outputs) == 1, material_path + " must have one vertex-color output")
    output = outputs[0]
    pending = deque([output.get_name()])
    ancestry = {output.get_name()}
    ancestry_edges = []
    while pending:
        target = pending.popleft()
        for edge in incoming.get(target, []):
            ancestry_edges.append(edge)
            if edge["source"] not in ancestry:
                ancestry.add(edge["source"])
                pending.append(edge["source"])

    def stable_node_key(name):
        node = by_name[name]
        return (
            node.get_class().get_name(),
            str(editor_property_or(node, "desc", "")),
            str(node.get_editor_property("parameter_name")) if node.get_class().get_name() == "MaterialExpressionScalarParameter" else "",
            name,
        )

    ancestry_nodes = [node_record(by_name[name]) for name in sorted(ancestry, key=stable_node_key)]
    vertex_input_names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(output)]
    vertex_input_sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, output))
    grass_signature_nodes = [
        node_record(node) for node in expressions
        if "R05" in str(editor_property_or(node, "desc", ""))
        and any(token in str(editor_property_or(node, "desc", "")).lower() for token in ("grass", "density", "outside", "original g"))
    ]
    return {
        "asset": material_path,
        "expression_count": len(expressions),
        "expression_class_counts": dict(sorted(Counter(node.get_class().get_name() for node in expressions).items())),
        "vertex_output": {
            "name": output.get_name(),
            "biome_count": int(output.get_editor_property("biome_count")),
            "biome_names": [str(value) for value in output.get_editor_property("biome_names")],
            "inputs": [
                {
                    "input": input_name,
                    "source": source.get_name() if source else None,
                    "source_class": source.get_class().get_name() if source else None,
                    "source_desc": str(editor_property_or(source, "desc", "")) if source else "",
                }
                for input_name, source in zip(vertex_input_names, vertex_input_sources)
            ],
        },
        "vertex_ancestry_nodes": ancestry_nodes,
        "vertex_ancestry_edges": sorted(ancestry_edges, key=lambda item: (item["target"], item["input"], item["source"])),
        "r05_grass_density_signature_nodes": sorted(grass_signature_nodes, key=lambda item: item["name"]),
    }


def foliage_record(path):
    foliage = load(path, "FoliageData")
    entries = []
    for index, item in enumerate(list(foliage.get_editor_property("foliage_list"))):
        scale = item.get_editor_property("scale")
        lods = []
        for lod in list(item.get_editor_property("lods")):
            lod_meshes = editor_property_or(lod, "meshes", [])
            lods.append({
                "activation_distance": int(lod.get_editor_property("activation_distance")),
                "density_scale": float(lod.get_editor_property("density_scale")),
                "legacy_mesh": asset_path(editor_property_or(lod, "mesh")),
                "meshes": [asset_path(mesh) for mesh in list(lod_meshes)],
            })
        entries.append({
            "index": index,
            "density": float(item.get_editor_property("foliage_density")),
            "scalable_density": bool(item.get_editor_property("scalable_density")),
            "spawn_distance": int(item.get_editor_property("spawn_distance")),
            "min_slope": int(item.get_editor_property("min_slope")),
            "max_slope": int(item.get_editor_property("max_slope")),
            "scale": [float(scale.get_editor_property("min")), float(scale.get_editor_property("max"))],
            "density_channel": str(item.get_editor_property("density_vertex_color_channel")),
            "invert_density_mask": bool(item.get_editor_property("invert_density_vertex_color_mask")),
            "legacy_mesh": asset_path(editor_property_or(item, "foliage_mesh")),
            "meshes": [asset_path(value.get_editor_property("mesh")) for value in list(item.get_editor_property("meshes"))],
            "lods": lods,
        })
    return {"asset": path, "entries": entries}


def planet_record(path):
    planet = load(path, "PlanetData")
    biomes = []
    for index, biome in enumerate(list(planet.get_editor_property("biome_data"))):
        biomes.append({
            "index": index,
            "name": str(struct_value(biome, ("name", "biome_name"))),
            "foliage_data": asset_path(struct_value(biome, ("foliage_data", "forest_foliage_data"))),
        })
    vertex_map = editor_property_or(planet, "vertex_color_biome_entry_map")
    terrain_map = editor_property_or(planet, "terrain_biome_entry_map")
    return {
        "asset": path,
        "generation_material": asset_path(planet.get_editor_property("generation_material")),
        "biome_mask_material": asset_path(planet.get_editor_property("biome_mask_material")),
        "planet_material": asset_path(planet.get_editor_property("planet_material")),
        "seed": int(planet.get_editor_property("generation_seed")),
        "max_recursion_level": int(planet.get_editor_property("max_recursion_level")),
        "vertex_color_biome_entry_map": [int(value) for value in list(vertex_map)] if vertex_map is not None else None,
        "terrain_biome_entry_map": [int(value) for value in list(terrain_map)] if terrain_map is not None else None,
        "entry_maps_python_exposed": vertex_map is not None and terrain_map is not None,
        "biomes": biomes,
    }


report = {
    "schema": "redmmo.profile_v1_foliage_eligibility.audit.v1",
    "started_utc": now(),
    "evidence_class": "fresh_editor_read_only_plus_installed_source_contract",
}

try:
    require(not RESULT.exists() and not RESULT.parent.exists(), "Result no-clobber failed")
    active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
    require(active == PROJECT.resolve(), "Wrong active project: " + str(active))
    world = unreal.EditorLevelLibrary.get_editor_world()
    require(world is not None and world.get_path_name().startswith("/Engine/Maps/Entry.Entry"), "Not isolated Entry map")
    require(not dirty_packages(), "Dirty packages before audit")
    gate = provider_gate()
    for path, expected_hash in {**EXPECTED, **PROTECTED}.items():
        require(path.is_file() and sha256(path) == expected_hash, "Hash drift: " + str(path))

    r10n_graph = graph(R10N_GENERATION)
    r16_graph = graph(R16_GENERATION)
    profile_graph = graph(PROFILE_GENERATION)
    r10o_planet = planet_record(R10O_PLANET)
    r17_planet = planet_record(R17_PLANET)
    profile_planet = planet_record(PROFILE_PLANET)
    foliage = foliage_record(R10O_FOLIAGE)

    r10n_vertex_inputs = r10n_graph["vertex_output"]["inputs"]
    r16_vertex_inputs = r16_graph["vertex_output"]["inputs"]
    profile_vertex_inputs = profile_graph["vertex_output"]["inputs"]
    r16_profile_vertex_equal = (
        r16_graph["vertex_output"] == profile_graph["vertex_output"]
        and r16_graph["vertex_ancestry_nodes"] == profile_graph["vertex_ancestry_nodes"]
        and r16_graph["vertex_ancestry_edges"] == profile_graph["vertex_ancestry_edges"]
    )
    r10n_r16_vertex_equal = (
        r10n_graph["vertex_output"] == r16_graph["vertex_output"]
        and r10n_graph["vertex_ancestry_nodes"] == r16_graph["vertex_ancestry_nodes"]
        and r10n_graph["vertex_ancestry_edges"] == r16_graph["vertex_ancestry_edges"]
    )
    profile_foliage_biomes = [item["name"] for item in profile_planet["biomes"] if item["foliage_data"]]
    profile_nonfoliage_biomes = [item["name"] for item in profile_planet["biomes"] if not item["foliage_data"]]

    report.update({
        "status": "PASS_READ_ONLY_ELIGIBILITY_CONTRACT_IDENTIFIED",
        "completed_utc": now(),
        "provider_gate": gate,
        "graphs": {"r10n_working": r10n_graph, "r16_successor": r16_graph, "profile_v1": profile_graph},
        "planets": {"r10o_working": r10o_planet, "r17_source": r17_planet, "profile_v1": profile_planet},
        "foliage": foliage,
        "comparison": {
            "r16_profile_vertex_contract_exactly_equal": r16_profile_vertex_equal,
            "r10n_r16_vertex_contract_exactly_equal": r10n_r16_vertex_equal,
            "r10n_vertex_inputs": r10n_vertex_inputs,
            "r16_vertex_inputs": r16_vertex_inputs,
            "profile_vertex_inputs": profile_vertex_inputs,
            "profile_biomes_with_foliage": profile_foliage_biomes,
            "profile_biomes_without_foliage": profile_nonfoliage_biomes,
            "all_profile_biomes_have_foliage": not profile_nonfoliage_biomes,
            "r10o_profile_biome_mask_equal": r10o_planet["biome_mask_material"] == profile_planet["biome_mask_material"],
            "r10o_biome_mask_material": r10o_planet["biome_mask_material"],
            "profile_biome_mask_material": profile_planet["biome_mask_material"],
            "source_code_dispatch_fact": (
                "BuildFoliageDispatchParams creates configurations for each unique non-null biome FoliageData, "
                "but the GPU shader multiplies each configuration by only the local biome strengths whose "
                "FoliageSources entry matches that source; null-biome regions therefore yield no instances."
            ),
        },
        "finding": (
            "ProfileV1 retains null foliage bindings for some seeded biomes. Since the fresh runtime created zero "
            "GPU foliage components at the relocated PlayerStart while the working R10O single-profile setup did, "
            "the source-backed leading cause is local classification into a null-foliage biome, not spawn altitude. "
            "The graph comparison below determines separately whether the working BLUE density-mask contract drifted."
        ),
        "save_called": False,
        "regeneration_called": False,
        "home_map_loaded": False,
        "dirty_packages_after": dirty_packages(),
        "hashes_after": {str(path): sha256(path) for path in {**EXPECTED, **PROTECTED}},
        "next_safe_action": (
            "Instrument one exact runtime PlayerStart biome-strength/vertex-color sample without moving spawn or changing assets. "
            "If it proves a null-foliage biome, repair only the ProfileV1 biome-to-foliage assignment policy under rollback; "
            "if it proves a foliage biome, instrument the density-mask value before mutation."
        ),
    })
    require(not report["dirty_packages_after"], "Audit dirtied packages")
    for path, expected_hash in {**EXPECTED, **PROTECTED}.items():
        require(report["hashes_after"][str(path)] == expected_hash, "Audit changed file: " + str(path))
except Exception as error:
    report.update({
        "status": "FAIL",
        "completed_utc": now(),
        "error": str(error),
        "traceback": traceback.format_exc(),
    })
finally:
    atomic_json(RESULT, report)
    unreal.log("REDMMO_PROFILE_V1_FOLIAGE_ELIGIBILITY " + report["status"])
    unreal.SystemLibrary.quit_editor()
