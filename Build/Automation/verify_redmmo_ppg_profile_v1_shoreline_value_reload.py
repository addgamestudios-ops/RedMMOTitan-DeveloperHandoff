"""Fresh-process readback of the persisted ProfileV1 shoreline scalar value."""

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
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1ShorelineValue_20260805_0614")
RESULT = DIAG / "verify_redmmo_ppg_profile_v1_shoreline_value_reload_result.json"

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
GENERATION = ROOT + "/M_PPG_ProfileV1_Generation"
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"
EXPECTED_GENERATION = "5165A27F0423735256EEE768739CE9547FEF7849BCA05540AAD63DF5BA1D96E3"
EXPECTED_VALUE = 0.012
EXPECTED_UNCHANGED = {
    ROOT + "/DA_PPG_ProfileV1_PlanetData": "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837",
    ROOT + "/M_PPG_ProfileV1_BiomeMask": "6A4EA303452559810E4FF805FE86AD7057D9807069B3585A8CC9489279BFA66D",
    ROOT + "/M_PPG_ProfileV1_SurfaceParent": "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768",
    ROOT + "/MI_PPG_ProfileV1_Surface": "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
ROLE_SOURCES = [
    ("Craters", "MaterialExpressionAdd_0"),
    ("Mountains", "MaterialExpressionReroute_0"),
    ("Desert", "MaterialExpressionDivide_0"),
    ("Hills", "MaterialExpressionAdd_3"),
    ("Poles", "MaterialExpressionSubtract_3"),
    ("Ocean", "MaterialExpressionSubtract_4"),
]


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


def input_sources(material, node):
    names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(node)]
    sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, node))
    require(len(names) == len(sources), "Input/source cardinality drift: " + node.get_name())
    return dict(zip(names, sources))


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


def write_json_exclusive(path, payload):
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


_EXIT = {"handle": None}


def schedule_exit(delay=7.0):
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
        "schema": "redmmo.ppg_profile_v1.shoreline_value.reload.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "editor_automation_read_only_fresh_reload",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        require(not RESULT.exists(), "Result no-clobber failed")
        world = unreal.EditorLevelLibrary.get_editor_world()
        editor_world = world.get_path_name() if world is not None else ""
        require(editor_world.startswith("/Engine/Maps/Entry.Entry"), "Editor world is not isolated Entry: " + editor_world)
        require(not dirty_packages(), "Dirty packages before verification")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
        require(GENERATION_FILE.is_file() and sha256(GENERATION_FILE) == EXPECTED_GENERATION, "Generation hash drift")
        for path, expected_hash in EXPECTED_UNCHANGED.items():
            require(asset_file(path).is_file() and sha256(asset_file(path)) == expected_hash,
                    "Unchanged ProfileV1 hash drift: " + path)
        for path, expected_hash in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Protected hash drift: " + str(path))
        report["provider_gate"] = provider_gate()

        material = unreal.EditorAssetLibrary.load_asset(GENERATION)
        require(material is not None and material.get_class().get_name() == "Material", "Generation material missing")
        nodes = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
        require(len(nodes) == 129, "Expression count drift")
        outputs = [node for node in nodes if node.get_class().get_name() == "MaterialExpressionPlanetElevationOutput"
                   and str(node.get_editor_property("desc")) == "RedProfile.ElevationOutput"]
        require(len(outputs) == 1, "Expected one tagged elevation output")
        output_inputs = input_sources(material, outputs[0])
        require(output_inputs.get("Global Height") is None, "Global Height must remain unconnected")
        thresholds = [node for node in nodes if node.get_class().get_name() == "MaterialExpressionScalarParameter"
                      and str(node.get_editor_property("parameter_name")) == "ShorelineFlattenThreshold"
                      and str(node.get_editor_property("desc")) == "RedProfile.ShorelineFlattenThreshold"]
        require(len(thresholds) == 1, "Expected one shared shoreline threshold")
        threshold = thresholds[0]
        require(abs(float(threshold.get_editor_property("default_value")) - EXPECTED_VALUE) <= 1e-9,
                "Persisted shoreline value mismatch")
        flatten_nodes = [node for node in nodes if node.get_class().get_name() == "MaterialExpressionPlanetFlattenElevation"]
        require(len(flatten_nodes) == 6, "Expected six native flatten nodes")
        by_desc = {str(node.get_editor_property("desc")): node for node in flatten_nodes}
        require(len(by_desc) == 6, "Flatten identity collision")
        wrappers = []
        for role, source_name in ROLE_SOURCES:
            flatten = by_desc.get("RedProfile.ShorelineFlatten." + role)
            require(flatten is not None, "Missing flatten identity: " + role)
            inputs = input_sources(material, flatten)
            require(inputs.get("Elevation") is not None and inputs["Elevation"].get_name() == source_name,
                    "Elevation source mismatch: " + role)
            require(inputs.get("Water Level") is None, "Water Level must remain unconnected: " + role)
            require(inputs.get("Threshold") == threshold, "Shared Threshold mismatch: " + role)
            require(output_inputs.get(role + " Height") == flatten, "Output wrapper mismatch: " + role)
            require(abs(float(flatten.get_editor_property("water_level"))) <= 1e-9, "Water default drift: " + role)
            require(abs(float(flatten.get_editor_property("threshold")) - 0.005) <= 1e-9,
                    "Native fallback threshold drift: " + role)
            wrappers.append({"role": role, "source": source_name, "node": flatten.get_name()})

        require(not dirty_packages(), "Verification dirtied packages")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map changed during verification")
        require(sha256(GENERATION_FILE) == EXPECTED_GENERATION, "Generation changed during verification")
        report.update({
            "status": "PASS_PROFILE_V1_SHORELINE_VALUE_FRESH_RELOAD_UNBOUND",
            "editor_world": editor_world,
            "generation_sha256_before_after": EXPECTED_GENERATION,
            "expression_count": len(nodes),
            "scalar_parameter": "ShorelineFlattenThreshold",
            "scalar_default": EXPECTED_VALUE,
            "wrapper_count": len(wrappers),
            "wrappers": wrappers,
            "save_called": False,
            "regeneration_called": False,
            "home_map_saved": False,
            "profile_bound_to_home": False,
            "dirty_packages_after": dirty_packages(),
            "next_safe_action": "Keep ProfileV1 unbound; the next separate gate is a fresh guarded binding/regeneration decision with runtime and real-GPU acceptance, not part of this slice.",
        })
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PPG_PROFILE_V1_SHORELINE_VALUE_RELOAD " + report["status"])
        schedule_exit()


main()
