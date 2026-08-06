import unreal


ASSET_PATH = "/Game/RedMMO/Environment/M_RedStarSolid"
PACKAGE_PATH = "/Game/RedMMO/Environment"
ASSET_NAME = "M_RedStarSolid"


def create_or_update_material():
    material = unreal.EditorAssetLibrary.load_asset(ASSET_PATH)
    material_was_created = material is None
    if material is None:
        material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            ASSET_NAME,
            PACKAGE_PATH,
            unreal.Material,
            unreal.MaterialFactoryNew(),
        )
    if not isinstance(material, unreal.Material):
        raise RuntimeError(f"{ASSET_PATH} exists but is not a Material")

    material.set_editor_property("material_domain", unreal.MaterialDomain.MD_SURFACE)
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    # Sparse star quads are ordinary emissive geometry, not a full-screen sky.
    # Marking them IsSky makes UE suppress SkyAtmosphere for every uncovered
    # pixel, producing the mostly-black background seen in the night orbit test.
    material.set_editor_property("is_sky", False)

    editing = unreal.MaterialEditingLibrary
    expressions = list(editing.get_material_expressions(material))
    color = next(
        (
            expression
            for expression in expressions
            if isinstance(expression, unreal.MaterialExpressionVectorParameter)
            and str(expression.get_editor_property("parameter_name")) == "Color"
        ),
        None,
    )
    emission = next(
        (
            expression
            for expression in expressions
            if isinstance(expression, unreal.MaterialExpressionScalarParameter)
            and str(expression.get_editor_property("parameter_name")) == "Emission"
        ),
        None,
    )

    # UE 5.8 asserts when Python destructively removes expressions from a loaded
    # material. Update the stable parameters in place, and only construct a graph
    # for a genuinely new empty asset.
    if color is not None and emission is not None:
        color.set_editor_property(
            "default_value", unreal.LinearColor(0.88, 0.94, 1.0, 1.0)
        )
        emission.set_editor_property("default_value", 16.0)
        editing.recompile_material(material)
        if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
            raise RuntimeError(f"Failed to save {ASSET_PATH}")
        return material

    if expressions and not material_was_created:
        raise RuntimeError(
            f"{ASSET_PATH} has an unexpected graph; refusing a destructive rebuild"
        )

    color = editing.create_material_expression(
        material, unreal.MaterialExpressionVectorParameter, -420, -40
    )
    color.set_editor_property("parameter_name", "Color")
    color.set_editor_property(
        "default_value", unreal.LinearColor(0.88, 0.94, 1.0, 1.0)
    )
    emission = editing.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -420, 130
    )
    emission.set_editor_property("parameter_name", "Emission")
    emission.set_editor_property("default_value", 16.0)
    final_emission = editing.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -110, 20
    )
    if not editing.connect_material_expressions(color, "", final_emission, "A"):
        raise RuntimeError("Failed to connect star Color")
    if not editing.connect_material_expressions(emission, "", final_emission, "B"):
        raise RuntimeError("Failed to connect star Emission")
    if not editing.connect_material_property(
        final_emission, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    ):
        raise RuntimeError("Failed to connect star emissive output")

    editing.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise RuntimeError(f"Failed to save {ASSET_PATH}")
    return material


result = create_or_update_material()
unreal.log_warning(
    "RED_STAR_SOLID_READY "
    + result.get_path_name()
    + " blend="
    + str(result.get_editor_property("blend_mode"))
    + " two_sided="
    + str(result.get_editor_property("two_sided"))
    + " is_sky="
    + str(result.get_editor_property("is_sky"))
)
