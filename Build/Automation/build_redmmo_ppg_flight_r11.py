"""Build the reversible clean-Red R11 PPG flight-control correction.

The installed PPG plugin remains immutable.  This duplicates its example pawn,
input context, and GameMode into /Game/RedMMO, reconnects only the missing
camera-pitch wire for forward flight, remaps descend from Left Shift to Left
Control, and sets the real home map to the project-owned GameMode.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import traceback

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_MAP_SHA = "C489B6000B359A7B52FBE7FD50A72A76232020DBC9A015DFC61CA2FB1120C46F"
SOURCE_PAWN = "/PPG/Example/Assets/Character/ExamplePlanetCharacter"
SOURCE_CONTEXT = "/PPG/Example/Assets/Character/Input/IMC_Default"
SOURCE_GAME_MODE = "/PPG/Example/Level/PPGExampleGameMode"
TARGET_CONTEXT = "/Game/RedMMO/Gameplay/Input/IMC_RedPlanet_R11"
TARGET_PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
TARGET_GAME_MODE = "/Game/RedMMO/Gameplay/Player/GM_RedPlanet_R11"
TARGETS = (TARGET_CONTEXT, TARGET_PAWN, TARGET_GAME_MODE)
RESULT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_Flight_R11_20260802"
    r"\build_redmmo_ppg_flight_r11_result.json"
)
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


def write_json(value: dict) -> None:
    os.makedirs(os.path.dirname(RESULT), exist_ok=True)
    temporary = RESULT + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary, RESULT)


def asset_path(value) -> str | None:
    return value.get_path_name().split(".")[0] if value is not None else None


def current_project() -> str:
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path()).replace("/", "\\")


def current_map() -> str:
    world = unreal.EditorLevelLibrary.get_editor_world()
    return world.get_path_name().split(":", 1)[0].split(".", 1)[0] if world else ""


def port_listening(port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.15)
    try:
        return probe.connect_ex(("127.0.0.1", port)) == 0
    finally:
        probe.close()


def dirty_packages() -> dict:
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


def load(path: str, kind: str):
    value = unreal.load_asset(path)
    require(value is not None, f"Missing {kind}: {path}")
    return value


def pin(node, name: str, direction):
    matches = [
        value for value in list(node.list_all_pins())
        if str(value.get_pin_name()).lower() == name.lower()
        and value.get_pin_direction() == direction
    ]
    require(len(matches) == 1, f"Ambiguous pin {name} on {node.get_node_title()}: {len(matches)}")
    return matches[0]


def unique_node(editor, title: str):
    matches = [node for node in list(editor.list_all_nodes()) if str(node.get_node_title()) == title]
    require(len(matches) == 1, f"Expected one '{title}' node, found {len(matches)}")
    return matches[0]


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
    return {
        "asset": asset_path(blueprint),
        "status": str(status),
        "warnings": warnings,
    }


def save_asset(asset) -> None:
    require(
        unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False),
        f"Unable to save {asset.get_path_name()}",
    )


def make_key(name: str):
    key = unreal.Key()
    key.set_editor_property("key_name", unreal.Name(name))
    require(str(key.get_editor_property("key_name")).lower() == name.lower(), f"FKey readback failed: {name}")
    return key


def duplicate(source: str, target: str, kind: str):
    require(not unreal.EditorAssetLibrary.does_asset_exist(target), f"No-clobber target exists: {target}")
    value = unreal.EditorAssetLibrary.duplicate_asset(source, target)
    require(value is not None, f"Unable to duplicate {kind}: {source} -> {target}")
    require(asset_path(value) == target, f"Duplicate path mismatch: {value.get_path_name()}")
    return value


def patch_context(context) -> dict:
    mapping_data = context.get_editor_property("default_key_mappings")
    mappings = list(mapping_data.get_editor_property("mappings"))
    records_before = []
    candidates = []
    for index, mapping in enumerate(mappings):
        action = mapping.get_editor_property("action")
        key = mapping.get_editor_property("key")
        key_name = str(key.get_editor_property("key_name"))
        action_name = asset_path(action)
        modifiers = [value.get_class().get_name() for value in mapping.get_editor_property("modifiers")]
        records_before.append({
            "index": index,
            "action": action_name,
            "key": key_name,
            "modifiers": modifiers,
        })
        if action_name == "/PPG/Example/Assets/Character/Input/Actions/IA_Move" and key_name.lower() == "leftshift":
            candidates.append((index, mapping))
    require(len(candidates) == 1, f"Expected one IA_Move LeftShift descend mapping: {records_before}")
    require(
        not any(record["key"].lower() == "leftcontrol" for record in records_before),
        "Input context already maps LeftControl; refusing ambiguous override",
    )
    index, mapping = candidates[0]
    source_descend_modifiers = list(records_before[index]["modifiers"])
    require(source_descend_modifiers, "PPG descend mapping has no modifier stack; refusing semantic drift")
    mapping.set_editor_property("key", make_key("LeftControl"))
    mappings[index] = mapping
    mapping_data.set_editor_property("mappings", mappings)
    context.set_editor_property("default_key_mappings", mapping_data)
    context.set_editor_property(
        "context_description",
        unreal.Text("Red R11: full-pitch camera flight; Space ascend; Left Ctrl descend."),
    )
    save_asset(context)

    records_after = []
    for position, value in enumerate(
        context.get_editor_property("default_key_mappings").get_editor_property("mappings")
    ):
        records_after.append({
            "index": position,
            "action": asset_path(value.get_editor_property("action")),
            "key": str(value.get_editor_property("key").get_editor_property("key_name")),
            "modifiers": [
                item.get_class().get_name() for item in value.get_editor_property("modifiers")
            ],
        })
    require(
        sum(record["key"].lower() == "leftcontrol" for record in records_after) == 1,
        f"LeftControl mapping readback failed: {records_after}",
    )
    require(
        not any(record["key"].lower() == "leftshift" for record in records_after),
        f"Legacy LeftShift descend remained: {records_after}",
    )
    require(
        records_after[index]["modifiers"] == source_descend_modifiers,
        f"Descend modifier stack drifted: {source_descend_modifiers} -> {records_after[index]['modifiers']}",
    )
    return {"before": records_before, "after": records_after}


def patch_pawn(pawn, context) -> dict:
    editor = unreal.BlueprintGraphEditor.get_graph_editor_by_name(pawn, unreal.Name("EventGraph"))
    require(editor is not None, "Duplicated pawn EventGraph is unavailable")

    forward = unique_node(editor, "GetForwardVector")
    forward_rotation = pin(forward, "InRot", unreal.EdGraphPinDirection.EGPD_INPUT)
    forward_rotation_links = list(forward_rotation.list_connected_pins())
    require(len(forward_rotation_links) == 1, "ForwardVector rotation source is ambiguous")
    world_rotation = forward_rotation_links[0].get_owning_node()
    require(str(world_rotation.get_node_title()) == "GetGravityWorldRotation", "Unexpected forward world-rotation source")
    world_pitch = pin(world_rotation, "Rotation_Pitch", unreal.EdGraphPinDirection.EGPD_INPUT)
    require(not list(world_pitch.list_connected_pins()), "Forward pitch is already connected; refusing drift")
    world_yaw = pin(world_rotation, "Rotation_Yaw", unreal.EdGraphPinDirection.EGPD_INPUT)
    yaw_links = list(world_yaw.list_connected_pins())
    require(len(yaw_links) == 1, "Forward yaw source is ambiguous")
    relative_rotation = yaw_links[0].get_owning_node()
    require(str(relative_rotation.get_node_title()) == "GetGravityRelativeRotation", "Unexpected gravity-relative source")
    relative_pitch = pin(relative_rotation, "ReturnValue_Pitch", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    require(not list(relative_pitch.list_connected_pins()), "Gravity-relative pitch is already consumed")
    require(relative_pitch.try_create_connection(world_pitch), "Unable to connect camera pitch into forward flight")
    require(
        any(value.is_same_native_pin(relative_pitch) for value in world_pitch.list_connected_pins()),
        "Forward pitch connection readback failed",
    )

    add_context = unique_node(editor, "AddMappingContext")
    context_pin = pin(add_context, "MappingContext", unreal.EdGraphPinDirection.EGPD_INPUT)
    before_context = str(context_pin.get_pin_value())
    require(
        before_context == SOURCE_CONTEXT + ".IMC_Default",
        f"Unexpected inherited mapping context: {before_context}",
    )
    require(context_pin.set_pin_value(context.get_path_name()), "Unable to set project input context")
    require(str(context_pin.get_pin_value()) == context.get_path_name(), "Input context pin readback failed")

    compile_report = compile_blueprint(pawn)
    save_asset(pawn)
    return {
        "camera_pitch_connection": "GetGravityRelativeRotation.ReturnValue_Pitch -> GetGravityWorldRotation.Rotation_Pitch -> GetForwardVector",
        "mapping_context_before": before_context,
        "mapping_context_after": str(context_pin.get_pin_value()),
        "compile": compile_report,
    }


def patch_game_mode(game_mode, pawn) -> dict:
    cdo = unreal.get_default_object(game_mode.generated_class())
    before = cdo.get_editor_property("default_pawn_class")
    pawn_class = pawn.generated_class()
    cdo.set_editor_property("default_pawn_class", pawn_class)
    require(cdo.get_editor_property("default_pawn_class") == pawn_class, "DefaultPawnClass readback failed")
    compile_report = compile_blueprint(game_mode)
    save_asset(game_mode)
    require(
        unreal.get_default_object(game_mode.generated_class()).get_editor_property("default_pawn_class") == pawn_class,
        "Saved GameMode DefaultPawnClass mismatch",
    )
    return {
        "before": before.get_path_name() if before else None,
        "after": pawn_class.get_path_name(),
        "compile": compile_report,
    }


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


def main() -> None:
    created = []
    original_game_mode = None
    map_changed = False
    report = {
        "schema": "redmmo.ppg_flight.r11.build.v1",
        "status": "RUNNING",
        "project": PROJECT,
        "map": MAP,
        "map_sha256_before": sha256(MAP_FILE),
        "targets": list(TARGETS),
        "provider_ports_closed": {str(port): not port_listening(port) for port in PROVIDER_PORTS},
        "writes": [],
    }
    try:
        require(
            unreal.Paths.is_same_path(current_project(), PROJECT),
            f"Wrong project: {current_project()}",
        )
        require(current_map() == MAP, f"Wrong map: {current_map()}")
        require(report["map_sha256_before"] == EXPECTED_MAP_SHA, "Home map hash drift")
        require(all(report["provider_ports_closed"].values()), "AI/MCP/provider port is listening")
        require(
            not list(unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=False)),
            "PIE must be stopped",
        )
        require(dirty_packages() == {"content": [], "maps": []}, f"Dirty package preflight failed: {dirty_packages()}")
        existing = [target for target in TARGETS if unreal.EditorAssetLibrary.does_asset_exist(target)]
        require(not existing, f"No-clobber R11 targets already exist: {existing}")

        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        settings = world.get_world_settings()
        source_game_mode = load(SOURCE_GAME_MODE, "PPG GameMode")
        original_game_mode = source_game_mode.generated_class()
        require(settings.get_editor_property("default_game_mode") == original_game_mode, "Unexpected home GameMode override")

        context = duplicate(SOURCE_CONTEXT, TARGET_CONTEXT, "input context")
        created.append(TARGET_CONTEXT)
        report["input"] = patch_context(context)
        report["writes"].append(TARGET_CONTEXT)

        pawn = duplicate(SOURCE_PAWN, TARGET_PAWN, "pawn")
        created.append(TARGET_PAWN)
        report["pawn"] = patch_pawn(pawn, context)
        report["writes"].append(TARGET_PAWN)

        game_mode = duplicate(SOURCE_GAME_MODE, TARGET_GAME_MODE, "GameMode")
        created.append(TARGET_GAME_MODE)
        report["game_mode"] = patch_game_mode(game_mode, pawn)
        report["writes"].append(TARGET_GAME_MODE)

        settings.set_editor_property("default_game_mode", game_mode.generated_class())
        require(settings.get_editor_property("default_game_mode") == game_mode.generated_class(), "WorldSettings GameMode write failed")
        map_changed = True
        require(unreal.EditorLevelLibrary.save_current_level(), "Unable to save real home map")
        report["writes"].append(MAP)

        require(unreal.EditorLoadingAndSavingUtils.load_map(MAP), "Fresh home-map reload failed")
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        reloaded = world.get_world_settings().get_editor_property("default_game_mode")
        require(reloaded == game_mode.generated_class(), f"Reloaded GameMode mismatch: {reloaded}")
        require(dirty_packages() == {"content": [], "maps": []}, f"Dirty packages after reload: {dirty_packages()}")

        report["map_sha256_after"] = sha256(MAP_FILE)
        require(report["map_sha256_after"] != EXPECTED_MAP_SHA, "Home map did not serialize R11 GameMode")
        report["reloaded_game_mode"] = reloaded.get_path_name()
        report["status"] = "PASS"
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        rollback = {"map_game_mode_restored": False, "asset_cleanup": None}
        try:
            if map_changed and original_game_mode is not None:
                world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
                world.get_world_settings().set_editor_property("default_game_mode", original_game_mode)
                rollback["map_game_mode_restored"] = bool(unreal.EditorLevelLibrary.save_current_level())
        except Exception as rollback_exc:
            rollback["map_restore_error"] = str(rollback_exc)
        rollback["asset_cleanup"] = delete_created(created)
        report["rollback"] = rollback
    write_json(report)
    unreal.log(f"REDMMO_PPG_FLIGHT_R11_BUILD={report['status']} RESULT={RESULT}")


main()
