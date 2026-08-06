"""Read-only R17 PPG biome remap and PlayerStart foliage eligibility audit.

Runs in one fresh RedMMO editor, writes one no-clobber diagnostic JSON on D:,
does not save packages/config/maps, and exits.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HOME_SHA256 = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"
R17_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/SeededBiomeSurface/R17/DA_PPG_HomeWorld_SeededBiomeSurface_R17"
R17_FILE = PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\SeededBiomeSurface\R17\DA_PPG_HomeWorld_SeededBiomeSurface_R17.uasset"
R17_SHA256 = "ADFC9D79B509A9998C66229CF67E65C6E560E238141BE30F22C705075C3C6C55"
R15_PARENT = "/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15/Materials/M_PPG_Home_BiomeSurface_R15"
RESULT = Path(os.environ["REDMMO_R17_RUNTIME_BIOME_AUDIT_RESULT"])
PROVIDER_PORTS = (5353, 8000, 8765)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def asset_path(value) -> str | None:
    if value is None:
        return None
    try:
        path = str(value.get_path_name())
    except Exception:
        return str(value)
    return path.split(".", 1)[0]


def dirty_packages() -> dict[str, list[str]]:
    return {
        "content": sorted(str(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()),
        "maps": sorted(str(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()),
    }


def provider_gate() -> dict[str, bool]:
    result: dict[str, bool] = {}
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    return result


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=False)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def struct_value(record, normalized_names: tuple[str, ...]):
    for key, value in record.to_dict().items():
        if str(key).replace("_", "").lower() in normalized_names:
            return value
    return None


def vector(value) -> list[float]:
    return [float(value.x), float(value.y), float(value.z)]


report = {
    "schema": "redmmo.r17_runtime_biome_remap_and_foliage.audit.v1",
    "started_utc": now(),
    "evidence_class": "editor_automation_read_only",
}

try:
    require(not RESULT.exists() and not RESULT.parent.exists(), "Audit output no-clobber failed")
    active_project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
    require(active_project == PROJECT.resolve(), f"Wrong active project: {active_project}")
    require(PROJECT_FILE.is_file(), "RedMMO project descriptor missing")
    require(HOME_FILE.is_file() and sha256(HOME_FILE) == HOME_SHA256, "R17 home map hash drift")
    require(R17_FILE.is_file() and sha256(R17_FILE) == R17_SHA256, "R17 PlanetData hash drift")
    require(dirty_packages() == {"content": [], "maps": []}, "Dirty packages before audit")
    gate = provider_gate()
    require(all(gate.values()), f"Provider/MCP listener active: {gate}")

    planet = unreal.load_asset(R17_PLANET)
    parent = unreal.load_asset(R15_PARENT)
    require(planet is not None and planet.get_class().get_name() == "PlanetData", "R17 PlanetData missing")
    require(parent is not None and parent.get_class().get_name() == "Material", "R15 parent missing")

    biome_records = []
    for index, biome in enumerate(list(planet.get_editor_property("biome_data"))):
        name = struct_value(biome, ("name", "biomename"))
        foliage = struct_value(biome, ("foliagedata", "forestfoliagedata"))
        biome_records.append({
            "planet_biome_index": index,
            "name": str(name),
            "foliage_data": asset_path(foliage),
        })
    planet_names = [item["name"] for item in biome_records]

    outputs = [
        expression for expression in unreal.MaterialEditingLibrary.get_material_expressions(parent)
        if expression.get_class().get_name() == "MaterialExpressionPlanetBiomeMaterialOutput"
    ]
    require(len(outputs) == 1, f"Expected one Planet Biome Material Output, got {len(outputs)}")
    output_names = [str(value) for value in outputs[0].get_editor_property("biome_names")]
    expected_map = [output_names.index(name) if name in output_names else -1 for name in planet_names]
    actual_map = [int(value) for value in planet.get_editor_property("surface_material_biome_entry_map")]

    strength_bindings = []
    for binding in list(planet.get_editor_property("surface_biome_strength_parameter_bindings")):
        record = binding.to_dict()
        strength_bindings.append({str(key): str(value) for key, value in record.items()})

    world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
    require(world is not None and dirty_packages() == {"content": [], "maps": []}, "Fresh map load failed/dirtied packages")
    actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
    require(len(spawners) == 1 and len(starts) == 1, "Expected one PlanetSpawnerBP_C and one PlayerStart")
    spawner = spawners[0]
    start = starts[0].get_actor_location()

    foliage_assets: dict[str, dict] = {}
    for biome in biome_records:
        foliage_path = biome["foliage_data"]
        if not foliage_path or foliage_path in foliage_assets:
            continue
        foliage = unreal.load_asset(foliage_path)
        if foliage is None:
            foliage_assets[foliage_path] = {"loadable": False}
            continue
        entries = []
        for entry_index, entry in enumerate(list(foliage.get_editor_property("foliage_list"))):
            scale = entry.get_editor_property("scale")
            entries.append({
                "entry_index": entry_index,
                "density": float(entry.get_editor_property("foliage_density")),
                "scale": [float(scale.get_editor_property("min")), float(scale.get_editor_property("max"))],
                "max_slope_degrees": int(entry.get_editor_property("max_slope")),
                "density_channel": str(entry.get_editor_property("density_vertex_color_channel")),
                "invert_density_mask": bool(entry.get_editor_property("invert_density_vertex_color_mask")),
                "meshes": [asset_path(item.get_editor_property("mesh")) for item in entry.get_editor_property("meshes")],
            })
        foliage_assets[foliage_path] = {"loadable": True, "entries": entries}

    finding = {
        "surface_remap_matches_output_names": actual_map == expected_map,
        "surface_remap_is_empty": not actual_map,
        "identity_fallback_would_be_wrong": list(range(len(planet_names))) != expected_map,
        "biomes_without_foliage_data": [item["name"] for item in biome_records if not item["foliage_data"]],
    }
    report.update({
        "status": "PASS_READ_ONLY_RUNTIME_CONTRACT_AUDIT",
        "completed_utc": now(),
        "provider_ports_closed": gate,
        "home_map_sha256": sha256(HOME_FILE),
        "r17_planet_sha256": sha256(R17_FILE),
        "planet_biome_names": planet_names,
        "surface_material_output_names": output_names,
        "surface_material_biome_entry_map_actual": actual_map,
        "surface_material_biome_entry_map_expected_by_name": expected_map,
        "surface_biome_strength_parameter_bindings": strength_bindings,
        "biomes": biome_records,
        "foliage_assets": foliage_assets,
        "spawner": {
            "planet_data": asset_path(spawner.get_editor_property("planet_data")),
            "biome_foliage_minimum_blend_strength": float(spawner.get_editor_property("biome_foliage_minimum_blend_strength")),
            "global_foliage_density_scale": float(spawner.get_editor_property("global_foliage_density_scale")),
            "max_foliage_instances_per_chunk": int(spawner.get_editor_property("max_foliage_instances_per_chunk")),
        },
        "player_start": {"location": vector(start), "radial_direction": vector(start.get_safe_normal())},
        "finding": finding,
        "persistent_writes": False,
        "dirty_packages_after": dirty_packages(),
    })
    require(report["dirty_packages_after"] == {"content": [], "maps": []}, "Audit dirtied packages")
    require(sha256(HOME_FILE) == HOME_SHA256 and sha256(R17_FILE) == R17_SHA256, "Audit changed R17 content")
except Exception as error:
    report.update({"status": "FAIL", "completed_utc": now(), "error": str(error)})
finally:
    try:
        atomic_json(RESULT, report)
    finally:
        unreal.SystemLibrary.quit_editor()
