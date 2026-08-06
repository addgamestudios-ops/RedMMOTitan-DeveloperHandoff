"""Read-only R36 audit of the SoStylized painted-grass material closure."""

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

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_SoStylizedGrassClosure_R36B_20260805T1425Z")
RESULT = DIAG / "closure_audit.json"
EXPORT = DIAG / "exports"
TEXTURES = [
    "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_BC",
    "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_R",
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


def closure(registry, root, cap=128):
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
            if value.startswith("/Game/SoStylized/") and value not in seen:
                pending.append(value)
    return sorted(seen)


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


def material_record(obj, registry):
    editing = unreal.MaterialEditingLibrary
    record = {
        "asset": asset_path(obj),
        "class": obj.get_class().get_name(),
        "dependency_closure": closure(registry, asset_path(obj)),
    }
    if obj.get_class().get_name() == "MaterialInstanceConstant":
        parent = obj.get_editor_property("parent")
        texture_parameters = {
            str(name): asset_path(editing.get_material_instance_texture_parameter_value(obj, name))
            for name in sorted(editing.get_texture_parameter_names(obj), key=str)
        }
        record["parent"] = asset_path(parent)
        record["texture_parameters"] = texture_parameters
        record["used_textures"] = sorted({value for value in texture_parameters.values() if value})
        if parent is not None and parent.get_class().get_name() == "Material":
            record["parent_used_textures"] = sorted({
                asset_path(item) for item in editing.get_used_textures(parent) if item is not None
            })
        record["scalar_parameters"] = {
            str(name): float(editing.get_material_instance_scalar_parameter_value(obj, name))
            for name in sorted(editing.get_scalar_parameter_names(obj), key=str)
        }
    else:
        record["used_textures"] = sorted({
            asset_path(item) for item in editing.get_used_textures(obj) if item is not None
        })
        record.update({
            "blend_mode": safe_property(obj, "blend_mode"),
            "shading_model": safe_property(obj, "shading_model"),
            "two_sided": safe_property(obj, "two_sided"),
            "material_domain": safe_property(obj, "material_domain"),
        })
    return record


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
        "schema": "redmmo.sostylized_grass_closure.read_only.r36.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "editor_automation_read_only_plus_diagnostic_texture_exports",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        require(not RESULT.exists() and not DIAG.exists(), "R36 no-clobber failed")
        require(not dirty_packages(), "Dirty packages before audit")
        report["provider_gate_before"] = provider_gate()
        for path, expected_hash in EXPECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Protected/current hash drift: " + str(path))

        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        textures = []
        material_paths = set()
        for path in TEXTURES:
            texture = unreal.EditorAssetLibrary.load_asset(path)
            require(texture is not None and texture.get_class().get_name() == "Texture2D", "Texture missing: " + path)
            package = package_file(path)
            require(package.is_file(), "Texture package file missing: " + path)
            refs = sorted({
                str(item) for item in unreal.EditorAssetLibrary.find_package_referencers_for_asset(path, False)
                if str(item).startswith("/Game/SoStylized/")
            })
            material_paths.update(refs)
            output = EXPORT / (path.rsplit("/", 1)[-1] + ".png")
            textures.append({
                "asset": path,
                "class": texture.get_class().get_name(),
                "package_sha256": sha256(package),
                "srgb": safe_property(texture, "srgb"),
                "compression_settings": safe_property(texture, "compression_settings"),
                "lod_group": safe_property(texture, "lod_group"),
                "virtual_texture_streaming": safe_property(texture, "virtual_texture_streaming"),
                "referencers": refs,
                "diagnostic_export": export_texture(texture, output),
            })

        material_records = []
        ignored_referencers = []
        for package_path in sorted(material_paths):
            data = registry.get_assets_by_package_name(unreal.Name(package_path), True)
            loaded = False
            for item in data:
                obj = item.get_asset()
                if obj is None:
                    continue
                class_name = obj.get_class().get_name()
                if class_name in ("Material", "MaterialInstanceConstant"):
                    material_records.append(material_record(obj, registry))
                    loaded = True
            if not loaded:
                ignored_referencers.append(package_path)

        report.update({
            "status": "PASS_READ_ONLY_SOSTYLIZED_CLOSURE_EXPORTED",
            "textures": textures,
            "material_records": material_records,
            "ignored_nonmaterial_referencers": ignored_referencers,
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
        unreal.log("REDMMO_SOSTYLIZED_GRASS_R36 " + report["status"])
        schedule_exit()


main()
