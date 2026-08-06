"""Persist one native shoreline-flatten wrapper in the unbound ProfileV1 graph.

This transaction changes only M_PPG_ProfileV1_Generation. It wraps the
existing Global Height source with PPG's native PlanetFlattenElevation node
and exposes one project-owned ShorelineFlattenThreshold scalar. It never loads
or saves the home map, never binds ProfileV1 to the home planet, and never
regenerates PPG.
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
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
GENERATION_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_Generation.uasset"
ROLLBACK_FILE = Path(
    r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1ShorelineFlatten_20260805T0518Z\M_PPG_ProfileV1_Generation.uasset"
)
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1ShorelineFlatten_20260805_0518")
RESULT = DIAG / "apply_redmmo_ppg_profile_v1_shoreline_flatten_result.json"

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
PLANET = ROOT + "/DA_PPG_ProfileV1_PlanetData"
GENERATION = ROOT + "/M_PPG_ProfileV1_Generation"
MASK = ROOT + "/M_PPG_ProfileV1_BiomeMask"
SURFACE_PARENT = ROOT + "/M_PPG_ProfileV1_SurfaceParent"
SURFACE_MI = ROOT + "/MI_PPG_ProfileV1_Surface"

EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"
EXPECTED_GENERATION = "5CD34E415CADD6B632B2896AE51461B8E7909FCC456027FC5E5CA8CC63EF541A"
EXPECTED_UNCHANGED = {
    PLANET: "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837",
    MASK: "6A4EA303452559810E4FF805FE86AD7057D9807069B3585A8CC9489279BFA66D",
    SURFACE_PARENT: "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768",
    SURFACE_MI: "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66",
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
    path = value.get_path_name().split(":", 1)[0]
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


def input_sources(material, node):
    names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(node)]
    sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, node))
    require(len(names) == len(sources), "Input/source cardinality drift: " + node.get_name())
    return dict(zip(names, sources))


def graph_edges(material):
    edges = []
    for target in unreal.MaterialEditingLibrary.get_material_expressions(material):
        for input_name, source in input_sources(material, target).items():
            if source is not None:
                edges.append({"source": source.get_name(), "target": target.get_name(), "input": input_name})
    return edges


def expression_nodes(material):
    return list(unreal.MaterialEditingLibrary.get_material_expressions(material))


def unchanged_hashes_ok():
    require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
    for path, expected_hash in EXPECTED_UNCHANGED.items():
        file_path = asset_file(path)
        require(file_path.is_file() and sha256(file_path) == expected_hash, "Unchanged ProfileV1 hash drift: " + path)
    for path, expected_hash in PROTECTED.items():
        require(path.is_file() and sha256(path) == expected_hash, "Protected hash drift: " + str(path))


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
        "schema": "redmmo.ppg_profile_v1.shoreline_flatten.build.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "editor_automation_persisted_unbound_asset_no_map_change",
    }
    save_called = False
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        require(not RESULT.exists(), "Result no-clobber failed")
        require(not dirty_packages(), "Dirty packages before shoreline transaction")
        require(GENERATION_FILE.is_file() and sha256(GENERATION_FILE) == EXPECTED_GENERATION, "Generation preimage hash drift")
        require(ROLLBACK_FILE.is_file() and sha256(ROLLBACK_FILE) == EXPECTED_GENERATION, "Rollback preimage missing or mismatched")
        unchanged_hashes_ok()
        report["provider_gate"] = provider_gate()

        material = unreal.EditorAssetLibrary.load_asset(GENERATION)
        require(material is not None and material.get_class().get_name() == "Material", "Generation material missing")
        nodes_before = expression_nodes(material)
        flatten_before = [node for node in nodes_before if node.get_class().get_name() == "MaterialExpressionPlanetFlattenElevation"]
        threshold_before = [
            node for node in nodes_before
            if node.get_class().get_name() == "MaterialExpressionScalarParameter"
            and str(node.get_editor_property("parameter_name")) == "ShorelineFlattenThreshold"
        ]
        require(not flatten_before, "Native flatten node already exists")
        require(not threshold_before, "ShorelineFlattenThreshold already exists")

        outputs = [
            node for node in nodes_before
            if node.get_class().get_name() == "MaterialExpressionPlanetElevationOutput"
            and str(node.get_editor_property("desc")) == "RedProfile.ElevationOutput"
        ]
        require(len(outputs) == 1, "Expected one tagged elevation output")
        output = outputs[0]
        output_inputs_before = input_sources(material, output)
        require("Global Height" in output_inputs_before, "Global Height input missing")
        prior_global_source = output_inputs_before["Global Height"]
        require(prior_global_source is not None, "Global Height is unconnected")

        flatten = unreal.MaterialEditingLibrary.create_material_expression(
            material, unreal.MaterialExpressionPlanetFlattenElevation, 80, -760
        )
        threshold = unreal.MaterialEditingLibrary.create_material_expression(
            material, unreal.MaterialExpressionScalarParameter, -240, -620
        )
        require(flatten is not None and threshold is not None, "Expression creation failed")
        flatten.set_editor_property("water_level", 0.0)
        flatten.set_editor_property("threshold", 0.005)
        flatten.set_editor_property("desc", "RedProfile.ShorelineFlatten")
        threshold.set_editor_property("parameter_name", unreal.Name("ShorelineFlattenThreshold"))
        threshold.set_editor_property("default_value", 0.005)
        threshold.set_editor_property("desc", "RedProfile.ShorelineFlattenThreshold")

        require(
            unreal.MaterialEditingLibrary.disconnect_material_expressions(output, "Global Height"),
            "Could not disconnect prior Global Height source",
        )
        require(
            unreal.MaterialEditingLibrary.connect_material_expressions(prior_global_source, "", flatten, "Elevation"),
            "Could not connect prior Global Height source to flatten Elevation",
        )
        require(
            unreal.MaterialEditingLibrary.connect_material_expressions(threshold, "", flatten, "Threshold"),
            "Could not connect shoreline scalar to flatten Threshold",
        )
        require(
            unreal.MaterialEditingLibrary.connect_material_expressions(flatten, "", output, "Global Height"),
            "Could not connect flatten output to Global Height",
        )

        flatten_inputs = input_sources(material, flatten)
        output_inputs_after = input_sources(material, output)
        require(flatten_inputs.get("Elevation") == prior_global_source, "Flatten Elevation source mismatch")
        require(flatten_inputs.get("Water Level") is None, "Water Level must remain unconnected")
        require(flatten_inputs.get("Threshold") == threshold, "Flatten Threshold source mismatch")
        require(output_inputs_after.get("Global Height") == flatten, "Global Height wrapper mismatch")
        require(abs(float(flatten.get_editor_property("water_level"))) <= 1e-9, "Water Level default drift")
        require(abs(float(flatten.get_editor_property("threshold")) - 0.005) <= 1e-9, "Flatten threshold default drift")
        require(abs(float(threshold.get_editor_property("default_value")) - 0.005) <= 1e-9, "Scalar default drift")

        edges = graph_edges(material)
        prior_to_flatten = [edge for edge in edges if edge["source"] == prior_global_source.get_name() and edge["target"] == flatten.get_name() and edge["input"] == "Elevation"]
        threshold_to_flatten = [edge for edge in edges if edge["source"] == threshold.get_name() and edge["target"] == flatten.get_name() and edge["input"] == "Threshold"]
        flatten_to_output = [edge for edge in edges if edge["source"] == flatten.get_name() and edge["target"] == output.get_name() and edge["input"] == "Global Height"]
        require(len(prior_to_flatten) == len(threshold_to_flatten) == len(flatten_to_output) == 1, "Exact shoreline edge contract failed")

        unreal.MaterialEditingLibrary.recompile_material(material)
        save_called = True
        require(unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False), "Generation material save failed")
        require(not dirty_packages(), "Dirty packages remain after shoreline save")
        new_hash = sha256(GENERATION_FILE)
        require(new_hash != EXPECTED_GENERATION, "Generation hash did not change")
        unchanged_hashes_ok()

        report.update({
            "status": "PASS_PROFILE_V1_NATIVE_SHORELINE_FLATTEN_PERSISTED_UNBOUND",
            "modified_packages": [GENERATION],
            "unchanged_packages": [PLANET, MASK, SURFACE_PARENT, SURFACE_MI],
            "generation_sha256_before": EXPECTED_GENERATION,
            "generation_sha256_after": new_hash,
            "rollback_file": str(ROLLBACK_FILE),
            "rollback_sha256": sha256(ROLLBACK_FILE),
            "expression_count_before": len(nodes_before),
            "expression_count_after": len(expression_nodes(material)),
            "prior_global_height_source": prior_global_source.get_name(),
            "flatten_node": flatten.get_name(),
            "threshold_node": threshold.get_name(),
            "threshold_parameter": "ShorelineFlattenThreshold",
            "threshold_default": 0.005,
            "water_level_default": 0.0,
            "edges": prior_to_flatten + threshold_to_flatten + flatten_to_output,
            "save_called": save_called,
            "regeneration_called": False,
            "home_map_loaded": False,
            "home_map_saved": False,
            "profile_bound_to_home": False,
            "dirty_packages_after": dirty_packages(),
            "next_safe_action": "Fresh-process reload only ProfileV1 packages and verify exact shoreline node, scalar, defaults, wiring and hashes; do not bind or regenerate the home map.",
        })
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["save_called"] = save_called
        report["rollback_required"] = save_called or (
            GENERATION_FILE.is_file() and sha256(GENERATION_FILE) != EXPECTED_GENERATION
        )
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PPG_PROFILE_V1_SHORELINE_FLATTEN " + report["status"])
        schedule_exit()


main()
