"""Read-only graph audit for the clean-Red grounded-footstep R16B fix."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import unreal


SOURCE = "/Game/SoStylized/Demo/Pawn/Mannequin/Animations/ThirdPerson_AnimBP"
RESULT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R16B_GroundedFootsteps_20260803_004400\audit_redmmo_grounded_footstep_r16b_r02_result.json")
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


def pin_record(pin):
    connected = []
    for other in list(pin.list_connected_pins()):
        owner = other.get_owning_node()
        connected.append({
            "node_title": str(owner.get_node_title()),
            "node_class": owner.get_class().get_name(),
            "pin": str(other.get_pin_name()),
            "direction": str(other.get_pin_direction()),
        })
    return {
        "name": str(pin.get_pin_name()),
        "direction": str(pin.get_pin_direction()),
        "value": str(pin.get_pin_value()),
        "connected": connected,
    }


def safe(call, default=None):
    try:
        return call()
    except Exception:
        return default


def main():
    payload = {"schema": "redmmo.r16b.grounded_footstep.audit.v1", "started_utc": now(), "status": "RUNNING"}
    try:
        require(not RESULT.exists(), "No-clobber result already exists")
        bp = unreal.EditorAssetLibrary.load_asset(SOURCE)
        require(bp is not None and bp.get_class().get_name() == "AnimBlueprint", "AnimBP missing or wrong class")
        graphs = [str(name) for name in unreal.BlueprintEditorLibrary.list_graph_names(bp)]
        records = []
        for graph_name in graphs:
            editor = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, unreal.Name(graph_name))
            if editor is None:
                continue
            for node in list(editor.list_all_nodes()):
                title = str(node.get_node_title())
                pins = [pin_record(pin) for pin in list(node.list_all_pins())]
                connected_titles = sorted({item["node_title"] for pin in pins for item in pin["connected"]})
                guid = safe(lambda: str(node.get_editor_property("node_guid")))
                position = safe(lambda: node.get_node_pos())
                records.append({
                    "graph": graph_name,
                    "title": title,
                    "class": node.get_class().get_name(),
                    "guid": guid,
                    "position": [int(position.x), int(position.y)] if position is not None else None,
                    "pins": pins,
                    "connected_titles": connected_titles,
                })
        interests = [
            item for item in records
            if any(term in item["title"].lower() for term in ("footstep", "play sound", "is moving on ground", "is falling"))
            or any(any(term in title.lower() for term in ("footstep", "play sound")) for title in item["connected_titles"])
        ]
        payload.update({
            "status": "PASS_READ_ONLY",
            "asset": SOURCE,
            "graph_names": graphs,
            "node_count": len(records),
            "interest_count": len(interests),
            "interest_nodes": interests,
            "dirty_content_packages": [str(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
            "dirty_map_packages": [str(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
        })
        require(not payload["dirty_content_packages"] and not payload["dirty_map_packages"], "Read-only audit dirtied packages")
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
        unreal.log("REDMMO_R16B_FOOTSTEP_AUDIT " + payload["status"])
        schedule_exit()


main()
