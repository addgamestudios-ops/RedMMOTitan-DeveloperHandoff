"""Rebuild the project-owned Night_T03 Milky Way material.

The vendor texture and Engine sky mesh are read-only inputs.  The material derives
equirectangular UVs from the camera-to-pixel world direction so the runtime result
does not depend on SM_SkySphere's imported UV channel.
"""

import unreal


ASSET_PATH = "/Game/RedMMO/Environment/Tests/M_RedStar_T03MilkyWayWorldDir"
PACKAGE_PATH = "/Game/RedMMO/Environment/Tests"
ASSET_NAME = "M_RedStar_T03MilkyWayWorldDir"
ATLAS_PATH = "/Game/SpaceColony/Textures/T_milky_way"


UV_CODE = r"""
float3 d = normalize(WorldDirection);
float u = frac(atan2(d.y, d.x) * 0.15915494309189535 + 0.5);
float v = saturate(0.5 - asin(clamp(d.z, -1.0, 1.0)) * 0.3183098861837907);
return float2(u, v);
"""


def create_or_rebuild_material():
    existing = unreal.EditorAssetLibrary.load_asset(ASSET_PATH)
    if existing is not None:
        if not isinstance(existing, unreal.Material):
            raise RuntimeError(f"{ASSET_PATH} exists but is not a Material")
        unreal.log_warning("RED_NIGHT_T03_MILKYWAY_EXISTS " + existing.get_path_name())
        return existing

    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        ASSET_NAME,
        PACKAGE_PATH,
        unreal.Material,
        unreal.MaterialFactoryNew(),
    )
    if not isinstance(material, unreal.Material):
        raise RuntimeError(f"Failed to create {ASSET_PATH}")

    atlas = unreal.EditorAssetLibrary.load_asset(ATLAS_PATH)
    if not isinstance(atlas, unreal.Texture2D):
        raise RuntimeError(f"Missing required Texture2D: {ATLAS_PATH}")

    material.set_editor_property("material_domain", unreal.MaterialDomain.MD_SURFACE)
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("is_sky", True)

    editing = unreal.MaterialEditingLibrary
    world_position = editing.create_material_expression(
        material, unreal.MaterialExpressionWorldPosition, -1050, -260
    )
    camera_position = editing.create_material_expression(
        material, unreal.MaterialExpressionCameraPositionWS, -1050, -100
    )
    world_direction = editing.create_material_expression(
        material, unreal.MaterialExpressionSubtract, -800, -180
    )
    spherical_uv = editing.create_material_expression(
        material, unreal.MaterialExpressionCustom, -530, -180
    )
    spherical_uv.set_editor_property(
        "description", "Camera-relative world-direction equirectangular projection"
    )
    spherical_uv.set_editor_property("code", UV_CODE)
    spherical_uv.set_editor_property(
        "output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT2
    )
    custom_input = unreal.CustomInput()
    custom_input.set_editor_property("input_name", "WorldDirection")
    spherical_uv.set_editor_property("inputs", [custom_input])

    atlas_sample = editing.create_material_expression(
        material, unreal.MaterialExpressionTextureSampleParameter2D, -250, -180
    )
    atlas_sample.set_editor_property("parameter_name", "StarAtlas")
    atlas_sample.set_editor_property("texture", atlas)

    emission = editing.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -250, 40
    )
    emission.set_editor_property("parameter_name", "Emission")
    emission.set_editor_property("default_value", 12.0)

    visibility = editing.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -250, 160
    )
    visibility.set_editor_property("parameter_name", "Visibility")
    visibility.set_editor_property("default_value", 1.0)

    gain = editing.create_material_expression(
        material, unreal.MaterialExpressionMultiply, 20, 80
    )
    emissive = editing.create_material_expression(
        material, unreal.MaterialExpressionMultiply, 260, -100
    )

    connections = [
        ("world-position", editing.connect_material_expressions(
            world_position, "", world_direction, "A")),
        ("camera-position", editing.connect_material_expressions(
            camera_position, "", world_direction, "B")),
        ("world-direction", editing.connect_material_expressions(
            world_direction, "", spherical_uv, "WorldDirection")),
        ("spherical-uv", editing.connect_material_expressions(
            spherical_uv, "", atlas_sample, "UVs")),
        ("emission", editing.connect_material_expressions(emission, "", gain, "A")),
        ("visibility", editing.connect_material_expressions(
            visibility, "", gain, "B")),
        ("atlas-rgb", editing.connect_material_expressions(
            atlas_sample, "RGB", emissive, "A")),
        ("gain", editing.connect_material_expressions(gain, "", emissive, "B")),
        ("emissive-output", editing.connect_material_property(
            emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)),
    ]
    failed_connections = [name for name, connected in connections if not connected]
    if failed_connections:
        raise RuntimeError(
            "Failed Night_T03 Milky Way graph connections: "
            + ", ".join(failed_connections)
        )

    editing.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise RuntimeError(f"Failed to save {ASSET_PATH}")
    return material


result = create_or_rebuild_material()
unreal.log_warning(
    "RED_NIGHT_T03_MILKYWAY_READY "
    + result.get_path_name()
    + " projection=world-direction atlas="
    + ATLAS_PATH
)
