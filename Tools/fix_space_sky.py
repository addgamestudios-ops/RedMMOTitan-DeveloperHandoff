"""
One-shot map fix for thin atmosphere + black space with stars.
Run with: UnrealEditor Titan.uproject /Game/RedMMO/Maps/RedPlanetGen -ExecutePythonScript=.../fix_space_sky.py
"""
import unreal

DONE_FLAG = "/tmp/titan_space_sky_fix.done"
LOG_PATH = "/tmp/titan_space_sky_fix.log"


def log(msg: str) -> None:
    line = str(msg)
    print(f"[fix_space_sky] {line}")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_editor_world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def ensure_star_material():
    """Create /Game/RedMMO/Materials/M_SpaceStars_Live using Engine T_Sky_Stars (no missing UDS dep)."""
    dest = "/Game/RedMMO/Materials/M_SpaceStars_Live"
    existing = unreal.load_asset(dest)
    if existing:
        log(f"star mat exists: {dest}")
        return existing

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.MaterialFactoryNew()
    mat = asset_tools.create_asset("M_SpaceStars_Live", "/Game/RedMMO/Materials", unreal.Material, factory)
    if not mat:
        raise RuntimeError("failed to create M_SpaceStars_Live")

    mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_SURFACE)
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)

    # Procedural-ish: Sample engine star texture in world-aligned spherical UVs via expressions.
    # Keep it simple: constant near-black base + white sparks from texture luminance * SpaceFade.
    tex = unreal.load_asset("/Engine/EngineSky/T_Sky_Stars")
    if not tex:
        tex = unreal.load_asset("/Engine/MapTemplates/Sky/T_Sky_Stars")

    create = unreal.MaterialEditingLibrary.create_material_expression
    connect = unreal.MaterialEditingLibrary.connect_material_property
    connect_expr = unreal.MaterialEditingLibrary.connect_material_expressions

    # SpaceFade scalar parameter (driven by RedPlayerCharacter UpdateSkyFade)
    fade = create(mat, unreal.MaterialExpressionScalarParameter, -600, 0)
    fade.set_editor_property("parameter_name", "SpaceFade")
    fade.set_editor_property("default_value", 0.0)

    # Constant black for emissive base when fade=0 (invisible)
    black = create(mat, unreal.MaterialExpressionConstant3Vector, -600, 200)
    black.set_editor_property("constant", unreal.LinearColor(0.0, 0.0, 0.0, 1.0))

    # Texture sample of stars
    ts = create(mat, unreal.MaterialExpressionTextureSample, -300, 0)
    if tex:
        ts.set_editor_property("texture", tex)

    # Multiply stars * SpaceFade for opacity / emissive
    mul = create(mat, unreal.MaterialExpressionMultiply, -50, 0)
    connect_expr(ts, "R", mul, "A")
    connect_expr(fade, "", mul, "B")

    # Boost brightness
    mul2 = create(mat, unreal.MaterialExpressionMultiply, 100, 0)
    boost = create(mat, unreal.MaterialExpressionConstant, 100, 120)
    boost.set_editor_property("r", 8.0)
    connect_expr(mul, "", mul2, "A")
    connect_expr(boost, "", mul2, "B")

    # Emissive = stars * fade * boost
    mul3 = create(mat, unreal.MaterialExpressionMultiply, 300, 0)
    ones = create(mat, unreal.MaterialExpressionConstant3Vector, 300, 150)
    ones.set_editor_property("constant", unreal.LinearColor(1.0, 1.0, 1.1, 1.0))
    connect_expr(mul2, "", mul3, "A")
    connect_expr(ones, "", mul3, "B")

    connect(mul3, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    connect(mul, "", unreal.MaterialProperty.MP_OPACITY)
    # Near-black base color
    connect(black, "", unreal.MaterialProperty.MP_BASE_COLOR)

    unreal.MaterialEditingLibrary.recompile_material(mat)
    unreal.EditorAssetLibrary.save_asset(dest)
    log(f"created star mat {dest}")
    return mat


def fix_atmosphere(world):
    actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SkyAtmosphere)
    if not actors:
        raise RuntimeError("no SkyAtmosphere")
    sa = actors[0]
    sa.set_actor_label("PlanetAtmosphere")
    sac = sa.get_component_by_class(unreal.SkyAtmosphereComponent)
    # Thin ~2.5 km shell on 6 km planet: denser near surface so stars don't punch through.
    sac.set_editor_property("bottom_radius", 6.0)
    sac.set_editor_property("atmosphere_height", 2.5)
    sac.set_editor_property("rayleigh_scattering_scale", 0.32)
    sac.set_editor_property("rayleigh_exponential_distribution", 1.2)
    sac.set_editor_property("mie_scattering_scale", 0.005)
    sac.set_editor_property("mie_exponential_distribution", 0.8)
    sac.set_editor_property("multi_scattering_factor", 1.15)
    sac.set_editor_property("aerial_pespective_view_distance_scale", 0.12)
    sac.set_editor_property("sky_luminance_factor", unreal.LinearColor(1.0, 1.0, 1.05, 1.0))
    sac.set_editor_property("ground_albedo", unreal.Color(26, 26, 26, 255))
    log(
        f"atmosphere height={sac.get_editor_property('atmosphere_height')} "
        f"rayleigh={sac.get_editor_property('rayleigh_scattering_scale')} "
        f"exp={sac.get_editor_property('rayleigh_exponential_distribution')}"
    )


def fix_skylight(world):
    actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SkyLight)
    if not actors:
        raise RuntimeError("no SkyLight")
    sl = actors[0]
    slc = sl.get_component_by_class(unreal.SkyLightComponent)
    before = (
        slc.get_editor_property("source_type"),
        slc.get_editor_property("cubemap"),
        slc.get_editor_property("intensity"),
    )
    # daylight cubemap was filling the void pale-blue outside/alongside atmosphere.
    slc.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
    slc.set_editor_property("cubemap", None)
    slc.set_editor_property("real_time_capture", True)
    slc.set_editor_property("intensity", 1.4)
    slc.set_editor_property("lower_hemisphere_is_black", True)
    log(f"skylight before={before} after=CAPTURED inten=1.4")


def cleanup_and_spawn_star_domes(world, mat):
    for a in list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor)):
        label = a.get_actor_label()
        tags = [str(t) for t in a.tags]
        if "Floor" in a.get_name() or label == "Floor" or "SpaceStarDome" in tags or "SpaceStarDome" in label:
            log(f"destroy {a.get_name()} ({label})")
            a.destroy_actor()

    mesh = unreal.load_asset(
        "/Game/AlienFantasyEnvironmentMe/Content/AlienEnvMegaPackVol1/Meshes/AlienJunglePlants/Space/SM_StarSphere"
    )
    if not mesh:
        mesh = unreal.load_asset("/Engine/BasicShapes/Sphere")
    bb = mesh.get_bounding_box()
    ext = bb.max - bb.min
    local_r = max(ext.x, ext.y, ext.z) * 0.5
    scale = 4000000.0 / max(local_r, 1.0)
    log(f"star mesh={mesh.get_name()} local_r={local_r} scale={scale}")

    def spawn(label, rot):
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.StaticMeshActor, unreal.Vector(0, 0, 0), rot
        )
        actor.set_actor_label(label)
        actor.tags = [unreal.Name("SpaceStarDome")]
        smc = actor.get_component_by_class(unreal.StaticMeshComponent)
        smc.set_editor_property("static_mesh", mesh)
        smc.set_material(0, mat)
        actor.set_actor_scale3d(unreal.Vector(scale, scale, scale))
        smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        smc.set_cast_shadow(False)
        try:
            smc.set_editor_property("bounds_scale", 50.0)
            smc.set_editor_property("never_distance_cull", True)
        except Exception as e:
            log(f"cull props warn: {e}")
        smc.set_visibility(True)
        log(f"spawned {label}")
        return actor

    spawn("SpaceStarDome_A", unreal.Rotator(0, 0, 0))
    spawn("SpaceStarDome_B", unreal.Rotator(180, 0, 0))


def save_map():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ok = les.save_current_level()
    log(f"save_current_level -> {ok}")
    return ok


def main():
    open(LOG_PATH, "w", encoding="utf-8").write("start\n")
    try:
        world = get_editor_world()
        if not world:
            raise RuntimeError("no editor world")
        log(f"world={world.get_path_name()}")
        fix_atmosphere(world)
        fix_skylight(world)
        mat = ensure_star_material()
        cleanup_and_spawn_star_domes(world, mat)
        save_map()
        # also save star mat package if dirty
        unreal.EditorAssetLibrary.save_directory("/Game/RedMMO/Materials")
        with open(DONE_FLAG, "w", encoding="utf-8") as f:
            f.write("ok\n")
        log("DONE ok")
    except Exception as e:
        log(f"FAILED: {e}")
        with open(DONE_FLAG, "w", encoding="utf-8") as f:
            f.write(f"fail: {e}\n")
        raise


main()
