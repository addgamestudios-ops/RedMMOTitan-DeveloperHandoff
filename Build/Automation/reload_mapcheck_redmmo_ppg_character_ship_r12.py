"""Reload and read back the serialized R12 character/ship slice without saving."""

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
MAP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
PAWN_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset"
SHIP_BP = "/Game/RedMMO/Gameplay/World/BP_RedParkedStarSparrow_R12"
SHIP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset"
SHIP_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
EXPECTED_MAP_SHA = "B66CE7E24465CB8ADA8F53D5F31B480289415D1641726BA7C276B0907BF20133"
EXPECTED_PAWN_SHA = "8421120C7FEE24FD457775789F0758D32F8D34AC7F0ECE5DA2603CFAA146F768"
EXPECTED_SHIP_SHA = "C9FDCF7D0FE89DACE39D418B79A7951C37C699C1FEA7E485C85670B2AB864BD6"
EXPECTED_MESH = "/Game/SoStylized/Demo/Pawn/Mannequin/Character/Mesh/SK_Mannequin"
EXPECTED_ANIM = "/Game/SoStylized/Demo/Pawn/Mannequin/Animations/ThirdPerson_AnimBP"
EXPECTED_SHIP_MESH = "/Game/StarSparrow/Meshes/Examples/SM_StarSparrow01"
HELPER_FILE = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomeStylizedRegion_R07_20260801_163147"
    r"\r07_character_ship_helpers.py"
)
EXPECTED_HELPER_SHA = "4688EEDB30C1995AD67CEDE46884B652400B5463F2787E3D85EDA4378B269ECE"
ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12_20260802"
RESULT = os.path.join(ROOT, "reload_mapcheck_redmmo_ppg_character_ship_r12_result.json")
DONE = os.path.join(ROOT, "reload_mapcheck_redmmo_ppg_character_ship_r12.done")
PROVIDER_PORTS = (5353, 8000, 8765)
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


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path: str, value: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary, path)


def asset_path(asset) -> str | None:
    if asset is None:
        return None
    path = str(asset.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    if "." in leaf:
        path = path.rsplit(".", 1)[0]
    if path.endswith("_C"):
        path = path[:-2]
    return path


def dirty_packages() -> list[str]:
    packages = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    packages += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({package.get_path_name() for package in packages})


def provider_gate() -> dict[str, bool]:
    output = {}
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            output[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(output.values()), "AI/MCP/provider port is listening")
    return output


def load_helper():
    require(sha256(HELPER_FILE) == EXPECTED_HELPER_SHA, "Reviewed R07 helper hash drift")
    spec = importlib.util.spec_from_file_location("redmmo_r12_reload_helpers", HELPER_FILE)
    require(spec is not None and spec.loader is not None, "Unable to load reviewed helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> dict:
    require(not os.path.exists(RESULT) and not os.path.exists(DONE), "R12 reload no-clobber failed")
    actual_project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    require(unreal.Paths.is_same_path(actual_project, PROJECT), "Wrong project: " + actual_project)
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    require(not level.is_in_play_in_editor(), "R12 reload refused during PIE")
    require(not dirty_packages(), "Dirty packages before R12 reload: " + str(dirty_packages()))
    require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "R12 map hash drift before reload")
    require(sha256(PAWN_FILE) == EXPECTED_PAWN_SHA, "R12 pawn hash drift before reload")
    require(sha256(SHIP_FILE) == EXPECTED_SHIP_SHA, "R12 ship hash drift before reload")
    ports = provider_gate()
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint drift: " + path)

    require(unreal.EditorLevelLibrary.load_level(MAP), "Unable to reload R12 home map")
    world = unreal.EditorLevelLibrary.get_editor_world()
    current = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
    require(current == MAP, "Wrong map after reload: " + current)
    actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
    ships = [actor for actor in actors if actor.get_actor_label() == SHIP_LABEL]
    require(len(ships) == 1, "R12 ship actor count after reload is not one")
    ship_actor = ships[0]
    components = list(ship_actor.get_components_by_class(unreal.StaticMeshComponent))
    components = [component for component in components if component.get_editor_property("static_mesh") is not None]
    require(len(components) == 1, "R12 ship visual component count is not one")
    require(asset_path(components[0].get_editor_property("static_mesh")) == EXPECTED_SHIP_MESH,
            "R12 ship mesh readback mismatch")
    require(not ship_actor.get_actor_enable_collision(), "R12 visual ship collision unexpectedly enabled")

    helper = load_helper()
    pawn = unreal.EditorAssetLibrary.load_asset(PAWN)
    require(isinstance(pawn, unreal.Blueprint), "R12 pawn failed to reload")
    records = helper._subobject_records(pawn)
    mesh_records = [record for record in records
                    if record["is_component"]
                    and isinstance(record["object_for_blueprint"], unreal.SkeletalMeshComponent)
                    and record["variable"] in ("Mesh", "CharacterMesh0")]
    unique = {}
    for record in mesh_records:
        unique[id(record["object_for_blueprint"])] = record["object_for_blueprint"]
    require(len(unique) == 1, "R12 pawn mesh component readback is ambiguous")
    mesh_component = list(unique.values())[0]
    require(asset_path(mesh_component.get_skeletal_mesh_asset()) == EXPECTED_MESH,
            "R12 mannequin mesh readback mismatch")
    anim_class = mesh_component.get_editor_property("anim_class")
    require(asset_path(anim_class) == EXPECTED_ANIM, "R12 mannequin AnimBP readback mismatch")
    require(not bool(mesh_component.get_editor_property("hidden_in_game")),
            "R12 mannequin is hidden in game")
    require(bool(mesh_component.get_editor_property("visible")), "R12 mannequin is not visible")

    unreal.SystemLibrary.execute_console_command(world, "MAP CHECK")
    time.sleep(0.25)
    require(not dirty_packages(), "R12 reload/MapCheck dirtied packages: " + str(dirty_packages()))
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint changed during reload: " + path)
    return {
        "schema": "redmmo.ppg_character_ship.r12.reload_mapcheck.v1",
        "status": "PASS_FRESH_RELOAD_SERIALIZED_READBACK_MAPCHECK_ISSUED",
        "project": PROJECT,
        "map": MAP,
        "map_sha256": sha256(MAP_FILE),
        "pawn_sha256": sha256(PAWN_FILE),
        "ship_blueprint_sha256": sha256(SHIP_FILE),
        "provider_ports_closed": ports,
        "dirty_packages": [],
        "protected_hashes_unchanged": True,
        "mapcheck_command_issued": True,
        "mapcheck_log_parse_required": True,
        "visible_character": {
            "mesh": EXPECTED_MESH,
            "anim_blueprint": EXPECTED_ANIM,
            "hidden_in_game": False,
            "visible": True,
        },
        "parked_ship": {
            "actor": ship_actor.get_path_name(),
            "label": SHIP_LABEL,
            "mesh": EXPECTED_SHIP_MESH,
            "collision": "disabled",
            "visual_only": True,
        },
        "map_saved_by_validation": False,
    }


try:
    _result = main()
except Exception as _error:
    _result = {
        "schema": "redmmo.ppg_character_ship.r12.reload_mapcheck.v1",
        "status": "FAIL",
        "error": str(_error),
        "traceback": traceback.format_exc(),
        "map_saved_by_validation": False,
    }
atomic_json(RESULT, _result)
with open(DONE, "w", encoding="utf-8") as _handle:
    _handle.write(_result["status"] + ("\n" if _result["status"].startswith("PASS") else ": " + _result.get("error", "") + "\n"))
if _result["status"].startswith("PASS"):
    unreal.log("REDMMO_R12_RELOAD_MAPCHECK PASS")
else:
    unreal.log_error("REDMMO_R12_RELOAD_MAPCHECK FAIL " + _result.get("error", ""))

