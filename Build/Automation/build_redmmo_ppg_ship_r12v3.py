"""Reframe the existing visual-only StarSparrow at native scale for R12V3."""

import hashlib
import json
import math
import os
import socket
import traceback

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PAWN_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset"
SHIP_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
SHIP_MESH = "/Game/StarSparrow/Meshes/Examples/SM_StarSparrow01"
EXPECTED_MAP = "013873CF751E7B1A7A3C042C2FC3CD6527760CB6B0A1B0416A8C69AAA31F4BC6"
EXPECTED_PAWN = "65A0413D1921F8ED2F6E4E3893B1C6B5CA3A0D1F7BCFC9AF9BF987940ECDC11E"
ROLLBACK = r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_Ship_R12V3_20260802_183854\pre_r12v3_manifest.json"
ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12V3_20260802"
RESULT = os.path.join(ROOT, "build_redmmo_ppg_ship_r12v3_result.json")
PROTECTED = {
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap":
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap":
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap":
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap":
        "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def rot(value):
    return [float(value.pitch), float(value.yaw), float(value.roll)]


def add(a, b):
    return unreal.Vector(a.x + b.x, a.y + b.y, a.z + b.z)


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def mul(a, scalar):
    return unreal.Vector(a.x * scalar, a.y * scalar, a.z * scalar)


def dot(a, b):
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def cross(a, b):
    return unreal.Vector(a.y * b.z - a.z * b.y,
                         a.z * b.x - a.x * b.z,
                         a.x * b.y - a.y * b.x)


def length(value):
    return math.sqrt(dot(value, value))


def normalized(value):
    magnitude = length(value)
    require(magnitude > 0.001, "Cannot normalize near-zero vector")
    return mul(value, 1.0 / magnitude)


def ports_closed():
    result = {}
    for port in (5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(result.values()), "Provider/MCP port unexpectedly open")
    return result


try:
    require(os.path.isfile(ROLLBACK), "R12V3 rollback manifest missing")
    actual_project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    require(unreal.Paths.is_same_path(actual_project, PROJECT), "Wrong project")
    world = unreal.EditorLevelLibrary.get_editor_world()
    require(world.get_path_name().split(":", 1)[0].split(".", 1)[0] == MAP, "Wrong map")
    require(sha256(MAP_FILE) == EXPECTED_MAP, "R12V2 map hash drift")
    require(sha256(PAWN_FILE) == EXPECTED_PAWN, "R12V2 pawn hash drift")
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint drift: " + path)
    provider_state = ports_closed()
    actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
    spawners = [a for a in actors if a.get_class().get_name() == "PlanetSpawnerBP_C"]
    starts = [a for a in actors if a.get_class().get_name() == "PlayerStart"]
    ships = [a for a in actors if a.get_actor_label() == SHIP_LABEL]
    require(len(spawners) == len(starts) == len(ships) == 1,
            "Expected one spawner, PlayerStart, and R12 ship")
    spawner, start, ship = spawners[0], starts[0], ships[0]
    center = spawner.get_actor_location()
    start_location = start.get_actor_location()
    radial_up = normalized(sub(start_location, center))
    tangent_x = sub(start.get_actor_forward_vector(),
                    mul(radial_up, dot(start.get_actor_forward_vector(), radial_up)))
    if length(tangent_x) < 0.01:
        tangent_x = cross(unreal.Vector(0.0, 0.0, 1.0), radial_up)
    if length(tangent_x) < 0.01:
        tangent_x = cross(unreal.Vector(0.0, 1.0, 0.0), radial_up)
    tangent_x = normalized(tangent_x)
    tangent_y = normalized(cross(radial_up, tangent_x))
    capsules = list(start.get_components_by_class(unreal.CapsuleComponent))
    half_height = float(capsules[0].get_unscaled_capsule_half_height()) if len(capsules) == 1 else 0.0
    shell_radius = length(sub(start_location, center)) - half_height
    direction = normalized(add(add(sub(start_location, center), mul(tangent_x, 2400.0)),
                               mul(tangent_y, -500.0)))
    surface = add(center, mul(direction, shell_radius))
    mesh = unreal.EditorAssetLibrary.load_asset(SHIP_MESH)
    require(isinstance(mesh, unreal.StaticMesh), "StarSparrow mesh unavailable")
    bounds = mesh.get_bounding_box()
    scale = 1.0
    root_offset = max(0.0, -float(bounds.min.z) * scale - 35.0)
    location = add(surface, mul(direction, root_offset))
    rotation = unreal.MathLibrary.make_rot_from_xz(tangent_x, direction)
    before = {
        "location": vec(ship.get_actor_location()),
        "rotation": rot(ship.get_actor_rotation()),
        "scale": vec(ship.get_actor_scale3d()),
    }
    ship.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    require(ship.set_actor_location(location, False, False) is not False, "Ship relocation failed")
    require(ship.set_actor_rotation(rotation, False) is not False, "Ship rotation failed")
    ship.set_actor_enable_collision(False)
    require(unreal.EditorLevelLibrary.save_current_level(), "R12V3 map save failed")
    require(sha256(PAWN_FILE) == EXPECTED_PAWN, "Ship-only pass changed pawn")
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint changed: " + path)
    payload = {
        "schema": "redmmo.ppg_ship.r12v3.build.v1",
        "status": "PASS_SERIALIZED_PENDING_RELOAD_REAL_GPU_VISUAL",
        "rollback": ROLLBACK,
        "provider_ports_closed": provider_state,
        "before": before,
        "after": {
            "location": vec(ship.get_actor_location()),
            "rotation": rot(ship.get_actor_rotation()),
            "scale": vec(ship.get_actor_scale3d()),
            "tangent_offset_cm": [2400.0, -500.0],
            "root_contact_offset_cm": root_offset,
            "native_mesh_max_dimension_cm": max(
                float(bounds.max.x - bounds.min.x),
                float(bounds.max.y - bounds.min.y),
                float(bounds.max.z - bounds.min.z),
            ),
        },
        "map_sha256": sha256(MAP_FILE),
        "pawn_sha256_unchanged": sha256(PAWN_FILE),
        "visual_only": True,
        "collision": "disabled",
        "surface_contact_claimed": False,
    }
except Exception as error:
    payload = {
        "schema": "redmmo.ppg_ship.r12v3.build.v1",
        "status": "FAIL",
        "error": str(error),
        "traceback": traceback.format_exc(),
        "rollback": ROLLBACK,
    }
os.makedirs(ROOT, exist_ok=True)
with open(RESULT + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(RESULT + ".tmp", RESULT)
if payload["status"].startswith("PASS"):
    unreal.log("REDMMO_R12V3_SHIP_BUILD PASS")
else:
    unreal.log_error("REDMMO_R12V3_SHIP_BUILD FAIL " + payload.get("error", ""))
