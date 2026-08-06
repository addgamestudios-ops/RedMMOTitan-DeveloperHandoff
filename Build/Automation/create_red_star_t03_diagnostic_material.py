import unreal


# This asset is deliberately disposable and map-scoped through native code.  It does
# not modify the shipped M_RedStarSolid material or vendor content.  The geometry
# remains the existing camera-relative procedural star field; this material only
# prevents SkyAtmosphere aerial perspective from extinguishing its sparse emissive
# pixels during the Night_T03 visual acceptance test.
ASSET_PATH = "/Game/RedMMO/Environment/Tests/M_RedStar_T03Diagnostic"
PACKAGE_PATH = "/Game/RedMMO/Environment/Tests"
ASSET_NAME = "M_RedStar_T03Diagnostic"


def create_material():
    if unreal.EditorAssetLibrary.does_asset_exist(ASSET_PATH):
        existing = unreal.EditorAssetLibrary.load_asset(ASSET_PATH)
        if not isinstance(existing, unreal.Material):
            raise RuntimeError(f"{ASSET_PATH} exists but is not a Material")
        unreal.log_warning("RED_T03_STAR_DIAGNOSTIC_REUSING " + existing.get_path_name())
        return existing

    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        ASSET_NAME,
        PACKAGE_PATH,
        unreal.Material,
        unreal.MaterialFactoryNew(),
    )
    if not isinstance(material, unreal.Material):
        raise RuntimeError(f"Failed to create {ASSET_PATH}")

    material.set_editor_property("material_domain", unreal.MaterialDomain.MD_SURFACE)
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    # IsSky skips aerial perspective on the star polygons themselves.  Since this
    # material is used only on sparse hexagons, it cannot replace the sky background.
    material.set_editor_property("is_sky", True)

    editing = unreal.MaterialEditingLibrary
    color = editing.create_material_expression(
        material, unreal.MaterialExpressionVectorParameter, -420, -40
    )
    color.set_editor_property("parameter_name", "Color")
    color.set_editor_property(
        "default_value", unreal.LinearColor(0.72, 0.84, 1.0, 1.0)
    )
    emission = editing.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -420, 130
    )
    emission.set_editor_property("parameter_name", "Emission")
    emission.set_editor_property("default_value", 32.0)
    multiply = editing.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -120, 25
    )
    if not editing.connect_material_expressions(color, "", multiply, "A"):
        raise RuntimeError("Failed to connect Color to the T03 star emissive graph")
    if not editing.connect_material_expressions(emission, "", multiply, "B"):
        raise RuntimeError("Failed to connect Emission to the T03 star emissive graph")
    if not editing.connect_material_property(
        multiply, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    ):
        raise RuntimeError("Failed to connect T03 star graph to Emissive Color")

    editing.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise RuntimeError(f"Failed to save {ASSET_PATH}")
    return material


result = create_material()
unreal.log_warning(
    "RED_T03_STAR_DIAGNOSTIC_READY "
    + result.get_path_name()
    + " is_sky="
    + str(result.get_editor_property("is_sky"))
    + " blend="
    + str(result.get_editor_property("blend_mode"))
    + " two_sided="
    + str(result.get_editor_property("two_sided"))
)
