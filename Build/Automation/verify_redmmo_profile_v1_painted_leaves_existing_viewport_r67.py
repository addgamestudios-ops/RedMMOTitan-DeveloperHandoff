"""Fresh-reload D3D12 proof for the R67 painted-leaf PPG surface branch."""

from __future__ import annotations

from pathlib import Path

import unreal


BASE_PATH = Path(r"D:\RedMMOTitan\Build\Automation\verify_redmmo_profile_v1_no_palms_existing_viewport_r66.py")
PROFILE_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset")
SOURCE_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\WorldAuthoring\PPG\ProfileV1\MI_PPG_ProfileV1_Surface.uasset")
TARGET_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_PaintedLeaves_R67.uasset")
BC_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\SoStylized\Environment\Landscape\Textures\T_Grass1_BC.uasset")
ROUGHNESS_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\SoStylized\Environment\Landscape\Textures\T_Grass1_R.uasset")
TARGET = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/MI_PPG_ProfileV1_PaintedLeaves_R67"
SOURCE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/MI_PPG_ProfileV1_Surface"
BC = "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_BC"
ROUGHNESS = "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_R"
FLAT_NORMAL = "/Engine/EngineMaterials/DefaultNormal"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1PaintedLeaves_R67_20260805T2202Z\Capture")
RESULT = DIAG / "result.json"
CAPTURE = DIAG / "R67_painted_leaves_uv24_no_palms_existing_viewport.png"


source = BASE_PATH.read_text(encoding="utf-8")
bootstrap = "\ntry:\n    _R66 = R66()"
if bootstrap not in source:
    raise RuntimeError("R66 bootstrap boundary missing")
scope = {"__name__": "redmmo_r66_base_for_r67", "__file__": str(BASE_PATH)}
exec(compile(source.split(bootstrap, 1)[0], str(BASE_PATH), "exec"), scope)

CHECKS = dict(scope["CHECKS"])
CHECKS[PROFILE_FILE] = "56EA5F830A8F581C1844B956EBABA556B45E200C397443F37BA921766862FC1A"
CHECKS[SOURCE_FILE] = "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66"
CHECKS[TARGET_FILE] = "745381295CDC76754B9FD347CC85CEBEC3151B042C366CDA40F1908163B8A4F7"
CHECKS[BC_FILE] = "A79C24EA6A1284E8E190CF46FF2349B9117B3A930A5C506C2D3764057890CF71"
CHECKS[ROUGHNESS_FILE] = "D0DF945E92DAE229AC684350D4C20FAD9783FE388C839BD14602A5277A445069"
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


def rgba(value):
    return [float(value.r), float(value.g), float(value.b), float(value.a)]


def verify_surface():
    profile = unreal.EditorAssetLibrary.load_asset(
        "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
    )
    source_instance = unreal.EditorAssetLibrary.load_asset(SOURCE)
    target = unreal.EditorAssetLibrary.load_asset(TARGET)
    require(profile is not None and profile.get_class().get_name() == "PlanetData", "ProfileV1 load failed")
    require(source_instance is not None and target is not None, "surface load failed")
    require(asset_path(profile.get_editor_property("planet_material")) == TARGET, "R67 planet material binding drift")
    require(asset_path(target.get_editor_property("parent")) == asset_path(source_instance.get_editor_property("parent")), "R67 parent drift")
    editing = unreal.MaterialEditingLibrary
    textures = {
        "R10L_StylizedGrass_BC": asset_path(editing.get_material_instance_texture_parameter_value(target, "R10L_StylizedGrass_BC")),
        "R10L_StylizedGrass_N": asset_path(editing.get_material_instance_texture_parameter_value(target, "R10L_StylizedGrass_N")),
        "R10L_StylizedGrass_ORM": asset_path(editing.get_material_instance_texture_parameter_value(target, "R10L_StylizedGrass_ORM")),
    }
    require(textures == {
        "R10L_StylizedGrass_BC": BC,
        "R10L_StylizedGrass_N": FLAT_NORMAL,
        "R10L_StylizedGrass_ORM": ROUGHNESS,
    }, "R67 texture binding drift")
    scalars = {
        name: float(editing.get_material_instance_scalar_parameter_value(target, name))
        for name in ("R10L_GroundUVScale", "R10L_NormalAmount", "R10L_GroundSpecular")
    }
    require(abs(scalars["R10L_GroundUVScale"] - 24.0) <= 0.0001, "R67 UV scale drift")
    require(abs(scalars["R10L_NormalAmount"]) <= 0.0001, "R67 normal amount drift")
    require(abs(scalars["R10L_GroundSpecular"] - 0.02) <= 0.0001, "R67 specular drift")
    vectors = {
        name: rgba(editing.get_material_instance_vector_parameter_value(target, name))
        for name in ("R10L_GroundTintA", "R10L_GroundTintB")
    }
    require(all(max(abs(component - 1.0) for component in value) <= 0.0001 for value in vectors.values()), "R67 tint drift")
    return {"planet_material": TARGET, "parent": asset_path(target.get_editor_property("parent")), "textures": textures, "scalars": scalars, "vectors": vectors}


class R67(BaseR66):
    def __init__(self):
        super().__init__()
        self.report.update({
            "schema": "redmmo.profile_v1_painted_leaves.verify.r67.v1",
            "evidence_class": "real_gpu_visual",
            "slice": "R67 painted-leaf UV24 ground with retained R66 no-palms and seeded grass",
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
            "status": "PASS_R67_PAINTED_LEAVES_FRESH_RELOAD_MAPCHECK_D3D12" if stable else "FAIL_R67_RUNTIME_DRIFT",
            "completed_utc": now(),
            "capture": {"path": str(CAPTURE), "bytes": CAPTURE.stat().st_size, "sha256": sha256(CAPTURE)},
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Fresh-reload MapCheck, runtime palm/grass census and D3D12 pixels for R67 only; visual retention still requires independent pixel review.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R67_VERIFY_" + ("PASS" if stable else "FAIL"))
        self.phase = "DONE"
        self.schedule_quit(3.0)


try:
    _R67 = R67()
    _R67.start()
    unreal.log("REDMMO_R67_VERIFY_STARTED")
except Exception as bootstrap_error:
    atomic_json(RESULT, {
        "schema": "redmmo.profile_v1_painted_leaves.verify.r67.v1",
        "status": "FAIL",
        "completed_utc": now(),
        "error": str(bootstrap_error),
    })
    unreal.SystemLibrary.quit_editor()
