"""Read-only inspection of the project-owned R10N grass material controls."""

from __future__ import annotations

import hashlib
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
OUT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_GrassMaterial_R32_20260805T1320Z\inspection.json")
MATERIALS = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_B_R10N",
]
SCALARS = [
    "GrassColor_Custom_Enable",
    "GrassColor_Effects_Enable",
    "GrassColor_FromLandscape_Amount",
    "GrassColor_Intensity",
    "GrassColor_Contrast",
    "GrassColor_Saturation",
    "GrassColor_MinValue",
    "GrassColor_MaxValue",
    "GrassEmissive_Intensity",
    "GrassHighlights_Amount",
    "GrassHighlights_Density",
    "GrassHighlights_Gradient_Contrast",
]
VECTORS = ["GrassColor_01", "GrassHighlights_Color", "GrassAO_Color"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def asset_path(value):
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def color(value):
    return [float(value.r), float(value.g), float(value.b), float(value.a)]


report = {
    "schema": "redmmo.grass_material.inspection.r32.v1",
    "captured_utc": datetime.now(timezone.utc).isoformat(),
    "status": "RUNNING",
    "material_editing_library_methods": sorted(
        name for name in dir(unreal.MaterialEditingLibrary)
        if "parameter" in name.lower() or "material_instance" in name.lower()
    ),
    "materials": [],
}

try:
    for package in MATERIALS:
        material = unreal.load_asset(package)
        if material is None:
            raise RuntimeError("material missing: " + package)
        base = material.get_base_material()
        file_path = PROJECT.parent / "Content" / Path(package.removeprefix("/Game/") + ".uasset")
        item = {
            "path": package,
            "file": str(file_path),
            "sha256": sha256(file_path),
            "parent": asset_path(material.get_editor_property("parent")),
            "base_material": asset_path(base),
            "base": {
                "blend_mode": str(base.get_editor_property("blend_mode")),
                "shading_model": str(base.get_editor_property("shading_model")),
                "two_sided": bool(base.get_editor_property("two_sided")),
                "opacity_mask_clip_value": float(base.get_editor_property("opacity_mask_clip_value")),
            },
            "scalars": {},
            "vectors": {},
        }
        for name in SCALARS:
            try:
                item["scalars"][name] = float(
                    unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(material, name)
                )
            except Exception as error:
                item["scalars"][name] = {"error": str(error)}
        for name in VECTORS:
            try:
                item["vectors"][name] = color(
                    unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(material, name)
                )
            except Exception as error:
                item["vectors"][name] = {"error": str(error)}
        report["materials"].append(item)
    report["status"] = "PASS_READ_ONLY"
except Exception as error:
    report.update({"status": "FAIL", "error": str(error), "traceback": traceback.format_exc()})

OUT.parent.mkdir(parents=True, exist_ok=True)
data = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
with OUT.open("xb") as stream:
    stream.write(data)
    stream.flush()
    os.fsync(stream.fileno())
unreal.SystemLibrary.quit_editor()
