"""Apply the project-owned R73 ProfileV1 presentation correction.

R73 makes exactly two authored corrections without changing the home map,
terrain, seed, PPG water, generated placement rules, or vendor assets:

* duplicate R66 into a rock-only foliage profile by setting only the approved
  grass entry density to zero, then bind it to Craters and Mountains while
  Hills retains the complete R66 dense-grass profile;
* duplicate R71 into a new surface parent and replace only Ocean BaseColor with
  a texture-preserving sand-to-aqua lerp so below-sea terrain reads aqua-tan.
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
R66_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_NoPalms_R66.uasset"
R71_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_RoleSurface_R71.uasset"
R71_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_RoleSurface_R71.uasset"
TARGET_FOLIAGE_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_RockOnly_R73.uasset"
TARGET_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_BiomePresentation_R73.uasset"
TARGET_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_BiomePresentation_R73.uasset"
PROTECTED_TEST = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap")
PROTECTED_FUSED = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap")
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1BiomePresentation_R73_20260805T2343Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1BiomePresentation_R73_20260805T2343Z\Apply")
RESULT = DIAG / "result.json"

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
PROFILE = ROOT + "/DA_PPG_ProfileV1_PlanetData"
R66 = ROOT + "/Profiles/DA_PPG_ProfileV1_NoPalms_R66"
R71_PARENT = ROOT + "/Materials/M_PPG_ProfileV1_RoleSurface_R71"
R71_MI = ROOT + "/Materials/MI_PPG_ProfileV1_RoleSurface_R71"
TARGET_FOLIAGE = ROOT + "/Profiles/DA_PPG_ProfileV1_RockOnly_R73"
TARGET_PARENT = ROOT + "/Materials/M_PPG_ProfileV1_BiomePresentation_R73"
TARGET_MI = ROOT + "/Materials/MI_PPG_ProfileV1_BiomePresentation_R73"

EXPECTED = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "BD5E46F3132A6A8947C1258AB18C0F152DD4836755A414B9CC876E3BD0D6CB0D",
    R66_FILE: "C0EE6CB0A2D9D679D1FB4D64747555D55A5AF18ABED4AEC2666A1D5BECDA97DC",
    R71_PARENT_FILE: "EA3A5704BDA1706C7720CDFB51F39CE370CCD844E6FECEDEB53CF3ACC4F555DE",
    R71_MI_FILE: "D4D222CF92769F99631B649198DD8C38032BD67B7853CD7B0A288E1657301253",
    PROTECTED_TEST: "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    PROTECTED_FUSED: "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


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


def normalized(value):
    return str(value).replace("_", "").replace(" ", "").lower()


def find_key(values, wanted):
    target = normalized(wanted)
    matches = [key for key in values if normalized(key) in (target, "b" + target)]
    require(len(matches) == 1, "missing reflected key " + wanted)
    return matches[0]


def stable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "get_path_name"):
        return asset_path(value)
    if isinstance(value, dict):
        return {str(key): stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [stable(item) for item in value]
    if hasattr(value, "to_dict"):
        return stable(value.to_dict())
    return str(value)


def field(value, wanted):
    values = value.to_dict()
    return values[find_key(values, wanted)]


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
    names = [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(node)]
    sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, node))
    require(len(names) == len(sources), "input reflection mismatch: " + node.get_name())
    return dict(zip(names, sources))


def node_by_desc(nodes, desc, class_name):
    matches = [node for node in nodes if node.get_class().get_name() == class_name and str(node.get_editor_property("desc")) == desc]
    require(len(matches) == 1, "expected one {} node with desc {}".format(class_name, desc))
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
    require(manifest_path.is_file(), "R73 checkpoint manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == "redmmo.ppg.profile_v1_biome_presentation.rollback.r73.v1", "checkpoint schema drift")
    records = manifest.get("records")
    require(isinstance(records, list) and len(records) == 8, "checkpoint record count drift")
    by_source = {str(Path(item["source"]).resolve(strict=True)): item for item in records}
    for path, expected in EXPECTED.items():
        item = by_source.get(str(path.resolve(strict=True)))
        require(item is not None and item.get("sha256") == expected, "checkpoint source mismatch: " + str(path))
        copy = Path(item["copy"])
        require(copy.is_file() and sha256(copy) == expected, "checkpoint copy mismatch: " + str(path))
    return str(manifest_path)


def main():
    report = {
        "schema": "redmmo.ppg.profile_v1_biome_presentation.apply.r73.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
        "rollback": str(ROLLBACK),
        "map_saved": False,
        "generation_called": False,
    }
    profile_values_before = None
    material_before = None
    target_foliage_created = False
    target_parent_created = False
    target_mi_created = False
    profile_saved = False
    try:
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists(), "R73 result no-clobber failed")
        for path, expected in EXPECTED.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        require(not TARGET_FOLIAGE_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(TARGET_FOLIAGE), "R73 foliage exists")
        require(not TARGET_PARENT_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(TARGET_PARENT), "R73 parent exists")
        require(not TARGET_MI_FILE.exists() and not unreal.EditorAssetLibrary.does_asset_exist(TARGET_MI), "R73 MI exists")
        report["rollback_manifest"] = verify_checkpoint()
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        report["provider_gate_before"] = provider_gate()

        source_foliage = load(R66, "FoliageData")
        source_entries = list(source_foliage.get_editor_property("foliage_list"))
        require(len(source_entries) == 3, "R66 foliage entry count drift")
        source_signatures = [stable(entry) for entry in source_entries]
        require(abs(float(source_entries[0].get_editor_property("foliage_density"))) <= 1.0e-6, "R66 palm density drift")
        grass_density_before = float(source_entries[1].get_editor_property("foliage_density"))
        rock_density_before = float(source_entries[2].get_editor_property("foliage_density"))
        require(grass_density_before > 0.0 and rock_density_before > 0.0, "R66 grass/rock density drift")

        target_foliage = unreal.EditorAssetLibrary.duplicate_asset(R66, TARGET_FOLIAGE)
        require(target_foliage is not None and target_foliage.get_class().get_name() == "FoliageData", "R73 foliage duplicate failed")
        target_foliage_created = True
        entries = list(target_foliage.get_editor_property("foliage_list"))
        grass_values = entries[1].to_dict()
        density_key = find_key(grass_values, "foliage_density")
        require(abs(float(grass_values[density_key]) - grass_density_before) <= 1.0e-6, "R73 grass density precondition drift")
        grass_values[density_key] = 0.0
        entries[1] = unreal.FoliageList(**grass_values)
        target_foliage.set_editor_property("foliage_list", entries)
        require(unreal.EditorAssetLibrary.save_loaded_asset(target_foliage, only_if_is_dirty=False), "R73 foliage save failed")
        verified_foliage = load(TARGET_FOLIAGE, "FoliageData")
        verified_entries = list(verified_foliage.get_editor_property("foliage_list"))
        require(abs(float(verified_entries[1].get_editor_property("foliage_density"))) <= 1.0e-6, "R73 grass density did not persist")
        require(stable(verified_entries[0]) == source_signatures[0], "R73 palm entry changed")
        require(stable(verified_entries[2]) == source_signatures[2], "R73 rock entry changed")
        expected_grass = source_entries[1].to_dict()
        expected_grass[find_key(expected_grass, "foliage_density")] = 0.0
        require(stable(verified_entries[1]) == stable(expected_grass), "R73 grass entry changed outside density")

        source_parent = load(R71_PARENT, "Material")
        source_mi = load(R71_MI, "MaterialInstanceConstant")
        require(asset_path(source_mi.get_editor_property("parent")) == R71_PARENT, "R71 MI parent drift")
        target_parent = unreal.EditorAssetLibrary.duplicate_asset(R71_PARENT, TARGET_PARENT)
        require(target_parent is not None and target_parent.get_class().get_name() == "Material", "R73 parent duplicate failed")
        target_parent_created = True
        nodes = list(unreal.MaterialEditingLibrary.get_material_expressions(target_parent))
        outputs = [node for node in nodes if node.get_class().get_name() == "MaterialExpressionPlanetBiomeMaterialOutput"]
        require(len(outputs) == 1, "R73 output node count drift")
        output = outputs[0]
        before_roles = input_sources(target_parent, output)
        require(all(before_roles.get(role) is not None for role in ("Craters", "Mountains", "Desert", "Hills", "Poles", "Ocean")), "R73 inherited role wiring incomplete")
        ocean_attrs = node_by_desc(nodes, "R71.Ocean.Attributes", "MaterialExpressionMakeMaterialAttributes")
        desert_samples = [node for node in nodes if node.get_name() == "MaterialExpressionTextureSample_3"]
        require(len(desert_samples) == 1 and desert_samples[0].get_class().get_name() == "MaterialExpressionTextureSample", "R73 inherited desert sample drift")
        desert_bc = desert_samples[0]
        editing = unreal.MaterialEditingLibrary
        aqua = create_parameter(target_parent, unreal.MaterialExpressionVectorParameter, "R73_OceanAqua", unreal.LinearColor(0.08, 0.62, 0.58, 1.0), 2380, 2300, "R73.Ocean.AquaColor")
        blend = create_parameter(target_parent, unreal.MaterialExpressionScalarParameter, "R73_OceanAquaBlend", 0.78, 2380, 2440, "R73.Ocean.AquaBlend")
        lerp = editing.create_material_expression(target_parent, unreal.MaterialExpressionLinearInterpolate, 2640, 2300)
        require(lerp is not None, "R73 ocean lerp creation failed")
        lerp.set_editor_property("desc", "R73.Ocean.SandToAqua")
        require(editing.connect_material_expressions(desert_bc, "", lerp, "A"), "R73 ocean sand connection failed")
        require(editing.connect_material_expressions(aqua, "", lerp, "B"), "R73 ocean aqua connection failed")
        require(editing.connect_material_expressions(blend, "", lerp, "Alpha"), "R73 ocean alpha connection failed")
        require(editing.disconnect_material_expressions(ocean_attrs, "BaseColor"), "R73 ocean old BaseColor disconnect failed")
        require(editing.connect_material_expressions(lerp, "", ocean_attrs, "BaseColor"), "R73 ocean BaseColor connection failed")
        ocean_inputs = input_sources(target_parent, ocean_attrs)
        require(ocean_inputs.get("BaseColor") == lerp, "R73 ocean BaseColor verification failed")
        after_roles = input_sources(target_parent, output)
        require({role: after_roles[role].get_name() for role in before_roles if role in after_roles} == {role: before_roles[role].get_name() for role in before_roles if role in after_roles}, "R73 role output identities changed")
        editing.recompile_material(target_parent)
        require(unreal.EditorAssetLibrary.save_loaded_asset(target_parent, only_if_is_dirty=False), "R73 parent save failed")

        target_mi = unreal.EditorAssetLibrary.duplicate_asset(R71_MI, TARGET_MI)
        require(target_mi is not None and target_mi.get_class().get_name() == "MaterialInstanceConstant", "R73 MI duplicate failed")
        target_mi_created = True
        editing.set_material_instance_parent(target_mi, target_parent)
        editing.update_material_instance(target_mi)
        require(unreal.EditorAssetLibrary.save_loaded_asset(target_mi, only_if_is_dirty=False), "R73 MI save failed")
        require(asset_path(target_mi.get_editor_property("parent")) == TARGET_PARENT, "R73 MI parent did not persist")

        profile = load(PROFILE, "PlanetData")
        require(int(profile.get_editor_property("generation_seed")) == 1337, "ProfileV1 seed drift")
        require(asset_path(profile.get_editor_property("planet_material")) == R71_MI, "ProfileV1 R71 material binding drift")
        profile_values_before = [item.to_dict() for item in list(profile.get_editor_property("biome_data"))]
        material_before = profile.get_editor_property("planet_material")
        rebound = []
        changed = []
        for values in profile_values_before:
            current = dict(values)
            name_key = find_key(current, "name")
            foliage_key = find_key(current, "foliage_data")
            name = str(current[name_key])
            current_foliage = asset_path(current[foliage_key])
            if name in ("Craters", "Mountains"):
                require(current_foliage == R66, "R73 source foliage drift for " + name)
                current[foliage_key] = verified_foliage
                changed.append(name)
            elif name == "Hills":
                require(current_foliage == R66, "R73 Hills R66 binding drift")
            else:
                require(current_foliage is None, "R73 unexpected foliage binding for " + name)
            rebound.append(unreal.BiomeData(**current))
        require(changed == ["Craters", "Mountains"], "R73 changed biome order drift: " + repr(changed))
        profile.set_editor_property("biome_data", rebound)
        profile.set_editor_property("planet_material", target_mi)
        require(int(profile.get_editor_property("generation_seed")) == 1337, "R73 seed changed")
        require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "R73 ProfileV1 save failed")
        profile_saved = True
        require(dirty_packages() == {"content": [], "maps": []}, "R73 dirty packages after save")

        reloaded = load(PROFILE, "PlanetData")
        require(asset_path(reloaded.get_editor_property("planet_material")) == TARGET_MI, "R73 material binding did not persist")
        bindings = []
        for biome in list(reloaded.get_editor_property("biome_data")):
            bindings.append({"name": str(field(biome, "name")), "foliage_data": asset_path(field(biome, "foliage_data"))})
        require([item["name"] for item in bindings if item["foliage_data"] == TARGET_FOLIAGE] == ["Craters", "Mountains"], "R73 rock-only bindings did not persist")
        require([item["name"] for item in bindings if item["foliage_data"] == R66] == ["Hills"], "R73 Hills R66 binding did not persist")
        for path, expected in EXPECTED.items():
            if path != PROFILE_FILE:
                require(sha256(path) == expected, "unrelated post-save drift: " + str(path))
        require(TARGET_FOLIAGE_FILE.is_file() and TARGET_PARENT_FILE.is_file() and TARGET_MI_FILE.is_file(), "R73 package missing")

        report.update({
            "status": "PASS_R73_BIOME_PRESENTATION_BOUND_PENDING_FRESH_RELOAD",
            "completed_utc": now(),
            "target_foliage": TARGET_FOLIAGE,
            "target_foliage_sha256": sha256(TARGET_FOLIAGE_FILE),
            "target_parent": TARGET_PARENT,
            "target_parent_sha256": sha256(TARGET_PARENT_FILE),
            "target_instance": TARGET_MI,
            "target_instance_sha256": sha256(TARGET_MI_FILE),
            "profile_sha256_before": EXPECTED[PROFILE_FILE],
            "profile_sha256_after": sha256(PROFILE_FILE),
            "home_map_sha256_before_after": sha256(HOME_FILE),
            "changed_foliage_biomes": changed,
            "bindings_after": bindings,
            "foliage_change": {"entry": 1, "grass_density_before": grass_density_before, "grass_density_after": 0.0, "rock_density_unchanged": rock_density_before},
            "ocean_change": {"base_texture": "/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_BC", "aqua": [0.08, 0.62, 0.58, 1.0], "blend": 0.78, "node": lerp.get_name()},
            "seed": 1337,
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Serialized R73 project-owned foliage/material successors and ProfileV1 bindings only; fresh reload, MapCheck, generation, runtime census and D3D12 visual review remain pending.",
        })
        atomic_json(RESULT, report)
        unreal.log("REDMMO_R73_APPLY_PASS")
    except Exception as error:
        rollback = {"attempted": True, "profile_restored": False, "foliage_deleted": False, "mi_deleted": False, "parent_deleted": False}
        try:
            if profile_saved and profile_values_before is not None and material_before is not None:
                profile = load(PROFILE, "PlanetData")
                profile.set_editor_property("biome_data", [unreal.BiomeData(**values) for values in profile_values_before])
                profile.set_editor_property("planet_material", material_before)
                require(unreal.EditorAssetLibrary.save_loaded_asset(profile, only_if_is_dirty=False), "R73 rollback profile save failed")
            rollback["profile_restored"] = sha256(PROFILE_FILE) == EXPECTED[PROFILE_FILE]
            for key, created, asset, file_path in (
                ("mi_deleted", target_mi_created, TARGET_MI, TARGET_MI_FILE),
                ("parent_deleted", target_parent_created, TARGET_PARENT, TARGET_PARENT_FILE),
                ("foliage_deleted", target_foliage_created, TARGET_FOLIAGE, TARGET_FOLIAGE_FILE),
            ):
                if created or unreal.EditorAssetLibrary.does_asset_exist(asset):
                    rollback[key] = bool(unreal.EditorAssetLibrary.delete_asset(asset))
                else:
                    rollback[key] = not file_path.exists()
        except Exception as rollback_error:
            rollback["error"] = str(rollback_error)
        report.update({
            "status": "FAIL_ROLLED_BACK" if all(rollback.get(key) for key in ("profile_restored", "foliage_deleted", "mi_deleted", "parent_deleted")) else "FAIL_ROLLBACK_INCOMPLETE",
            "completed_utc": now(),
            "error": str(error),
            "traceback": traceback.format_exc(),
            "rollback_result": rollback,
        })
        if not RESULT.exists():
            atomic_json(RESULT, report)
        unreal.log_error("REDMMO_R73_APPLY_FAIL " + str(error))
    finally:
        unreal.SystemLibrary.quit_editor()


main()
