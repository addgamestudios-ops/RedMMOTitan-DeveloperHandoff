"""Metal-safe M_SpaceStars_Live — no Power node (was Missing Power Base input).

Errors from prior rebuild:
  (Node Power) Missing Power Base input
  Sky materials must be opaque or masked, and unlit.

Fix: TextureSample * SpaceFade * StarBrightness -> Emissive, Additive, not sky.
"""
import unreal

LOG = "/tmp/titan_star_mat_v2.log"


def log(msg):
    print(f"[star_v2] {msg}")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def main():
    open(LOG, "w", encoding="utf-8").write("start\n")
    path = "/Game/RedMMO/Materials/M_SpaceStars_Live"
    mat = unreal.load_asset(path)
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
        ("wireframe", False),
    ):
        try:
            mat.set_editor_property(prop, val)
            log(f"set {prop}={val}")
        except Exception as e:
            log(f"skip {prop}: {e}")

    fade = create(mat, unreal.MaterialExpressionScalarParameter, -700, 0)
    fade.set_editor_property("parameter_name", "SpaceFade")
    fade.set_editor_property("default_value", 0.0)

    bright = create(mat, unreal.MaterialExpressionScalarParameter, -700, 180)
    bright.set_editor_property("parameter_name", "StarBrightness")
    bright.set_editor_property("default_value", 14.0)

    tex = unreal.load_asset("/Engine/EngineSky/T_Sky_Stars")
    if not tex:
        tex = unreal.load_asset("/Engine/MapTemplates/Sky/T_Sky_Stars")
    ts = create(mat, unreal.MaterialExpressionTextureSample, -420, 0)
    if tex:
        ts.set_editor_property("texture", tex)

    # stars * fade  (use RGB out → first mul input via empty pin name)
    mul_fade = create(mat, unreal.MaterialExpressionMultiply, -160, 0)
    connect_expr(ts, "", mul_fade, "A")
    connect_expr(fade, "", mul_fade, "B")

    mul_bright = create(mat, unreal.MaterialExpressionMultiply, 80, 0)
    connect_expr(mul_fade, "", mul_bright, "A")
    connect_expr(bright, "", mul_bright, "B")

    tint = create(mat, unreal.MaterialExpressionConstant3Vector, 80, 180)
    tint.set_editor_property("constant", unreal.LinearColor(1.05, 1.05, 1.15, 1.0))
    mul_rgb = create(mat, unreal.MaterialExpressionMultiply, 280, 0)
    connect_expr(mul_bright, "", mul_rgb, "A")
    connect_expr(tint, "", mul_rgb, "B")

    connect(mul_rgb, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    black = create(mat, unreal.MaterialExpressionConstant3Vector, -700, 360)
    black.set_editor_property("constant", unreal.LinearColor(0.0, 0.0, 0.0, 1.0))
    connect(black, "", unreal.MaterialProperty.MP_BASE_COLOR)

    unreal.MaterialEditingLibrary.recompile_material(mat)
    ok = unreal.EditorAssetLibrary.save_asset(path)
    log(f"saved={ok} path={path}")
    log("DONE ok")


main()
