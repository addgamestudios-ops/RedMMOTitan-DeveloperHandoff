"""Read-only reflection audit for UE 5.8 Single Layer Water material output."""

import unreal


editing = unreal.MaterialEditingLibrary
master = unreal.EditorAssetLibrary.load_asset(
    "/Game/SoStylized/Environment/Water/Legacy/M_Water"
)
if not isinstance(master, unreal.Material):
    raise RuntimeError("So Stylized legacy water master is missing")

unreal.log_warning("RED_SINGLE_LAYER_API editing_dir=" + ",".join(sorted(dir(editing))))
get_expressions = getattr(editing, "get_material_expressions", None)
if get_expressions is None:
    raise RuntimeError("MaterialEditingLibrary.get_material_expressions is unavailable")
nodes = [
    expression
    for expression in get_expressions(master)
    if isinstance(expression, unreal.MaterialExpressionSingleLayerWaterMaterialOutput)
]
if len(nodes) != 1:
    raise RuntimeError(f"expected one Single Layer Water output, found {len(nodes)}")

node = nodes[0]
unreal.log_warning("RED_SINGLE_LAYER_API node=" + node.get_path_name())
unreal.log_warning("RED_SINGLE_LAYER_API node_dir=" + ",".join(sorted(dir(node))))
unreal.log_warning(
    "RED_SINGLE_LAYER_API input_names="
    + ",".join(str(value) for value in editing.get_material_expression_input_names(node))
)
unreal.log_warning(
    "RED_SINGLE_LAYER_API input_types="
    + ",".join(str(value) for value in editing.get_material_expression_input_types(node))
)

for property_name in (
    "scattering_coefficients",
    "absorption_coefficients",
    "phase_g",
    "color_scale_behind_water",
):
    try:
        value = node.get_editor_property(property_name)
        unreal.log_warning(f"RED_SINGLE_LAYER_API property={property_name} value={value}")
    except Exception as exc:
        unreal.log_error(f"RED_SINGLE_LAYER_API missing_property={property_name} error={exc}")
