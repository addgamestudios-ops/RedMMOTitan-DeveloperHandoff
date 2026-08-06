#!/usr/bin/env python3
"""Create merge-safe hub stub levels under /Game/RedMMO/Maps/Hubs (Unreal Python).

Run:
  UnrealEditor-Cmd.exe <Project.uproject> -ExecutePythonScript=<this file> -unattended -nop4 -nosplash
"""
from __future__ import annotations

import unreal

HUB_DIR = "/Game/RedMMO/Maps/Hubs"
MAPS = (
    "L_Hub_Persistent",
    "L_Hub_Env_Visuals",
    "L_Hub_Gameplay_Logic",
)
STREAM_INTO_PERSISTENT = (
    "L_Hub_Env_Visuals",
    "L_Hub_Gameplay_Logic",
)


def ensure_world(name: str) -> unreal.World | None:
    path = f"{HUB_DIR}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.log(f"[HubStubs] exists: {path}")
        return unreal.EditorAssetLibrary.load_asset(path)
    factory = unreal.WorldFactory()
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    asset = asset_tools.create_asset(name, HUB_DIR, unreal.World, factory)
    if not asset:
        unreal.log_error(f"[HubStubs] failed to create {path}")
        return None
    unreal.EditorAssetLibrary.save_asset(path)
    unreal.log(f"[HubStubs] created: {path}")
    return asset


def wire_streaming(persistent_name: str, child_names: tuple[str, ...]) -> None:
    """Best-effort: add always-loaded streaming level refs on Persistent."""
    pers_path = f"{HUB_DIR}/{persistent_name}"
    if not unreal.EditorAssetLibrary.does_asset_exist(pers_path):
        unreal.log_error(f"[HubStubs] missing persistent {pers_path}")
        return

    # Load persistent as current editor world for streaming edits.
    unreal.EditorLoadingAndSavingUtils.load_map(pers_path)
    world = unreal.EditorLevelLibrary.get_editor_world()
    if not world:
        unreal.log_error("[HubStubs] no editor world after load")
        return

    existing = set()
    try:
        for streaming in world.get_streaming_levels():
            # Soft object path package name
            try:
                pkg = streaming.get_world_asset_package_f_name()
                existing.add(str(pkg))
            except Exception:
                pass
    except Exception as exc:
        unreal.log_warning(f"[HubStubs] could not enumerate streaming levels: {exc}")

    for child in child_names:
        child_path = f"{HUB_DIR}/{child}"
        package_name = child_path
        if any(child in e for e in existing):
            unreal.log(f"[HubStubs] streaming already present: {child}")
            continue
        try:
            # UE 5.x: EditorLevelUtils.add_level_to_world
            streaming_level = unreal.EditorLevelUtils.add_level_to_world(
                world,
                child_path,
                unreal.LevelStreamingDynamic,
            )
            if streaming_level:
                streaming_level.set_editor_property("should_be_loaded", True)
                streaming_level.set_editor_property("should_be_visible", True)
                unreal.log(f"[HubStubs] streamed into Persistent: {child_path}")
            else:
                unreal.log_warning(f"[HubStubs] add_level_to_world returned None for {child_path}")
        except Exception as exc:
            unreal.log_warning(
                f"[HubStubs] streaming wire skipped for {child_path}: {exc}. "
                "Create empty maps; wire Levels window manually if needed."
            )

    try:
        unreal.EditorLevelLibrary.save_current_level()
        unreal.EditorAssetLibrary.save_asset(pers_path)
    except Exception as exc:
        unreal.log_warning(f"[HubStubs] save persistent warning: {exc}")


def main() -> None:
    unreal.EditorAssetLibrary.make_directory(HUB_DIR)
    for name in MAPS:
        ensure_world(name)
    wire_streaming("L_Hub_Persistent", STREAM_INTO_PERSISTENT)
    unreal.EditorAssetLibrary.save_directory(HUB_DIR, only_if_is_dirty=False, recursive=True)
    unreal.log("[HubStubs] done")


if __name__ == "__main__":
    main()
