"""Read-only topology audit for ProfileV1 generation PlanetNoise nodes."""

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
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"
GENERATION = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_Generation"
EXPECTED_GENERATION = "5CD34E415CADD6B632B2896AE51461B8E7909FCC456027FC5E5CA8CC63EF541A"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1DetailNoiseTopology_20260805_0437")
RESULT = DIAG / "audit_redmmo_ppg_profile_v1_detail_noise_topology_result.json"
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


def input_edges(material, expressions):
    edges = []
    reverse = {node.get_name(): [] for node in expressions}
    for target in expressions:
        names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(target)]
        sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, target))
        require(len(names) == len(sources), "Input/source cardinality drift: " + target.get_name())
        for input_name, source in zip(names, sources):
            if source is None:
                continue
            edge = {"source": source.get_name(), "target": target.get_name(), "input": input_name}
            edges.append(edge)
            reverse.setdefault(source.get_name(), []).append(edge)
    return edges, reverse


def shortest_paths(start, reverse, by_name, target_classes):
    pending = deque([(start, [start])])
    seen = {start}
    found = []
    while pending:
        current, path = pending.popleft()
        for edge in reverse.get(current, []):
            target = edge["target"]
            if target in seen:
                continue
            next_path = path + [target]
            seen.add(target)
            target_class = by_name[target].get_class().get_name()
            if target_class in target_classes:
                found.append({"target": target, "target_class": target_class, "path": next_path})
            pending.append((target, next_path))
    return found


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
        "schema": "redmmo.ppg_profile_v1.detail_noise_topology.read_only.v1",
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
        generation_file = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_Generation.uasset"
        require(generation_file.is_file() and sha256(generation_file) == EXPECTED_GENERATION, "Generation hash drift")
        report["provider_gate"] = provider_gate()
        for path, expected_hash in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Protected hash drift: " + str(path))

        material = unreal.EditorAssetLibrary.load_asset(GENERATION)
        require(material is not None and material.get_class().get_name() == "Material", "Generation material missing")
        expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
        by_name = {node.get_name(): node for node in expressions}
        edges, reverse = input_edges(material, expressions)
        noises = [node for node in expressions if node.get_class().get_name() == "MaterialExpressionPlanetNoise"]
        require(len(noises) == 9, "Expected exactly nine generation PlanetNoise nodes")
        target_classes = {"MaterialExpressionPlanetElevationOutput", "MaterialExpressionPlanetVertexColorOutput"}

        records = []
        for node in sorted(noises, key=lambda value: value.get_name()):
            direct = reverse.get(node.get_name(), [])
            paths = shortest_paths(node.get_name(), reverse, by_name, target_classes)
            records.append({
                "node": node.get_name(),
                "desc": str(node.get_editor_property("desc")),
                "noise_type": str(node.get_editor_property("noise_type")),
                "base_frequency": float(node.get_editor_property("base_frequency")),
                "octaves": int(node.get_editor_property("octaves")),
                "erosion_strength": float(node.get_editor_property("erosion_strength")),
                "erosion_crease_rounding": float(node.get_editor_property("erosion_crease_rounding")),
                "x": int(node.get_editor_property("material_expression_editor_x")),
                "y": int(node.get_editor_property("material_expression_editor_y")),
                "direct_consumers": direct,
                "output_paths_without_hidden_named_reroutes": paths,
                "reaches_elevation_output": any(item["target_class"] == "MaterialExpressionPlanetElevationOutput" for item in paths),
                "reaches_vertex_color_output": any(item["target_class"] == "MaterialExpressionPlanetVertexColorOutput" for item in paths),
            })

        max_frequency = max(item["base_frequency"] for item in records)
        max_nodes = [item for item in records if item["base_frequency"] == max_frequency]
        exact_candidates = [item for item in max_nodes if item["reaches_elevation_output"]]
        unique = exact_candidates[0] if len(exact_candidates) == 1 else None
        report.update({
            "status": "PASS_UNIQUE_DETAIL_NOISE_TOPOLOGY" if unique else "FAIL_CLOSED_DETAIL_NOISE_NOT_UNIQUE",
            "generation_material": GENERATION,
            "expression_count": len(expressions),
            "edge_count": len(edges),
            "noise_nodes": records,
            "max_frequency": max_frequency,
            "max_frequency_nodes": [item["node"] for item in max_nodes],
            "unique_detail_noise_candidate": unique,
            "selection_contract": {
                "requires_unique_highest_frequency": True,
                "requires_normal_graph_path_to_elevation_output": True,
                "candidate_count": len(exact_candidates),
            },
            "save_called": False,
            "regeneration_called": False,
            "dirty_packages_after": dirty_packages(),
            "home_map_sha256_before_after": EXPECTED_HOME,
            "generation_sha256_before_after": EXPECTED_GENERATION,
            "next_safe_action": (
                "Under fresh rollback, tag only the unique proven node as RedProfile.DetailNoise without changing values or connections; keep ProfileV1 unbound."
                if unique else
                "Keep DetailNoise fail-closed and rotate to another independent control group; do not tag from frequency alone."
            ),
        })
        require(not report["dirty_packages_after"], "Audit dirtied packages")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map changed")
        require(sha256(generation_file) == EXPECTED_GENERATION, "Generation package changed")
        for path, expected_hash in PROTECTED.items():
            require(sha256(path) == expected_hash, "Protected file changed: " + str(path))
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PPG_PROFILE_V1_DETAIL_NOISE_TOPOLOGY " + report["status"])
        schedule_exit()


main()
