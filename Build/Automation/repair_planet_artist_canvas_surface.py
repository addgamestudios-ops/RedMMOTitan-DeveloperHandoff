import json
import unreal


MAP = "/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas"
OUT = "D:/RedMMOTitanWindowsData/ArtistHandoff/artist_canvas_surface_repair.json"
STANDALONE_SUNSKY = "/SunPosition/SunSky.SunSky_C"


def read_property(obj, name):
    for candidate in (name, "b" + name[0].upper() + name[1:]):
        try:
            return candidate, obj.get_editor_property(candidate)
        except Exception:
            pass
    raise RuntimeError(
        f"Missing property {name} on {obj.get_class().get_path_name()}"
    )


def set_property(obj, name, value):
    reflected, old_value = read_property(obj, name)
    obj.set_editor_property(reflected, value)
    return reflected, old_value


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
planet.modify()

# Generate the complete low-cost authored proxy with the smallest legal chunk
# pool, then discard the streaming pool through the native cleanup API.
restores = []
for property_name, value in (
    ("max_chunks_per_face", 1),
    ("view_distance", 1.0),
    ("terrain_collision_view_distance", 0.5),
    ("enable_water", False),
    ("enable_foliage", False),
    ("enable_grass", False),
    ("enable_resident_macro_surface", True),
):
    reflected, old_value = set_property(planet, property_name, value)
    restores.append((reflected, old_value))

preview = getattr(planet, "preview_planet", None)
if not callable(preview):
    raise RuntimeError("CLM planet does not expose preview_planet()")
preview()

resident = None
water_mesh = None
for component in planet.get_components_by_class(unreal.ActorComponent) or []:
    if component.get_name() == "ResidentMacroSurface":
        resident = component
    elif component.get_name() == "WaterSphereMesh":
        water_mesh = component

if resident is None:
    raise RuntimeError("ResidentMacroSurface component not found")
if water_mesh is None:
    raise RuntimeError("WaterSphereMesh component not found")

section_count = int(resident.get_num_sections())
if section_count < 1 or not bool(resident.is_visible()):
    raise RuntimeError(
        "Resident surface generation failed: "
        f"sections={section_count}, visible={resident.is_visible()}"
    )

clear_streamed = getattr(planet, "clear_streamed_chunks_keep_resident", None)
if not callable(clear_streamed):
    raise RuntimeError(
        "PlanetGen build does not expose clear_streamed_chunks_keep_resident()"
    )
clear_streamed()

for reflected, old_value in restores:
    planet.set_editor_property(reflected, old_value)

# Re-assert the authoring-map invariants after restoring unrelated settings.
set_property(planet, "enable_water", False)
set_property(planet, "water_material", None)
set_property(planet, "enable_foliage", False)
set_property(planet, "enable_grass", False)
set_property(planet, "enable_resident_macro_surface", True)

_, terrain_material = read_property(planet, "terrain_material")
if terrain_material is None:
    raise RuntimeError("Artist planet has no authored terrain material")
resident.set_material(0, terrain_material)
resident.set_visibility(True, True)
resident.set_hidden_in_game(False)
resident.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
resident.modify()

water_mesh.set_visibility(False, True)
water_mesh.set_hidden_in_game(True)
water_mesh.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
try:
    water_mesh.clear_all_mesh_sections()
except Exception:
    pass
water_mesh.modify()

# The PlanetGen SunSky blueprint already owns the one atmosphere the canvas
# needs. The retained standalone SunSky produced two active atmospheres and the
# severe washed-out/layered presentation shown in player feedback.
removed_sunsky = []
for actor in list(actor_subsystem.get_all_level_actors()):
    if actor.get_class().get_path_name() == STANDALONE_SUNSKY:
        removed_sunsky.append(actor.get_actor_label())
        if not actor_subsystem.destroy_actor(actor):
            raise RuntimeError(
                f"Could not remove duplicate standalone SunSky {actor.get_actor_label()}"
            )

if len(removed_sunsky) != 1:
    raise RuntimeError(
        f"Expected exactly one duplicate standalone SunSky, removed {removed_sunsky}"
    )

# The previous PlayerStart was inside the 7.958 km-radius planet. Put the
# editor/PIE start above the highest legal north-pole terrain elevation.
player_starts = [
    actor
    for actor in actor_subsystem.get_all_level_actors()
    if actor.get_class().get_path_name() == "/Script/Engine.PlayerStart"
]
if len(player_starts) != 1:
    raise RuntimeError(f"Expected one PlayerStart, found {len(player_starts)}")

_, radius = read_property(planet, "planet_radius")
_, max_height = read_property(planet, "max_height")
planet_location = planet.get_actor_location()
start_location = planet_location + unreal.Vector(
    0.0, 0.0, float(radius) + float(max_height) + 500.0
)
player_starts[0].set_actor_location(start_location, False, False)
player_starts[0].set_actor_rotation(unreal.Rotator(0.0, 0.0, 0.0), False)
player_starts[0].modify()

planet.modify()
if not unreal.EditorAssetLibrary.save_asset(MAP, only_if_is_dirty=False):
    raise RuntimeError(f"Unable to save repaired artist map {MAP}")

final_actors = list(actor_subsystem.get_all_level_actors())
chunk_actors = [
    actor
    for actor in final_actors
    if actor.get_class().get_path_name() == "/Script/PlanetGen.CLMPlanetChunk"
]
acceptance = {
    "actor_count_30": len(final_actors) == 30,
    "no_chunk_actors": len(chunk_actors) == 0,
    "resident_sections": int(resident.get_num_sections()) >= 1,
    "resident_visible": bool(resident.is_visible()),
    "water_disabled": not bool(read_property(planet, "enable_water")[1]),
    "water_hidden": not bool(water_mesh.is_visible()),
    "one_duplicate_sunsky_removed": len(removed_sunsky) == 1,
    "player_start_outside_planet": (
        player_starts[0].get_actor_location() - planet_location
    ).length() > float(radius),
}
passed = all(acceptance.values())

payload = {
    "map": MAP,
    "planet_class": planet.get_class().get_path_name(),
    "actor_count": len(final_actors),
    "resident_sections_before_save": section_count,
    "resident_sections_after_save": int(resident.get_num_sections()),
    "resident_material": resident.get_material(0).get_path_name(),
    "removed_sunsky": removed_sunsky,
    "player_start": {
        "x": player_starts[0].get_actor_location().x,
        "y": player_starts[0].get_actor_location().y,
        "z": player_starts[0].get_actor_location().z,
    },
    "acceptance": acceptance,
    "passed": passed,
}
with open(OUT, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)

unreal.SystemLibrary.execute_console_command(world, "MAP CHECK DONTDISPLAYDIALOG")
unreal.SystemLibrary.execute_console_command(world, "FLUSHLOG")

if not passed:
    raise RuntimeError(f"Artist canvas repair acceptance failed: {payload}")

unreal.log(
    "RED_ARTIST_CANVAS_SURFACE_REPAIR_PASS "
    f"actors={len(final_actors)} sections={resident.get_num_sections()} "
    f"player_start_z={player_starts[0].get_actor_location().z:.1f}"
)

# Do not retain Python wrappers for actors/components destroyed during this
# script. UE's commandlet tears Python down after the map is saved; releasing
# these wrappers first prevents shutdown from touching a destroyed UObject.
actors = []
final_actors = []
standalone_sunsky = []
chunk_actors = []
player_starts = []
components = None
resident = None
water_mesh = None
planet = None
world = None
