import unreal


INSTANCE_PATH = "/Game/RedMMO/Materials/MI_RedGrapplePlasma"


instance = unreal.EditorAssetLibrary.load_asset(INSTANCE_PATH)
if instance is None:
    raise RuntimeError(f"Missing grapple material instance: {INSTANCE_PATH}")

parent = instance.get_editor_property("parent")
if parent is None:
    raise RuntimeError(f"Grapple material instance has no parent: {INSTANCE_PATH}")

previous_value = parent.get_editor_property("used_with_spline_meshes")
if not previous_value:
    # The purchased projectile material is being used inside this project as a
    # spline-mesh grapple fallback. Enable its explicit UE usage flag so the
    # renderer compiles the correct permutation instead of silently swapping in
    # DefaultMaterial at runtime.
    parent.set_editor_property("used_with_spline_meshes", True)
    unreal.MaterialEditingLibrary.recompile_material(parent)
    if not unreal.EditorAssetLibrary.save_loaded_asset(parent, False):
        raise RuntimeError(f"Failed to save spline-mesh usage on {parent.get_path_name()}")

final_value = parent.get_editor_property("used_with_spline_meshes")
if not final_value:
    raise RuntimeError(f"Spline-mesh usage flag did not persist on {parent.get_path_name()}")

unreal.log_warning(
    "RED_GRAPPLE_SPLINE_USAGE_READY parent="
    + parent.get_path_name()
    + " before="
    + str(previous_value)
    + " after="
    + str(final_value)
)
