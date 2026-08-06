"""Read-only dependency map for all six ProfileV1 surface branches.

The audit traces each connected PlanetBiomeMaterialOutput role upstream through
the project-owned material graph, resolves named reroutes, inventories exact
function/texture/parameter dependencies, and computes branch overlap. It never
saves, binds, regenerates, or loads the home map intentionally.
"""

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
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1SurfaceBranches_20260805_0426_R02")
RESULT = DIAG / "audit_redmmo_ppg_profile_v1_surface_branches_result.json"

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
PLANET = ROOT + "/DA_PPG_ProfileV1_PlanetData"
SURFACE_MI = ROOT + "/MI_PPG_ProfileV1_Surface"
SURFACE_PARENT = ROOT + "/M_PPG_ProfileV1_SurfaceParent"
GENERATION = ROOT + "/M_PPG_ProfileV1_Generation"
MASK = ROOT + "/M_PPG_ProfileV1_BiomeMask"

EXPECTED_HASHES = {
    PLANET: "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837",
    GENERATION: "5CD34E415CADD6B632B2896AE51461B8E7909FCC456027FC5E5CA8CC63EF541A",
    MASK: "6A4EA303452559810E4FF805FE86AD7057D9807069B3585A8CC9489279BFA66D",
    SURFACE_MI: "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66",
    SURFACE_PARENT: "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768",
}

PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

ROLES = ["Craters", "Mountains", "Desert", "Hills", "Poles", "Ocean"]
OUTPUT_IDENTITY = "RedProfile.PresentationRoles;Order=Craters,Mountains,Desert,Hills,Poles,Ocean"


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


def safe_property(obj, name):
    try:
        return obj.get_editor_property(name)
    except Exception:
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
    record = {
        "node": node.get_name(),
        "class": node.get_class().get_name(),
        "parameter": str(name),
    }
    default = safe_property(node, "default_value")
    if default is not None:
        record["default"] = str(default)
    texture = dependency_value(node, "texture")
    if texture:
        record["texture"] = texture
    return record


def direct_asset_record(path):
    exists = bool(unreal.EditorAssetLibrary.does_asset_exist(path))
    asset = unreal.EditorAssetLibrary.load_asset(path) if exists else None
    return {
        "asset": path,
        "exists": exists,
        "class": asset.get_class().get_name() if asset is not None else None,
        "project_owned": path.startswith("/Game/RedMMO/"),
        "installed_pack_content": path.startswith("/Game/") and not path.startswith("/Game/RedMMO/"),
        "plugin_content": not path.startswith("/Game/"),
    }


def trace_branch(material, root):
    all_expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
    declarations_by_guid = {}
    for expression in all_expressions:
        if expression.get_class().get_name() != "MaterialExpressionNamedRerouteDeclaration":
            continue
        guid = safe_property(expression, "variable_guid")
        if guid is not None:
            declarations_by_guid[str(guid)] = expression
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
        param = parameter_record(node)
        if param:
            parameters.append(param)

        inputs = expression_inputs(material, node)
        for input_name, source in inputs:
            edges.append({
                "target": node.get_name(),
                "input": input_name,
                "source": source.get_name() if source is not None else None,
            })
            if source is not None:
                pending.append(source)

        if class_name == "MaterialExpressionNamedRerouteUsage":
            declaration = safe_property(node, "declaration")
            if not isinstance(declaration, unreal.Object):
                declaration_guid = safe_property(node, "declaration_guid")
                declaration = declarations_by_guid.get(str(declaration_guid))
            if isinstance(declaration, unreal.Object):
                reroutes.append({"usage": node.get_name(), "declaration": declaration.get_name()})
                edges.append({"target": node.get_name(), "input": "NamedDeclaration", "source": declaration.get_name()})
                pending.append(declaration)
            else:
                unresolved.append({
                    "node": node.get_name(),
                    "reason": "named reroute declaration unavailable by pointer and GUID",
                    "declaration_guid": str(safe_property(node, "declaration_guid")),
                    "known_declaration_guids": sorted(declarations_by_guid),
                })

    nodes.sort(key=lambda item: item["name"])
    edges.sort(key=lambda item: (item["target"], item["input"], item["source"] or ""))
    parameters.sort(key=lambda item: (item["parameter"], item["node"]))
    external = sorted(functions | textures)
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
        "direct_external_assets": [direct_asset_record(path) for path in external],
        "presentation_signature_sha256": signature,
    }


def fixed_point_closure(registry, roots, cap=512):
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
        for dep in registry.get_dependencies(unreal.Name(package), options) or []:
            value = str(dep)
            if value.startswith(("/Game/", "/PPG/", "/Engine/")) and value not in seen:
                pending.append(value)
    return sorted(seen)


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
        "schema": "redmmo.ppg_profile_v1.surface_branches.read_only.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "editor_automation_read_only",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        require(not RESULT.exists(), "Result no-clobber failed")
        require(not dirty_packages(), "Dirty packages before branch audit")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
        report["provider_gate"] = provider_gate()
        for path, expected_hash in EXPECTED_HASHES.items():
            require(asset_file(path).is_file() and sha256(asset_file(path)) == expected_hash, "Profile package hash drift: " + path)
        for path, expected_hash in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Protected hash drift: " + str(path))

        planet = unreal.EditorAssetLibrary.load_asset(PLANET)
        surface_mi = unreal.EditorAssetLibrary.load_asset(SURFACE_MI)
        material = unreal.EditorAssetLibrary.load_asset(SURFACE_PARENT)
        require(planet is not None and planet.get_class().get_name() == "PlanetData", "PlanetData missing")
        require(surface_mi is not None and surface_mi.get_class().get_name() == "MaterialInstanceConstant", "Surface MI missing")
        require(material is not None and material.get_class().get_name() == "Material", "Surface parent missing")
        require(asset_path(planet.get_editor_property("planet_material")) == SURFACE_MI, "PlanetData surface binding drift")
        require(asset_path(surface_mi.get_editor_property("parent")) == SURFACE_PARENT, "Surface parent binding drift")

        expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
        outputs = [node for node in expressions if node.get_class().get_name() == "MaterialExpressionPlanetBiomeMaterialOutput"]
        require(len(outputs) == 1, "Expected one PlanetBiomeMaterialOutput")
        output = outputs[0]
        require(str(output.get_editor_property("desc")) == OUTPUT_IDENTITY, "Output identity drift")
        biome_names = [str(value) for value in list(output.get_editor_property("biome_names"))]
        require(biome_names == ROLES, "Output role order drift")

        output_inputs = expression_inputs(material, output)
        input_map = {name: source for name, source in output_inputs}
        require(all(role in input_map and input_map[role] is not None for role in ROLES), "Disconnected biome role")
        branches = {role: trace_branch(material, input_map[role]) for role in ROLES}
        report["partial_branches_before_completeness_gate"] = branches
        require(all(not value["unresolved_trace_points"] for value in branches.values()), "Unresolved branch trace points after pointer-and-GUID resolution")

        role_node_sets = {role: {item["name"] for item in record["nodes"]} for role, record in branches.items()}
        common_nodes = sorted(set.intersection(*(values for values in role_node_sets.values())))
        pairwise = []
        for index, left in enumerate(ROLES):
            for right in ROLES[index + 1:]:
                intersection = role_node_sets[left] & role_node_sets[right]
                union = role_node_sets[left] | role_node_sets[right]
                pairwise.append({
                    "left": left,
                    "right": right,
                    "shared_node_count": len(intersection),
                    "union_node_count": len(union),
                    "jaccard": round(len(intersection) / len(union), 6) if union else 1.0,
                    "same_presentation_signature": branches[left]["presentation_signature_sha256"] == branches[right]["presentation_signature_sha256"],
                })

        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        branch_closures = {}
        for role, record in branches.items():
            roots = set(record["material_functions"]) | set(record["textures"])
            branch_closures[role] = fixed_point_closure(registry, roots)

        report.update({
            "status": "PASS_SIX_SURFACE_BRANCHES_MAPPED_READ_ONLY",
            "surface_parent": SURFACE_PARENT,
            "surface_output": {
                "node": output.get_name(),
                "identity": str(output.get_editor_property("desc")),
                "input_names": [name for name, _source in output_inputs],
                "biome_names": biome_names,
            },
            "branches": branches,
            "branch_dependency_closures": branch_closures,
            "common_upstream_nodes": common_nodes,
            "pairwise_overlap": pairwise,
            "exact_project_owned_role_candidates": {
                role: {
                    "candidate_node": branches[role]["root_node"],
                    "candidate_identity": "RedProfile.Role." + role,
                    "owning_material": SURFACE_PARENT,
                    "requires_future_write": True,
                }
                for role in ROLES
            },
            "package_hashes_before_after": EXPECTED_HASHES,
            "home_map_sha256_before_after": EXPECTED_HOME,
            "save_called": False,
            "regeneration_called": False,
            "dirty_packages_after": dirty_packages(),
            "next_safe_action": "Under fresh rollback, tag the six exact branch-root nodes with RedProfile.Role identities only if their roots are distinct and the audit closure is complete; keep ProfileV1 unbound and do not change branch connections or runtime parameters.",
        })
        require(not report["dirty_packages_after"], "Audit dirtied packages")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map changed")
        for path, expected_hash in EXPECTED_HASHES.items():
            require(sha256(asset_file(path)) == expected_hash, "Profile package changed: " + path)
        for path, expected_hash in PROTECTED.items():
            require(sha256(path) == expected_hash, "Protected file changed: " + str(path))
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PPG_PROFILE_V1_SURFACE_BRANCHES " + report["status"])
        schedule_exit()


main()
