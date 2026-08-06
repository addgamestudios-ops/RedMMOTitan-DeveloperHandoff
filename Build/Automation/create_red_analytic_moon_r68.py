"""Create the project-owned R68 unlit visual-moon material.

The asset is presentation-only. It owns no collision, gravity, orbit, terrain,
water, atmosphere, or gameplay authority.
"""

import unreal


ASSET_PATH = "/Game/RedMMO/Environment/M_RedAnalyticMoon_R68"
PACKAGE_PATH = "/Game/RedMMO/Environment"
ASSET_NAME = "M_RedAnalyticMoon_R68"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


existing = unreal.EditorAssetLibrary.load_asset(ASSET_PATH)
if existing is not None:
    require(isinstance(existing, unreal.Material), "R68 moon path is not a Material")
    material = existing
else:
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        ASSET_NAME,
        PACKAGE_PATH,
        unreal.Material,
        unreal.MaterialFactoryNew(),
    )
    require(isinstance(material, unreal.Material), "Unable to create R68 moon material")
    material.set_editor_property("material_domain", unreal.MaterialDomain.MD_SURFACE)
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)

    editing = unreal.MaterialEditingLibrary
    moon_color = editing.create_material_expression(
        material, unreal.MaterialExpressionVectorParameter, -600, -100
    )
    moon_color.set_editor_property("parameter_name", "MoonColor")
    moon_color.set_editor_property("default_value", unreal.LinearColor(0.72, 0.82, 1.0, 1.0))

    emission = editing.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -600, 50
    )
    emission.set_editor_property("parameter_name", "Emission")
    emission.set_editor_property("default_value", 2.5)

    visibility = editing.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -600, 180
    )
    visibility.set_editor_property("parameter_name", "Visibility")
    visibility.set_editor_property("default_value", 0.0)

    color_times_emission = editing.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -300, -50
    )
    output = editing.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -100, 0
    )
    require(editing.connect_material_expressions(moon_color, "", color_times_emission, "A"),
            "Unable to connect MoonColor")
    require(editing.connect_material_expressions(emission, "", color_times_emission, "B"),
            "Unable to connect Emission")
    require(editing.connect_material_expressions(color_times_emission, "", output, "A"),
            "Unable to connect color-times-emission")
    require(editing.connect_material_expressions(visibility, "", output, "B"),
            "Unable to connect Visibility")
    require(editing.connect_material_property(output, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR),
            "Unable to connect moon emissive output")
    editing.recompile_material(material)
    require(unreal.EditorAssetLibrary.save_loaded_asset(material, False),
            "Unable to save R68 moon material")

unreal.log_warning("REDMMO_R68_MOON_MATERIAL_READY " + material.get_path_name())
