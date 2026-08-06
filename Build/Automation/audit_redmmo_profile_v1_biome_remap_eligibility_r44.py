"""Read-only R44 audit of ProfileV1 biome entry maps and grass eligibility.

Runs in one fresh provider-off D3D12 RedMMO editor, loads the exact saved home
map without PIE or regeneration, writes one no-clobber JSON on D:, saves no
package, and exits.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
PROFILE_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
GENERATION = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_Generation"
GENERATION_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_Generation.uasset"
BIOME_MASK = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_BiomeMask"
BIOME_MASK_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_BiomeMask.uasset"
SURFACE_MI = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/MI_PPG_ProfileV1_Surface"
SURFACE_MI_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\MI_PPG_ProfileV1_Surface.uasset"
SURFACE_PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_SurfaceParent"
SURFACE_PARENT_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_SurfaceParent.uasset"
R29_FOLIAGE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassEligible_R29"
R29_FOLIAGE_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
RESULT = Path(os.environ["REDMMO_R44_RESULT"])

EXPECTED = {
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970",
    GENERATION_FILE: "5165A27F0423735256EEE768739CE9547FEF7849BCA05540AAD63DF5BA1D96E3",
    BIOME_MASK_FILE: "6A4EA303452559810E4FF805FE86AD7057D9807069B3585A8CC9489279BFA66D",
    SURFACE_MI_FILE: "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66",
    SURFACE_PARENT_FILE: "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768",
    R29_FOLIAGE_FILE: "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

APPROVED_GRASS = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value) -> str | None:
    if value is None:
        return None
    path = str(value.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def normalized(value) -> str:
    return str(value).replace("_", "").replace(" ", "").lower()


def struct_value(record, names):
    wanted = {normalized(name) for name in names}
    for key, value in record.to_dict().items():
        if normalized(key) in wanted:
            return value
    return None


def property_or(value, name, default=None):
    try:
        return value.get_editor_property(name)
    except Exception:
        return default


def dirty_packages() -> dict[str, list[str]]:
    return {
        "content": sorted(asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()),
        "maps": sorted(asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()),
    }


def provider_gate() -> dict[str, bool]:
    records = {}
    for port in (11111, 5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            records[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    return records


def atomic_json(path: Path, payload: dict) -> None:
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


def load(path: str, class_name: str):
    value = unreal.EditorAssetLibrary.load_asset(path)
    require(value is not None, "Missing asset: " + path)
    require(value.get_class().get_name() == class_name, "Class mismatch: " + path)
    return value


def first_output(material, class_name: str):
    outputs = [
        expression for expression in unreal.MaterialEditingLibrary.get_material_expressions(material)
        if expression.get_class().get_name() == class_name
    ]
    require(len(outputs) == 1, f"{asset_path(material)} expected one {class_name}, got {len(outputs)}")
    return outputs[0]


def entry_map_record(planet, material, output_class: str, actual, stored_property: str) -> dict:
    output = first_output(material, output_class)
    input_count = int(output.get_editor_property("biome_count"))
    names = [str(value) for value in list(output.get_editor_property("biome_names"))]
    planet_names = [
        str(struct_value(biome, ("name", "biome_name")))
        for biome in list(planet.get_editor_property("biome_data"))
    ]
    require(len(names) >= input_count, f"{output_class} biome_names shorter than biome_count")
    input_names = names[:input_count]
    first_index = {}
    for index, name in enumerate(input_names):
        first_index.setdefault(name, index)
    expected = [first_index.get(name, -1) for name in planet_names]
    actual = [int(value) for value in list(actual)]
    return {
        "material": asset_path(material),
        "output_class": output_class,
        "planet_biome_names": planet_names,
        "input_names": input_names,
        "input_count": input_count,
        "stored_property": stored_property,
        "actual": actual,
        "expected_by_name": expected,
        "matches_by_name": actual == expected,
        "identity_fallback_would_be_wrong": list(range(len(planet_names))) != expected,
        "missing_planet_names": [name for name, index in zip(planet_names, expected) if index < 0],
    }


def foliage_record(path: str) -> dict:
    foliage = load(path, "FoliageData")
    entries = []
    for index, entry in enumerate(list(foliage.get_editor_property("foliage_list"))):
        scale = entry.get_editor_property("scale")
        meshes = [asset_path(item.get_editor_property("mesh")) for item in list(entry.get_editor_property("meshes"))]
        lods = []
        for lod in list(property_or(entry, "lods", [])):
            lods.append({
                "activation_distance": int(lod.get_editor_property("activation_distance")),
                "density_scale": float(lod.get_editor_property("density_scale")),
                "meshes": [asset_path(item) for item in list(property_or(lod, "meshes", []))],
            })
        entries.append({
            "index": index,
            "meshes": meshes,
            "approved_grass_exact": meshes == APPROVED_GRASS,
            "density": float(entry.get_editor_property("foliage_density")),
            "spawn_distance": int(entry.get_editor_property("spawn_distance")),
            "scale": [float(scale.get_editor_property("min")), float(scale.get_editor_property("max"))],
            "density_channel": str(entry.get_editor_property("density_vertex_color_channel")),
            "invert_density_mask": bool(entry.get_editor_property("invert_density_vertex_color_mask")),
            "min_slope": int(entry.get_editor_property("min_slope")),
            "max_slope": int(entry.get_editor_property("max_slope")),
            "lods": lods,
        })
    return {"asset": path, "entries": entries}


report = {
    "schema": "redmmo.profile_v1_biome_remap_eligibility.audit.r44.v1",
    "started_utc": now(),
    "evidence_class": "fresh_editor_d3d12_read_only_automation",
}

try:
    require(not RESULT.exists() and not RESULT.parent.exists(), "R44 output no-clobber failed")
    active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
    require(active == PROJECT_FILE.resolve(strict=True), "Wrong active project")
    command = str(unreal.SystemLibrary.get_command_line()).lower()
    require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "Renderer gate failed")
    require(dirty_packages() == {"content": [], "maps": []}, "Editor started dirty")
    gate = provider_gate()
    require(all(gate.values()), "Provider listener active: " + str(gate))
    for path, expected in EXPECTED.items():
        require(path.is_file() and sha256(path) == expected, "Preflight hash drift: " + str(path))

    planet = load(PROFILE, "PlanetData")
    generation = load(GENERATION, "Material")
    biome_mask = load(BIOME_MASK, "Material")
    surface_mi = load(SURFACE_MI, "MaterialInstanceConstant")
    surface_parent = load(SURFACE_PARENT, "Material")
    require(asset_path(planet.get_editor_property("generation_material")) == GENERATION, "Generation binding drift")
    require(asset_path(planet.get_editor_property("biome_mask_material")) == BIOME_MASK, "Biome-mask binding drift")
    require(asset_path(planet.get_editor_property("planet_material")) == SURFACE_MI, "Surface binding drift")
    require(asset_path(surface_mi.get_editor_property("parent")) == SURFACE_PARENT, "Surface parent drift")

    native_maps = unreal.RedPPGFoliageDiagnostics.inspect_biome_entry_maps(planet)
    require(bool(native_maps.get_editor_property("is_planet_data")), "Native entry-map bridge rejected PlanetData")
    maps = {
        "surface": entry_map_record(planet, surface_parent, "MaterialExpressionPlanetBiomeMaterialOutput", native_maps.get_editor_property("surface_material"), "SurfaceMaterialBiomeEntryMap"),
        "biome_mask": entry_map_record(planet, biome_mask, "MaterialExpressionPlanetBiomeMaskOutput", native_maps.get_editor_property("biome_mask"), "BiomeMaskBiomeEntryMap"),
        "terrain": entry_map_record(planet, generation, "MaterialExpressionPlanetElevationOutput", native_maps.get_editor_property("terrain"), "TerrainBiomeEntryMap"),
        "vertex_color": entry_map_record(planet, generation, "MaterialExpressionPlanetVertexColorOutput", native_maps.get_editor_property("vertex_color"), "VertexColorBiomeEntryMap"),
    }

    biomes = []
    foliage_assets = {}
    for index, biome in enumerate(list(planet.get_editor_property("biome_data"))):
        name = str(struct_value(biome, ("name", "biome_name")))
        foliage_path = asset_path(struct_value(biome, ("foliage_data", "forest_foliage_data")))
        biomes.append({"index": index, "name": name, "foliage_data": foliage_path})
        if foliage_path and foliage_path not in foliage_assets:
            foliage_assets[foliage_path] = foliage_record(foliage_path)

    grass_entries = []
    for foliage in foliage_assets.values():
        for entry in foliage["entries"]:
            if entry["approved_grass_exact"]:
                grass_entries.append({"foliage_asset": foliage["asset"], **entry})

    world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
    require(world is not None, "Home map load failed")
    actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    require(len(spawners) == 1, "Expected one PlanetSpawnerBP_C")
    spawner = spawners[0]
    require(asset_path(spawner.get_editor_property("planet_data")) == PROFILE, "Home spawner ProfileV1 binding drift")

    grass_biomes = [item["name"] for item in biomes if item["foliage_data"] in {entry["foliage_asset"] for entry in grass_entries}]
    grass_contract = bool(grass_entries) and all(
        "none" in entry["density_channel"].lower() and not entry["invert_density_mask"]
        for entry in grass_entries
    )
    findings = {
        "all_entry_maps_match_by_name": all(item["matches_by_name"] for item in maps.values()),
        "entry_map_mismatches": [name for name, item in maps.items() if not item["matches_by_name"]],
        "approved_grass_entry_count": len(grass_entries),
        "approved_grass_eligibility_matches_r29": grass_contract,
        "approved_grass_biomes": grass_biomes,
        "r29_foliage_bound_to_expected_land_biomes": all(name in grass_biomes for name in ("Craters", "Hills", "Mountains")),
    }
    report.update({
        "status": "PASS_READ_ONLY_CONTRACT_AUDIT",
        "completed_utc": now(),
        "provider_ports_closed": gate,
        "profile": PROFILE,
        "biomes": biomes,
        "entry_maps": maps,
        "foliage_assets": foliage_assets,
        "approved_grass_entries": grass_entries,
        "spawner": {
            "planet_data": asset_path(spawner.get_editor_property("planet_data")),
            "biome_foliage_minimum_blend_strength": float(spawner.get_editor_property("biome_foliage_minimum_blend_strength")),
            "global_foliage_density_scale": float(spawner.get_editor_property("global_foliage_density_scale")),
            "max_foliage_instances_per_chunk": int(spawner.get_editor_property("max_foliage_instances_per_chunk")),
        },
        "findings": findings,
        "dirty_packages_after": dirty_packages(),
        "persistent_writes": False,
    })
    require(report["dirty_packages_after"] == {"content": [], "maps": []}, "Audit dirtied packages")
    report["hashes_after"] = {str(path): sha256(path) for path in EXPECTED}
    for path, expected in EXPECTED.items():
        require(report["hashes_after"][str(path)] == expected, "Audit changed file: " + str(path))
except Exception as error:
    report.update({"status": "FAIL", "completed_utc": now(), "error": str(error), "traceback": traceback.format_exc()})
finally:
    try:
        atomic_json(RESULT, report)
    finally:
        unreal.log("REDMMO_R44 " + report["status"])
        unreal.SystemLibrary.quit_editor()
