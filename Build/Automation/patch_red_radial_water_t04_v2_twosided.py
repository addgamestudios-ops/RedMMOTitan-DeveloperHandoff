"""Make the project-owned T04 radial water visible from PlanetGen's exterior.

PlanetGen's generated WaterSphereMesh triangles are wound toward the centre.
Its authored water masters are two-sided, but the first RED V2 diagnostic
master was not, so the renderer culled the whole ocean from an exterior camera.
This edits only the project-owned material flag; purchased vendor assets remain
read-only and the material graph is not rebuilt.
"""

import unreal


MATERIAL_PATH = "/Game/RedMMO/Environment/Tests/M_RedRadialWater_T04_V2"

material = unreal.EditorAssetLibrary.load_asset(MATERIAL_PATH)
if not isinstance(material, unreal.Material):
    raise RuntimeError(f"missing project-owned material {MATERIAL_PATH}")

material.set_editor_property("two_sided", True)
unreal.MaterialEditingLibrary.recompile_material(material)
if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
    raise RuntimeError(f"could not save {MATERIAL_PATH}")

unreal.log_warning(
    "RED_RADIAL_WATER_T04_TWOSIDED_READY "
    f"material={material.get_path_name()} two_sided={material.get_editor_property('two_sided')}"
)
