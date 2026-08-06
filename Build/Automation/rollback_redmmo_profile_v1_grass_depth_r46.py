"""Rollback the visually ineffective project-owned R46 grass depth successor."""

from __future__ import annotations

import hashlib
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
HOME_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
R29 = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassEligible_R29"
R29_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
R46 = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassDepth_R46"
R46_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassDepth_R46.uasset"
RESULT = Path(os.environ["REDMMO_R46_ROLLBACK_RESULT"])
EXPECTED = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "DEB1EF5AB1E1558661F0F622F8654A9E3FBB6B1A9B7E83092AA5C6540FC490DB",
    R29_FILE: "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8",
    R46_FILE: "BCC1EE9838E31A27D55651E4A1302A4EBA276B827D5070038611D89EE88E4253",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value):
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def normalized(value):
    return str(value).replace("_", "").replace(" ", "").lower()


def find_key(values, wanted):
    matches = [key for key in values if normalized(key) == normalized(wanted)]
    require(len(matches) == 1, "missing exact field " + wanted)
    return matches[0]


def dirty_packages():
    return {
        "content": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}),
        "maps": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}),
    }


def write_result(payload):
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with RESULT.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def run():
    active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
    require(active == PROJECT.resolve(strict=True), "wrong project")
    require(not RESULT.exists(), "rollback result no-clobber failed")
    for path, expected in EXPECTED.items():
        require(path.is_file() and sha256(path) == expected, "rollback preflight drift: " + str(path))
    require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")

    profile = unreal.EditorAssetLibrary.load_asset(PROFILE)
    source = unreal.EditorAssetLibrary.load_asset(R29)
    target = unreal.EditorAssetLibrary.load_asset(R46)
    require(profile is not None and source is not None and target is not None, "rollback asset load failed")
    biomes = list(profile.get_editor_property("biome_data"))
    restored = []
    for index, biome in enumerate(biomes):
        values = biome.to_dict()
        key = find_key(values, "foliage_data")
        if asset_path(values[key]) == R46:
            values[key] = source
            biomes[index] = unreal.BiomeData(**values)
            restored.append(str(biome.get_editor_property("name")))
    require(restored == ["Craters", "Hills", "Mountains"], "unexpected rollback bindings: " + repr(restored))
    profile.set_editor_property("biome_data", biomes)
    require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "rollback ProfileV1 save failed")
    target = None
    unreal.SystemLibrary.collect_garbage()
    require(unreal.EditorAssetLibrary.delete_asset(R46), "R46 asset deletion failed")
    require(not R46_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(R46), "R46 target remains")
    require(dirty_packages() == {"content": [], "maps": []}, "rollback left dirty packages")
    for path, expected in EXPECTED.items():
        if path in (PROFILE_FILE, R46_FILE):
            continue
        require(sha256(path) == expected, "preserved file changed: " + str(path))

    return {
        "schema": "redmmo.ppg_profile_v1.grass_depth.rollback.r46.v1",
        "status": "PASS_R46_INEFFECTIVE_DEPTH_SUCCESSOR_REMOVED",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "restored_biomes": restored,
        "profile_sha256_after_unreal_rebind": sha256(PROFILE_FILE),
        "expected_byte_exact_preimage_sha256": "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970",
        "r46_asset_exists_after": R46_FILE.exists(),
        "home_sha256_before_after": EXPECTED[HOME_FILE],
        "r29_sha256_before_after": EXPECTED[R29_FILE],
        "dirty_packages_after": dirty_packages(),
        "claim_limit": "Rollback transaction only; exact ProfileV1 preimage restoration is verified by the outer guard.",
    }


try:
    write_result(run())
    unreal.log("REDMMO_R46_ROLLBACK_PASS")
except Exception as error:
    write_result({
        "schema": "redmmo.ppg_profile_v1.grass_depth.rollback.r46.v1",
        "status": "FAIL",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "error": str(error),
        "traceback": traceback.format_exc(),
    })
    unreal.log_error("REDMMO_R46_ROLLBACK_FAIL " + str(error))
finally:
    unreal.SystemLibrary.quit_editor()
