"""Guarded R76 project-owned Oasis-look successor for native PPG water."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import time

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
CONTENT = PROJECT.parent / "Content"
HOME_FILE = CONTENT / "RedMMO" / "Maps" / "RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = CONTENT / "RedMMO" / "WorldAuthoring" / "PPG" / "ProfileV1" / "DA_PPG_ProfileV1_PlanetData.uasset"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1OasisWater_R76_20260806T0026Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1OasisWater_R76_20260806T0026Z\Apply")
RESULT = DIAG / "result.json"

EXPECTED_HOME = "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3"
EXPECTED_PROFILE = "E19F14597BA1B73C958F6022B92A41B0C1A5F61573390295D3EEBD7484DBC335"
PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
PPG_MASTER = "/PPG/Water/Materials/M_PlanetaryOceanWater"
OASIS_MI = "/Game/StylizedDesertOasis/Materials/Instances/Environment/MI_Water"
NORMAL_1 = "/Game/StylizedDesertOasis/Materials/MasterMaterials/UtilTextures/T_Water_01_N"
NORMAL_2 = "/Game/StylizedDesertOasis/Materials/MasterMaterials/UtilTextures/T_Water_02_N"
TARGET_DIR = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials"
TARGET_PARENT = TARGET_DIR + "/M_PPG_ProfileV1_OasisWater_R76"
TARGET_MI = TARGET_DIR + "/MI_PPG_ProfileV1_OasisWater_R76"
TARGET_PARENT_FILE = CONTENT / "RedMMO" / "WorldAuthoring" / "PPG" / "ProfileV1" / "Materials" / "M_PPG_ProfileV1_OasisWater_R76.uasset"
TARGET_MI_FILE = CONTENT / "RedMMO" / "WorldAuthoring" / "PPG" / "ProfileV1" / "Materials" / "MI_PPG_ProfileV1_OasisWater_R76.uasset"


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(obj):
    if not obj:
        return None
    return str(obj.get_path_name()).split(".", 1)[0]


def load(path, class_name):
    obj = unreal.EditorAssetLibrary.load_asset(path)
    require(obj is not None and obj.get_class().get_name() == class_name, "Load failed: " + path)
    return obj


def dirty_packages():
    return {
        "content": sorted(asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()),
        "maps": sorted(asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()),
    }


def provider_gate():
    state = {}
    for port in (11111, 5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.1)
        state[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        probe.close()
    require(all(state.values()), "Provider listener active")
    return state


def write_once(payload):
    DIAG.mkdir(parents=True, exist_ok=False)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with RESULT.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def create_parameter(material, cls, name, value, x, y, desc):
    node = unreal.MaterialEditingLibrary.create_material_expression(material, cls, x, y)
    require(node is not None, "Parameter creation failed: " + name)
    node.set_editor_property("parameter_name", unreal.Name(name))
    node.set_editor_property("default_value", value)
    node.set_editor_property("desc", desc)
    return node


def input_sources(material, node):
    names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(node)]
    sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, node))
    require(len(names) == len(sources), "Input reflection mismatch: " + node.get_name())
    return dict(zip(names, sources))


def color(value):
    return [float(value.r), float(value.g), float(value.b), float(value.a)]


def verify_checkpoint():
    manifest_path = ROLLBACK / "manifest.json"
    copy = ROLLBACK / "DA_PPG_ProfileV1_PlanetData.uasset"
    require(manifest_path.is_file() and copy.is_file(), "R76 checkpoint missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == "redmmo.rollback.profile_v1_oasis_water.r76.v1", "R76 checkpoint schema drift")
    require(sha256(copy) == EXPECTED_PROFILE, "R76 checkpoint preimage drift")
    return {"manifest": str(manifest_path), "manifest_sha256": sha256(manifest_path), "profile_copy_sha256": sha256(copy)}


_EXIT = {"handle": None}


def schedule_exit(delay=3.0):
    started = time.monotonic()

    def tick(_delta):
        if time.monotonic() - started < delay:
            return
        handle = _EXIT.get("handle")
        if handle is not None:
            unreal.unregister_slate_post_tick_callback(handle)
            _EXIT["handle"] = None
        unreal.SystemLibrary.quit_editor()

    _EXIT["handle"] = unreal.register_slate_post_tick_callback(tick)


def main():
    report = {
        "schema": "redmmo.ppg.profile_v1_oasis_water.apply.r76.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
        "rollback": str(ROLLBACK),
        "map_saved": False,
        "generation_called": False,
    }
    created_parent = False
    created_mi = False
    profile_saved = False
    original_water = None
    try:
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "Wrong project")
        require(not RESULT.exists() and not DIAG.exists(), "R76 apply no-clobber failed")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
        require(sha256(PROFILE_FILE) == EXPECTED_PROFILE, "ProfileV1 hash drift")
        require(not TARGET_PARENT_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(TARGET_PARENT), "R76 parent exists")
        require(not TARGET_MI_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(TARGET_MI), "R76 MI exists")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor started dirty")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "Renderer gate failed")
        require(unreal.EditorLevelLibrary.get_editor_world().get_path_name().startswith("/Engine/Maps/Entry.Entry"), "R76 apply not isolated on Entry")
        report["provider_gate_before"] = provider_gate()
        report["checkpoint"] = verify_checkpoint()

        source = load(PPG_MASTER, "Material")
        oasis_mi = load(OASIS_MI, "MaterialInstanceConstant")
        normal_1 = load(NORMAL_1, "Texture2D")
        normal_2 = load(NORMAL_2, "Texture2D")
        editing = unreal.MaterialEditingLibrary
        oasis_absorption = editing.get_material_instance_vector_parameter_value(oasis_mi, "Absorption Coefficient")

        target = unreal.EditorAssetLibrary.duplicate_asset(PPG_MASTER, TARGET_PARENT)
        require(target is not None and target.get_class().get_name() == "Material", "R76 parent duplicate failed")
        created_parent = True
        inherited_expression_count = len(list(editing.get_material_expressions(target)))
        inherited_scalar_names = {str(item) for item in editing.get_scalar_parameter_names(target)}
        inherited_texture_names = {str(item) for item in editing.get_texture_parameter_names(target)}
        require("PlanetRadius" in inherited_scalar_names and "HeightMap" in inherited_texture_names, "Inherited PPG interface missing")

        old_normal = editing.get_material_property_input_node(target, unreal.MaterialProperty.MP_NORMAL)
        old_base = editing.get_material_property_input_node(target, unreal.MaterialProperty.MP_BASE_COLOR)
        require(old_normal is not None and old_base is not None, "Inherited PPG visual roots missing")
        old_normal_output = str(editing.get_material_property_input_node_output_name(target, unreal.MaterialProperty.MP_NORMAL))
        old_base_output = str(editing.get_material_property_input_node_output_name(target, unreal.MaterialProperty.MP_BASE_COLOR))

        nodes = list(editing.get_material_expressions(target))
        water_outputs = [node for node in nodes if node.get_class().get_name() == "MaterialExpressionSingleLayerWaterMaterialOutput"]
        require(len(water_outputs) == 1, "Expected one inherited SingleLayerWater output")
        water_output = water_outputs[0]
        water_inputs = input_sources(target, water_output)
        absorption_input = next((name for name in water_inputs if "absorption" in name.lower()), None)
        require(absorption_input is not None and water_inputs[absorption_input] is not None, "Inherited absorption input missing")

        uv = editing.create_material_expression(target, unreal.MaterialExpressionTextureCoordinate, 3000, -900)
        tiling_1 = create_parameter(target, unreal.MaterialExpressionScalarParameter, "R76_OasisNormalTiling1", 64.0, 3000, -760, "R76.Oasis.NormalTiling1")
        tiling_2 = create_parameter(target, unreal.MaterialExpressionScalarParameter, "R76_OasisNormalTiling2", 96.0, 3000, -620, "R76.Oasis.NormalTiling2")
        scale_1 = editing.create_material_expression(target, unreal.MaterialExpressionMultiply, 3240, -900)
        scale_2 = editing.create_material_expression(target, unreal.MaterialExpressionMultiply, 3240, -660)
        panner_1 = editing.create_material_expression(target, unreal.MaterialExpressionPanner, 3480, -900)
        panner_2 = editing.create_material_expression(target, unreal.MaterialExpressionPanner, 3480, -660)
        panner_1.set_editor_property("speed_x", 0.014)
        panner_1.set_editor_property("speed_y", -0.009)
        panner_2.set_editor_property("speed_x", -0.010)
        panner_2.set_editor_property("speed_y", 0.012)
        sample_1 = editing.create_material_expression(target, unreal.MaterialExpressionTextureSampleParameter2D, 3720, -900)
        sample_2 = editing.create_material_expression(target, unreal.MaterialExpressionTextureSampleParameter2D, 3720, -660)
        sample_1.set_editor_property("parameter_name", unreal.Name("R76_OasisNormal1"))
        sample_2.set_editor_property("parameter_name", unreal.Name("R76_OasisNormal2"))
        sample_1.set_editor_property("texture", normal_1)
        sample_2.set_editor_property("texture", normal_2)
        sample_1.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        sample_2.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        oasis_mix = create_parameter(target, unreal.MaterialExpressionScalarParameter, "R76_OasisNormalMix", 0.5, 3720, -460, "R76.Oasis.NormalMix")
        oasis_lerp = editing.create_material_expression(target, unreal.MaterialExpressionLinearInterpolate, 3960, -780)
        overlay_amount = create_parameter(target, unreal.MaterialExpressionScalarParameter, "R76_OasisNormalAmount", 0.42, 3960, -500, "R76.Oasis.NormalAmount")
        normal_lerp = editing.create_material_expression(target, unreal.MaterialExpressionLinearInterpolate, 4200, -700)

        surface_tint = create_parameter(target, unreal.MaterialExpressionVectorParameter, "R76_SurfaceTint", unreal.LinearColor(0.03, 0.32, 0.36, 1.0), 3720, -260, "R76.Oasis.SurfaceTint")
        surface_amount = create_parameter(target, unreal.MaterialExpressionScalarParameter, "R76_SurfaceTintAmount", 0.38, 3720, -100, "R76.Oasis.SurfaceTintAmount")
        surface_lerp = editing.create_material_expression(target, unreal.MaterialExpressionLinearInterpolate, 4200, -200)
        absorption = create_parameter(target, unreal.MaterialExpressionVectorParameter, "R76_AbsorptionCoefficient", oasis_absorption, 3960, 120, "R76.Oasis.AbsorptionCoefficient")

        links = [
            (editing.connect_material_expressions(uv, "", scale_1, "A"), "uv-scale1"),
            (editing.connect_material_expressions(tiling_1, "", scale_1, "B"), "tiling1"),
            (editing.connect_material_expressions(uv, "", scale_2, "A"), "uv-scale2"),
            (editing.connect_material_expressions(tiling_2, "", scale_2, "B"), "tiling2"),
            (editing.connect_material_expressions(scale_1, "", panner_1, "Coordinate"), "scale1-panner"),
            (editing.connect_material_expressions(scale_2, "", panner_2, "Coordinate"), "scale2-panner"),
            (editing.connect_material_expressions(panner_1, "", sample_1, "UVs"), "panner1-sample"),
            (editing.connect_material_expressions(panner_2, "", sample_2, "UVs"), "panner2-sample"),
            (editing.connect_material_expressions(sample_1, "RGB", oasis_lerp, "A"), "normal1-oasis"),
            (editing.connect_material_expressions(sample_2, "RGB", oasis_lerp, "B"), "normal2-oasis"),
            (editing.connect_material_expressions(oasis_mix, "", oasis_lerp, "Alpha"), "oasis-mix"),
            (editing.connect_material_expressions(old_normal, old_normal_output, normal_lerp, "A"), "ppg-normal"),
            (editing.connect_material_expressions(oasis_lerp, "", normal_lerp, "B"), "oasis-normal"),
            (editing.connect_material_expressions(overlay_amount, "", normal_lerp, "Alpha"), "normal-amount"),
            (editing.connect_material_expressions(old_base, old_base_output, surface_lerp, "A"), "ppg-base"),
            (editing.connect_material_expressions(surface_tint, "", surface_lerp, "B"), "surface-tint"),
            (editing.connect_material_expressions(surface_amount, "", surface_lerp, "Alpha"), "surface-amount"),
            (editing.connect_material_expressions(absorption, "", water_output, absorption_input), "absorption"),
            (editing.connect_material_property(normal_lerp, "", unreal.MaterialProperty.MP_NORMAL), "normal-output"),
            (editing.connect_material_property(surface_lerp, "", unreal.MaterialProperty.MP_BASE_COLOR), "base-output"),
        ]
        failed = [name for ok, name in links if not ok]
        require(not failed, "R76 material links failed: " + ",".join(failed))
        editing.recompile_material(target)
        require(unreal.EditorAssetLibrary.save_loaded_asset(target, only_if_is_dirty=False), "R76 parent save failed")

        target_mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            "MI_PPG_ProfileV1_OasisWater_R76", TARGET_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew()
        )
        require(target_mi is not None and target_mi.get_class().get_name() == "MaterialInstanceConstant", "R76 MI creation failed")
        created_mi = True
        editing.set_material_instance_parent(target_mi, target)
        editing.set_material_instance_texture_parameter_value(target_mi, "R76_OasisNormal1", normal_1)
        editing.set_material_instance_texture_parameter_value(target_mi, "R76_OasisNormal2", normal_2)
        editing.set_material_instance_vector_parameter_value(target_mi, "R76_AbsorptionCoefficient", oasis_absorption)
        editing.set_material_instance_vector_parameter_value(target_mi, "R76_SurfaceTint", unreal.LinearColor(0.03, 0.32, 0.36, 1.0))
        for name, value in {
            "R76_OasisNormalTiling1": 64.0,
            "R76_OasisNormalTiling2": 96.0,
            "R76_OasisNormalMix": 0.5,
            "R76_OasisNormalAmount": 0.42,
            "R76_SurfaceTintAmount": 0.38,
        }.items():
            editing.set_material_instance_scalar_parameter_value(target_mi, name, value)
        editing.update_material_instance(target_mi)
        require(unreal.EditorAssetLibrary.save_loaded_asset(target_mi, only_if_is_dirty=False), "R76 MI save failed")

        profile = load(PROFILE, "PlanetData")
        require(int(profile.get_editor_property("generation_seed")) == 1337, "Seed drift")
        require(bool(profile.get_editor_property("generate_water")), "Water generation disabled")
        original_water = profile.get_editor_property("water_material")
        require(asset_path(original_water) == PPG_MASTER, "Source water binding drift")
        profile.set_editor_property("water_material", target_mi)
        require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "ProfileV1 save failed")
        profile_saved = True

        verified_parent = load(TARGET_PARENT, "Material")
        verified_mi = load(TARGET_MI, "MaterialInstanceConstant")
        verified_profile = load(PROFILE, "PlanetData")
        scalar_names = {str(item) for item in editing.get_scalar_parameter_names(verified_mi)}
        texture_names = {str(item) for item in editing.get_texture_parameter_names(verified_mi)}
        require("PlanetRadius" in scalar_names and "HeightMap" in texture_names, "R76 inherited native interface missing")
        require(asset_path(verified_profile.get_editor_property("water_material")) == TARGET_MI, "R76 binding did not persist")
        require(asset_path(verified_mi.get_editor_property("parent")) == TARGET_PARENT, "R76 MI parent drift")
        require(dirty_packages() == {"content": [], "maps": []}, "Dirty packages after R76 apply")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map changed")

        report.update({
            "status": "PASS_R76_PROJECT_OWNED_PPG_OASIS_WATER_APPLIED",
            "completed_utc": now(),
            "profile_sha256_after": sha256(PROFILE_FILE),
            "home_sha256_after": sha256(HOME_FILE),
            "target_parent_sha256": sha256(TARGET_PARENT_FILE),
            "target_mi_sha256": sha256(TARGET_MI_FILE),
            "target_parent": TARGET_PARENT,
            "target_mi": TARGET_MI,
            "water_binding_before": PPG_MASTER,
            "water_binding_after": asset_path(verified_profile.get_editor_property("water_material")),
            "oasis_absorption": color(oasis_absorption),
            "oasis_normals": [NORMAL_1, NORMAL_2],
            "inherited_expression_count": inherited_expression_count,
            "expression_count_after": len(list(editing.get_material_expressions(verified_parent))),
            "native_interface": {"HeightMap": True, "PlanetRadius": True},
            "controls": {
                "R76_OasisNormalTiling1": 64.0,
                "R76_OasisNormalTiling2": 96.0,
                "R76_OasisNormalMix": 0.5,
                "R76_OasisNormalAmount": 0.42,
                "R76_SurfaceTint": [0.03, 0.32, 0.36, 1.0],
                "R76_SurfaceTintAmount": 0.38,
            },
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Asset creation and serialized ProfileV1 binding only; fresh reload, native water runtime components and real-GPU shoreline appearance remain unproven.",
        })
        write_once(report)
        unreal.log_warning("REDMMO_R76_APPLY_PASS " + report["status"])
    except Exception as exc:
        report.update({"status": "FAIL_R76_APPLY", "error": repr(exc), "completed_utc": now()})
        try:
            if profile_saved and original_water is not None:
                profile = unreal.EditorAssetLibrary.load_asset(PROFILE)
                if profile:
                    profile.set_editor_property("water_material", original_water)
                    unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False)
            if created_mi and unreal.EditorAssetLibrary.does_asset_exist(TARGET_MI):
                unreal.EditorAssetLibrary.delete_asset(TARGET_MI)
            if created_parent and unreal.EditorAssetLibrary.does_asset_exist(TARGET_PARENT):
                unreal.EditorAssetLibrary.delete_asset(TARGET_PARENT)
            if not DIAG.exists():
                write_once(report)
        finally:
            unreal.log_error("REDMMO_R76_APPLY_FAIL " + repr(exc))
    schedule_exit()


main()
