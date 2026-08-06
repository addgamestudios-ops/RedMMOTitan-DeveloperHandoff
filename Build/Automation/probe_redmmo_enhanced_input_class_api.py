"""Read-only UE 5.8 Python reflection probe for Enhanced Input access."""

import json
import os
import unreal


OUTPUT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_Flight_R11_20260802"
    r"\probe_enhanced_input_class_api.json"
)


def names(value):
    return sorted(name for name in dir(value) if not name.startswith("_"))


payload = {
    "unreal_subsystem_names": sorted(
        name for name in dir(unreal) if "subsystem" in name.lower() or "localplayer" in name.lower()
    ),
    "local_player_class": names(unreal.LocalPlayer) if hasattr(unreal, "LocalPlayer") else [],
    "player_controller_class": names(unreal.PlayerController) if hasattr(unreal, "PlayerController") else [],
    "enhanced_input_local_player_subsystem_class": (
        names(unreal.EnhancedInputLocalPlayerSubsystem)
        if hasattr(unreal, "EnhancedInputLocalPlayerSubsystem")
        else []
    ),
    "gameplay_statics_class": names(unreal.GameplayStatics),
}
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
temporary = OUTPUT + ".tmp"
with open(temporary, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(temporary, OUTPUT)
unreal.log("REDMMO_ENHANCED_INPUT_CLASS_API_PROBE_DONE")
