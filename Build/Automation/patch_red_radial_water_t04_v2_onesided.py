"""Return RED's V2 radial water to one-sided after fixing sphere winding."""

import unreal


MATERIAL_PATH = "/Game/RedMMO/Environment/Tests/M_RedRadialWater_T04_V2"

material = unreal.EditorAssetLibrary.load_asset(MATERIAL_PATH)
if not isinstance(material, unreal.Material):
    raise RuntimeError(f"missing project-owned material {MATERIAL_PATH}")

material.set_editor_property("two_sided", False)
unreal.MaterialEditingLibrary.recompile_material(material)
if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
    raise RuntimeError(f"could not save {MATERIAL_PATH}")

unreal.log_warning(
    "RED_RADIAL_WATER_T04_ONESIDED_READY "
    f"material={material.get_path_name()} two_sided={material.get_editor_property('two_sided')}"
)
