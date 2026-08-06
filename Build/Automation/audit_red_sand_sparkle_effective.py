"""Read-only effective-parameter and sparkle-branch audit for isolated T02."""

import unreal


T02 = "/Game/RedMMO/Materials/DesertSparkleTest/MI_PlanetBiome_DesertSparkle_T02"
DEMO = "/Game/SoStylized/Environment/Landscape/Materials/MI_Landscape_Desert"
FUNCTION = "/Game/SoStylized/Materials/MF_DesertSand"
SPARKLE_FUNCTION = "/Game/SoStylized/Materials/MF_Sparkle"


def safe_property(obj, name):
    try:
        value = obj.get_editor_property(name)
        if isinstance(value, unreal.Object):
            return value.get_path_name()
        return str(value)
    except Exception as exc:
        return f"<unavailable:{exc}>"


def dump_instance(label, path):
    instance = unreal.load_asset(path)
    if not instance:
        raise RuntimeError(f"Missing {label}: {path}")
    unreal.log(f"RED_SAND_EFFECTIVE_INSTANCE label={label} path={path}")
    for name in unreal.MaterialEditingLibrary.get_vector_parameter_names(instance):
        if "Sparkle" not in str(name):
            continue
        value = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(instance, name)
        overridden = unreal.MaterialEditingLibrary.is_material_instance_parameter_overridden(instance, name)
        unreal.log(
            f"RED_SAND_EFFECTIVE_VECTOR label={label} name={name!s} value={value!s} overridden={overridden}"
        )
    for name in unreal.MaterialEditingLibrary.get_scalar_parameter_names(instance):
        if "Sparkle" not in str(name):
            continue
        value = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(instance, name)
        overridden = unreal.MaterialEditingLibrary.is_material_instance_parameter_overridden(instance, name)
        unreal.log(
            f"RED_SAND_EFFECTIVE_SCALAR label={label} name={name!s} value={value!s} overridden={overridden}"
        )
    for name in unreal.MaterialEditingLibrary.get_static_switch_parameter_names(instance):
        if not any(token in str(name) for token in ("Sparkle", "WorldRotation", "Ripple")):
            continue
        value = unreal.MaterialEditingLibrary.get_material_instance_static_switch_parameter_value(
            instance, name
        )
        overridden = unreal.MaterialEditingLibrary.is_material_instance_parameter_overridden(instance, name)
        unreal.log(
            f"RED_SAND_EFFECTIVE_SWITCH label={label} name={name!s} value={value} overridden={overridden}"
        )


dump_instance("t02", T02)
dump_instance("demo", DEMO)

function = unreal.load_asset(FUNCTION)
if not function:
    raise RuntimeError(f"Missing function: {FUNCTION}")
expressions = unreal.MaterialEditingLibrary.get_material_function_expressions(function)
for index, expression in enumerate(expressions):
    class_name = expression.get_class().get_name()
    parameter_name = safe_property(expression, "parameter_name")
    material_function = safe_property(expression, "material_function")
    if (
        "Sparkle" in parameter_name
        or "Sparkle" in material_function
        or "StaticSwitch" in class_name
    ):
        unreal.log(
            "RED_SAND_EFFECTIVE_EXPR "
            f"index={index} class={class_name} path={expression.get_path_name()} "
            f"parameter={parameter_name} function={material_function} "
            f"default={safe_property(expression, 'default_value')} "
            f"a={safe_property(expression, 'a')} b={safe_property(expression, 'b')}"
        )
        if "MaterialFunctionCall" in class_name:
            unreal.log(
                "RED_SAND_EFFECTIVE_CALL "
                f"index={index} "
                f"input_names={list(unreal.MaterialEditingLibrary.get_material_expression_input_names(expression))} "
                f"output_names={list(unreal.MaterialEditingLibrary.get_material_expression_output_names(expression))} "
                f"inputs={safe_property(expression, 'function_inputs')} "
                f"outputs={safe_property(expression, 'function_outputs')}"
            )

sparkle_function = unreal.load_asset(SPARKLE_FUNCTION)
if not sparkle_function:
    raise RuntimeError(f"Missing sparkle function: {SPARKLE_FUNCTION}")
sparkle_expressions = unreal.MaterialEditingLibrary.get_material_function_expressions(sparkle_function)
unreal.log(
    f"RED_SAND_EFFECTIVE_SPARKLE_FUNCTION path={SPARKLE_FUNCTION} expressions={len(sparkle_expressions)}"
)
for index, expression in enumerate(sparkle_expressions):
    class_name = expression.get_class().get_name()
    if any(token in class_name for token in ("FunctionInput", "FunctionOutput", "Parameter", "StaticSwitch", "CollectionParameter")):
        unreal.log(
            "RED_SAND_EFFECTIVE_SPARKLE_EXPR "
            f"index={index} class={class_name} path={expression.get_path_name()} "
            f"input={safe_property(expression, 'input_name')} "
            f"output={safe_property(expression, 'output_name')} "
            f"parameter={safe_property(expression, 'parameter_name')} "
            f"default={safe_property(expression, 'default_value')}"
        )

unreal.log("RED_SAND_EFFECTIVE_RESULT OK read-only")
