import unreal


ASSET_PATH = "/Game/RedMMO/Environment/M_RedAnalyticStarDomeCubeUV_V2"
PACKAGE_PATH = "/Game/RedMMO/Environment"
ASSET_NAME = "M_RedAnalyticStarDomeCubeUV_V2"


CUSTOM_CODE = r"""
float longitude = (SphereUV.x * 2.0 - 1.0) * 3.14159265359;
float latitude = (0.5 - saturate(SphereUV.y)) * 3.14159265359;
float cosLat = cos(latitude);
float3 d = float3(
    cosLat * cos(longitude),
    cosLat * sin(longitude),
    sin(latitude));

float3 ad = max(abs(d), float3(0.00001, 0.00001, 0.00001));
float2 q;
float face;

if (ad.x >= ad.y && ad.x >= ad.z)
{
    if (d.x >= 0.0) { face = 0.0; q = float2( d.y, d.z) / ad.x; }
    else            { face = 1.0; q = float2(-d.y, d.z) / ad.x; }
}
else if (ad.y >= ad.z)
{
    if (d.y >= 0.0) { face = 2.0; q = float2(-d.x, d.z) / ad.y; }
    else            { face = 3.0; q = float2( d.x, d.z) / ad.y; }
}
else
{
    if (d.z >= 0.0) { face = 4.0; q = float2(d.x,  d.y) / ad.z; }
    else            { face = 5.0; q = float2(d.x, -d.y) / ad.z; }
}

float cells = max(floor(CellScale + 0.5), 1.0);
float2 faceUV = saturate(q * 0.5 + 0.5);
float2 p = min(faceUV, float2(0.999999, 0.999999)) * cells;
float2 cell = floor(p);
float2 f = frac(p);

float4 phase = float4(
    dot(cell, float2(127.1,   311.7)),
    dot(cell, float2(269.5,   183.3)),
    dot(cell, float2(419.2,   371.9)),
    dot(cell, float2(12.9898, 78.233)));

phase += face * float4(74.7, 53.3, 91.9, 37.1)
       + Seed * float4(19.19, 7.13, 3.71, 11.17);

float4 h = frac(sin(phase) * float4(
    43758.5453, 22578.1459, 19642.3490, 31821.5319));

float2 cellQ = ((cell + 0.5) / cells) * 2.0 - 1.0;
float inv = rsqrt(1.0 + dot(cellQ, cellQ));
float densityHere = saturate(Density * inv * inv * inv);
float present = step(1.0 - densityHere, h.x);

float2 center = lerp(float2(0.20, 0.20), float2(0.80, 0.80), h.yz);
float bright = pow(h.w, 10.0);
float radius = max(PointRadius, 0.01) * lerp(1.0, 2.1, bright);
float dist = length(f - center);
float aa = clamp(0.5 * fwidth(dist), 0.005, 0.10);
float star = present * (1.0 - smoothstep(radius, radius + aa, dist));

float3 color = lerp(
    float3(0.62, 0.78, 1.00),
    float3(1.00, 0.90, 0.72),
    h.z);
float magnitude = lerp(0.55, 3.50, bright);

return color * star * magnitude
    * max(Visibility, 0.0)
    * max(Emission, 0.0);
"""


def build_new_material():
    if unreal.EditorAssetLibrary.does_asset_exist(ASSET_PATH):
        raise RuntimeError(f"Refusing to overwrite existing diagnostic asset: {ASSET_PATH}")

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
    material.set_editor_property("is_sky", True)

    editing = unreal.MaterialEditingLibrary
    sphere_uv = editing.create_material_expression(
        material, unreal.MaterialExpressionTextureCoordinate, -700, -250
    )

    defaults = [
        ("CellScale", 160.0),
        ("Density", 0.23),
        ("PointRadius", 0.13),
        ("Seed", 17.0),
        ("Visibility", 1.0),
        ("Emission", 64.0),
    ]
    scalar_nodes = {}
    for index, (name, value) in enumerate(defaults):
        node = editing.create_material_expression(
            material,
            unreal.MaterialExpressionScalarParameter,
            -700,
            -110 + index * 105,
        )
        node.set_editor_property("parameter_name", name)
        node.set_editor_property("default_value", value)
        scalar_nodes[name] = node

    custom = editing.create_material_expression(
        material, unreal.MaterialExpressionCustom, -260, 0
    )
    custom.set_editor_property(
        "description", "Single-face UV-derived deterministic RED star dome V2"
    )
    custom.set_editor_property("code", CUSTOM_CODE)
    custom.set_editor_property(
        "output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3
    )
    input_names = ["SphereUV"] + [name for name, _ in defaults]
    custom_inputs = []
    for name in input_names:
        custom_input = unreal.CustomInput()
        custom_input.set_editor_property("input_name", name)
        custom_inputs.append(custom_input)
    custom.set_editor_property("inputs", custom_inputs)

    if not editing.connect_material_expressions(sphere_uv, "", custom, "SphereUV"):
        raise RuntimeError("Failed to connect Engine Sphere UV0")
    for name, node in scalar_nodes.items():
        if not editing.connect_material_expressions(node, "", custom, name):
            raise RuntimeError(f"Failed to connect {name}")
    if not editing.connect_material_property(
        custom, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    ):
        raise RuntimeError("Failed to connect CubeUV V2 emissive output")

    editing.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise RuntimeError(f"Failed to save {ASSET_PATH}")
    return material


result = build_new_material()
unreal.log_warning(
    "RED_ANALYTIC_CUBE_UV_V2_STAR_DOME_READY "
    + result.get_path_name()
    + " blend="
    + str(result.get_editor_property("blend_mode"))
    + " two_sided="
    + str(result.get_editor_property("two_sided"))
    + " is_sky="
    + str(result.get_editor_property("is_sky"))
)
