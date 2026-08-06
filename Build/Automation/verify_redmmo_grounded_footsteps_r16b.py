"""Fresh-reload verification for the project-owned R16B footstep gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
SOURCE_ABP = "/Game/SoStylized/Demo/Pawn/Mannequin/Animations/ThirdPerson_AnimBP"
TARGET_ABP = "/Game/RedMMO/Gameplay/Player/Animation/ABP_RedPlanetGroundedAudio_R16"
PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
SOURCE_FILE = Path(
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\SoStylized\Demo\Pawn"
    r"\Mannequin\Animations\ThirdPerson_AnimBP.uasset"
)
TARGET_FILE = Path(
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player"
    r"\Animation\ABP_RedPlanetGroundedAudio_R16.uasset"
)
PAWN_FILE = Path(
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player"
    r"\BP_RedPlanetCharacter_R11.uasset"
)
MAP_FILE = Path(
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps"
    r"\RedMMO_PPG_HomeWorld.umap"
)
HELPER_FILE = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomeStylizedRegion_R07_20260801_163147"
    r"\r07_character_ship_helpers.py"
)
RESULT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R16B_GroundedFootsteps_20260803_004400"
    r"\verify_redmmo_grounded_footsteps_r16b_result.json"
)
EXPECTED = {
    str(SOURCE_FILE): "6E4FCBE46EF2CD932DF12A45E7EC456F487372D70E171FC36699EABE99AB7BB9",
    str(TARGET_FILE): "50F31A9AAD43F46FBC2620E670810EB18B5AA565CB89758BB9133BD3FA490758",
    str(PAWN_FILE): "E20639B7DDA6C7D667E20FBB8201B1F12BC217281D17A56E6FAABB0FFB626351",
    str(MAP_FILE): "1821ED915E924085A2D6B3E1A85984A0F207C116EFF32AC974E8F0B7CD217F87",
    str(HELPER_FILE): "4688EEDB30C1995AD67CEDE46884B652400B5463F2787E3D85EDA4378B269ECE",
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
PROVIDER_PORTS = (5353, 8000, 8765)
_EXIT = {"handle": None}


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value) -> str | None:
    if value is None:
        return None
    path = str(value.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    if "." in leaf:
        path = path.rsplit(".", 1)[0]
    if path.endswith("_C"):
        path = path[:-2]
    return path


def dirty_packages() -> dict[str, list[str]]:
    return {
        "content": sorted(
            {item.get_path_name() for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
        ),
        "maps": sorted(
            {item.get_path_name() for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}
        ),
    }


def provider_gate() -> dict[str, bool]:
    closed = {}
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            closed[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(closed.values()), "AI/MCP/provider listener is active")
    return closed


def schedule_exit(delay: float = 6.0) -> None:
    started = time.monotonic()

    def tick(_delta: float) -> None:
        if time.monotonic() - started < delay:
            return
        handle = _EXIT.get("handle")
        if handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(handle)
            except Exception:
                pass
            _EXIT["handle"] = None
        unreal.SystemLibrary.quit_editor()

    _EXIT["handle"] = unreal.register_slate_post_tick_callback(tick)


def load_helper():
    spec = importlib.util.spec_from_file_location("redmmo_r16b_verify_helpers", str(HELPER_FILE))
    require(spec is not None and spec.loader is not None, "R07 helper import unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pin(node, name: str, direction):
    normalized = name.lower().replace(" ", "")
    matches = [
        item for item in list(node.list_all_pins())
        if str(item.get_pin_name()).lower().replace(" ", "") == normalized
        and item.get_pin_direction() == direction
    ]
    require(len(matches) == 1, f"Ambiguous pin {name} on {node.get_node_title()}: {len(matches)}")
    return matches[0]


def links(pin_value):
    return list(pin_value.list_connected_pins())


def linked_exactly(pin_value, expected) -> bool:
    values = links(pin_value)
    return len(values) == 1 and bool(values[0].is_same_native_pin(expected))


def find_exact_node(editor, title: str, node_class: str, x: int, y: int):
    matches = []
    for node in list(editor.list_all_nodes()):
        position = node.get_node_pos()
        if (
            str(node.get_node_title()) == title
            and node.get_class().get_name() == node_class
            and int(position.x) == x
            and int(position.y) == y
        ):
            matches.append(node)
    require(len(matches) == 1, f"Expected exact node {title}@({x},{y}), found {len(matches)}")
    return matches[0]


def verify_graph(target) -> dict:
    editor = unreal.BlueprintGraphEditor.get_graph_editor_by_name(target, unreal.Name("EventGraph"))
    require(editor is not None, "R16B target EventGraph unavailable")
    event_walk = find_exact_node(editor, "AnimNotify_Footstep", "K2Node_Event", -1152, 509)
    sound_walk = find_exact_node(editor, "PlaySound2D", "K2Node_CallFunction", -896, 512)
    event_run = find_exact_node(editor, "AnimNotify_FootstepRun", "K2Node_Event", -304, 512)
    sound_run = find_exact_node(editor, "PlaySound2D", "K2Node_CallFunction", -48, 512)

    grounded_nodes = [
        node for node in list(editor.list_all_nodes())
        if str(node.get_node_title()) == "IsMovingOnGround"
        and node.get_class().get_name() == "K2Node_CallFunction"
    ]
    require(len(grounded_nodes) == 1, f"Expected one IsMovingOnGround node, found {len(grounded_nodes)}")
    grounded = grounded_nodes[0]
    grounded_out = pin(grounded, "ReturnValue", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    grounded_self = pin(grounded, "self", unreal.EdGraphPinDirection.EGPD_INPUT)
    movement_outputs = links(grounded_self)
    require(len(movement_outputs) == 1, "IsMovingOnGround self must have one movement source")
    movement = movement_outputs[0].get_owning_node()
    require(str(movement.get_node_title()) == "GetMovementComponent", "Ground query movement node drifted")
    movement_self = pin(movement, "self", unreal.EdGraphPinDirection.EGPD_INPUT)
    owner_outputs = links(movement_self)
    require(len(owner_outputs) == 1, "GetMovementComponent self must have one pawn source")
    owner = owner_outputs[0].get_owning_node()
    require(str(owner.get_node_title()) == "TryGetPawnOwner", "Ground query pawn node drifted")

    records = []
    for label, event, sound in (("walk", event_walk, sound_walk), ("run", event_run, sound_run)):
        event_then = pin(event, "then", unreal.EdGraphPinDirection.EGPD_OUTPUT)
        sound_execute = pin(sound, "execute", unreal.EdGraphPinDirection.EGPD_INPUT)
        branch_inputs = links(event_then)
        require(len(branch_inputs) == 1, f"{label} notify must feed one branch")
        branch = branch_inputs[0].get_owning_node()
        require(branch.get_class().get_name() == "K2Node_IfThenElse", f"{label} notify target is not Branch")
        branch_execute = pin(branch, "execute", unreal.EdGraphPinDirection.EGPD_INPUT)
        branch_condition = pin(branch, "Condition", unreal.EdGraphPinDirection.EGPD_INPUT)
        branch_true = pin(branch, "then", unreal.EdGraphPinDirection.EGPD_OUTPUT)
        branch_false = pin(branch, "else", unreal.EdGraphPinDirection.EGPD_OUTPUT)
        require(linked_exactly(event_then, branch_execute), f"{label} notify -> branch readback failed")
        require(linked_exactly(branch_condition, grounded_out), f"{label} grounded condition readback failed")
        require(linked_exactly(branch_true, sound_execute), f"{label} true -> sound readback failed")
        require(linked_exactly(sound_execute, branch_true), f"{label} sound execute readback failed")
        require(not links(branch_false), f"{label} false path must be silent")
        records.append({
            "notify": label,
            "condition": "IsMovingOnGround",
            "true": "PlaySound2D",
            "false": "unconnected_silent",
        })
    require(len(links(grounded_out)) == 2, "IsMovingOnGround must feed exactly two Branch conditions")

    errors = []
    warnings = []
    for graph in list(unreal.BlueprintEditorLibrary.list_graphs(target)):
        graph_editor = unreal.BlueprintGraphEditor.get_graph_editor(graph)
        errors.extend(f"{graph.get_name()}::{node.get_node_title()}" for node in graph_editor.list_nodes_with_errors())
        warnings.extend(f"{graph.get_name()}::{node.get_node_title()}" for node in graph_editor.list_nodes_with_warnings())
    require(not errors, "R16B target graph errors: " + str(errors))
    return {
        "ground_query": "TryGetPawnOwner -> GetMovementComponent -> IsMovingOnGround",
        "notify_paths": records,
        "graph_errors": errors,
        "graph_warnings": warnings,
    }


def verify_pawn(target) -> dict:
    pawn = unreal.EditorAssetLibrary.load_asset(PAWN)
    require(isinstance(pawn, unreal.Blueprint), "R11 pawn failed to reload")
    helper = load_helper()
    records = [
        item for item in helper._subobject_records(pawn)
        if item["is_component"]
        and isinstance(item["object_for_blueprint"], unreal.SkeletalMeshComponent)
        and item["variable"] in ("Mesh", "CharacterMesh0")
    ]
    unique = {}
    for record in records:
        unique[id(record["object_for_blueprint"])] = record["object_for_blueprint"]
    require(len(unique) == 1, f"R11 pawn mesh component is ambiguous: {len(unique)}")
    mesh = list(unique.values())[0]
    require(asset_path(mesh.get_editor_property("anim_class")) == TARGET_ABP, "R16B pawn AnimBP rebind did not persist")
    return {
        "component": mesh.get_path_name(),
        "anim_blueprint": asset_path(mesh.get_editor_property("anim_class")),
        "visible": bool(mesh.get_editor_property("visible")),
        "hidden_in_game": bool(mesh.get_editor_property("hidden_in_game")),
    }


def main() -> dict:
    require(not RESULT.exists(), f"No-clobber result exists: {RESULT}")
    actual_project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    require(unreal.Paths.is_same_path(actual_project, PROJECT), "Wrong project: " + actual_project)
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    require(not level.is_in_play_in_editor(), "R16B verification refused during PIE")
    require(dirty_packages() == {"content": [], "maps": []}, "Dirty packages before R16B verification")
    for path, expected in EXPECTED.items():
        require(Path(path).exists(), "Required file missing: " + path)
        require(sha256(path) == expected, "R16B verification hash drift: " + path)
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint drift: " + path)
    ports = provider_gate()

    target = unreal.EditorAssetLibrary.load_asset(TARGET_ABP)
    require(target is not None and target.get_class().get_name() == "AnimBlueprint", "R16B target failed to reload")
    graph = verify_graph(target)
    pawn = verify_pawn(target)

    require(unreal.EditorLevelLibrary.load_level(MAP), "Unable to fresh-reload RedMMO home map")
    world = unreal.EditorLevelLibrary.get_editor_world()
    current_map = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
    require(current_map == MAP, "Wrong map after fresh reload: " + current_map)
    actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
    rejected_water = [actor for actor in actors if actor.get_actor_label() == "RedMMO_StylizedPilot_OasisWater_R06"]
    require(not rejected_water, "Rejected R06 square water plane returned")
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECK")
    time.sleep(0.5)
    require(dirty_packages() == {"content": [], "maps": []}, "R16B verification dirtied packages")
    for path, expected in EXPECTED.items():
        require(sha256(path) == expected, "R16B verification changed file: " + path)
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint changed during verification: " + path)

    return {
        "schema": "redmmo.r16b.grounded_footsteps.verify.v1",
        "status": "PASS_FRESH_RELOAD_GRAPH_PAWN_MAPCHECK_ISSUED",
        "completed_utc": now(),
        "project": PROJECT,
        "map": MAP,
        "map_sha256": sha256(MAP_FILE),
        "target_anim_blueprint": TARGET_ABP,
        "target_sha256": sha256(TARGET_FILE),
        "pawn_sha256": sha256(PAWN_FILE),
        "vendor_sha256_unchanged": sha256(SOURCE_FILE),
        "graph": graph,
        "pawn": pawn,
        "map_actor_count": len(actors),
        "rejected_r06_water_actor_count": len(rejected_water),
        "mapcheck_command_issued": True,
        "mapcheck_log_parse_required": True,
        "dirty_packages": {"content": [], "maps": []},
        "provider_ports_closed": ports,
        "protected_hashes_unchanged": True,
        "claim_limit": "Fresh serialized/static readback only. Audible behavior still requires real PIE audio evidence.",
    }


payload = {"schema": "redmmo.r16b.grounded_footsteps.verify.v1", "started_utc": now(), "status": "RUNNING"}
try:
    payload = main()
except Exception as exc:
    payload.update({
        "status": "FAIL",
        "completed_utc": now(),
        "error": repr(exc),
        "traceback": traceback.format_exc(),
        "dirty_packages": dirty_packages(),
    })
finally:
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    with RESULT.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    unreal.log("REDMMO_R16B_GROUNDED_FOOTSTEPS_VERIFY " + payload["status"])
    schedule_exit()
