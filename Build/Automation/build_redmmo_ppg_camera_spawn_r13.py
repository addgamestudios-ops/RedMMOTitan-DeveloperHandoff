"""Build the versioned R13 gravity-relative third-person spawn-camera fix.

The successful R11 flight pawn and GameMode remain intact.  This script
duplicates them, adds one DoOnce camera initializer after PPG establishes the
movement component's gravity direction, compiles both new assets, and only then
switches the clean RedMMO home map to the R13 GameMode.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import time
import traceback

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
SOURCE_PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
SOURCE_PAWN_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset"
SOURCE_GAME_MODE = "/Game/RedMMO/Gameplay/Player/GM_RedPlanet_R11"
SOURCE_GAME_MODE_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\GM_RedPlanet_R11.uasset"
TARGET_PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R13"
TARGET_GAME_MODE = "/Game/RedMMO/Gameplay/Player/GM_RedPlanet_R13"
TARGET_PAWN_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R13.uasset"
TARGET_GAME_MODE_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\GM_RedPlanet_R13.uasset"
SHIP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset"

EXPECTED = {
    MAP_FILE: "0A7252E93F6F75FA7FAFAD856C7249E6964C27E34B9DD1386202080E2FD2D6CF",
    SOURCE_PAWN_FILE: "65A0413D1921F8ED2F6E4E3893B1C6B5CA3A0D1F7BCFC9AF9BF987940ECDC11E",
    SOURCE_GAME_MODE_FILE: "0696DE6039A5389BF0F872DB84D970E981C69184CD3AEA0279D89001B98BBEBD",
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

ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R13_20260802"
RESULT = os.path.join(ROOT, "build_redmmo_ppg_camera_spawn_r13_result.json")
ROLLBACK = r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_CameraSpawn_R13_20260802_220000"
ROLLBACK_MANIFEST = os.path.join(ROLLBACK, "pre_r13_manifest.json")
PROVIDER_PORTS = (5353, 8000, 8765)


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path: str, value) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary, path)


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


def dirty_packages() -> dict[str, list[str]]:
    return {
        "content": sorted({value.get_path_name() for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}),
        "maps": sorted({value.get_path_name() for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}),
    }


def asset_path(value) -> str:
    return value.get_path_name().split(".", 1)[0]


def load(path: str, kind: str):
    value = unreal.load_asset(path)
    require(value is not None, f"Missing {kind}: {path}")
    return value


def duplicate(source: str, target: str, kind: str):
    require(not unreal.EditorAssetLibrary.does_asset_exist(target), f"No-clobber target exists: {target}")
    value = unreal.EditorAssetLibrary.duplicate_asset(source, target)
    require(value is not None, f"Unable to duplicate {kind}: {source} -> {target}")
    require(asset_path(value) == target, f"Duplicate path mismatch: {value.get_path_name()}")
    return value


def pin(node, name: str, direction):
    matches = [
        value for value in list(node.list_all_pins())
        if str(value.get_pin_name()).lower().replace(" ", "") == name.lower().replace(" ", "")
        and value.get_pin_direction() == direction
    ]
    require(len(matches) == 1, f"Ambiguous pin {name} on {node.get_node_title()}: {len(matches)}")
    return matches[0]


def nodes(editor, title: str):
    return [value for value in list(editor.list_all_nodes()) if str(value.get_node_title()) == title]


def compile_blueprint(blueprint) -> dict:
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    status = blueprint.get_editor_property("status")
    accepted = {
        unreal.BlueprintStatus.BS_UP_TO_DATE,
        unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS,
    }
    require(status in accepted, f"Blueprint compile failed: {blueprint.get_path_name()} status={status}")
    errors = []
    warnings = []
    for graph in list(unreal.BlueprintEditorLibrary.list_graphs(blueprint)):
        editor = unreal.BlueprintGraphEditor.get_graph_editor(graph)
        require(editor is not None, f"No graph editor: {graph.get_path_name()}")
        errors.extend(f"{graph.get_name()}::{node.get_node_title()}" for node in editor.list_nodes_with_errors())
        warnings.extend(f"{graph.get_name()}::{node.get_node_title()}" for node in editor.list_nodes_with_warnings())
    require(not errors, f"Blueprint graph errors: {errors}")
    return {"asset": asset_path(blueprint), "status": str(status), "warnings": warnings}


def save_asset(asset) -> None:
    require(unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False),
            f"Unable to save {asset.get_path_name()}")


def backup() -> dict:
    require(not os.path.exists(ROLLBACK), f"Rollback target already exists: {ROLLBACK}")
    os.makedirs(ROLLBACK)
    records = []
    for source, expected in EXPECTED.items():
        require(sha256(source) == expected, f"Pre-R13 hash drift: {source}")
        target = os.path.join(ROLLBACK, os.path.basename(source))
        shutil.copy2(source, target)
        require(sha256(target) == expected, f"Rollback copy mismatch: {target}")
        records.append({"source": source, "backup": target, "sha256": expected})
    payload = {
        "schema": "redmmo.ppg_camera_spawn.r13.rollback.v1",
        "project": PROJECT,
        "map": MAP,
        "records": records,
        "protected": PROTECTED,
        "restoration": "Close Unreal; copy the named backup over its exact source path; remove only the new R13 pawn/GameMode packages.",
    }
    atomic_json(ROLLBACK_MANIFEST, payload)
    return payload


def add_camera_initializer(pawn) -> dict:
    editor = unreal.BlueprintGraphEditor.get_graph_editor_by_name(pawn, unreal.Name("EventGraph"))
    require(editor is not None, "Duplicated pawn EventGraph is unavailable")

    gravity_sets = nodes(editor, "SetGravityDirection")
    controllers = nodes(editor, "GetController")
    movements = nodes(editor, "Get CharacterMovement")
    require(len(gravity_sets) == 1, f"Expected one SetGravityDirection, found {len(gravity_sets)}")
    require(len(controllers) == 1, f"Expected one GetController, found {len(controllers)}")
    require(movements, "No inherited CharacterMovement getter exists")

    do_once = editor.create_node_from_name(
        "Utilities|FlowControl|DoOnce", unreal.Vector2D(1200.0, -1400.0), []
    )
    require(do_once is not None, "Unable to create R13 DoOnce node")
    get_control = editor.add_call_function_node("/Script/Engine.Controller:GetControlRotation")
    get_gravity = editor.add_call_function_node("/Script/Engine.CharacterMovementComponent:GetGravityDirection")
    to_relative = editor.add_call_function_node("/Script/PPG.GravityController:GetGravityRelativeRotation")
    break_rotation = editor.add_call_function_node("/Script/Engine.KismetMathLibrary:BreakRotator")
    make_rotation = editor.add_call_function_node("/Script/Engine.KismetMathLibrary:MakeRotator")
    to_world = editor.add_call_function_node("/Script/PPG.GravityController:GetGravityWorldRotation")
    set_control = editor.add_call_function_node("/Script/Engine.Controller:SetControlRotation")
    created = [do_once, get_control, get_gravity, to_relative, break_rotation, make_rotation, to_world, set_control]
    require(all(value is not None for value in created), "One or more R13 graph nodes failed to create")

    gravity_then = pin(gravity_sets[0], "then", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    do_execute = pin(do_once, "execute", unreal.EdGraphPinDirection.EGPD_INPUT)
    do_completed = pin(do_once, "Completed", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    set_execute = pin(set_control, "execute", unreal.EdGraphPinDirection.EGPD_INPUT)
    require(gravity_then.try_create_connection(do_execute), "SetGravityDirection -> DoOnce failed")
    require(do_completed.try_create_connection(set_execute), "DoOnce -> SetControlRotation failed")

    controller_out = pin(controllers[0], "ReturnValue", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    require(controller_out.try_create_connection(pin(get_control, "self", unreal.EdGraphPinDirection.EGPD_INPUT)),
            "Controller -> GetControlRotation failed")
    require(controller_out.try_create_connection(pin(set_control, "self", unreal.EdGraphPinDirection.EGPD_INPUT)),
            "Controller -> SetControlRotation failed")

    movement_out = pin(movements[0], "CharacterMovement", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    require(movement_out.try_create_connection(pin(get_gravity, "self", unreal.EdGraphPinDirection.EGPD_INPUT)),
            "CharacterMovement -> GetGravityDirection failed")
    gravity_out = pin(get_gravity, "ReturnValue", unreal.EdGraphPinDirection.EGPD_OUTPUT)

    control_rotation = pin(get_control, "ReturnValue", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    require(control_rotation.try_create_connection(pin(to_relative, "Rotation", unreal.EdGraphPinDirection.EGPD_INPUT)),
            "ControlRotation -> gravity-relative conversion failed")
    require(gravity_out.try_create_connection(pin(to_relative, "GravityDirection", unreal.EdGraphPinDirection.EGPD_INPUT)),
            "Gravity direction -> relative conversion failed")
    require(pin(to_relative, "ReturnValue", unreal.EdGraphPinDirection.EGPD_OUTPUT).try_create_connection(
        pin(break_rotation, "InRot", unreal.EdGraphPinDirection.EGPD_INPUT)),
        "Relative rotation -> BreakRotator failed")

    require(pin(break_rotation, "Yaw", unreal.EdGraphPinDirection.EGPD_OUTPUT).try_create_connection(
        pin(make_rotation, "Yaw", unreal.EdGraphPinDirection.EGPD_INPUT)),
        "Preserved relative yaw connection failed")
    pitch_pin = pin(make_rotation, "Pitch", unreal.EdGraphPinDirection.EGPD_INPUT)
    roll_pin = pin(make_rotation, "Roll", unreal.EdGraphPinDirection.EGPD_INPUT)
    require(pitch_pin.set_pin_value("0.0"), "Initial local pitch write failed")
    require(roll_pin.set_pin_value("0.0"), "Initial local roll write failed")

    require(pin(make_rotation, "ReturnValue", unreal.EdGraphPinDirection.EGPD_OUTPUT).try_create_connection(
        pin(to_world, "Rotation", unreal.EdGraphPinDirection.EGPD_INPUT)),
        "MakeRotator -> gravity-world conversion failed")
    require(gravity_out.try_create_connection(pin(to_world, "GravityDirection", unreal.EdGraphPinDirection.EGPD_INPUT)),
            "Gravity direction -> world conversion failed")
    require(pin(to_world, "ReturnValue", unreal.EdGraphPinDirection.EGPD_OUTPUT).try_create_connection(
        pin(set_control, "NewRotation", unreal.EdGraphPinDirection.EGPD_INPUT)),
        "Gravity-world rotation -> SetControlRotation failed")

    report = compile_blueprint(pawn)
    save_asset(pawn)
    return {
        "trigger": "SetGravityDirection.then -> DoOnce.Completed",
        "rotation_policy": "preserve gravity-relative yaw; initialize local pitch=0 and roll=0 once",
        "nodes_created": [str(value.get_node_title()) for value in created],
        "compile": report,
    }


def patch_game_mode(game_mode, pawn) -> dict:
    cdo = unreal.get_default_object(game_mode.generated_class())
    before = cdo.get_editor_property("default_pawn_class")
    cdo.set_editor_property("default_pawn_class", pawn.generated_class())
    require(cdo.get_editor_property("default_pawn_class") == pawn.generated_class(),
            "R13 DefaultPawnClass readback failed")
    report = compile_blueprint(game_mode)
    save_asset(game_mode)
    return {"before": before.get_path_name() if before else None,
            "after": pawn.generated_class().get_path_name(), "compile": report}


def delete_created(created: list[str]) -> dict:
    deleted = []
    failed = []
    for target in reversed(created):
        try:
            if unreal.EditorAssetLibrary.does_asset_exist(target):
                (deleted if unreal.EditorAssetLibrary.delete_asset(target) else failed).append(target)
        except Exception:
            failed.append(target)
    return {"deleted": deleted, "failed": failed}


def main() -> dict:
    started = time.time()
    require(not os.path.exists(RESULT), "R13 result no-clobber failed")
    actual_project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    require(unreal.Paths.is_same_path(actual_project, PROJECT), f"Wrong project: {actual_project}")
    subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    require(not subsystem.is_in_play_in_editor(), "R13 build refused while PIE is active")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    current_map = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
    require(current_map == MAP, f"Wrong map: {current_map}")
    require(dirty_packages() == {"content": [], "maps": []}, f"Dirty package preflight failed: {dirty_packages()}")
    ports = provider_gate()
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, f"Protected checkpoint hash drift: {path}")
    require(not unreal.EditorAssetLibrary.does_asset_exist(TARGET_PAWN), "R13 pawn already exists")
    require(not unreal.EditorAssetLibrary.does_asset_exist(TARGET_GAME_MODE), "R13 GameMode already exists")

    report = {
        "schema": "redmmo.ppg_camera_spawn.r13.build.v1",
        "status": "RUNNING",
        "project": PROJECT,
        "map": MAP,
        "provider_ports_closed": ports,
        "rollback": backup(),
        "writes": [],
        "map_saved": False,
    }
    created = []
    map_changed = False
    source_game_mode = load(SOURCE_GAME_MODE, "R11 GameMode")
    original_game_mode_class = source_game_mode.generated_class()
    settings = world.get_world_settings()
    require(settings.get_editor_property("default_game_mode") == original_game_mode_class,
            "Home map is not currently bound to R11 GameMode")
    try:
        pawn = duplicate(SOURCE_PAWN, TARGET_PAWN, "R13 pawn")
        created.append(TARGET_PAWN)
        report["pawn"] = add_camera_initializer(pawn)
        report["writes"].append(TARGET_PAWN)

        game_mode = duplicate(SOURCE_GAME_MODE, TARGET_GAME_MODE, "R13 GameMode")
        created.append(TARGET_GAME_MODE)
        report["game_mode"] = patch_game_mode(game_mode, pawn)
        report["writes"].append(TARGET_GAME_MODE)

        settings.set_editor_property("default_game_mode", game_mode.generated_class())
        require(settings.get_editor_property("default_game_mode") == game_mode.generated_class(),
                "WorldSettings R13 GameMode write failed")
        map_changed = True
        require(unreal.EditorLevelLibrary.save_current_level(), "Unable to save R13 home map")
        report["map_saved"] = True
        report["writes"].append(MAP)

        require(unreal.EditorLoadingAndSavingUtils.load_map(MAP), "Fresh R13 home-map reload failed")
        reloaded_world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        reloaded_game_mode = reloaded_world.get_world_settings().get_editor_property("default_game_mode")
        require(reloaded_game_mode == game_mode.generated_class(), f"Reloaded R13 GameMode mismatch: {reloaded_game_mode}")
        require(dirty_packages() == {"content": [], "maps": []}, f"Dirty packages after R13 reload: {dirty_packages()}")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, f"Protected checkpoint changed during R13: {path}")

        report.update({
            "status": "PASS_SERIALIZED_RELOADED_PENDING_MAPCHECK_REAL_D3D12_PIE",
            "map_sha256_before": EXPECTED[MAP_FILE],
            "map_sha256_after": sha256(MAP_FILE),
            "pawn_sha256": sha256(TARGET_PAWN_FILE),
            "game_mode_sha256": sha256(TARGET_GAME_MODE_FILE),
            "reloaded_game_mode": reloaded_game_mode.get_path_name(),
            "protected_hashes_unchanged": True,
            "elapsed_seconds": time.time() - started,
        })
        require(report["map_sha256_after"] != EXPECTED[MAP_FILE], "R13 map hash did not change")
        return report
    except Exception:
        rollback_report = {"map_game_mode_restored": False, "asset_cleanup": None}
        try:
            if map_changed:
                current_world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
                current_world.get_world_settings().set_editor_property("default_game_mode", original_game_mode_class)
                rollback_report["map_game_mode_restored"] = bool(unreal.EditorLevelLibrary.save_current_level())
        except Exception as rollback_error:
            rollback_report["map_restore_error"] = str(rollback_error)
        rollback_report["asset_cleanup"] = delete_created(created)
        report["rollback_after_failure"] = rollback_report
        raise


try:
    _result = main()
    atomic_json(RESULT, _result)
    unreal.log("REDMMO_R13_CAMERA_SPAWN_BUILD PASS")
except Exception as _error:
    _failure = {
        "schema": "redmmo.ppg_camera_spawn.r13.build.v1",
        "status": "FAIL",
        "error": str(_error),
        "traceback": traceback.format_exc(),
        "rollback_manifest": ROLLBACK_MANIFEST if os.path.exists(ROLLBACK_MANIFEST) else None,
    }
    atomic_json(RESULT, _failure)
    unreal.log_error("REDMMO_R13_CAMERA_SPAWN_BUILD FAIL " + str(_error))
