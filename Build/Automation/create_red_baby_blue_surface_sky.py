import unreal


ASSET_PATH = "/Game/RedMMO/Environment/M_RedBabyBlueSurfaceSky"
PACKAGE_PATH = "/Game/RedMMO/Environment"
ASSET_NAME = "M_RedBabyBlueSurfaceSky"


def create_or_rebuild_material():
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

    # A deliberately tiny, deterministic surface-only sky.  The authored
    # SoStylized day curve grades purple under the project's physical 75 klux
    # sun/exposure, so the runtime surface dome needs an explicit Fortnite-like
    # baby-blue emission.  The dome is hidden before the orbital presentation
    # takes over; the real SkyAtmosphere remains responsible for the limb.
    material.set_editor_property("material_domain", unreal.MaterialDomain.MD_SURFACE)
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("is_sky", True)

    editing = unreal.MaterialEditingLibrary
    existing_expressions = list(editing.get_material_expressions(material))
    existing_color = next(
        (
            expression
            for expression in existing_expressions
            if isinstance(expression, unreal.MaterialExpressionVectorParameter)
            and str(expression.get_editor_property("parameter_name")) == "SkyColor"
        ),
        None,
    )
    existing_emission = next(
        (
            expression
            for expression in existing_expressions
            if isinstance(expression, unreal.MaterialExpressionScalarParameter)
            and str(expression.get_editor_property("parameter_name")) == "Emission"
        ),
        None,
    )

    # UE 5.8 roots expressions belonging to a loaded material. Calling
    # delete_all_material_expressions on that asset asserts in UObjectBaseUtility
    # before Python can save anything. Update the stable named parameters in place
    # and only construct the graph for a genuinely new, empty material.
    if existing_color is not None and existing_emission is not None:
        existing_color.set_editor_property(
            "default_value", unreal.LinearColor(0.35, 0.72, 1.0, 1.0)
        )
        existing_emission.set_editor_property("default_value", 18000.0)
        editing.recompile_material(material)
        if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
            raise RuntimeError(f"Failed to save {ASSET_PATH}")
        return material

    if existing_expressions and not material_was_created:
        raise RuntimeError(
            f"{ASSET_PATH} has an unexpected material graph; refusing a destructive rebuild"
        )

    color = editing.create_material_expression(
        material, unreal.MaterialExpressionVectorParameter, -420, -40
    )
    color.set_editor_property("parameter_name", "SkyColor")
    color.set_editor_property(
        "default_value", unreal.LinearColor(0.35, 0.72, 1.0, 1.0)
    )

    emission = editing.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -420, 130
    )
    emission.set_editor_property("parameter_name", "Emission")
    emission.set_editor_property("default_value", 18000.0)

    final_emission = editing.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -110, 20
    )
    if not editing.connect_material_expressions(color, "", final_emission, "A"):
        raise RuntimeError("Failed to connect SkyColor")
    if not editing.connect_material_expressions(emission, "", final_emission, "B"):
        raise RuntimeError("Failed to connect Emission")
    if not editing.connect_material_property(
        final_emission, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    ):
        raise RuntimeError("Failed to connect emissive output")

    editing.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise RuntimeError(f"Failed to save {ASSET_PATH}")
    return material


result = create_or_rebuild_material()
unreal.log_warning(
    "RED_BABY_BLUE_SKY_MATERIAL_READY "
    + result.get_path_name()
    + " is_sky="
    + str(result.get_editor_property("is_sky"))
)
