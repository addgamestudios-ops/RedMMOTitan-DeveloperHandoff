"""Read-only direct-topology audit for unresolved ProfileV1 biome relief controls."""

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
GENERATION = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_Generation"
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"
EXPECTED_GENERATION = "5CD34E415CADD6B632B2896AE51461B8E7909FCC456027FC5E5CA8CC63EF541A"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1ReliefPartners_20260805_0447_R02")
RESULT = DIAG / "audit_redmmo_ppg_profile_v1_relief_partners_result.json"
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
ROLE_INPUTS = {
    "Craters": "Craters Height",
    "Mountains": "Mountains Height",
    "Desert": "Desert Height",
    "Hills": "Hills Height",
    "Ocean": "Ocean Height",
    "Poles": "Poles Height",
}
UNRESOLVED = ("Craters", "Mountains", "Desert", "Hills")


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
    inbound = {node.get_name(): [] for node in expressions}
    outbound = {node.get_name(): [] for node in expressions}
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


def upstream_closure(root, inbound):
    pending = deque([root])
    seen = {root}
    while pending:
        current = pending.popleft()
        for edge in inbound.get(current, []):
            source = edge["source"]
            if source not in seen:
                seen.add(source)
                pending.append(source)
    return seen


def scalar_record(node, outbound):
    return {
        "node": node.get_name(),
        "parameter": str(node.get_editor_property("parameter_name")),
        "default": float(node.get_editor_property("default_value")),
        "desc": str(node.get_editor_property("desc")),
        "direct_consumers": outbound.get(node.get_name(), []),
    }


def constant_record(node, outbound):
    return {
        "node": node.get_name(),
        "value": float(node.get_editor_property("r")),
        "direct_consumers": outbound.get(node.get_name(), []),
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
        "schema": "redmmo.ppg_profile_v1.relief_partners.read_only.v1",
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

        material = unreal.EditorAssetLibrary.load_asset(GENERATION)
        require(material is not None and material.get_class().get_name() == "Material", "Generation material missing")
        expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
        by_name = {node.get_name(): node for node in expressions}
        edges, inbound, outbound = graph_edges(material, expressions)
        outputs = [node for node in expressions if node.get_class().get_name() == "MaterialExpressionPlanetElevationOutput"]
        require(len(outputs) == 1, "Expected one PlanetElevationOutput")
        output = outputs[0]
        require(str(output.get_editor_property("biome_names")) == '["Craters", "Mountains", "Desert", "Ocean", "Hills", "Poles"]', "Biome order drift")

        output_edges = {edge["input"]: edge for edge in inbound[output.get_name()]}
        require(all(name in output_edges for name in ROLE_INPUTS.values()), "One or more biome height inputs are disconnected")
        role_records = {}
        for role, input_name in ROLE_INPUTS.items():
            root = output_edges[input_name]["source"]
            closure = upstream_closure(root, inbound)
            scalars = sorted(
                [scalar_record(by_name[name], outbound) for name in closure
                 if by_name[name].get_class().get_name() == "MaterialExpressionScalarParameter"],
                key=lambda item: item["node"],
            )
            constants = sorted(
                [constant_record(by_name[name], outbound) for name in closure
                 if by_name[name].get_class().get_name() == "MaterialExpressionConstant"],
                key=lambda item: item["node"],
            )
            named_boundaries = sorted(
                name for name in closure
                if "NamedReroute" in by_name[name].get_class().get_name()
            )
            role_records[role] = {
                "output_input": input_name,
                "branch_root": root,
                "branch_root_class": by_name[root].get_class().get_name(),
                "normal_upstream_node_count": len(closure),
                "scalar_parameters": scalars,
                "literal_constants": constants,
                "planet_noise_nodes": sorted(
                    name for name in closure
                    if by_name[name].get_class().get_name() == "MaterialExpressionPlanetNoise"
                ),
                "named_reroute_boundaries": named_boundaries,
            }
            if role in UNRESOLVED:
                found = [item["parameter"] for item in scalars]
                role_local = [name for name in found if role.lower() in name.lower()]
                has_height = any("height" in name.lower() for name in role_local)
                has_bias = any("offset" in name.lower() or "bias" in name.lower() for name in role_local)
                missing = []
                if not has_height:
                    missing.append("HeightScale")
                if not has_bias:
                    missing.append("HeightBias")
                role_records[role]["direct_parameter_contract"] = {
                    "all_parameters_in_closure": found,
                    "role_local_parameters": role_local,
                    "has_role_local_height_parameter": has_height,
                    "has_role_local_bias_parameter": has_bias,
                    "missing_profile_partners": missing,
                }

        report.update({
            "status": "PASS_RELIEF_PARTNER_ABSENCE_MAPPED",
            "generation_material": GENERATION,
            "expression_count": len(expressions),
            "edge_count": len(edges),
            "elevation_output": output.get_name(),
            "biome_names": str(output.get_editor_property("biome_names")),
            "roles": role_records,
            "verified_unresolved_contract": {
                role: role_records[role]["direct_parameter_contract"] for role in UNRESOLVED
            },
            "save_called": False,
            "regeneration_called": False,
            "dirty_packages_after": dirty_packages(),
            "home_map_sha256_before_after": EXPECTED_HOME,
            "generation_sha256_before_after": EXPECTED_GENERATION,
            "next_safe_action": (
                "Keep the four missing relief partners fail-closed. Next audit ShorelineFlattenThreshold against the native shoreline-smoothing connection before any project-owned graph extension."
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
        unreal.log("REDMMO_PPG_PROFILE_V1_RELIEF_PARTNERS " + report["status"])
        schedule_exit()


main()
