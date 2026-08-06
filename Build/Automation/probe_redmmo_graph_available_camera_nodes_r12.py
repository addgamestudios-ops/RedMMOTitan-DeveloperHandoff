"""Read-only filter of UE 5.8 Blueprint node descriptors for camera init."""

import json
import os

import unreal


PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
OUT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12V3_20260802"
    r"\probe_redmmo_graph_available_camera_nodes_r12.json"
)
bp = unreal.EditorAssetLibrary.load_asset(PAWN)
editor = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, unreal.Name("EventGraph"))
if editor is None:
    raise RuntimeError("EventGraph editor unavailable")
matches = []
for item in list(editor.list_available_nodes([])):
    text = str(item)
    lowered = text.lower()
    if any(token in lowered for token in (
        "control rotation", "actor rotation", "controller", "gravity world rotation"
    )):
        matches.append({
            "text": text,
            "class": item.get_class().get_path_name() if hasattr(item, "get_class") else None,
            "dir": [name for name in dir(item) if not name.startswith("_")],
        })
payload = {"match_count": len(matches), "matches": matches[:500]}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(OUT + ".tmp", OUT)
unreal.log("REDMMO_R12_AVAILABLE_CAMERA_NODES_PROBE PASS")
