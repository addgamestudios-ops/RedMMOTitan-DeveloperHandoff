"""Playtest: atm height 1.0 km, volumetric clouds, re-assert SpaceStarDome + M_SpaceStars_Live.
Run via MCP execute_python or -ExecutePythonScript after editor loads RedPlanetGen.
"""
import unreal

LOG = "/tmp/titan_playtest_atm_clouds.log"


def log(msg):
    print(f"[playtest_fix] {msg}")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def main():
    open(LOG, "w", encoding="utf-8").write("start\n")
    uew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not uew:
        raise RuntimeError("no editor world")
    log(f"world={uew.get_path_name()}")

    atms = unreal.GameplayStatics.get_all_actors_of_class(uew, unreal.SkyAtmosphere)
    if not atms:
        raise RuntimeError("no SkyAtmosphere")
    sa = atms[0]
    sa.set_actor_label("PlanetAtmosphere")
    sac = sa.get_component_by_class(unreal.SkyAtmosphereComponent)
    before_h = sac.get_editor_property("atmosphere_height")
    sac.set_editor_property("bottom_radius", 6.0)
    sac.set_editor_property("atmosphere_height", 1.0)
    sac.set_editor_property("rayleigh_scattering_scale", 0.40)
    sac.set_editor_property("rayleigh_exponential_distribution", 1.0)
    sac.set_editor_property("mie_scattering_scale", 0.006)
    sac.set_editor_property("mie_exponential_distribution", 0.7)
    sac.set_editor_property("multi_scattering_factor", 1.2)
    sac.set_editor_property("aerial_pespective_view_distance_scale", 0.10)
    log(f"atm height {before_h} -> {sac.get_editor_property('atmosphere_height')}")

    clouds = unreal.GameplayStatics.get_all_actors_of_class(uew, unreal.VolumetricCloud)
    if not clouds:
        cloud = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.VolumetricCloud, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0)
        )
        cloud.set_actor_label("RedVolumetricClouds")
        cc = cloud.get_component_by_class(unreal.VolumetricCloudComponent)
        if cc:
            cc.set_editor_property("layer_bottom_altitude", 0.35)
            cc.set_editor_property("layer_height", 0.55)
        log("spawned RedVolumetricClouds")
    else:
        for c in clouds:
            cc = c.get_component_by_class(unreal.VolumetricCloudComponent)
            if cc:
                cc.set_editor_property("layer_bottom_altitude", 0.35)
                cc.set_editor_property("layer_height", 0.55)
            log(f"tuned existing cloud {c.get_actor_label()}")

    mat = unreal.load_asset("/Game/RedMMO/Materials/M_SpaceStars_Live")
    if not mat:
        raise RuntimeError("M_SpaceStars_Live missing")
    log(f"star mat={mat.get_path_name()}")

    mesh = unreal.load_asset(
        "/Game/AlienFantasyEnvironmentMe/Content/AlienEnvMegaPackVol1/Meshes/AlienJunglePlants/Space/SM_StarSphere"
    )
    if not mesh:
        mesh = unreal.load_asset("/Engine/BasicShapes/Sphere")
    bb = mesh.get_bounding_box()
    ext = bb.max - bb.min
    local_r = max(ext.x, ext.y, ext.z) * 0.5
    scale = 4000000.0 / max(local_r, 1.0)

    domes = []
    for a in unreal.GameplayStatics.get_all_actors_of_class(uew, unreal.StaticMeshActor):
        tags = [str(t) for t in a.tags]
        if "SpaceStarDome" in tags or "SpaceStarDome" in a.get_actor_label():
            domes.append(a)
    log(f"existing domes={len(domes)}")

    def ensure_dome(label, rot):
        existing = None
        for a in domes:
            if a.get_actor_label() == label or label in a.get_actor_label():
                existing = a
                break
        if existing is None:
            existing = unreal.EditorLevelLibrary.spawn_actor_from_class(
                unreal.StaticMeshActor, unreal.Vector(0, 0, 0), rot
            )
            existing.set_actor_label(label)
            log(f"spawned {label}")
        existing.tags = [unreal.Name("SpaceStarDome")]
        smc = existing.get_component_by_class(unreal.StaticMeshComponent)
        smc.set_editor_property("static_mesh", mesh)
        smc.set_material(0, mat)
        existing.set_actor_scale3d(unreal.Vector(scale, scale, scale))
        smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        smc.set_cast_shadow(False)
        try:
            smc.set_editor_property("bounds_scale", 50.0)
            smc.set_editor_property("never_distance_cull", True)
        except Exception as e:
            log(f"cull props: {e}")
        smc.set_visibility(True)
        try:
            mid = smc.create_and_set_material_instance_dynamic(0)
            if mid:
                mid.set_scalar_parameter_value("SpaceFade", 0.0)
        except Exception as e:
            log(f"mid warn: {e}")
        log(f"ensured {label}")
        return existing

    ensure_dome("SpaceStarDome_A", unreal.Rotator(0, 0, 0))
    ensure_dome("SpaceStarDome_B", unreal.Rotator(180, 0, 0))

    try:
        r = unreal.RedMMOEditorTools.apply_so_stylized_sand_to_planet_biome()
        log(f"sand MI: {r}")
    except Exception as e:
        log(f"sand MI warn: {e}")

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ok = les.save_current_level()
    log(f"save_current_level -> {ok}")
    unreal.EditorAssetLibrary.save_asset("/Game/RedMMO/Materials/M_SpaceStars_Live")
    log("DONE ok")


main()
