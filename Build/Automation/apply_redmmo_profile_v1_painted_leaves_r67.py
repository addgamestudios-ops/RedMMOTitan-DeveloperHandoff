"""Create and bind the project-owned R67 denser painted-leaf PPG surface.

The existing project-owned surface instance remains byte-identical. R67 is a
new material-instance branch using the verified SoStylized painted grass color
and roughness textures, flat normal, and UV scale 24 so the painted clutter is
half the prior R62 world size. Only ProfileV1.planet_material is rebound.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
HOME_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
SOURCE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\MI_PPG_ProfileV1_Surface.uasset"
R66_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_NoPalms_R66.uasset"
BC_FILE = PROJECT.parent / r"Content\SoStylized\Environment\Landscape\Textures\T_Grass1_BC.uasset"
ROUGHNESS_FILE = PROJECT.parent / r"Content\SoStylized\Environment\Landscape\Textures\T_Grass1_R.uasset"
TARGET_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_PaintedLeaves_R67.uasset"
PROTECTED_TEST = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap")
PROTECTED_FUSED = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap")
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1PaintedLeaves_R67_20260805T2202Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1PaintedLeaves_R67_20260805T2202Z\Apply")
RESULT = DIAG / "apply_result.json"

PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
SOURCE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/MI_PPG_ProfileV1_Surface"
TARGET = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/MI_PPG_ProfileV1_PaintedLeaves_R67"
R66 = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_NoPalms_R66"
BC = "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_BC"
ROUGHNESS = "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_R"
FLAT_NORMAL = "/Engine/EngineMaterials/DefaultNormal"

EXPECTED = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "4D22E5BD8DC106061BC3EF086BB95FA85AA570A4BAD66325E002135E1C7AC96F",
    SOURCE_FILE: "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66",
    R66_FILE: "C0EE6CB0A2D9D679D1FB4D64747555D55A5AF18ABED4AEC2666A1D5BECDA97DC",
    BC_FILE: "A79C24EA6A1284E8E190CF46FF2349B9117B3A930A5C506C2D3764057890CF71",
    ROUGHNESS_FILE: "D0DF945E92DAE229AC684350D4C20FAD9783FE388C839BD14602A5277A445069",
    PROTECTED_TEST: "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    PROTECTED_FUSED: "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
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


def normalized(value):
    return str(value).replace("_", "").replace(" ", "").lower()


def field(value, wanted):
    values = value.to_dict()
    target = normalized(wanted)
    matches = [item for key, item in values.items() if normalized(key) in (target, "b" + target)]
    require(len(matches) == 1, "missing reflected field " + wanted)
    return matches[0]


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


def load(path, class_name):
    value = unreal.EditorAssetLibrary.load_asset(path)
    require(value is not None and value.get_class().get_name() == class_name, "load failed: " + path)
    return value


def verify_r66(profile):
    require(int(profile.get_editor_property("generation_seed")) == 1337, "ProfileV1 seed drift")
    bindings = []
    for biome in list(profile.get_editor_property("biome_data")):
        bindings.append({"name": str(field(biome, "name")), "foliage_data": asset_path(field(biome, "foliage_data"))})
    require([item["name"] for item in bindings if item["foliage_data"] == R66] == ["Craters", "Hills", "Mountains"], "R66 binding drift")
    return bindings


def main():
    report = {
        "schema": "redmmo.profile_v1_painted_leaves.apply.r67.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
        "rollback": str(ROLLBACK),
        "map_loaded": False,
        "map_saved": False,
        "generation_called": False,
    }
    target_created = False
    profile_saved = False
    try:
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists(), "R67 result no-clobber failed")
        require(not TARGET_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(TARGET), "R67 target already exists")
        require(ROLLBACK.is_dir() and (ROLLBACK / "manifest.json").is_file(), "rollback missing")
        for path, expected in EXPECTED.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        for path in (PROFILE_FILE, SOURCE_FILE, R66_FILE, HOME_FILE):
            copy = ROLLBACK / path.name
            require(copy.is_file() and sha256(copy) == EXPECTED[path], "rollback preimage mismatch: " + path.name)
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        report["provider_gate_before"] = provider_gate()
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-nullrhi" in command and "-renderoffscreen" in command, "apply renderer gate failed")

        profile = load(PROFILE, "PlanetData")
        bindings = verify_r66(profile)
        require(asset_path(profile.get_editor_property("planet_material")) == SOURCE, "source planet material binding drift")
        source = load(SOURCE, "MaterialInstanceConstant")
        source_parent = asset_path(source.get_editor_property("parent"))

        target = unreal.EditorAssetLibrary.duplicate_asset(SOURCE, TARGET)
        require(target is not None and target.get_class().get_name() == "MaterialInstanceConstant", "R67 duplicate failed")
        target_created = True
        require(asset_path(target.get_editor_property("parent")) == source_parent, "R67 parent drift")
        editing = unreal.MaterialEditingLibrary
        required_textures = {"R10L_StylizedGrass_BC", "R10L_StylizedGrass_N", "R10L_StylizedGrass_ORM"}
        required_scalars = {"R10L_NormalAmount", "R10L_GroundSpecular", "R10L_GroundUVScale"}
        required_vectors = {"R10L_GroundTintA", "R10L_GroundTintB"}
        require(required_textures <= {str(item) for item in editing.get_texture_parameter_names(target)}, "texture controls missing")
        require(required_scalars <= {str(item) for item in editing.get_scalar_parameter_names(target)}, "scalar controls missing")
        require(required_vectors <= {str(item) for item in editing.get_vector_parameter_names(target)}, "vector controls missing")
        texture_targets = {
            "R10L_StylizedGrass_BC": load(BC, "Texture2D"),
            "R10L_StylizedGrass_N": load(FLAT_NORMAL, "Texture2D"),
            "R10L_StylizedGrass_ORM": load(ROUGHNESS, "Texture2D"),
        }
        for name, value in texture_targets.items():
            editing.set_material_instance_texture_parameter_value(target, name, value)
            require(asset_path(editing.get_material_instance_texture_parameter_value(target, name)) == asset_path(value), "texture write failed: " + name)
        for name, value in {"R10L_NormalAmount": 0.0, "R10L_GroundSpecular": 0.02, "R10L_GroundUVScale": 24.0}.items():
            editing.set_material_instance_scalar_parameter_value(target, name, value)
            require(abs(float(editing.get_material_instance_scalar_parameter_value(target, name)) - value) <= 0.0001, "scalar write failed: " + name)
        neutral = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)
        for name in required_vectors:
            editing.set_material_instance_vector_parameter_value(target, name, neutral)
        editing.update_material_instance(target)
        require(unreal.EditorAssetLibrary.save_loaded_asset(target, only_if_is_dirty=False), "R67 material save failed")

        profile.set_editor_property("planet_material", target)
        require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "ProfileV1 save failed")
        profile_saved = True
        require(dirty_packages() == {"content": [], "maps": []}, "dirty packages after save")

        reloaded_profile = load(PROFILE, "PlanetData")
        require(asset_path(reloaded_profile.get_editor_property("planet_material")) == TARGET, "R67 profile binding did not persist")
        verify_r66(reloaded_profile)
        require(TARGET_FILE.is_file(), "R67 package missing")
        for path, expected in EXPECTED.items():
            if path != PROFILE_FILE:
                require(sha256(path) == expected, "unrelated post-save drift: " + str(path))
        report.update({
            "status": "PASS_R67_PAINTED_LEAVES_BOUND_PENDING_FRESH_RELOAD",
            "completed_utc": now(),
            "target_material": TARGET,
            "target_sha256": sha256(TARGET_FILE),
            "profile_sha256_before": EXPECTED[PROFILE_FILE],
            "profile_sha256_after": sha256(PROFILE_FILE),
            "source_surface_sha256_before_after": sha256(SOURCE_FILE),
            "home_map_sha256_before_after": sha256(HOME_FILE),
            "seed": 1337,
            "r66_bindings": bindings,
            "parameters": {
                "base_color": BC,
                "roughness": ROUGHNESS,
                "normal": FLAT_NORMAL,
                "uv_scale": 24.0,
                "normal_amount": 0.0,
                "specular": 0.02,
                "tints": [1.0, 1.0, 1.0, 1.0],
            },
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Serialized R67 project-owned material branch and ProfileV1 planet-material rebind only; fresh reload, MapCheck, runtime census and D3D12 visual review remain pending.",
        })
        atomic_json(RESULT, report)
        unreal.log("REDMMO_R67_APPLY_PASS")
    except Exception as error:
        rollback = {"attempted": True, "profile_restored": False, "target_deleted": False}
        try:
            if profile_saved:
                profile = load(PROFILE, "PlanetData")
                profile.set_editor_property("planet_material", load(SOURCE, "MaterialInstanceConstant"))
                require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "rollback ProfileV1 save failed")
            rollback["profile_restored"] = sha256(PROFILE_FILE) == EXPECTED[PROFILE_FILE]
            if target_created or unreal.EditorAssetLibrary.does_asset_exist(TARGET):
                rollback["target_deleted"] = bool(unreal.EditorAssetLibrary.delete_asset(TARGET))
            else:
                rollback["target_deleted"] = not TARGET_FILE.exists()
        except Exception as rollback_error:
            rollback["error"] = str(rollback_error)
        report.update({
            "status": "FAIL_ROLLED_BACK" if rollback.get("profile_restored") and rollback.get("target_deleted") else "FAIL_ROLLBACK_INCOMPLETE",
            "completed_utc": now(),
            "error": str(error),
            "traceback": traceback.format_exc(),
            "rollback_result": rollback,
        })
        if not RESULT.exists():
            atomic_json(RESULT, report)
        unreal.log_error("REDMMO_R67_APPLY_FAIL " + str(error))
    finally:
        unreal.SystemLibrary.quit_editor()


main()
