"""Editor one-shot: star dome mat, white cloud MIC, SoStylized sand tiling.
Run via MCP execute_python_code after editor is up (not during PIE).
"""
import unreal

LOG = "/tmp/titan_stars_clouds_sand_mat.log"


def log(msg):
    print(f"[fix_mats] {msg}")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def fix_star_material():
    """Additive stars with depth test ON (no blizzard-over-hull) and mild contrast."""
    path = "/Game/RedMMO/Materials/M_SpaceStars_Live"
    mat = unreal.load_asset(path)
    if not mat:
        raise RuntimeError("M_SpaceStars_Live missing")

    unreal.MaterialEditingLibrary.delete_all_material_expressions(mat)

    create = unreal.MaterialEditingLibrary.create_material_expression
    connect = unreal.MaterialEditingLibrary.connect_material_property
    connect_expr = unreal.MaterialEditingLibrary.connect_material_expressions

    mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_SURFACE)
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    try:
        mat.set_editor_property("disable_depth_test", False)
    except Exception as e:
        log(f"disable_depth_test warn: {e}")

    fade = create(mat, unreal.MaterialExpressionScalarParameter, -700, 0)
    fade.set_editor_property("parameter_name", "SpaceFade")
    fade.set_editor_property("default_value", 0.0)

    bright = create(mat, unreal.MaterialExpressionScalarParameter, -700, 140)
    bright.set_editor_property("parameter_name", "StarBrightness")
    bright.set_editor_property("default_value", 10.0)

    tex = unreal.load_asset("/Engine/EngineSky/T_Sky_Stars")
    if not tex:
        tex = unreal.load_asset("/Engine/MapTemplates/Sky/T_Sky_Stars")
    ts = create(mat, unreal.MaterialExpressionTextureSample, -400, 0)
    if tex:
        ts.set_editor_property("texture", tex)

    # Mild power keeps sparse stars; power 8 previously crushed them to black.
    powexp = create(mat, unreal.MaterialExpressionPower, -200, 80)
    exp = create(mat, unreal.MaterialExpressionConstant, -200, 160)
    exp.set_editor_property("r", 1.6)
    connect_expr(ts, "R", powexp, "Base")
    connect_expr(exp, "", powexp, "Exp")

    mul_fade = create(mat, unreal.MaterialExpressionMultiply, -50, 0)
    connect_expr(powexp, "", mul_fade, "A")
    connect_expr(fade, "", mul_fade, "B")

    mul_bright = create(mat, unreal.MaterialExpressionMultiply, 120, 0)
    connect_expr(mul_fade, "", mul_bright, "A")
    connect_expr(bright, "", mul_bright, "B")

    mul_rgb = create(mat, unreal.MaterialExpressionMultiply, 300, 0)
    ones = create(mat, unreal.MaterialExpressionConstant3Vector, 300, 140)
    ones.set_editor_property("constant", unreal.LinearColor(1.0, 1.0, 1.05, 1.0))
    connect_expr(mul_bright, "", mul_rgb, "A")
    connect_expr(ones, "", mul_rgb, "B")

    connect(mul_rgb, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    connect(mul_fade, "", unreal.MaterialProperty.MP_OPACITY)

    black = create(mat, unreal.MaterialExpressionConstant3Vector, -700, 300)
    black.set_editor_property("constant", unreal.LinearColor(0.0, 0.0, 0.0, 1.0))
    connect(black, "", unreal.MaterialProperty.MP_BASE_COLOR)

    unreal.MaterialEditingLibrary.recompile_material(mat)
    unreal.EditorAssetLibrary.save_asset(path)
    log(f"star mat ADDITIVE depth-tested StarBrightness=5 @ {path}")


def fix_cloud_mic():
    path = "/Game/RedMMO/Materials/MIC_RedPlanet_Clouds"
    mic = unreal.load_asset(path)
    if not mic:
        src = unreal.load_asset(
            "/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst"
        )
        if not src:
            log("WARN: no cloud MIC source")
            return
        mic = unreal.AssetToolsHelpers.get_asset_tools().duplicate_asset(
            "MIC_RedPlanet_Clouds", "/Game/RedMMO/Materials", src
        )
        log(f"duplicated cloud MIC -> {mic}")

    white = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)
    for name in ("Cloud_AlbedoColor", "Albedo", "AlbedoColor", "Storm_AlbedoColor"):
        try:
            unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(
                mic, name, white
            )
        except Exception:
            pass
    for name, val in (
        ("BrightnessMult", 6.0),
        ("Cloud_GlobalDensity", 0.85),
        ("Cloud_GlobalCoverage", 0.88),
        ("MultiScatteringContribution", 1.0),
        ("MultiScatteringOcclusion", 0.15),
        ("FillScatterIntensity", 1.25),
    ):
        try:
            unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                mic, name, val
            )
        except Exception:
            pass
    unreal.MaterialEditingLibrary.update_material_instance(mic)
    unreal.EditorAssetLibrary.save_asset(path)
    log(f"cloud MIC whitened {path}")


def fix_sand_mi():
    try:
        r = unreal.RedMMOEditorTools.apply_so_stylized_sand_to_planet_biome()
        log(f"sand apply: {r}")
    except Exception as e:
        log(f"sand apply warn: {e}")
    try:
        unreal.RedMMOEditorTools.set_mi_layer_scalar_parameter(
            "/Game/RedMMO/Materials/MI_PlanetBiome_RED.MI_PlanetBiome_RED",
            "3",
            "CloseRangeTiling",
            6.0,
        )
        unreal.RedMMOEditorTools.set_mi_layer_scalar_parameter(
            "/Game/RedMMO/Materials/MI_PlanetBiome_RED.MI_PlanetBiome_RED",
            "3",
            "FarRangeTiling",
            6.0,
        )
        log("sand tiling Layer[3] -> Close=6 Far=6 (So Stylized demo-scale correction)")
    except Exception as e:
        log(f"sand tiling warn: {e}")
    unreal.EditorAssetLibrary.save_asset("/Game/RedMMO/Materials/MI_PlanetBiome_RED")


def main():
    open(LOG, "w", encoding="utf-8").write("start\n")
    fix_star_material()
    fix_cloud_mic()
    fix_sand_mi()
    log("DONE ok")


main()
