"""Read-only ProfileV1 audit for PPG native shoreline smoothing capability and graph use."""

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
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
GENERATION_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_Generation.uasset"
GENERATION = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_Generation"
PLANET_DATA = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"
EXPECTED_GENERATION = "5CD34E415CADD6B632B2896AE51461B8E7909FCC456027FC5E5CA8CC63EF541A"
PLUGIN = Path(r"D:\UE_5.8\Engine\Plugins\Marketplace\Procedur890d9e860517V2")
HEADER = PLUGIN / r"Source\PPG\Public\MaterialExpressionPlanetFlattenElevation.h"
CPP = PLUGIN / r"Source\PPG\Private\MaterialExpressionPlanetFlattenElevation.cpp"
SHADER = PLUGIN / r"Shaders\NoiseLib.usf"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1ShorelineSmoothing_20260805_0458")
RESULT = DIAG / "audit_redmmo_ppg_profile_v1_shoreline_smoothing_result.json"
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def require(value, message):
    if not value:
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


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write((json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8"))
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
    require(all(item["closed"] for item in records), "Provider/MCP listener active")
    return records


def graph_edges(material, expressions):
    edges = []
    for target in expressions:
        names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(target)]
        sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, target))
        require(len(names) == len(sources), "Input/source cardinality drift: " + target.get_name())
        for input_name, source in zip(names, sources):
            if source is not None:
                edges.append({"source": source.get_name(), "target": target.get_name(), "input": input_name})
    return edges


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
        "schema": "redmmo.ppg_profile_v1.shoreline_smoothing.read_only.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "editor_automation_read_only",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        require(not RESULT.exists(), "Result no-clobber failed")
        require(not dirty_packages(), "Dirty packages before audit")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home hash drift")
        require(GENERATION_FILE.is_file() and sha256(GENERATION_FILE) == EXPECTED_GENERATION, "Generation hash drift")
        report["provider_gate"] = provider_gate()
        for path, expected_hash in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Protected hash drift: " + str(path))

        for path in (HEADER, CPP, SHADER):
            require(path.is_file(), "Installed PPG source missing: " + str(path))
        header_text = HEADER.read_text(encoding="utf-8")
        cpp_text = CPP.read_text(encoding="utf-8")
        shader_text = SHADER.read_text(encoding="utf-8")
        require("float Threshold = 0.005f;" in header_text, "Native threshold default drift")
        require('return TEXT("Smooths elevation near water level.");' in cpp_text, "Native node description drift")
        require("float mask = smoothstep(0.0, threshold, diff);" in shader_text, "Native smoothing formula drift")
        require("return lerp(waterLevel, elevation, mask);" in shader_text, "Native smoothing result drift")

        material = unreal.EditorAssetLibrary.load_asset(GENERATION)
        planet = unreal.EditorAssetLibrary.load_asset(PLANET_DATA)
        require(material is not None and material.get_class().get_name() == "Material", "Generation material missing")
        require(planet is not None, "ProfileV1 PlanetData missing")
        expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
        edges = graph_edges(material, expressions)
        flatten_nodes = [node for node in expressions if node.get_class().get_name() == "MaterialExpressionPlanetFlattenElevation"]
        shoreline_parameters = []
        for node in expressions:
            if node.get_class().get_name() != "MaterialExpressionScalarParameter":
                continue
            name = str(node.get_editor_property("parameter_name"))
            if any(token in name.lower() for token in ("shore", "flatten", "threshold", "waterlevel", "water_level")):
                shoreline_parameters.append({
                    "node": node.get_name(),
                    "parameter": name,
                    "default": float(node.get_editor_property("default_value")),
                    "desc": str(node.get_editor_property("desc")),
                })
        exact = [item for item in shoreline_parameters if item["parameter"] == "ShorelineFlattenThreshold"]
        flatten_edges = [edge for edge in edges if any(
            edge["source"] == node.get_name() or edge["target"] == node.get_name() for node in flatten_nodes
        )]
        require(len(flatten_nodes) == 0, "ProfileV1 unexpectedly contains native flatten nodes; audit contract needs review")
        require(len(exact) == 0, "ProfileV1 unexpectedly contains exact shoreline threshold parameter")

        report.update({
            "status": "PASS_NATIVE_FLATTEN_CAPABILITY_ABSENT_FROM_PROFILE_GRAPH",
            "generation_material": GENERATION,
            "planet_data": PLANET_DATA,
            "generate_native_radial_water": bool(planet.get_editor_property("generate_water")),
            "expression_count": len(expressions),
            "edge_count": len(edges),
            "native_flatten_node_count": len(flatten_nodes),
            "native_flatten_nodes": [node.get_name() for node in flatten_nodes],
            "native_flatten_edges": flatten_edges,
            "shoreline_like_scalar_parameters": shoreline_parameters,
            "exact_shoreline_flatten_threshold_count": len(exact),
            "can_map_existing_connected_threshold": False,
            "installed_native_capability": {
                "class": "MaterialExpressionPlanetFlattenElevation",
                "inputs": ["Elevation", "Water Level", "Threshold"],
                "default_water_level": 0.0,
                "default_threshold": 0.005,
                "formula": "smoothstep distance from water level, then lerp waterLevel to elevation",
                "header_sha256": sha256(HEADER),
                "cpp_sha256": sha256(CPP),
                "shader_sha256": sha256(SHADER),
            },
            "save_called": False,
            "regeneration_called": False,
            "dirty_packages_after": dirty_packages(),
            "home_map_sha256_before_after": EXPECTED_HOME,
            "generation_sha256_before_after": EXPECTED_GENERATION,
            "next_safe_action": (
                "Do not map ShorelineFlattenThreshold to an existing node. Prepare a rollback-backed unbound ProfileV1 graph-extension transaction that adds the native flatten node plus one exact project-owned threshold parameter, without binding or regeneration."
            ),
        })
        require(not report["dirty_packages_after"], "Audit dirtied packages")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map changed")
        require(sha256(GENERATION_FILE) == EXPECTED_GENERATION, "Generation package changed")
        for path, expected_hash in PROTECTED.items():
            require(sha256(path) == expected_hash, "Protected file changed: " + str(path))
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PPG_PROFILE_V1_SHORELINE_SMOOTHING " + report["status"])
        schedule_exit()


main()
