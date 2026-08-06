"""Fresh-reload untouched Lit-first proof for the R48 Opaque-only discriminator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import unreal


BASE_PATH = Path("D:/RedMMOTitan/Build/Automation/verify_redmmo_grass_render_refresh_r41b_lit_first.py")
SPEC = importlib.util.spec_from_file_location("redmmo_r41b_grass_verify_base_for_r48", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load proven R41B Lit-first verifier")

base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

PROJECT_ROOT = base.PROJECT.parent
PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
R29 = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassEligible_R29"
R32 = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R32/Materials/M_GrassChunks_PPGReadable_R32"
INSTANCE_A = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_A_R10N"
INSTANCE_B = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_B_R10N"
PROFILE_FILE = PROJECT_ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
R29_FILE = PROJECT_ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
R32_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R32\Materials\M_GrassChunks_PPGReadable_R32.uasset"
INSTANCE_A_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset"
INSTANCE_B_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset"
MESH_A_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset"
MESH_B_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset"

base.DIAG = Path("D:/RedMMOTitanWindowsData/Diagnostics/RedMMO_GrassBlendOpaque_R48_20260805T1725Z")
base.RESULT = base.DIAG / "verify_result.json"
base.LIT = base.DIAG / "R48_untouched_lit_first_opaque.png"
base.CHECKS[base.HEADER_FILE] = "94BEB7B37448C5CEC49F1F38B927B9AA153AAC7671F78B42EC78B46D24AE1639"
base.CHECKS[base.SOURCE_FILE] = "022C2B422D9BA20270B6CFA88BF1DB6B51D967AB2E88A7E6C34898CB1E4CD893"
base.CHECKS[base.BINARY_FILE] = "21081D7DA8239FD6606868808BB48234117B81C9A27ACBC7E25CA7F5D713FA30"
base.CHECKS[PROFILE_FILE] = "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970"
base.CHECKS[R29_FILE] = "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8"
base.CHECKS[R32_FILE] = "E70E920D46B123E5C1BC82C09A3D53FD86869AF6953F1C08732BB01AE2507797"
base.CHECKS[INSTANCE_A_FILE] = "91A0E7233A5922A921FB4CF8692B8631DBB7AEFE7D3D106FDB63C44DB412CE47"
base.CHECKS[INSTANCE_B_FILE] = "19D1B594553977A6A7BA116271F103DCD4044F8F24C3E8B5CF8F596082A9F68E"
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


def capture_r48(self):
    profile = self.spawner.get_editor_property("planet_data")
    base.require(profile is not None and asset_path(profile) == PROFILE, "PIE ProfileV1 binding drift")
    bindings = []
    for biome in list(profile.get_editor_property("biome_data")):
        bindings.append({
            "name": str(biome.get_editor_property("name")),
            "foliage": asset_path(find_field(biome, "foliage_data")),
        })
    bound = [item["name"] for item in bindings if item["foliage"] == R29]
    base.require(bound == ["Craters", "Hills", "Mountains"], "R29 biome binding drift: " + repr(bindings))

    material = unreal.load_asset(R32)
    a = unreal.load_asset(INSTANCE_A)
    b = unreal.load_asset(INSTANCE_B)
    base.require(material is not None and a is not None and b is not None, "approved material load failed")
    blend = str(material.get_editor_property("blend_mode"))
    base.require("BLEND_OPAQUE" in blend, "R48 parent is not Opaque")
    base.require(bool(material.get_editor_property("two_sided")), "R48 two-sided drift")
    base.require(asset_path(a.get_editor_property("parent")) == R32, "instance A parent drift")
    base.require(asset_path(b.get_editor_property("parent")) == R32, "instance B parent drift")
    lib = unreal.MaterialEditingLibrary
    switches = [
        bool(lib.get_material_instance_static_switch_parameter_value(item, "GrassNearGround_Dithering_Enable"))
        for item in (a, b)
    ]
    base.require(switches == [True, True], "approved instance switch drift")
    self.report["r48_blend_contract"] = {
        "profile": PROFILE,
        "foliage": R29,
        "bound_biomes": bound,
        "parent": R32,
        "blend_mode": blend,
        "two_sided": True,
        "near_ground_dither_instance_switches_preserved": switches,
        "masked_opacity_path_active": False,
        "changed_only": "parent blend mode Masked to Opaque",
    }
    original_capture(self)


def finish_r48(self):
    base.require(not self.level.is_in_play_in_editor(), "PIE did not stop")
    base.require(base.dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
    for path, expected in base.CHECKS.items():
        base.require(base.sha256(path) == expected, "post-PIE drift: " + str(path))
    self.report.update({
        "schema": "redmmo.grass_blend.verify.r48.v1",
        "status": "PASS_R48_OPAQUE_UNTOUCHED_LIT_FIRST_CAPTURE_PENDING_PIXEL_REVIEW",
        "completed_utc": base.now(),
        "dirty_packages_after": base.dirty_packages(),
        "provider_gate_after": base.provider_gate(),
        "save_called": False,
        "visibility_cycle_called": False,
        "view_mode_command_called_before_capture": False,
        "component_property_mutation_called": False,
        "claim_limit": (
            "Fresh-reload untouched Lit-first D3D12 PIE after the blend-only Opaque discriminator; "
            "pixel review is separate and no gameplay, package, replication, multiplayer or user-acceptance claim is made."
        ),
    })
    base.atomic_json(base.RESULT, self.report)
    unreal.log("REDMMO_R48_VERIFY_PASS")
    self.phase = "DONE"
    self.schedule_quit(3.0)


base.R41B.capture_lit_first = capture_r48
base.R41B.finish = finish_r48
base._R41B.report.update({
    "schema": "redmmo.grass_blend.verify.r48.v1",
    "slice": "R48 project-owned Opaque-only grass discriminator",
    "expected_components": 196,
    "expected_instances": 2218356,
})
unreal.log("REDMMO_R48_VERIFY_STARTED")
