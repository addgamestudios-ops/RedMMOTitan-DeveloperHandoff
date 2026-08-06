"""Fresh-reload untouched Lit-first proof for the R49 WPO-only discriminator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import unreal


BASE_PATH = Path("D:/RedMMOTitan/Build/Automation/verify_redmmo_grass_render_refresh_r41b_lit_first.py")
SPEC = importlib.util.spec_from_file_location("redmmo_r41b_grass_verify_base_for_r49", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load proven R41B Lit-first verifier")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

PROJECT_ROOT = base.PROJECT.parent
PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
R29 = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassEligible_R29"
R32 = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R32/Materials/M_GrassChunks_PPGReadable_R32"
INSTANCES = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_B_R10N",
]
PROFILE_FILE = PROJECT_ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
R29_FILE = PROJECT_ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
R32_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R32\Materials\M_GrassChunks_PPGReadable_R32.uasset"
INSTANCE_A_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset"
INSTANCE_B_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset"
MESH_A_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset"
MESH_B_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset"
WPO_PARAMETERS = [
    "CameraWPOIntensity",
    "DistanceFieldWPOIntensity",
    "MeshMaskingWPOIntensity",
    "PlayerWPOScale_Intensity",
    "PlayerWPO_Intensity",
    "WPO_LandscapeLuminance_Intensity",
]
PRESERVED = {
    "GrassLocalZ_ScaleMultiply": 1.4500000476837158,
    "LocalScale_Multiply": 1.2999999523162842,
    "GrassDitheringMask_Intensity": 40.0,
    "GrassDitheringMask_Contrast": 3.5,
    "GrassDitheringCameraAngle_Intensity": -0.30000001192092896,
}

base.DIAG = Path("D:/RedMMOTitanWindowsData/Diagnostics/RedMMO_GrassWPOZero_R49_20260805T1735Z")
base.RESULT = base.DIAG / "verify_result.json"
base.LIT = base.DIAG / "R49_untouched_lit_first_wpo_zero.png"
base.CHECKS[base.HEADER_FILE] = "94BEB7B37448C5CEC49F1F38B927B9AA153AAC7671F78B42EC78B46D24AE1639"
base.CHECKS[base.SOURCE_FILE] = "022C2B422D9BA20270B6CFA88BF1DB6B51D967AB2E88A7E6C34898CB1E4CD893"
base.CHECKS[base.BINARY_FILE] = "21081D7DA8239FD6606868808BB48234117B81C9A27ACBC7E25CA7F5D713FA30"
base.CHECKS[PROFILE_FILE] = "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970"
base.CHECKS[R29_FILE] = "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8"
base.CHECKS[R32_FILE] = "2BD2B8DD41C611CF1250F1A39C40D3B4A7C47B5EB71ECD1497732546B80F0210"
base.CHECKS[INSTANCE_A_FILE] = "F12DE4ED57DFD5985C0B63F8FA4A4EB1EBDD7BC3044FAF3286C6E8E1B18FF700"
base.CHECKS[INSTANCE_B_FILE] = "A190A3BBA93B8F47960B83B2524AFA50F15B73DA499E1551BC243187F03B7C46"
base.CHECKS[MESH_A_FILE] = "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443"
base.CHECKS[MESH_B_FILE] = "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475"


def asset_path(value):
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def normalized(value):
    return str(value).replace("_", "").replace(" ", "").lower()


def find_field(value, wanted):
    fields = value.to_dict()
    matches = [item for key, item in fields.items() if normalized(key) == normalized(wanted)]
    base.require(len(matches) == 1, "missing exact reflected field " + wanted)
    return matches[0]


original_capture = base.R41B.capture_lit_first


def capture_r49(self):
    profile = self.spawner.get_editor_property("planet_data")
    base.require(profile is not None and asset_path(profile) == PROFILE, "PIE ProfileV1 binding drift")
    bindings = []
    for biome in list(profile.get_editor_property("biome_data")):
        bindings.append({"name": str(biome.get_editor_property("name")), "foliage": asset_path(find_field(biome, "foliage_data"))})
    bound = [item["name"] for item in bindings if item["foliage"] == R29]
    base.require(bound == ["Craters", "Hills", "Mountains"], "R29 biome binding drift: " + repr(bindings))
    material = unreal.load_asset(R32)
    base.require(material is not None and "BLEND_MASKED" in str(material.get_editor_property("blend_mode")), "R32 Masked parent drift")
    editing = unreal.MaterialEditingLibrary
    records = []
    for asset in INSTANCES:
        instance = unreal.load_asset(asset)
        base.require(instance is not None and asset_path(instance.get_editor_property("parent")) == R32, "instance parent drift: " + asset)
        wpo = {name: float(editing.get_material_instance_scalar_parameter_value(instance, name)) for name in WPO_PARAMETERS}
        preserved = {name: float(editing.get_material_instance_scalar_parameter_value(instance, name)) for name in PRESERVED}
        base.require(all(abs(value) <= 1.0e-7 for value in wpo.values()), "WPO value drift: " + asset)
        for name, expected in PRESERVED.items():
            base.require(abs(preserved[name] - expected) <= 1.0e-5, "preserved scalar drift: " + asset + " " + name)
        records.append({"asset": asset, "wpo": wpo, "preserved": preserved})
    self.report["r49_wpo_contract"] = {
        "profile": PROFILE,
        "foliage": R29,
        "bound_biomes": bound,
        "parent": R32,
        "parent_blend": "Masked",
        "instances": records,
        "changed_only": WPO_PARAMETERS,
    }
    original_capture(self)


def finish_r49(self):
    base.require(not self.level.is_in_play_in_editor(), "PIE did not stop")
    base.require(base.dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
    for path, expected in base.CHECKS.items():
        base.require(base.sha256(path) == expected, "post-PIE drift: " + str(path))
    self.report.update({
        "schema": "redmmo.grass_wpo.verify.r49.v1",
        "status": "PASS_R49_WPO_ZERO_UNTOUCHED_LIT_FIRST_CAPTURE_PENDING_PIXEL_REVIEW",
        "completed_utc": base.now(),
        "dirty_packages_after": base.dirty_packages(),
        "provider_gate_after": base.provider_gate(),
        "save_called": False,
        "visibility_cycle_called": False,
        "view_mode_command_called_before_capture": False,
        "component_property_mutation_called": False,
        "claim_limit": "Fresh-reload untouched Lit-first D3D12 PIE after WPO-only zeroing; pixel review is separate.",
    })
    base.atomic_json(base.RESULT, self.report)
    unreal.log("REDMMO_R49_VERIFY_PASS")
    self.phase = "DONE"
    self.schedule_quit(3.0)


base.R41B.capture_lit_first = capture_r49
base.R41B.finish = finish_r49
base._R41B.report.update({
    "schema": "redmmo.grass_wpo.verify.r49.v1",
    "slice": "R49 approved-instance WPO-only discriminator",
    "expected_components": 196,
    "expected_instances": 2218356,
})
unreal.log("REDMMO_R49_VERIFY_STARTED")
