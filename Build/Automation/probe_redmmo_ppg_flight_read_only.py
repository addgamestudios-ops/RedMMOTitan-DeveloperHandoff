"""Read-only introspection of the clean Red MMO PPG example pawn.

This script is intended to run inside the already-open UE 5.8 editor through
the Python console.  It never saves a package or changes an object.  The JSON
report is written outside the Unreal project so it can be reviewed before the
flight implementation is selected.
"""

from __future__ import annotations

import json
import os
import traceback

import unreal


OUTPUT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_PPG_Flight_R11_20260802"
    r"\probe_ppg_flight_read_only.json"
)
PAWN = "/PPG/Example/Assets/Character/ExamplePlanetCharacter"
GAME_MODE = "/PPG/Example/Level/PPGExampleGameMode"


def _write(value: dict) -> None:
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    temporary = OUTPUT + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary, OUTPUT)


def _safe(callable_value, default=None):
    try:
        return callable_value()
    except Exception as exc:  # diagnostic output must retain unavailable facts
        return {"unavailable": str(exc)} if default is None else default


def _asset_path(value):
    if value is None:
        return None
    return _safe(lambda: value.get_path_name(), str(value))


def main() -> None:
    report = {
        "schema": "redmmo.ppg_flight.read_only_probe.v1",
        "status": "RUNNING",
        "writes": [],
        "pawn": PAWN,
        "game_mode": GAME_MODE,
    }
    try:
        dirty_before = {
            "content": sorted(
                package.get_path_name()
                for package in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
            ),
            "maps": sorted(
                package.get_path_name()
                for package in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
            ),
        }
        report["dirty_before"] = dirty_before

        pawn_bp = unreal.load_asset(PAWN)
        game_mode_bp = unreal.load_asset(GAME_MODE)
        if pawn_bp is None or game_mode_bp is None:
            raise RuntimeError("Required PPG example Blueprint is missing")

        report["blueprint_editor_library_api"] = sorted(
            name for name in dir(unreal.BlueprintEditorLibrary) if not name.startswith("_")
        )
        report["blueprint_graph_editor_api"] = sorted(
            name for name in dir(unreal.BlueprintGraphEditor) if not name.startswith("_")
        )
        report["pawn_blueprint_dir"] = sorted(
            name for name in dir(pawn_bp) if not name.startswith("_")
        )

        generated_class = pawn_bp.generated_class()
        pawn_cdo = unreal.get_default_object(generated_class)
        report["pawn_generated_class"] = _asset_path(generated_class)
        report["pawn_cdo"] = _asset_path(pawn_cdo)
        report["pawn_cdo_dir"] = sorted(
            name for name in dir(pawn_cdo) if not name.startswith("_")
        )

        property_candidates = [
            "default_mapping_context",
            "mapping_context",
            "input_mapping_context",
            "default_input_mapping_context",
            "mesh",
            "character_movement",
            "controller",
            "auto_possess_player",
            "auto_receive_input",
            "use_controller_rotation_pitch",
            "use_controller_rotation_yaw",
            "use_controller_rotation_roll",
        ]
        properties = {}
        for name in property_candidates:
            properties[name] = _safe(
                lambda candidate=name: _asset_path(pawn_cdo.get_editor_property(candidate))
            )
        report["pawn_selected_properties"] = properties

        graph_names = [str(name) for name in unreal.BlueprintEditorLibrary.list_graph_names(pawn_bp)]
        report["graph_names"] = graph_names
        graph_reports = []
        pin_api_recorded = False
        for graph_name in graph_names:
            item = {"name": graph_name}
            editor = _safe(
                lambda current=graph_name: unreal.BlueprintGraphEditor.get_graph_editor_by_name(
                    pawn_bp, unreal.Name(current)
                )
            )
            if isinstance(editor, dict):
                item["editor"] = editor
                graph_reports.append(item)
                continue
            item["editor_class"] = editor.get_class().get_path_name() if editor else None
            if editor:
                item["editor_dir"] = sorted(
                    name for name in dir(editor) if not name.startswith("_")
                )
                item["errors"] = _safe(
                    lambda: [str(node.get_node_title()) for node in editor.list_nodes_with_errors()]
                )
                item["warnings"] = _safe(
                    lambda: [str(node.get_node_title()) for node in editor.list_nodes_with_warnings()]
                )
                node_records = []
                for node in list(editor.list_all_nodes()):
                    record = {
                        "class": node.get_class().get_path_name(),
                        "title": str(node.get_node_title()),
                        "position": str(node.get_node_pos()),
                        "pins": [],
                    }
                    for pin in list(node.list_all_pins()):
                        if not pin_api_recorded:
                            report["blueprint_pin_api"] = sorted(
                                name for name in dir(pin) if not name.startswith("_")
                            )
                            pin_api_recorded = True
                        linked = []
                        for connected in list(pin.list_connected_pins()):
                            outer = _safe(lambda value=connected: value.get_owning_node())
                            linked.append(
                                {
                                    "pin": str(connected.get_pin_name()),
                                    "node_class": (
                                        outer.get_class().get_path_name()
                                        if outer and not isinstance(outer, dict)
                                        else outer
                                    ),
                                    "node_title": (
                                        str(outer.get_node_title())
                                        if outer and not isinstance(outer, dict)
                                        and hasattr(outer, "get_node_title")
                                        else None
                                    ),
                                    "outer_path": (
                                        outer.get_path_name()
                                        if outer and not isinstance(outer, dict)
                                        else outer
                                    ),
                                }
                            )
                        record["pins"].append(
                            {
                                "name": str(pin.get_pin_name()),
                                "direction": str(pin.get_pin_direction()),
                                "value": str(pin.get_pin_value()),
                                "linked": linked,
                            }
                        )
                    node_records.append(record)
                item["nodes"] = node_records
                for event_name in ("ReceiveBeginPlay", "ReceiveTick"):
                    node = _safe(lambda value=event_name: editor.find_event_node(unreal.Name(value)))
                    item[event_name] = (
                        {
                            "class": node.get_class().get_path_name(),
                            "title": str(node.get_node_title()),
                            "dir": sorted(name for name in dir(node) if not name.startswith("_")),
                        }
                        if node and not isinstance(node, dict)
                        else node
                    )
            graph_reports.append(item)
        report["graphs"] = graph_reports

        gm_class = game_mode_bp.generated_class()
        gm_cdo = unreal.get_default_object(gm_class)
        report["game_mode_default_pawn"] = _asset_path(
            gm_cdo.get_editor_property("default_pawn_class")
        )

        report["dirty_after"] = {
            "content": sorted(
                package.get_path_name()
                for package in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
            ),
            "maps": sorted(
                package.get_path_name()
                for package in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
            ),
        }
        if report["dirty_after"] != dirty_before:
            raise RuntimeError("Read-only probe changed dirty-package state")
        report["status"] = "PASS"
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    _write(report)
    unreal.log(f"REDMMO_PPG_FLIGHT_PROBE={report['status']} OUTPUT={OUTPUT}")


main()
