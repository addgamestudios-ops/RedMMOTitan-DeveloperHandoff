"""Build the project-owned R16B grounded-only footstep audio gate.

This transaction duplicates the vendor AnimBP, rewires only the two audited
footstep notify execution edges through IsMovingOnGround, and rebinds the
existing R11 pawn mesh to the project-owned duplicate. It never edits the
vendor package, map, PPG data, input mapping, water, or vehicle assets.
"""

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
ROLLBACK_MANIFEST = Path(
    r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_R16B_GroundedFootsteps_20260803_005400_A01"
    r"\manifest.json"
)
ROLLBACK_PAWN = ROLLBACK_MANIFEST.parent / "BP_RedPlanetCharacter_R11.pre_r16b.uasset"
RESULT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R16B_GroundedFootsteps_20260803_004400"
    r"\build_redmmo_grounded_footsteps_r16b_result.json"
)

EXPECTED = {
    str(SOURCE_FILE): "6E4FCBE46EF2CD932DF12A45E7EC456F487372D70E171FC36699EABE99AB7BB9",
    str(PAWN_FILE): "65A0413D1921F8ED2F6E4E3893B1C6B5CA3A0D1F7BCFC9AF9BF987940ECDC11E",
    str(MAP_FILE): "1821ED915E924085A2D6B3E1A85984A0F207C116EFF32AC974E8F0B7CD217F87",
    str(HELPER_FILE): "4688EEDB30C1995AD67CEDE46884B652400B5463F2787E3D85EDA4378B269ECE",
    str(ROLLBACK_PAWN): "65A0413D1921F8ED2F6E4E3893B1C6B5CA3A0D1F7BCFC9AF9BF987940ECDC11E",
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
    spec = importlib.util.spec_from_file_location("redmmo_r16b_helpers", str(HELPER_FILE))
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


def same_pin(left, right) -> bool:
    return bool(left.is_same_native_pin(right))


def links(pin_value):
    return list(pin_value.list_connected_pins())


def linked_exactly(pin_value, expected) -> bool:
    values = links(pin_value)
    return len(values) == 1 and same_pin(values[0], expected)


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


def compile_blueprint(blueprint) -> dict:
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    status = blueprint.get_editor_property("status")
    accepted = {
        unreal.BlueprintStatus.BS_UP_TO_DATE,
        unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS,
    }
    require(status in accepted, f"Blueprint compile failed: {blueprint.get_path_name()} status={status}")
    errors = []
    warnings = []
    for graph in list(unreal.BlueprintEditorLibrary.list_graphs(blueprint)):
        editor = unreal.BlueprintGraphEditor.get_graph_editor(graph)
        require(editor is not None, f"No graph editor: {graph.get_path_name()}")
        errors.extend(f"{graph.get_name()}::{node.get_node_title()}" for node in editor.list_nodes_with_errors())
        warnings.extend(f"{graph.get_name()}::{node.get_node_title()}" for node in editor.list_nodes_with_warnings())
    require(not errors, f"Blueprint graph errors: {errors}")
    return {"status": str(status), "errors": errors, "warnings": warnings}


def save_asset(asset) -> None:
    require(
        unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False),
        f"Unable to save {asset.get_path_name()}",
    )


def set_node_position(node, x: int, y: int) -> None:
    try:
        node.set_node_pos(unreal.IntPoint(x, y))
    except Exception:
        pass


def build_ground_gate(target) -> dict:
    editor = unreal.BlueprintGraphEditor.get_graph_editor_by_name(target, unreal.Name("EventGraph"))
    require(editor is not None, "Target AnimBP EventGraph unavailable")

    event_walk = find_exact_node(editor, "AnimNotify_Footstep", "K2Node_Event", -1152, 509)
    sound_walk = find_exact_node(editor, "PlaySound2D", "K2Node_CallFunction", -896, 512)
    event_run = find_exact_node(editor, "AnimNotify_FootstepRun", "K2Node_Event", -304, 512)
    sound_run = find_exact_node(editor, "PlaySound2D", "K2Node_CallFunction", -48, 512)

    event_walk_then = pin(event_walk, "then", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    sound_walk_execute = pin(sound_walk, "execute", unreal.EdGraphPinDirection.EGPD_INPUT)
    event_run_then = pin(event_run, "then", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    sound_run_execute = pin(sound_run, "execute", unreal.EdGraphPinDirection.EGPD_INPUT)
    require(linked_exactly(event_walk_then, sound_walk_execute), "Walk direct exec edge drifted")
    require(linked_exactly(event_run_then, sound_run_execute), "Run direct exec edge drifted")

    try_owner = editor.add_call_function_node("/Script/Engine.AnimInstance:TryGetPawnOwner")
    get_movement = editor.add_call_function_node("/Script/Engine.Pawn:GetMovementComponent")
    is_grounded = editor.add_call_function_node("/Script/Engine.NavMovementComponent:IsMovingOnGround")
    branch_walk = editor.add_branch_node()
    branch_run = editor.add_branch_node()
    created = [try_owner, get_movement, is_grounded, branch_walk, branch_run]
    require(all(created), "One or more R16B nodes could not be created")
    set_node_position(try_owner, -1504, 736)
    set_node_position(get_movement, -1280, 736)
    set_node_position(is_grounded, -992, 736)
    set_node_position(branch_walk, -976, 496)
    set_node_position(branch_run, -128, 496)

    owner_out = pin(try_owner, "ReturnValue", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    movement_self = pin(get_movement, "self", unreal.EdGraphPinDirection.EGPD_INPUT)
    movement_out = pin(get_movement, "ReturnValue", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    grounded_self = pin(is_grounded, "self", unreal.EdGraphPinDirection.EGPD_INPUT)
    grounded_out = pin(is_grounded, "ReturnValue", unreal.EdGraphPinDirection.EGPD_OUTPUT)
    require(owner_out.try_create_connection(movement_self), "TryGetPawnOwner -> GetMovementComponent failed")
    require(movement_out.try_create_connection(grounded_self), "GetMovementComponent -> IsMovingOnGround failed")

    rewires = []
    for label, event_then, sound_execute, branch in (
        ("walk", event_walk_then, sound_walk_execute, branch_walk),
        ("run", event_run_then, sound_run_execute, branch_run),
    ):
        branch_execute = pin(branch, "execute", unreal.EdGraphPinDirection.EGPD_INPUT)
        branch_condition = pin(branch, "Condition", unreal.EdGraphPinDirection.EGPD_INPUT)
        branch_true = pin(branch, "then", unreal.EdGraphPinDirection.EGPD_OUTPUT)
        branch_false = pin(branch, "else", unreal.EdGraphPinDirection.EGPD_OUTPUT)

        event_then.break_single_pin_link(sound_execute)
        require(not links(event_then), f"{label} event still linked after exact unlink")
        require(not links(sound_execute), f"{label} sound still linked after exact unlink")
        require(event_then.try_create_connection(branch_execute), f"{label} event -> branch failed")
        require(grounded_out.try_create_connection(branch_condition), f"grounded -> {label} condition failed")
        require(branch_true.try_create_connection(sound_execute), f"{label} true -> sound failed")

        require(linked_exactly(event_then, branch_execute), f"{label} event rewire readback failed")
        require(linked_exactly(branch_execute, event_then), f"{label} branch execute readback failed")
        require(linked_exactly(branch_condition, grounded_out), f"{label} condition readback failed")
        require(linked_exactly(branch_true, sound_execute), f"{label} true output readback failed")
        require(linked_exactly(sound_execute, branch_true), f"{label} sound input readback failed")
        require(not links(branch_false), f"{label} false output must be unconnected")
        rewires.append({
            "notify": label,
            "old_direct_edge_removed": True,
            "new_edge": "AnimNotify -> Branch(IsMovingOnGround) -> PlaySound2D",
            "false_path": "unconnected_silent",
        })

    require(linked_exactly(owner_out, movement_self), "Owner chain readback failed")
    require(linked_exactly(movement_out, grounded_self), "Movement chain readback failed")
    require(len(links(grounded_out)) == 2, "Grounded output must feed exactly two branches")

    compile_report = compile_blueprint(target)
    save_asset(target)
    return {
        "nodes_created": [str(node.get_node_title()) for node in created],
        "ground_query": "TryGetPawnOwner -> GetMovementComponent -> IsMovingOnGround",
        "rewires": rewires,
        "compile": compile_report,
    }


def rebind_pawn(target) -> dict:
    pawn = unreal.EditorAssetLibrary.load_asset(PAWN)
    require(isinstance(pawn, unreal.Blueprint), "R11 pawn failed to load")
    helper = load_helper()
    records = [
        item for item in helper._subobject_records(pawn)
        if item["is_component"]
        and isinstance(item["object_for_blueprint"], unreal.SkeletalMeshComponent)
        and item["variable"] in ("Mesh", "CharacterMesh0")
    ]
    unique = {}
    for record in records:
        component = record["object_for_blueprint"]
        unique[id(component)] = component
    require(len(unique) == 1, f"R11 pawn mesh component is ambiguous: {len(unique)}")
    mesh = list(unique.values())[0]
    before_class = mesh.get_editor_property("anim_class")
    require(asset_path(before_class) == SOURCE_ABP, "R11 pawn AnimBP precondition drifted")
    mesh.modify()
    mesh.set_editor_property("anim_class", target.generated_class())
    require(asset_path(mesh.get_editor_property("anim_class")) == TARGET_ABP, "R16B AnimBP rebind readback failed")
    compile_report = compile_blueprint(pawn)
    save_asset(pawn)
    return {
        "component": mesh.get_path_name(),
        "before": asset_path(before_class),
        "after": asset_path(mesh.get_editor_property("anim_class")),
        "compile": compile_report,
    }


def main() -> dict:
    require(not RESULT.exists(), f"No-clobber result exists: {RESULT}")
    actual_project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    require(unreal.Paths.is_same_path(actual_project, PROJECT), "Wrong project: " + actual_project)
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    require(not level.is_in_play_in_editor(), "R16B refused during PIE")
    require(dirty_packages() == {"content": [], "maps": []}, "Dirty packages before R16B")
    require(ROLLBACK_MANIFEST.exists(), "R16B rollback manifest missing")
    for path, expected in EXPECTED.items():
        require(Path(path).exists(), "Required file missing: " + path)
        require(sha256(path) == expected, "R16B precondition hash drift: " + path)
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint drift: " + path)
    require(not TARGET_FILE.exists(), "R16B target package already exists")
    require(not unreal.EditorAssetLibrary.does_asset_exist(TARGET_ABP), "R16B target asset already exists")
    ports = provider_gate()

    source = unreal.EditorAssetLibrary.load_asset(SOURCE_ABP)
    require(source is not None and source.get_class().get_name() == "AnimBlueprint", "Vendor AnimBP load failed")
    unreal.EditorAssetLibrary.make_directory("/Game/RedMMO/Gameplay/Player/Animation")
    target = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_ABP, TARGET_ABP)
    require(target is not None and asset_path(target) == TARGET_ABP, "AnimBP duplication failed")

    graph = build_ground_gate(target)
    pawn = rebind_pawn(target)
    require(TARGET_FILE.exists(), "R16B target package missing after save")
    require(sha256(SOURCE_FILE) == EXPECTED[str(SOURCE_FILE)], "Vendor AnimBP changed")
    require(sha256(MAP_FILE) == EXPECTED[str(MAP_FILE)], "Home map changed during R16B")
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected checkpoint changed during R16B: " + path)
    require(dirty_packages() == {"content": [], "maps": []}, "Dirty packages remain after R16B save")

    return {
        "schema": "redmmo.r16b.grounded_footsteps.build.v1",
        "status": "PASS_STATIC_COMPILE_SAVE",
        "completed_utc": now(),
        "project": PROJECT,
        "source_vendor_anim_blueprint": SOURCE_ABP,
        "source_vendor_sha256": sha256(SOURCE_FILE),
        "target_project_anim_blueprint": TARGET_ABP,
        "target_sha256": sha256(TARGET_FILE),
        "pawn": PAWN,
        "pawn_sha256": sha256(PAWN_FILE),
        "home_map_sha256_unchanged": sha256(MAP_FILE),
        "provider_ports_closed": ports,
        "graph": graph,
        "pawn_rebind": pawn,
        "dirty_packages": {"content": [], "maps": []},
        "protected_hashes_unchanged": True,
        "claim_limit": "Static compile/save only. Audible grounded/silent-airborne behavior requires a real PIE audio test.",
    }


payload = {"schema": "redmmo.r16b.grounded_footsteps.build.v1", "started_utc": now(), "status": "RUNNING"}
try:
    payload = main()
except Exception as exc:
    payload.update({
        "status": "FAIL",
        "completed_utc": now(),
        "error": repr(exc),
        "traceback": traceback.format_exc(),
        "source_sha256": sha256(SOURCE_FILE) if SOURCE_FILE.exists() else None,
        "pawn_sha256": sha256(PAWN_FILE) if PAWN_FILE.exists() else None,
        "target_exists": TARGET_FILE.exists(),
        "dirty_packages": dirty_packages(),
    })
    if TARGET_FILE.exists() and sha256(PAWN_FILE) == EXPECTED[str(PAWN_FILE)]:
        try:
            payload["cleanup_target_deleted"] = bool(unreal.EditorAssetLibrary.delete_asset(TARGET_ABP))
        except Exception as cleanup_error:
            payload["cleanup_error"] = repr(cleanup_error)
finally:
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    with RESULT.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    unreal.log("REDMMO_R16B_GROUNDED_FOOTSTEPS " + payload["status"])
    schedule_exit()
