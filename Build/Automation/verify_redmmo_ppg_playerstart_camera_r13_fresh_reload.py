"""Fresh-process serialized readback and MapCheck for persisted R13 camera seed.

The outer launcher must open RedMMO_PPG_HomeWorld directly. This verifier never
loads, edits, saves, or reloads a map.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import socket
import time
import traceback

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_MAP = "C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0"
EXPECTED_GAME_MODE = "/Game/RedMMO/Gameplay/Player/GM_RedPlanet_R11.GM_RedPlanet_R11_C"
PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
SHIP_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
SHIP_MESH = "/Game/StarSparrow/Meshes/Examples/SM_StarSparrow01"
TARGET = {"pitch": 0.0, "yaw": -5.282777, "roll": 0.0}
HELPER = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomeStylizedRegion_R07_20260801_163147"
    r"\r07_character_ship_helpers.py"
)
HELPER_SHA = "4688EEDB30C1995AD67CEDE46884B652400B5463F2787E3D85EDA4378B269ECE"
ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_PlayerStartCamera_R13FreshReload_20260802"
RESULT = os.path.join(ROOT, "verify_redmmo_ppg_playerstart_camera_r13_fresh_reload_result.json")
EXPECTED_FILES = {
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset":
        "65A0413D1921F8ED2F6E4E3893B1C6B5CA3A0D1F7BCFC9AF9BF987940ECDC11E",
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\GM_RedPlanet_R11.uasset":
        "0696DE6039A5389BF0F872DB84D970E981C69184CD3AEA0279D89001B98BBEBD",
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Input\IMC_RedPlanet_R11.uasset":
        "09AC8B9CAB42342C49A22BC6CC1B4A1770B9FB56CE1E251A8E0B0C50581E1DC6",
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset":
        "C9FDCF7D0FE89DACE39D418B79A7951C37C699C1FEA7E485C85670B2AB864BD6",
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


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value):
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    if "." in leaf:
        path = path.rsplit(".", 1)[0]
    return path[:-2] if path.endswith("_C") else path


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({value.get_path_name() for value in values})


def verify_hashes(records, label):
    actual = {}
    for path, expected in records.items():
        require(os.path.isfile(path), f"{label} missing: {path}")
        actual[path] = sha256(path)
        require(actual[path] == expected, f"{label} drift: {path}")
    return actual


def provider_gate():
    state = {}
    for port in (5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            state[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(state.values()), "Provider/MCP listener unexpectedly open")
    return state


def command_log():
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    require(match, "Dedicated -abslog argument missing")
    return match.group(1) or match.group(2)


def map_check(world):
    path = command_log()
    require(os.path.isfile(path), "MapCheck log missing")
    offset = os.path.getsize(path)
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECKDEP NOCLEARLOG")
    pattern = re.compile(r"MapCheck: Map check complete: (\d+) Error\(s\), (\d+) Warning\(s\)")
    matches = []
    for _ in range(120):
        time.sleep(0.1)
        with open(path, "rb") as handle:
            handle.seek(min(offset, os.path.getsize(path)))
            matches = pattern.findall(handle.read().decode("utf-8", errors="replace"))
        if matches:
            break
    require(matches, "No fresh MapCheck completion marker")
    errors, warnings = (int(value) for value in matches[-1])
    require(errors == 0 and warnings == 0, f"MapCheck failed: {errors}/{warnings}")
    return {"errors": errors, "warnings": warnings, "log": path}


def load_helper():
    require(os.path.isfile(HELPER), "R07 helper missing")
    require(sha256(HELPER) == HELPER_SHA, "R07 helper hash drift")
    spec = importlib.util.spec_from_file_location("redmmo_r13_fresh_helper", HELPER)
    require(spec is not None and spec.loader is not None, "R07 helper unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unique_component(bp, helper, component_class, variable):
    matches = {}
    for record in helper._subobject_records(bp):
        component = record["object_for_blueprint"]
        if record["variable"] == variable and isinstance(component, component_class):
            matches[id(record["associated"] or component)] = component
    require(len(matches) == 1, f"Serialized {variable} component is ambiguous")
    return next(iter(matches.values()))


def main():
    require(not os.path.exists(RESULT), "R13 fresh verifier no-clobber failed")
    project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    require(unreal.Paths.is_same_path(project, PROJECT), "Wrong project")
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    require(not level.is_in_play_in_editor(), "PIE is active")
    require(not dirty_packages(), f"Fresh verifier started dirty: {dirty_packages()}")
    require(sha256(MAP_FILE) == EXPECTED_MAP, "Persisted home-map hash drift")
    invariants = verify_hashes(EXPECTED_FILES, "R13 invariant")
    protected = verify_hashes(PROTECTED, "protected checkpoint")
    ports = provider_gate()

    world = unreal.EditorLevelLibrary.get_editor_world()
    world_path = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
    require(world_path == MAP, f"Wrong startup map: {world_path}")
    game_mode = world.get_world_settings().get_editor_property("default_game_mode")
    require(game_mode.get_path_name() == EXPECTED_GAME_MODE, f"Wrong GameMode: {game_mode}")
    actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
    starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    ships = [actor for actor in actors if actor.get_actor_label() == SHIP_LABEL]
    require(len(starts) == len(spawners) == len(ships) == 1, "Expected one PlayerStart/spawner/ship")
    rotation = starts[0].get_actor_rotation()
    actual_rotation = {
        "pitch": float(rotation.pitch), "yaw": float(rotation.yaw), "roll": float(rotation.roll)
    }
    require(all(abs(actual_rotation[key] - TARGET[key]) <= 0.001 for key in TARGET),
            f"Persisted PlayerStart rotation drift: {actual_rotation}")
    status = spawners[0].get_planet_generation_status()
    generation = {
        "phase": str(status.get_editor_property("phase")),
        "progress": float(status.get_editor_property("progress")),
        "is_generating": bool(status.get_editor_property("is_generating")),
    }
    require("COMPLETE" in generation["phase"].upper()
            and generation["progress"] >= 0.999 and not generation["is_generating"],
            f"PPG not ready: {generation}")

    ship = ships[0]
    mesh_components = [component for component in ship.get_components_by_class(unreal.StaticMeshComponent)
                       if component.get_editor_property("static_mesh") is not None]
    require(len(mesh_components) == 1, "Ship mesh component count is not one")
    require(asset_path(mesh_components[0].get_editor_property("static_mesh")) == SHIP_MESH,
            "Ship mesh binding drift")
    require(not ship.get_actor_enable_collision(), "Visual-only ship collision is enabled")

    helper = load_helper()
    pawn = unreal.EditorAssetLibrary.load_asset(PAWN)
    require(isinstance(pawn, unreal.Blueprint), "R11 pawn unavailable")
    root = unique_component(pawn, helper, unreal.CapsuleComponent, "CapsuleComponent")
    arm = unique_component(pawn, helper, unreal.SpringArmComponent, "SpringArm")
    camera = unique_component(pawn, helper, unreal.CameraComponent, "Camera")
    require(arm.get_attach_parent() == root, "SpringArm parent drift")
    require(camera.get_attach_parent() == arm, "Camera parent drift")
    require(str(camera.get_attach_socket_name()) == "SpringEndpoint", "Camera socket drift")
    require(abs(float(arm.get_editor_property("target_arm_length")) - 400.0) <= 0.001,
            "SpringArm length drift")
    require(abs(float(camera.get_editor_property("field_of_view")) - 90.0) <= 0.001,
            "Camera FOV drift")

    check = map_check(world)
    require(not dirty_packages(), f"MapCheck dirtied packages: {dirty_packages()}")
    require(sha256(MAP_FILE) == EXPECTED_MAP, "Fresh verifier changed home map")
    require(verify_hashes(EXPECTED_FILES, "R13 invariant after MapCheck") == invariants,
            "Invariant set changed")
    require(verify_hashes(PROTECTED, "protected checkpoint after MapCheck") == protected,
            "Protected set changed")
    return {
        "schema": "redmmo.ppg_playerstart_camera.r13.fresh_reload_mapcheck.v1",
        "status": "PASS_FRESH_PROCESS_SERIALIZED_READBACK_MAPCHECK_PENDING_REAL_D3D12_PIE",
        "map": MAP,
        "map_sha256": EXPECTED_MAP,
        "playerstart_rotation": actual_rotation,
        "generation": generation,
        "camera": {"target_arm_length": 400.0, "field_of_view": 90.0},
        "ship": {"mesh": SHIP_MESH, "collision": "disabled", "visual_only": True},
        "map_check": check,
        "provider_ports_closed": ports,
        "dirty_packages": [],
        "map_loaded_by_script": False,
        "map_saved_by_script": False,
    }


try:
    payload = main()
except Exception as error:
    payload = {
        "schema": "redmmo.ppg_playerstart_camera.r13.fresh_reload_mapcheck.v1",
        "status": "FAIL",
        "error": str(error),
        "traceback": traceback.format_exc(),
        "map_loaded_by_script": False,
        "map_saved_by_script": False,
    }
os.makedirs(ROOT, exist_ok=True)
with open(RESULT, "xb") as handle:
    handle.write((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    handle.flush()
    os.fsync(handle.fileno())
if payload["status"].startswith("PASS"):
    unreal.log("REDMMO_R13_FRESH_RELOAD_MAPCHECK PASS")
else:
    unreal.log_error("REDMMO_R13_FRESH_RELOAD_MAPCHECK FAIL " + payload.get("error", ""))
