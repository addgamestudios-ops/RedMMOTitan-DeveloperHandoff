"""Read-only parameter audit for the purchased So Stylized desert demo MI."""

import unreal


path = "/Game/SoStylized/Environment/Landscape/Materials/MI_Landscape_Desert"
asset = unreal.load_asset(path)
if not asset:
    raise RuntimeError(f"Missing {path}")

unreal.log(f"RED_SAND_DEMO_AUDIT asset={path} class={asset.get_class().get_name()}")
for name in sorted(n for n in dir(unreal.MaterialEditingLibrary) if "parameter" in n.lower() or "switch" in n.lower()):
    unreal.log(f"RED_SAND_DEMO_API {name}")

for property_name in (
    "parent",
    "scalar_parameter_values",
    "vector_parameter_values",
    "static_parameters",
    "static_switch_parameter_values",
):
    try:
        value = asset.get_editor_property(property_name)
        unreal.log(f"RED_SAND_DEMO_PROPERTY name={property_name} value={value}")
    except Exception as exc:
        unreal.log_warning(f"RED_SAND_DEMO_PROPERTY name={property_name} unavailable={exc}")

for parameter_name in unreal.MaterialEditingLibrary.get_static_switch_parameter_names(asset):
    value = unreal.MaterialEditingLibrary.get_material_instance_static_switch_parameter_value(
        asset, parameter_name
    )
    overridden = unreal.MaterialEditingLibrary.is_material_instance_parameter_overridden(
        asset, parameter_name
    )
    source = unreal.MaterialEditingLibrary.get_static_switch_parameter_source(asset, parameter_name)
    unreal.log(
        f"RED_SAND_DEMO_SWITCH name={parameter_name} value={value} "
        f"overridden={overridden} source={source}"
    )

for parameter_name in unreal.MaterialEditingLibrary.get_scalar_parameter_names(asset):
    text = str(parameter_name)
    if "Sand" not in text and "Sparkle" not in text:
        continue
    value = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(
        asset, parameter_name
    )
    overridden = unreal.MaterialEditingLibrary.is_material_instance_parameter_overridden(
        asset, parameter_name
    )
    unreal.log(
        f"RED_SAND_DEMO_SCALAR name={parameter_name} value={value} overridden={overridden}"
    )

t02_path = "/Game/RedMMO/Materials/DesertSparkleTest/MI_PlanetBiome_DesertSparkle_T02"
t02 = unreal.load_asset(t02_path)
if not t02:
    raise RuntimeError(f"Missing {t02_path}")
for parameter_name in unreal.MaterialEditingLibrary.get_static_switch_parameter_names(t02):
    text = str(parameter_name)
    if "Sparkle" not in text and "Ripple" not in text and "WorldRotation" not in text:
        continue
    value = unreal.MaterialEditingLibrary.get_material_instance_static_switch_parameter_value(
        t02, parameter_name
    )
    overridden = unreal.MaterialEditingLibrary.is_material_instance_parameter_overridden(
        t02, parameter_name
    )
    unreal.log(
        f"RED_SAND_T02_MI_SWITCH name={parameter_name} value={value} overridden={overridden}"
    )
for parameter_name in unreal.MaterialEditingLibrary.get_scalar_parameter_names(t02):
    text = str(parameter_name)
    if "Desert Sparkle" not in text and "Desert Sand" not in text:
        continue
    value = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(
        t02, parameter_name
    )
    overridden = unreal.MaterialEditingLibrary.is_material_instance_parameter_overridden(
        t02, parameter_name
    )
    unreal.log(
        f"RED_SAND_T02_MI_SCALAR name={parameter_name} value={value} overridden={overridden}"
    )
