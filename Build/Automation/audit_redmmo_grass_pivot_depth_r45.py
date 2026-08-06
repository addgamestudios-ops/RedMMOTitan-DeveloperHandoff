"""Read-only R45 audit of approved grass pivots and PPG surface-depth math.

Runs in one fresh provider-off D3D12 RedMMO editor without loading a map,
regenerating a planet, starting PIE, or saving a package.  It records the exact
approved mesh bounds, the persisted R29 foliage depth/alignment contract, and
the resulting radial base/top interval implied by installed PPG's placement
formula.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
R29_FOLIAGE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassEligible_R29"
R29_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
RESULT = Path(os.environ["REDMMO_R45_RESULT"])

VENDOR_MESH = "/Game/StylizedRocksPack_01/Common/GrassChunks/Meshes/SM_GrassChunk_01"
APPROVED_MESHES = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
]
APPROVED_MATERIALS = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_B_R10N",
]

EXPECTED = {
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970",
    R29_FILE: "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset":
        "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset":
        "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value) -> str | None:
    if value is None:
        return None
    path = str(value.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def load(path: str, expected_class: str):
    value = unreal.EditorAssetLibrary.load_asset(path)
    require(value is not None, "Missing asset: " + path)
    require(value.get_class().get_name() == expected_class, "Class drift: " + path)
    return value


def vec(value) -> list[float]:
    return [float(value.x), float(value.y), float(value.z)]


def dirty_packages() -> dict[str, list[str]]:
    return {
        "content": sorted(asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()),
        "maps": sorted(asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()),
    }


def provider_gate() -> dict[str, bool]:
    records = {}
    for port in (11111, 5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            records[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    return records


def atomic_json(path: Path, payload: dict) -> None:
    require(not path.exists() and not path.parent.exists(), "R45 output no-clobber failed")
    path.parent.mkdir(parents=True, exist_ok=False)
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def bounds_record(mesh) -> dict:
    bounds = mesh.get_bounds()
    origin = bounds.origin
    extent = bounds.box_extent
    minimum = unreal.Vector(origin.x - extent.x, origin.y - extent.y, origin.z - extent.z)
    maximum = unreal.Vector(origin.x + extent.x, origin.y + extent.y, origin.z + extent.z)
    height = float(maximum.z - minimum.z)
    return {
        "origin_cm": vec(origin),
        "box_extent_cm": vec(extent),
        "minimum_cm": vec(minimum),
        "maximum_cm": vec(maximum),
        "height_cm": height,
        "pivot_above_local_min_cm": float(-minimum.z),
        "pivot_z_fraction_from_base": float(-minimum.z / height) if height > 0.0 else None,
        "sphere_radius_cm": float(bounds.sphere_radius),
    }


def scalar(instance, name: str) -> float | None:
    try:
        return float(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(instance, name))
    except Exception:
        return None


def placement_interval(bounds: dict, depth: float, scale: float) -> dict:
    minimum_z = bounds["minimum_cm"][2]
    maximum_z = bounds["maximum_cm"][2]
    base = -depth + minimum_z * scale
    top = -depth + maximum_z * scale
    total = top - base
    visible = max(top, 0.0) - max(base, 0.0)
    return {
        "ppg_scale": scale,
        "radial_base_from_generated_surface_cm": base,
        "radial_top_from_generated_surface_cm": top,
        "static_mesh_height_above_generated_surface_cm": max(top, 0.0),
        "static_mesh_height_below_generated_surface_cm": max(-base, 0.0),
        "static_mesh_visible_height_fraction": visible / total if total > 0.0 else None,
    }


report = {
    "schema": "redmmo.grass_pivot_depth.audit.r45.v1",
    "started_utc": now(),
    "evidence_class": "fresh_editor_d3d12_read_only_automation",
}

try:
    active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
    require(active == PROJECT_FILE.resolve(strict=True), "Wrong active project")
    command = str(unreal.SystemLibrary.get_command_line()).lower()
    require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "Renderer gate failed")
    require(dirty_packages() == {"content": [], "maps": []}, "Editor started dirty")
    gate = provider_gate()
    require(all(gate.values()), "Provider listener active: " + str(gate))
    for path, expected in EXPECTED.items():
        require(path.is_file() and sha256(path) == expected, "Preflight hash drift: " + str(path))

    meshes = []
    for path in [VENDOR_MESH, *APPROVED_MESHES]:
        mesh = load(path, "StaticMesh")
        record = bounds_record(mesh)
        record.update({
            "asset": path,
            "nanite_enabled": bool(mesh.get_editor_property("nanite_settings").enabled),
            "material_slots": [asset_path(item.material_interface) for item in list(mesh.get_editor_property("static_materials"))],
        })
        meshes.append(record)

    material_controls = []
    for path in APPROVED_MATERIALS:
        instance = load(path, "MaterialInstanceConstant")
        material_controls.append({
            "asset": path,
            "parent": asset_path(instance.get_editor_property("parent")),
            "local_scale_multiply": scalar(instance, "LocalScale_Multiply"),
            "grass_local_z_scale_multiply": scalar(instance, "GrassLocalZ_ScaleMultiply"),
            "grass_highlights_amount": scalar(instance, "GrassHighlights_Amount"),
            "grass_highlights_density": scalar(instance, "GrassHighlights_Density"),
            "grass_highlights_gradient_contrast": scalar(instance, "GrassHighlights_Gradient_Contrast"),
        })

    foliage = load(R29_FOLIAGE, "FoliageData")
    grass_entries = []
    for index, entry in enumerate(list(foliage.get_editor_property("foliage_list"))):
        entry_meshes = [asset_path(item.get_editor_property("mesh")) for item in list(entry.get_editor_property("meshes"))]
        if entry_meshes != APPROVED_MESHES:
            continue
        scale = entry.get_editor_property("scale")
        grass_entries.append({
            "index": index,
            "meshes": entry_meshes,
            "depth_offset_cm": float(entry.get_editor_property("depth_offset")),
            "align_to_terrain": bool(entry.get_editor_property("align_to_terrain")),
            "scale_min": float(scale.get_editor_property("min")),
            "scale_max": float(scale.get_editor_property("max")),
            "density": float(entry.get_editor_property("foliage_density")),
        })
    require(len(grass_entries) == 1, "Expected one exact approved grass entry")
    contract = grass_entries[0]
    approved_bounds = meshes[1:]
    require(approved_bounds[0]["minimum_cm"] == approved_bounds[1]["minimum_cm"], "Approved mesh min bounds differ")
    require(approved_bounds[0]["maximum_cm"] == approved_bounds[1]["maximum_cm"], "Approved mesh max bounds differ")
    require(meshes[0]["minimum_cm"] == approved_bounds[0]["minimum_cm"], "Alias/vendor min bounds differ")
    require(meshes[0]["maximum_cm"] == approved_bounds[0]["maximum_cm"], "Alias/vendor max bounds differ")

    intervals = [
        placement_interval(approved_bounds[0], contract["depth_offset_cm"], contract["scale_min"]),
        placement_interval(approved_bounds[0], contract["depth_offset_cm"], contract["scale_max"]),
    ]
    base_at_min = intervals[0]["radial_base_from_generated_surface_cm"]
    top_at_min = intervals[0]["radial_top_from_generated_surface_cm"]
    findings = {
        "aliases_preserve_vendor_bounds": True,
        "pivot_is_inside_vertical_bounds": approved_bounds[0]["minimum_cm"][2] < 0.0 < approved_bounds[0]["maximum_cm"][2],
        "ppg_depth_moves_pivot_below_generated_surface": contract["depth_offset_cm"] > 0.0,
        "static_mesh_crosses_generated_surface_at_min_scale": base_at_min < 0.0 < top_at_min,
        "static_mesh_fully_below_generated_surface_at_min_scale": top_at_min <= 0.0,
    }
    report.update({
        "status": "PASS_READ_ONLY_PIVOT_DEPTH_AUDIT",
        "completed_utc": now(),
        "provider_ports_closed": gate,
        "map_loaded": False,
        "pie_started": False,
        "regeneration_called": False,
        "meshes": meshes,
        "material_controls": material_controls,
        "foliage_entry": contract,
        "installed_ppg_placement_contract": {
            "shader_expression": "LocalInstancePosition = LocalTerrainPosition - TerrainNormal * DepthOffset",
            "instance_up": "terrain normal when align_to_terrain; radial up otherwise",
            "depth_positive_direction": "below generated surface",
        },
        "static_mesh_radial_intervals": intervals,
        "findings": findings,
        "dirty_packages_after": dirty_packages(),
        "persistent_writes": False,
    })
    require(report["dirty_packages_after"] == {"content": [], "maps": []}, "Audit dirtied packages")
    report["hashes_after"] = {str(path): sha256(path) for path in EXPECTED}
    for path, expected in EXPECTED.items():
        require(report["hashes_after"][str(path)] == expected, "Audit changed file: " + str(path))
except Exception as error:
    report.update({"status": "FAIL", "completed_utc": now(), "error": str(error), "traceback": traceback.format_exc()})
finally:
    try:
        atomic_json(RESULT, report)
    finally:
        unreal.log("REDMMO_R45 " + report["status"])
        unreal.SystemLibrary.quit_editor()
