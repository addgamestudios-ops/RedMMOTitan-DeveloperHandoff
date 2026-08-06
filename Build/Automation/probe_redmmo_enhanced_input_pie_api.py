"""Read-only dump of the live PIE Enhanced Input injection API."""

import json
import os
import unreal


output = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_Flight_R11_20260802\probe_enhanced_input_pie_api.json"
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
world = editor.get_game_world()
controller = unreal.GameplayStatics.get_player_controller(world, 0) if world else None
local_player = controller.get_editor_property("player") if controller else None
subsystem = None
errors = []
if controller:
    for name in ("get_local_player_subsystem", "get_enhanced_input_local_player_subsystem"):
        try:
            method = getattr(controller, name, None)
            if callable(method):
                subsystem = method()
                break
        except Exception as exc:
            errors.append(f"{name}: {exc}")
if subsystem is None and controller:
    try:
        subsystem = unreal.SubsystemBlueprintLibrary.get_local_player_subsystem_from_player_controller(
            controller, unreal.EnhancedInputLocalPlayerSubsystem
        )
    except Exception as exc:
        errors.append(f"SubsystemBlueprintLibrary: {exc}")

payload = {
    "world": world.get_path_name() if world else None,
    "controller": controller.get_path_name() if controller else None,
    "controller_dir": sorted(name for name in dir(controller) if not name.startswith("_")) if controller else [],
    "local_player": str(local_player),
    "subsystem": subsystem.get_path_name() if subsystem else None,
    "subsystem_dir": sorted(name for name in dir(subsystem) if not name.startswith("_")) if subsystem else [],
    "enhanced_subsystem_class_dir": sorted(
        name for name in dir(unreal.EnhancedInputLocalPlayerSubsystem) if not name.startswith("_")
    ),
    "input_action_value_dir": sorted(
        name for name in dir(unreal.InputActionValue) if not name.startswith("_")
    ) if hasattr(unreal, "InputActionValue") else [],
    "errors": errors,
}
temporary = output + ".tmp"
os.makedirs(os.path.dirname(output), exist_ok=True)
with open(temporary, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True, default=str)
    handle.write("\n")
os.replace(temporary, output)
unreal.log("REDMMO_ENHANCED_INPUT_PIE_API_PROBE_DONE")
