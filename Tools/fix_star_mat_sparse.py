"""Rebuild M_SpaceStars_Live as sparse additive stars (Metal-safe, no Power).

T_Sky_Stars is dense noise — multiplying it by brightness makes a white blizzard
that also reads as grey grain when partially faded. Threshold so only bright
texels survive, then apply a modest StarBrightness.
"""
import unreal

LOG = "/tmp/titan_star_mat_sparse.log"
PATH = "/Game/RedMMO/Materials/M_SpaceStars_Live"


def log(msg):
    print(f"[star_sparse] {msg}")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def main():
    open(LOG, "w", encoding="utf-8").write("start\n")
    mat = unreal.load_asset(PATH)
    if not mat:
        raise RuntimeError("missing M_SpaceStars_Live")

    unreal.MaterialEditingLibrary.delete_all_material_expressions(mat)

    create = unreal.MaterialEditingLibrary.create_material_expression
    connect = unreal.MaterialEditingLibrary.connect_material_property
    connect_expr = unreal.MaterialEditingLibrary.connect_material_expressions

    mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_SURFACE)
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    for prop, val in (
        ("disable_depth_test", False),
        ("is_sky", False),
        ("b_is_sky", False),
        ("used_with_sky_atmosphere", False),
        ("allow_negative_emissive_color", True),
    ):
        try:
            mat.set_editor_property(prop, val)
        except Exception as e:
            log(f"skip {prop}: {e}")

    fade = create(mat, unreal.MaterialExpressionScalarParameter, -900, 0)
    fade.set_editor_property("parameter_name", "SpaceFade")
    fade.set_editor_property("default_value", 0.0)

    bright = create(mat, unreal.MaterialExpressionScalarParameter, -900, 160)
    bright.set_editor_property("parameter_name", "StarBrightness")
    bright.set_editor_property("default_value", 4.0)

    thresh = create(mat, unreal.MaterialExpressionScalarParameter, -900, 320)
    thresh.set_editor_property("parameter_name", "StarThreshold")
    thresh.set_editor_property("default_value", 0.82)

    tex = unreal.load_asset("/Engine/EngineSky/T_Sky_Stars")
    if not tex:
        tex = unreal.load_asset("/Engine/MapTemplates/Sky/T_Sky_Stars")
    ts = create(mat, unreal.MaterialExpressionTextureSample, -620, 0)
    if tex:
        ts.set_editor_property("texture", tex)

    # Keep only bright texels: saturate(tex - threshold)
    sub = create(mat, unreal.MaterialExpressionSubtract, -360, 0)
    connect_expr(ts, "", sub, "A")
    connect_expr(thresh, "", sub, "B")

    sat = create(mat, unreal.MaterialExpressionSaturate, -200, 0)
    connect_expr(sub, "", sat, "")

    # Remap remaining range so survivors are punchy: sat / (1 - threshold) ≈ sat * 5.5
    one = create(mat, unreal.MaterialExpressionConstant, -900, 480)
    one.set_editor_property("r", 1.0)
    denom = create(mat, unreal.MaterialExpressionSubtract, -620, 320)
    connect_expr(one, "", denom, "A")
    connect_expr(thresh, "", denom, "B")
    # Avoid div-by-zero with max(denom, 0.05)
    min_d = create(mat, unreal.MaterialExpressionConstant, -620, 480)
    min_d.set_editor_property("r", 0.05)
    safe_d = create(mat, unreal.MaterialExpressionMax, -420, 320)
    connect_expr(denom, "", safe_d, "A")
    connect_expr(min_d, "", safe_d, "B")

    div = create(mat, unreal.MaterialExpressionDivide, -40, 0)
    connect_expr(sat, "", div, "A")
    connect_expr(safe_d, "", div, "B")

    mul_fade = create(mat, unreal.MaterialExpressionMultiply, 140, 0)
    connect_expr(div, "", mul_fade, "A")
    connect_expr(fade, "", mul_fade, "B")

    mul_bright = create(mat, unreal.MaterialExpressionMultiply, 320, 0)
    connect_expr(mul_fade, "", mul_bright, "A")
    connect_expr(bright, "", mul_bright, "B")

    tint = create(mat, unreal.MaterialExpressionConstant3Vector, 320, 180)
    tint.set_editor_property("constant", unreal.LinearColor(1.0, 1.02, 1.12, 1.0))
    mul_rgb = create(mat, unreal.MaterialExpressionMultiply, 500, 0)
    connect_expr(mul_bright, "", mul_rgb, "A")
    connect_expr(tint, "", mul_rgb, "B")

    connect(mul_rgb, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    black = create(mat, unreal.MaterialExpressionConstant3Vector, -900, 600)
    black.set_editor_property("constant", unreal.LinearColor(0.0, 0.0, 0.0, 1.0))
    connect(black, "", unreal.MaterialProperty.MP_BASE_COLOR)

    unreal.MaterialEditingLibrary.recompile_material(mat)
    ok = unreal.EditorAssetLibrary.save_asset(PATH)
    log(f"saved={ok}")
    log("DONE ok")


main()
