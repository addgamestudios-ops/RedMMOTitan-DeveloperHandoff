"""Create the additive clean-RedMMO Trooper gameplay assets (A01).

Run this only inside the clean project with Unreal Python.  The transaction is
deliberately map-free and config-free: it creates seven on-foot Enhanced Input
actions, five ship actions, two mapping contexts, and four project-owned
Blueprint children.  All Trooper source content is authenticated through the
completed A12/A13 no-clobber manifests.  The pre-existing migrated StarSparrow
Blueprint is independently hash-pinned and must load as an exact ``RedShip``
subclass before a project-owned A01 child and GameMode assignment are created.

Required environment variable:

    REDMMO_TROOPER_ASSET_BUILD_REPORT

The report must be a new JSON path below
``D:\\RedMMOTitanWindowsData\\Diagnostics``.  The script refuses existing
targets and an existing report.  If creation fails, it deletes only assets it
created during this invocation, in reverse dependency order.  It never edits
or saves a map, config, source package, vendor package, or pre-existing asset.

Evidence boundary: a PASS proves same-process editor creation, Blueprint
compile, reflected readback, exact source hashes, exact created-package saves,
and zero dirty packages.  It does not prove fresh-process reload, MapCheck,
animation/skeleton compatibility in motion, visuals, controls, collision,
networking, PIE, player acceptance, or packaging.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import socket
import traceback
from typing import Any, Iterable, Sequence

import unreal


PROJECT_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
PROJECT_CONTENT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content"
EXPECTED_PROJECT_SHA256 = "54E664A24FA5E9129C022740EE624F84389F1825AA9A4AE07D5E99DD783F382E"

HOME_MAP_FILE = (
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps"
    r"\RedMMO_PPG_HomeWorld.umap"
)
EXPECTED_HOME_MAP_SHA256 = "1821ED915E924085A2D6B3E1A85984A0F207C116EFF32AC974E8F0B7CD217F87"

A12_MANIFEST = (
    r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_TitanStrictPayload_A12_20260803_060715"
    r"\strict_payload_manifest_post.json"
)
A12_MANIFEST_SHA256 = "5A1FE625098BC233EE4B8D5BB995FDC103705B41BC894AD64A3C92C333C80AEA"
A13_MANIFEST = (
    r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_TitanLocomotionPayload_A13_20260803_061035"
    r"\locomotion_payload_manifest_post.json"
)
A13_MANIFEST_SHA256 = "8E8D40724FEA5BB27DE21F3ABA92E6E11A14F67D72A8A1F488488A3346E929CD"

PROVIDER_PORTS = (5353, 8000, 8765)
REPORT_ENV = "REDMMO_TROOPER_ASSET_BUILD_REPORT"
REPORT_ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics"

PROTECTED_FILES = {
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen.umap":
        "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724",
    r"D:\RedMMOTitan\Content\RedMMO\Environment\DA_RED_Planet50Km_FusedHeightfield.uasset":
        "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap":
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap":
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    (
        r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests"
        r"\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"
    ): "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    (
        r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714"
        r"\RedPlanetGen_50km_FusedPrototype.umap"
    ): "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}

ROOT = "/Game/RedMMO/Gameplay/Trooper/A01"
INPUT_ROOT = ROOT + "/Input"
ACTION_PATHS = {
    "move": INPUT_ROOT + "/IA_RedMove",
    "look": INPUT_ROOT + "/IA_RedLook",
    "jump": INPUT_ROOT + "/IA_RedJump",
    "sprint": INPUT_ROOT + "/IA_RedSprint",
    "fire": INPUT_ROOT + "/IA_RedFire",
    "ads": INPUT_ROOT + "/IA_RedADS",
    "interact": INPUT_ROOT + "/IA_RedInteract",
}
INPUT_CONTEXT = INPUT_ROOT + "/IMC_RedTrooper_A01"
SHIP_ACTION_PATHS = {
    "move": INPUT_ROOT + "/IA_RedShipMove",
    "look": INPUT_ROOT + "/IA_RedShipLook",
    "roll": INPUT_ROOT + "/IA_RedShipRoll",
    "boost": INPUT_ROOT + "/IA_RedShipBoost",
    "exit": INPUT_ROOT + "/IA_RedShipExit",
}
SHIP_INPUT_CONTEXT = INPUT_ROOT + "/IMC_RedShip_A01"
BOLT_BP = ROOT + "/Combat/BP_RedBolt_Trooper_A01"
PLAYER_BP = ROOT + "/Player/BP_RedTrooperPlayer_A01"
SHIP_BP = ROOT + "/Ship/BP_RedModularStarSparrow_Trooper_A01"
GAME_MODE_BP = ROOT + "/Player/GM_RedTrooperPPG_A01"
TARGETS = (
    tuple(ACTION_PATHS.values())
    + (INPUT_CONTEXT,)
    + tuple(SHIP_ACTION_PATHS.values())
    + (SHIP_INPUT_CONTEXT, BOLT_BP, PLAYER_BP, SHIP_BP, GAME_MODE_BP)
)

SOURCE_SHIP_CLASS = (
    "/Game/RedMMO/Ships/BP_RedModularStarSparrow."
    "BP_RedModularStarSparrow_C"
)
SOURCE_SHIP_FILE = (
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Ships"
    r"\BP_RedModularStarSparrow.uasset"
)
SOURCE_SHIP_SHA256 = "A8A6E128C2A08AE95A745B3A70C47A372339F314C67C6CE37539A25B67DC78C9"

BODY_MESH = (
    "/Game/Action_Trooper/Meshes/Trooper_UE4_Tall_Female/"
    "SK_TF_Trooper_Standalone_Covered.SK_TF_Trooper_Standalone_Covered"
)
RIFLE_MESH = "/Game/RedMMO/Weapons/SK_RedTrooper_Rifle_A.SK_RedTrooper_Rifle_A"
ANIMATIONS = {
    "idle_animation": (
        "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_Idle."
        "A_Female_Tall_Idle"
    ),
    "walk_animation": (
        "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_ThirdPersonWalk."
        "A_Female_Tall_ThirdPersonWalk"
    ),
    "run_animation": (
        "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_Run."
        "A_Female_Tall_Run"
    ),
    "jump_start_animation": (
        "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_ThirdPersonJump_Start."
        "A_Female_Tall_ThirdPersonJump_Start"
    ),
    "jump_loop_animation": (
        "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_ThirdPersonJump_Loop."
        "A_Female_Tall_ThirdPersonJump_Loop"
    ),
    "jump_end_animation": (
        "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_ThirdPersonJump_End."
        "A_Female_Tall_ThirdPersonJump_End"
    ),
}
MUZZLE_VFX = "/Game/ProjectilesVol1/Effects/P_Flash_4.P_Flash_4"
IMPACT_VFX = "/Game/ProjectilesVol1/Effects/P_Hit_3.P_Hit_3"
BOLT_MESH = "/Game/ProjectilesVol1/Models/SM_Conus.SM_Conus"
BOLT_MATERIAL = "/Game/RedMMO/Materials/M_BoltTracer.M_BoltTracer"

REQUIRED_A12_PACKAGES = tuple(
    path.split(".", 1)[0]
    for path in (BODY_MESH, RIFLE_MESH, MUZZLE_VFX, IMPACT_VFX, BOLT_MESH, BOLT_MATERIAL)
)
REQUIRED_A13_PACKAGES = tuple(path.split(".", 1)[0] for path in ANIMATIONS.values())

NATIVE_CLASSES = {
    "bolt": "/Script/RedMMO.RedBolt",
    "player": "/Script/RedMMO.RedPlayerCharacter",
    "game_mode": "/Script/RedMMO.RedPPGGameplayGameMode",
    "ship": "/Script/RedMMO.RedShip",
}

CLAIM_LIMIT = (
    "Same-process Unreal Editor asset creation, Blueprint compile, reflected readback, "
    "exact source/hash gates, exact target saves, no map/config write, and zero dirty "
    "packages only. No fresh-process reload, MapCheck, runtime, animation compatibility, "
    "visual, control-feel, collision, networking, PIE/player, package, or multiplayer claim."
)


class BuildError(RuntimeError):
    pass


def require(value: Any, message: str) -> None:
    if not value:
        raise BuildError(message)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def canonical_file(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def package_path(value: Any) -> str | None:
    if value is None:
        return None
    return value.get_path_name().split(":", 1)[0].split(".", 1)[0]


def asset_file(path: str) -> str:
    require(path.startswith("/Game/"), "Not a /Game package: " + path)
    return os.path.join(PROJECT_CONTENT, *path[len("/Game/"):].split("/")) + ".uasset"


def report_path_from_env() -> str:
    raw = os.environ.get(REPORT_ENV, "").strip()
    require(raw, "Required environment variable is unset: " + REPORT_ENV)
    path = canonical_file(raw)
    root = canonical_file(REPORT_ROOT)
    require(os.path.commonpath([path, root]) == root, "Report path must stay under " + REPORT_ROOT)
    require(path.lower().endswith(".json"), "Report must use a .json filename")
    require(not os.path.lexists(path), "Report no-clobber target exists: " + path)
    require(not os.path.lexists(path + ".tmp"), "Report staging path exists: " + path + ".tmp")
    return path


def write_report(path: str, value: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def dirty_packages() -> dict[str, list[str]]:
    return {
        "content": sorted(
            {package.get_path_name() for package in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
        ),
        "maps": sorted(
            {package.get_path_name() for package in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}
        ),
    }


def port_listening(port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.15)
    try:
        return probe.connect_ex(("127.0.0.1", port)) == 0
    finally:
        probe.close()


def current_project() -> str:
    return unreal.Paths.convert_relative_path_to_full(
        unreal.Paths.get_project_file_path()
    ).replace("/", "\\")


def verify_protected_hashes() -> dict[str, str]:
    actual = {}
    for path, expected in PROTECTED_FILES.items():
        require(os.path.isfile(path), "Protected file is missing: " + path)
        value = sha256(path)
        require(value == expected, "Protected hash drift: " + path)
        actual[path] = value
    return actual


def load_manifest(path: str, expected_sha: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    require(os.path.isfile(path), "Required payload manifest is missing: " + path)
    require(sha256(path) == expected_sha, "Payload manifest hash drift: " + path)
    with open(path, "r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    require(value.get("result") == "complete_no_clobber_exact_hash_match", "Manifest is not complete: " + path)
    records = value.get("files")
    require(isinstance(records, list), "Manifest files array is missing: " + path)
    by_package = {}
    for record in records:
        package = record.get("package_name")
        require(isinstance(package, str) and package.startswith("/Game/"), "Unsafe manifest package")
        require(package not in by_package, "Duplicate manifest package: " + package)
        by_package[package] = record
    return value, by_package


def verify_manifest_packages(
    records: dict[str, dict[str, Any]], required: Sequence[str], label: str
) -> list[dict[str, Any]]:
    result = []
    content_root = canonical_file(PROJECT_CONTENT)
    for package in required:
        require(package in records, f"{label} does not authenticate {package}")
        record = records[package]
        destination = canonical_file(str(record.get("destination_path", "")))
        expected_destination = canonical_file(asset_file(package))
        require(destination == expected_destination, f"{label} destination drift for {package}")
        require(os.path.commonpath([destination, content_root]) == content_root, "Payload left clean Content root")
        require(os.path.isfile(destination), "Authenticated payload file is missing: " + destination)
        actual_sha = sha256(destination)
        expected_sha = str(record.get("sha256", "")).upper()
        require(actual_sha == expected_sha, "Authenticated payload hash drift: " + package)
        result.append({
            "package": package,
            "file": destination,
            "sha256": actual_sha,
            "bytes": os.path.getsize(destination),
        })
    return result


def load_typed(object_path: str, expected_type: type, label: str):
    value = unreal.load_object(None, object_path)
    require(value is not None, f"Missing {label}: {object_path}")
    require(isinstance(value, expected_type), f"Wrong {label} class at {object_path}: {value.get_class()}")
    return value


def load_subclass(class_path: str, parent_class, label: str):
    value = unreal.load_class(None, class_path)
    require(value is not None, f"Missing {label}: {class_path}")
    require(value.get_path_name() == class_path, f"{label} class-path drift: {value.get_path_name()}")
    is_child = bool(unreal.MathLibrary.class_is_child_of(value, parent_class))
    require(is_child, f"{label} is not a subclass of {parent_class.get_path_name()}: {class_path}")
    return value


def split_asset(path: str) -> tuple[str, str]:
    folder, name = path.rsplit("/", 1)
    require(folder.startswith(ROOT) and name, "Target escaped Trooper A01 root: " + path)
    return folder, name


def delete_helper_owned_asset(path: str, original_error: Exception) -> None:
    """Close the pre-append rollback gap for one exact no-clobber target."""
    cleanup_error = None
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            require(
                unreal.EditorAssetLibrary.delete_asset(path),
                "Helper-local delete returned false: " + path,
            )
        require(
            not unreal.EditorAssetLibrary.does_asset_exist(path),
            "Helper-local rollback left an asset: " + path,
        )
        require(
            not os.path.lexists(asset_file(path)),
            "Helper-local rollback left a file: " + asset_file(path),
        )
        dirty = dirty_packages()
        require(path not in dirty["content"], "Helper-local rollback left a dirty package: " + path)
        require(not dirty["maps"], "Helper-local rollback dirtied a map: " + str(dirty["maps"]))
    except Exception as error:
        cleanup_error = error
    if cleanup_error is not None:
        raise BuildError(
            f"Asset helper failed for {path}: {original_error}; "
            f"helper-local rollback also failed: {cleanup_error}"
        ) from cleanup_error


def create_data_asset(path: str, asset_class: type, factory_class: type):
    folder, name = split_asset(path)
    require(not unreal.EditorAssetLibrary.does_asset_exist(path), "No-clobber asset exists: " + path)
    require(not os.path.lexists(asset_file(path)), "No-clobber file exists: " + asset_file(path))
    try:
        value = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, folder, asset_class.static_class(), factory_class()
        )
        require(value is not None and package_path(value) == path, "Asset creation failed: " + path)
        require(isinstance(value, asset_class), "Created asset type mismatch: " + path)
        return value
    except Exception as error:
        delete_helper_owned_asset(path, error)
        raise


def create_blueprint(path: str, parent_class):
    folder, name = split_asset(path)
    require(not unreal.EditorAssetLibrary.does_asset_exist(path), "No-clobber asset exists: " + path)
    require(not os.path.lexists(asset_file(path)), "No-clobber file exists: " + asset_file(path))
    try:
        factory = unreal.BlueprintFactory()
        factory.set_editor_property("parent_class", parent_class)
        value = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, folder, unreal.Blueprint.static_class(), factory
        )
        require(isinstance(value, unreal.Blueprint), "Blueprint creation failed: " + path)
        require(package_path(value) == path, "Blueprint package mismatch: " + path)
        require(value.get_blueprint_parent_class() == parent_class, "Blueprint parent mismatch: " + path)
        return value
    except Exception as error:
        delete_helper_owned_asset(path, error)
        raise


def compile_blueprint(blueprint) -> dict[str, Any]:
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    status = blueprint.get_editor_property("status")
    accepted = {
        unreal.BlueprintStatus.BS_UP_TO_DATE,
        unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS,
    }
    require(status in accepted, f"Blueprint compile failed: {blueprint.get_path_name()} status={status}")
    errors = []
    warnings = []
    graphs = []
    for graph in list(unreal.BlueprintEditorLibrary.list_graphs(blueprint)):
        editor = unreal.BlueprintGraphEditor.get_graph_editor(graph)
        require(editor is not None, "Graph editor unavailable: " + graph.get_path_name())
        graph_errors = list(editor.list_nodes_with_errors())
        graph_warnings = list(editor.list_nodes_with_warnings())
        errors.extend(f"{graph.get_name()}::{node.get_node_title()}" for node in graph_errors)
        warnings.extend(f"{graph.get_name()}::{node.get_node_title()}" for node in graph_warnings)
        graphs.append({
            "graph": graph.get_name(),
            "nodes": len(list(editor.list_all_nodes())),
            "errors": len(graph_errors),
            "warnings": len(graph_warnings),
        })
    require(not errors, f"Blueprint graph errors in {blueprint.get_path_name()}: {errors}")
    return {
        "asset": package_path(blueprint),
        "parent_class": blueprint.get_blueprint_parent_class().get_path_name(),
        "generated_class": blueprint.generated_class().get_path_name(),
        "status": str(status),
        "graphs": graphs,
        "warnings": warnings,
    }


def subobject_records(blueprint) -> list[dict[str, Any]]:
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    require(subsystem is not None, "SubobjectDataSubsystem is unavailable")
    handles = list(subsystem.k2_gather_subobject_data_for_blueprint(blueprint))
    require(handles, "No Blueprint subobject data: " + blueprint.get_path_name())
    library = unreal.SubobjectDataBlueprintFunctionLibrary
    records = []
    for handle in handles:
        data = library.get_data(handle)
        records.append({
            "variable": str(library.get_variable_name(data)),
            "display": str(library.get_display_name(data)),
            "component": library.get_object_for_blueprint(data, blueprint),
            "is_component": bool(library.is_component(data)),
            "is_inherited": bool(library.is_inherited_component(data)),
        })
    return records


def one_component(blueprint, component_type: type, expected_names: Iterable[str]):
    names = set(expected_names)
    candidates = [
        record for record in subobject_records(blueprint)
        if record["is_component"]
        and isinstance(record["component"], component_type)
        and record["variable"] in names
    ]
    identities = {}
    for record in candidates:
        identities.setdefault(id(record["component"]), record)
    unique = list(identities.values())
    require(
        len(unique) == 1,
        f"Expected one {component_type.__name__} {sorted(names)} in {blueprint.get_path_name()}; "
        f"found {[(r['variable'], str(r['component'])) for r in candidates]}",
    )
    component = unique[0]["component"]
    require(package_path(component) == package_path(blueprint), "Refusing non-project component template edit")
    return component, unique[0]


def make_key(name: str):
    key = unreal.Key()
    key.set_editor_property("key_name", unreal.Name(name))
    require(str(key.get_editor_property("key_name")).lower() == name.lower(), "FKey readback failed: " + name)
    return key


def new_modifier(context, modifier_type: type, name: str):
    modifier = unreal.new_object(modifier_type, outer=context, name=name)
    require(modifier is not None, "Unable to create input modifier: " + name)
    return modifier


def new_swizzle(context, name: str, order):
    modifier = new_modifier(context, unreal.InputModifierSwizzleAxis, name)
    modifier.set_editor_property("order", order)
    require(modifier.get_editor_property("order") == order, "Swizzle readback failed: " + name)
    return modifier


def enhanced_mapping(action, key_name: str, modifiers: Sequence[Any] = ()):
    mapping = unreal.EnhancedActionKeyMapping()
    mapping.set_editor_property("action", action)
    mapping.set_editor_property("key", make_key(key_name))
    mapping.set_editor_property("modifiers", list(modifiers))
    mapping.set_editor_property("triggers", [])
    return mapping


def mapping_record(mapping) -> dict[str, Any]:
    return {
        "action": package_path(mapping.get_editor_property("action")),
        "key": str(mapping.get_editor_property("key").get_editor_property("key_name")),
        "modifiers": [value.get_class().get_name() for value in mapping.get_editor_property("modifiers")],
        "triggers": [value.get_class().get_name() for value in mapping.get_editor_property("triggers")],
    }


def create_input_assets(
    created: list[str],
) -> tuple[dict[str, Any], Any, dict[str, Any], Any, dict[str, Any]]:
    actions = {}
    action_report = {}
    for name, path in ACTION_PATHS.items():
        action = create_data_asset(path, unreal.InputAction, unreal.InputAction_Factory)
        created.append(path)
        action.modify()
        value_type = (
            unreal.InputActionValueType.AXIS2D
            if name in ("move", "look")
            else unreal.InputActionValueType.BOOLEAN
        )
        action.set_editor_property("value_type", value_type)
        action.set_editor_property("action_description", unreal.Text("Red Trooper A01 " + name.title()))
        if name == "move":
            action.set_editor_property(
                "accumulation_behavior",
                unreal.InputActionAccumulationBehavior.CUMULATIVE,
            )
        require(action.get_editor_property("value_type") == value_type, "Input action value-type readback failed: " + path)
        actions[name] = action
        action_report[name] = {"path": path, "value_type": str(value_type)}

    context = create_data_asset(
        INPUT_CONTEXT, unreal.InputMappingContext, unreal.InputMappingContext_Factory
    )
    created.append(INPUT_CONTEXT)
    context.modify()
    move_w_swizzle = new_swizzle(context, "MoveW_SwizzleYXZ", unreal.InputAxisSwizzle.YXZ)
    move_s_swizzle = new_swizzle(context, "MoveS_SwizzleYXZ", unreal.InputAxisSwizzle.YXZ)
    move_s_negate = new_modifier(context, unreal.InputModifierNegate, "MoveS_Negate")
    move_a_negate = new_modifier(context, unreal.InputModifierNegate, "MoveA_Negate")
    mappings = [
        enhanced_mapping(actions["move"], "W", [move_w_swizzle]),
        enhanced_mapping(actions["move"], "S", [move_s_swizzle, move_s_negate]),
        enhanced_mapping(actions["move"], "A", [move_a_negate]),
        enhanced_mapping(actions["move"], "D"),
        enhanced_mapping(actions["look"], "Mouse2D"),
        enhanced_mapping(actions["jump"], "SpaceBar"),
        enhanced_mapping(actions["sprint"], "LeftShift"),
        enhanced_mapping(actions["fire"], "LeftMouseButton"),
        enhanced_mapping(actions["ads"], "RightMouseButton"),
        enhanced_mapping(actions["interact"], "F"),
    ]
    mapping_data = context.get_editor_property("default_key_mappings")
    mapping_data.set_editor_property("mappings", mappings)
    context.set_editor_property("default_key_mappings", mapping_data)
    context.set_editor_property(
        "context_description",
        unreal.Text("Red Trooper A01: WASD, mouse, Space, Shift, LMB, RMB, F interact."),
    )
    actual_records = [
        mapping_record(value)
        for value in context.get_editor_property("default_key_mappings").get_editor_property("mappings")
    ]
    expected_pairs = {
        (ACTION_PATHS["move"], "w"), (ACTION_PATHS["move"], "s"),
        (ACTION_PATHS["move"], "a"), (ACTION_PATHS["move"], "d"),
        (ACTION_PATHS["look"], "mouse2d"), (ACTION_PATHS["jump"], "spacebar"),
        (ACTION_PATHS["sprint"], "leftshift"),
        (ACTION_PATHS["fire"], "leftmousebutton"),
        (ACTION_PATHS["ads"], "rightmousebutton"), (ACTION_PATHS["interact"], "f"),
    }
    require(len(actual_records) == 10, "Unexpected on-foot IMC mapping count")
    require(all(not record["triggers"] for record in actual_records), "Unexpected on-foot input trigger")
    require(
        {(record["action"], record["key"].lower()) for record in actual_records} == expected_pairs,
        "On-foot IMC action/key readback mismatch",
    )

    ship_actions = {}
    ship_action_report = {}
    ship_value_types = {
        "move": unreal.InputActionValueType.AXIS3D,
        "look": unreal.InputActionValueType.AXIS2D,
        "roll": unreal.InputActionValueType.AXIS1D,
        "boost": unreal.InputActionValueType.BOOLEAN,
        "exit": unreal.InputActionValueType.BOOLEAN,
    }
    for name, path in SHIP_ACTION_PATHS.items():
        action = create_data_asset(path, unreal.InputAction, unreal.InputAction_Factory)
        created.append(path)
        action.modify()
        value_type = ship_value_types[name]
        action.set_editor_property("value_type", value_type)
        action.set_editor_property("action_description", unreal.Text("Red Ship A01 " + name.title()))
        if name in ("move", "roll"):
            action.set_editor_property(
                "accumulation_behavior", unreal.InputActionAccumulationBehavior.CUMULATIVE
            )
        require(action.get_editor_property("value_type") == value_type, "Ship action value-type readback failed: " + path)
        ship_actions[name] = action
        ship_action_report[name] = {"path": path, "value_type": str(value_type)}

    ship_context = create_data_asset(
        SHIP_INPUT_CONTEXT, unreal.InputMappingContext, unreal.InputMappingContext_Factory
    )
    created.append(SHIP_INPUT_CONTEXT)
    ship_context.modify()
    ship_s_negate = new_modifier(ship_context, unreal.InputModifierNegate, "ShipMoveS_Negate")
    ship_a_swizzle = new_swizzle(
        ship_context, "ShipMoveA_SwizzleYXZ", unreal.InputAxisSwizzle.YXZ
    )
    ship_a_negate = new_modifier(ship_context, unreal.InputModifierNegate, "ShipMoveA_Negate")
    ship_d_swizzle = new_swizzle(
        ship_context, "ShipMoveD_SwizzleYXZ", unreal.InputAxisSwizzle.YXZ
    )
    ship_up_swizzle = new_swizzle(
        ship_context, "ShipMoveUp_SwizzleZYX", unreal.InputAxisSwizzle.ZYX
    )
    ship_down_swizzle = new_swizzle(
        ship_context, "ShipMoveDown_SwizzleZYX", unreal.InputAxisSwizzle.ZYX
    )
    ship_down_negate = new_modifier(
        ship_context, unreal.InputModifierNegate, "ShipMoveDown_Negate"
    )
    ship_roll_q_negate = new_modifier(
        ship_context, unreal.InputModifierNegate, "ShipRollQ_Negate"
    )
    ship_mappings = [
        enhanced_mapping(ship_actions["move"], "W"),
        enhanced_mapping(ship_actions["move"], "S", [ship_s_negate]),
        enhanced_mapping(ship_actions["move"], "A", [ship_a_swizzle, ship_a_negate]),
        enhanced_mapping(ship_actions["move"], "D", [ship_d_swizzle]),
        enhanced_mapping(ship_actions["move"], "SpaceBar", [ship_up_swizzle]),
        enhanced_mapping(
            ship_actions["move"], "LeftControl", [ship_down_swizzle, ship_down_negate]
        ),
        enhanced_mapping(ship_actions["look"], "Mouse2D"),
        enhanced_mapping(ship_actions["roll"], "Q", [ship_roll_q_negate]),
        enhanced_mapping(ship_actions["roll"], "E"),
        enhanced_mapping(ship_actions["boost"], "LeftShift"),
        enhanced_mapping(ship_actions["exit"], "F"),
    ]
    ship_mapping_data = ship_context.get_editor_property("default_key_mappings")
    ship_mapping_data.set_editor_property("mappings", ship_mappings)
    ship_context.set_editor_property("default_key_mappings", ship_mapping_data)
    ship_context.set_editor_property(
        "context_description",
        unreal.Text(
            "Red Ship A01: WASD planar flight, Space/Ctrl vertical, mouse look, "
            "Q/E roll, Shift boost, F exit."
        ),
    )
    actual_ship_mappings = list(
        ship_context.get_editor_property("default_key_mappings").get_editor_property("mappings")
    )
    ship_records = [mapping_record(value) for value in actual_ship_mappings]
    expected_ship_pairs = {
        (SHIP_ACTION_PATHS["move"], "w"), (SHIP_ACTION_PATHS["move"], "s"),
        (SHIP_ACTION_PATHS["move"], "a"), (SHIP_ACTION_PATHS["move"], "d"),
        (SHIP_ACTION_PATHS["move"], "spacebar"),
        (SHIP_ACTION_PATHS["move"], "leftcontrol"),
        (SHIP_ACTION_PATHS["look"], "mouse2d"),
        (SHIP_ACTION_PATHS["roll"], "q"), (SHIP_ACTION_PATHS["roll"], "e"),
        (SHIP_ACTION_PATHS["boost"], "leftshift"), (SHIP_ACTION_PATHS["exit"], "f"),
    }
    require(len(ship_records) == 11, "Unexpected ship IMC mapping count")
    require(all(not record["triggers"] for record in ship_records), "Unexpected ship input trigger")
    require(
        {(record["action"], record["key"].lower()) for record in ship_records}
        == expected_ship_pairs,
        "Ship IMC action/key readback mismatch",
    )
    ship_by_key = {record["key"].lower(): record for record in ship_records}
    ship_objects_by_key = {
        str(mapping.get_editor_property("key").get_editor_property("key_name")).lower(): mapping
        for mapping in actual_ship_mappings
    }
    require(
        ship_by_key["s"]["modifiers"] == ["InputModifierNegate"]
        and ship_by_key["a"]["modifiers"]
        == ["InputModifierSwizzleAxis", "InputModifierNegate"]
        and ship_by_key["d"]["modifiers"] == ["InputModifierSwizzleAxis"]
        and ship_by_key["spacebar"]["modifiers"] == ["InputModifierSwizzleAxis"]
        and ship_by_key["leftcontrol"]["modifiers"]
        == ["InputModifierSwizzleAxis", "InputModifierNegate"]
        and ship_by_key["q"]["modifiers"] == ["InputModifierNegate"]
        and all(
            ship_by_key[key]["modifiers"] == []
            for key in ("w", "mouse2d", "e", "leftshift", "f")
        ),
        "Ship IMC modifier-stack readback mismatch",
    )
    def swizzle_orders(key_name: str) -> list[Any]:
        return [
            modifier.get_editor_property("order")
            for modifier in ship_objects_by_key[key_name].get_editor_property("modifiers")
            if isinstance(modifier, unreal.InputModifierSwizzleAxis)
        ]

    require(not swizzle_orders("w") and not swizzle_orders("s"), "Ship forward axis was swizzled")
    require(
        swizzle_orders("a") == [unreal.InputAxisSwizzle.YXZ]
        and swizzle_orders("d") == [unreal.InputAxisSwizzle.YXZ],
        "Ship strafe swizzle readback mismatch",
    )
    require(
        swizzle_orders("spacebar") == [unreal.InputAxisSwizzle.ZYX]
        and swizzle_orders("leftcontrol") == [unreal.InputAxisSwizzle.ZYX],
        "Ship vertical swizzle readback mismatch",
    )
    return actions, context, ship_actions, ship_context, {
        "on_foot": {
            "actions": action_report,
            "context": INPUT_CONTEXT,
            "mappings": actual_records,
        },
        "ship": {
            "actions": ship_action_report,
            "context": SHIP_INPUT_CONTEXT,
            "mappings": ship_records,
        },
    }


def create_bolt(created: list[str], assets: dict[str, Any], classes: dict[str, Any]):
    blueprint = create_blueprint(BOLT_BP, classes["bolt"])
    created.append(BOLT_BP)
    blueprint.modify()
    cdo = unreal.get_default_object(blueprint.generated_class())
    cdo.modify()
    cdo.set_editor_property("projectile_mesh_asset", assets["bolt_mesh"])
    cdo.set_editor_property("projectile_material", assets["bolt_material"])
    cdo.set_editor_property("impact_vfx", assets["impact_vfx"])
    require(cdo.get_editor_property("projectile_mesh_asset") == assets["bolt_mesh"], "Bolt mesh readback failed")
    require(cdo.get_editor_property("projectile_material") == assets["bolt_material"], "Bolt material readback failed")
    require(cdo.get_editor_property("impact_vfx") == assets["impact_vfx"], "Impact VFX readback failed")
    compile_report = compile_blueprint(blueprint)
    return blueprint, {
        "path": BOLT_BP,
        "projectile_mesh": BOLT_MESH,
        "projectile_material": BOLT_MATERIAL,
        "impact_vfx": IMPACT_VFX,
        "compile": compile_report,
    }


def configure_component_mesh(component, mesh, label: str) -> None:
    setter = getattr(component, "set_skeletal_mesh_asset", None)
    getter = getattr(component, "get_skeletal_mesh_asset", None)
    require(callable(setter) and callable(getter), label + " skeletal mesh accessors unavailable")
    component.modify()
    setter(mesh)
    require(getter() == mesh, label + " skeletal mesh readback failed")


def vector_is(value, x: float, y: float, z: float, tolerance: float = 0.001) -> bool:
    return (
        abs(float(value.x) - x) <= tolerance
        and abs(float(value.y) - y) <= tolerance
        and abs(float(value.z) - z) <= tolerance
    )


def rotator_is(
    value, pitch: float, yaw: float, roll: float, tolerance: float = 0.001
) -> bool:
    return (
        abs(float(value.pitch) - pitch) <= tolerance
        and abs(float(value.yaw) - yaw) <= tolerance
        and abs(float(value.roll) - roll) <= tolerance
    )


def set_component_attach_socket(component, parent, socket_name: str) -> str:
    """Set the inherited template socket without assuming one Python exposure.

    UE exposes AttachSocketName as a reflected property on some builds and only
    the Blueprint-callable K2 attachment wrapper on others.  Both routes are
    exact readback-gated; neither may silently fall back to root attachment.
    """
    route = "reflected_attach_socket_name"
    try:
        component.set_editor_property("attach_socket_name", unreal.Name(socket_name))
    except Exception:
        route = "k2_attach_to_component_keep_relative"
        attach = getattr(component, "attach_to_component", None)
        require(callable(attach), "No supported SceneComponent socket-assignment API")
        attached = attach(
            parent,
            unreal.Name(socket_name),
            unreal.AttachmentRule.KEEP_RELATIVE,
            unreal.AttachmentRule.KEEP_RELATIVE,
            unreal.AttachmentRule.KEEP_RELATIVE,
            False,
        )
        require(attached, "K2 socket attachment failed: " + socket_name)
    require(component.get_attach_parent() == parent, "Component attachment parent readback failed")
    require(str(component.get_attach_socket_name()) == socket_name, "Component socket readback failed")
    return route


def create_player(
    created: list[str], actions: dict[str, Any], context, ship_context, bolt_blueprint,
    assets: dict[str, Any], classes: dict[str, Any]
):
    blueprint = create_blueprint(PLAYER_BP, classes["player"])
    created.append(PLAYER_BP)
    blueprint.modify()
    cdo = unreal.get_default_object(blueprint.generated_class())
    cdo.modify()
    cdo.set_editor_property("default_mapping_context", context)
    cdo.set_editor_property("ship_mapping_context", ship_context)
    player_action_bindings = (
        ("move_action", "move"), ("look_action", "look"),
        ("jump_action", "jump"), ("sprint_action", "sprint"),
        ("fire_action", "fire"), ("ads_action", "ads"),
        ("interact_action", "interact"),
    )
    for property_name, action_name in player_action_bindings:
        cdo.set_editor_property(property_name, actions[action_name])
    for property_name, animation in assets["animations"].items():
        cdo.set_editor_property(property_name, animation)
    cdo.set_editor_property("bolt_class", bolt_blueprint.generated_class())
    cdo.set_editor_property("muzzle_vfx", assets["muzzle_vfx"])
    cdo.set_editor_property("muzzle_socket_name", unreal.Name("Muzzle"))

    body, body_record = one_component(
        blueprint, unreal.SkeletalMeshComponent, ("CharacterMesh0", "Mesh")
    )
    weapon, weapon_record = one_component(
        blueprint, unreal.SkeletalMeshComponent, ("WeaponMesh",)
    )
    configure_component_mesh(body, assets["body_mesh"], "Body")
    require(
        body.does_socket_exist(unreal.Name("hand_rSocket")),
        "Trooper body mesh does not expose hand_rSocket",
    )
    body.set_editor_property("animation_mode", unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    body.set_editor_property("hidden_in_game", False)
    body.set_editor_property("visible", True)
    body.set_editor_property("relative_location", unreal.Vector(0.0, 0.0, -96.0))
    body.set_editor_property(
        "relative_rotation", unreal.Rotator(pitch=0.0, yaw=-90.0, roll=0.0)
    )
    body.set_editor_property("relative_scale3d", unreal.Vector(1.0, 1.0, 1.0))

    configure_component_mesh(weapon, assets["rifle_mesh"], "Weapon")
    require(
        weapon.does_socket_exist(unreal.Name("Muzzle")),
        "Trooper rifle mesh does not expose Muzzle",
    )
    weapon.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    weapon.set_editor_property("generate_overlap_events", False)
    weapon_socket_route = set_component_attach_socket(weapon, body, "hand_rSocket")
    weapon.set_editor_property("relative_location", unreal.Vector(0.0, 0.0, 0.0))
    weapon.set_editor_property(
        "relative_rotation", unreal.Rotator(pitch=0.0, yaw=0.0, roll=0.0)
    )
    weapon.set_editor_property("relative_scale3d", unreal.Vector(1.0, 1.0, 1.0))
    require(str(weapon.get_attach_socket_name()) == "hand_rSocket", "Weapon socket readback failed")
    require(weapon.get_attach_parent() == body, "Weapon is not attached to the inherited body mesh")

    for property_name, expected in (
        ("default_mapping_context", context),
        ("ship_mapping_context", ship_context),
        ("bolt_class", bolt_blueprint.generated_class()),
        ("muzzle_vfx", assets["muzzle_vfx"]),
    ):
        require(cdo.get_editor_property(property_name) == expected, "Player property readback failed: " + property_name)
    for property_name, action_name in player_action_bindings:
        require(
            cdo.get_editor_property(property_name) == actions[action_name],
            "Player action readback failed: " + property_name,
        )
    for property_name, expected in assets["animations"].items():
        require(cdo.get_editor_property(property_name) == expected, "Animation readback failed: " + property_name)
    compile_report = compile_blueprint(blueprint)
    return blueprint, {
        "path": PLAYER_BP,
        "body_mesh": BODY_MESH,
        "body_component_variable": body_record["variable"],
        "body_relative_location": [0.0, 0.0, -96.0],
        "body_relative_rotation": [0.0, -90.0, 0.0],
        "body_scale": [1.0, 1.0, 1.0],
        "rifle_mesh": RIFLE_MESH,
        "weapon_component_variable": weapon_record["variable"],
        "weapon_socket": "hand_rSocket",
        "weapon_socket_assignment_route": weapon_socket_route,
        "weapon_relative_transform": "identity",
        "weapon_collision": "NoCollision",
        "muzzle_socket": "Muzzle",
        "muzzle_vfx": MUZZLE_VFX,
        "animations": ANIMATIONS,
        "input_context": INPUT_CONTEXT,
        "ship_input_context": SHIP_INPUT_CONTEXT,
        "body_socket_verified": "hand_rSocket",
        "rifle_socket_verified": "Muzzle",
        "compile": compile_report,
    }


def create_ship(
    created: list[str], source_ship_class, on_foot_context, ship_actions: dict[str, Any],
    ship_context, classes: dict[str, Any]
):
    blueprint = create_blueprint(SHIP_BP, source_ship_class)
    created.append(SHIP_BP)
    blueprint.modify()
    require(
        unreal.MathLibrary.class_is_child_of(blueprint.generated_class(), classes["ship"]),
        "A01 ship Blueprint is not a RedShip subclass",
    )
    cdo = unreal.get_default_object(blueprint.generated_class())
    cdo.modify()
    cdo.set_editor_property("ship_mapping_context", ship_context)
    cdo.set_editor_property("on_foot_mapping_context", on_foot_context)
    ship_action_bindings = (
        ("move_action", "move"),
        ("look_action", "look"),
        ("roll_action", "roll"),
        ("boost_action", "boost"),
        ("exit_action", "exit"),
    )
    for property_name, action_name in ship_action_bindings:
        cdo.set_editor_property(property_name, ship_actions[action_name])
    for property_name, expected in (
        ("ship_mapping_context", ship_context),
        ("on_foot_mapping_context", on_foot_context),
    ):
        require(
            cdo.get_editor_property(property_name) == expected,
            "Ship context readback failed: " + property_name,
        )
    for property_name, action_name in ship_action_bindings:
        require(
            cdo.get_editor_property(property_name) == ship_actions[action_name],
            "Ship action readback failed: " + property_name,
        )
    compile_report = compile_blueprint(blueprint)
    return blueprint, {
        "path": SHIP_BP,
        "source_parent_class": source_ship_class.get_path_name(),
        "native_base_class": classes["ship"].get_path_name(),
        "ship_mapping_context": SHIP_INPUT_CONTEXT,
        "on_foot_mapping_context": INPUT_CONTEXT,
        "actions": SHIP_ACTION_PATHS,
        "compile": compile_report,
    }


def create_game_mode(
    created: list[str], player_blueprint, starter_ship_class, classes: dict[str, Any]
):
    blueprint = create_blueprint(GAME_MODE_BP, classes["game_mode"])
    created.append(GAME_MODE_BP)
    blueprint.modify()
    cdo = unreal.get_default_object(blueprint.generated_class())
    cdo.modify()
    cdo.set_editor_property("default_pawn_class", player_blueprint.generated_class())
    cdo.set_editor_property("starter_ship_class", starter_ship_class)
    require(
        cdo.get_editor_property("default_pawn_class") == player_blueprint.generated_class(),
        "GameMode pawn readback failed",
    )
    require(
        cdo.get_editor_property("starter_ship_class") == starter_ship_class,
        "GameMode starter-ship readback failed",
    )
    compile_report = compile_blueprint(blueprint)
    return blueprint, {
        "path": GAME_MODE_BP,
        "default_pawn_class": player_blueprint.generated_class().get_path_name(),
        "starter_ship_class": starter_ship_class.get_path_name(),
        "compile": compile_report,
    }


def verify_player_components_after_save(player_blueprint, assets: dict[str, Any]) -> dict[str, Any]:
    body, body_record = one_component(
        player_blueprint, unreal.SkeletalMeshComponent, ("CharacterMesh0", "Mesh")
    )
    weapon, weapon_record = one_component(
        player_blueprint, unreal.SkeletalMeshComponent, ("WeaponMesh",)
    )
    require(body.get_skeletal_mesh_asset() == assets["body_mesh"], "Saved body mesh readback failed")
    require(
        body.does_socket_exist(unreal.Name("hand_rSocket")),
        "Saved Trooper body hand_rSocket readback failed",
    )
    require(
        body.get_editor_property("animation_mode") == unreal.AnimationMode.ANIMATION_SINGLE_NODE,
        "Saved body animation mode readback failed",
    )
    require(
        vector_is(body.get_editor_property("relative_location"), 0.0, 0.0, -96.0),
        "Saved body location readback failed",
    )
    require(
        rotator_is(body.get_editor_property("relative_rotation"), 0.0, -90.0, 0.0),
        "Saved body rotation readback failed",
    )
    require(
        vector_is(body.get_editor_property("relative_scale3d"), 1.0, 1.0, 1.0),
        "Saved body scale readback failed",
    )
    require(weapon.get_skeletal_mesh_asset() == assets["rifle_mesh"], "Saved rifle mesh readback failed")
    require(
        weapon.does_socket_exist(unreal.Name("Muzzle")),
        "Saved Trooper rifle Muzzle readback failed",
    )
    require(
        weapon.get_collision_enabled() == unreal.CollisionEnabled.NO_COLLISION,
        "Saved weapon collision readback failed",
    )
    require(
        not bool(weapon.get_editor_property("generate_overlap_events")),
        "Saved weapon overlap readback failed",
    )
    require(weapon.get_attach_parent() == body, "Saved weapon parent readback failed")
    require(str(weapon.get_attach_socket_name()) == "hand_rSocket", "Saved weapon socket readback failed")
    require(
        vector_is(weapon.get_editor_property("relative_location"), 0.0, 0.0, 0.0)
        and rotator_is(weapon.get_editor_property("relative_rotation"), 0.0, 0.0, 0.0)
        and vector_is(weapon.get_editor_property("relative_scale3d"), 1.0, 1.0, 1.0),
        "Saved weapon identity transform readback failed",
    )
    return {
        "body_component_variable": body_record["variable"],
        "body_mesh": BODY_MESH,
        "body_relative_location": [0.0, 0.0, -96.0],
        "body_relative_rotation": [0.0, -90.0, 0.0],
        "body_scale": [1.0, 1.0, 1.0],
        "body_socket_verified": "hand_rSocket",
        "weapon_component_variable": weapon_record["variable"],
        "rifle_mesh": RIFLE_MESH,
        "weapon_parent": body_record["variable"],
        "weapon_socket": "hand_rSocket",
        "weapon_relative_transform": "identity",
        "weapon_collision": "NoCollision",
        "rifle_socket_verified": "Muzzle",
    }


def allowed_dirty_only() -> dict[str, list[str]]:
    dirty = dirty_packages()
    expected = set(TARGETS)
    require(not dirty["maps"], "Map package became dirty: " + str(dirty["maps"]))
    unexpected = sorted(set(dirty["content"]) - expected)
    require(not unexpected, "Unexpected dirty content packages: " + str(unexpected))
    return dirty


def save_created_assets(created: Sequence[str]) -> list[dict[str, Any]]:
    require(set(created) == set(TARGETS), "Created-target set is incomplete or unexpected")
    allowed_dirty_only()
    records = []
    for path in created:
        asset = unreal.EditorAssetLibrary.load_asset(path)
        require(asset is not None, "Created asset cannot be loaded for save: " + path)
        require(
            unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False),
            "Unable to save created asset: " + path,
        )
    require(dirty_packages() == {"content": [], "maps": []}, "Dirty packages remain after exact saves")
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous([ROOT], force_rescan=True)
    for path in TARGETS:
        file_path = asset_file(path)
        require(os.path.isfile(file_path), "Saved target file is missing: " + file_path)
        data = registry.get_asset_by_object_path(unreal.Name(path + "." + path.rsplit("/", 1)[1]))
        require(data.is_valid(), "Asset Registry readback failed: " + path)
        records.append({
            "package": path,
            "file": file_path,
            "sha256": sha256(file_path),
            "bytes": os.path.getsize(file_path),
            "class": str(data.asset_class_path),
        })
    return records


def delete_created(created: Sequence[str]) -> dict[str, Any]:
    deleted = []
    failed = []
    for path in reversed(list(created)):
        try:
            if not unreal.EditorAssetLibrary.does_asset_exist(path):
                continue
            if unreal.EditorAssetLibrary.delete_asset(path):
                deleted.append(path)
            else:
                failed.append(path)
        except Exception as error:
            failed.append(path + " :: " + str(error))
    remaining_assets = [
        path for path in created if unreal.EditorAssetLibrary.does_asset_exist(path)
    ]
    remaining_files = [asset_file(path) for path in created if os.path.lexists(asset_file(path))]
    remaining_dirty = dirty_packages()
    dirty_created = sorted(set(remaining_dirty["content"]) & set(created))
    return {
        "mode": "delete_only_assets_created_by_this_invocation_in_reverse_dependency_order",
        "deleted": deleted,
        "failed": failed,
        "remaining_assets": remaining_assets,
        "remaining_files": remaining_files,
        "remaining_created_dirty_packages": dirty_created,
        "remaining_dirty_packages": remaining_dirty,
        "complete": not failed and not remaining_assets and not remaining_files and not dirty_created,
    }


def verify_static_preflight() -> dict[str, Any]:
    require(os.path.isfile(PROJECT_FILE), "Clean RedMMO project file is missing")
    require(sha256(PROJECT_FILE) == EXPECTED_PROJECT_SHA256, "Clean RedMMO project descriptor hash drift")
    require(
        unreal.Paths.is_same_path(current_project(), PROJECT_FILE),
        "Wrong Unreal project: " + current_project(),
    )
    require(os.path.isfile(HOME_MAP_FILE), "Clean RedMMO home map is missing")
    require(sha256(HOME_MAP_FILE) == EXPECTED_HOME_MAP_SHA256, "Home map prehash drift")
    require(os.path.isfile(SOURCE_SHIP_FILE), "Source ship Blueprint package is missing")
    require(
        sha256(SOURCE_SHIP_FILE) == SOURCE_SHIP_SHA256,
        "Source ship Blueprint package hash drift",
    )
    providers = {str(port): port_listening(port) for port in PROVIDER_PORTS}
    require(not any(providers.values()), "AI/MCP/provider listener is active: " + str(providers))
    require(
        not list(unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=False)),
        "PIE must be stopped",
    )
    before_dirty = dirty_packages()
    require(before_dirty == {"content": [], "maps": []}, "Pre-existing dirty packages: " + str(before_dirty))
    existing = [path for path in TARGETS if unreal.EditorAssetLibrary.does_asset_exist(path)]
    require(not existing, "No-clobber targets already exist: " + str(existing))
    existing_files = [asset_file(path) for path in TARGETS if os.path.lexists(asset_file(path))]
    require(not existing_files, "No-clobber target files already exist: " + str(existing_files))

    a12, a12_records = load_manifest(A12_MANIFEST, A12_MANIFEST_SHA256)
    a13, a13_records = load_manifest(A13_MANIFEST, A13_MANIFEST_SHA256)
    authenticated = {
        "a12": verify_manifest_packages(a12_records, REQUIRED_A12_PACKAGES, "A12"),
        "a13": verify_manifest_packages(a13_records, REQUIRED_A13_PACKAGES, "A13"),
    }
    return {
        "project_file": PROJECT_FILE,
        "project_sha256": EXPECTED_PROJECT_SHA256,
        "home_map_file": HOME_MAP_FILE,
        "home_map_sha256": EXPECTED_HOME_MAP_SHA256,
        "source_ship_file": SOURCE_SHIP_FILE,
        "source_ship_sha256": SOURCE_SHIP_SHA256,
        "source_ship_class": SOURCE_SHIP_CLASS,
        "provider_ports_listening": providers,
        "dirty_packages": before_dirty,
        "protected_hashes": verify_protected_hashes(),
        "manifests": {
            "a12": {"path": A12_MANIFEST, "sha256": A12_MANIFEST_SHA256, "result": a12.get("result")},
            "a13": {"path": A13_MANIFEST, "sha256": A13_MANIFEST_SHA256, "result": a13.get("result")},
        },
        "authenticated_bindings": authenticated,
    }


def run_build() -> dict[str, Any]:
    created: list[str] = []
    started = dt.datetime.now(dt.timezone.utc)
    report = {
        "schema_version": 1,
        "transaction": "clean_redmmo_trooper_assets_a01",
        "captured_utc": started.isoformat(),
        "status": "running",
        "evidence_class": "unreal_editor_asset_creation_automation",
        "project": PROJECT_FILE,
        "map_mutation_authorized": False,
        "map_saved": False,
        "config_saved": False,
        "vendor_assets_modified": False,
        "targets": list(TARGETS),
        "target_count": len(TARGETS),
        "claim_limit": CLAIM_LIMIT,
    }
    try:
        report["preflight"] = verify_static_preflight()
        classes = {}
        for key, path in NATIVE_CLASSES.items():
            value = unreal.load_class(None, path)
            require(value is not None and value.get_path_name() == path, "Native class unavailable: " + path)
            classes[key] = value

        assets = {
            "body_mesh": load_typed(BODY_MESH, unreal.SkeletalMesh, "Trooper body mesh"),
            "rifle_mesh": load_typed(RIFLE_MESH, unreal.SkeletalMesh, "Trooper rifle mesh"),
            "muzzle_vfx": load_typed(MUZZLE_VFX, unreal.NiagaraSystem, "muzzle Niagara system"),
            "impact_vfx": load_typed(IMPACT_VFX, unreal.NiagaraSystem, "impact Niagara system"),
            "bolt_mesh": load_typed(BOLT_MESH, unreal.StaticMesh, "bolt mesh"),
            "bolt_material": load_typed(BOLT_MATERIAL, unreal.MaterialInterface, "bolt material"),
            "animations": {
                property_name: load_typed(path, unreal.AnimationAsset, property_name)
                for property_name, path in ANIMATIONS.items()
            },
        }
        source_ship_class = load_subclass(
            SOURCE_SHIP_CLASS, classes["ship"], "source ship Blueprint"
        )
        source_load_dirty = dirty_packages()
        require(
            source_load_dirty == {"content": [], "maps": []},
            "Source loading dirtied a pre-existing package: " + str(source_load_dirty),
        )
        report["source_load_dirty_gate"] = source_load_dirty
        actions, context, ship_actions, ship_context, report["input"] = create_input_assets(
            created
        )
        bolt, report["bolt"] = create_bolt(created, assets, classes)
        player, report["player"] = create_player(
            created, actions, context, ship_context, bolt, assets, classes
        )
        ship, report["ship"] = create_ship(
            created, source_ship_class, context, ship_actions, ship_context, classes
        )
        game_mode, report["game_mode"] = create_game_mode(
            created, player, ship.generated_class(), classes
        )

        # Recompile in dependency order after all class references are established.
        report["final_compile"] = [
            compile_blueprint(bolt),
            compile_blueprint(player),
            compile_blueprint(ship),
            compile_blueprint(game_mode),
        ]
        report["dirty_before_exact_save"] = allowed_dirty_only()
        ports_before_save = {str(port): port_listening(port) for port in PROVIDER_PORTS}
        require(
            not any(ports_before_save.values()),
            "AI/MCP/provider listener opened before save: " + str(ports_before_save),
        )
        report["provider_ports_before_exact_save"] = ports_before_save
        report["saved_assets"] = save_created_assets(created)

        # Final reflected readback after save; this is intentionally same-process.
        player_cdo = unreal.get_default_object(player.generated_class())
        game_mode_cdo = unreal.get_default_object(game_mode.generated_class())
        ship_cdo = unreal.get_default_object(ship.generated_class())
        bolt_cdo = unreal.get_default_object(bolt.generated_class())
        require(
            ship.get_blueprint_parent_class() == source_ship_class,
            "Saved A01 ship parent-class readback failed",
        )
        require(
            unreal.MathLibrary.class_is_child_of(ship.generated_class(), classes["ship"]),
            "Saved A01 ship RedShip-subclass readback failed",
        )
        require(player_cdo.get_editor_property("default_mapping_context") == context, "Saved context readback failed")
        require(
            player_cdo.get_editor_property("ship_mapping_context") == ship_context,
            "Saved player ship-context readback failed",
        )
        require(
            player_cdo.get_editor_property("interact_action") == actions["interact"],
            "Saved player interact-action readback failed",
        )
        for property_name, action_name in (
            ("move_action", "move"), ("look_action", "look"),
            ("jump_action", "jump"), ("sprint_action", "sprint"),
            ("fire_action", "fire"), ("ads_action", "ads"),
            ("interact_action", "interact"),
        ):
            require(
                player_cdo.get_editor_property(property_name) == actions[action_name],
                "Saved player action readback failed: " + property_name,
            )
        for property_name, expected in assets["animations"].items():
            require(
                player_cdo.get_editor_property(property_name) == expected,
                "Saved player animation readback failed: " + property_name,
            )
        require(player_cdo.get_editor_property("bolt_class") == bolt.generated_class(), "Saved bolt-class readback failed")
        require(
            player_cdo.get_editor_property("muzzle_vfx") == assets["muzzle_vfx"],
            "Saved muzzle VFX readback failed",
        )
        require(
            str(player_cdo.get_editor_property("muzzle_socket_name")) == "Muzzle",
            "Saved muzzle socket-name readback failed",
        )
        require(game_mode_cdo.get_editor_property("default_pawn_class") == player.generated_class(), "Saved pawn-class readback failed")
        require(
            game_mode_cdo.get_editor_property("starter_ship_class") == ship.generated_class(),
            "Saved starter-ship-class readback failed",
        )
        require(
            ship_cdo.get_editor_property("ship_mapping_context") == ship_context
            and ship_cdo.get_editor_property("on_foot_mapping_context") == context,
            "Saved ship context readback failed",
        )
        for property_name, action_name in (
            ("move_action", "move"), ("look_action", "look"),
            ("roll_action", "roll"), ("boost_action", "boost"),
            ("exit_action", "exit"),
        ):
            require(
                ship_cdo.get_editor_property(property_name) == ship_actions[action_name],
                "Saved ship action readback failed: " + property_name,
            )
        require(
            bolt_cdo.get_editor_property("projectile_mesh_asset") == assets["bolt_mesh"],
            "Saved bolt mesh readback failed",
        )
        require(
            bolt_cdo.get_editor_property("projectile_material") == assets["bolt_material"],
            "Saved bolt material readback failed",
        )
        require(bolt_cdo.get_editor_property("impact_vfx") == assets["impact_vfx"], "Saved impact VFX readback failed")
        report["post_save_cdo_readback"] = {
            "player_actions": ACTION_PATHS,
            "player_animations": ANIMATIONS,
            "player_mapping_context": INPUT_CONTEXT,
            "player_ship_mapping_context": SHIP_INPUT_CONTEXT,
            "player_bolt_class": bolt.generated_class().get_path_name(),
            "player_muzzle_vfx": MUZZLE_VFX,
            "player_muzzle_socket": "Muzzle",
            "ship_actions": SHIP_ACTION_PATHS,
            "ship_mapping_context": SHIP_INPUT_CONTEXT,
            "ship_on_foot_mapping_context": INPUT_CONTEXT,
            "bolt_mesh": BOLT_MESH,
            "bolt_material": BOLT_MATERIAL,
            "bolt_impact_vfx": IMPACT_VFX,
            "game_mode_default_pawn_class": player.generated_class().get_path_name(),
            "game_mode_starter_ship_class": ship.generated_class().get_path_name(),
        }
        report["player_component_readback_after_save"] = verify_player_components_after_save(
            player, assets
        )
        require(sha256(HOME_MAP_FILE) == EXPECTED_HOME_MAP_SHA256, "Home map changed during asset-only transaction")
        require(
            sha256(SOURCE_SHIP_FILE) == SOURCE_SHIP_SHA256,
            "Source ship Blueprint changed during asset-only transaction",
        )
        post_protected = verify_protected_hashes()
        require(post_protected == report["preflight"]["protected_hashes"], "Protected hashes changed")
        ports_after = {str(port): port_listening(port) for port in PROVIDER_PORTS}
        require(not any(ports_after.values()), "AI/MCP/provider listener opened: " + str(ports_after))
        require(dirty_packages() == {"content": [], "maps": []}, "Post-build dirty package drift")
        report.update({
            "status": "pass_created_compiled_saved_same_process_readback",
            "created_assets": list(created),
            "home_map_sha256_after": sha256(HOME_MAP_FILE),
            "source_ship_sha256_after": sha256(SOURCE_SHIP_FILE),
            "protected_hashes_after": post_protected,
            "provider_ports_listening_after": ports_after,
            "dirty_packages_after": dirty_packages(),
            "rollback": {
                "mode": "additive_no_preimages",
                "instruction": (
                    "With PIE/editor work stopped, remove only the exact packages in created_assets "
                    "in reverse order. No map/config/source/vendor preimage exists because none changed."
                ),
            },
            "elapsed_seconds": (dt.datetime.now(dt.timezone.utc) - started).total_seconds(),
        })
        return report
    except Exception as error:
        report.update({
            "status": "fail_rolled_back_if_possible",
            "error": str(error),
            "traceback": traceback.format_exc(),
            "created_before_failure": list(created),
            "rollback": delete_created(created),
            "home_map_sha256_after_failure": sha256(HOME_MAP_FILE) if os.path.isfile(HOME_MAP_FILE) else None,
            "source_ship_sha256_after_failure": (
                sha256(SOURCE_SHIP_FILE) if os.path.isfile(SOURCE_SHIP_FILE) else None
            ),
            "dirty_packages_after_failure": dirty_packages(),
            "elapsed_seconds": (dt.datetime.now(dt.timezone.utc) - started).total_seconds(),
        })
        return report


_REPORT_PATH = report_path_from_env()
_REPORT = run_build()
try:
    write_report(_REPORT_PATH, _REPORT)
except Exception as _REPORT_ERROR:
    _REPORT_ROLLBACK = None
    if str(_REPORT.get("status", "")).startswith("pass_"):
        _REPORT_ROLLBACK = delete_created(_REPORT.get("created_assets", []))
    unreal.log_error(
        "REDMMO_TROOPER_ASSET_BUILD_A01 REPORT_WRITE_FAIL report=" + _REPORT_PATH
        + " error=" + str(_REPORT_ERROR)
        + " rollback=" + str(_REPORT_ROLLBACK)
    )
    raise BuildError("Durable report write failed: " + str(_REPORT_ERROR)) from _REPORT_ERROR
if not str(_REPORT.get("status", "")).startswith("pass_"):
    unreal.log_error(
        "REDMMO_TROOPER_ASSET_BUILD_A01 FAIL report=" + _REPORT_PATH
        + " error=" + str(_REPORT.get("error"))
    )
    raise BuildError(str(_REPORT.get("error")))
unreal.log("REDMMO_TROOPER_ASSET_BUILD_A01 PASS report=" + _REPORT_PATH)
