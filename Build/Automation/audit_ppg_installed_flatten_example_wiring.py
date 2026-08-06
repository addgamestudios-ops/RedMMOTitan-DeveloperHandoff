"""Read-only installed PPG material audit for native flatten-elevation example wiring."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
GENERATION_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_Generation.uasset"
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"
EXPECTED_GENERATION = "5CD34E415CADD6B632B2896AE51461B8E7909FCC456027FC5E5CA8CC63EF541A"
EXAMPLE = "/PPG/Example/Assets/M_PPG_ExampleGeneration"
PLUGIN = Path(r"D:\UE_5.8\Engine\Plugins\Marketplace\Procedur890d9e860517V2")
EXAMPLE_FILE = PLUGIN / r"Content\Example\Assets\M_PPG_ExampleGeneration.uasset"
DESCRIPTOR = PLUGIN / "PPG.uplugin"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\PPG_InstalledFlattenExampleWiring_20260805_0508_R02")
RESULT = DIAG / "audit_ppg_installed_flatten_example_wiring_result.json"
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
    inbound = {node.get_name(): [] for node in expressions}
    outbound = {node.get_name(): [] for node in expressions}
    edges = []
    for target in expressions:
        names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(target)]
        sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, target))
        require(len(names) == len(sources), "Input/source cardinality drift: " + target.get_name())
        for input_name, source in zip(names, sources):
            if source is None:
                continue
            edge = {"source": source.get_name(), "target": target.get_name(), "input": input_name}
            edges.append(edge)
            inbound[target.get_name()].append(edge)
            outbound[source.get_name()].append(edge)
    return edges, inbound, outbound


def paths_to_elevation(start, outbound, by_name):
    pending = deque([(start, [start])])
    seen = {start}
    found = []
    while pending:
        current, path = pending.popleft()
        for edge in outbound.get(current, []):
            target = edge["target"]
            if target in seen:
                continue
            next_path = path + [target]
            seen.add(target)
            if by_name[target].get_class().get_name() == "MaterialExpressionPlanetElevationOutput":
                found.append({"target": target, "final_input": edge["input"], "path": next_path})
            pending.append((target, next_path))
    return found


def material_record(material):
    expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
    by_name = {node.get_name(): node for node in expressions}
    edges, inbound, outbound = graph_edges(material, expressions)
    nodes = [node for node in expressions if node.get_class().get_name() == "MaterialExpressionPlanetFlattenElevation"]
    records = []
    for node in nodes:
        input_names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(node)]
        input_edges = {edge["input"]: edge["source"] for edge in inbound[node.get_name()]}
        records.append({
            "node": node.get_name(),
            "desc": str(node.get_editor_property("desc")),
            "water_level_default": float(node.get_editor_property("water_level")),
            "threshold_default": float(node.get_editor_property("threshold")),
            "declared_inputs": input_names,
            "connected_inputs": input_edges,
            "direct_consumers": outbound[node.get_name()],
            "paths_to_elevation_output": paths_to_elevation(node.get_name(), outbound, by_name),
        })
    return {
        "asset": asset_path(material),
        "expression_count": len(expressions),
        "edge_count": len(edges),
        "flatten_nodes": records,
    }


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
        "schema": "redmmo.ppg.installed_flatten_example_wiring.read_only.v1",
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
        require(EXAMPLE_FILE.is_file() and DESCRIPTOR.is_file(), "Installed PPG example or descriptor missing")
        report["provider_gate"] = provider_gate()
        for path, expected_hash in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Protected hash drift: " + str(path))

        paths = list(unreal.EditorAssetLibrary.list_assets("/PPG", recursive=True, include_folder=False))
        material_paths = []
        hits = []
        for path in paths:
            data = unreal.EditorAssetLibrary.find_asset_data(path)
            class_name = str(data.asset_class_path.asset_name) if data.is_valid() else ""
            if class_name != "Material":
                continue
            material_paths.append(path)
            material = unreal.EditorAssetLibrary.load_asset(path)
            require(material is not None, "Material failed to load: " + path)
            record = material_record(material)
            if record["flatten_nodes"]:
                hits.append(record)

        example_material = unreal.EditorAssetLibrary.load_asset(EXAMPLE)
        require(example_material is not None, "Exact PPG example generation material failed to load")
        example = material_record(example_material)
        valid_candidates = []
        for material_record_value in hits:
            for node_value in material_record_value["flatten_nodes"]:
                valid = (
                    node_value["declared_inputs"] == ["Elevation", "Water Level", "Threshold"]
                    and "Elevation" in node_value["connected_inputs"]
                    and any(path["final_input"] == "Global Height" for path in node_value["paths_to_elevation_output"])
                )
                if valid:
                    valid_candidates.append({
                        "material": material_record_value["asset"],
                        "node": node_value,
                    })

        official_candidates = [item for item in valid_candidates if item["material"] == EXAMPLE]
        node = official_candidates[0]["node"] if len(official_candidates) == 1 else None
        if node is not None:
            status = "PASS_OFFICIAL_EXAMPLE_FLATTEN_WIRING_AUTHENTICATED"
            next_action = (
                "Under a fresh rollback, add only the authenticated native flatten wrapper and one exact ShorelineFlattenThreshold scalar to unbound ProfileV1 Global Height, then save/reload that asset without binding or regeneration."
            )
        elif valid_candidates:
            status = "PASS_INSTALLED_NONEXAMPLE_FLATTEN_WIRING_AUTHENTICATED"
            next_action = (
                "Review the exact installed non-example material provenance, then use its source-backed wiring only in a rollback-backed unbound ProfileV1 extension without binding or regeneration."
            )
        else:
            status = "PASS_NO_INSTALLED_FLATTEN_WIRING_EXAMPLE_FOUND"
            next_action = (
                "No installed material demonstrates the node. Use the already authenticated native C++/shader input contract to prepare a rollback-backed unbound ProfileV1 wrapper transaction; do not claim vendor-example provenance."
            )

        report.update({
            "status": status,
            "plugin_descriptor": str(DESCRIPTOR),
            "plugin_descriptor_sha256": sha256(DESCRIPTOR),
            "installed_asset_count": len(paths),
            "installed_material_count": len(material_paths),
            "materials_with_flatten_count": len(hits),
            "materials_with_flatten": hits,
            "official_example": example,
            "official_example_file": str(EXAMPLE_FILE),
            "official_example_sha256": sha256(EXAMPLE_FILE),
            "valid_wiring_candidates": valid_candidates,
            "official_example_candidate_count": len(official_candidates),
            "authenticated_contract": ({
                "node_class": "MaterialExpressionPlanetFlattenElevation",
                "elevation_source": node["connected_inputs"]["Elevation"],
                "water_level_source": node["connected_inputs"].get("Water Level"),
                "threshold_source": node["connected_inputs"].get("Threshold"),
                "water_level_default": node["water_level_default"],
                "threshold_default": node["threshold_default"],
                "output_target": node["direct_consumers"],
                "output_path": node["paths_to_elevation_output"][0],
            } if node is not None else None),
            "save_called": False,
            "regeneration_called": False,
            "dirty_packages_after": dirty_packages(),
            "home_map_sha256_before_after": EXPECTED_HOME,
            "generation_sha256_before_after": EXPECTED_GENERATION,
            "next_safe_action": next_action,
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
        unreal.log("REDMMO_PPG_INSTALLED_FLATTEN_EXAMPLE_WIRING " + report["status"])
        schedule_exit()


main()
