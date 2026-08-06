"""Read-only UE Python trace API inventory for the R12 surface probe."""

import json
import os
import unreal


OUT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12_20260802\probe_unreal_trace_api_r12.json"
if os.path.exists(OUT):
    raise RuntimeError("R12 trace API probe no-clobber failed")

result = {
    "trace_type_query": [name for name in dir(unreal.TraceTypeQuery) if not name.startswith("_")],
    "collision_channel": [name for name in dir(unreal.CollisionChannel) if not name.startswith("_")],
    "system_library_trace_methods": [
        name for name in dir(unreal.SystemLibrary) if "trace" in name.lower()
    ],
    "kismet_system_library_trace_methods": [
        name for name in dir(unreal.KismetSystemLibrary) if "trace" in name.lower()
    ] if hasattr(unreal, "KismetSystemLibrary") else [],
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as handle:
    json.dump(result, handle, indent=2, sort_keys=True)
    handle.write("\n")
unreal.log("REDMMO_R12_TRACE_API_PROBE PASS")
