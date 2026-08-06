"""Create the V2 project-owned radial water material for NightWater_T04.

The purchased So Stylized assets remain read-only inputs.  The flat demo master
uses distance-field/planar edge branches that become a flashing white shell on
PlanetGen's spherical ocean.  This small test master reuses the pack's authored
dual water-normal textures and UV animation while keeping the graph independent from
mesh distance fields, scene depth, planar world axes, and the demo day-cycle MPC.

V2 adds explicit normal strength plus a camera-distance fade.  That keeps the
near-shore animation readable while preventing the first proof's 8,192-repeat
normal from filtering into flat water nearby and sparkling at grazing distance.

The script creates new assets only.  It deliberately refuses to rebuild an
existing material because deleting expressions from an already loaded UE 5.8
material has previously tripped an editor assertion in this project.
"""

import unreal


ROOT = "/Game/RedMMO/Environment/Tests"
MATERIAL_NAME = "M_RedRadialWater_T04_V2"
INSTANCE_NAME = "MI_RedRadialWater_Night_T04_V2"
MATERIAL_PATH = f"{ROOT}/{MATERIAL_NAME}"
INSTANCE_PATH = f"{ROOT}/{INSTANCE_NAME}"
NORMAL_TEXTURE_1_PATH = (
    "/Game/StylizedDesertOasis/Materials/MasterMaterials/UtilTextures/T_Water_01_N"
)
NORMAL_TEXTURE_2_PATH = (
    "/Game/StylizedDesertOasis/Materials/MasterMaterials/UtilTextures/T_Water_02_N"
)


def fail(message: str) -> None:
    unreal.log_error("RED_RADIAL_WATER_T04_FAILED " + message)
    raise RuntimeError(message)


def create_parameter(editing, material, expression_class, name, default, x, y):
    expression = editing.create_material_expression(material, expression_class, x, y)
    if not expression:
        fail(f"could not create parameter {name}")
    expression.set_editor_property("parameter_name", name)
    expression.set_editor_property("default_value", default)
    return expression


if unreal.EditorAssetLibrary.does_asset_exist(MATERIAL_PATH):
    fail(
        f"{MATERIAL_PATH} already exists; refusing an in-place graph rebuild. "
        "Use a new test suffix for another experiment."
    )
if unreal.EditorAssetLibrary.does_asset_exist(INSTANCE_PATH):
    fail(
        f"{INSTANCE_PATH} already exists without its expected new master; "
        "refusing to overwrite it."
    )

normal_texture_1 = unreal.EditorAssetLibrary.load_asset(NORMAL_TEXTURE_1_PATH)
normal_texture_2 = unreal.EditorAssetLibrary.load_asset(NORMAL_TEXTURE_2_PATH)
if not isinstance(normal_texture_1, unreal.Texture2D):
    fail(f"missing purchased Stylized Desert Oasis Texture2D {NORMAL_TEXTURE_1_PATH}")
if not isinstance(normal_texture_2, unreal.Texture2D):
    fail(f"missing purchased Stylized Desert Oasis Texture2D {NORMAL_TEXTURE_2_PATH}")

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
material = asset_tools.create_asset(
    MATERIAL_NAME,
    ROOT,
    unreal.Material,
    unreal.MaterialFactoryNew(),
)
if not isinstance(material, unreal.Material):
    fail(f"could not create {MATERIAL_PATH}")

material.set_editor_property("material_domain", unreal.MaterialDomain.MD_SURFACE)
material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
material.set_editor_property("two_sided", False)
material.set_editor_property("tangent_space_normal", True)
try:
    material.set_editor_property(
        "translucency_lighting_mode",
        unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING,
    )
except Exception as exc:
    # The enum/property name has changed across UE minors.  The default
    # translucency path is still a valid diagnostic, so keep asset creation
    # deterministic and report the fallback explicitly.
    unreal.log_warning("RED_RADIAL_WATER_T04 translucency lighting fallback: " + str(exc))

editing = unreal.MaterialEditingLibrary

uv = editing.create_material_expression(
    material, unreal.MaterialExpressionTextureCoordinate, -1500, -260
)
tiling_1 = create_parameter(
    editing,
    material,
    unreal.MaterialExpressionScalarParameter,
    "WaveTiling1",
    4096.0,
    -1500,
    -80,
)
tiling_2 = create_parameter(
    editing,
    material,
    unreal.MaterialExpressionScalarParameter,
    "WaveTiling2",
    6144.0,
    -1500,
    80,
)
scaled_uv_1 = editing.create_material_expression(
    material, unreal.MaterialExpressionMultiply, -1260, -300
)
scaled_uv_2 = editing.create_material_expression(
    material, unreal.MaterialExpressionMultiply, -1260, -80
)
panner_1 = editing.create_material_expression(
    material, unreal.MaterialExpressionPanner, -1030, -300
)
panner_1.set_editor_property("speed_x", 0.014)
panner_1.set_editor_property("speed_y", -0.009)
panner_2 = editing.create_material_expression(
    material, unreal.MaterialExpressionPanner, -1030, -80
)
panner_2.set_editor_property("speed_x", -0.010)
panner_2.set_editor_property("speed_y", 0.012)

normal_sample_1 = editing.create_material_expression(
    material, unreal.MaterialExpressionTextureSampleParameter2D, -800, -300
)
normal_sample_1.set_editor_property("parameter_name", "OasisWaterNormal1")
normal_sample_1.set_editor_property("texture", normal_texture_1)
normal_sample_1.set_editor_property(
    "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL
)
normal_sample_2 = editing.create_material_expression(
    material, unreal.MaterialExpressionTextureSampleParameter2D, -800, -80
)
normal_sample_2.set_editor_property("parameter_name", "OasisWaterNormal2")
normal_sample_2.set_editor_property("texture", normal_texture_2)
normal_sample_2.set_editor_property(
    "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL
)
normal_blend_amount = create_parameter(
    editing,
    material,
    unreal.MaterialExpressionScalarParameter,
    "NormalBlend",
    0.5,
    -800,
    120,
)
normal_blend = editing.create_material_expression(
    material, unreal.MaterialExpressionLinearInterpolate, -540, -180
)

normal_strength = create_parameter(
    editing,
    material,
    unreal.MaterialExpressionScalarParameter,
    "NormalStrength",
    0.38,
    -800,
    300,
)
fade_start = create_parameter(
    editing,
    material,
    unreal.MaterialExpressionScalarParameter,
    "NormalFadeStartCm",
    15000.0,
    -1500,
    300,
)
fade_end = create_parameter(
    editing,
    material,
    unreal.MaterialExpressionScalarParameter,
    "NormalFadeEndCm",
    150000.0,
    -1500,
    440,
)
pixel_depth = editing.create_material_expression(
    material, unreal.MaterialExpressionPixelDepth, -1500, 580
)
depth_minus_start = editing.create_material_expression(
    material, unreal.MaterialExpressionSubtract, -1240, 420
)
fade_range = editing.create_material_expression(
    material, unreal.MaterialExpressionSubtract, -1240, 600
)
fade_ratio = editing.create_material_expression(
    material, unreal.MaterialExpressionDivide, -1010, 500
)
fade_saturate = editing.create_material_expression(
    material, unreal.MaterialExpressionSaturate, -800, 500
)
fade_inverse = editing.create_material_expression(
    material, unreal.MaterialExpressionOneMinus, -620, 500
)
effective_strength = editing.create_material_expression(
    material, unreal.MaterialExpressionMultiply, -430, 420
)
flat_normal = create_parameter(
    editing,
    material,
    unreal.MaterialExpressionVectorParameter,
    "FlatNormal",
    unreal.LinearColor(0.0, 0.0, 1.0, 1.0),
    -430,
    240,
)
normal_output = editing.create_material_expression(
    material, unreal.MaterialExpressionLinearInterpolate, -180, -60
)

base_color = create_parameter(
    editing,
    material,
    unreal.MaterialExpressionVectorParameter,
    "WaterTint",
    unreal.LinearColor(0.012, 0.105, 0.34, 1.0),
    -180,
    180,
)
roughness = create_parameter(
    editing,
    material,
    unreal.MaterialExpressionScalarParameter,
    "Roughness",
    0.28,
    -180,
    300,
)
specular = create_parameter(
    editing,
    material,
    unreal.MaterialExpressionScalarParameter,
    "Specular",
    0.34,
    -180,
    420,
)
opacity = create_parameter(
    editing,
    material,
    unreal.MaterialExpressionScalarParameter,
    "Opacity",
    0.88,
    -180,
    540,
)

connections = [
    ("uv-to-scale-1", editing.connect_material_expressions(uv, "", scaled_uv_1, "A")),
    ("tiling-1-to-scale", editing.connect_material_expressions(tiling_1, "", scaled_uv_1, "B")),
    ("uv-to-scale-2", editing.connect_material_expressions(uv, "", scaled_uv_2, "A")),
    ("tiling-2-to-scale", editing.connect_material_expressions(tiling_2, "", scaled_uv_2, "B")),
    ("scaled-uv-1-to-panner", editing.connect_material_expressions(scaled_uv_1, "", panner_1, "Coordinate")),
    ("scaled-uv-2-to-panner", editing.connect_material_expressions(scaled_uv_2, "", panner_2, "Coordinate")),
    ("panner-1-to-normal", editing.connect_material_expressions(panner_1, "", normal_sample_1, "UVs")),
    ("panner-2-to-normal", editing.connect_material_expressions(panner_2, "", normal_sample_2, "UVs")),
    ("normal-1-to-blend", editing.connect_material_expressions(normal_sample_1, "RGB", normal_blend, "A")),
    ("normal-2-to-blend", editing.connect_material_expressions(normal_sample_2, "RGB", normal_blend, "B")),
    ("normal-blend-alpha", editing.connect_material_expressions(normal_blend_amount, "", normal_blend, "Alpha")),
    ("depth-minus-start-a", editing.connect_material_expressions(pixel_depth, "", depth_minus_start, "A")),
    ("depth-minus-start-b", editing.connect_material_expressions(fade_start, "", depth_minus_start, "B")),
    ("fade-range-a", editing.connect_material_expressions(fade_end, "", fade_range, "A")),
    ("fade-range-b", editing.connect_material_expressions(fade_start, "", fade_range, "B")),
    ("fade-ratio-a", editing.connect_material_expressions(depth_minus_start, "", fade_ratio, "A")),
    ("fade-ratio-b", editing.connect_material_expressions(fade_range, "", fade_ratio, "B")),
    ("fade-ratio-saturate", editing.connect_material_expressions(fade_ratio, "", fade_saturate, "")),
    ("fade-saturate-invert", editing.connect_material_expressions(fade_saturate, "", fade_inverse, "")),
    ("strength-times-fade-a", editing.connect_material_expressions(normal_strength, "", effective_strength, "A")),
    ("strength-times-fade-b", editing.connect_material_expressions(fade_inverse, "", effective_strength, "B")),
    ("flat-normal", editing.connect_material_expressions(flat_normal, "", normal_output, "A")),
    ("blended-normal", editing.connect_material_expressions(normal_blend, "", normal_output, "B")),
    ("normal-strength", editing.connect_material_expressions(effective_strength, "", normal_output, "Alpha")),
    ("base-color", editing.connect_material_property(base_color, "", unreal.MaterialProperty.MP_BASE_COLOR)),
    ("roughness", editing.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)),
    ("specular", editing.connect_material_property(specular, "", unreal.MaterialProperty.MP_SPECULAR)),
    ("opacity", editing.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY)),
    ("normal", editing.connect_material_property(normal_output, "", unreal.MaterialProperty.MP_NORMAL)),
]
failed = [name for name, connected in connections if not connected]
if failed:
    fail("material graph connections failed: " + ", ".join(failed))

editing.recompile_material(material)
if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
    fail(f"could not save {MATERIAL_PATH}")

instance = asset_tools.create_asset(
    INSTANCE_NAME,
    ROOT,
    unreal.MaterialInstanceConstant,
    unreal.MaterialInstanceConstantFactoryNew(),
)
if not isinstance(instance, unreal.MaterialInstanceConstant):
    fail(f"could not create {INSTANCE_PATH}")
editing.set_material_instance_parent(instance, material)
editing.set_material_instance_vector_parameter_value(
    instance, "WaterTint", unreal.LinearColor(0.012, 0.105, 0.34, 1.0)
)
for name, value in {
    "WaveTiling1": 4096.0,
    "WaveTiling2": 6144.0,
    "NormalBlend": 0.5,
    "NormalStrength": 0.38,
    "NormalFadeStartCm": 15000.0,
    "NormalFadeEndCm": 150000.0,
    "Roughness": 0.28,
    "Specular": 0.34,
    "Opacity": 0.88,
}.items():
    editing.set_material_instance_scalar_parameter_value(instance, name, value)
editing.update_material_instance(instance)
if not unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False):
    fail(f"could not save {INSTANCE_PATH}")

unreal.log_warning(
    "RED_RADIAL_WATER_T04_READY material="
    + material.get_path_name()
    + " instance="
    + instance.get_path_name()
    + " normals="
    + NORMAL_TEXTURE_1_PATH
    + ","
    + NORMAL_TEXTURE_2_PATH
    + " topology=uv0-sphere dual-panner distance-fade no-distance-fields no-scene-depth no-day-cycle-mpc"
)
