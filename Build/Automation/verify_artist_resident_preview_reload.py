import json
import unreal


MAP = "/Game/RedMMO/Maps/Tests/RedPlanetGen_50km_ArtistResidentPreview_T01"
OUT = "D:/RedMMOTitanWindowsData/ArtistHandoff/artist_resident_preview_reload_verify.json"


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
resident = None
water_mesh = None
for component in planet.get_components_by_class(unreal.ActorComponent) or []:
    if component.get_name() == "ResidentMacroSurface":
        resident = component
    elif component.get_name() == "WaterSphereMesh":
        water_mesh = component

if resident is None:
    raise RuntimeError("ResidentMacroSurface component not found after reload")
if water_mesh is None:
    raise RuntimeError("WaterSphereMesh component not found after reload")

section_count = int(resident.get_num_sections())
resident_visible = bool(resident.is_visible())
water_enabled = bool(read_property(planet, "enable_water"))
water_visible = bool(water_mesh.is_visible())

acceptance = {
    "exact_actor_count_31": len(actors) == 31,
    "resident_section_serialized": section_count >= 1,
    "resident_visible_after_reload": resident_visible,
    "water_disabled": not water_enabled,
    "water_mesh_hidden": not water_visible,
}
passed = all(acceptance.values())

payload = {
    "map": MAP,
    "actor_count": len(actors),
    "planet_class": planet.get_class().get_path_name(),
    "resident_sections_after_reload": section_count,
    "resident_visible_after_reload": resident_visible,
    "water_enabled": water_enabled,
    "water_mesh_visible": water_visible,
    "acceptance": acceptance,
    "passed": passed,
}
with open(OUT, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)

unreal.SystemLibrary.execute_console_command(world, "MAP CHECK")

if not passed:
    raise RuntimeError(f"Artist resident reload acceptance failed: {payload}")

unreal.log(
    "RED_ARTIST_RESIDENT_RELOAD_VERIFY_PASS "
    f"actors={len(actors)} sections={section_count} water_visible={water_visible}"
)
