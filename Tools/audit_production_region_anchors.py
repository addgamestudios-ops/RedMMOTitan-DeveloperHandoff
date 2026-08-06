"""Read-only audit proving production has no 50 km region anchors or terrain stamps."""

import unreal


PRODUCTION_MAP = "/Game/RedMMO/Maps/RedPlanetGen"


level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not level_subsystem.load_level(PRODUCTION_MAP):
    raise RuntimeError(f"Failed to load production map for read-only audit: {PRODUCTION_MAP}")

anchor_class = getattr(unreal, "RedPlanetRegionAnchor", None)
if anchor_class is None:
    raise RuntimeError(
        "Python type unreal.RedPlanetRegionAnchor is unavailable; rebuild TitanEditor first"
    )

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level_actors = list(actor_subsystem.get_all_level_actors())
anchor_paths = sorted(
    actor.get_path_name()
    for actor in level_actors
    if isinstance(actor, anchor_class)
)
if anchor_paths:
    raise RuntimeError(
        "Production map must not contain RED region authoring anchors: " f"{anchor_paths}"
    )

planet_class = getattr(unreal, "CLMPlanet", None)
if planet_class is None:
    raise RuntimeError("Python type unreal.CLMPlanet is unavailable; rebuild TitanEditor first")

production_planets = [actor for actor in level_actors if isinstance(actor, planet_class)]
if len(production_planets) != 1:
    raise RuntimeError(
        "Expected exactly one PlanetGen planet in production, found "
        f"{len(production_planets)}"
    )

terrain_stamps = list(production_planets[0].get_editor_property("terrain_stamps"))
if terrain_stamps:
    raise RuntimeError(
        "Production map must not contain 50 km test terrain stamps: "
        f"count={len(terrain_stamps)}"
    )

unreal.log(
    "RED_PRODUCTION_REGION_ANCHOR_AUDIT "
    f"map={PRODUCTION_MAP} count={len(anchor_paths)} terrain_stamps={len(terrain_stamps)} "
    "result=clean read_only=true"
)
