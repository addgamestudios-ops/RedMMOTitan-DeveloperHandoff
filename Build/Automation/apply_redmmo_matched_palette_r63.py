"""Apply one transient, rollback-backed R63 ground/grass palette candidate."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
PROJECT_SHA = "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F"
HOME_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HOME_SHA = "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3"
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
PROFILE_SHA = "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970"
FOLIAGE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
FOLIAGE_SHA = "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8"
SURFACE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/MI_PPG_ProfileV1_Surface"
SURFACE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\MI_PPG_ProfileV1_Surface.uasset"
SURFACE_SHA = "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66"
SURFACE_PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_SurfaceParent"
SURFACE_PARENT_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_SurfaceParent.uasset"
SURFACE_PARENT_SHA = "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768"
R32_PARENT = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R32/Materials/M_GrassChunks_PPGReadable_R32"
R32_PARENT_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R32\Materials\M_GrassChunks_PPGReadable_R32.uasset"
R32_PARENT_SHA = "2BD2B8DD41C611CF1250F1A39C40D3B4A7C47B5EB71ECD1497732546B80F0210"
GRASS = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_B_R10N",
]
GRASS_FILES = [
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset",
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset",
]
GRASS_SHAS = [
    "91A0E7233A5922A921FB4CF8692B8631DBB7AEFE7D3D106FDB63C44DB412CE47",
    "19D1B594553977A6A7BA116271F103DCD4044F8F24C3E8B5CF8F596082A9F68E",
]
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"): "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"): "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
BC = "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_BC"
ROUGHNESS = "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_R"
FLAT_NORMAL = "/Engine/EngineMaterials/DefaultNormal"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeMatchedPalette_R63_20260805T2112Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_MatchedPalette_R63_20260805T2112Z\Apply")
RESULT = DIAG / "apply_result.json"

GROUND_TINTS = {
    "R10L_GroundTintA": unreal.LinearColor(0.72, 0.85, 0.58, 1.0),
    "R10L_GroundTintB": unreal.LinearColor(0.48, 0.66, 0.34, 1.0),
}
GRASS_COLORS = [
    unreal.LinearColor(0.030, 0.105, 0.015, 1.0),
    unreal.LinearColor(0.038, 0.135, 0.020, 1.0),
]
GRASS_HIGHLIGHTS = [
    unreal.LinearColor(0.065, 0.155, 0.030, 1.0),
    unreal.LinearColor(0.085, 0.200, 0.040, 1.0),
]
GRASS_SCALARS = {
    "GrassColor_Intensity": 0.74,
    "GrassColor_Contrast": 0.94,
    "GrassColor_Saturation": -0.10,
    "GrassColor_MinValue": 0.66,
    "GrassColor_MaxValue": 0.88,
}


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


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def asset_path(value):
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def rgba(value):
    return [float(value.r), float(value.g), float(value.b), float(value.a)]


def dirty_packages():
    return {
        "content": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}),
        "maps": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}),
    }


def provider_gate():
    state = {}
    for port in (11111, 5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            state[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(state.values()), "provider listener active: " + repr(state))
    return state


def schedule_exit(delay):
    started = time.monotonic()
    state = {"handle": None}

    def tick(_delta):
        if time.monotonic() - started < delay:
            return
        try:
            unreal.unregister_slate_post_tick_callback(state["handle"])
        except Exception:
            pass
        unreal.SystemLibrary.quit_editor()

    state["handle"] = unreal.register_slate_post_tick_callback(tick)


def set_vector(editing, instance, name, target, record):
    before = editing.get_material_instance_vector_parameter_value(instance, name)
    editing.set_material_instance_vector_parameter_value(instance, name, target)
    after = editing.get_material_instance_vector_parameter_value(instance, name)
    require(max(abs(a - b) for a, b in zip(rgba(after), rgba(target))) <= 0.0001, "vector postcondition failed: " + name)
    record[name] = {"before": rgba(before), "after": rgba(after)}


def main():
    report = {
        "schema": "redmmo.matched_palette.apply.r63.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "project_owned_serialized_mutation",
    }
    try:
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not ROLLBACK.exists(), "R63 no-clobber failed")
        for path, expected in (
            (PROJECT, PROJECT_SHA), (HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA),
            (FOLIAGE_FILE, FOLIAGE_SHA), (SURFACE_FILE, SURFACE_SHA),
            (SURFACE_PARENT_FILE, SURFACE_PARENT_SHA), (R32_PARENT_FILE, R32_PARENT_SHA),
        ):
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        for path, expected in zip(GRASS_FILES, GRASS_SHAS):
            require(path.is_file() and sha256(path) == expected, "grass input drift: " + str(path))
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "protected drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        report["provider_gate_before"] = provider_gate()

        ROLLBACK.mkdir(parents=True, exist_ok=False)
        rollback_assets = []
        for source in [SURFACE_FILE, *GRASS_FILES]:
            target = ROLLBACK / source.name
            shutil.copy2(source, target)
            require(sha256(target) == sha256(source), "rollback copy mismatch: " + str(source))
            rollback_assets.append({"source": str(source), "source_sha256": sha256(source), "copy": str(target), "copy_sha256": sha256(target)})
        manifest = ROLLBACK / "pre_mutation_manifest.json"
        atomic_json(manifest, {
            "schema": "redmmo.rollback.r63.v1",
            "created_utc": now(),
            "scope": "surface MI plus two approved grass MIs only",
            "assets": rollback_assets,
        })

        editing = unreal.MaterialEditingLibrary
        surface = unreal.load_asset(SURFACE)
        require(surface is not None and asset_path(surface.get_editor_property("parent")) == SURFACE_PARENT, "surface/parent drift")
        surface_record = {"textures": {}, "scalars": {}, "vectors": {}}
        texture_targets = {
            "R10L_StylizedGrass_BC": unreal.load_asset(BC),
            "R10L_StylizedGrass_N": unreal.load_asset(FLAT_NORMAL),
            "R10L_StylizedGrass_ORM": unreal.load_asset(ROUGHNESS),
        }
        require(all(texture_targets.values()), "ground texture closure failed to load")
        for name, target in texture_targets.items():
            surface_record["textures"][name] = {"before": asset_path(editing.get_material_instance_texture_parameter_value(surface, name)), "after": asset_path(target)}
            editing.set_material_instance_texture_parameter_value(surface, name, target)
            require(asset_path(editing.get_material_instance_texture_parameter_value(surface, name)) == asset_path(target), "texture postcondition failed: " + name)
        for name, target in {"R10L_NormalAmount": 0.0, "R10L_GroundSpecular": 0.02, "R10L_GroundUVScale": 12.0}.items():
            before = float(editing.get_material_instance_scalar_parameter_value(surface, name))
            editing.set_material_instance_scalar_parameter_value(surface, name, target)
            after = float(editing.get_material_instance_scalar_parameter_value(surface, name))
            require(abs(after - target) <= 0.0001, "surface scalar postcondition failed: " + name)
            surface_record["scalars"][name] = {"before": before, "after": after}
        for name, target in GROUND_TINTS.items():
            set_vector(editing, surface, name, target, surface_record["vectors"])
        editing.update_material_instance(surface)
        require(unreal.EditorAssetLibrary.save_loaded_asset(surface, only_if_is_dirty=False), "surface save failed")

        grass_records = []
        for index, package in enumerate(GRASS):
            instance = unreal.load_asset(package)
            require(instance is not None and asset_path(instance.get_editor_property("parent")) == R32_PARENT, "grass/parent drift: " + package)
            scalar_names = {str(item) for item in editing.get_scalar_parameter_names(instance)}
            vector_names = {str(item) for item in editing.get_vector_parameter_names(instance)}
            require(set(GRASS_SCALARS) <= scalar_names, "grass scalar controls missing: " + package)
            require({"GrassColor_01", "GrassHighlights_Color"} <= vector_names, "grass vector controls missing: " + package)
            record = {"asset": package, "scalars": {}, "vectors": {}}
            for name, target in GRASS_SCALARS.items():
                before = float(editing.get_material_instance_scalar_parameter_value(instance, name))
                editing.set_material_instance_scalar_parameter_value(instance, name, target)
                after = float(editing.get_material_instance_scalar_parameter_value(instance, name))
                require(abs(after - target) <= 0.0001, "grass scalar postcondition failed: " + name)
                record["scalars"][name] = {"before": before, "after": after}
            set_vector(editing, instance, "GrassColor_01", GRASS_COLORS[index], record["vectors"])
            set_vector(editing, instance, "GrassHighlights_Color", GRASS_HIGHLIGHTS[index], record["vectors"])
            editing.update_material_instance(instance)
            require(unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False), "grass save failed: " + package)
            grass_records.append(record)

        require(dirty_packages() == {"content": [], "maps": []}, "material saves left dirty packages")
        temporary_hashes = {str(path): sha256(path) for path in [SURFACE_FILE, *GRASS_FILES]}
        for path, expected in ((HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA), (FOLIAGE_FILE, FOLIAGE_SHA), (SURFACE_PARENT_FILE, SURFACE_PARENT_SHA), (R32_PARENT_FILE, R32_PARENT_SHA)):
            require(sha256(path) == expected, "unrelated project asset drift: " + str(path))
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "protected post-drift: " + str(path))
        require(all(temporary_hashes[str(path)] != expected for path, expected in zip([SURFACE_FILE, *GRASS_FILES], [SURFACE_SHA, *GRASS_SHAS])), "one or more material instances did not serialize")

        report.update({
            "status": "PASS_R63_TRANSIENT_PALETTE_SERIALIZED_PENDING_D3D12_REVIEW",
            "completed_utc": now(),
            "surface": surface_record,
            "grass": grass_records,
            "temporary_hashes": temporary_hashes,
            "rollback": {"directory": str(ROLLBACK), "manifest": str(manifest), "assets": rollback_assets},
            "provider_gate_after": provider_gate(),
            "claim_limit": "Three project-owned material instances only; density, height, meshes, placement, seed, topology, map, gameplay and vendor assets unchanged.",
        })
        atomic_json(RESULT, report)
        unreal.log("REDMMO_R63_APPLY_PASS")
    except Exception as error:
        report.update({"status": "FAIL", "error": str(error), "traceback": traceback.format_exc(), "completed_utc": now()})
        if not RESULT.exists():
            atomic_json(RESULT, report)
        unreal.log_error("REDMMO_R63_APPLY_FAIL " + str(error))
    schedule_exit(2.0)


main()
