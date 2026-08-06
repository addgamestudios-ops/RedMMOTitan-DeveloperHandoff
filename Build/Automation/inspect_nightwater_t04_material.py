"""Read-only audit for the disposable NightWater_T04 material harness.

This does not alter any vendor or project asset.  It reports the inherited
material parameter surface and the live override values so a GPU-visible
night-water failure can be attributed before changing a project-owned child.
"""

import unreal


INSTANCE_PATH = "/Game/RedMMO/Environment/Tests/MI_RedClearWater_Night_T04"
MPC_PATH = "/Game/SoStylized/Environment/MPC_GlobalEnvironment.MPC_GlobalEnvironment"


def load_required(path: str):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if not asset:
        raise RuntimeError(f"Missing asset: {path}")
    return asset


instance = load_required(INSTANCE_PATH)
parent = instance.get_editor_property("parent")
unreal.log_warning(
    "RED_NIGHT_WATER_AUDIT instance="
    + instance.get_path_name()
    + " parent="
    + (parent.get_path_name() if parent else "<none>")
)

for name in sorted(unreal.MaterialEditingLibrary.get_scalar_parameter_names(instance)):
    value = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(
        instance, name
    )
    unreal.log_warning(f"RED_NIGHT_WATER_SCALAR {name}={value}")

for name in sorted(unreal.MaterialEditingLibrary.get_vector_parameter_names(instance)):
    value = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(
        instance, name
    )
    unreal.log_warning(f"RED_NIGHT_WATER_VECTOR {name}={value}")

collection = load_required(MPC_PATH)
for parameter in collection.get_editor_property("scalar_parameters"):
    name = parameter.get_editor_property("parameter_name")
    value = parameter.get_editor_property("default_value")
    unreal.log_warning(f"RED_NIGHT_WATER_MPC_DEFAULT {name}={value}")

unreal.log_warning("RED_NIGHT_WATER_AUDIT_COMPLETE")
