"""Create and bind one project-owned ProfileV1 grass depth-only successor."""

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
PROJECT_SHA = "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F"
HOME_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HOME_SHA = "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3"
PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
PROFILE_SHA = "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970"
SOURCE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassEligible_R29"
SOURCE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
SOURCE_SHA = "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8"
TARGET = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassDepth_R46"
TARGET_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassDepth_R46.uasset"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1GrassDepth_R46_20260805T1650Z")
ROLLBACK_COPY = ROLLBACK / "DA_PPG_ProfileV1_PlanetData.pre_r46.uasset"
ROLLBACK_MANIFEST = ROLLBACK / "manifest.json"
RESULT = Path(os.environ["REDMMO_R46_APPLY_RESULT"])
OLD_DEPTH = 20.0
NEW_DEPTH = -50.0

GRASS_MESHES = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
]
PRESERVED = {
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset":
        "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset":
        "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
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


def normalized_key(name):
    return str(name).replace("_", "").replace(" ", "").lower()


def find_key(values, wanted):
    wanted = normalized_key(wanted)
    matches = [key for key in values if normalized_key(key) == wanted]
    require(len(matches) == 1, "expected exactly one {} field".format(wanted))
    return matches[0]


def stable_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {normalized_key(k): stable_value(v) for k, v in sorted(value.items(), key=lambda pair: normalized_key(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [stable_value(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return stable_value(to_dict())
    get_path_name = getattr(value, "get_path_name", None)
    if callable(get_path_name):
        return asset_path(value)
    return str(value)


def signature(value, exclude=()):
    excluded = {normalized_key(item) for item in exclude}
    return {
        normalized_key(key): stable_value(item)
        for key, item in value.to_dict().items()
        if normalized_key(key) not in excluded
    }


def mesh_bindings(entry):
    return [asset_path(item.get_editor_property("mesh")) for item in entry.get_editor_property("meshes")]


def dirty_packages():
    content = [asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    maps = [asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    return {"content": sorted(set(content)), "maps": sorted(set(maps))}


def provider_gate():
    result = {}
    for port in (11111, 5353, 8000, 8765):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.15)
        try:
            result[str(port)] = sock.connect_ex(("127.0.0.1", port)) != 0
        finally:
            sock.close()
    return result


def load(path, class_name):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None and asset.get_class().get_name() == class_name, "load failed: " + path)
    return asset


def run():
    active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
    require(active == PROJECT.resolve(strict=True), "wrong project")
    require(not RESULT.exists(), "R46 apply result no-clobber failed")
    require(not TARGET_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(TARGET), "R46 target already exists")
    for path, expected in {PROJECT: PROJECT_SHA, HOME_FILE: HOME_SHA, PROFILE_FILE: PROFILE_SHA, SOURCE_FILE: SOURCE_SHA, **PRESERVED}.items():
        require(Path(path).is_file() and sha256(path) == expected, "preflight hash drift: " + str(path))
    require(ROLLBACK_COPY.is_file() and sha256(ROLLBACK_COPY) == PROFILE_SHA, "rollback preimage invalid")
    require(ROLLBACK_MANIFEST.is_file(), "rollback manifest missing")
    require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
    require(all(provider_gate().values()), "provider listener active")
    command = str(unreal.SystemLibrary.get_command_line()).lower()
    require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")

    source = load(SOURCE, "FoliageData")
    source_entries = list(source.get_editor_property("foliage_list"))
    require(len(source_entries) == 3, "R29 foliage entry count drift")
    grass_indices = [i for i, entry in enumerate(source_entries) if mesh_bindings(entry) == GRASS_MESHES]
    require(grass_indices == [1], "approved grass entry identity drift")
    source_grass = source_entries[1]
    require(abs(float(source_grass.get_editor_property("depth_offset")) - OLD_DEPTH) <= 1.0e-5, "R29 grass depth drift")
    require(abs(float(source_grass.get_editor_property("foliage_density")) - 90.0) <= 1.0e-5, "R29 density drift")
    require("none" in str(source_grass.get_editor_property("density_vertex_color_channel")).lower(), "R29 eligibility drift")
    require(not bool(source_grass.get_editor_property("invert_density_vertex_color_mask")), "R29 invert drift")

    target = unreal.EditorAssetLibrary.duplicate_asset(SOURCE, TARGET)
    require(target is not None, "R46 duplicate failed")
    entries = list(target.get_editor_property("foliage_list"))
    values = entries[1].to_dict()
    depth_key = find_key(values, "depth_offset")
    values[depth_key] = NEW_DEPTH
    entries[1] = unreal.FoliageList(**values)
    target.set_editor_property("foliage_list", entries)
    target_entries = list(target.get_editor_property("foliage_list"))
    require(signature(target_entries[0]) == signature(source_entries[0]), "non-grass entry 0 changed")
    require(signature(target_entries[2]) == signature(source_entries[2]), "non-grass entry 2 changed")
    require(mesh_bindings(target_entries[1]) == GRASS_MESHES, "approved grass meshes changed")
    require(abs(float(target_entries[1].get_editor_property("depth_offset")) - NEW_DEPTH) <= 1.0e-5, "R46 depth did not apply")
    require(signature(target_entries[1], ("depth_offset",)) == signature(source_grass, ("depth_offset",)), "grass changed outside depth")
    require(unreal.EditorAssetLibrary.save_loaded_asset(target, only_if_is_dirty=False), "R46 foliage save failed")

    profile = load(PROFILE, "PlanetData")
    before_seed = int(profile.get_editor_property("generation_seed"))
    before_radius = float(profile.get_editor_property("planet_radius"))
    biomes = list(profile.get_editor_property("biome_data"))
    changed = []
    for index, biome in enumerate(biomes):
        biome_values = biome.to_dict()
        key = find_key(biome_values, "foliage_data")
        if asset_path(biome_values[key]) == SOURCE:
            biome_values[key] = target
            biomes[index] = unreal.BiomeData(**biome_values)
            changed.append(str(biome.get_editor_property("name")))
    require(changed == ["Craters", "Hills", "Mountains"], "unexpected profile binding changes: " + str(changed))
    profile.set_editor_property("biome_data", biomes)
    require(int(profile.get_editor_property("generation_seed")) == before_seed == 1337, "seed changed")
    require(abs(float(profile.get_editor_property("planet_radius")) - before_radius) <= 0.01, "radius changed")
    require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "ProfileV1 save failed")
    require(dirty_packages() == {"content": [], "maps": []}, "dirty packages remain")

    require(sha256(HOME_FILE) == HOME_SHA and sha256(SOURCE_FILE) == SOURCE_SHA, "home or R29 source changed")
    for path, expected in PRESERVED.items():
        require(sha256(path) == expected, "preserved package changed: " + str(path))
    require(TARGET_FILE.is_file(), "R46 package not persisted")
    target_sha = sha256(TARGET_FILE)
    profile_sha = sha256(PROFILE_FILE)
    require(profile_sha != PROFILE_SHA, "ProfileV1 hash did not change")

    return {
        "schema": "redmmo.ppg_profile_v1.grass_depth.apply.r46.v1",
        "status": "PASS_R46_DEPTH_ONLY_SUCCESSOR_BOUND",
        "completed_utc": now(),
        "evidence_class": "automation",
        "source_foliage": SOURCE,
        "source_sha256_before_after": SOURCE_SHA,
        "target_foliage": TARGET,
        "target_sha256": target_sha,
        "profile_sha256_before": PROFILE_SHA,
        "profile_sha256_after": profile_sha,
        "home_sha256_before_after": HOME_SHA,
        "changed_biomes": changed,
        "grass_depth_offset_before_cm": OLD_DEPTH,
        "grass_depth_offset_after_cm": NEW_DEPTH,
        "approved_meshes": GRASS_MESHES,
        "preserved_density": float(target_entries[1].get_editor_property("foliage_density")),
        "preserved_scale": stable_value(target_entries[1].get_editor_property("scale")),
        "rollback": str(ROLLBACK),
        "dirty_packages_after": dirty_packages(),
        "provider_gate_after": provider_gate(),
        "save_called": True,
        "generation_called": False,
        "pie_started": False,
        "claim_limit": "Persistence only; fresh reload and untouched Lit-first pixel visibility remain unproven.",
    }


try:
    write_json(RESULT, run())
    unreal.log("REDMMO_R46_APPLY_PASS")
except Exception as error:
    write_json(RESULT, {
        "schema": "redmmo.ppg_profile_v1.grass_depth.apply.r46.v1",
        "status": "FAIL",
        "completed_utc": now(),
        "error": str(error),
        "traceback": traceback.format_exc(),
    })
    unreal.log_error("REDMMO_R46_APPLY_FAIL " + str(error))
finally:
    unreal.SystemLibrary.quit_editor()
