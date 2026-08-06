import unreal


# Disposable Night_T03-only star material.  Unlike the first opaque diagnostic,
# this uses additive blending so it is drawn after the physical SkyAtmosphere.
# It remains a project asset and is never assigned to production maps/materials.
ASSET_PATH = "/Game/RedMMO/Environment/Tests/M_RedStar_T03OverlayDiagnostic"
PACKAGE_PATH = "/Game/RedMMO/Environment/Tests"
ASSET_NAME = "M_RedStar_T03OverlayDiagnostic"


def create_material():
    created = False
    if unreal.EditorAssetLibrary.does_asset_exist(ASSET_PATH):
        material = unreal.EditorAssetLibrary.load_asset(ASSET_PATH)
        if not isinstance(material, unreal.Material):
            raise RuntimeError(f"{ASSET_PATH} exists but is not a Material")
        unreal.log_warning("RED_T03_STAR_OVERLAY_REUSING " + material.get_path_name())
    else:
        material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            ASSET_NAME,
            PACKAGE_PATH,
            unreal.Material,
            unreal.MaterialFactoryNew(),
        )
        if not isinstance(material, unreal.Material):
            raise RuntimeError(f"Failed to create {ASSET_PATH}")
        created = True

    material.set_editor_property("material_domain", unreal.MaterialDomain.MD_SURFACE)
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    # This material is a disposable render-layer proof. Drawing it after depth
    # establishes whether the already-verified procedural star geometry reaches
    # the real D3D12 main view; it is never selected by normal gameplay.
    material.set_editor_property("disable_depth_test", True)

    if created:
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
            raise RuntimeError("Failed to connect Color to the T03 overlay star graph")
        if not editing.connect_material_expressions(emission, "", multiply, "B"):
            raise RuntimeError("Failed to connect Emission to the T03 overlay star graph")
        if not editing.connect_material_property(
            multiply, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
        ):
            raise RuntimeError("Failed to connect T03 overlay graph to Emissive Color")

    unreal.MaterialEditingLibrary.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise RuntimeError(f"Failed to save {ASSET_PATH}")
    return material


result = create_material()
unreal.log_warning(
    "RED_T03_STAR_OVERLAY_READY "
    + result.get_path_name()
    + " blend="
    + str(result.get_editor_property("blend_mode"))
    + " two_sided="
    + str(result.get_editor_property("two_sided"))
    + " depth_test_disabled="
    + str(result.get_editor_property("disable_depth_test"))
)
