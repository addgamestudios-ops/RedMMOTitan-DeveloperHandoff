"""Fresh reload and serialized readback for the R12V2 visual correction."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import time
import traceback

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
SHIP_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
SHIP_MESH = "/Game/StarSparrow/Meshes/Examples/SM_StarSparrow01"
EXPECTED = {
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap":
        "013873CF751E7B1A7A3C042C2FC3CD6527760CB6B0A1B0416A8C69AAA31F4BC6",
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset":
        "65A0413D1921F8ED2F6E4E3893B1C6B5CA3A0D1F7BCFC9AF9BF987940ECDC11E",
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset":
        "C9FDCF7D0FE89DACE39D418B79A7951C37C699C1FEA7E485C85670B2AB864BD6",
}
PROTECTED = {
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap":
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap":
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap":
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap":
        "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}
HELPER = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomeStylizedRegion_R07_20260801_163147"
    r"\r07_character_ship_helpers.py"
)
ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12V2_20260802"
RESULT = os.path.join(ROOT, "reload_mapcheck_redmmo_ppg_character_ship_r12v2_result.json")
DONE = os.path.join(ROOT, "reload_mapcheck_redmmo_ppg_character_ship_r12v2.done")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(asset):
    if asset is None:
        return None
    value = asset.get_path_name().split(":", 1)[0]
    leaf = value.rsplit("/", 1)[-1]
    if "." in leaf:
        value = value.rsplit(".", 1)[0]
    return value[:-2] if value.endswith("_C") else value


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({value.get_path_name() for value in values})


def provider_gate():
    state = {}
    for port in (5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            state[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(state.values()), "Provider/MCP listener unexpectedly open")
    return state


def load_helper():
    spec = importlib.util.spec_from_file_location("redmmo_r12v2_reload_helper", HELPER)
    require(spec is not None and spec.loader is not None, "R07 helper unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unique_component(bp, helper, component_class, variable):
    matches = {}
    for record in helper._subobject_records(bp):
        component = record["object_for_blueprint"]
        if record["variable"] == variable and isinstance(component, component_class):
            matches[id(record["associated"] or component)] = component
    require(len(matches) == 1, f"Serialized {variable} component is ambiguous")
    return next(iter(matches.values()))


def main():
    require(not os.path.exists(RESULT) and not os.path.exists(DONE), "R12V2 reload no-clobber failed")
    actual_project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    require(unreal.Paths.is_same_path(actual_project, PROJECT), "Wrong project")
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    require(not level.is_in_play_in_editor(), "Refusing R12V2 reload during PIE")
    require(not dirty_packages(), "Dirty packages before reload: " + str(dirty_packages()))
    for path, expected in EXPECTED.items():
        require(sha256(path) == expected, "R12V2 serialized hash drift: " + path)
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint drift: " + path)
    ports = provider_gate()
    require(unreal.EditorLevelLibrary.load_level(MAP), "Unable to reload home map")
    world = unreal.EditorLevelLibrary.get_editor_world()
    current = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
    require(current == MAP, "Wrong map after reload: " + current)
    actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
    ships = [actor for actor in actors if actor.get_actor_label() == SHIP_LABEL]
    require(len(ships) == 1, "R12 ship actor count is not one")
    ship = ships[0]
    ship_components = [component for component in ship.get_components_by_class(unreal.StaticMeshComponent)
                       if component.get_editor_property("static_mesh") is not None]
    require(len(ship_components) == 1, "R12 ship mesh component count is not one")
    require(asset_path(ship_components[0].get_editor_property("static_mesh")) == SHIP_MESH,
            "R12 ship mesh mismatch")
    require(not ship.get_actor_enable_collision(), "Visual-only ship collision unexpectedly enabled")

    helper = load_helper()
    pawn = unreal.EditorAssetLibrary.load_asset(PAWN)
    require(isinstance(pawn, unreal.Blueprint), "R11 pawn unavailable after reload")
    root = unique_component(pawn, helper, unreal.CapsuleComponent, "CapsuleComponent")
    arm = unique_component(pawn, helper, unreal.SpringArmComponent, "SpringArm")
    camera = unique_component(pawn, helper, unreal.CameraComponent, "Camera")
    require(arm.get_attach_parent() == root, "Reloaded SpringArm parent mismatch")
    require(camera.get_attach_parent() == arm, "Reloaded Camera parent mismatch")
    require(str(camera.get_attach_socket_name()) == "SpringEndpoint", "Reloaded camera socket mismatch")
    require(float(arm.get_editor_property("target_arm_length")) == 400.0,
            "Reloaded spring arm length mismatch")
    require(float(camera.get_editor_property("field_of_view")) == 90.0,
            "Reloaded camera FOV mismatch")
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECK")
    time.sleep(0.25)
    require(not dirty_packages(), "Reload/MapCheck dirtied packages: " + str(dirty_packages()))
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint changed during reload: " + path)
    return {
        "schema": "redmmo.ppg_character_ship.r12v2.reload_mapcheck.v1",
        "status": "PASS_FRESH_RELOAD_SERIALIZED_READBACK_MAPCHECK_ISSUED",
        "map": MAP,
        "provider_ports_closed": ports,
        "dirty_packages": [],
        "camera": {
            "spring_arm_parent": root.get_path_name(),
            "camera_parent": arm.get_path_name(),
            "camera_socket": str(camera.get_attach_socket_name()),
            "target_arm_length": float(arm.get_editor_property("target_arm_length")),
            "field_of_view": float(camera.get_editor_property("field_of_view")),
        },
        "ship": {
            "actor": ship.get_path_name(),
            "mesh": SHIP_MESH,
            "collision": "disabled",
            "visual_only": True,
        },
        "protected_hashes_unchanged": True,
        "map_saved_by_validation": False,
        "mapcheck_command_issued": True,
    }


try:
    payload = main()
except Exception as error:
    payload = {
        "schema": "redmmo.ppg_character_ship.r12v2.reload_mapcheck.v1",
        "status": "FAIL",
        "error": str(error),
        "traceback": traceback.format_exc(),
        "map_saved_by_validation": False,
    }
os.makedirs(ROOT, exist_ok=True)
with open(RESULT + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(RESULT + ".tmp", RESULT)
with open(DONE, "w", encoding="utf-8") as handle:
    handle.write(payload["status"] + "\n")
if payload["status"].startswith("PASS"):
    unreal.log("REDMMO_R12V2_RELOAD_MAPCHECK PASS")
else:
    unreal.log_error("REDMMO_R12V2_RELOAD_MAPCHECK FAIL " + payload.get("error", ""))
