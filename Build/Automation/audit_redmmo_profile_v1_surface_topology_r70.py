"""Complete read-only ProfileV1 surface topology through compiled reroute data."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import traceback
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_SurfaceTopologyBridge_R70_20260805T2241Z\Audit")
RESULT = DIAG / os.environ.get("REDMMO_R70_RESULT_NAME", "result.json")

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
PLANET = ROOT + "/DA_PPG_ProfileV1_PlanetData"
SURFACE_MI = ROOT + "/Materials/MI_PPG_ProfileV1_PaintedLeaves_R67"
SURFACE_PARENT = ROOT + "/M_PPG_ProfileV1_SurfaceParent"
GENERATION = ROOT + "/M_PPG_ProfileV1_Generation"
MASK = ROOT + "/M_PPG_ProfileV1_BiomeMask"
NO_PALMS = ROOT + "/Profiles/DA_PPG_ProfileV1_NoPalms_R66"

EXPECTED_HASHES = {
    PLANET: "56EA5F830A8F581C1844B956EBABA556B45E200C397443F37BA921766862FC1A",
    GENERATION: "5165A27F0423735256EEE768739CE9547FEF7849BCA05540AAD63DF5BA1D96E3",
    MASK: "6A4EA303452559810E4FF805FE86AD7057D9807069B3585A8CC9489279BFA66D",
    SURFACE_MI: "745381295CDC76754B9FD347CC85CEBEC3151B042C366CDA40F1908163B8A4F7",
    SURFACE_PARENT: "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768",
    NO_PALMS: "C0EE6CB0A2D9D679D1FB4D64747555D55A5AF18ABED4AEC2666A1D5BECDA97DC",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
ROLES = ["Craters", "Mountains", "Desert", "Hills", "Poles", "Ocean"]
OUTPUT_IDENTITY = "RedProfile.PresentationRoles;Order=Craters,Mountains,Desert,Hills,Poles,Ocean"


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


def asset_file(path):
    require(path.startswith("/Game/"), "Unexpected package root: " + path)
    return PROJECT / ("Content" + path.removeprefix("/Game").replace("/", os.sep) + ".uasset")


def asset_path(value):
    if value is None:
        return None
    path = str(value.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({asset_path(value) for value in values})


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def provider_gate():
    result = {}
    for port in (11111, 5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(result.values()), "Provider/MCP listener unexpectedly active")
    return result


def safe_property(obj, name):
    try:
        return obj.get_editor_property(name)
    except Exception:
        return None


def struct_value(record, *names):
    wanted = {name.replace("_", "").lower() for name in names}
    for key, value in record.to_dict().items():
        if str(key).replace("_", "").lower() in wanted:
            return value
    return None


def expression_inputs(material, node):
    names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(node)]
    sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, node))
    require(len(names) == len(sources), "Input/source cardinality drift: " + node.get_name())
    return list(zip(names, sources))


def dependency_value(node, property_name):
    value = safe_property(node, property_name)
    return asset_path(value) if isinstance(value, unreal.Object) else None


def parameter_record(node):
    name = safe_property(node, "parameter_name")
    if name is None:
        return None
    record = {"node": node.get_name(), "class": node.get_class().get_name(), "parameter": str(name)}
    default = safe_property(node, "default_value")
    if default is not None:
        record["default"] = str(default)
    texture = dependency_value(node, "texture")
    if texture:
        record["texture"] = texture
    return record


def trace_branch(material, root):
    pending = [root]
    seen = set()
    nodes = []
    edges = []
    functions = set()
    textures = set()
    parameters = []
    reroutes = []
    unresolved = []

    while pending:
        node = pending.pop()
        if node is None or node.get_name() in seen:
            continue
        seen.add(node.get_name())
        class_name = node.get_class().get_name()
        nodes.append({"name": node.get_name(), "class": class_name})

        function_path = dependency_value(node, "material_function")
        texture_path = dependency_value(node, "texture")
        if function_path:
            functions.add(function_path)
        if texture_path:
            textures.add(texture_path)
        parameter = parameter_record(node)
        if parameter:
            parameters.append(parameter)

        for input_name, source in expression_inputs(material, node):
            edges.append({
                "target": node.get_name(), "input": input_name,
                "source": source.get_name() if source is not None else None})
            if source is not None:
                pending.append(source)

        if class_name == "MaterialExpressionNamedRerouteUsage":
            bridge = unreal.RedPPGFoliageDiagnostics.inspect_named_reroute_usage(node)
            is_usage = bool(struct_value(bridge, "is_named_reroute_usage"))
            resolved = bool(struct_value(bridge, "declaration_resolved"))
            guid_matches = bool(struct_value(bridge, "guid_matches_declaration"))
            declaration = struct_value(bridge, "declaration")
            declaration_input = struct_value(bridge, "declaration_input_expression")
            record = {
                "usage": node.get_name(),
                "is_usage": is_usage,
                "resolved": resolved,
                "guid_matches": guid_matches,
                "usage_guid": str(struct_value(bridge, "declaration_guid")),
                "declaration_guid": str(struct_value(bridge, "declaration_variable_guid")),
                "declaration_name": str(struct_value(bridge, "declaration_name")),
                "declaration_node": declaration.get_name() if isinstance(declaration, unreal.Object) else None,
                "declaration_input_node": declaration_input.get_name() if isinstance(declaration_input, unreal.Object) else None,
                "declaration_input_output_index": int(struct_value(bridge, "declaration_input_output_index") or 0),
            }
            reroutes.append(record)
            if not is_usage or not resolved or not guid_matches or not isinstance(declaration, unreal.Object):
                unresolved.append(record)
            else:
                edges.append({
                    "target": node.get_name(), "input": "NamedDeclaration",
                    "source": declaration.get_name()})
                pending.append(declaration)
                if isinstance(declaration_input, unreal.Object):
                    pending.append(declaration_input)

    nodes.sort(key=lambda item: item["name"])
    edges.sort(key=lambda item: (item["target"], item["input"], item["source"] or ""))
    parameters.sort(key=lambda item: (item["parameter"], item["node"]))
    signature_payload = {
        "classes": sorted(Counter(item["class"] for item in nodes).items()),
        "functions": sorted(functions),
        "textures": sorted(textures),
        "parameters": parameters,
    }
    signature = hashlib.sha256(json.dumps(signature_payload, sort_keys=True).encode("utf-8")).hexdigest().upper()
    return {
        "root_node": root.get_name(),
        "root_class": root.get_class().get_name(),
        "node_count": len(nodes),
        "class_counts": dict(sorted(Counter(item["class"] for item in nodes).items())),
        "nodes": nodes,
        "edges": edges,
        "material_functions": sorted(functions),
        "textures": sorted(textures),
        "parameters": parameters,
        "named_reroutes": sorted(reroutes, key=lambda item: item["usage"]),
        "unresolved_trace_points": unresolved,
        "presentation_signature_sha256": signature,
    }


def fixed_point_closure(registry, roots, cap=1024):
    options = unreal.AssetRegistryDependencyOptions(
        include_soft_package_references=True,
        include_hard_package_references=True,
        include_searchable_names=False,
        include_soft_management_references=False,
        include_hard_management_references=False,
    )
    pending = deque(sorted(roots))
    seen = set()
    while pending:
        package = pending.popleft()
        if package in seen:
            continue
        require(len(seen) < cap, "Dependency closure cap exceeded")
        seen.add(package)
        for dependency in registry.get_dependencies(unreal.Name(package), options) or []:
            value = str(dependency)
            if value.startswith(("/Game/", "/PPG/", "/Engine/")) and value not in seen:
                pending.append(value)
    return sorted(seen)


_EXIT = {"handle": None}


def schedule_exit(delay=3.0):
    started = time.monotonic()

    def tick(_delta):
        if time.monotonic() - started < delay:
            return
        handle = _EXIT.get("handle")
        if handle is not None:
            unreal.unregister_slate_post_tick_callback(handle)
            _EXIT["handle"] = None
        unreal.SystemLibrary.quit_editor()

    _EXIT["handle"] = unreal.register_slate_post_tick_callback(tick)


def main():
    report = {
        "schema": "redmmo.ppg_profile_v1.surface_topology.r70.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        require(not RESULT.exists(), "Result no-clobber failed")
        require(not dirty_packages(), "Dirty packages before R70")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
        report["provider_gate_before"] = provider_gate()
        for path, expected_hash in EXPECTED_HASHES.items():
            require(asset_file(path).is_file() and sha256(asset_file(path)) == expected_hash,
                    "Package hash drift: " + path)
        for path, expected_hash in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected_hash,
                    "Protected hash drift: " + str(path))

        planet = unreal.EditorAssetLibrary.load_asset(PLANET)
        surface_mi = unreal.EditorAssetLibrary.load_asset(SURFACE_MI)
        material = unreal.EditorAssetLibrary.load_asset(SURFACE_PARENT)
        require(planet is not None and planet.get_class().get_name() == "PlanetData", "PlanetData missing")
        require(surface_mi is not None and surface_mi.get_class().get_name() == "MaterialInstanceConstant", "R67 MI missing")
        require(material is not None and material.get_class().get_name() == "Material", "Surface parent missing")
        require(asset_path(planet.get_editor_property("planet_material")) == SURFACE_MI, "R67 binding drift")
        require(asset_path(surface_mi.get_editor_property("parent")) == SURFACE_PARENT, "Surface parent drift")

        expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
        outputs = [node for node in expressions
                   if node.get_class().get_name() == "MaterialExpressionPlanetBiomeMaterialOutput"]
        require(len(outputs) == 1, "Expected one PlanetBiomeMaterialOutput")
        output = outputs[0]
        require(str(output.get_editor_property("desc")) == OUTPUT_IDENTITY, "Output identity drift")
        biome_names = [str(value) for value in list(output.get_editor_property("biome_names"))]
        require(biome_names == ROLES, "Output role order drift")
        output_inputs = expression_inputs(material, output)
        input_map = {name: source for name, source in output_inputs}
        require(all(role in input_map and input_map[role] is not None for role in ROLES),
                "Disconnected biome role")

        branches = {role: trace_branch(material, input_map[role]) for role in ROLES}
        require(all(not record["unresolved_trace_points"] for record in branches.values()),
                "Compiled bridge left unresolved reroutes")
        require(all(record["named_reroutes"] for record in branches.values()),
                "Expected named reroutes in every branch")

        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        closures = {}
        for role, record in branches.items():
            roots = set(record["material_functions"]) | set(record["textures"])
            closures[role] = fixed_point_closure(registry, roots)

        role_node_sets = {role: {item["name"] for item in record["nodes"]}
                          for role, record in branches.items()}
        common_nodes = sorted(set.intersection(*(values for values in role_node_sets.values())))
        signature_groups = {}
        for role, record in branches.items():
            signature_groups.setdefault(record["presentation_signature_sha256"], []).append(role)

        report.update({
            "status": "PASS_R70_COMPLETE_SIX_BIOME_SURFACE_TOPOLOGY_READ_ONLY",
            "surface_parent": SURFACE_PARENT,
            "active_surface_instance": SURFACE_MI,
            "surface_output": {
                "node": output.get_name(),
                "identity": str(output.get_editor_property("desc")),
                "biome_names": biome_names,
                "input_names": [name for name, _source in output_inputs],
            },
            "branches": branches,
            "branch_dependency_closures": closures,
            "common_upstream_nodes": common_nodes,
            "signature_groups": [
                {"signature_sha256": signature, "roles": roles}
                for signature, roles in sorted(signature_groups.items())
            ],
            "bridge_resolution": {
                "all_usages_resolved": True,
                "all_guids_match": True,
                "unresolved_count": 0,
                "implementation": "/Script/RedMMO.RedPPGFoliageDiagnostics.InspectNamedRerouteUsage",
            },
            "home_map_sha256_before_after": EXPECTED_HOME,
            "package_hashes_before_after": EXPECTED_HASHES,
            "save_called": False,
            "regeneration_called": False,
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": (
                "Complete read-only material topology and package closure only; no visual, "
                "material-write, regeneration, gameplay, package, replication or multiplayer claim."),
        })
        require(not report["dirty_packages_after"], "R70 dirtied packages")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map changed")
        for path, expected_hash in EXPECTED_HASHES.items():
            require(sha256(asset_file(path)) == expected_hash, "Package changed: " + path)
        for path, expected_hash in PROTECTED.items():
            require(sha256(path) == expected_hash, "Protected file changed: " + str(path))
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_R70_SURFACE_TOPOLOGY " + report["status"])
        schedule_exit()


main()
