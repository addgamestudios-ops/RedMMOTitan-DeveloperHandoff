"""Read-only R17/R15 PPG surface-material output contract audit.

Run in one fresh RedMMO editor process.  This script authenticates the saved
R17 binding, inventories the exact R15 parent graph reused by R17, proves
whether the native Planet Biome Material Output exists, writes one no-clobber
diagnostic JSON, and exits without saving content, maps, or config.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HOME_SHA256 = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"
R15_PARENT = "/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15/Materials/M_PPG_Home_BiomeSurface_R15"
R15_INSTANCE = "/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15/Materials/MI_PPG_Home_BiomeSurface_R15"
R17_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/SeededBiomeSurface/R17/DA_PPG_HomeWorld_SeededBiomeSurface_R17"
RESULT = Path(os.environ["REDMMO_R17_BIOME_OUTPUT_AUDIT_RESULT"])
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
    path = str(value.get_path_name())
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


report = {
    "schema": "redmmo.r17_biome_output_contract.audit.v1",
    "started_utc": now(),
    "evidence_class": "fresh_editor_read_only",
}

try:
    require(not RESULT.exists() and not RESULT.parent.exists(), "Audit output no-clobber failed")
    active_project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
    require(active_project == PROJECT.resolve(), f"Wrong active project: {active_project}")
    require(PROJECT_FILE.is_file(), "RedMMO project descriptor missing")
    require(HOME_FILE.is_file() and sha256(HOME_FILE) == HOME_SHA256, "R17 home map hash drift")
    require(dirty_packages() == {"content": [], "maps": []}, "Dirty packages before audit")
    gate = provider_gate()
    require(all(gate.values()), f"Provider/MCP listener active: {gate}")

    parent = unreal.load_asset(R15_PARENT)
    instance = unreal.load_asset(R15_INSTANCE)
    planet = unreal.load_asset(R17_PLANET)
    require(parent is not None and parent.get_class().get_name() == "Material", "R15 parent missing")
    require(instance is not None and instance.get_class().get_name() == "MaterialInstanceConstant", "R15 instance missing")
    require(planet is not None and planet.get_class().get_name() == "PlanetData", "R17 PlanetData missing")

    expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(parent))
    class_counts = Counter(expression.get_class().get_name() for expression in expressions)
    biome_outputs = [
        expression for expression in expressions
        if expression.get_class().get_name() == "MaterialExpressionPlanetBiomeMaterialOutput"
    ]
    biome_samples = [
        expression for expression in expressions
        if "Biome" in expression.get_class().get_name() and "Sample" in expression.get_class().get_name()
    ]
    biome_output_records = []
    for output in biome_outputs:
        input_names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(output)]
        input_sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(parent, output))
        require(len(input_names) == len(input_sources), "Biome output input/source cardinality drift")
        biome_output_records.append({
            "name": output.get_name(),
            "biome_count": int(output.get_editor_property("biome_count")),
            "biome_names": [str(value) for value in output.get_editor_property("biome_names")],
            "inputs": [
                {
                    "input": input_name,
                    "connected": source is not None,
                    "source_name": source.get_name() if source is not None else None,
                    "source_class": source.get_class().get_name() if source is not None else None,
                }
                for input_name, source in zip(input_names, input_sources)
            ],
        })
    biome_sample_records = []
    for sample in biome_samples:
        biome_sample_records.append({
            "name": sample.get_name(),
            "class": sample.get_class().get_name(),
            "inputs": [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(sample)],
            "outputs": [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_output_names(sample)],
        })

    report.update({
        "status": "PASS_READ_ONLY_CONTRACT_INVENTORY",
        "completed_utc": now(),
        "home_map_sha256": sha256(HOME_FILE),
        "provider_ports_closed": gate,
        "r17": {
            "planet": R17_PLANET,
            "planet_material": asset_path(planet.get_editor_property("planet_material")),
            "biome_mask_material": asset_path(planet.get_editor_property("biome_mask_material")),
            "generation_material": asset_path(planet.get_editor_property("generation_material")),
            "seed": int(planet.get_editor_property("generation_seed")),
            "biome_count": len(list(planet.get_editor_property("biome_data"))),
        },
        "r15_surface_parent": {
            "asset": R15_PARENT,
            "expression_count": len(expressions),
            "expression_class_counts": dict(sorted(class_counts.items())),
            "planet_biome_material_output_count": len(biome_outputs),
            "planet_biome_material_outputs": biome_output_records,
            "biome_sample_count": len(biome_samples),
            "biome_sample_classes": [value.get_class().get_name() for value in biome_samples],
            "biome_samples": biome_sample_records,
            "uses_material_attributes": bool(parent.get_editor_property("use_material_attributes")),
        },
        "finding": (
            "R17 reuses an R15 conventional surface graph with no native Planet Biome Material Output; "
            "the six PlanetData biome records therefore cannot select distinct material-attribute branches."
            if not biome_outputs else
            "R15 contains the native Planet Biome Material Output; inspect its names and connections next."
        ),
        "dirty_packages_after": dirty_packages(),
        "persistent_writes": False,
    })
    require(report["dirty_packages_after"] == {"content": [], "maps": []}, "Audit dirtied packages")
    require(sha256(HOME_FILE) == HOME_SHA256, "Audit changed home map")
except Exception as error:
    report.update({"status": "FAIL", "completed_utc": now(), "error": str(error)})
finally:
    try:
        atomic_json(RESULT, report)
    finally:
        unreal.SystemLibrary.quit_editor()
