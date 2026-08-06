"""Rebuild M_SpaceStars_Live as a Metal-SM6-safe additive unlit material.

Prior graph failed to compile on SF_METAL_SM6 (Default Material substituted → invisible stars).
Keep it minimal: TextureSample * Power * SpaceFade * StarBrightness → Emissive only.
No Opacity pin on Additive (Metal compile hazard).
"""
import unreal

LOG = "/tmp/titan_star_mat_metal.log"


def log(msg):
    print(f"[star_metal] {msg}")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def main():
    open(LOG, "w", encoding="utf-8").write("start\n")
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
    # Depth test ON so stars don't paint over the ship hull.
    try:
        mat.set_editor_property("disable_depth_test", False)
    except Exception as e:
        log(f"disable_depth_test warn: {e}")
    try:
        mat.set_editor_property("allow_negative_emissive_color", True)
    except Exception:
        pass

    fade = create(mat, unreal.MaterialExpressionScalarParameter, -800, 0)
    fade.set_editor_property("parameter_name", "SpaceFade")
    fade.set_editor_property("default_value", 0.0)

    bright = create(mat, unreal.MaterialExpressionScalarParameter, -800, 160)
    bright.set_editor_property("parameter_name", "StarBrightness")
    bright.set_editor_property("default_value", 12.0)

    tex = unreal.load_asset("/Engine/EngineSky/T_Sky_Stars")
    if not tex:
        tex = unreal.load_asset("/Engine/MapTemplates/Sky/T_Sky_Stars")
    ts = create(mat, unreal.MaterialExpressionTextureSample, -500, 0)
    if tex:
        ts.set_editor_property("texture", tex)
        try:
            ts.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        except Exception:
            pass

    # Mild contrast — power 2.5 previously crushed sparse stars; keep Metal-simple.
    powexp = create(mat, unreal.MaterialExpressionPower, -280, 40)
    exp = create(mat, unreal.MaterialExpressionConstant, -280, 160)
    exp.set_editor_property("r", 1.5)
    connect_expr(ts, "R", powexp, "Base")
    connect_expr(exp, "", powexp, "Exp")

    mul_fade = create(mat, unreal.MaterialExpressionMultiply, -80, 0)
    connect_expr(powexp, "", mul_fade, "A")
    connect_expr(fade, "", mul_fade, "B")

    mul_bright = create(mat, unreal.MaterialExpressionMultiply, 120, 0)
    connect_expr(mul_fade, "", mul_bright, "A")
    connect_expr(bright, "", mul_bright, "B")

    # RGB tint slightly cool-white
    mul_rgb = create(mat, unreal.MaterialExpressionMultiply, 320, 0)
    tint = create(mat, unreal.MaterialExpressionConstant3Vector, 320, 160)
    tint.set_editor_property("constant", unreal.LinearColor(1.0, 1.0, 1.08, 1.0))
    connect_expr(mul_bright, "", mul_rgb, "A")
    connect_expr(tint, "", mul_rgb, "B")

    # Emissive ONLY — do NOT wire Opacity on Additive (Metal SM6 compile fail).
    connect(mul_rgb, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    black = create(mat, unreal.MaterialExpressionConstant3Vector, -800, 320)
    black.set_editor_property("constant", unreal.LinearColor(0.0, 0.0, 0.0, 1.0))
    connect(black, "", unreal.MaterialProperty.MP_BASE_COLOR)

    unreal.MaterialEditingLibrary.recompile_material(mat)
    unreal.EditorAssetLibrary.save_asset(path)
    log(f"rebuilt Metal-safe additive emissive-only @ {path}")

    # Also push white cloud MIC params (runtime MID overrides these too).
    mic_path = "/Game/RedMMO/Materials/MIC_RedPlanet_Clouds"
    mic = unreal.load_asset(mic_path)
    if mic:
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
            ("MultiScatteringOcclusion", 0.12),
            ("FillScatterIntensity", 1.75),
        ):
            try:
                unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                    mic, name, val
                )
            except Exception:
                pass
        unreal.MaterialEditingLibrary.update_material_instance(mic)
        unreal.EditorAssetLibrary.save_asset(mic_path)
        log(f"cloud MIC whitened {mic_path}")
    else:
        log("WARN: MIC_RedPlanet_Clouds missing")

    log("DONE ok")


main()
