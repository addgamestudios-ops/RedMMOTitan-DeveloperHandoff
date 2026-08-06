"""Fresh-reload D3D12 proof for the R71 role-specific PPG surface.

Reuses the proven R66 no-palms lifecycle harness. This verifier performs no
asset or map writes: it checks the serialized role graph and binding, runs a
fresh MapCheck, enters PIE once, requires the established seeded grass census
and zero palms, and captures the live player viewport.
"""

from __future__ import annotations

from pathlib import Path

import unreal


BASE_PATH = Path(r"D:\RedMMOTitan\Build\Automation\verify_redmmo_profile_v1_no_palms_existing_viewport_r66.py")
ROOT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\WorldAuthoring\PPG\ProfileV1")
BINARY_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Binaries\Win64\UnrealEditor-RedMMO.dll")
PROFILE_FILE = ROOT / "DA_PPG_ProfileV1_PlanetData.uasset"
SOURCE_PARENT_FILE = ROOT / "M_PPG_ProfileV1_SurfaceParent.uasset"
SOURCE_MI_FILE = ROOT / r"Materials\MI_PPG_ProfileV1_PaintedLeaves_R67.uasset"
TARGET_PARENT_FILE = ROOT / r"Materials\M_PPG_ProfileV1_RoleSurface_R71.uasset"
TARGET_MI_FILE = ROOT / r"Materials\MI_PPG_ProfileV1_RoleSurface_R71.uasset"
ROCK_BC_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\StylizedRocksPack_01\DetailTextures\T_Rock_Painterly_01_BC.uasset")
SAND_BC_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\SoStylized\Environment\Landscape\Textures\T_DesertSand_BC.uasset")
SAND_N_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\SoStylized\Environment\Landscape\Textures\T_DesertSand_N.uasset")

PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
SOURCE_PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_SurfaceParent"
SOURCE_MI = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/MI_PPG_ProfileV1_PaintedLeaves_R67"
TARGET_PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/M_PPG_ProfileV1_RoleSurface_R71"
TARGET_MI = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/MI_PPG_ProfileV1_RoleSurface_R71"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1RoleSurface_R71B_20260805T2311Z\Capture")
RESULT = DIAG / "result.json"
CAPTURE = DIAG / "R71_role_surface_no_palms_existing_viewport.png"


source = BASE_PATH.read_text(encoding="utf-8")
bootstrap = "\ntry:\n    _R66 = R66()"
if bootstrap not in source:
    raise RuntimeError("R66 bootstrap boundary missing")
scope = {"__name__": "redmmo_r66_base_for_r71", "__file__": str(BASE_PATH)}
exec(compile(source.split(bootstrap, 1)[0], str(BASE_PATH), "exec"), scope)

CHECKS = dict(scope["CHECKS"])
DIAGNOSTICS_HEADER = scope["namespace"]["DIAGNOSTICS_HEADER"]
DIAGNOSTICS_SOURCE = scope["namespace"]["DIAGNOSTICS_SOURCE"]
CHECKS[DIAGNOSTICS_HEADER] = "C04B35F4528431CEBFF123B7664AD9F5D6D1D76BAE93AFF907A687B4D7BD79BC"
CHECKS[DIAGNOSTICS_SOURCE] = "366EAF660316DB1DC07E3EFAEA369E43D83C89DB4277108798DB90D896D13C44"
CHECKS[BINARY_FILE] = "78EFF5DF6AAEA92C93246C22DE9755313AE5CE90793758C9B4A2BB2820BC8C31"
CHECKS[PROFILE_FILE] = "BD5E46F3132A6A8947C1258AB18C0F152DD4836755A414B9CC876E3BD0D6CB0D"
CHECKS[SOURCE_PARENT_FILE] = "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768"
CHECKS[SOURCE_MI_FILE] = "745381295CDC76754B9FD347CC85CEBEC3151B042C366CDA40F1908163B8A4F7"
CHECKS[TARGET_PARENT_FILE] = "EA3A5704BDA1706C7720CDFB51F39CE370CCD844E6FECEDEB53CF3ACC4F555DE"
CHECKS[TARGET_MI_FILE] = "D4D222CF92769F99631B649198DD8C38032BD67B7853CD7B0A288E1657301253"
CHECKS[ROCK_BC_FILE] = "8215B784DB3B93AE4E60FE56C24CA76DF15DECBB9FBDA688A6279AF7F79A21CE"
CHECKS[SAND_BC_FILE] = "F75127B8E6EF87EED13A70C9347621505E1C148C89FCAB3D94FC652916406E7E"
CHECKS[SAND_N_FILE] = "D9745C402982E5CDBED7D8F563E24200468970CC25EC896AF96963F4F6CA9843"
scope["CHECKS"] = CHECKS
scope["DIAG"] = DIAG
scope["RESULT"] = RESULT
scope["CAPTURE"] = CAPTURE
scope["namespace"]["CHECKS"] = CHECKS
scope["namespace"]["DIAG"] = DIAG
scope["namespace"]["RESULT"] = RESULT
scope["namespace"]["CAPTURE"] = CAPTURE

BaseR66 = scope["R66"]
require = scope["require"]
now = scope["now"]
sha256 = scope["sha256"]
atomic_json = scope["atomic_json"]
asset_path = scope["asset_path"]
dirty_packages = scope["dirty_packages"]
provider_gate = scope["provider_gate"]


def input_sources(material, node):
    names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(node)]
    sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, node))
    require(len(names) == len(sources), "input reflection mismatch")
    return dict(zip(names, sources))


def verify_surface():
    profile = unreal.EditorAssetLibrary.load_asset(PROFILE)
    source_parent = unreal.EditorAssetLibrary.load_asset(SOURCE_PARENT)
    source_mi = unreal.EditorAssetLibrary.load_asset(SOURCE_MI)
    target_parent = unreal.EditorAssetLibrary.load_asset(TARGET_PARENT)
    target_mi = unreal.EditorAssetLibrary.load_asset(TARGET_MI)
    require(profile is not None and profile.get_class().get_name() == "PlanetData", "ProfileV1 load failed")
    require(source_parent is not None and source_mi is not None, "protected source surface load failed")
    require(target_parent is not None and target_parent.get_class().get_name() == "Material", "R71 parent load failed")
    require(target_mi is not None and target_mi.get_class().get_name() == "MaterialInstanceConstant", "R71 MI load failed")
    require(asset_path(profile.get_editor_property("planet_material")) == TARGET_MI, "R71 planet material binding drift")
    require(asset_path(target_mi.get_editor_property("parent")) == TARGET_PARENT, "R71 MI parent drift")
    require(asset_path(source_mi.get_editor_property("parent")) == SOURCE_PARENT, "R67 protected source parent drift")

    nodes = list(unreal.MaterialEditingLibrary.get_material_expressions(target_parent))
    outputs = [node for node in nodes if node.get_class().get_name() == "MaterialExpressionPlanetBiomeMaterialOutput"]
    require(len(outputs) == 1, "R71 PlanetBiomeMaterialOutput count drift")
    output = outputs[0]
    require(str(output.get_editor_property("desc")) == "RedProfile.PresentationRoles;Order=Craters,Mountains,Desert,Hills,Poles,Ocean", "R71 output identity drift")
    sources = input_sources(target_parent, output)
    role_nodes = {role: sources.get(role) for role in ("Craters", "Mountains", "Desert", "Hills", "Poles", "Ocean")}
    require(all(role_nodes.values()), "R71 disconnected presentation role")
    mapping = {role: node.get_name() for role, node in role_nodes.items()}
    require(mapping == {
        "Craters": "MaterialExpressionMakeMaterialAttributes_9",
        "Mountains": "MaterialExpressionMakeMaterialAttributes_10",
        "Desert": "MaterialExpressionMakeMaterialAttributes_3",
        "Hills": "MaterialExpressionMakeMaterialAttributes_8",
        "Poles": "MaterialExpressionMakeMaterialAttributes_11",
        "Ocean": "MaterialExpressionMakeMaterialAttributes_12",
    }, "R71 role mapping drift: " + repr(mapping))
    require(role_nodes["Craters"] is not role_nodes["Mountains"], "R71 craters/mountains co-owned")
    require(role_nodes["Desert"] is not role_nodes["Hills"], "R71 desert/hills co-owned")
    return {
        "planet_material": TARGET_MI,
        "instance_parent": TARGET_PARENT,
        "role_mapping": mapping,
        "seed": int(profile.get_editor_property("generation_seed")),
        "source_parent_preserved": SOURCE_PARENT,
        "source_instance_preserved": SOURCE_MI,
    }


class R71(BaseR66):
    def __init__(self):
        super().__init__()
        self.report.update({
            "schema": "redmmo.profile_v1_role_surface.verify.r71.v1",
            "evidence_class": "real_gpu_visual",
            "slice": "R71 role-specific PPG surface with retained R66 no-palms and seeded grass",
        })

    def authenticate(self):
        self.report["serialized_surface"] = verify_surface()
        super().authenticate()

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in CHECKS.items():
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        require(CAPTURE.is_file() and CAPTURE.stat().st_size > 0, "capture missing")
        stable = self.report["lifecycle_analysis"]["readiness_stable"] and self.report["lifecycle_analysis"]["palm_zero_throughout"]
        self.report.update({
            "status": "PASS_R71_ROLE_SURFACE_FRESH_RELOAD_MAPCHECK_D3D12" if stable else "FAIL_R71_RUNTIME_DRIFT",
            "completed_utc": now(),
            "capture": {"path": str(CAPTURE), "bytes": CAPTURE.stat().st_size, "sha256": sha256(CAPTURE)},
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Fresh-reload MapCheck, runtime palm/grass census and one D3D12 player viewport for R71; full-planet role coverage, visual acceptance and packaged-build readiness are not claimed.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R71_VERIFY_" + ("PASS" if stable else "FAIL"))
        self.phase = "DONE"
        self.schedule_quit(3.0)


try:
    _R71 = R71()
    _R71.start()
    unreal.log("REDMMO_R71_VERIFY_STARTED")
except Exception as bootstrap_error:
    atomic_json(RESULT, {
        "schema": "redmmo.profile_v1_role_surface.verify.r71.v1",
        "status": "FAIL",
        "completed_utc": now(),
        "error": str(bootstrap_error),
    })
    unreal.SystemLibrary.quit_editor()
