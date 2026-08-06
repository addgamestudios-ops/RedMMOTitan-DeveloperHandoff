"""Playtest fix: atmosphere_height 2.5→2.0 km, ensure SpaceStarDome + M_SpaceStars_Live, save map.
Run via MCP execute_python_code or -ExecutePythonScript.
Does NOT touch jetpack / RedPlayerCharacter attach.
"""
import unreal

LOG = "/tmp/titan_atm_stars_fix.log"


def log(msg):
    print(f"[atm_stars] {msg}")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def main():
    open(LOG, "w", encoding="utf-8").write("start\n")
    uew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not uew:
        raise RuntimeError("no editor world")
    log(f"world={uew.get_path_name()}")

    # --- Atmosphere ~2.0 km, keep dense Rayleigh ---
    atms = unreal.GameplayStatics.get_all_actors_of_class(uew, unreal.SkyAtmosphere)
    if not atms:
        raise RuntimeError("no SkyAtmosphere")
    sa = atms[0]
    sa.set_actor_label("PlanetAtmosphere")
    sac = sa.get_component_by_class(unreal.SkyAtmosphereComponent)
    before_h = sac.get_editor_property("atmosphere_height")
    sac.set_editor_property("bottom_radius", 6.0)
    sac.set_editor_property("atmosphere_height", 2.0)
    # Slightly denser near-surface so stars don't punch through the thinner shell.
    sac.set_editor_property("rayleigh_scattering_scale", 0.36)
    sac.set_editor_property("rayleigh_exponential_distribution", 1.1)
    sac.set_editor_property("mie_scattering_scale", 0.005)
    sac.set_editor_property("mie_exponential_distribution", 0.8)
    sac.set_editor_property("multi_scattering_factor", 1.15)
    sac.set_editor_property("aerial_pespective_view_distance_scale", 0.12)
    log(
        f"atm height {before_h} -> {sac.get_editor_property('atmosphere_height')} "
        f"rayleigh={sac.get_editor_property('rayleigh_scattering_scale')} "
        f"exp={sac.get_editor_property('rayleigh_exponential_distribution')}"
    )

    # --- Star material ---
    mat = unreal.load_asset("/Game/RedMMO/Materials/M_SpaceStars_Live")
    if not mat:
        # Fall back to running ensure from fix_space_sky if missing
        log("WARN: M_SpaceStars_Live missing — load/create via fix_space_sky ensure")
        raise RuntimeError("M_SpaceStars_Live missing")
    log(f"star mat={mat.get_path_name()}")

    # --- Domes ---
    domes = []
    for a in unreal.GameplayStatics.get_all_actors_of_class(uew, unreal.StaticMeshActor):
        tags = [str(t) for t in a.tags]
        if "SpaceStarDome" in tags or "SpaceStarDome" in a.get_actor_label():
            domes.append(a)
    log(f"existing domes={len(domes)}")

    mesh = unreal.load_asset(
        "/Game/AlienFantasyEnvironmentMe/Content/AlienEnvMegaPackVol1/Meshes/AlienJunglePlants/Space/SM_StarSphere"
    )
    if not mesh:
        mesh = unreal.load_asset("/Engine/BasicShapes/Sphere")
    bb = mesh.get_bounding_box()
    ext = bb.max - bb.min
    local_r = max(ext.x, ext.y, ext.z) * 0.5
    scale = 4000000.0 / max(local_r, 1.0)

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
        # Default SpaceFade=0 so ground stays clear; UpdateSkyFade drives it in PIE.
        try:
            mid = smc.create_and_set_material_instance_dynamic(0)
            if mid:
                mid.set_scalar_parameter_value("SpaceFade", 0.0)
        except Exception as e:
            log(f"mid warn: {e}")
        log(f"ensured {label} scale={scale} mat={mat.get_name()}")
        return existing

    ensure_dome("SpaceStarDome_A", unreal.Rotator(0, 0, 0))
    ensure_dome("SpaceStarDome_B", unreal.Rotator(180, 0, 0))

    # Re-assert SoStylized sand on MIC (editor asset) — LayerParameter only.
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
