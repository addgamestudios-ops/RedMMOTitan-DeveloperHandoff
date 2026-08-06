"""Create a sphere-safe So Stylized Single Layer Water material for T04.

Vendor assets are read-only inputs.  This project-owned material keeps the
purchased So Stylized animated normal treatment, but removes the flat-demo
distance-field, scene-depth shoreline, planar-world and day-cycle branches.
Single Layer Water supplies physically coherent blue absorption/scattering on
the moonlit radial ocean instead of the dark translucent wedge from V2.
"""

import os
import unreal


ROOT = "/Game/RedMMO/Environment/Tests"
VARIANT = os.environ.get("RED_RADIAL_WATER_VARIANT", "V3").upper()
IS_LIT_V4 = VARIANT == "V4"
MATERIAL_NAME = "M_RedRadialWater_T04_V4" if IS_LIT_V4 else "M_RedRadialWater_T04_V3"
INSTANCE_NAME = "MI_RedRadialWater_Night_T04_V4" if IS_LIT_V4 else "MI_RedRadialWater_Night_T04_V3"
MATERIAL_PATH = f"{ROOT}/{MATERIAL_NAME}"
INSTANCE_PATH = f"{ROOT}/{INSTANCE_NAME}"
NORMAL_TEXTURE_PATH = "/Game/SoStylized/Demo/Textures/T_Water_N"


def fail(message: str) -> None:
    unreal.log_error(f"RED_RADIAL_WATER_T04_{VARIANT}_FAILED " + message)
    raise RuntimeError(message)


def parameter(editing, material, expression_class, name, default, x, y):
    expression = editing.create_material_expression(material, expression_class, x, y)
    if not expression:
        fail(f"could not create parameter {name}")
    expression.set_editor_property("parameter_name", name)
    expression.set_editor_property("default_value", default)
    return expression


for asset_path in (MATERIAL_PATH, INSTANCE_PATH):
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        fail(f"{asset_path} already exists; use a new suffix rather than rebuilding in place")

normal_texture = unreal.EditorAssetLibrary.load_asset(NORMAL_TEXTURE_PATH)
if not isinstance(normal_texture, unreal.Texture2D):
    fail(f"missing purchased So Stylized water normal {NORMAL_TEXTURE_PATH}")

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
material = asset_tools.create_asset(
    MATERIAL_NAME, ROOT, unreal.Material, unreal.MaterialFactoryNew()
)
if not isinstance(material, unreal.Material):
    fail(f"could not create {MATERIAL_PATH}")

material.set_editor_property("material_domain", unreal.MaterialDomain.MD_SURFACE)
material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE if IS_LIT_V4 else unreal.BlendMode.BLEND_MASKED)
material.set_editor_property(
    "shading_model",
    unreal.MaterialShadingModel.MSM_DEFAULT_LIT if IS_LIT_V4
    else unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER,
)
material.set_editor_property("two_sided", False)
material.set_editor_property("tangent_space_normal", True)
material.set_editor_property("opacity_mask_clip_value", 0.0)

editing = unreal.MaterialEditingLibrary

uv = editing.create_material_expression(
    material, unreal.MaterialExpressionTextureCoordinate, -1500, -320
)
tiling_1 = parameter(
    editing, material, unreal.MaterialExpressionScalarParameter,
    "WaveTiling1", 4096.0, -1500, -160
)
tiling_2 = parameter(
    editing, material, unreal.MaterialExpressionScalarParameter,
    "WaveTiling2", 6144.0, -1500, 0
)
scaled_uv_1 = editing.create_material_expression(
    material, unreal.MaterialExpressionMultiply, -1260, -320
)
scaled_uv_2 = editing.create_material_expression(
    material, unreal.MaterialExpressionMultiply, -1260, -80
)
panner_1 = editing.create_material_expression(
    material, unreal.MaterialExpressionPanner, -1030, -320
)
panner_1.set_editor_property("speed_x", 0.011)
panner_1.set_editor_property("speed_y", -0.007)
panner_2 = editing.create_material_expression(
    material, unreal.MaterialExpressionPanner, -1030, -80
)
panner_2.set_editor_property("speed_x", -0.008)
panner_2.set_editor_property("speed_y", 0.010)

normal_1 = editing.create_material_expression(
    material, unreal.MaterialExpressionTextureSampleParameter2D, -800, -320
)
normal_1.set_editor_property("parameter_name", "SoStylizedWaterNormal1")
normal_1.set_editor_property("texture", normal_texture)
normal_1.set_editor_property(
    "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL
)
normal_2 = editing.create_material_expression(
    material, unreal.MaterialExpressionTextureSampleParameter2D, -800, -80
)
normal_2.set_editor_property("parameter_name", "SoStylizedWaterNormal2")
normal_2.set_editor_property("texture", normal_texture)
normal_2.set_editor_property(
    "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL
)
blend_amount = parameter(
    editing, material, unreal.MaterialExpressionScalarParameter,
    "NormalBlend", 0.5, -800, 120
)
normal_blend = editing.create_material_expression(
    material, unreal.MaterialExpressionLinearInterpolate, -560, -180
)
normal_normalize = editing.create_material_expression(
    material, unreal.MaterialExpressionNormalize, -360, -180
)

strength = parameter(
    editing, material, unreal.MaterialExpressionScalarParameter,
    "NormalStrength", 0.42, -800, 300
)
fade_start = parameter(
    editing, material, unreal.MaterialExpressionScalarParameter,
    "NormalFadeStartCm", 50000.0, -1500, 320
)
fade_end = parameter(
    editing, material, unreal.MaterialExpressionScalarParameter,
    "NormalFadeEndCm", 250000.0, -1500, 480
)
pixel_depth = editing.create_material_expression(
    material, unreal.MaterialExpressionPixelDepth, -1500, 640
)
depth_minus_start = editing.create_material_expression(
    material, unreal.MaterialExpressionSubtract, -1240, 400
)
fade_range = editing.create_material_expression(
    material, unreal.MaterialExpressionSubtract, -1240, 600
)
fade_ratio = editing.create_material_expression(
    material, unreal.MaterialExpressionDivide, -1010, 500
)
fade_saturate = editing.create_material_expression(
    material, unreal.MaterialExpressionSaturate, -810, 500
)
fade_inverse = editing.create_material_expression(
    material, unreal.MaterialExpressionOneMinus, -620, 500
)
effective_strength = editing.create_material_expression(
    material, unreal.MaterialExpressionMultiply, -430, 400
)
flat_normal = parameter(
    editing, material, unreal.MaterialExpressionVectorParameter,
    "FlatNormal", unreal.LinearColor(0.0, 0.0, 1.0, 1.0), -430, 220
)
normal_output = editing.create_material_expression(
    material, unreal.MaterialExpressionLinearInterpolate, -160, -100
)

base_color = parameter(
    editing, material, unreal.MaterialExpressionVectorParameter,
    "WaterTint", unreal.LinearColor(0.008, 0.12, 0.34, 1.0), 80, -80
)
roughness = parameter(
    editing, material, unreal.MaterialExpressionScalarParameter,
    "Roughness", 0.16, 80, 60
)
specular = parameter(
    editing, material, unreal.MaterialExpressionScalarParameter,
    "Specular", 0.45, 80, 180
)
opacity_mask = editing.create_material_expression(
    material, unreal.MaterialExpressionConstant, 80, 300
)
opacity_mask.set_editor_property("r", 1.0)

scattering = parameter(
    editing, material, unreal.MaterialExpressionVectorParameter,
    "ScatteringCoefficients",
    unreal.LinearColor(0.000003, 0.000020, 0.000050, 1.0), 320, -260
)
absorption = parameter(
    editing, material, unreal.MaterialExpressionVectorParameter,
    "AbsorptionCoefficients",
    unreal.LinearColor(0.000080, 0.000018, 0.000006, 1.0), 320, -100
)
phase_g = parameter(
    editing, material, unreal.MaterialExpressionScalarParameter,
    "PhaseG", 0.72, 320, 60
)
behind_water = parameter(
    editing, material, unreal.MaterialExpressionVectorParameter,
    "ColorScaleBehindWater",
    unreal.LinearColor(0.30, 0.68, 1.0, 1.0), 320, 220
)
night_fill = parameter(
    editing, material, unreal.MaterialExpressionScalarParameter,
    "NightFill", 0.22, 320, 380
)
night_emissive = editing.create_material_expression(
    material, unreal.MaterialExpressionMultiply, 560, 360
)
single_layer = None
if not IS_LIT_V4:
    single_layer = editing.create_material_expression(
        material, unreal.MaterialExpressionSingleLayerWaterMaterialOutput, 620, -80
    )

connections = [
    ("uv-scale1-a", editing.connect_material_expressions(uv, "", scaled_uv_1, "A")),
    ("uv-scale1-b", editing.connect_material_expressions(tiling_1, "", scaled_uv_1, "B")),
    ("uv-scale2-a", editing.connect_material_expressions(uv, "", scaled_uv_2, "A")),
    ("uv-scale2-b", editing.connect_material_expressions(tiling_2, "", scaled_uv_2, "B")),
    ("panner1", editing.connect_material_expressions(scaled_uv_1, "", panner_1, "Coordinate")),
    ("panner2", editing.connect_material_expressions(scaled_uv_2, "", panner_2, "Coordinate")),
    ("normal1-uv", editing.connect_material_expressions(panner_1, "", normal_1, "UVs")),
    ("normal2-uv", editing.connect_material_expressions(panner_2, "", normal_2, "UVs")),
    ("normal1-blend", editing.connect_material_expressions(normal_1, "RGB", normal_blend, "A")),
    ("normal2-blend", editing.connect_material_expressions(normal_2, "RGB", normal_blend, "B")),
    ("normal-blend-alpha", editing.connect_material_expressions(blend_amount, "", normal_blend, "Alpha")),
    ("normal-normalize", editing.connect_material_expressions(normal_blend, "", normal_normalize, "VectorInput")),
    ("depth-start-a", editing.connect_material_expressions(pixel_depth, "", depth_minus_start, "A")),
    ("depth-start-b", editing.connect_material_expressions(fade_start, "", depth_minus_start, "B")),
    ("fade-range-a", editing.connect_material_expressions(fade_end, "", fade_range, "A")),
    ("fade-range-b", editing.connect_material_expressions(fade_start, "", fade_range, "B")),
    ("fade-ratio-a", editing.connect_material_expressions(depth_minus_start, "", fade_ratio, "A")),
    ("fade-ratio-b", editing.connect_material_expressions(fade_range, "", fade_ratio, "B")),
    ("fade-saturate", editing.connect_material_expressions(fade_ratio, "", fade_saturate, "")),
    ("fade-inverse", editing.connect_material_expressions(fade_saturate, "", fade_inverse, "")),
    ("strength-a", editing.connect_material_expressions(strength, "", effective_strength, "A")),
    ("strength-b", editing.connect_material_expressions(fade_inverse, "", effective_strength, "B")),
    ("flat-normal", editing.connect_material_expressions(flat_normal, "", normal_output, "A")),
    ("animated-normal", editing.connect_material_expressions(normal_normalize, "", normal_output, "B")),
    ("normal-alpha", editing.connect_material_expressions(effective_strength, "", normal_output, "Alpha")),
    ("base-color", editing.connect_material_property(base_color, "", unreal.MaterialProperty.MP_BASE_COLOR)),
    ("roughness", editing.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)),
    ("specular", editing.connect_material_property(specular, "", unreal.MaterialProperty.MP_SPECULAR)),
    ("normal", editing.connect_material_property(normal_output, "", unreal.MaterialProperty.MP_NORMAL)),
]
if IS_LIT_V4:
    connections += [
        ("emissive-a", editing.connect_material_expressions(base_color, "", night_emissive, "A")),
        ("emissive-b", editing.connect_material_expressions(night_fill, "", night_emissive, "B")),
        ("emissive", editing.connect_material_property(night_emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)),
    ]
else:
    connections += [
        ("opacity-mask", editing.connect_material_property(opacity_mask, "", unreal.MaterialProperty.MP_OPACITY_MASK)),
        ("slw-scattering", editing.connect_material_expressions(scattering, "", single_layer, "ScatteringCoefficients")),
        ("slw-absorption", editing.connect_material_expressions(absorption, "", single_layer, "AbsorptionCoefficients")),
        ("slw-phase", editing.connect_material_expressions(phase_g, "", single_layer, "PhaseG")),
        ("slw-behind", editing.connect_material_expressions(behind_water, "", single_layer, "ColorScaleBehindWater")),
    ]
failed = [name for name, connected in connections if not connected]
if failed:
    fail("material graph connections failed: " + ", ".join(failed))

editing.recompile_material(material)
if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
    fail(f"could not save {MATERIAL_PATH}")

instance = asset_tools.create_asset(
    INSTANCE_NAME, ROOT, unreal.MaterialInstanceConstant,
    unreal.MaterialInstanceConstantFactoryNew()
)
if not isinstance(instance, unreal.MaterialInstanceConstant):
    fail(f"could not create {INSTANCE_PATH}")
editing.set_material_instance_parent(instance, material)
editing.set_material_instance_vector_parameter_value(
    instance, "WaterTint", unreal.LinearColor(0.008, 0.12, 0.34, 1.0)
)
editing.set_material_instance_vector_parameter_value(
    instance, "ScatteringCoefficients",
    unreal.LinearColor(0.000003, 0.000020, 0.000050, 1.0)
)
editing.set_material_instance_vector_parameter_value(
    instance, "AbsorptionCoefficients",
    unreal.LinearColor(0.000080, 0.000018, 0.000006, 1.0)
)
editing.set_material_instance_vector_parameter_value(
    instance, "ColorScaleBehindWater", unreal.LinearColor(0.30, 0.68, 1.0, 1.0)
)
for name, value in {
    "WaveTiling1": 4096.0,
    "WaveTiling2": 6144.0,
    "NormalBlend": 0.5,
    "NormalStrength": 0.42,
    "NormalFadeStartCm": 50000.0,
    "NormalFadeEndCm": 250000.0,
    "Roughness": 0.16,
    "Specular": 0.45,
    "PhaseG": 0.72,
    "NightFill": 0.22,
}.items():
    editing.set_material_instance_scalar_parameter_value(instance, name, value)
editing.update_material_instance(instance)
if not unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False):
    fail(f"could not save {INSTANCE_PATH}")

unreal.log_warning(
    f"RED_RADIAL_WATER_T04_{VARIANT}_READY material=" + material.get_path_name()
    + " instance=" + instance.get_path_name()
    + " source_normal=" + NORMAL_TEXTURE_PATH
    + " shading=SingleLayerWater topology=uv0-sphere no-planar-shore-branches"
)
