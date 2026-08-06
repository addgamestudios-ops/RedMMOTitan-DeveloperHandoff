"""Read-only focused graph inventory for R13 camera initialization."""

from __future__ import annotations

import json
import os

import unreal


OUT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R13_20260802"
    r"\probe_redmmo_r13_pawn_graph.json"
)
BP = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"


def pin_record(value):
    linked = []
    for other in list(value.list_connected_pins()):
        linked.append({
            "node": str(other.get_owning_node().get_node_title()),
            "pin": str(other.get_pin_name()),
        })
    return {
        "name": str(value.get_pin_name()),
        "direction": str(value.get_pin_direction()),
        "value": str(value.get_pin_value()),
        "links": linked,
    }


bp = unreal.load_asset(BP)
if not isinstance(bp, unreal.Blueprint):
    raise RuntimeError("R11 pawn unavailable")
editor = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, unreal.Name("EventGraph"))
if editor is None:
    raise RuntimeError("R11 EventGraph unavailable")

needles = (
    "beginplay", "controller", "mapping", "character movement", "gravity",
    "forwardvector", "delay",
)
records = []
for index, node in enumerate(list(editor.list_all_nodes())):
    title = str(node.get_node_title())
    if any(needle in title.lower() for needle in needles):
        records.append({
            "index": index,
            "title": title,
            "class": node.get_class().get_path_name(),
            "pins": [pin_record(value) for value in list(node.list_all_pins())],
        })

payload = {"asset": BP, "node_count": len(list(editor.list_all_nodes())), "records": records}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(OUT + ".tmp", OUT)
unreal.log("REDMMO_R13_PAWN_GRAPH_PROBE PASS")
