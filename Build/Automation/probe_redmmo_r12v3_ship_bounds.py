"""Read-only editor probe for the R12V3 parked StarSparrow bounds."""

import json
import math
import os

import unreal


MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
OUT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12V3_20260802"
    r"\probe_redmmo_r12v3_ship_bounds.json"
)


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def dot(a, b):
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def normalized(value):
    magnitude = math.sqrt(dot(value, value))
    if magnitude < 0.001:
        raise RuntimeError("Near-zero vector")
    return unreal.Vector(value.x / magnitude, value.y / magnitude, value.z / magnitude)


world = unreal.EditorLevelLibrary.get_editor_world()
if world.get_path_name().split(":", 1)[0].split(".", 1)[0] != MAP:
    raise RuntimeError("Wrong map")
actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
ship = next(a for a in actors if a.get_actor_label() == LABEL)
spawner = next(a for a in actors if a.get_class().get_name() == "PlanetSpawnerBP_C")
start = next(a for a in actors if a.get_class().get_name() == "PlayerStart")
components = [
    c for c in ship.get_components_by_class(unreal.StaticMeshComponent)
    if c.get_editor_property("static_mesh") is not None
]
if len(components) != 1:
    raise RuntimeError("Expected exactly one ship mesh component")
component = components[0]
mesh = component.get_editor_property("static_mesh")
box = mesh.get_bounding_box()
bounds_origin, bounds_extent = ship.get_actor_bounds(False, False)
center = spawner.get_actor_location()
radial_up = normalized(sub(start.get_actor_location(), center))
start_forward = start.get_actor_forward_vector()
start_tangent_forward = sub(start_forward, unreal.Vector(
    radial_up.x * dot(start_forward, radial_up),
    radial_up.y * dot(start_forward, radial_up),
    radial_up.z * dot(start_forward, radial_up),
))
start_tangent_forward = normalized(start_tangent_forward)
target_start_rotation = unreal.MathLibrary.make_rot_from_xz(start_tangent_forward, radial_up)
payload = {
    "actor_location": vec(ship.get_actor_location()),
    "actor_rotation": str(ship.get_actor_rotation()),
    "actor_scale": vec(ship.get_actor_scale3d()),
    "actor_bounds_origin": vec(bounds_origin),
    "actor_bounds_extent": vec(bounds_extent),
    "actor_origin_radial_delta_from_start_cm": dot(
        sub(ship.get_actor_location(), start.get_actor_location()), radial_up
    ),
    "bounds_center_radial_delta_from_start_cm": dot(
        sub(bounds_origin, start.get_actor_location()), radial_up
    ),
    "bounds_radial_half_extent_upper_bound_cm": (
        abs(radial_up.x) * bounds_extent.x
        + abs(radial_up.y) * bounds_extent.y
        + abs(radial_up.z) * bounds_extent.z
    ),
    "component_relative_location": vec(component.get_editor_property("relative_location")),
    "component_relative_rotation": str(component.get_editor_property("relative_rotation")),
    "component_relative_scale": vec(component.get_editor_property("relative_scale3d")),
    "mesh_local_min": vec(box.min),
    "mesh_local_max": vec(box.max),
    "player_start": vec(start.get_actor_location()),
    "player_start_rotation": str(start.get_actor_rotation()),
    "player_start_forward": vec(start_forward),
    "player_start_forward_dot_radial_up": dot(start_forward, radial_up),
    "player_start_tangent_forward": vec(start_tangent_forward),
    "player_start_target_tangent_rotation": str(target_start_rotation),
    "radial_up": vec(radial_up),
    "actor_forward": vec(ship.get_actor_forward_vector()),
    "actor_right": vec(ship.get_actor_right_vector()),
    "actor_up": vec(ship.get_actor_up_vector()),
    "actor_up_dot_radial_up": dot(ship.get_actor_up_vector(), radial_up),
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(OUT + ".tmp", OUT)
unreal.log("REDMMO_R12V3_SHIP_BOUNDS_PROBE PASS")
