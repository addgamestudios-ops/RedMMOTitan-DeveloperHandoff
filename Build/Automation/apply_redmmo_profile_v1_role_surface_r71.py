"""Create and bind the project-owned R71 role-specific PPG surface.

The current source parent and R67 material instance remain byte-identical. The
new parent reconnects only the six PlanetBiomeMaterialOutput presentation
inputs so the global R10 stylized layer no longer masks every biome. Terrain,
seed, water, foliage bindings and seeded placements are not edited.
"""

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
CONTENT = PROJECT.parent / "Content"
HOME_FILE = CONTENT / r"RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
SOURCE_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_SurfaceParent.uasset"
SOURCE_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_PaintedLeaves_R67.uasset"
R66_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_NoPalms_R66.uasset"
ROCK_BC_FILE = CONTENT / r"StylizedRocksPack_01\DetailTextures\T_Rock_Painterly_01_BC.uasset"
SAND_BC_FILE = CONTENT / r"SoStylized\Environment\Landscape\Textures\T_DesertSand_BC.uasset"
SAND_N_FILE = CONTENT / r"SoStylized\Environment\Landscape\Textures\T_DesertSand_N.uasset"
TARGET_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_RoleSurface_R71.uasset"
TARGET_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_RoleSurface_R71.uasset"
PROTECTED_TEST = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap")
PROTECTED_FUSED = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap")
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1RoleSurface_R71_20260805T2300Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1RoleSurface_R71_20260805T2300Z\Apply")
RESULT = DIAG / "result.json"

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
PROFILE = ROOT + "/DA_PPG_ProfileV1_PlanetData"
SOURCE_PARENT = ROOT + "/M_PPG_ProfileV1_SurfaceParent"
SOURCE_MI = ROOT + "/Materials/MI_PPG_ProfileV1_PaintedLeaves_R67"
R66 = ROOT + "/Profiles/DA_PPG_ProfileV1_NoPalms_R66"
TARGET_PARENT = ROOT + "/Materials/M_PPG_ProfileV1_RoleSurface_R71"
TARGET_MI = ROOT + "/Materials/MI_PPG_ProfileV1_RoleSurface_R71"
ROCK_BC = "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_Painterly_01_BC"
SAND_BC = "/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_BC"
SAND_N = "/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_N"

EXPECTED = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "56EA5F830A8F581C1844B956EBABA556B45E200C397443F37BA921766862FC1A",
    SOURCE_PARENT_FILE: "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768",
    SOURCE_MI_FILE: "745381295CDC76754B9FD347CC85CEBEC3151B042C366CDA40F1908163B8A4F7",
    R66_FILE: "C0EE6CB0A2D9D679D1FB4D64747555D55A5AF18ABED4AEC2666A1D5BECDA97DC",
    ROCK_BC_FILE: "8215B784DB3B93AE4E60FE56C24CA76DF15DECBB9FBDA688A6279AF7F79A21CE",
    SAND_BC_FILE: "F75127B8E6EF87EED13A70C9347621505E1C148C89FCAB3D94FC652916406E7E",
    SAND_N_FILE: "D9745C402982E5CDBED7D8F563E24200468970CC25EC896AF96963F4F6CA9843",
    PROTECTED_TEST: "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    PROTECTED_FUSED: "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
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


def normalized(value):
    return str(value).replace("_", "").replace(" ", "").lower()


def field(value, wanted):
    values = value.to_dict()
    target = normalized(wanted)
    matches = [item for key, item in values.items() if normalized(key) in (target, "b" + target)]
    require(len(matches) == 1, "missing reflected field " + wanted)
    return matches[0]


def dirty_packages():
    return {
        "content": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}),
        "maps": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}),
    }


def provider_gate():
    state = {}
    for port in (11111, 5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            state[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(state.values()), "provider listener active: " + repr(state))
    return state


def load(path, class_name):
    value = unreal.EditorAssetLibrary.load_asset(path)
    require(value is not None and value.get_class().get_name() == class_name, "load failed: " + path)
    return value


def by_name(nodes, name, class_name=None):
    matches = [node for node in nodes if node.get_name() == name]
    require(len(matches) == 1, "expected exact node " + name)
    if class_name:
        require(matches[0].get_class().get_name() == class_name, "class drift for " + name)
    return matches[0]


def input_sources(material, node):
    names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(node)]
    sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, node))
    require(len(names) == len(sources), "input reflection mismatch for " + node.get_name())
    return dict(zip(names, sources))


def verify_r66(profile):
    require(int(profile.get_editor_property("generation_seed")) == 1337, "ProfileV1 seed drift")
    bindings = []
    for biome in list(profile.get_editor_property("biome_data")):
        bindings.append({"name": str(field(biome, "name")), "foliage_data": asset_path(field(biome, "foliage_data"))})
    require([item["name"] for item in bindings if item["foliage_data"] == R66] == ["Craters", "Hills", "Mountains"], "R66 binding drift")
    return bindings


def create_parameter(material, cls, name, value, x, y, desc):
    node = unreal.MaterialEditingLibrary.create_material_expression(material, cls, x, y)
    require(node is not None, "create failed: " + name)
    node.set_editor_property("parameter_name", unreal.Name(name))
    node.set_editor_property("default_value", value)
    node.set_editor_property("desc", desc)
    return node


def main():
    report = {
        "schema": "redmmo.profile_v1_role_surface.apply.r71.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
        "rollback": str(ROLLBACK),
        "map_saved": False,
        "generation_called": False,
    }
    parent_created = False
    mi_created = False
    profile_saved = False
    try:
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists(), "R71 result no-clobber failed")
        require(not TARGET_PARENT_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(TARGET_PARENT), "R71 parent exists")
        require(not TARGET_MI_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(TARGET_MI), "R71 MI exists")
        require(ROLLBACK.is_dir() and (ROLLBACK / "manifest.yaml").is_file(), "rollback missing")
        for path, expected in EXPECTED.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        for path in (PROFILE_FILE, SOURCE_PARENT_FILE, SOURCE_MI_FILE, R66_FILE, HOME_FILE):
            copy = ROLLBACK / path.name
            require(copy.is_file() and sha256(copy) == EXPECTED[path], "rollback preimage mismatch: " + path.name)
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "apply renderer gate failed")
        report["provider_gate_before"] = provider_gate()

        profile = load(PROFILE, "PlanetData")
        bindings = verify_r66(profile)
        require(asset_path(profile.get_editor_property("planet_material")) == SOURCE_MI, "R67 source binding drift")
        source_parent = load(SOURCE_PARENT, "Material")
        source_mi = load(SOURCE_MI, "MaterialInstanceConstant")
        require(asset_path(source_mi.get_editor_property("parent")) == SOURCE_PARENT, "R67 parent drift")

        parent = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_PARENT, TARGET_PARENT)
        require(parent is not None and parent.get_class().get_name() == "Material", "R71 parent duplicate failed")
        parent_created = True
        nodes = list(unreal.MaterialEditingLibrary.get_material_expressions(parent))
        output_nodes = [node for node in nodes if node.get_class().get_name() == "MaterialExpressionPlanetBiomeMaterialOutput"]
        require(len(output_nodes) == 1, "expected one PlanetBiomeMaterialOutput")
        output = output_nodes[0]
        require(str(output.get_editor_property("desc")) == "RedProfile.PresentationRoles;Order=Craters,Mountains,Desert,Hills,Poles,Ocean", "output identity drift")
        before = input_sources(parent, output)
        for role in ("Craters", "Mountains", "Desert", "Hills", "Poles", "Ocean"):
            require(before.get(role) is not None, "missing source role " + role)

        uv = by_name(nodes, "MaterialExpressionMultiply_16", "MaterialExpressionMultiply")
        hills = by_name(nodes, "MaterialExpressionMakeMaterialAttributes_8", "MaterialExpressionMakeMaterialAttributes")
        desert = by_name(nodes, "MaterialExpressionMakeMaterialAttributes_3", "MaterialExpressionMakeMaterialAttributes")
        desert_bc = by_name(nodes, "MaterialExpressionTextureSample_3", "MaterialExpressionTextureSample")
        flat_normal = by_name(nodes, "MaterialExpressionVectorParameter_8", "MaterialExpressionVectorParameter")

        editing = unreal.MaterialEditingLibrary
        rock_sample = editing.create_material_expression(parent, unreal.MaterialExpressionTextureSampleParameter2D, 1250, 420)
        require(rock_sample is not None, "rock sample creation failed")
        rock_sample.set_editor_property("parameter_name", unreal.Name("R71_RockPainterly_BC"))
        rock_sample.set_editor_property("texture", load(ROCK_BC, "Texture2D"))
        rock_sample.set_editor_property("desc", "R71.PainterlyRock.BaseColor")
        require(editing.connect_material_expressions(uv, "", rock_sample, "UVs"), "rock UV connection failed")

        roughness = create_parameter(parent, unreal.MaterialExpressionScalarParameter, "R71_SurfaceRoughness", 0.82, 1500, 760, "R71.SharedRoughness")
        specular = create_parameter(parent, unreal.MaterialExpressionScalarParameter, "R71_SurfaceSpecular", 0.02, 1500, 900, "R71.SharedSpecular")

        def role_attributes(role, base_source, tint, x, y):
            tint_node = create_parameter(parent, unreal.MaterialExpressionVectorParameter, "R71_" + role + "Tint", unreal.LinearColor(*tint), x, y, "R71." + role + ".Tint")
            multiply = editing.create_material_expression(parent, unreal.MaterialExpressionMultiply, x + 230, y)
            attrs = editing.create_material_expression(parent, unreal.MaterialExpressionMakeMaterialAttributes, x + 470, y)
            require(multiply is not None and attrs is not None, "role node creation failed: " + role)
            multiply.set_editor_property("desc", "R71." + role + ".TintedBaseColor")
            attrs.set_editor_property("desc", "R71." + role + ".Attributes")
            require(editing.connect_material_expressions(base_source, "", multiply, "A"), "base connection failed: " + role)
            require(editing.connect_material_expressions(tint_node, "", multiply, "B"), "tint connection failed: " + role)
            require(editing.connect_material_expressions(multiply, "", attrs, "BaseColor"), "base-color attributes failed: " + role)
            require(editing.connect_material_expressions(flat_normal, "", attrs, "Normal"), "flat-normal attributes failed: " + role)
            require(editing.connect_material_expressions(roughness, "", attrs, "Roughness"), "roughness attributes failed: " + role)
            require(editing.connect_material_expressions(specular, "", attrs, "Specular"), "specular attributes failed: " + role)
            return attrs

        craters = role_attributes("Craters", rock_sample, (0.72, 0.62, 0.58, 1.0), 1250, 1100)
        mountains = role_attributes("Mountains", rock_sample, (0.62, 0.68, 0.78, 1.0), 1250, 1500)
        poles = role_attributes("Poles", rock_sample, (1.00, 1.04, 1.12, 1.0), 1250, 1900)
        ocean = role_attributes("Ocean", desert_bc, (0.72, 0.92, 0.88, 1.0), 1250, 2300)
        role_sources = {
            "Craters": craters,
            "Mountains": mountains,
            "Desert": desert,
            "Hills": hills,
            "Poles": poles,
            "Ocean": ocean,
        }
        for role, source in role_sources.items():
            require(editing.disconnect_material_expressions(output, role), "disconnect failed: " + role)
            require(editing.connect_material_expressions(source, "", output, role), "output connection failed: " + role)
        after = input_sources(parent, output)
        require({role: after[role].get_name() for role in role_sources} == {role: source.get_name() for role, source in role_sources.items()}, "R71 output mapping mismatch")

        editing.recompile_material(parent)
        require(unreal.EditorAssetLibrary.save_loaded_asset(parent, only_if_is_dirty=False), "R71 parent save failed")

        target_mi = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_MI, TARGET_MI)
        require(target_mi is not None and target_mi.get_class().get_name() == "MaterialInstanceConstant", "R71 MI duplicate failed")
        mi_created = True
        editing.set_material_instance_parent(target_mi, parent)
        editing.update_material_instance(target_mi)
        require(unreal.EditorAssetLibrary.save_loaded_asset(target_mi, only_if_is_dirty=False), "R71 MI save failed")
        require(asset_path(target_mi.get_editor_property("parent")) == TARGET_PARENT, "R71 MI parent did not persist")

        profile.set_editor_property("planet_material", target_mi)
        require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "ProfileV1 save failed")
        profile_saved = True
        require(dirty_packages() == {"content": [], "maps": []}, "dirty packages after save")

        reloaded_profile = load(PROFILE, "PlanetData")
        require(asset_path(reloaded_profile.get_editor_property("planet_material")) == TARGET_MI, "R71 binding did not persist")
        verify_r66(reloaded_profile)
        require(TARGET_PARENT_FILE.is_file() and TARGET_MI_FILE.is_file(), "R71 package missing")
        for path, expected in EXPECTED.items():
            if path != PROFILE_FILE:
                require(sha256(path) == expected, "unrelated post-save drift: " + str(path))

        report.update({
            "status": "PASS_R71_ROLE_SURFACE_BOUND_PENDING_FRESH_RELOAD",
            "completed_utc": now(),
            "target_parent": TARGET_PARENT,
            "target_parent_sha256": sha256(TARGET_PARENT_FILE),
            "target_instance": TARGET_MI,
            "target_instance_sha256": sha256(TARGET_MI_FILE),
            "profile_sha256_before": EXPECTED[PROFILE_FILE],
            "profile_sha256_after": sha256(PROFILE_FILE),
            "source_parent_sha256_before_after": sha256(SOURCE_PARENT_FILE),
            "source_r67_sha256_before_after": sha256(SOURCE_MI_FILE),
            "home_map_sha256_before_after": sha256(HOME_FILE),
            "seed": 1337,
            "r66_bindings": bindings,
            "role_sources": {role: source.get_name() for role, source in role_sources.items()},
            "role_assets": {
                "Hills": "R67 painted SoStylized T_Grass1 closure",
                "Desert": [SAND_BC, SAND_N],
                "Craters": ROCK_BC,
                "Mountains": ROCK_BC,
                "Poles": ROCK_BC,
                "Ocean": SAND_BC,
            },
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Serialized R71 role-specific surface parent/instance and ProfileV1 binding only; fresh reload, one regeneration, MapCheck, runtime census and D3D12 visual review remain pending.",
        })
        atomic_json(RESULT, report)
        unreal.log("REDMMO_R71_APPLY_PASS")
    except Exception as error:
        rollback = {"attempted": True, "profile_rebound_r67": False, "target_mi_deleted": False, "target_parent_deleted": False}
        try:
            if profile_saved:
                profile = load(PROFILE, "PlanetData")
                profile.set_editor_property("planet_material", load(SOURCE_MI, "MaterialInstanceConstant"))
                require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "rollback ProfileV1 save failed")
            rollback["profile_rebound_r67"] = asset_path(load(PROFILE, "PlanetData").get_editor_property("planet_material")) == SOURCE_MI
            if mi_created or unreal.EditorAssetLibrary.does_asset_exist(TARGET_MI):
                rollback["target_mi_deleted"] = bool(unreal.EditorAssetLibrary.delete_asset(TARGET_MI))
            else:
                rollback["target_mi_deleted"] = not TARGET_MI_FILE.exists()
            if parent_created or unreal.EditorAssetLibrary.does_asset_exist(TARGET_PARENT):
                rollback["target_parent_deleted"] = bool(unreal.EditorAssetLibrary.delete_asset(TARGET_PARENT))
            else:
                rollback["target_parent_deleted"] = not TARGET_PARENT_FILE.exists()
        except Exception as rollback_error:
            rollback["error"] = str(rollback_error)
        report.update({
            "status": "FAIL_ROLLED_BACK" if all(rollback.get(key) for key in ("profile_rebound_r67", "target_mi_deleted", "target_parent_deleted")) else "FAIL_ROLLBACK_INCOMPLETE",
            "completed_utc": now(),
            "error": str(error),
            "traceback": traceback.format_exc(),
            "rollback_result": rollback,
        })
        if not RESULT.exists():
            atomic_json(RESULT, report)
        unreal.log_error("REDMMO_R71_APPLY_FAIL " + str(error))
    finally:
        unreal.SystemLibrary.quit_editor()


main()
