"""Read-only audit of the isolated PlanetGen/So Stylized material graph interfaces.

This script never saves a package.  It records the function-call pin signatures,
material parameter visibility, and source function expression classes needed to
diagnose the T02 test chain without opening a second GPU editor.
"""

import unreal


SOURCE_FUNCTION = "/Game/SoStylized/Materials/MF_DesertSand"
SOURCE_PLANET = "/PlanetGen/Materials/Landscape/M_Planet"
TEST_PLANET = "/Game/RedMMO/Materials/DesertSparkleTest/M_Planet_DesertSparkle_T02"
TEST_BIOME = "/Game/RedMMO/Materials/DesertSparkleTest/MI_PlanetBiome_DesertSparkle_T02"


def safe_property(obj, name):
    try:
        value = obj.get_editor_property(name)
        if isinstance(value, unreal.Object):
            return value.get_path_name()
        return str(value)
    except Exception as exc:
        return f"<unavailable:{exc}>"


def dump_material(label, path):
    asset = unreal.load_asset(path)
    if not asset:
        raise RuntimeError(f"Missing {label}: {path}")
    expressions = unreal.MaterialEditingLibrary.get_material_expressions(asset)
    unreal.log(
        f"RED_SAND_GRAPH_MATERIAL label={label} path={path} expressions={len(expressions)} "
        f"scalars={list(unreal.MaterialEditingLibrary.get_scalar_parameter_names(asset))} "
        f"switches={list(unreal.MaterialEditingLibrary.get_static_switch_parameter_names(asset))}"
    )
    for index, expression in enumerate(expressions):
        class_name = expression.get_class().get_name()
        if "MaterialFunctionCall" not in class_name:
            continue
        function_path = safe_property(expression, "material_function")
        inputs = list(unreal.MaterialEditingLibrary.get_material_expression_input_names(expression))
        outputs = list(unreal.MaterialEditingLibrary.get_material_expression_output_names(expression))
        upstream = [
            node.get_path_name()
            for node in unreal.MaterialEditingLibrary.get_inputs_for_material_expression(asset, expression)
            if node
        ]
        unreal.log(
            f"RED_SAND_GRAPH_CALL material={label} index={index} function={function_path} "
            f"inputs={inputs} outputs={outputs} upstream={upstream}"
        )
    return asset


source_function = unreal.load_asset(SOURCE_FUNCTION)
if not source_function:
    raise RuntimeError(f"Missing source function: {SOURCE_FUNCTION}")
function_expressions = unreal.MaterialEditingLibrary.get_material_function_expressions(source_function)
unreal.log(
    f"RED_SAND_GRAPH_FUNCTION path={SOURCE_FUNCTION} expressions={len(function_expressions)} "
    f"usage={safe_property(source_function, 'material_function_usage')}"
)
for index, expression in enumerate(function_expressions):
    class_name = expression.get_class().get_name()
    if any(token in class_name for token in ("FunctionInput", "FunctionOutput", "Parameter", "StaticSwitch")):
        unreal.log(
            f"RED_SAND_GRAPH_FUNCTION_EXPR index={index} class={class_name} path={expression.get_path_name()} "
            f"input_name={safe_property(expression, 'input_name')} "
            f"output_name={safe_property(expression, 'output_name')} "
            f"parameter_name={safe_property(expression, 'parameter_name')} "
            f"expression_guid={safe_property(expression, 'expression_guid')}"
        )

dump_material("source_planet", SOURCE_PLANET)
dump_material("test_planet", TEST_PLANET)

test_biome = unreal.load_asset(TEST_BIOME)
if not test_biome:
    raise RuntimeError(f"Missing test biome: {TEST_BIOME}")
unreal.log(
    f"RED_SAND_GRAPH_MI path={TEST_BIOME} parent={safe_property(test_biome, 'parent')} "
    f"scalars={list(unreal.MaterialEditingLibrary.get_scalar_parameter_names(test_biome))} "
    f"switches={list(unreal.MaterialEditingLibrary.get_static_switch_parameter_names(test_biome))}"
)
unreal.log("RED_SAND_GRAPH_RESULT OK read-only")
