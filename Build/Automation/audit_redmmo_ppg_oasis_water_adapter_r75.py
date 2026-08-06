"""Read-only R75 audit of Oasis water versus PPG's native spherical-water contract.

The audit loads the installed owned assets in the clean RedMMO project, records
their public material interfaces and dependency closures, compares those
interfaces with the exact parameters PPG injects into every native water chunk,
and exits without saving a package or starting PIE.
"""

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import time

import unreal


PROJECT_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
CONTENT = PROJECT_FILE.parent / "Content"
HOME = CONTENT / "RedMMO" / "Maps" / "RedMMO_PPG_HomeWorld.umap"
PROFILE = CONTENT / "RedMMO" / "WorldAuthoring" / "PPG" / "ProfileV1" / "DA_PPG_ProfileV1_PlanetData.uasset"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_OasisWaterAdapter_R75B_20260806T0022Z")
RESULT = DIAG / "result.json"

EXPECTED_HOME = "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3"
EXPECTED_PROFILE = "E19F14597BA1B73C958F6022B92A41B0C1A5F61573390295D3EEBD7484DBC335"

OASIS_MI = "/Game/StylizedDesertOasis/Materials/Instances/Environment/MI_Water"
OASIS_MASTER = "/Game/StylizedDesertOasis/Materials/MasterMaterials/M_Water"
PPG_MASTER = "/PPG/Water/Materials/M_PlanetaryOceanWater"

REQUIRED_TEXTURES = {"HeightMap"}
REQUIRED_SCALARS = {"PlanetRadius"}
REQUIRED_VECTORS = set()
INJECTED_OPTIONAL_SCALARS = {"ChunkSizeHigh", "ChunkSizeLow", "PlanetPositionScale"}
INJECTED_OPTIONAL_VECTORS = {
    "ComponentLocation",
    "ComponentLocationHigh",
    "ComponentLocationLow",
    "ComponentLocationLWC",
    "ChunkLocationHigh",
    "ChunkLocationLow",
    "PlanetSpaceRotation",
}
PORTS = (11111, 5353, 8000, 8765)


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(obj):
    if not obj:
        return None
    value = str(obj.get_path_name()).split(".", 1)[0]
    return value


def package_file(package):
    if package.startswith("/Game/"):
        return CONTENT / (package.removeprefix("/Game/").replace("/", os.sep) + ".uasset")
    if package.startswith("/PPG/"):
        return Path(r"D:\UE_5.8\Engine\Plugins\Marketplace\Procedur890d9e860517V2\Content") / (
            package.removeprefix("/PPG/").replace("/", os.sep) + ".uasset"
        )
    return None


def provider_gate():
    states = {}
    for port in PORTS:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.08)
        states[str(port)] = sock.connect_ex(("127.0.0.1", port)) != 0
        sock.close()
    require(all(states.values()), "Provider listener active")
    return states


def dirty_packages():
    return {
        "content": sorted(str(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()),
        "maps": sorted(str(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()),
    }


def write_once(payload):
    DIAG.mkdir(parents=True, exist_ok=False)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with RESULT.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def material_interface(asset):
    editing = unreal.MaterialEditingLibrary
    return {
        "asset": asset_path(asset),
        "class": asset.get_class().get_name(),
        "scalar_parameters": sorted(str(item) for item in editing.get_scalar_parameter_names(asset)),
        "vector_parameters": sorted(str(item) for item in editing.get_vector_parameter_names(asset)),
        "texture_parameters": sorted(str(item) for item in editing.get_texture_parameter_names(asset)),
        "static_switch_parameters": sorted(str(item) for item in editing.get_static_switch_parameter_names(asset)),
    }


def parent_chain(asset):
    chain = []
    current = asset
    while isinstance(current, unreal.MaterialInstance):
        parent = current.get_editor_property("parent")
        chain.append(asset_path(parent))
        current = parent
        if not current:
            break
    return chain


def safe_property(obj, name):
    try:
        value = obj.get_editor_property(name)
    except Exception:
        return None
    if hasattr(value, "get_path_name"):
        return asset_path(value)
    return str(value)


def expression_inventory(material):
    records = []
    for node in unreal.MaterialEditingLibrary.get_material_expressions(material):
        record = {"class": node.get_class().get_name(), "name": node.get_name()}
        for name in ("parameter_name", "texture", "material_function", "desc"):
            value = safe_property(node, name)
            if value not in (None, "None", ""):
                record[name] = value
        records.append(record)
    return records


def closure(registry, root, prefix, cap=256):
    options = unreal.AssetRegistryDependencyOptions(
        include_soft_package_references=True,
        include_hard_package_references=True,
        include_searchable_names=False,
        include_soft_management_references=False,
        include_hard_management_references=False,
    )
    pending = deque([root])
    seen = set()
    while pending:
        package = pending.popleft()
        if package in seen:
            continue
        require(len(seen) < cap, "Dependency closure cap exceeded: " + root)
        seen.add(package)
        for dep in registry.get_dependencies(unreal.Name(package), options) or []:
            value = str(dep)
            if value.startswith(prefix) and value not in seen:
                pending.append(value)
    records = []
    for package in sorted(seen):
        file_path = package_file(package)
        obj = unreal.EditorAssetLibrary.load_asset(package)
        records.append(
            {
                "package": package,
                "loadable": bool(obj),
                "class": obj.get_class().get_name() if obj else None,
                "file": str(file_path) if file_path else None,
                "bytes": file_path.stat().st_size if file_path and file_path.is_file() else None,
                "sha256": sha256(file_path) if file_path and file_path.is_file() else None,
            }
        )
    return records


def compatibility(record):
    textures = set(record["texture_parameters"])
    scalars = set(record["scalar_parameters"])
    vectors = set(record["vector_parameters"])
    missing = {
        "textures": sorted(REQUIRED_TEXTURES - textures),
        "scalars": sorted(REQUIRED_SCALARS - scalars),
        "vectors": sorted(REQUIRED_VECTORS - vectors),
    }
    return {
        "direct_bind_compatible": not any(missing.values()),
        "missing_required_parameters": missing,
        "present_required_parameters": {
            "textures": sorted(REQUIRED_TEXTURES & textures),
            "scalars": sorted(REQUIRED_SCALARS & scalars),
            "vectors": sorted(REQUIRED_VECTORS & vectors),
        },
    }


_EXIT = {"handle": None}


def schedule_exit(delay=2.0):
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
        "schema": "redmmo.ppg.oasis_water_adapter.audit.r75.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        require(active == os.path.normcase(os.path.abspath(str(PROJECT_FILE))), "Active project mismatch")
        require(not RESULT.exists() and not DIAG.exists(), "R75 no-clobber path exists")
        require(sha256(HOME) == EXPECTED_HOME, "Home map hash drift")
        require(sha256(PROFILE) == EXPECTED_PROFILE, "ProfileV1 hash drift")
        require(not any(dirty_packages().values()), "Dirty packages before R75")
        report["provider_gate_before"] = provider_gate()

        oasis_mi = unreal.EditorAssetLibrary.load_asset(OASIS_MI)
        oasis_master = unreal.EditorAssetLibrary.load_asset(OASIS_MASTER)
        ppg_master = unreal.EditorAssetLibrary.load_asset(PPG_MASTER)
        require(isinstance(oasis_mi, unreal.MaterialInstance), "Oasis MI_Water missing")
        require(isinstance(oasis_master, unreal.Material), "Oasis M_Water missing")
        require(isinstance(ppg_master, unreal.Material), "PPG water master missing")

        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        oasis_interface = material_interface(oasis_mi)
        ppg_interface = material_interface(ppg_master)
        oasis_nodes = expression_inventory(oasis_master)
        ppg_nodes = expression_inventory(ppg_master)
        oasis_closure = closure(registry, OASIS_MI, "/Game/StylizedDesertOasis/")
        ppg_closure = closure(registry, PPG_MASTER, "/PPG/")

        planar_or_scene_classes = sorted(
            {
                item["class"]
                for item in oasis_nodes
                if any(
                    token in item["class"].lower()
                    for token in ("worldposition", "distancefield", "scenedepth", "depthfade", "pixeldepth", "runtimevirtualtexture")
                )
            }
        )
        oasis_texture_assets = sorted(
            {item["texture"] for item in oasis_nodes if item.get("texture")}
        )
        oasis_function_assets = sorted(
            {item["material_function"] for item in oasis_nodes if item.get("material_function")}
        )

        report.update(
            {
                "oasis": {
                    "instance": oasis_interface,
                    "parent_chain": parent_chain(oasis_mi),
                    "master": material_interface(oasis_master),
                    "master_properties": {
                        "material_domain": safe_property(oasis_master, "material_domain"),
                        "blend_mode": safe_property(oasis_master, "blend_mode"),
                        "shading_model": safe_property(oasis_master, "shading_model"),
                        "two_sided": safe_property(oasis_master, "two_sided"),
                    },
                    "expression_count": len(oasis_nodes),
                    "expression_classes": sorted({item["class"] for item in oasis_nodes}),
                    "planar_or_scene_dependency_classes": planar_or_scene_classes,
                    "referenced_textures": oasis_texture_assets,
                    "referenced_material_functions": oasis_function_assets,
                    "dependency_closure": oasis_closure,
                    "dependency_count": len(oasis_closure),
                    "all_dependencies_loadable": all(item["loadable"] for item in oasis_closure),
                    "ppg_compatibility": compatibility(oasis_interface),
                },
                "ppg": {
                    "master": ppg_interface,
                    "master_properties": {
                        "material_domain": safe_property(ppg_master, "material_domain"),
                        "blend_mode": safe_property(ppg_master, "blend_mode"),
                        "shading_model": safe_property(ppg_master, "shading_model"),
                        "two_sided": safe_property(ppg_master, "two_sided"),
                    },
                    "expression_count": len(ppg_nodes),
                    "expression_classes": sorted({item["class"] for item in ppg_nodes}),
                    "dependency_closure": ppg_closure,
                    "dependency_count": len(ppg_closure),
                    "all_dependencies_loadable": all(item["loadable"] for item in ppg_closure),
                    "ppg_compatibility": compatibility(ppg_interface),
                },
                "required_native_chunk_parameters": {
                    "textures": sorted(REQUIRED_TEXTURES),
                    "scalars": sorted(REQUIRED_SCALARS),
                    "vectors": sorted(REQUIRED_VECTORS),
                    "injected_but_not_consumed_by_stock_master_scalars": sorted(INJECTED_OPTIONAL_SCALARS),
                    "injected_but_not_consumed_by_stock_master_vectors": sorted(INJECTED_OPTIONAL_VECTORS),
                    "source": "installed PPG ChunkObject.cpp SetPlanetSurfaceMaterialParameters plus AddWaterChunk; the stock master authenticates HeightMap and PlanetRadius as its consumed public interface",
                },
                "adapter_decision": {
                    "direct_oasis_binding_safe": compatibility(oasis_interface)["direct_bind_compatible"],
                    "safe_route": "Create a project-owned successor of the proven PPG spherical-water graph, preserve every required PPG parameter and native chunk binding, then reuse only verified owned Oasis visual inputs such as its normal textures and restrained color controls.",
                    "forbidden_route": "Do not bind MI_Water or M_Water directly to PlanetData and do not place a planar carrier.",
                    "requires_real_gpu_next": True,
                },
                "persistent_map_or_asset_writes": False,
                "generation_called": False,
                "pie_started": False,
                "dirty_packages_after": dirty_packages(),
                "home_sha256_after": sha256(HOME),
                "profile_sha256_after": sha256(PROFILE),
                "provider_gate_after": provider_gate(),
                "status": "PASS_R75_OASIS_CLOSURE_LOADABLE_DIRECT_BIND_INCOMPATIBLE_ADAPTER_ROUTE_PROVEN_NO_SAVE",
                "completed_utc": now(),
                "claim_limit": "Read-only material-interface and dependency-closure proof only; no water adapter was created, bound, rendered or visually accepted.",
            }
        )
        require(report["oasis"]["all_dependencies_loadable"], "Oasis dependency closure contains unloadable assets")
        require(not report["oasis"]["ppg_compatibility"]["direct_bind_compatible"], "Unexpected direct Oasis compatibility")
        require(report["ppg"]["ppg_compatibility"]["direct_bind_compatible"], "PPG master missing its own injected interface")
        require(not any(report["dirty_packages_after"].values()), "Dirty packages after R75")
        require(report["home_sha256_after"] == EXPECTED_HOME, "Home map changed")
        require(report["profile_sha256_after"] == EXPECTED_PROFILE, "ProfileV1 changed")
        write_once(report)
        unreal.log_warning("REDMMO_R75_PASS " + report["status"])
    except Exception as exc:
        report.update({"status": "FAIL_R75", "error": repr(exc), "completed_utc": now()})
        try:
            if not DIAG.exists():
                write_once(report)
        finally:
            unreal.log_error("REDMMO_R75_FAIL " + repr(exc))
    schedule_exit()


main()
