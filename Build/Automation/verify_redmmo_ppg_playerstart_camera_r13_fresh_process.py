"""Fresh-process, no-save readback and MapCheck for R13 PlayerStart camera."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import socket
import time
import traceback
from datetime import datetime, timezone

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
GAME_MODE = "/Game/RedMMO/Gameplay/Player/GM_RedPlanet_R11"
SHIP_BP = "/Game/RedMMO/Gameplay/World/BP_RedParkedStarSparrow_R12"
SHIP_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
SHIP_MESH = "/Game/StarSparrow/Meshes/Examples/SM_StarSparrow01"
TARGET_ROTATION = {"pitch": 0.0, "yaw": -5.282777, "roll": 0.0}
EXPECTED = {
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap":
        "C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0",
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
HELPER = (
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_PPG_HomeStylizedRegion_R07_20260801_163147"
    r"\r07_character_ship_helpers.py"
)
HELPER_SHA = "4688EEDB30C1995AD67CEDE46884B652400B5463F2787E3D85EDA4378B269ECE"
ROOT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_PPG_PlayerStartCamera_R13FreshReadback_20260802"
)
RESULT = os.path.join(ROOT, "verify_redmmo_ppg_playerstart_camera_r13_result.json")


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def verify(records: dict[str, str], label: str) -> dict[str, str]:
    actual: dict[str, str] = {}
    for path, expected in records.items():
        require(os.path.isfile(path), f"{label} missing: {path}")
        actual[path] = sha256(path)
        require(actual[path] == expected, f"{label} hash drift: {path}")
    return actual


def asset_path(value) -> str | None:
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def dirty_packages() -> dict[str, list[str]]:
    return {
        "content": sorted(
            package.get_path_name()
            for package in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        ),
        "maps": sorted(
            package.get_path_name()
            for package in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        ),
    }


def provider_gate() -> dict[str, bool]:
    state: dict[str, bool] = {}
    for port in (5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            state[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(state.values()), f"Provider/MCP listener unexpectedly open: {state}")
    return state


def wrapped_angle_delta(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def rotation_record(value) -> dict[str, float]:
    return {
        "pitch": float(value.pitch),
        "yaw": float(value.yaw),
        "roll": float(value.roll),
    }


def rotation_matches(actual: dict[str, float], expected: dict[str, float]) -> bool:
    return all(
        wrapped_angle_delta(actual[key], expected[key]) <= 0.05
        for key in ("pitch", "yaw", "roll")
    )


def generation_record(spawner) -> dict[str, object]:
    method = getattr(spawner, "get_planet_generation_status", None)
    require(callable(method), "PPG generation status method unavailable")
    status = method()
    record = {
        "phase": str(status.get_editor_property("phase")),
        "progress": float(status.get_editor_property("progress")),
        "is_generating": bool(status.get_editor_property("is_generating")),
    }
    require(
        "COMPLETE" in record["phase"].upper()
        and record["progress"] >= 0.999
        and not record["is_generating"],
        f"PPG is not COMPLETE and idle: {record}",
    )
    return record


def load_helper():
    require(os.path.isfile(HELPER) and sha256(HELPER) == HELPER_SHA, "R12 helper drift")
    spec = importlib.util.spec_from_file_location("redmmo_r13_readback_helper", HELPER)
    require(spec is not None and spec.loader is not None, "R12 helper unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unique_component(blueprint, helper, component_class, variable):
    matches = {}
    for record in helper._subobject_records(blueprint):
        component = record["object_for_blueprint"]
        if record["variable"] == variable and isinstance(component, component_class):
            matches[id(record["associated"] or component)] = component
    require(len(matches) == 1, f"Serialized {variable} component is ambiguous")
    return next(iter(matches.values()))


def command_log() -> str:
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    return (
        (match.group(1) or match.group(2))
        if match
        else r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Saved\Logs\RedMMO.log"
    )


def map_check(world) -> dict[str, object]:
    log_path = command_log()
    require(os.path.isfile(log_path), f"Fresh-process log missing: {log_path}")
    offset = os.path.getsize(log_path)
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECKDEP NOCLEARLOG")
    pattern = re.compile(
        r"MapCheck: Map check complete: (\d+) Error\(s\), (\d+) Warning\(s\)"
    )
    matches: list[tuple[str, str]] = []
    fresh_text = ""
    for _ in range(120):
        time.sleep(0.1)
        with open(log_path, "rb") as handle:
            handle.seek(min(offset, os.path.getsize(log_path)))
            fresh_text = handle.read().decode("utf-8", errors="replace")
        matches = pattern.findall(fresh_text)
        if matches:
            break
    require(matches, "No fresh authoritative MapCheck completion marker")
    errors, warnings = (int(value) for value in matches[-1])
    require(errors == 0 and warnings == 0, f"MapCheck failed: {errors}/{warnings}")
    marker = f"MapCheck: Map check complete: {errors} Error(s), {warnings} Warning(s)"
    return {
        "errors": errors,
        "warnings": warnings,
        "marker": marker,
        "log": log_path,
        "fresh_log_offset": offset,
    }


def main() -> dict[str, object]:
    require(not os.path.exists(RESULT), "R13 fresh-readback result no-clobber failed")
    project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    require(unreal.Paths.is_same_path(project, PROJECT), f"Wrong project: {project}")
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    require(level is not None and not level.is_in_play_in_editor(), "PIE is active")
    world = unreal.EditorLevelLibrary.get_editor_world()
    require(world is not None, "Editor world unavailable")
    world_path = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
    require(world_path == MAP, f"OS launch did not open the required map: {world_path}")
    require(dirty_packages() == {"content": [], "maps": []}, "Fresh editor is dirty")
    invariants = verify(EXPECTED, "R13 invariant")
    protected = verify(PROTECTED, "protected checkpoint")
    providers = provider_gate()

    actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
    starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
    require(len(starts) == 1, f"Expected one PlayerStart, found {len(starts)}")
    start_rotation = rotation_record(starts[0].get_actor_rotation())
    require(rotation_matches(start_rotation, TARGET_ROTATION), f"R13 rotation drift: {start_rotation}")

    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    require(len(spawners) == 1, f"Expected one PlanetSpawnerBP_C, found {len(spawners)}")
    generation = generation_record(spawners[0])

    ships = [actor for actor in actors if asset_path(actor.get_class()) == SHIP_BP]
    require(len(ships) == 1, f"Expected one R12 ship, found {len(ships)}")
    ship = ships[0]
    require(ship.get_actor_label() == SHIP_LABEL, f"R12 ship label drift: {ship.get_actor_label()}")
    require(not ship.get_actor_enable_collision(), "R12 visual ship collision is enabled")
    ship_meshes = [
        component
        for component in ship.get_components_by_class(unreal.StaticMeshComponent)
        if component.get_editor_property("static_mesh") is not None
    ]
    require(len(ship_meshes) == 1, f"Expected one populated ship mesh, found {len(ship_meshes)}")
    require(
        asset_path(ship_meshes[0].get_editor_property("static_mesh")) == SHIP_MESH,
        "R12 ship mesh drift",
    )

    helper = load_helper()
    pawn = unreal.EditorAssetLibrary.load_asset(PAWN)
    game_mode = unreal.EditorAssetLibrary.load_asset(GAME_MODE)
    require(isinstance(pawn, unreal.Blueprint), "R11 pawn Blueprint unavailable")
    require(isinstance(game_mode, unreal.Blueprint), "R11 GameMode Blueprint unavailable")
    root = unique_component(pawn, helper, unreal.CapsuleComponent, "CapsuleComponent")
    arm = unique_component(pawn, helper, unreal.SpringArmComponent, "SpringArm")
    camera = unique_component(pawn, helper, unreal.CameraComponent, "Camera")
    require(arm.get_attach_parent() == root, "R11 SpringArm parent drift")
    require(camera.get_attach_parent() == arm, "R11 Camera parent drift")
    require(str(camera.get_attach_socket_name()) == "SpringEndpoint", "R11 camera socket drift")
    require(math.isclose(float(arm.get_editor_property("target_arm_length")), 400.0, abs_tol=0.001),
            "R11 arm length drift")
    require(math.isclose(float(camera.get_editor_property("field_of_view")), 90.0, abs_tol=0.001),
            "R11 camera FOV drift")
    world_game_mode = world.get_world_settings().get_editor_property("default_game_mode")
    require(asset_path(world_game_mode) == GAME_MODE, "Home map GameMode drift")
    game_mode_cdo = unreal.get_default_object(game_mode.generated_class())
    require(asset_path(game_mode_cdo.get_editor_property("default_pawn_class")) == PAWN,
            "R11 GameMode default pawn drift")

    check = map_check(world)
    require(dirty_packages() == {"content": [], "maps": []}, "MapCheck dirtied packages")
    require(verify(EXPECTED, "R13 invariant after MapCheck") == invariants,
            "R13 invariant set changed during verification")
    require(verify(PROTECTED, "protected checkpoint after MapCheck") == protected,
            "Protected checkpoint set changed during verification")
    return {
        "schema": "redmmo.ppg_playerstart_camera.r13.fresh_readback_mapcheck.v1",
        "status": "PASS_FRESH_PROCESS_SERIALIZED_READBACK_MAPCHECK_0_ERRORS_0_WARNINGS_PENDING_REAL_PIE",
        "started_from_os_map_argument": True,
        "map_loaded_by_script": False,
        "project": PROJECT,
        "map": MAP,
        "map_sha256": EXPECTED[next(iter(EXPECTED))],
        "playerstart": {"actor": starts[0].get_path_name(), "rotation": start_rotation},
        "ppg_generation": generation,
        "ship": {
            "actor": ship.get_path_name(),
            "label": SHIP_LABEL,
            "mesh": SHIP_MESH,
            "collision": "disabled",
        },
        "r11_camera": {
            "spring_arm_parent": root.get_path_name(),
            "camera_parent": arm.get_path_name(),
            "camera_socket": "SpringEndpoint",
            "target_arm_length": float(arm.get_editor_property("target_arm_length")),
            "field_of_view": float(camera.get_editor_property("field_of_view")),
            "game_mode": GAME_MODE,
            "default_pawn": PAWN,
        },
        "provider_ports_closed": providers,
        "dirty_packages": {"content": [], "maps": []},
        "map_check": check,
        "verified_invariants": invariants,
        "protected_hashes": protected,
        "map_saved_by_verifier": False,
        "evidence_class": "automation_fresh_process_serialized_readback_mapcheck",
        "completed_utc": now(),
    }


payload = {
    "schema": "redmmo.ppg_playerstart_camera.r13.fresh_readback_mapcheck.v1",
    "status": "FAIL",
    "map_saved_by_verifier": False,
    "completed_utc": now(),
}
try:
    payload = main()
except Exception as error:
    payload.update({"error": str(error), "traceback": traceback.format_exc()})

os.makedirs(ROOT, exist_ok=True)
with open(RESULT, "xb") as handle:
    handle.write((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    handle.flush()
    os.fsync(handle.fileno())
if payload["status"].startswith("PASS"):
    unreal.log("REDMMO_R13_FRESH_READBACK_MAPCHECK PASS")
else:
    unreal.log_error("REDMMO_R13_FRESH_READBACK_MAPCHECK FAIL " + payload.get("error", ""))
