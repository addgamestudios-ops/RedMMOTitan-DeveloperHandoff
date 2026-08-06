import unreal


ASSET_PATH = "/Game/RedMMO/Environment/M_RedStarSpriteMasked"
PACKAGE_PATH = "/Game/RedMMO/Environment"
ASSET_NAME = "M_RedStarSpriteMasked"
POINT_TEXTURE = "/Game/ProjectilesVol1/Textures/T_Point5"


def create_or_rebuild_material():
    material = unreal.EditorAssetLibrary.load_asset(ASSET_PATH)
    if material is None:
        material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            ASSET_NAME,
            PACKAGE_PATH,
            unreal.Material,
            unreal.MaterialFactoryNew(),
        )
    if not isinstance(material, unreal.Material):
        raise RuntimeError(f"{ASSET_PATH} exists but is not a Material")

    point_texture = unreal.EditorAssetLibrary.load_asset(POINT_TEXTURE)
    if point_texture is None:
        raise RuntimeError(f"Missing required point texture: {POINT_TEXTURE}")

    # Render as a masked sky surface rather than translucent additive geometry.
    # The additive version inherited UE's translucency fogging and the 20-160 km
    # camera-relative shell was attenuated into the brown oval artifacts seen in
    # packaged GPU captures. IsSky bypasses atmospheric fog for these authored
    # points, while the texture mask keeps the background fully transparent.
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("is_sky", True)
    material.set_editor_property("opacity_mask_clip_value", 0.06)

    editing = unreal.MaterialEditingLibrary
    editing.delete_all_material_expressions(material)

    texture = editing.create_material_expression(
        material, unreal.MaterialExpressionTextureSampleParameter2D, -700, -30
    )
    texture.set_editor_property("parameter_name", "StarTexture")
    texture.set_editor_property("texture", point_texture)

    color = editing.create_material_expression(
        material, unreal.MaterialExpressionVectorParameter, -700, 180
    )
    color.set_editor_property("parameter_name", "Color")
    color.set_editor_property(
        "default_value", unreal.LinearColor(0.85, 0.92, 1.0, 1.0)
    )

    emission = editing.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -700, 350
    )
    emission.set_editor_property("parameter_name", "Emission")
    emission.set_editor_property("default_value", 12.0)

    masked_color = editing.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -400, 20
    )
    final_emission = editing.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -140, 20
    )

    if not editing.connect_material_expressions(texture, "RGB", masked_color, "A"):
        raise RuntimeError("Failed to connect StarTexture RGB to masked color")
    if not editing.connect_material_expressions(color, "", masked_color, "B"):
        raise RuntimeError("Failed to connect Color to masked color")
    if not editing.connect_material_expressions(masked_color, "", final_emission, "A"):
        raise RuntimeError("Failed to connect masked color to final emission")
    if not editing.connect_material_expressions(emission, "", final_emission, "B"):
        raise RuntimeError("Failed to connect Emission scalar")
    if not editing.connect_material_property(
        final_emission, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    ):
        raise RuntimeError("Failed to connect final emissive color")
    if not editing.connect_material_property(
        texture, "R", unreal.MaterialProperty.MP_OPACITY_MASK
    ):
        raise RuntimeError("Failed to connect StarTexture red channel to opacity mask")

    editing.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise RuntimeError(f"Failed to save {ASSET_PATH}")
    return material


result = create_or_rebuild_material()
unreal.log_warning(
    "RED_STAR_MATERIAL_READY "
    + result.get_path_name()
    + " blend="
    + str(result.get_editor_property("blend_mode"))
    + " two_sided="
    + str(result.get_editor_property("two_sided"))
    + " is_sky="
    + str(result.get_editor_property("is_sky"))
)
