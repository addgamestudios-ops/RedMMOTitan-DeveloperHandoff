import json
import unreal


MAP = "/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas"
OUT = "D:/RedMMOTitanWindowsData/ArtistHandoff/artist_canvas_runtime_diagnostic.json"


def vector(value):
    return {"x": value.x, "y": value.y, "z": value.z}


def rotation(value):
    return {"pitch": value.pitch, "yaw": value.yaw, "roll": value.roll}


world = unreal.EditorLoadingAndSavingUtils.load_map(MAP)
if not world:
    raise RuntimeError(f"Unable to load {MAP}")

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rows = []
for actor in actor_subsystem.get_all_level_actors():
    actor_row = {
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_path_name(),
        "location": vector(actor.get_actor_location()),
        "rotation": rotation(actor.get_actor_rotation()),
        "scale": vector(actor.get_actor_scale3d()),
        "hidden_editor": bool(actor.is_hidden_ed()),
        "components": [],
    }
    for component in actor.get_components_by_class(unreal.SceneComponent):
        component_row = {
            "name": component.get_name(),
            "class": component.get_class().get_path_name(),
            "location": vector(component.get_world_location()),
            "rotation": rotation(component.get_world_rotation()),
            "scale": vector(component.get_world_scale()),
            "visible": bool(component.is_visible()),
        }
        if isinstance(component, unreal.StaticMeshComponent):
            mesh = component.get_editor_property("static_mesh")
            component_row["static_mesh"] = mesh.get_path_name() if mesh else ""
        actor_row["components"].append(component_row)
    rows.append(actor_row)

payload = {
    "map": MAP,
    "actor_count": len(rows),
    "actors": sorted(rows, key=lambda row: row["label"]),
}
with open(OUT, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)

unreal.log(f"RED_ARTIST_CANVAS_DIAGNOSTIC_READY actors={len(rows)} path={OUT}")
