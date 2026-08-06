"""Apply the rollback-backed R37 SoStylized ground-texture successor."""

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
PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_SurfaceParent"
PARENT_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_SurfaceParent.uasset"
PARENT_SHA = "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768"
GRASS_FILES = {
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset": "91A0E7233A5922A921FB4CF8692B8631DBB7AEFE7D3D106FDB63C44DB412CE47",
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset": "19D1B594553977A6A7BA116271F103DCD4044F8F24C3E8B5CF8F596082A9F68E",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"): "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"): "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

BC = "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_BC"
ROUGHNESS = "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_R"
FLAT_NORMAL = "/Engine/EngineMaterials/DefaultNormal"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeSoStylizedGround_R37_20260805T1430Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_SoStylizedGround_R37_20260805T1430Z")
RESULT = DIAG / "apply_result.json"


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


def color(value):
    return [float(value.r), float(value.g), float(value.b), float(value.a)]


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


def main():
    report = {
        "schema": "redmmo.sostylized_ground.apply.r37.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "project_owned_serialized_mutation",
    }
    ok = False
    try:
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not ROLLBACK.exists(), "R37 no-clobber failed")
        for path, expected in (
            (PROJECT, PROJECT_SHA), (HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA),
            (FOLIAGE_FILE, FOLIAGE_SHA), (SURFACE_FILE, SURFACE_SHA), (PARENT_FILE, PARENT_SHA),
        ):
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        for path, expected in {**GRASS_FILES, **PROTECTED}.items():
            require(path.is_file() and sha256(path) == expected, "protected/grass drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        report["provider_gate_before"] = provider_gate()

        ROLLBACK.mkdir(parents=True, exist_ok=False)
        rollback_asset = ROLLBACK / SURFACE_FILE.name
        shutil.copy2(SURFACE_FILE, rollback_asset)
        require(sha256(rollback_asset) == SURFACE_SHA, "rollback copy mismatch")
        manifest = ROLLBACK / "pre_mutation_manifest.json"
        atomic_json(manifest, {
            "schema": "redmmo.rollback.r37.v1",
            "created_utc": now(),
            "source": str(SURFACE_FILE),
            "source_sha256": SURFACE_SHA,
            "rollback_copy": str(rollback_asset),
            "rollback_sha256": sha256(rollback_asset),
            "scope": "MI_PPG_ProfileV1_Surface only",
        })

        instance = unreal.load_asset(SURFACE)
        require(instance is not None and asset_path(instance.get_editor_property("parent")) == PARENT, "surface/parent drift")
        editing = unreal.MaterialEditingLibrary
        texture_names = {str(item) for item in editing.get_texture_parameter_names(instance)}
        scalar_names = {str(item) for item in editing.get_scalar_parameter_names(instance)}
        vector_names = {str(item) for item in editing.get_vector_parameter_names(instance)}
        required_textures = {"R10L_StylizedGrass_BC", "R10L_StylizedGrass_N", "R10L_StylizedGrass_ORM"}
        required_scalars = {"R10L_NormalAmount", "R10L_GroundSpecular", "R10L_GroundUVScale"}
        required_vectors = {"R10L_GroundTintA", "R10L_GroundTintB"}
        require(required_textures <= texture_names, "texture controls missing")
        require(required_scalars <= scalar_names, "scalar controls missing")
        require(required_vectors <= vector_names, "vector controls missing")

        texture_targets = {
            "R10L_StylizedGrass_BC": unreal.load_asset(BC),
            "R10L_StylizedGrass_N": unreal.load_asset(FLAT_NORMAL),
            "R10L_StylizedGrass_ORM": unreal.load_asset(ROUGHNESS),
        }
        require(all(texture_targets.values()), "one or more texture targets failed to load")
        before = {"textures": {}, "scalars": {}, "vectors": {}}
        after = {"textures": {}, "scalars": {}, "vectors": {}}
        for name, target in texture_targets.items():
            before["textures"][name] = asset_path(editing.get_material_instance_texture_parameter_value(instance, name))
            editing.set_material_instance_texture_parameter_value(instance, name, target)
            after["textures"][name] = asset_path(editing.get_material_instance_texture_parameter_value(instance, name))
            require(after["textures"][name] == asset_path(target), "texture postcondition failed: " + name)
        scalar_targets = {"R10L_NormalAmount": 0.0, "R10L_GroundSpecular": 0.02, "R10L_GroundUVScale": 12.0}
        for name, target in scalar_targets.items():
            before["scalars"][name] = float(editing.get_material_instance_scalar_parameter_value(instance, name))
            editing.set_material_instance_scalar_parameter_value(instance, name, target)
            after["scalars"][name] = float(editing.get_material_instance_scalar_parameter_value(instance, name))
            require(abs(after["scalars"][name] - target) <= 0.0001, "scalar postcondition failed: " + name)
        neutral = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)
        for name in sorted(required_vectors):
            before["vectors"][name] = color(editing.get_material_instance_vector_parameter_value(instance, name))
            editing.set_material_instance_vector_parameter_value(instance, name, neutral)
            after["vectors"][name] = color(editing.get_material_instance_vector_parameter_value(instance, name))
            require(max(abs(value - 1.0) for value in after["vectors"][name]) <= 0.0001, "vector postcondition failed: " + name)

        editing.update_material_instance(instance)
        require(unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False), "surface save failed")
        post_hash = sha256(SURFACE_FILE)
        require(post_hash != SURFACE_SHA, "surface serialized hash did not change")
        require(dirty_packages() == {"content": [], "maps": []}, "surface save left dirty packages")
        for path, expected in ((HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA), (FOLIAGE_FILE, FOLIAGE_SHA), (PARENT_FILE, PARENT_SHA)):
            require(sha256(path) == expected, "unrelated project asset drift: " + str(path))
        for path, expected in {**GRASS_FILES, **PROTECTED}.items():
            require(sha256(path) == expected, "protected/grass post-drift: " + str(path))
        report.update({
            "status": "PASS_R37_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_AND_D3D12_VISUAL",
            "completed_utc": now(),
            "surface": SURFACE,
            "surface_sha256_before": SURFACE_SHA,
            "surface_sha256_after": post_hash,
            "material_parent": PARENT,
            "changes": {"before": before, "after": after},
            "rollback": {"directory": str(ROLLBACK), "asset": str(rollback_asset), "manifest": str(manifest)},
            "provider_gate_after": provider_gate(),
            "claim_limit": "Only the project-owned active PPG surface material instance changed; map, seed, topology, foliage placement, grass assets, water, spawn, and gameplay were not changed.",
        })
        DIAG.mkdir(parents=True, exist_ok=False)
        atomic_json(RESULT, report)
        unreal.log("REDMMO_R37_APPLY_PASS")
        ok = True
    except Exception as exc:
        report.update({"status": "FAIL", "completed_utc": now(), "error": str(exc), "traceback": traceback.format_exc()})
        if not RESULT.exists():
            DIAG.mkdir(parents=True, exist_ok=True)
            atomic_json(RESULT, report)
        unreal.log_error("REDMMO_R37_APPLY_FAIL " + str(exc))
    finally:
        schedule_exit(3.0 if ok else 2.0)


main()
