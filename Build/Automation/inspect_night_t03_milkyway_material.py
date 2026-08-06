"""Read-only audit/export for the isolated Night_T03 Milky Way material."""

import os
import unreal


MATERIAL_PATH = "/Game/RedMMO/Environment/Tests/M_RedStar_T03MilkyWayWorldDir"
TEXTURE_PATH = "/Game/SpaceColony/Textures/T_milky_way"
MESH_PATH = "/Engine/EngineSky/SM_SkySphere"
OUTPUT_DIR = os.environ.get(
    "RED_NIGHT_T03_AUDIT_DIR",
    "D:/RedMMOTitanWindowsData/Diagnostics/NightT03_MilkyWay_AssetAudit",
)


def emit(message):
    unreal.log("RED_NIGHT_T03_MILKYWAY_AUDIT " + str(message))


os.makedirs(OUTPUT_DIR, exist_ok=True)
material = unreal.EditorAssetLibrary.load_asset(MATERIAL_PATH)
texture = unreal.EditorAssetLibrary.load_asset(TEXTURE_PATH)
mesh = unreal.EditorAssetLibrary.load_asset(MESH_PATH)

if not isinstance(material, unreal.Material):
    raise RuntimeError(f"Missing project material: {MATERIAL_PATH}")
if not isinstance(texture, unreal.Texture2D):
    raise RuntimeError(f"Missing Texture2D: {TEXTURE_PATH}")
if not isinstance(mesh, unreal.StaticMesh):
    raise RuntimeError(f"Missing sky mesh: {MESH_PATH}")

for property_name in (
    "material_domain",
    "blend_mode",
    "shading_model",
    "two_sided",
    "is_sky",
):
    emit(f"material {property_name}={material.get_editor_property(property_name)}")

editing = unreal.MaterialEditingLibrary
emit(f"material scalar_parameters={sorted(str(v) for v in editing.get_scalar_parameter_names(material))}")
emit(f"material texture_parameters={sorted(str(v) for v in editing.get_texture_parameter_names(material))}")
for name in ("Visibility", "Emission"):
    try:
        emit(f"material scalar_default {name}={editing.get_material_default_scalar_parameter_value(material, name)}")
    except Exception as exc:
        emit(f"material scalar_default {name}=unavailable:{exc}")
try:
    emit(
        "material texture_default StarAtlas="
        + str(editing.get_material_default_texture_parameter_value(material, "StarAtlas"))
    )
except Exception as exc:
    emit(f"material texture_default StarAtlas=unavailable:{exc}")

emit(
    f"texture size={texture.blueprint_get_size_x()}x{texture.blueprint_get_size_y()} "
    f"srgb={texture.get_editor_property('srgb')} "
    f"compression={texture.get_editor_property('compression_settings')} "
    f"lod_group={texture.get_editor_property('lod_group')}"
)
emit(f"mesh bounds={mesh.get_bounding_box()}")

task = unreal.AssetExportTask()
task.set_editor_property("object", texture)
task.set_editor_property("filename", os.path.join(OUTPUT_DIR, "T_milky_way.png"))
task.set_editor_property("automated", True)
task.set_editor_property("prompt", False)
task.set_editor_property("replace_identical", True)
task.set_editor_property("exporter", unreal.TextureExporterPNG())
exported = unreal.Exporter.run_asset_export_task(task)
emit(f"texture_exported={exported} output={task.get_editor_property('filename')}")
emit("complete")
