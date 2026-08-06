"""Read-only graph audit for grounded footstep ownership on the R87 A01 Trooper."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import unreal


SOURCE = "/Game/Action_Trooper/Animations/Tall_Female/ABP_ThirdPerson_Female_Tall"
RESULT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R87_GroundedFootstepAudit_20260806T0813Z\result.json"
)
TERMS = (
    "footstep",
    "play sound",
    "spawn sound",
    "is moving on ground",
    "is falling",
    "notify",
)
_EXIT = {"handle": None}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def schedule_exit(delay=6.0):
    started = time.monotonic()

    def tick(_delta):
        if time.monotonic() - started < delay:
            return
        handle = _EXIT.get("handle")
        if handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(handle)
            except Exception:
                pass
            _EXIT["handle"] = None
        unreal.SystemLibrary.quit_editor()

    _EXIT["handle"] = unreal.register_slate_post_tick_callback(tick)


def safe(call, default=None):
    try:
        return call()
    except Exception:
        return default


def pin_record(pin):
    connected = []
    for other in list(pin.list_connected_pins()):
        owner = other.get_owning_node()
        connected.append(
            {
                "node_title": str(owner.get_node_title()),
                "node_class": owner.get_class().get_name(),
                "pin": str(other.get_pin_name()),
                "direction": str(other.get_pin_direction()),
            }
        )
    return {
        "name": str(pin.get_pin_name()),
        "direction": str(pin.get_pin_direction()),
        "value": str(pin.get_pin_value()),
        "connected": connected,
    }


def main():
    payload = {
        "schema": "redmmo.r87.a01_trooper.grounded_footstep.audit.v1",
        "started_utc": now(),
        "status": "RUNNING",
        "asset": SOURCE,
        "mutation_policy": "read_only_no_save",
    }
    try:
        require(not RESULT.exists(), "No-clobber result already exists")
        blueprint = unreal.EditorAssetLibrary.load_asset(SOURCE)
        require(
            blueprint is not None and blueprint.get_class().get_name() == "AnimBlueprint",
            "A01 Trooper AnimBP missing or wrong class",
        )
        graphs = [str(name) for name in unreal.BlueprintEditorLibrary.list_graph_names(blueprint)]
        records = []
        for graph_name in graphs:
            editor = unreal.BlueprintGraphEditor.get_graph_editor_by_name(
                blueprint, unreal.Name(graph_name)
            )
            if editor is None:
                continue
            for node in list(editor.list_all_nodes()):
                title = str(node.get_node_title())
                pins = [pin_record(pin) for pin in list(node.list_all_pins())]
                connected_titles = sorted(
                    {item["node_title"] for pin in pins for item in pin["connected"]}
                )
                guid = safe(lambda: str(node.get_editor_property("node_guid")))
                position = safe(lambda: node.get_node_pos())
                records.append(
                    {
                        "graph": graph_name,
                        "title": title,
                        "class": node.get_class().get_name(),
                        "guid": guid,
                        "position": (
                            [int(position.x), int(position.y)]
                            if position is not None
                            else None
                        ),
                        "pins": pins,
                        "connected_titles": connected_titles,
                    }
                )

        def is_interest(item):
            searchable = [item["title"], *item["connected_titles"]]
            return any(term in value.lower() for term in TERMS for value in searchable)

        interests = [item for item in records if is_interest(item)]
        titles = [item["title"].lower() for item in records]
        payload.update(
            {
                "status": "PASS_READ_ONLY",
                "graph_names": graphs,
                "node_count": len(records),
                "interest_count": len(interests),
                "interest_nodes": interests,
                "title_term_counts": {
                    term: sum(term in title for title in titles) for term in TERMS
                },
                "dirty_content_packages": [
                    str(value)
                    for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
                ],
                "dirty_map_packages": [
                    str(value)
                    for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
                ],
            }
        )
        require(
            not payload["dirty_content_packages"] and not payload["dirty_map_packages"],
            "Read-only audit dirtied packages",
        )
    except Exception as exc:
        payload["status"] = "FAIL"
        payload["error"] = repr(exc)
    finally:
        payload["completed_utc"] = now()
        RESULT.parent.mkdir(parents=True, exist_ok=True)
        with RESULT.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        unreal.log("REDMMO_R87_A01_FOOTSTEP_AUDIT " + payload["status"])
        schedule_exit()


main()
