"""Apply the bounded R49 project-owned grass WPO-only discriminator."""

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
ROOT = PROJECT.parent
RESULT = Path(os.environ["REDMMO_R49_APPLY_RESULT"])
R32 = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R32/Materials/M_GrassChunks_PPGReadable_R32"
INSTANCES = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_B_R10N",
]
INSTANCE_FILES = [
    ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset",
    ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset",
]
PREIMAGE_HASHES = [
    "91A0E7233A5922A921FB4CF8692B8631DBB7AEFE7D3D106FDB63C44DB412CE47",
    "19D1B594553977A6A7BA116271F103DCD4044F8F24C3E8B5CF8F596082A9F68E",
]
WPO_PARAMETERS = {
    "CameraWPOIntensity": 0.009999999776482582,
    "DistanceFieldWPOIntensity": 0.5076889991760254,
    "MeshMaskingWPOIntensity": 0.009999999776482582,
    "PlayerWPOScale_Intensity": 0.10000000149011612,
    "PlayerWPO_Intensity": 0.5360000133514404,
    "WPO_LandscapeLuminance_Intensity": 1.100000023841858,
}
PRESERVED_SCALARS = {
    "GrassLocalZ_ScaleMultiply": 1.4500000476837158,
    "LocalScale_Multiply": 1.2999999523162842,
    "GrassDitheringMask_Intensity": 40.0,
    "GrassDitheringMask_Contrast": 3.5,
    "GrassDitheringCameraAngle_Intensity": -0.30000001192092896,
}
CHECKS = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    ROOT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap": "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset": "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970",
    ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset": "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8",
    ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R32\Materials\M_GrassChunks_PPGReadable_R32.uasset": "2BD2B8DD41C611CF1250F1A39C40D3B4A7C47B5EB71ECD1497732546B80F0210",
    ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset": "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset": "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"): "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"): "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
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


def dirty_packages():
    return {
        "content": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}),
        "maps": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}),
    }


def provider_gate():
    result = {}
    for port in (11111, 5353, 8000, 8765):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.15)
        try:
            result[str(port)] = sock.connect_ex(("127.0.0.1", port)) != 0
        finally:
            sock.close()
    require(all(result.values()), "provider listener active: " + repr(result))
    return result


def scalar(instance, name):
    return float(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(instance, name))


def write(payload):
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with RESULT.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def run():
    require(not RESULT.exists(), "result no-clobber failed")
    active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
    require(active == PROJECT.resolve(strict=True), "wrong project")
    require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
    providers = provider_gate()
    for path, expected in CHECKS.items():
        require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
    for path, expected in zip(INSTANCE_FILES, PREIMAGE_HASHES):
        require(path.is_file() and sha256(path) == expected, "instance preimage drift: " + str(path))

    editing = unreal.MaterialEditingLibrary
    records = []
    for asset, file_path in zip(INSTANCES, INSTANCE_FILES):
        instance = unreal.load_asset(asset)
        require(instance is not None and instance.get_class().get_name() == "MaterialInstanceConstant", "instance load failed: " + asset)
        require(asset_path(instance.get_editor_property("parent")) == R32, "instance parent drift: " + asset)
        before = {name: scalar(instance, name) for name in WPO_PARAMETERS}
        preserved_before = {name: scalar(instance, name) for name in PRESERVED_SCALARS}
        for name, expected in WPO_PARAMETERS.items():
            require(abs(before[name] - expected) <= 1.0e-5, "WPO prevalue drift: " + asset + " " + name)
            editing.set_material_instance_scalar_parameter_value(instance, name, 0.0)
        require(unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False), "instance save failed: " + asset)
        after = {name: scalar(instance, name) for name in WPO_PARAMETERS}
        preserved_after = {name: scalar(instance, name) for name in PRESERVED_SCALARS}
        require(all(abs(value) <= 1.0e-7 for value in after.values()), "WPO zero write failed: " + asset)
        for name, expected in PRESERVED_SCALARS.items():
            require(abs(preserved_before[name] - expected) <= 1.0e-5, "preserved prevalue drift: " + asset + " " + name)
            require(abs(preserved_after[name] - expected) <= 1.0e-5, "preserved scalar changed: " + asset + " " + name)
        records.append({"asset": asset, "file": str(file_path), "before": before, "after": after, "preserved": preserved_after})

    require(dirty_packages() == {"content": [], "maps": []}, "save left dirty package")
    for path, expected in CHECKS.items():
        require(sha256(path) == expected, "protected input drift after save: " + str(path))
    post_hashes = [sha256(path) for path in INSTANCE_FILES]
    require(all(after != before for after, before in zip(post_hashes, PREIMAGE_HASHES)), "instance bytes did not change")
    return {
        "schema": "redmmo.grass_wpo.apply.r49.v1",
        "status": "PASS_R49_WPO_INTENSITIES_ZERO_APPLIED",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "records": records,
        "preimage_hashes": PREIMAGE_HASHES,
        "postimage_hashes": post_hashes,
        "changed_only": sorted(WPO_PARAMETERS),
        "provider_gate": providers,
        "dirty_packages_after": dirty_packages(),
        "save_called": True,
        "map_loaded": False,
        "pie_started": False,
        "claim_limit": "Project-owned approved-instance WPO-only mutation; no visual or runtime acceptance claim.",
    }


try:
    write(run())
    unreal.log("REDMMO_R49_APPLY_PASS")
except Exception as error:
    write({
        "schema": "redmmo.grass_wpo.apply.r49.v1",
        "status": "FAIL",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "error": str(error),
        "traceback": traceback.format_exc(),
    })
    unreal.log_error("REDMMO_R49_APPLY_FAIL " + str(error))
finally:
    unreal.SystemLibrary.quit_editor()
