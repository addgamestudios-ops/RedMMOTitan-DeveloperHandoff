"""Create and bind the project-owned R66 no-palms PPG foliage successor.

The exact R29 foliage asset remains immutable.  R66 duplicates it, changes only
tree entry 0 density from 10 to zero, and rebinds the existing Craters, Hills
and Mountains ProfileV1 biome slots.  No map is loaded or saved here; the
separate fresh D3D12 verifier owns regeneration, MapCheck and visual proof.
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
R29_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
R66_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_NoPalms_R66.uasset"
PROTECTED_TEST = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap")
PROTECTED_FUSED = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap")
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1NoPalms_R66_20260805T2144Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1NoPalms_R66_20260805T2144Z\Apply")
RESULT = DIAG / "apply_result.json"

PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
R29 = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassEligible_R29"
R66 = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_NoPalms_R66"
PALM = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R09/Meshes/SM_Tree_OasisPalm01_R09"

EXPECTED = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970",
    R29_FILE: "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8",
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


def find_key(values, wanted):
    target = normalized(wanted)
    matches = [key for key in values if normalized(key) in (target, "b" + target)]
    require(len(matches) == 1, "missing reflected field " + wanted)
    return matches[0]


def stable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "get_path_name"):
        return asset_path(value)
    if isinstance(value, dict):
        return {str(key): stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [stable(item) for item in value]
    if hasattr(value, "to_dict"):
        return stable(value.to_dict())
    return str(value)


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


def mesh_bindings(entry):
    return [asset_path(item.get_editor_property("mesh")) for item in list(entry.get_editor_property("meshes"))]


def lod_mesh_bindings(entry):
    return [
        [asset_path(mesh) for mesh in list(lod.get_editor_property("meshes"))]
        for lod in list(entry.get_editor_property("lods"))
    ]


def main():
    active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
    report = {
        "schema": "redmmo.profile_v1_no_palms.apply.r66.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
        "rollback": str(ROLLBACK),
        "save_called": False,
        "map_loaded": False,
        "map_saved": False,
        "generation_called": False,
    }
    source_profile_values = None
    target_created = False
    profile_saved = False
    try:
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists(), "R66 result no-clobber failed")
        require(not R66_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(R66), "R66 target already exists")
        require(ROLLBACK.is_dir(), "rollback directory missing")
        for path, expected in EXPECTED.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        require((ROLLBACK / PROFILE_FILE.name).is_file() and sha256(ROLLBACK / PROFILE_FILE.name) == EXPECTED[PROFILE_FILE], "profile rollback invalid")
        require((ROLLBACK / R29_FILE.name).is_file() and sha256(ROLLBACK / R29_FILE.name) == EXPECTED[R29_FILE], "R29 rollback invalid")
        require((ROLLBACK / HOME_FILE.name).is_file() and sha256(ROLLBACK / HOME_FILE.name) == EXPECTED[HOME_FILE], "home rollback invalid")
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        report["provider_gate_before"] = provider_gate()
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-nullrhi" in command and "-renderoffscreen" in command, "apply renderer gate failed")

        source = load(R29, "FoliageData")
        source_entries = list(source.get_editor_property("foliage_list"))
        require(len(source_entries) == 3, "R29 foliage entry count drift")
        require(mesh_bindings(source_entries[0]) == [PALM], "R29 tree slot identity drift")
        require(abs(float(source_entries[0].get_editor_property("foliage_density")) - 10.0) <= 1.0e-6, "R29 tree density drift")
        require("green" in str(source_entries[0].get_editor_property("density_vertex_color_channel")).lower(), "R29 tree density channel drift")
        require(not bool(source_entries[0].get_editor_property("invert_density_vertex_color_mask")), "R29 tree mask inversion drift")
        source_signatures = [stable(item) for item in source_entries]

        target = unreal.EditorAssetLibrary.duplicate_asset(R29, R66)
        require(target is not None and target.get_class().get_name() == "FoliageData", "R66 duplicate failed")
        target_created = True
        entries = list(target.get_editor_property("foliage_list"))
        values = entries[0].to_dict()
        density_key = find_key(values, "foliage_density")
        require(abs(float(values[density_key]) - 10.0) <= 1.0e-6, "R66 pre-change tree density drift")
        values[density_key] = 0.0
        entries[0] = unreal.FoliageList(**values)
        target.set_editor_property("foliage_list", entries)
        require(unreal.EditorAssetLibrary.save_loaded_asset(target, only_if_is_dirty=False), "R66 foliage save failed")

        verified_target = load(R66, "FoliageData")
        target_entries = list(verified_target.get_editor_property("foliage_list"))
        require(len(target_entries) == 3, "R66 foliage entry count drift")
        require(abs(float(target_entries[0].get_editor_property("foliage_density"))) <= 1.0e-6, "R66 tree density did not persist as zero")
        require(mesh_bindings(target_entries[0]) == [PALM], "R66 tree mesh identity changed")
        require(lod_mesh_bindings(target_entries[0]) == lod_mesh_bindings(source_entries[0]), "R66 tree LOD mesh bindings changed")
        for index in (1, 2):
            require(stable(target_entries[index]) == source_signatures[index], "R66 non-tree entry changed: " + str(index))
        source_tree_without_density = source_entries[0].to_dict()
        target_tree_without_density = target_entries[0].to_dict()
        source_tree_without_density[find_key(source_tree_without_density, "foliage_density")] = 0.0
        require(stable(target_tree_without_density) == stable(source_tree_without_density), "R66 tree changed outside density")

        profile = load(PROFILE, "PlanetData")
        require(int(profile.get_editor_property("generation_seed")) == 1337, "ProfileV1 seed drift")
        source_profile_values = [item.to_dict() for item in list(profile.get_editor_property("biome_data"))]
        before_profile = stable(source_profile_values)
        changed = []
        rebound = []
        for values in source_profile_values:
            current = dict(values)
            name_key = find_key(current, "name")
            foliage_key = find_key(current, "foliage_data")
            name = str(current[name_key])
            if asset_path(current[foliage_key]) == R29:
                current[foliage_key] = verified_target
                changed.append(name)
            rebound.append(unreal.BiomeData(**current))
        require(changed == ["Craters", "Hills", "Mountains"], "unexpected rebound biomes: " + repr(changed))
        profile.set_editor_property("biome_data", rebound)
        require(int(profile.get_editor_property("generation_seed")) == 1337, "ProfileV1 seed changed")
        require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "ProfileV1 save failed")
        profile_saved = True
        require(dirty_packages() == {"content": [], "maps": []}, "dirty packages remain after R66 save")

        reloaded_profile = load(PROFILE, "PlanetData")
        after_values = [item.to_dict() for item in list(reloaded_profile.get_editor_property("biome_data"))]
        after_bindings = []
        for values in after_values:
            after_bindings.append({
                "name": str(values[find_key(values, "name")]),
                "foliage_data": asset_path(values[find_key(values, "foliage_data")]),
            })
        require([item["name"] for item in after_bindings if item["foliage_data"] == R66] == ["Craters", "Hills", "Mountains"], "R66 bindings did not persist")
        require(sha256(R29_FILE) == EXPECTED[R29_FILE], "R29 source changed")
        require(sha256(HOME_FILE) == EXPECTED[HOME_FILE], "home map changed")
        require(sha256(PROTECTED_TEST) == EXPECTED[PROTECTED_TEST] and sha256(PROTECTED_FUSED) == EXPECTED[PROTECTED_FUSED], "protected checkpoint changed")
        require(R66_FILE.is_file(), "R66 package missing")
        report.update({
            "status": "PASS_R66_NO_PALMS_SUCCESSOR_BOUND_PENDING_FRESH_RELOAD",
            "completed_utc": now(),
            "save_called": True,
            "source_foliage": R29,
            "source_foliage_sha256_before_after": sha256(R29_FILE),
            "target_foliage": R66,
            "target_foliage_sha256": sha256(R66_FILE),
            "profile_v1_sha256_after": sha256(PROFILE_FILE),
            "home_map_sha256_before_after": sha256(HOME_FILE),
            "changed_biomes": changed,
            "bindings_after": after_bindings,
            "tree_before": {"mesh": PALM, "density": 10.0},
            "tree_after": {"mesh": PALM, "density": 0.0},
            "grass_entry_unchanged": stable(target_entries[1]) == source_signatures[1],
            "rock_entry_unchanged": stable(target_entries[2]) == source_signatures[2],
            "provider_gate_after": provider_gate(),
            "dirty_packages_after": dirty_packages(),
            "claim_limit": "Serialized project-owned foliage successor and ProfileV1 rebind only; fresh reload, regeneration, MapCheck, runtime component census and pixels remain pending.",
        })
        atomic_json(RESULT, report)
        unreal.log("REDMMO_R66_APPLY_PASS")
    except Exception as error:
        rollback = {"attempted": True, "profile_restored": False, "target_deleted": False}
        try:
            if profile_saved and source_profile_values is not None:
                profile = load(PROFILE, "PlanetData")
                profile.set_editor_property("biome_data", [unreal.BiomeData(**values) for values in source_profile_values])
                require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "rollback ProfileV1 save failed")
                rollback["profile_restored"] = sha256(PROFILE_FILE) == EXPECTED[PROFILE_FILE]
            else:
                rollback["profile_restored"] = sha256(PROFILE_FILE) == EXPECTED[PROFILE_FILE]
            if target_created or unreal.EditorAssetLibrary.does_asset_exist(R66):
                rollback["target_deleted"] = bool(unreal.EditorAssetLibrary.delete_asset(R66))
            else:
                rollback["target_deleted"] = not R66_FILE.exists()
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
        unreal.log_error("REDMMO_R66_APPLY_FAIL " + str(error))
    finally:
        unreal.SystemLibrary.quit_editor()


main()
