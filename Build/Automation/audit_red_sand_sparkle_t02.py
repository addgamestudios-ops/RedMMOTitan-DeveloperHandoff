"""Read-only audit of the project-owned T02 So Stylized function instance."""

import unreal


paths = {
    "mfi": "/Game/RedMMO/Materials/DesertSparkleTest/MFI_DesertSandSparkle_T02",
    "parent": "/Game/RedMMO/Materials/DesertSparkleTest/M_Planet_DesertSparkle_T02",
    "biome": "/Game/RedMMO/Materials/DesertSparkleTest/MI_PlanetBiome_DesertSparkle_T02",
}
for label, path in paths.items():
    asset = unreal.load_asset(path)
    unreal.log(f"RED_SAND_T02_AUDIT asset={label} path={path} loaded={bool(asset)} class={asset.get_class().get_name() if asset else 'missing'}")

mfi = unreal.load_asset(paths["mfi"])
if not mfi:
    raise RuntimeError("T02 MFI missing")
for property_name in (
    "parent",
    "scalar_parameter_values",
    "vector_parameter_values",
    "static_switch_parameter_values",
):
    try:
        value = mfi.get_editor_property(property_name)
        unreal.log(f"RED_SAND_T02_AUDIT property={property_name} value={value}")
    except Exception as exc:
        unreal.log_warning(f"RED_SAND_T02_AUDIT property={property_name} unavailable={exc}")

for index, parameter in enumerate(mfi.get_editor_property("static_switch_parameter_values")):
    fields = {}
    for field_name in ("parameter_info", "value", "override", "expression_guid"):
        try:
            fields[field_name] = parameter.get_editor_property(field_name)
        except Exception as exc:
            fields[field_name] = f"UNAVAILABLE:{exc}"
    info = fields.get("parameter_info")
    try:
        name = info.get_editor_property("name")
        association = info.get_editor_property("association")
        layer_index = info.get_editor_property("index")
    except Exception as exc:
        name = f"UNAVAILABLE:{exc}"
        association = "unknown"
        layer_index = -999
    unreal.log(
        "RED_SAND_T02_SWITCH "
        f"index={index} name={name} association={association} layer_index={layer_index} "
        f"value={fields.get('value')} override={fields.get('override')} "
        f"guid={fields.get('expression_guid')}"
    )
