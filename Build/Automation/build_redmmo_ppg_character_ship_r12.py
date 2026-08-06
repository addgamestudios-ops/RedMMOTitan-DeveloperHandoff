"""Build the bounded R12 visible-player and parked-ship slice in clean RedMMO.

This script deliberately preserves the successful R11 GameMode, pawn logic,
input, PPG generation, terrain, water, and seed.  It changes only the R11
pawn's visual mesh/AnimBP, creates one project-owned no-collision ship visual,
and places one labelled ship reference near PlayerStart.  The placement is a
PlayerStart-derived radial approximation and must pass the later real-GPU
contact review before it is described as grounded.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import socket
import time
import traceback

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
PAWN_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset"
SHIP_BP = "/Game/RedMMO/Gameplay/World/BP_RedParkedStarSparrow_R12"
SHIP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset"
SHIP_MESH = "/Game/StarSparrow/Meshes/Examples/SM_StarSparrow01"
SHIP_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
SHIP_FOLDER = "Red/Gameplay/R12/ShipReference"

EXPECTED_MAP_SHA = "3F98136280504222E5340DB7044F0F3564E8BFFD7221C4EC2F2DF655CE2FFAEC"
EXPECTED_PAWN_SHA = "B86B12ACF5CFB9A8DBC82650F56D815B0C6BE8BC32A099A510C5A085158931E6"
EXPECTED_PARTIAL_MANNEQUIN_PAWN_SHA = "E8B0712C9A57EA162180E8648C7BDCA5D95B58A9D71593F0495713DD492C7852"
HELPER_FILE = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomeStylizedRegion_R07_20260801_163147"
    r"\r07_character_ship_helpers.py"
)
EXPECTED_HELPER_SHA = "4688EEDB30C1995AD67CEDE46884B652400B5463F2787E3D85EDA4378B269ECE"
ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12_20260802"
RESULT = os.path.join(ROOT, "build_redmmo_ppg_character_ship_r12_result.json")
DONE = os.path.join(ROOT, "build_redmmo_ppg_character_ship_r12.done")
PROVIDER_PORTS = (5353, 8000, 8765)

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


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path: str, value: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary, path)


def vec(value) -> list[float]:
    return [float(value.x), float(value.y), float(value.z)]


def rot(value) -> list[float]:
    return [float(value.pitch), float(value.yaw), float(value.roll)]


def add(a, b):
    return unreal.Vector(a.x + b.x, a.y + b.y, a.z + b.z)


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def mul(value, scalar: float):
    return unreal.Vector(value.x * scalar, value.y * scalar, value.z * scalar)


def dot(a, b) -> float:
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def cross(a, b):
    return unreal.Vector(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def length(value) -> float:
    return math.sqrt(dot(value, value))


def normalized(value):
    magnitude = length(value)
    require(magnitude > 1.0e-6, "Cannot normalize zero vector")
    return mul(value, 1.0 / magnitude)


def provider_gate() -> dict[str, bool]:
    result = {}
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(result.values()), "AI/MCP/provider listener is active")
    return result


def dirty_packages() -> list[str]:
    packages = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    packages += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({package.get_path_name() for package in packages})


def load_helper():
    require(sha256(HELPER_FILE) == EXPECTED_HELPER_SHA, "Reviewed R07 helper hash drift")
    spec = importlib.util.spec_from_file_location("redmmo_r12_character_ship_helpers", HELPER_FILE)
    require(spec is not None and spec.loader is not None, "Unable to load reviewed R07 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TARGET_PAWN = PAWN
    module.TARGET_VISUAL_SHIP = SHIP_BP
    module.SHIP_LABEL = SHIP_LABEL
    module.SHIP_FOLDER = SHIP_FOLDER

    def split_r12(path: str):
        require(path == SHIP_BP, "R12 helper attempted an unexpected target: " + path)
        return path.rsplit("/", 1)

    module._split_asset_path = split_r12
    return module


def create_ship_blueprint(helper):
    """Create the R12 visual ship using UE 5.8 reflected properties."""
    require(not unreal.EditorAssetLibrary.does_asset_exist(SHIP_BP),
            "R12 ship Blueprint already exists")
    closure = helper.verify_asset_dependency_closure(SHIP_MESH)
    mesh = unreal.EditorAssetLibrary.load_asset(SHIP_MESH)
    require(isinstance(mesh, unreal.StaticMesh), "StarSparrow mesh failed to load")
    folder, name = SHIP_BP.rsplit("/", 1)
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", unreal.Actor.static_class())
    bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.Blueprint.static_class(), factory
    )
    require(isinstance(bp, unreal.Blueprint), "Unable to create R12 ship Blueprint")
    try:
        component = helper._add_blueprint_component(bp, unreal.StaticMeshComponent, "ShipVisual")
        require(component.set_static_mesh(mesh), "Unable to assign StarSparrow mesh")
        component.set_collision_profile_name(unreal.Name("NoCollision"))
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        component.set_editor_property("generate_overlap_events", False)
        component.set_editor_property("cast_shadow", True)
        component.set_editor_property("relative_location", unreal.Vector(0.0, 0.0, 0.0))
        component.set_editor_property("relative_rotation", unreal.Rotator(0.0, 0.0, 0.0))
        component.set_editor_property("relative_scale3d", unreal.Vector(1.0, 1.0, 1.0))
        compile_report = helper._compile_blueprint(bp)
        helper._save_asset(bp)
        return bp, {
            "blueprint": SHIP_BP,
            "mesh": SHIP_MESH,
            "component": "ShipVisual",
            "collision": "NO_COLLISION",
            "generate_overlap_events": False,
            "visual_only": True,
            "dependency_closure": closure,
            "compile": compile_report,
        }
    except Exception:
        if unreal.EditorAssetLibrary.does_asset_exist(SHIP_BP):
            unreal.EditorAssetLibrary.delete_asset(SHIP_BP)
        raise


def main() -> dict:
    started = time.time()
    report = {
        "schema": "redmmo.ppg_character_ship.r12.build.v1",
        "status": "RUNNING",
        "project": PROJECT,
        "map": MAP,
        "map_saved": False,
        "evidence_class": "serialized_editor_mutation_pending_reload_runtime_visual",
        "rollback": r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_CharacterShip_R12_20260802_175054\pre_r12_manifest.json",
    }
    require(not os.path.exists(RESULT) and not os.path.exists(DONE), "R12 build no-clobber failed")
    actual_project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    require(unreal.Paths.is_same_path(actual_project, PROJECT), "Wrong project: " + actual_project)
    subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    require(not subsystem.is_in_play_in_editor(), "R12 build refused while PIE is active")
    world = unreal.EditorLevelLibrary.get_editor_world()
    current_map = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
    require(current_map == MAP, "Wrong map: " + current_map)
    require(not dirty_packages(), "Dirty packages before R12 build: " + str(dirty_packages()))
    require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "R12 home-map prehash drift")
    pawn_prehash = sha256(PAWN_FILE)
    require(
        pawn_prehash in (EXPECTED_PAWN_SHA, EXPECTED_PARTIAL_MANNEQUIN_PAWN_SHA),
        "R12 pawn prehash drift",
    )
    report["resumed_after_safe_partial_mannequin_save"] = (
        pawn_prehash == EXPECTED_PARTIAL_MANNEQUIN_PAWN_SHA
    )
    require(not os.path.exists(SHIP_FILE), "R12 target ship Blueprint already exists")
    report["provider_ports_closed"] = provider_gate()
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint hash drift: " + path)

    actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
    require(len(spawners) == 1 and len(starts) == 1, "Expected one PPG spawner and one PlayerStart")
    require(not [actor for actor in actors if actor.get_actor_label() == SHIP_LABEL],
            "R12 parked ship label already exists")
    spawner = spawners[0]
    player_start = starts[0]

    helper = load_helper()
    pawn = unreal.EditorAssetLibrary.load_asset(PAWN)
    require(isinstance(pawn, unreal.Blueprint), "R11 pawn failed to load")
    report["visible_character"] = helper.configure_visible_mannequin(pawn)
    ship_bp, report["ship_blueprint"] = create_ship_blueprint(helper)

    center = spawner.get_actor_location()
    start_location = player_start.get_actor_location()
    radial_up = normalized(sub(start_location, center))
    forward = player_start.get_actor_forward_vector()
    tangent_x = sub(forward, mul(radial_up, dot(forward, radial_up)))
    if length(tangent_x) < 0.01:
        tangent_x = cross(unreal.Vector(0.0, 0.0, 1.0), radial_up)
    if length(tangent_x) < 0.01:
        tangent_x = cross(unreal.Vector(0.0, 1.0, 0.0), radial_up)
    tangent_x = normalized(tangent_x)
    tangent_y = normalized(cross(radial_up, tangent_x))
    capsules = list(player_start.get_components_by_class(unreal.CapsuleComponent))
    player_start_half_height = 0.0
    if len(capsules) == 1:
        player_start_half_height = float(capsules[0].get_unscaled_capsule_half_height())
    start_radius = length(sub(start_location, center))
    surface_radius = start_radius - player_start_half_height
    require(surface_radius > 1000000.0, "PlayerStart-derived radial surface is invalid")
    approximate_direction = normalized(add(
        add(sub(start_location, center), mul(tangent_x, 4200.0)),
        mul(tangent_y, -1400.0),
    ))
    approximate_surface = add(center, mul(approximate_direction, surface_radius))

    ship_mesh = unreal.EditorAssetLibrary.load_asset(SHIP_MESH)
    require(isinstance(ship_mesh, unreal.StaticMesh), "StarSparrow mesh failed to load")
    box = ship_mesh.get_bounding_box()
    dimensions = (
        float(box.max.x - box.min.x),
        float(box.max.y - box.min.y),
        float(box.max.z - box.min.z),
    )
    maximum_dimension = max(dimensions)
    require(maximum_dimension > 1.0, "StarSparrow bounds are invalid")
    target_max_dimension_cm = 3000.0
    ship_scale = target_max_dimension_cm / maximum_dimension
    require(0.05 <= ship_scale <= 20.0, "Unsafe StarSparrow scale")
    root_contact_offset = max(0.0, -float(box.min.z) * ship_scale - 25.0)
    ship_location = add(approximate_surface, mul(approximate_direction, root_contact_offset))
    ship_rotation = unreal.MathLibrary.make_rot_from_xz(tangent_x, approximate_direction)

    ship_class = ship_bp.generated_class()
    require(ship_class is not None, "R12 ship generated class unavailable")
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    ship_actor = actor_subsystem.spawn_actor_from_class(ship_class, ship_location, ship_rotation)
    require(ship_actor is not None, "Unable to spawn the R12 parked ship")
    ship_actor.set_actor_label(SHIP_LABEL)
    ship_actor.set_folder_path(SHIP_FOLDER)
    ship_actor.set_actor_scale3d(unreal.Vector(ship_scale, ship_scale, ship_scale))
    ship_actor.set_actor_enable_collision(False)
    ship_actor.set_editor_property("tags", [
        unreal.Name("RedMMO"), unreal.Name("R12"), unreal.Name("ParkedShipReference"),
        unreal.Name("VisualOnlyNoFlight"), unreal.Name("NoCollision"),
    ])
    actual_up = ship_actor.get_actor_up_vector()
    require(dot(actual_up, approximate_direction) >= 0.995, "R12 ship radial-up alignment failed")
    report["ship_placement"] = {
        "actor": ship_actor.get_path_name(),
        "label": SHIP_LABEL,
        "folder": SHIP_FOLDER,
        "location": vec(ship_actor.get_actor_location()),
        "rotation": rot(ship_actor.get_actor_rotation()),
        "scale": vec(ship_actor.get_actor_scale3d()),
        "mesh_dimensions_cm_unscaled": list(dimensions),
        "target_max_dimension_cm": target_max_dimension_cm,
        "player_start": vec(start_location),
        "player_start_capsule_half_height_cm": player_start_half_height,
        "planet_center": vec(center),
        "approximate_surface_point": vec(approximate_surface),
        "placement_basis": "PlayerStart radial shell plus bounded tangent offset",
        "authoritative_surface_trace": False,
        "surface_contact_claimed": False,
        "requires_real_gpu_contact_review": True,
        "visual_only": True,
        "collision": "disabled",
        "flight_boarding_or_travel_claimed": False,
    }

    require(unreal.EditorLevelLibrary.save_current_level(), "Unable to save R12 home map")
    report["map_saved"] = True
    require(os.path.isfile(SHIP_FILE), "Saved R12 ship Blueprint file missing")
    require(sha256(MAP_FILE) != EXPECTED_MAP_SHA, "R12 home map hash did not change")
    require(sha256(PAWN_FILE) != EXPECTED_PAWN_SHA, "R12 pawn hash did not change")
    require(not dirty_packages(), "Dirty packages after R12 save: " + str(dirty_packages()))
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint changed during R12 build: " + path)
    report.update({
        "status": "PASS_SERIALIZED_PENDING_RELOAD_MAPCHECK_REAL_PIE_VISUAL",
        "home_map_sha256_before": EXPECTED_MAP_SHA,
        "home_map_sha256_after": sha256(MAP_FILE),
        "pawn_sha256_before": EXPECTED_PAWN_SHA,
        "pawn_sha256_after": sha256(PAWN_FILE),
        "ship_blueprint_sha256": sha256(SHIP_FILE),
        "protected_hashes_unchanged": True,
        "source_packages_modified": False,
        "elapsed_seconds": time.time() - started,
    })
    return report


try:
    _result = main()
    atomic_json(RESULT, _result)
    with open(DONE, "w", encoding="utf-8") as _handle:
        _handle.write(_result["status"] + "\n")
    unreal.log("REDMMO_R12_CHARACTER_SHIP_BUILD PASS")
except Exception as _error:
    _failure = {
        "schema": "redmmo.ppg_character_ship.r12.build.v1",
        "status": "FAIL",
        "error": str(_error),
        "traceback": traceback.format_exc(),
        "map_saved": False,
        "rollback": r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_CharacterShip_R12_20260802_175054\pre_r12_manifest.json",
    }
    atomic_json(RESULT, _failure)
    with open(DONE, "w", encoding="utf-8") as _handle:
        _handle.write("FAIL: " + str(_error) + "\n")
    unreal.log_error("REDMMO_R12_CHARACTER_SHIP_BUILD FAIL " + str(_error))
