"""Create a test-only So Stylized desert material and demo-tuned instance.

This script intentionally creates and edits assets only beneath
/Game/RedMMO/Materials/DesertSparkleTest.  It never changes the purchased
So Stylized or PlanetGen source assets.
"""

import traceback
import unreal


TEST_ROOT = "/Game/RedMMO/Materials/DesertSparkleTest"
MATERIAL_PATH = TEST_ROOT + "/M_DesertSandSparkle_T01"
INSTANCE_PATH = TEST_ROOT + "/MI_DesertSandSparkle_Demo_T01"
FUNCTION_PATH = "/Game/SoStylized/Materials/MF_DesertSand"


def fail(message):
    unreal.log_error("[RedMMO Sand Test] " + message)
    raise RuntimeError(message)


try:
    material = unreal.load_asset(MATERIAL_PATH)
    function = unreal.load_asset(FUNCTION_PATH)
    if not material:
        fail("Missing test material: " + MATERIAL_PATH)
    if not function:
        fail("Missing purchased So Stylized function: " + FUNCTION_PATH)

    # This is a brand-new test material. Clear only its own graph so the
    # operation remains repeatable while leaving all source assets intact.
    for expression in list(unreal.MaterialEditingLibrary.get_material_expressions(material)):
        unreal.MaterialEditingLibrary.delete_material_expression(material, expression)

    material.set_editor_property("use_material_attributes", True)
    call = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionMaterialFunctionCall,
        -420,
        0,
    )
    call.set_editor_property("material_function", function)
    unreal.MaterialEditingLibrary.connect_material_property(
        call,
        "Attributes",
        unreal.MaterialProperty.MP_MATERIAL_ATTRIBUTES,
    )
    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)

    instance = unreal.load_asset(INSTANCE_PATH)
    if not instance:
        factory = unreal.MaterialInstanceConstantFactoryNew()
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        instance = asset_tools.create_asset(
            "MI_DesertSandSparkle_Demo_T01",
            TEST_ROOT,
            unreal.MaterialInstanceConstant,
            factory,
        )
    if not instance:
        fail("Could not create or load test material instance")
    # UE 5.8's MaterialInstanceConstantFactoryNew does not expose an
    # initial_parent property.  Assign the parent after creation instead;
    # this changes only the isolated /Game test asset.
    unreal.MaterialEditingLibrary.set_material_instance_parent(instance, material)

    # Explicitly mirror the values used by the purchased So Stylized desert
    # demonstration material. Keeping the values here (instead of relying on
    # function defaults) makes this project-side test repeatable and lets us
    # compare it honestly against the demo map. This changes only the test MI.
    demo_scalars = {
        "Desert Sand Scale": 1024.0,
        "Desert Sand Normal Texture Scale": 2400.0,
        "Desert Sand Roughness Min": 0.5,
        "Desert Sand Roughness Max": 0.7,
        "Desert Sand Specular": 0.2,
        "Desert Sparkle Scale": 1600.0,
        "Desert Sparkle Brightness": 15.0,
        "Desert Sparkle Contrast": 8.0,
        "Desert Sparkle Tolerance": 0.75,
        "Desert Sparkle Speed": 1.0,
        "Desert Sparkle Fade Start": 1000.0,
        "Desert Sparkle Fade End": 5000.0,
        "Desert Sparkle Shrink Amount": 0.3,
        "Desert Sparkle Shrink Near Distance": 500.0,
        "Desert Sparkle Shrink Far Distance": 2500.0,
    }
    for name, value in demo_scalars.items():
        unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
            instance,
            unreal.Name(name),
            value,
        )
    unreal.MaterialEditingLibrary.update_material_instance(instance)
    unreal.EditorAssetLibrary.save_loaded_asset(instance)
    unreal.log("[RedMMO Sand Test] Created test-only material and demo-tuned instance:")
    unreal.log("  " + MATERIAL_PATH)
    unreal.log("  " + INSTANCE_PATH)
except Exception:
    unreal.log_error("[RedMMO Sand Test] Failed:\n" + traceback.format_exc())
    raise
