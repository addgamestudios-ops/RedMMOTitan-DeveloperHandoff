"""Read-only live PIE probe for a Python route to Enhanced Input injection."""

import json
import os
import time
import traceback
import unreal


OUTPUT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_Flight_R11_20260802"
    r"\probe_enhanced_input_live_access.json"
)


def names(value):
    return sorted(name for name in dir(value) if not name.startswith("_"))


def atomic(value):
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    temporary = OUTPUT + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary, OUTPUT)


class Probe:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.started = time.monotonic()
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.level.editor_request_begin_play()

    def finish(self, value):
        atomic(value)
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.log("REDMMO_ENHANCED_INPUT_LIVE_ACCESS_PROBE_DONE")

    def tick(self, _delta):
        try:
            if time.monotonic() - self.started > 90.0:
                raise RuntimeError("PIE startup timeout")
            world = self.editor.get_game_world()
            if world is None or not self.level.is_in_play_in_editor():
                return
            controller = unreal.GameplayStatics.get_player_controller(world, 0)
            if controller is None:
                return
            player = controller.get_editor_property("player")
            player_input = controller.get_editor_property("player_input")
            value = {
                "status": "PASS",
                "world": world.get_path_name(),
                "controller": controller.get_path_name(),
                "player": player.get_path_name() if player else None,
                "player_class": player.get_class().get_path_name() if player else None,
                "player_dir": names(player) if player else [],
                "player_input": player_input.get_path_name() if player_input else None,
                "player_input_class": player_input.get_class().get_path_name() if player_input else None,
                "player_input_dir": names(player_input) if player_input else [],
                "unreal_object_access_names": sorted(
                    name for name in dir(unreal)
                    if "object" in name.lower() or "iterator" in name.lower() or "subsystem" in name.lower()
                ),
            }
            self.finish(value)
        except Exception as exc:
            self.finish({
                "status": "FAIL",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            })


_REDMMO_ENHANCED_INPUT_LIVE_ACCESS_PROBE = Probe()
