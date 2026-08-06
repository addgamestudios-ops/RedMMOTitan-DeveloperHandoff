import unreal


INSTANCE_PATH = "/Game/RedMMO/Materials/MI_RedGrapplePlasma"


instance = unreal.EditorAssetLibrary.load_asset(INSTANCE_PATH)
if instance is None:
    raise RuntimeError(f"Missing grapple material instance: {INSTANCE_PATH}")

parent = instance.get_editor_property("parent")
if parent is None:
    raise RuntimeError(f"Grapple material instance has no parent: {INSTANCE_PATH}")

unreal.log_warning(
    "RED_GRAPPLE_MATERIAL_INSPECT instance="
    + instance.get_path_name()
    + " parent="
    + parent.get_path_name()
)

for property_name in sorted(name for name in dir(parent) if "spline" in name.lower()):
    try:
        value = parent.get_editor_property(property_name)
    except Exception as error:
        value = f"<unreadable: {error}>"
    unreal.log_warning(f"RED_GRAPPLE_MATERIAL_PROPERTY {property_name}={value}")

mesh = unreal.EditorAssetLibrary.load_asset("/Game/ProjectilesVol1/Models/SM_BeamMesh")
if mesh is None:
    raise RuntimeError("Missing spline fallback mesh /Game/ProjectilesVol1/Models/SM_BeamMesh")
try:
    bounds = mesh.get_bounds()
except Exception as error:
    bounds = f"<unreadable: {error}>"
unreal.log_warning(
    "RED_GRAPPLE_SPLINE_MESH path=" + mesh.get_path_name() + " bounds=" + str(bounds)
)
for index, static_material in enumerate(mesh.get_editor_property("static_materials")):
    unreal.log_warning(
        "RED_GRAPPLE_SPLINE_MESH_MATERIAL index="
        + str(index)
        + " material="
        + str(static_material.get_editor_property("material_interface"))
    )
