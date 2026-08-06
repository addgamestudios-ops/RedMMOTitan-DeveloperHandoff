"""Read-only-by-final-state UE 5.8 graph capability probe for RedMMO R17 fighter entry.

The probe duplicates the current project-owned R11 pawn into a temporary
project-owned diagnostic Blueprint, exercises only BlueprintGraphEditor node
creation and connection APIs, writes a JSON report, then deletes the temporary
asset before exiting.  It never saves or changes the home map.
"""

from __future__ import annotations

import json
import os
import socket
import traceback

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
SOURCE = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
TEMP = "/Game/RedMMO/Diagnostics/R17/BP_RedFighterGraphProbe_R17_TEMP"
RESULT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R17_FighterEntry_20260803"
    r"\probe_redmmo_fighter_entry_graph_r17_result.json"
)
PROVIDER_PORTS = (5353, 8000, 8765)


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def norm(value) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def provider_gate() -> dict[str, bool]:
    result: dict[str, bool] = {}
    for port in PROVIDER_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.15)
            result[str(port)] = sock.connect_ex(("127.0.0.1", port)) != 0
    require(all(result.values()), f"Provider port unexpectedly open: {result}")
    return result


def asset_path(value) -> str | None:
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    if "." in leaf:
        path = path.rsplit(".", 1)[0]
    return path[:-2] if path.endswith("_C") else path


def pin(node, names, direction=None):
    wanted = {norm(name) for name in names}
    matches = [
        value for value in node.list_all_pins()
        if norm(value.get_pin_name()) in wanted
        and (direction is None or value.get_pin_direction() == direction)
    ]
    require(
        len(matches) == 1,
        f"Ambiguous pin {names} on {node.get_node_title()}: "
        f"{[(str(v.get_pin_name()), str(v.get_pin_direction())) for v in matches]}",
    )
    return matches[0]


def pin_record(value) -> dict:
    record = {
        "name": str(value.get_pin_name()),
        "direction": str(value.get_pin_direction()),
        "value": str(value.get_pin_value()),
        "connected": [
            f"{item.get_owning_node().get_node_title()}::{item.get_pin_name()}"
            for item in value.list_connected_pins()
        ],
    }
    for method in ("get_pin_type", "get_pin_sub_category", "get_pin_sub_category_object"):
        function = getattr(value, method, None)
        if callable(function):
            try:
                observed = function()
                record[method] = observed.get_path_name() if hasattr(observed, "get_path_name") else str(observed)
            except Exception as exc:
                record[method] = f"ERROR:{exc}"
    return record


def node_record(node) -> dict:
    return {
        "title": str(node.get_node_title()),
        "class": node.get_class().get_name(),
        "pins": [pin_record(value) for value in node.list_all_pins()],
    }


def main() -> dict:
    actual_project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    require(unreal.Paths.is_same_path(actual_project, PROJECT), f"Wrong project: {actual_project}")
    require(not list(unreal.EditorLevelLibrary.get_pie_worlds(False)), "PIE is active")
    require(not unreal.EditorAssetLibrary.does_asset_exist(TEMP), f"Stale temp asset exists: {TEMP}")
    require(unreal.EditorLoadingAndSavingUtils.load_map(MAP), f"Unable to load {MAP}")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    require(world.get_path_name().split(":", 1)[0].split(".", 1)[0] == MAP, "Wrong map loaded")

    report = {
        "schema": "redmmo.fighter_entry.graph_probe.r17.v1",
        "status": "RUNNING",
        "project": actual_project,
        "map": MAP,
        "provider_ports_closed": provider_gate(),
        "temp_asset": TEMP,
        "home_map_saved": False,
    }
    try:
        temp = unreal.EditorAssetLibrary.duplicate_asset(SOURCE, TEMP)
        require(isinstance(temp, unreal.Blueprint), "Unable to create temporary Blueprint duplicate")
        require(asset_path(temp) == TEMP, f"Temp path mismatch: {temp.get_path_name()}")
        editor = unreal.BlueprintGraphEditor.get_graph_editor_by_name(temp, unreal.Name("EventGraph"))
        require(editor is not None, "Temporary EventGraph unavailable")

        available = [str(value) for value in editor.list_available_nodes([])]
        terms = ("possess", "getactorofclass", "getdistanceto", "lessequal", "isvalid")
        report["available_actions"] = {
            term: sorted(value for value in available if term in norm(value))[:80]
            for term in terms
        }

        nodes = {}
        function_paths = {
            "get_actor": "/Script/Engine.GameplayStatics.GetActorOfClass",
            "get_player_controller": "/Script/Engine.GameplayStatics.GetPlayerController",
            "get_distance": "/Script/Engine.Actor.GetDistanceTo",
            "is_valid": "/Script/Engine.KismetSystemLibrary.IsValid",
            "possess": "/Script/Engine.Controller.Possess",
        }
        for key, path in function_paths.items():
            value = editor.add_call_function_node(path)
            require(value is not None, f"Unable to create {key}: {path}")
            nodes[key] = value

        less_equal = None
        less_equal_path = None
        for candidate in (
            "/Script/Engine.KismetMathLibrary.LessEqual_FloatFloat",
            "/Script/Engine.KismetMathLibrary.LessEqual_DoubleDouble",
        ):
            try:
                value = editor.add_call_function_node(candidate)
            except Exception:
                value = None
            if value is not None:
                less_equal = value
                less_equal_path = candidate
                break
        require(less_equal is not None, "No supported <= numeric Blueprint function")
        nodes["less_equal"] = less_equal
        report["less_equal_path"] = less_equal_path

        class_pin = pin(nodes["get_actor"], ("ActorClass",), unreal.EdGraphPinDirection.EGPD_INPUT)
        generated_class = temp.generated_class()
        require(generated_class is not None, "Temporary Blueprint has no generated class")
        require(class_pin.set_pin_value(generated_class.get_path_name()), "Unable to type GetActorOfClass")

        actor_return = pin(nodes["get_actor"], ("ReturnValue",), unreal.EdGraphPinDirection.EGPD_OUTPUT)
        possess_pawn = pin(nodes["possess"], ("InPawn", "Pawn"), unreal.EdGraphPinDirection.EGPD_INPUT)
        require(actor_return.try_create_connection(possess_pawn), "Typed GetActorOfClass cannot connect to Possess Pawn")

        controller_return = pin(
            nodes["get_player_controller"], ("ReturnValue",), unreal.EdGraphPinDirection.EGPD_OUTPUT
        )
        possess_target = pin(nodes["possess"], ("self", "Target"), unreal.EdGraphPinDirection.EGPD_INPUT)
        require(controller_return.try_create_connection(possess_target), "PlayerController cannot connect to Possess target")

        other_actor = pin(nodes["get_distance"], ("OtherActor",), unreal.EdGraphPinDirection.EGPD_INPUT)
        require(actor_return.try_create_connection(other_actor), "Typed fighter cannot connect to GetDistanceTo")
        valid_object = pin(nodes["is_valid"], ("Object",), unreal.EdGraphPinDirection.EGPD_INPUT)
        require(actor_return.try_create_connection(valid_object), "Typed fighter cannot connect to IsValid")

        distance_return = pin(nodes["get_distance"], ("ReturnValue",), unreal.EdGraphPinDirection.EGPD_OUTPUT)
        numeric_inputs = [
            value for value in less_equal.list_all_pins()
            if value.get_pin_direction() == unreal.EdGraphPinDirection.EGPD_INPUT
            and norm(value.get_pin_name()) in {"a", "b"}
        ]
        require(len(numeric_inputs) == 2, f"Unexpected <= pins: {node_record(less_equal)}")
        first = [value for value in numeric_inputs if norm(value.get_pin_name()) == "a"][0]
        second = [value for value in numeric_inputs if norm(value.get_pin_name()) == "b"][0]
        require(distance_return.try_create_connection(first), "Distance cannot connect to <= A")
        require(second.set_pin_value("5000.0"), "Unable to set fighter entry radius")

        report["nodes"] = {key: node_record(value) for key, value in nodes.items()}
        report["connections"] = {
            "typed_actor_to_possess": True,
            "controller_to_possess": True,
            "typed_actor_to_distance": True,
            "typed_actor_to_validity": True,
            "distance_to_less_equal": True,
        }
        report["status"] = "PASS"
    finally:
        # The duplicated package is intentionally never saved.  ForceDelete on a
        # loaded Blueprint that contains typed self references trips an engine
        # ObjectTools ensure in UE 5.8.  Let process teardown discard this
        # unsaved diagnostic package, then require the external launcher to prove
        # that no .uasset exists before treating the probe as durable evidence.
        report["temp_unsaved_discard_on_exit"] = True
        report["temp_exists_in_memory_before_exit"] = unreal.EditorAssetLibrary.does_asset_exist(TEMP)
        report["dirty_packages_after"] = {
            "content": sorted(str(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()),
            "maps": sorted(str(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()),
        }
        unexpected_content = [
            value for value in report["dirty_packages_after"]["content"]
            if TEMP not in str(value)
        ]
        require(
            not unexpected_content and not report["dirty_packages_after"]["maps"],
            f"Unexpected dirty packages remained: {report['dirty_packages_after']}",
        )
    return report


os.makedirs(os.path.dirname(RESULT), exist_ok=True)
payload = None
try:
    payload = main()
except Exception as exc:
    payload = {
        "schema": "redmmo.fighter_entry.graph_probe.r17.v1",
        "status": "FAIL",
        "error": str(exc),
        "traceback": traceback.format_exc(),
        "temp_exists_in_memory_before_exit": unreal.EditorAssetLibrary.does_asset_exist(TEMP),
    }

with open(RESULT + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
os.replace(RESULT + ".tmp", RESULT)
if payload.get("status") == "PASS":
    unreal.log("REDMMO_R17_FIGHTER_GRAPH_PROBE_PASS")
else:
    unreal.log_error("REDMMO_R17_FIGHTER_GRAPH_PROBE_FAIL " + payload.get("error", "unknown"))
unreal.SystemLibrary.quit_editor()
