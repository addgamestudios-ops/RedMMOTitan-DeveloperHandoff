"""Correct the R12 third-person camera and visual-only parked ship in clean RedMMO."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import socket
import traceback

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO"
ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12V2_20260802"
RESULT = os.path.join(ROOT, "build_redmmo_ppg_character_ship_r12v2_result.json")
DONE = os.path.join(ROOT, "build_redmmo_ppg_character_ship_r12v2.done")
HELPER = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomeStylizedRegion_R07_20260801_163147"
    r"\r07_character_ship_helpers.py"
)
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
SHIP_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
SHIP_MESH = "/Game/StarSparrow/Meshes/Examples/SM_StarSparrow01"
MAP_FILE = os.path.join(PROJECT, r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap")
PAWN_FILE = os.path.join(PROJECT, r"Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset")
SHIP_FILE = os.path.join(PROJECT, r"Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset")
EXPECTED = {
    MAP_FILE: "B66CE7E24465CB8ADA8F53D5F31B480289415D1641726BA7C276B0907BF20133",
    PAWN_FILE: "8421120C7FEE24FD457775789F0758D32F8D34AC7F0ECE5DA2603CFAA146F768",
    SHIP_FILE: "C9FDCF7D0FE89DACE39D418B79A7951C37C699C1FEA7E485C85670B2AB864BD6",
}
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
ROLLBACK = (
    r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_CharacterShip_R12V2_20260802_182912"
    r"\pre_r12v2_manifest.json"
)


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


def mul(value, scalar):
    return unreal.Vector(value.x * scalar, value.y * scalar, value.z * scalar)


def dot(a, b):
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def cross(a, b):
    return unreal.Vector(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def length(value):
    return math.sqrt(dot(value, value))


def normalized(value):
    magnitude = length(value)
    require(magnitude > 0.001, "Cannot normalize near-zero vector")
    return mul(value, 1.0 / magnitude)


def load_helper():
    spec = importlib.util.spec_from_file_location("redmmo_r12v2_helper", HELPER)
    require(spec is not None and spec.loader is not None, "R07 helper import spec unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def provider_gate():
    closed = {}
    for port in (5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            closed[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(closed.values()), "Provider/MCP port unexpectedly open: " + str(closed))
    return closed


def unique_component_records(bp, helper, component_class, variable):
    records = []
    seen = set()
    for record in helper._subobject_records(bp):
        component = record["object_for_blueprint"]
        if record["variable"] != variable or not isinstance(component, component_class):
            continue
        identity = id(record["associated"] or component)
        if identity in seen:
            continue
        seen.add(identity)
        records.append(record)
    require(len(records) == 1, f"Expected one logical {variable} component, found {len(records)}")
    return records[0]


def configure_camera(bp, helper):
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    require(subsystem is not None, "SubobjectDataSubsystem unavailable")
    root_record = unique_component_records(bp, helper, unreal.CapsuleComponent, "CapsuleComponent")
    arm_record = unique_component_records(bp, helper, unreal.SpringArmComponent, "SpringArm")
    camera_record = unique_component_records(bp, helper, unreal.CameraComponent, "Camera")
    root = root_record["object_for_blueprint"]
    arm = arm_record["object_for_blueprint"]
    camera = camera_record["object_for_blueprint"]
    before = {
        "arm_parent": arm.get_attach_parent().get_path_name() if arm.get_attach_parent() else None,
        "camera_parent": camera.get_attach_parent().get_path_name() if camera.get_attach_parent() else None,
        "arm_length": float(arm.get_editor_property("target_arm_length")),
        "arm_location": vec(arm.get_editor_property("relative_location")),
        "camera_fov": float(camera.get_editor_property("field_of_view")),
    }
    require(subsystem.attach_subobject(root_record["handle"], arm_record["handle"]),
            "Unable to attach SpringArm subobject to capsule")
    require(subsystem.attach_subobject(arm_record["handle"], camera_record["handle"]),
            "Unable to attach Camera subobject to SpringArm")
    keep_relative = unreal.AttachmentRule.KEEP_RELATIVE
    require(arm.attach_to_component(
        root, unreal.Name("None"), keep_relative, keep_relative, keep_relative, False
    ), "SpringArm component-template attachment failed")
    require(camera.attach_to_component(
        arm, unreal.Name("SpringEndpoint"), keep_relative, keep_relative, keep_relative, False
    ), "Camera component-template attachment failed")
    arm.set_editor_property("relative_location", unreal.Vector(0.0, 0.0, 70.0))
    arm.set_editor_property("relative_rotation", unreal.Rotator(0.0, 0.0, 0.0))
    arm.set_editor_property("relative_scale3d", unreal.Vector(1.0, 1.0, 1.0))
    arm.set_editor_property("target_arm_length", 400.0)
    arm.set_editor_property("socket_offset", unreal.Vector(0.0, 0.0, 0.0))
    arm.set_editor_property("target_offset", unreal.Vector(0.0, 0.0, 0.0))
    arm.set_editor_property("use_pawn_control_rotation", True)
    arm.set_editor_property("do_collision_test", True)
    arm.set_editor_property("inherit_pitch", True)
    arm.set_editor_property("inherit_yaw", True)
    arm.set_editor_property("inherit_roll", True)
    camera.set_editor_property("relative_location", unreal.Vector(0.0, 0.0, 0.0))
    camera.set_editor_property("relative_rotation", unreal.Rotator(0.0, 0.0, 0.0))
    camera.set_editor_property("relative_scale3d", unreal.Vector(1.0, 1.0, 1.0))
    camera.set_editor_property("field_of_view", 90.0)
    camera.set_editor_property("use_pawn_control_rotation", False)
    require(arm.get_attach_parent() == root, "SpringArm parent readback mismatch")
    require(camera.get_attach_parent() == arm, "Camera parent readback mismatch")
    require(str(camera.get_attach_socket_name()) == "SpringEndpoint",
            "Camera spring endpoint socket readback mismatch")
    compile_report = helper._compile_blueprint(bp)
    helper._save_asset(bp)
    require(float(arm.get_editor_property("target_arm_length")) == 400.0,
            "Saved spring arm length readback mismatch")
    return {
        "before": before,
        "after": {
            "arm_parent": arm.get_attach_parent().get_path_name(),
            "camera_parent": camera.get_attach_parent().get_path_name(),
            "camera_socket": str(camera.get_attach_socket_name()),
            "arm_length": float(arm.get_editor_property("target_arm_length")),
            "arm_location": vec(arm.get_editor_property("relative_location")),
            "camera_fov": float(camera.get_editor_property("field_of_view")),
            "arm_use_pawn_control_rotation": bool(arm.get_editor_property("use_pawn_control_rotation")),
            "camera_use_pawn_control_rotation": bool(camera.get_editor_property("use_pawn_control_rotation")),
        },
        "compile": compile_report,
        "event_graph_or_input_modified": False,
    }


def move_ship(actors):
    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
    ships = [actor for actor in actors if actor.get_actor_label() == SHIP_LABEL]
    require(len(spawners) == 1 and len(starts) == 1 and len(ships) == 1,
            "Expected exactly one spawner, PlayerStart, and R12 ship")
    spawner, player_start, ship = spawners[0], starts[0], ships[0]
    center = spawner.get_actor_location()
    start = player_start.get_actor_location()
    radial_up = normalized(sub(start, center))
    forward = player_start.get_actor_forward_vector()
    tangent_x = sub(forward, mul(radial_up, dot(forward, radial_up)))
    if length(tangent_x) < 0.01:
        tangent_x = cross(unreal.Vector(0.0, 0.0, 1.0), radial_up)
    if length(tangent_x) < 0.01:
        tangent_x = cross(unreal.Vector(0.0, 1.0, 0.0), radial_up)
    tangent_x = normalized(tangent_x)
    tangent_y = normalized(cross(radial_up, tangent_x))
    capsules = list(player_start.get_components_by_class(unreal.CapsuleComponent))
    half_height = float(capsules[0].get_unscaled_capsule_half_height()) if len(capsules) == 1 else 0.0
    surface_radius = length(sub(start, center)) - half_height
    require(surface_radius > 1000000.0, "PlayerStart-derived radial shell invalid")
    direction = normalized(add(add(sub(start, center), mul(tangent_x, 1800.0)), mul(tangent_y, -300.0)))
    approximate_surface = add(center, mul(direction, surface_radius))
    mesh = unreal.EditorAssetLibrary.load_asset(SHIP_MESH)
    require(isinstance(mesh, unreal.StaticMesh), "StarSparrow mesh unavailable")
    bounds = mesh.get_bounding_box()
    scale = float(ship.get_actor_scale3d().x)
    require(0.05 <= scale <= 20.0, "Existing ship scale invalid")
    root_contact_offset = max(0.0, -float(bounds.min.z) * scale - 40.0)
    location = add(approximate_surface, mul(direction, root_contact_offset))
    rotation = unreal.MathLibrary.make_rot_from_xz(tangent_x, direction)
    before = {
        "location": vec(ship.get_actor_location()),
        "rotation": rot(ship.get_actor_rotation()),
        "scale": vec(ship.get_actor_scale3d()),
    }
    require(ship.set_actor_location(location, False, False) is not False, "Ship relocation failed")
    require(ship.set_actor_rotation(rotation, False) is not False, "Ship rotation failed")
    ship.set_actor_enable_collision(False)
    require(dot(ship.get_actor_up_vector(), direction) >= 0.995, "Ship radial-up readback failed")
    return {
        "before": before,
        "after": {
            "location": vec(ship.get_actor_location()),
            "rotation": rot(ship.get_actor_rotation()),
            "scale": vec(ship.get_actor_scale3d()),
        },
        "tangent_offset_cm": [1800.0, -300.0],
        "root_contact_offset_cm": root_contact_offset,
        "surface_basis": "PlayerStart radial shell; visual acceptance still required",
        "authoritative_surface_trace": False,
        "surface_contact_claimed": False,
        "visual_only": True,
        "collision": "disabled",
    }


def write_result(payload):
    os.makedirs(ROOT, exist_ok=True)
    with open(RESULT + ".tmp", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(RESULT + ".tmp", RESULT)


try:
    report = {
        "schema": "redmmo.ppg_character_ship.r12v2.build.v1",
        "status": "STARTED",
        "rollback": ROLLBACK,
        "project": unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path()),
        "current_map": unreal.EditorLevelLibrary.get_editor_world().get_path_name().split(".")[0],
    }
    require(os.path.isfile(ROLLBACK), "R12V2 rollback manifest missing")
    require(report["project"].replace("/", "\\").lower() ==
            os.path.join(PROJECT, "RedMMO.uproject").lower(), "Wrong project")
    require(report["current_map"] == MAP, "Wrong current map")
    for path, expected in EXPECTED.items():
        require(sha256(path) == expected, "R12 serialized input hash drift: " + path)
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint hash drift: " + path)
    report["provider_ports_closed"] = provider_gate()
    helper = load_helper()
    pawn = unreal.EditorAssetLibrary.load_asset(PAWN)
    require(isinstance(pawn, unreal.Blueprint), "R11 pawn Blueprint unavailable")
    report["camera"] = configure_camera(pawn, helper)
    actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
    report["ship"] = move_ship(actors)
    require(unreal.EditorLevelLibrary.save_current_level(), "Unable to save R12V2 home map")
    report["status"] = "PASS_SERIALIZED_PENDING_RELOAD_MAPCHECK_REAL_PIE_VISUAL"
    report["hashes"] = {
        "map": sha256(MAP_FILE),
        "pawn": sha256(PAWN_FILE),
        "ship_blueprint": sha256(SHIP_FILE),
    }
    report["protected_hashes"] = {path: sha256(path) for path in PROTECTED}
    write_result(report)
    with open(DONE, "w", encoding="utf-8") as handle:
        handle.write(report["status"] + "\n")
    unreal.log("REDMMO_R12V2_BUILD " + report["status"])
except Exception as error:
    failure = {
        "schema": "redmmo.ppg_character_ship.r12v2.build.v1",
        "status": "FAIL",
        "error": str(error),
        "traceback": traceback.format_exc(),
        "rollback": ROLLBACK,
    }
    write_result(failure)
    unreal.log_error("REDMMO_R12V2_BUILD FAIL " + str(error))

