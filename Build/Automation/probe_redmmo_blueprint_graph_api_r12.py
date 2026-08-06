"""Read-only UE 5.8 BlueprintGraphEditor API signature probe."""

import json
import os

import unreal


OUT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12V3_20260802"
    r"\probe_redmmo_blueprint_graph_api_r12.json"
)
names = [
    "add_call_function_node",
    "find_event_node",
    "add_custom_event_node",
    "add_branch_node",
    "create_node_from_name",
]
payload = {
    name: str(getattr(unreal.BlueprintGraphEditor, name).__doc__)
    for name in names
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(OUT + ".tmp", OUT)
unreal.log("REDMMO_R12_GRAPH_API_PROBE PASS")
