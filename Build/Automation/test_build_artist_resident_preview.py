import json
import unreal


SOURCE = "/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas"
TEST = "/Game/RedMMO/Maps/Tests/RedPlanetGen_50km_ArtistResidentPreview_T01"
OUT = "D:/RedMMOTitanWindowsData/ArtistHandoff/artist_resident_preview_test.json"


def read_property(obj, name):
    for candidate in (name, "b" + name[0].upper() + name[1:]):
        try:
            return candidate, obj.get_editor_property(candidate)
        except Exception:
            pass
    raise RuntimeError(f"Missing property {name} on {obj.get_class().get_path_name()}")


def set_property(obj, name, value):
    reflected, old_value = read_property(obj, name)
    obj.set_editor_property(reflected, value)
    return reflected, old_value


if unreal.EditorAssetLibrary.does_asset_exist(TEST):
    raise RuntimeError(f"Disposable test map already exists; refusing overwrite: {TEST}")

if unreal.EditorAssetLibrary.duplicate_asset(SOURCE, TEST) is None:
    raise RuntimeError(f"Unable to duplicate {SOURCE} to {TEST}")

if not unreal.EditorLevelLibrary.load_level(TEST):
    raise RuntimeError(f"Unable to load {TEST}")

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = list(actor_subsystem.get_all_level_actors())
planets = [
    actor
    for actor in actors
    if "CLMPlanet" in actor.get_class().get_path_name()
]
if len(planets) != 1:
    raise RuntimeError(f"Expected one CLM planet, found {len(planets)}")

planet = planets[0]
planet.modify()
restores = []
for property_name, value in (
    ("max_chunks_per_face", 1),
    ("view_distance", 0.1),
    ("terrain_collision_view_distance", 0.1),
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
for component in planet.get_components_by_class(unreal.ActorComponent) or []:
    if component.get_name() == "ResidentMacroSurface":
        resident = component
        break
if resident is None:
    raise RuntimeError("ResidentMacroSurface component not found")

section_count_before = int(resident.get_num_sections())
visible_before = bool(resident.is_visible())
if section_count_before < 1 or not visible_before:
    raise RuntimeError(
        f"Resident preview did not build: sections={section_count_before}, "
        f"visible={visible_before}"
    )

# The artist canvas needs only the serialized full-planet macro proxy. Remove the
# streamed chunk pool before saving so the handoff stays small and editable.
destroyed_chunks = 0
for actor in list(actor_subsystem.get_all_level_actors()):
    if actor == planet:
        continue
    class_path = actor.get_class().get_path_name()
    if class_path == "/Script/PlanetGen.CLMPlanetChunk" or actor.get_owner() == planet:
        if actor_subsystem.destroy_actor(actor):
            destroyed_chunks += 1

for reflected, old_value in restores:
    planet.set_editor_property(reflected, old_value)

# Avoid serializing a dynamic material instance into the standalone map. The
# authored terrain material asset contains the same shader graph and remains a
# normal project dependency.
try:
    _, terrain_material = read_property(planet, "terrain_material")
    if terrain_material is not None:
        resident.set_material(0, terrain_material)
except Exception as exc:
    unreal.log_warning(f"Could not restore resident material asset: {exc}")

resident.set_visibility(True, True)
resident.modify()
planet.modify()

if not unreal.EditorAssetLibrary.save_asset(TEST, only_if_is_dirty=False):
    raise RuntimeError(f"Unable to save {TEST}")

payload = {
    "source": SOURCE,
    "test": TEST,
    "planet_class": planet.get_class().get_path_name(),
    "resident_sections_before_save": section_count_before,
    "resident_visible_before_save": visible_before,
    "destroyed_chunk_actors": destroyed_chunks,
    "actor_count_after_cleanup": len(actor_subsystem.get_all_level_actors()),
}
with open(OUT, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)

unreal.log(
    "RED_ARTIST_RESIDENT_PREVIEW_TEST_READY "
    f"sections={section_count_before} destroyed_chunks={destroyed_chunks}"
)
