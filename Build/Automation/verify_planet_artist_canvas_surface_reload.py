import json
import unreal


MAP = "/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas"
OUT = "D:/RedMMOTitanWindowsData/ArtistHandoff/artist_canvas_surface_reload_verify.json"
STANDALONE_SUNSKY = "/SunPosition/SunSky.SunSky_C"
SKY_ATMOSPHERE_COMPONENT = "/Script/Engine.SkyAtmosphereComponent"


def read_property(obj, name):
    for candidate in (name, "b" + name[0].upper() + name[1:]):
        try:
            return obj.get_editor_property(candidate)
        except Exception:
            pass
    raise RuntimeError(
        f"Missing property {name} on {obj.get_class().get_path_name()}"
    )


world = unreal.EditorLoadingAndSavingUtils.load_map(MAP)
if not world:
    raise RuntimeError(f"Unable to load {MAP}")

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = list(actor_subsystem.get_all_level_actors())
planets = [
    actor for actor in actors if "CLMPlanet" in actor.get_class().get_path_name()
]
if len(planets) != 1:
    raise RuntimeError(f"Expected one CLM planet, found {len(planets)}")

planet = planets[0]
components = {
    component.get_name(): component
    for component in planet.get_components_by_class(unreal.ActorComponent) or []
}
resident = components.get("ResidentMacroSurface")
water_mesh = components.get("WaterSphereMesh")
if resident is None or water_mesh is None:
    raise RuntimeError("Planet resident/water procedural component missing")

standalone_sunsky = [
    actor
    for actor in actors
    if actor.get_class().get_path_name() == STANDALONE_SUNSKY
]
chunk_actors = [
    actor
    for actor in actors
    if actor.get_class().get_path_name() == "/Script/PlanetGen.CLMPlanetChunk"
]
player_starts = [
    actor
    for actor in actors
    if actor.get_class().get_path_name() == "/Script/Engine.PlayerStart"
]

visible_atmospheres = []
for actor in actors:
    for component in actor.get_components_by_class(unreal.SceneComponent) or []:
        if component.get_class().get_path_name() != SKY_ATMOSPHERE_COMPONENT:
            continue
        if component.is_visible():
            visible_atmospheres.append(
                f"{actor.get_actor_label()}.{component.get_name()}"
            )

radius = float(read_property(planet, "planet_radius"))
planet_location = planet.get_actor_location()
player_start_distance = (
    (player_starts[0].get_actor_location() - planet_location).length()
    if len(player_starts) == 1
    else 0.0
)
resident_material = resident.get_material(0)
resident_material_path = resident_material.get_path_name() if resident_material else ""

acceptance = {
    "actor_count_30": len(actors) == 30,
    "one_planet": len(planets) == 1,
    "no_chunk_actors": len(chunk_actors) == 0,
    "resident_section_serialized": int(resident.get_num_sections()) >= 1,
    "resident_component_visible": bool(resident.is_visible()),
    "resident_section_zero_visible": bool(resident.is_mesh_section_visible(0)),
    "resident_uses_authored_material": resident_material_path
    == "/Game/RedMMO/Materials/MI_PlanetBiome_RED.MI_PlanetBiome_RED",
    "water_disabled": not bool(read_property(planet, "enable_water")),
    "water_mesh_hidden": not bool(water_mesh.is_visible()),
    "no_standalone_sunsky": len(standalone_sunsky) == 0,
    "exactly_one_visible_atmosphere": len(visible_atmospheres) == 1,
    "one_player_start": len(player_starts) == 1,
    "player_start_outside_planet": player_start_distance > radius,
}
passed = all(acceptance.values())

payload = {
    "map": MAP,
    "actor_count": len(actors),
    "planet_class": planet.get_class().get_path_name(),
    "resident_sections_after_reload": int(resident.get_num_sections()),
    "resident_visible_after_reload": bool(resident.is_visible()),
    "resident_material": resident_material_path,
    "water_enabled": bool(read_property(planet, "enable_water")),
    "water_mesh_visible": bool(water_mesh.is_visible()),
    "standalone_sunsky_count": len(standalone_sunsky),
    "visible_atmospheres": visible_atmospheres,
    "player_start_distance_cm": player_start_distance,
    "planet_radius_cm": radius,
    "acceptance": acceptance,
    "passed": passed,
}
with open(OUT, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)

unreal.SystemLibrary.execute_console_command(
    world, "MAP CHECK DONTDISPLAYDIALOG"
)
unreal.SystemLibrary.execute_console_command(world, "FLUSHLOG")

if not passed:
    raise RuntimeError(f"Artist canvas reload acceptance failed: {payload}")

unreal.log(
    "RED_ARTIST_CANVAS_RELOAD_VERIFY_PASS "
    f"actors={len(actors)} sections={resident.get_num_sections()} "
    f"atmospheres={len(visible_atmospheres)} water_visible={water_mesh.is_visible()}"
)
