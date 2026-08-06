"""Create and bind the rollback-backed R80 ProfileV1 shoreline successor.

R80 changes only project-owned surface material packages plus the ProfileV1
planet_material pointer.  It samples the already runtime-bound PPG BiomeMap
alpha with the terrain triangle convention and uses that exact datum to tint
the existing painted Desert sand into wet and submerged bands.  No map, seed,
topology, water geometry/material, foliage, placement, or vendor asset changes.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
CONTENT = PROJECT.parent / "Content"
HOME_FILE = CONTENT / r"RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
SOURCE_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_BiomePresentation_R73.uasset"
SOURCE_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_BiomePresentation_R73.uasset"
WATER_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_OasisWater_R78.uasset"
WATER_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_OasisWater_R78.uasset"
TARGET_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_ShorelineBands_R80.uasset"
TARGET_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_ShorelineBands_R80.uasset"
PROTECTED_TEST = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap")
PROTECTED_FUSED = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap")
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1ShorelineBands_R80_20260806T0150Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1ShorelineBands_R80_20260806T0150Z\Apply2")
RESULT = DIAG / "result.json"

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
PROFILE = ROOT + "/DA_PPG_ProfileV1_PlanetData"
SOURCE_PARENT = ROOT + "/Materials/M_PPG_ProfileV1_BiomePresentation_R73"
SOURCE_MI = ROOT + "/Materials/MI_PPG_ProfileV1_BiomePresentation_R73"
WATER_MI = ROOT + "/Materials/MI_PPG_ProfileV1_OasisWater_R78"
TARGET_PARENT = ROOT + "/Materials/M_PPG_ProfileV1_ShorelineBands_R80"
TARGET_MI = ROOT + "/Materials/MI_PPG_ProfileV1_ShorelineBands_R80"

EXPECTED = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "AA3B15F4538145C6B51B589D6B8F3E40899ACC136F573101E86C5790783E22C2",
    SOURCE_PARENT_FILE: "8D33435C91E0FE4813D5077991EDC6990AD5257395F67D6F5FDACBCE4F260992",
    SOURCE_MI_FILE: "17C83A43FCB0AB9B22AC7EF499D53A8B7B2435B3F709CA585374E64F48371E91",
    WATER_PARENT_FILE: "B815972272713EDEC40A6CF33591E2FEF05F54D575C6049B29983330D23022F1",
    WATER_MI_FILE: "2D3DFCC7583CABBCC551DD7D08A2CF5E33CC19465D14EAB5C4308DEC018DAE9A",
    PROTECTED_TEST: "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    PROTECTED_FUSED: "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

MASK_CODE = r"""
uint Width = 1u;
uint Height = 2u;
BiomeMap.GetDimensions(Width, Height);
uint VertexHeight = max(Height / 2u, 1u);
float2 Grid = saturate(UV) * float2(max(Width, 1u) - 1u, VertexHeight - 1u);
float2 GridFloor = floor(Grid);
float2 Fraction = saturate(Grid - GridFloor);
uint2 MaxCoordinate = uint2(max(Width, 1u) - 1u, VertexHeight - 1u);
uint2 Coordinate00 = min(uint2(GridFloor), MaxCoordinate);
uint2 Coordinate10 = min(Coordinate00 + uint2(1u, 0u), MaxCoordinate);
uint2 Coordinate01 = min(Coordinate00 + uint2(0u, 1u), MaxCoordinate);
uint2 Coordinate11 = min(Coordinate00 + uint2(1u, 1u), MaxCoordinate);
float4 SampleWeights;
if (Fraction.x + Fraction.y <= 1.0)
{
    SampleWeights = float4(1.0 - Fraction.x - Fraction.y, Fraction.x, Fraction.y, 0.0);
}
else
{
    SampleWeights = float4(0.0, 1.0 - Fraction.y, 1.0 - Fraction.x, Fraction.x + Fraction.y - 1.0);
}
float4 SeaSamples = float4(
    saturate(BiomeMap.Load(int3(int2(Coordinate00), 0)).a),
    saturate(BiomeMap.Load(int3(int2(Coordinate10), 0)).a),
    saturate(BiomeMap.Load(int3(int2(Coordinate01), 0)).a),
    saturate(BiomeMap.Load(int3(int2(Coordinate11), 0)).a));
float SeaAlpha = saturate(dot(SeaSamples, SampleWeights));
float Depth = saturate(1.0 - SeaAlpha);
float Underwater = smoothstep(0.0005, 0.0025, Depth);
float SafeFeather = max(Feather, 0.0005);
float Submerged = Underwater * smoothstep(max(WetDepth - SafeFeather, 0.0025), WetDepth + SafeFeather, Depth);
float Wet = Underwater * (1.0 - Submerged);
float Dry = saturate(1.0 - Wet - Submerged);
return float3(Dry, Wet, Submerged);
"""


def require(value, message):
    if not value:
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


def input_sources(material, node):
    editing = unreal.MaterialEditingLibrary
    names = [str(value) for value in editing.get_material_expression_input_names(node)]
    sources = list(editing.get_inputs_for_material_expression(material, node))
    require(len(names) == len(sources), "input reflection mismatch: " + node.get_name())
    return dict(zip(names, sources))


def by_name(nodes, name, class_name):
    matches = [node for node in nodes if node.get_name() == name and node.get_class().get_name() == class_name]
    require(len(matches) == 1, "node identity drift: " + name)
    return matches[0]


def by_desc(nodes, desc, class_name):
    matches = []
    for node in nodes:
        if node.get_class().get_name() != class_name:
            continue
        try:
            value = str(node.get_editor_property("desc"))
        except Exception:
            value = ""
        if value == desc:
            matches.append(node)
    require(len(matches) == 1, "node description drift: " + desc)
    return matches[0]


def create_parameter(material, cls, name, value, x, y, desc):
    node = unreal.MaterialEditingLibrary.create_material_expression(material, cls, x, y)
    require(node is not None, "parameter creation failed: " + name)
    node.set_editor_property("parameter_name", unreal.Name(name))
    node.set_editor_property("default_value", value)
    node.set_editor_property("desc", desc)
    return node


def verify_checkpoint():
    manifest_path = ROLLBACK / "manifest.json"
    require(manifest_path.is_file(), "R80 checkpoint manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == "redmmo.ppg.profile_v1_shoreline_bands.rollback.r80.v1", "checkpoint schema drift")
    records = manifest.get("records")
    require(isinstance(records, list) and len(records) == len(EXPECTED), "checkpoint record count drift")
    by_source = {str(Path(item["source"]).resolve(strict=True)): item for item in records}
    for path, expected in EXPECTED.items():
        item = by_source.get(str(path.resolve(strict=True)))
        require(item is not None and item.get("sha256") == expected, "checkpoint source mismatch: " + str(path))
        copy = Path(item["copy"])
        require(copy.is_file() and sha256(copy) == expected, "checkpoint copy mismatch: " + str(path))
    return str(manifest_path)


_EXIT = {"handle": None}


def schedule_exit(delay=6.0):
    started = time.monotonic()

    def tick(_delta):
        if time.monotonic() - started < delay:
            return
        handle = _EXIT.get("handle")
        if handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(handle)
            except Exception:
                pass
            _EXIT["handle"] = None
        unreal.SystemLibrary.quit_editor()

    _EXIT["handle"] = unreal.register_slate_post_tick_callback(tick)


def main():
    report = {
        "schema": "redmmo.ppg.profile_v1_shoreline_bands.apply.r80.v1",
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
        require(not RESULT.exists(), "R80 result no-clobber failed")
        for path, expected in EXPECTED.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        require(not TARGET_PARENT_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(TARGET_PARENT), "R80 parent exists")
        require(not TARGET_MI_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(TARGET_MI), "R80 MI exists")
        report["rollback_manifest"] = verify_checkpoint()
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        report["provider_gate_before"] = provider_gate()

        profile = load(PROFILE, "PlanetData")
        require(int(profile.get_editor_property("generation_seed")) == 1337, "ProfileV1 seed drift")
        require(asset_path(profile.get_editor_property("planet_material")) == SOURCE_MI, "R73 surface binding drift")
        require(asset_path(profile.get_editor_property("water_material")) == WATER_MI, "R78 water binding drift")
        source_parent = load(SOURCE_PARENT, "Material")
        source_mi = load(SOURCE_MI, "MaterialInstanceConstant")
        require(asset_path(source_mi.get_editor_property("parent")) == SOURCE_PARENT, "R73 MI parent drift")

        parent = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_PARENT, TARGET_PARENT)
        require(parent is not None and parent.get_class().get_name() == "Material", "R80 parent duplicate failed")
        parent_created = True
        editing = unreal.MaterialEditingLibrary
        nodes = list(editing.get_material_expressions(parent))
        outputs = [node for node in nodes if node.get_class().get_name() == "MaterialExpressionPlanetBiomeMaterialOutput"]
        require(len(outputs) == 1, "R80 output node count drift")
        output = outputs[0]
        role_before = input_sources(parent, output)
        require(all(role_before.get(role) is not None for role in ("Craters", "Mountains", "Desert", "Hills", "Poles", "Ocean")), "R80 inherited role wiring incomplete")

        desert_attrs = by_name(nodes, "MaterialExpressionMakeMaterialAttributes_3", "MaterialExpressionMakeMaterialAttributes")
        ocean_attrs = by_desc(nodes, "R71.Ocean.Attributes", "MaterialExpressionMakeMaterialAttributes")
        desert_inputs = input_sources(parent, desert_attrs)
        ocean_inputs = input_sources(parent, ocean_attrs)
        dry_base = desert_inputs.get("BaseColor")
        require(dry_base is not None and ocean_inputs.get("BaseColor") is not None, "R80 inherited BaseColor wiring incomplete")

        biome_map = editing.create_material_expression(parent, unreal.MaterialExpressionTextureObjectParameter, 2260, 2760)
        require(biome_map is not None, "R80 BiomeMap texture object creation failed")
        biome_map.set_editor_property("parameter_name", unreal.Name("BiomeMap"))
        biome_map.set_editor_property("texture", load("/Engine/EngineResources/DefaultTexture.DefaultTexture", "Texture2D"))
        biome_map.set_editor_property("desc", "R80.RuntimeBoundBiomeMap")
        uv = editing.create_material_expression(parent, unreal.MaterialExpressionTextureCoordinate, 2260, 2910)
        require(uv is not None, "R80 UV node creation failed")
        wet_depth = create_parameter(parent, unreal.MaterialExpressionScalarParameter, "R80_WetDepth", 0.070, 2260, 3060, "R80.WetDepth")
        feather = create_parameter(parent, unreal.MaterialExpressionScalarParameter, "R80_WetFeather", 0.025, 2260, 3200, "R80.WetFeather")
        masks = editing.create_material_expression(parent, unreal.MaterialExpressionCustom, 2580, 2880)
        require(masks is not None, "R80 custom mask creation failed")
        masks.set_editor_property("description", "R80 triangle-consistent BiomeMap-alpha dry/wet/submerged masks")
        masks.set_editor_property("code", MASK_CODE)
        masks.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        custom_inputs = []
        for name in ("BiomeMap", "UV", "WetDepth", "Feather"):
            item = unreal.CustomInput()
            item.set_editor_property("input_name", name)
            custom_inputs.append(item)
        masks.set_editor_property("inputs", custom_inputs)
        require(editing.connect_material_expressions(biome_map, "", masks, "BiomeMap"), "R80 BiomeMap connection failed")
        require(editing.connect_material_expressions(uv, "", masks, "UV"), "R80 UV connection failed")
        require(editing.connect_material_expressions(wet_depth, "", masks, "WetDepth"), "R80 WetDepth connection failed")
        require(editing.connect_material_expressions(feather, "", masks, "Feather"), "R80 Feather connection failed")

        wet_mask = editing.create_material_expression(parent, unreal.MaterialExpressionComponentMask, 2900, 2990)
        sub_mask = editing.create_material_expression(parent, unreal.MaterialExpressionComponentMask, 2900, 3130)
        require(wet_mask is not None and sub_mask is not None, "R80 mask split creation failed")
        wet_mask.set_editor_property("r", False)
        wet_mask.set_editor_property("g", True)
        wet_mask.set_editor_property("b", False)
        wet_mask.set_editor_property("a", False)
        sub_mask.set_editor_property("r", False)
        sub_mask.set_editor_property("g", False)
        sub_mask.set_editor_property("b", True)
        sub_mask.set_editor_property("a", False)
        require(editing.connect_material_expressions(masks, "", wet_mask, ""), "R80 wet mask connection failed")
        require(editing.connect_material_expressions(masks, "", sub_mask, ""), "R80 submerged mask connection failed")

        wet_tint = create_parameter(parent, unreal.MaterialExpressionVectorParameter, "R80_WetSandTint", unreal.LinearColor(0.62, 0.52, 0.38, 1.0), 3260, 2720, "R80.WetSandTint")
        sub_tint = create_parameter(parent, unreal.MaterialExpressionVectorParameter, "R80_SubmergedSandTint", unreal.LinearColor(0.25, 0.72, 0.62, 1.0), 3260, 2860, "R80.SubmergedSandTint")
        wet_color = editing.create_material_expression(parent, unreal.MaterialExpressionMultiply, 3500, 2720)
        sub_color = editing.create_material_expression(parent, unreal.MaterialExpressionMultiply, 3500, 2860)
        wet_lerp = editing.create_material_expression(parent, unreal.MaterialExpressionLinearInterpolate, 3760, 2800)
        sub_lerp = editing.create_material_expression(parent, unreal.MaterialExpressionLinearInterpolate, 4020, 2880)
        require(all(node is not None for node in (wet_color, sub_color, wet_lerp, sub_lerp)), "R80 color graph creation failed")
        wet_color.set_editor_property("desc", "R80.TexturePreservingWetSand")
        sub_color.set_editor_property("desc", "R80.TexturePreservingSubmergedSand")
        wet_lerp.set_editor_property("desc", "R80.DryToWetSand")
        sub_lerp.set_editor_property("desc", "R80.WetToSubmergedSand")
        for label, source, target, input_name in (
            ("wet dry base", dry_base, wet_color, "A"),
            ("wet tint", wet_tint, wet_color, "B"),
            ("sub dry base", dry_base, sub_color, "A"),
            ("sub tint", sub_tint, sub_color, "B"),
            ("dry lerp A", dry_base, wet_lerp, "A"),
            ("wet lerp B", wet_color, wet_lerp, "B"),
            ("wet lerp alpha", wet_mask, wet_lerp, "Alpha"),
            ("sub lerp A", wet_lerp, sub_lerp, "A"),
            ("sub lerp B", sub_color, sub_lerp, "B"),
            ("sub lerp alpha", sub_mask, sub_lerp, "Alpha"),
        ):
            require(editing.connect_material_expressions(source, "", target, input_name), "R80 connection failed: " + label)

        require(editing.disconnect_material_expressions(desert_attrs, "BaseColor"), "R80 Desert BaseColor disconnect failed")
        require(editing.connect_material_expressions(sub_lerp, "", desert_attrs, "BaseColor"), "R80 Desert BaseColor connect failed")
        require(editing.disconnect_material_expressions(ocean_attrs, "BaseColor"), "R80 Ocean BaseColor disconnect failed")
        require(editing.connect_material_expressions(sub_lerp, "", ocean_attrs, "BaseColor"), "R80 Ocean BaseColor connect failed")
        desert_after = input_sources(parent, desert_attrs)
        ocean_after = input_sources(parent, ocean_attrs)
        require(desert_after.get("BaseColor") == sub_lerp and ocean_after.get("BaseColor") == sub_lerp, "R80 shoreline output wiring failed")
        role_after = input_sources(parent, output)
        require({role: role_after[role].get_name() for role in role_before} == {role: role_before[role].get_name() for role in role_before}, "R80 role output identity changed")

        editing.recompile_material(parent)
        require(unreal.EditorAssetLibrary.save_loaded_asset(parent, only_if_is_dirty=False), "R80 parent save failed")
        target_mi = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_MI, TARGET_MI)
        require(target_mi is not None and target_mi.get_class().get_name() == "MaterialInstanceConstant", "R80 MI duplicate failed")
        mi_created = True
        editing.set_material_instance_parent(target_mi, parent)
        editing.update_material_instance(target_mi)
        require(unreal.EditorAssetLibrary.save_loaded_asset(target_mi, only_if_is_dirty=False), "R80 MI save failed")
        require(asset_path(target_mi.get_editor_property("parent")) == TARGET_PARENT, "R80 MI parent did not persist")
        scalar_names = {str(item) for item in editing.get_scalar_parameter_names(target_mi)}
        vector_names = {str(item) for item in editing.get_vector_parameter_names(target_mi)}
        texture_names = {str(item) for item in editing.get_texture_parameter_names(target_mi)}
        require({"R80_WetDepth", "R80_WetFeather"} <= scalar_names, "R80 scalar controls missing")
        require({"R80_WetSandTint", "R80_SubmergedSandTint"} <= vector_names, "R80 vector controls missing")
        require("BiomeMap" in texture_names, "R80 runtime BiomeMap parameter missing")

        profile.set_editor_property("planet_material", target_mi)
        require(int(profile.get_editor_property("generation_seed")) == 1337, "R80 seed changed")
        require(asset_path(profile.get_editor_property("water_material")) == WATER_MI, "R80 water changed")
        require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "R80 ProfileV1 save failed")
        profile_saved = True
        require(dirty_packages() == {"content": [], "maps": []}, "R80 dirty packages after save")
        reloaded = load(PROFILE, "PlanetData")
        require(asset_path(reloaded.get_editor_property("planet_material")) == TARGET_MI, "R80 binding did not persist")
        require(int(reloaded.get_editor_property("generation_seed")) == 1337, "R80 seed persistence drift")
        require(asset_path(reloaded.get_editor_property("water_material")) == WATER_MI, "R80 water persistence drift")
        for path, expected in EXPECTED.items():
            if path != PROFILE_FILE:
                require(sha256(path) == expected, "unrelated post-save drift: " + str(path))

        report.update({
            "status": "PASS_R80_SHORELINE_BANDS_BOUND_PENDING_FRESH_RELOAD",
            "completed_utc": now(),
            "target_parent": TARGET_PARENT,
            "target_parent_sha256": sha256(TARGET_PARENT_FILE),
            "target_instance": TARGET_MI,
            "target_instance_sha256": sha256(TARGET_MI_FILE),
            "profile_sha256_before": EXPECTED[PROFILE_FILE],
            "profile_sha256_after": sha256(PROFILE_FILE),
            "home_map_sha256_before_after": sha256(HOME_FILE),
            "seed": 1337,
            "water_binding_unchanged": WATER_MI,
            "controls": {"wet_depth": 0.070, "wet_feather": 0.025, "wet_tint": [0.62, 0.52, 0.38, 1.0], "submerged_tint": [0.25, 0.72, 0.62, 1.0]},
            "modified_roles": ["Desert", "Ocean"],
            "runtime_parameter": "BiomeMap",
            "triangle_consistent": True,
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Serialized R80 project-owned material successor and ProfileV1 pointer only; fresh reload, MapCheck, runtime binding and D3D12 exact-coast visual acceptance remain pending.",
        })
        atomic_json(RESULT, report)
        unreal.log("REDMMO_R80_APPLY_PASS")
    except Exception as error:
        rollback = {"attempted": True, "profile_restored": False, "mi_deleted": False, "parent_deleted": False}
        try:
            if profile_saved:
                profile = load(PROFILE, "PlanetData")
                profile.set_editor_property("planet_material", load(SOURCE_MI, "MaterialInstanceConstant"))
                require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "R80 rollback profile save failed")
            rollback["profile_restored"] = sha256(PROFILE_FILE) == EXPECTED[PROFILE_FILE]
            for key, created, asset, file_path in (
                ("mi_deleted", mi_created, TARGET_MI, TARGET_MI_FILE),
                ("parent_deleted", parent_created, TARGET_PARENT, TARGET_PARENT_FILE),
            ):
                if created or unreal.EditorAssetLibrary.does_asset_exist(asset):
                    rollback[key] = bool(unreal.EditorAssetLibrary.delete_asset(asset)) or not file_path.exists()
                else:
                    rollback[key] = not file_path.exists()
        except Exception as rollback_error:
            rollback["error"] = str(rollback_error)
        report.update({
            "status": "FAIL_ROLLED_BACK" if all(rollback.get(key) for key in ("profile_restored", "mi_deleted", "parent_deleted")) else "FAIL_ROLLBACK_INCOMPLETE",
            "completed_utc": now(),
            "error": str(error),
            "traceback": traceback.format_exc(),
            "rollback_result": rollback,
            "dirty_packages_after": dirty_packages(),
        })
        if not RESULT.exists():
            atomic_json(RESULT, report)
        unreal.log_error("REDMMO_R80_APPLY_FAIL: " + str(error))
    finally:
        schedule_exit()


main()
