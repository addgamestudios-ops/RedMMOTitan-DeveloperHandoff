"""Read-only R47 audit of the approved grass opacity/WPO/dither path."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import traceback
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
ROOT = PROJECT.parent
RESULT = Path(os.environ["REDMMO_R47_RESULT"])
VENDOR_PARENT = "/Game/StylizedRocksPack_01/Common/GrassChunks/Materials/M_GrassChunks_Base"
VENDOR_INSTANCE = "/Game/StylizedRocksPack_01/Common/GrassChunks/Materials/MI_GrassChunks_01"
R32_PARENT = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R32/Materials/M_GrassChunks_PPGReadable_R32"
R10N_INSTANCES = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_B_R10N",
]
CHECKS = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    ROOT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap": "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset": "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970",
    ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset": "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8",
    ROOT / r"Content\StylizedRocksPack_01\Common\GrassChunks\Materials\M_GrassChunks_Base.uasset": "B8FD57E1371DAEC8AAE33C9A4A4F15A9420F7BFD8A8F0F0138F36822355EEE10",
    ROOT / r"Content\StylizedRocksPack_01\Common\GrassChunks\Materials\MI_GrassChunks_01.uasset": "003CA8267AD521A77401638FD41C201FF5D2A3693AC10F1D5582C19F9BC35BC7",
    ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R32\Materials\M_GrassChunks_PPGReadable_R32.uasset": "2BD2B8DD41C611CF1250F1A39C40D3B4A7C47B5EB71ECD1497732546B80F0210",
    ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset": "91A0E7233A5922A921FB4CF8692B8631DBB7AEFE7D3D106FDB63C44DB412CE47",
    ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset": "19D1B594553977A6A7BA116271F103DCD4044F8F24C3E8B5CF8F596082A9F68E",
    ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset": "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset": "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"): "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"): "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
KEYWORDS = ("opacity", "alpha", "dither", "fade", "wpo", "position", "camera", "player", "distance", "scale", "mask")


def require(value, message):
    if not value:
        raise RuntimeError(message)


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


def stable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "get_path_name"):
        return asset_path(value)
    if hasattr(value, "to_dict"):
        return {str(key): stable(item) for key, item in value.to_dict().items()}
    if isinstance(value, (list, tuple)):
        return [stable(item) for item in value]
    return str(value)


def safe_prop(obj, name):
    try:
        return stable(obj.get_editor_property(name))
    except Exception:
        return None


def dirty_packages():
    return {
        "content": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}),
        "maps": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}),
    }


def provider_gate():
    result = {}
    for port in (11111, 5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(result.values()), "provider listener active")
    return result


def node_record(node):
    result = {
        "name": node.get_name(),
        "class": node.get_class().get_name(),
        "desc": safe_prop(node, "desc"),
    }
    for prop in ("parameter_name", "default_value", "value", "material_function", "texture"):
        value = safe_prop(node, prop)
        if value is not None:
            result[prop] = value
    return result


def graph(material):
    expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
    nodes = {node.get_name(): node for node in expressions}
    records = {name: node_record(node) for name, node in nodes.items()}
    inbound = {name: [] for name in nodes}
    edges = []
    for target in expressions:
        names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(target)]
        sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, target))
        require(len(names) == len(sources), "input cardinality drift: " + target.get_name())
        for input_name, source in zip(names, sources):
            if source is None:
                continue
            edge = {"source": source.get_name(), "target": target.get_name(), "input": input_name}
            edges.append(edge)
            inbound[target.get_name()].append(edge)
    topology = [
        (
            records[name]["class"],
            records[name].get("parameter_name"),
            records[name].get("material_function"),
            records[name].get("texture"),
        )
        for name in sorted(records)
    ]
    topology_edges = sorted((records[edge["source"]]["class"], records[edge["target"]]["class"], edge["input"]) for edge in edges)
    signature = hashlib.sha256(json.dumps({"nodes": topology, "edges": topology_edges}, sort_keys=True).encode("utf-8")).hexdigest().upper()
    return expressions, nodes, records, inbound, edges, signature


def property_closure(material, enum_name, nodes, records, inbound):
    enum_value = getattr(unreal.MaterialProperty, enum_name, None)
    if enum_value is None:
        return {"enum_available": False}
    root = unreal.MaterialEditingLibrary.get_material_property_input_node(material, enum_value)
    output = str(unreal.MaterialEditingLibrary.get_material_property_input_node_output_name(material, enum_value))
    if root is None:
        return {"enum_available": True, "root": None, "output": output, "reachable": []}
    pending = deque([root.get_name()])
    seen = set()
    while pending:
        name = pending.popleft()
        if name in seen:
            continue
        seen.add(name)
        for edge in inbound.get(name, []):
            pending.append(edge["source"])
    reachable = [records[name] for name in sorted(seen)]
    hidden_reroute_stops = [
        item for item in reachable
        if item["class"] == "MaterialExpressionNamedRerouteUsage" and not inbound.get(item["name"])
    ]
    return {
        "enum_available": True,
        "root": records[root.get_name()],
        "output": output,
        "reachable_count": len(reachable),
        "reachable": reachable,
        "hidden_reroute_stops": hidden_reroute_stops,
    }


def material_record(path):
    material = unreal.EditorAssetLibrary.load_asset(path)
    require(material is not None, "material load failed: " + path)
    expressions, nodes, records, inbound, edges, signature = graph(material)
    flags = {}
    for name in (
        "blend_mode", "two_sided", "opacity_mask_clip_value", "dithered_lod_transition",
        "used_with_instanced_static_meshes", "used_with_foliage", "automatically_set_usage_in_editor",
        "use_material_attributes", "allow_negative_emissive_color",
    ):
        flags[name] = safe_prop(material, name)
    function_calls = [item for item in records.values() if item["class"] == "MaterialExpressionMaterialFunctionCall"]
    relevant_parameters = [
        item for item in records.values()
        if item.get("parameter_name") and any(key in str(item["parameter_name"]).lower() for key in KEYWORDS)
    ]
    return {
        "path": path,
        "flags": flags,
        "expression_count": len(expressions),
        "edge_count": len(edges),
        "class_counts": dict(sorted(Counter(item["class"] for item in records.values()).items())),
        "topology_signature": signature,
        "function_calls": sorted(function_calls, key=lambda item: item["name"]),
        "relevant_parameters": sorted(relevant_parameters, key=lambda item: str(item.get("parameter_name"))),
        "properties": {
            "base_color": property_closure(material, "MP_BASE_COLOR", nodes, records, inbound),
            "opacity_mask": property_closure(material, "MP_OPACITY_MASK", nodes, records, inbound),
            "world_position_offset": property_closure(material, "MP_WORLD_POSITION_OFFSET", nodes, records, inbound),
            "pixel_depth_offset": property_closure(material, "MP_PIXEL_DEPTH_OFFSET", nodes, records, inbound),
        },
    }


def instance_record(path):
    instance = unreal.EditorAssetLibrary.load_asset(path)
    require(instance is not None, "instance load failed: " + path)
    lib = unreal.MaterialEditingLibrary
    scalars = {}
    switches = {}
    for name_value in lib.get_scalar_parameter_names(instance):
        name = str(name_value)
        if any(key in name.lower() for key in KEYWORDS):
            scalars[name] = float(lib.get_material_instance_scalar_parameter_value(instance, name))
    for name_value in lib.get_static_switch_parameter_names(instance):
        name = str(name_value)
        if any(key in name.lower() for key in KEYWORDS):
            switches[name] = bool(lib.get_material_instance_static_switch_parameter_value(instance, name))
    return {
        "path": path,
        "parent": asset_path(instance.get_editor_property("parent")),
        "base_material": asset_path(instance.get_base_material()),
        "relevant_scalars": dict(sorted(scalars.items())),
        "relevant_switches": dict(sorted(switches.items())),
    }


def write_result(payload):
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with RESULT.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def run():
    active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
    require(active == PROJECT.resolve(strict=True), "wrong project")
    require(not RESULT.exists(), "R47 result no-clobber failed")
    for path, expected in CHECKS.items():
        require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
    require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
    command = str(unreal.SystemLibrary.get_command_line()).lower()
    require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
    providers = provider_gate()

    vendor = material_record(VENDOR_PARENT)
    project = material_record(R32_PARENT)
    vendor_instance = instance_record(VENDOR_INSTANCE)
    project_instances = [instance_record(path) for path in R10N_INSTANCES]
    require(vendor["expression_count"] == project["expression_count"] == 516, "parent expression-count drift")
    require(vendor["topology_signature"] == project["topology_signature"], "R32 graph topology differs from vendor")
    require(vendor["flags"]["blend_mode"] != project["flags"]["blend_mode"], "expected R32 blend-mode divergence absent")
    require("opaque" in str(vendor["flags"]["blend_mode"]).lower(), "vendor parent is not Opaque")
    require("masked" in str(project["flags"]["blend_mode"]).lower(), "R32 parent is not Masked")
    opacity = project["properties"]["opacity_mask"]
    wpo = project["properties"]["world_position_offset"]
    require(opacity.get("root") is not None, "R32 opacity root missing")
    require(wpo.get("root") is not None, "R32 WPO root missing")
    switch_values = [item["relevant_switches"].get("GrassNearGround_Dithering_Enable") for item in project_instances]
    require(switch_values == [True, True], "R10N near-ground dither switch drift")

    return {
        "schema": "redmmo.grass.opacity_wpo.audit.r47.v1",
        "status": "PASS_R47_READ_ONLY_OPACITY_WPO_DITHER_AUDIT",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "automation",
        "vendor_parent": vendor,
        "project_parent": project,
        "vendor_instance": vendor_instance,
        "project_instances": project_instances,
        "diagnosis": {
            "graph_topology_byte_independent_signature_equal": True,
            "vendor_parent_blend_mode": vendor["flags"]["blend_mode"],
            "project_parent_blend_mode": project["flags"]["blend_mode"],
            "r32_activates_vendor_opacity_path_that_vendor_opaque_ignores": True,
            "r32_opacity_mask_clip_value": project["flags"]["opacity_mask_clip_value"],
            "near_ground_dither_enabled_on_both_approved_instances": True,
            "wpo_root_connected": True,
            "opacity_hidden_reroute_stops": len(opacity.get("hidden_reroute_stops", [])),
            "wpo_hidden_reroute_stops": len(wpo.get("hidden_reroute_stops", [])),
            "causality_boundary": (
                "R32 uniquely activates the vendor graph's dormant opacity path by changing Opaque to Masked, and both approved instances enable near-ground dithering. "
                "This is the first untested material-path divergence, but read-only topology cannot prove which opacity/WPO branch produces zero pixels because named-reroute usage links are hidden from UE Python."
            ),
        },
        "dirty_packages_after": dirty_packages(),
        "provider_gate_before_after": providers,
        "save_called": False,
        "map_loaded": False,
        "pie_started": False,
        "screenshot_called": False,
        "claim_limit": "Read-only D3D12 asset/topology automation only; no visual or runtime acceptance claim.",
    }


try:
    write_result(run())
    unreal.log("REDMMO_R47_PASS")
except Exception as error:
    write_result({
        "schema": "redmmo.grass.opacity_wpo.audit.r47.v1",
        "status": "FAIL",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "error": str(error),
        "traceback": traceback.format_exc(),
    })
    unreal.log_error("REDMMO_R47_FAIL " + str(error))
finally:
    unreal.SystemLibrary.quit_editor()
