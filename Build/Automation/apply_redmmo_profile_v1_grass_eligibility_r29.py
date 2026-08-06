"""Create and bind the rollback-backed ProfileV1 grass-eligibility successor."""

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
PROFILE_SHA = "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837"
SOURCE = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/Profiles/DA_PPG_HomeWorld_StylizedForest_R10O"
SOURCE_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\Profiles\DA_PPG_HomeWorld_StylizedForest_R10O.uasset"
SOURCE_SHA = "4D7B577684CF74CBF56BCB6AF8A6867DAD130C8BACF022CF461D86A53833E18F"
TARGET = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassEligible_R29"
TARGET_PACKAGE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles"
TARGET_NAME = "DA_PPG_ProfileV1_GrassEligible_R29"
TARGET_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1GrassEligibility_R29_20260805T1230Z")
ROLLBACK_COPY = ROLLBACK / "DA_PPG_ProfileV1_PlanetData.pre_r29.uasset"
ROLLBACK_MANIFEST = ROLLBACK / "manifest.json"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1GrassEligibility_R29B_20260805T1235Z")
RESULT = DIAG / "apply_result.json"
TARGET_SHA = "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8"

GRASS_MESHES = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
]
GRASS_FILES = {
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset":
        "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset":
        "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


class GateError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


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
    require(len(matches) == 1, "expected one key {} in {}".format(wanted, list(values)))
    return matches[0]


def stable_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {
            normalized_key(key): stable_value(item)
            for key, item in sorted(value.items(), key=lambda pair: normalized_key(pair[0]))
        }
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
    return [
        asset_path(item.get_editor_property("mesh"))
        for item in entry.get_editor_property("meshes")
    ]


def dirty_packages():
    content = [asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    maps = [asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    return {"content": sorted(set(content)), "maps": sorted(set(maps))}


def planet_identity(profile):
    """Capture every editable non-biome PlanetData field this transaction must preserve."""
    fields = (
        "planet_radius",
        "noise_height",
        "generation_seed",
        "min_recursion_level",
        "max_recursion_level",
        "planet_material",
        "generation_material",
        "biome_mask_material",
        "planet_position_scale",
        "generate_water",
        "water_material",
        "far_water_material",
        "water_simulation_data",
        "recursion_level_for_material_change",
    )
    identity = {}
    for field in fields:
        identity[field] = stable_value(profile.get_editor_property(field))
    return identity


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
    require(not RESULT.exists(), "R29B result no-clobber failed")
    require(sha256(PROJECT) == PROJECT_SHA, "project descriptor drift")
    require(sha256(HOME_FILE) == HOME_SHA, "home map drift")
    require(sha256(PROFILE_FILE) == PROFILE_SHA, "ProfileV1 drift")
    require(sha256(SOURCE_FILE) == SOURCE_SHA, "R10O source drift")
    require(TARGET_FILE.is_file() and sha256(TARGET_FILE) == TARGET_SHA, "validated R29 target drift")
    require(ROLLBACK_COPY.is_file() and sha256(ROLLBACK_COPY) == PROFILE_SHA, "rollback preimage invalid")
    require(ROLLBACK_MANIFEST.is_file(), "rollback manifest missing")
    for path, expected in GRASS_FILES.items():
        require(path.is_file() and sha256(path) == expected, "grass asset drift: " + str(path))
    for path, expected in PROTECTED.items():
        require(path.is_file() and sha256(path) == expected, "protected package drift: " + str(path))
    require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
    require(all(provider_gate().values()), "provider listener active")
    command = str(unreal.SystemLibrary.get_command_line()).lower()
    require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")

    source = load(SOURCE, "FoliageData")
    source_entries = list(source.get_editor_property("foliage_list"))
    require(len(source_entries) == 3, "source foliage entry count drift")
    grass_indices = [index for index, entry in enumerate(source_entries) if mesh_bindings(entry) == GRASS_MESHES]
    require(grass_indices == [1], "expected exact grass entry at index 1")
    source_grass = source_entries[1]
    require("blue" in str(source_grass.get_editor_property("density_vertex_color_channel")).lower(), "source grass mask is not BLUE")
    require(bool(source_grass.get_editor_property("invert_density_vertex_color_mask")), "source grass mask is not inverted")

    target = load(TARGET, "FoliageData")
    verified_entries = list(target.get_editor_property("foliage_list"))
    require(len(verified_entries) == len(source_entries), "target entry count drift")
    for index in (0, 2):
        require(signature(verified_entries[index]) == signature(source_entries[index]), "non-grass entry changed: {}".format(index))
    verified_grass = verified_entries[1]
    require(mesh_bindings(verified_grass) == GRASS_MESHES, "grass mesh identity changed")
    require("none" in str(verified_grass.get_editor_property("density_vertex_color_channel")).lower(), "target grass mask not None")
    require(not bool(verified_grass.get_editor_property("invert_density_vertex_color_mask")), "target grass invert not false")
    require(
        signature(verified_grass, ("density_vertex_color_channel", "invert_density_vertex_color_mask"))
        == signature(source_grass, ("density_vertex_color_channel", "invert_density_vertex_color_mask")),
        "grass field changed outside eligibility mask",
    )
    require(sha256(TARGET_FILE) == TARGET_SHA, "target changed during validation")

    profile = load(PROFILE, "PlanetData")
    before_profile_identity = planet_identity(profile)
    biomes = list(profile.get_editor_property("biome_data"))
    changed = []
    before_bindings = []
    after_bindings = []
    for index, biome in enumerate(biomes):
        values = biome.to_dict()
        key = find_key(values, "foliage_data")
        name = str(biome.get_editor_property("name"))
        before = asset_path(values[key])
        before_bindings.append({"index": index, "name": name, "foliage": before})
        if before == SOURCE:
            values[key] = target
            biomes[index] = unreal.BiomeData(**values)
            changed.append(name)
            after = TARGET
        else:
            after = before
        after_bindings.append({"index": index, "name": name, "foliage": after})
    require(changed == ["Craters", "Hills", "Mountains"], "unexpected changed biomes: " + str(changed))
    profile.set_editor_property("biome_data", biomes)
    require(planet_identity(profile) == before_profile_identity, "ProfileV1 changed outside biome data")
    require(int(profile.get_editor_property("generation_seed")) == 1337, "seed changed")
    require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "ProfileV1 save failed")
    require(dirty_packages() == {"content": [], "maps": []}, "dirty packages remain")

    require(sha256(HOME_FILE) == HOME_SHA, "home map changed")
    require(sha256(SOURCE_FILE) == SOURCE_SHA, "R10O source changed")
    for path, expected in GRASS_FILES.items():
        require(sha256(path) == expected, "grass asset changed: " + str(path))
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "protected package changed: " + str(path))
    profile_after = sha256(PROFILE_FILE)
    target_after = sha256(TARGET_FILE)
    require(profile_after != PROFILE_SHA, "ProfileV1 hash did not change")

    return {
        "schema": "redmmo.ppg_profile_v1.grass_eligibility.apply.r29b.v1",
        "status": "PASS_R29B_GRASS_ELIGIBILITY_SUCCESSOR_BOUND",
        "started_from_profile_sha256": PROFILE_SHA,
        "completed_utc": now(),
        "evidence_class": "automation",
        "source_foliage": SOURCE,
        "source_foliage_sha256_before_after": SOURCE_SHA,
        "target_foliage": TARGET,
        "target_foliage_sha256_before_after": target_after,
        "preserved_planet_identity": before_profile_identity,
        "profile_v1_sha256_after": profile_after,
        "home_map_sha256_before_after": HOME_SHA,
        "changed_biomes": changed,
        "biome_bindings_before": before_bindings,
        "biome_bindings_after": after_bindings,
        "grass_before": {
            "density_vertex_color_channel": str(source_grass.get_editor_property("density_vertex_color_channel")),
            "invert_density_vertex_color_mask": bool(source_grass.get_editor_property("invert_density_vertex_color_mask")),
        },
        "grass_after": {
            "density_vertex_color_channel": str(verified_grass.get_editor_property("density_vertex_color_channel")),
            "invert_density_vertex_color_mask": bool(verified_grass.get_editor_property("invert_density_vertex_color_mask")),
            "meshes": mesh_bindings(verified_grass),
            "density": float(verified_grass.get_editor_property("foliage_density")),
            "scale": stable_value(verified_grass.get_editor_property("scale")),
            "culling_distance": float(verified_grass.get_editor_property("culling_distance")),
        },
        "rollback": str(ROLLBACK),
        "dirty_packages_after": dirty_packages(),
        "provider_gate_after": provider_gate(),
        "save_called": True,
        "generation_called": False,
        "pie_started": False,
        "claim_limit": "Persistence transaction only; fresh reload, active runtime grass and pixel visibility remain unproven.",
    }


try:
    payload = run()
    write_json(RESULT, payload)
    unreal.log("REDMMO_R29_PASS")
except Exception as error:
    write_json(RESULT, {
        "schema": "redmmo.ppg_profile_v1.grass_eligibility.apply.r29b.v1",
        "status": "FAIL",
        "error": str(error),
        "traceback": traceback.format_exc(),
        "completed_utc": now(),
    })
    unreal.log_error("REDMMO_R29B_FAIL " + str(error))
finally:
    unreal.SystemLibrary.quit_editor()
