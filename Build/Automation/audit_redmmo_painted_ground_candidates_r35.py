"""Read-only R35 audit and diagnostic export of installed painted-ground candidates."""

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
PROFILE_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
SURFACE_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\MI_PPG_ProfileV1_Surface.uasset"
EXPECTED = {
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970",
    SURFACE_FILE: "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PaintedGroundCandidates_R35_20260805T1410Z")
RESULT = DIAG / "candidate_audit.json"
EXPORT = DIAG / "exports"

MATERIAL_INSTANCES = [
    "/Game/AlienJungle/Materials/Primary/MI_bushA_leafGround",
    "/Game/AlienJungle/Materials/Primary/MI_bushB_leafGround",
    "/Game/AlienJungle/Materials/Primary/MI_bushC_leafGround",
    "/Game/AlienJungle/Materials/Primary/MI_landscape",
]

TEXTURE_CANDIDATES = [
    "/Game/AlienJungle/Textures/T_bushAleaf_c",
    "/Game/AlienJungle/Textures/T_groundDirtA_c",
    "/Game/AlienJungle/Textures/T_groundMossA_c",
    "/Game/AlienJungle/Textures/T_groundRockMossA_c",
    "/Game/AlienJungle/Textures/T_groundRootMossA_c",
    "/Game/Zenscape_Island/Texture/Grass/T_Grass_Tile_SplatMap_C_02",
    "/Game/Zenscape_Savanna/Model/Grass/Grass/Textures/T_Grass_Tile_C",
    "/Game/Zenscape_Savanna/Model/Grass/Grass/Textures/T_Grass_Tile_SplatMap_01_C",
    "/Game/Zenscape_Savanna/Model/Grass/Grass/Textures/T_Grass_Tile_SplatMap_C_02",
    "/Game/Zenscape_Savanna/Model/Grass/Grass/Textures/T_Grass_Tile_SplatMap_C_03",
    "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_BC",
    "/Game/StylizedRocksPack_01/Common/TilingTextures/T_StylizedGrass_01_BC",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
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


def safe_property(obj, name):
    try:
        value = obj.get_editor_property(name)
        if isinstance(value, unreal.Object):
            return asset_path(value)
        if hasattr(value, "name"):
            return str(value)
        return value
    except Exception:
        return None


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def provider_gate():
    states = {}
    for port in (11111, 5353, 8000, 8765):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.15)
        try:
            states[str(port)] = sock.connect_ex(("127.0.0.1", port)) != 0
        finally:
            sock.close()
    require(all(states.values()), "Provider listener active")
    return states


def write_once(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def package_file(package_path):
    require(package_path.startswith("/Game/"), "Expected project package: " + package_path)
    return PROJECT / ("Content" + package_path.removeprefix("/Game").replace("/", os.sep) + ".uasset")


def closure(registry, root, cap=96):
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
            if value.startswith(("/Game/AlienJungle/", "/Game/Zenscape_Island/", "/Game/Zenscape_Savanna/", "/Game/SoStylized/", "/Game/StylizedRocksPack_01/")) and value not in seen:
                pending.append(value)
    return sorted(seen)


def material_record(instance, registry):
    editing = unreal.MaterialEditingLibrary
    textures = {}
    for raw_name in sorted(editing.get_texture_parameter_names(instance), key=str):
        value = editing.get_material_instance_texture_parameter_value(instance, raw_name)
        textures[str(raw_name)] = asset_path(value)
    scalars = {}
    for raw_name in sorted(editing.get_scalar_parameter_names(instance), key=str):
        scalars[str(raw_name)] = float(editing.get_material_instance_scalar_parameter_value(instance, raw_name))
    return {
        "asset": asset_path(instance),
        "class": instance.get_class().get_name(),
        "parent": asset_path(instance.get_editor_property("parent")),
        "texture_parameters": textures,
        "scalar_parameters": scalars,
        "dependency_closure": closure(registry, asset_path(instance)),
    }


def export_texture(texture, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    task = unreal.AssetExportTask()
    task.set_editor_property("object", texture)
    task.set_editor_property("filename", str(output))
    task.set_editor_property("automated", True)
    task.set_editor_property("prompt", False)
    task.set_editor_property("replace_identical", False)
    task.set_editor_property("use_file_archive", False)
    task.set_editor_property("write_empty_files", False)
    task.set_editor_property("exporter", unreal.TextureExporterPNG())
    ok = bool(unreal.Exporter.run_asset_export_task(task))
    require(ok and output.is_file() and output.stat().st_size > 0, "Texture export failed: " + asset_path(texture))
    return {"path": str(output), "bytes": output.stat().st_size, "sha256": sha256(output)}


def texture_record(texture, registry):
    path = asset_path(texture)
    source_file = package_file(path)
    output = EXPORT / (path.rsplit("/", 1)[-1] + ".png")
    require(source_file.is_file(), "Texture package file missing: " + path)
    return {
        "asset": path,
        "class": texture.get_class().get_name(),
        "package_sha256": sha256(source_file),
        "size_x": int(texture.blueprint_get_size_x()),
        "size_y": int(texture.blueprint_get_size_y()),
        "srgb": safe_property(texture, "srgb"),
        "compression_settings": safe_property(texture, "compression_settings"),
        "lod_group": safe_property(texture, "lod_group"),
        "virtual_texture_streaming": safe_property(texture, "virtual_texture_streaming"),
        "dependency_closure": closure(registry, path),
        "diagnostic_export": export_texture(texture, output),
    }


_EXIT = {"handle": None}


def schedule_exit(delay=3.0):
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
        "schema": "redmmo.painted_ground_candidates.read_only.r35.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "editor_automation_read_only_plus_diagnostic_texture_exports",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        require(not RESULT.exists() and not DIAG.exists(), "R35 no-clobber failed")
        require(not dirty_packages(), "Dirty packages before audit")
        report["provider_gate_before"] = provider_gate()
        for path, expected_hash in EXPECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Protected/current hash drift: " + str(path))

        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        materials = []
        for path in MATERIAL_INSTANCES:
            asset = unreal.EditorAssetLibrary.load_asset(path)
            require(asset is not None and asset.get_class().get_name() == "MaterialInstanceConstant", "Material instance missing: " + path)
            materials.append(material_record(asset, registry))

        textures = []
        for path in TEXTURE_CANDIDATES:
            asset = unreal.EditorAssetLibrary.load_asset(path)
            require(asset is not None and asset.get_class().get_name() == "Texture2D", "Texture missing: " + path)
            textures.append(texture_record(asset, registry))

        report.update({
            "status": "PASS_READ_ONLY_CANDIDATES_EXPORTED",
            "material_instances": materials,
            "texture_candidates": textures,
            "candidate_count": len(textures),
            "save_called": False,
            "map_loaded": False,
            "regeneration_called": False,
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "protected_hashes_before_after": {str(path): sha256(path) for path in EXPECTED},
        })
        require(not report["dirty_packages_after"], "Audit dirtied packages")
        for path, expected_hash in EXPECTED.items():
            require(sha256(path) == expected_hash, "Audit changed package: " + str(path))
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_once(RESULT, report)
        unreal.log("REDMMO_PAINTED_GROUND_R35 " + report["status"])
        schedule_exit()


main()
