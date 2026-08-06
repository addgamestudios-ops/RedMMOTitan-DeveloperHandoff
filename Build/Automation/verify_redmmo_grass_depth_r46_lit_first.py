"""Fresh-process untouched Lit-first proof for the R46 depth-only grass successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import unreal


BASE_PATH = Path("D:/RedMMOTitan/Build/Automation/verify_redmmo_grass_render_refresh_r41b_lit_first.py")
SPEC = importlib.util.spec_from_file_location("redmmo_r41b_grass_verify_base_for_r46", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load proven R41B Lit-first verifier")

base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

PROJECT_ROOT = base.PROJECT.parent
PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
R46 = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassDepth_R46"
R29 = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassEligible_R29"
R46_FILE = PROJECT_ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassDepth_R46.uasset"
R29_FILE = PROJECT_ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
PROFILE_FILE = PROJECT_ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
MESH_A_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset"
MESH_B_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset"

base.DIAG = Path("D:/RedMMOTitanWindowsData/Diagnostics/RedMMO_GrassDepth_R46B_20260805T1700Z")
base.RESULT = base.DIAG / "verify_result.json"
base.LIT = base.DIAG / "R46_untouched_lit_first_depth_corrected.png"
base.CHECKS[base.HEADER_FILE] = "94BEB7B37448C5CEC49F1F38B927B9AA153AAC7671F78B42EC78B46D24AE1639"
base.CHECKS[base.SOURCE_FILE] = "022C2B422D9BA20270B6CFA88BF1DB6B51D967AB2E88A7E6C34898CB1E4CD893"
base.CHECKS[base.BINARY_FILE] = "21081D7DA8239FD6606868808BB48234117B81C9A27ACBC7E25CA7F5D713FA30"
base.CHECKS[PROFILE_FILE] = "DEB1EF5AB1E1558661F0F622F8654A9E3FBB6B1A9B7E83092AA5C6540FC490DB"
base.CHECKS[R46_FILE] = "BCC1EE9838E31A27D55651E4A1302A4EBA276B827D5070038611D89EE88E4253"
base.CHECKS[R29_FILE] = "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8"
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


def capture_r46(self):
    profile = self.spawner.get_editor_property("planet_data")
    base.require(profile is not None and asset_path(profile) == PROFILE, "PIE ProfileV1 binding drift")
    bindings = []
    foliage = None
    for biome in list(profile.get_editor_property("biome_data")):
        biome_foliage = find_field(biome, "foliage_data")
        bindings.append({
            "name": str(biome.get_editor_property("name")),
            "foliage": asset_path(biome_foliage),
        })
        if asset_path(biome_foliage) == R46:
            foliage = biome_foliage
    expected_bound = [item["name"] for item in bindings if item["foliage"] == R46]
    base.require(expected_bound == ["Craters", "Hills", "Mountains"], "R46 biome binding drift: " + repr(bindings))
    base.require(foliage is not None, "PIE R46 foliage reference missing")
    entries = list(foliage.get_editor_property("foliage_list"))
    base.require(len(entries) == 3, "R46 foliage entry count drift")
    grass = entries[1]
    depth = float(grass.get_editor_property("depth_offset"))
    density = float(grass.get_editor_property("foliage_density"))
    base.require(abs(depth - (-50.0)) <= 1.0e-5, "R46 depth drift")
    base.require(abs(density - 90.0) <= 1.0e-5, "R46 density drift")
    self.report["r46_depth_contract"] = {
        "profile": PROFILE,
        "foliage": R46,
        "bound_biomes": expected_bound,
        "depth_offset_cm": depth,
        "density": density,
        "source_r29_preserved": base.sha256(R29_FILE),
    }
    original_capture(self)


def finish_r46(self):
    base.require(not self.level.is_in_play_in_editor(), "PIE did not stop")
    base.require(base.dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
    for path, expected in base.CHECKS.items():
        base.require(base.sha256(path) == expected, "post-PIE drift: " + str(path))
    self.report.update({
        "schema": "redmmo.grass_depth.verify.r46.v1",
        "status": "PASS_R46_UNTOUCHED_LIT_FIRST_CAPTURE_PENDING_PIXEL_REVIEW",
        "completed_utc": base.now(),
        "dirty_packages_after": base.dirty_packages(),
        "provider_gate_after": base.provider_gate(),
        "save_called": False,
        "visibility_cycle_called": False,
        "view_mode_command_called_before_capture": False,
        "component_property_mutation_called": False,
        "claim_limit": (
            "Fresh-reload untouched Lit-first D3D12 PIE after the depth-only successor; "
            "pixel review is separate and no gameplay, package, replication, multiplayer or user-acceptance claim is made."
        ),
    })
    base.atomic_json(base.RESULT, self.report)
    unreal.log("REDMMO_R46_VERIFY_PASS")
    self.phase = "DONE"
    self.schedule_quit(3.0)


base.R41B.capture_lit_first = capture_r46
base.R41B.finish = finish_r46
base._R41B.report.update({
    "schema": "redmmo.grass_depth.verify.r46.v1",
    "slice": "R46 depth-only approved grass successor",
    "expected_components": 196,
    "expected_instances": 2218356,
    "expected_depth_offset_cm": -50.0,
})
unreal.log("REDMMO_R46_VERIFY_STARTED")
