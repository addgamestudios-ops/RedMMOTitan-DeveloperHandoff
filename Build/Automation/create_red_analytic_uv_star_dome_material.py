import unreal


ASSET_PATH = "/Game/RedMMO/Environment/M_RedAnalyticStarDomeUV"
PACKAGE_PATH = "/Game/RedMMO/Environment"
ASSET_NAME = "M_RedAnalyticStarDomeUV"


CUSTOM_CODE = r"""
struct FRedUvStarEval
{
    float4 Hash42(float2 p, float face, float seed)
    {
        float4 q = frac(float4(p.x, p.y, face, seed)
            * float4(0.1031, 0.1030, 0.0973, 0.1099));
        q += dot(q, q.wzxy + 33.33);
        return frac((q.xxyz + q.yzzw) * q.zywx);
    }

    float3 Layer(float2 uv, float face, float cellScale, float density,
        float baseRadius, float seed)
    {
        float2 p = uv * cellScale;
        float2 cell = floor(p);
        float2 local = frac(p);
        float4 h = Hash42(cell, face, seed);
        float present = step(1.0 - saturate(density), h.x);
        float2 center = lerp(float2(0.16, 0.16), float2(0.84, 0.84), h.yz);
        float tier = pow(h.w, 16.0);
        float radius = baseRadius * lerp(0.72, 2.45, tier);
        float distanceToStar = length(local - center);
        float aa = max(fwidth(distanceToStar) * 1.35, 0.002);
        float core = present
            * (1.0 - smoothstep(radius, radius + aa, distanceToStar));
        float halo = present * tier * 0.12
            * (1.0 - smoothstep(radius * 1.8, radius * 5.0 + aa, distanceToStar));
        float temp = frac(h.w * 7.13 + h.x * 3.71);
        float3 cool = float3(0.58, 0.75, 1.00);
        float3 neutral = float3(1.00, 0.98, 0.92);
        float3 warm = float3(1.00, 0.78, 0.54);
        float3 color = temp < 0.55
            ? lerp(cool, neutral, temp / 0.55)
            : lerp(neutral, warm, (temp - 0.55) / 0.45);
        return color * (core * lerp(0.72, 4.20, tier) + halo);
    }
};

// The Engine Sphere UV is a reliable static-mesh vertex-factory input. Reconstruct a
// continuous spherical direction from it, then use seam-soft tri-planar star layers.
// This removes the CameraVector expression that evaluated black in the V4J real-GPU view.
float longitude = (SphereUV.x * 2.0 - 1.0) * 3.14159265359;
float latitude = (0.5 - SphereUV.y) * 3.14159265359;
float cosLatitude = cos(latitude);
float3 d = normalize(float3(
    cosLatitude * cos(longitude),
    cosLatitude * sin(longitude),
    sin(latitude)));
float3 ad = abs(d);
float3 w = pow(ad, 12.0);
w /= max(w.x + w.y + w.z, 0.0001);
float2 uvX = d.yz / max(ad.x, 0.05);
float2 uvY = d.xz / max(ad.y, 0.05);
float2 uvZ = d.xy / max(ad.z, 0.05);

FRedUvStarEval S;
float3 sx = S.Layer(uvX, d.x >= 0.0 ? 11.0 : 17.0,
    CellScale, Density, PointRadius, Seed);
float3 sy = S.Layer(uvY, d.y >= 0.0 ? 23.0 : 29.0,
    CellScale, Density, PointRadius, Seed);
float3 sz = S.Layer(uvZ, d.z >= 0.0 ? 31.0 : 37.0,
    CellScale, Density, PointRadius, Seed);
return (sx * w.x + sy * w.y + sz * w.z)
    * max(Visibility, 0.0) * max(Emission, 0.0);
"""


def build_new_material():
    existing = unreal.EditorAssetLibrary.load_asset(ASSET_PATH)
    if existing is not None:
        if not isinstance(existing, unreal.Material):
            raise RuntimeError(f"{ASSET_PATH} exists but is not a Material")
        unreal.log_warning("RED_ANALYTIC_UV_STAR_DOME_EXISTS " + existing.get_path_name())
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
    material.set_editor_property("is_sky", True)

    editing = unreal.MaterialEditingLibrary
    sphere_uv = editing.create_material_expression(
        material, unreal.MaterialExpressionTextureCoordinate, -700, -250
    )

    defaults = [
        ("CellScale", 72.0),
        ("Density", 0.080),
        ("PointRadius", 0.110),
        ("Seed", 17.0),
        ("Visibility", 0.0),
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
        "description", "Texture-free UV-derived deterministic RED star dome"
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
        raise RuntimeError("Failed to connect Engine Sphere UV")
    for name, node in scalar_nodes.items():
        if not editing.connect_material_expressions(node, "", custom, name):
            raise RuntimeError(f"Failed to connect {name}")
    if not editing.connect_material_property(
        custom, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    ):
        raise RuntimeError("Failed to connect analytic UV emissive output")

    editing.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise RuntimeError(f"Failed to save {ASSET_PATH}")
    return material


result = build_new_material()
unreal.log_warning(
    "RED_ANALYTIC_UV_STAR_DOME_READY "
    + result.get_path_name()
    + " blend="
    + str(result.get_editor_property("blend_mode"))
    + " two_sided="
    + str(result.get_editor_property("two_sided"))
    + " is_sky="
    + str(result.get_editor_property("is_sky"))
)
