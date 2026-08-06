"""Fresh-process, no-save verifier for the clean RedMMO Trooper/ship A01 assets.

Required environment variables:

``REDMMO_TROOPER_ASSET_BUILD_INPUT_REPORT`` points at the completed asset-build
report and ``REDMMO_TROOPER_ASSET_RELOAD_REPORT`` names a new JSON evidence
file below the D: diagnostics root.  The verifier loads the exact eighteen
project-owned packages in a new Unreal process, validates their serialized
types, mappings, Blueprint parents/defaults and mesh/socket bindings, and
refuses any map/config/vendor mutation.  It intentionally does not compile,
save, open a project map, start PIE, or claim runtime/visual acceptance.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import socket
import traceback
from typing import Any, Iterable

import unreal


PROJECT_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
PROJECT_SHA256 = "54E664A24FA5E9129C022740EE624F84389F1825AA9A4AE07D5E99DD783F382E"
HOME_MAP_FILE = (
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps"
    r"\RedMMO_PPG_HomeWorld.umap"
)
HOME_MAP_SHA256 = "1821ED915E924085A2D6B3E1A85984A0F207C116EFF32AC974E8F0B7CD217F87"
SOURCE_SHIP_CLASS = (
    "/Game/RedMMO/Ships/BP_RedModularStarSparrow."
    "BP_RedModularStarSparrow_C"
)
SOURCE_SHIP_FILE = (
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Ships"
    r"\BP_RedModularStarSparrow.uasset"
)
SOURCE_SHIP_SHA256 = "A8A6E128C2A08AE95A745B3A70C47A372339F314C67C6CE37539A25B67DC78C9"
PROVIDER_PORTS = (5353, 8000, 8765)
REPORT_ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics"
BUILD_REPORT_ENV = "REDMMO_TROOPER_ASSET_BUILD_INPUT_REPORT"
REPORT_ENV = "REDMMO_TROOPER_ASSET_RELOAD_REPORT"

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

BODY_MESH = (
    "/Game/Action_Trooper/Meshes/Trooper_UE4_Tall_Female/"
    "SK_TF_Trooper_Standalone_Covered.SK_TF_Trooper_Standalone_Covered"
)
RIFLE_MESH = "/Game/RedMMO/Weapons/SK_RedTrooper_Rifle_A.SK_RedTrooper_Rifle_A"
MUZZLE_VFX = "/Game/ProjectilesVol1/Effects/P_Flash_4.P_Flash_4"
IMPACT_VFX = "/Game/ProjectilesVol1/Effects/P_Hit_3.P_Hit_3"
BOLT_MESH = "/Game/ProjectilesVol1/Models/SM_Conus.SM_Conus"
BOLT_MATERIAL = "/Game/RedMMO/Materials/M_BoltTracer.M_BoltTracer"
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
NATIVE_CLASSES = {
    "bolt": "/Script/RedMMO.RedBolt",
    "player": "/Script/RedMMO.RedPlayerCharacter",
    "game_mode": "/Script/RedMMO.RedPPGGameplayGameMode",
    "ship": "/Script/RedMMO.RedShip",
}
PROTECTED_FILES = {
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen.umap":
        "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724",
    r"D:\RedMMOTitan\Content\RedMMO\Environment\DA_RED_Planet50Km_FusedHeightfield.uasset":
        "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap":
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap":
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap":
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap":
        "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}


class VerifyError(RuntimeError):
    pass


def require(value: Any, message: str) -> None:
    if not value:
        raise VerifyError(message)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def canonical(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def validated_report_path(value: str) -> str:
    require(bool(value), "Verifier report environment is missing")
    result = canonical(value)
    require(
        os.path.commonpath([result, canonical(REPORT_ROOT)]) == canonical(REPORT_ROOT),
        "Unsafe verifier report path",
    )
    require(not os.path.lexists(result), "Verifier report no-clobber failed")
    return result


def current_project() -> str:
    return canonical(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    )


def package_path(value: Any) -> str:
    package = value.get_outermost()
    return package.get_path_name() if package is not None else ""


def asset_file(package: str) -> str:
    require(package.startswith("/Game/"), "Unsafe package: " + package)
    return os.path.join(
        r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content",
        package[len("/Game/") :].replace("/", os.sep) + ".uasset",
    )


def dirty_packages() -> dict[str, list[str]]:
    content = sorted(
        package.get_path_name()
        for package in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    )
    maps = sorted(
        package.get_path_name()
        for package in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    )
    return {"content": content, "maps": maps}


def port_listening(port: int) -> bool:
    for host in ("127.0.0.1", "::1"):
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as value:
            value.settimeout(0.15)
            if value.connect_ex((host, port)) == 0:
                return True
    return False


def load_json(path: str) -> dict[str, Any]:
    require(os.path.isfile(path), "Missing JSON: " + path)
    with open(path, "r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    require(isinstance(value, dict), "JSON root is not an object: " + path)
    return value


def load_asset(path: str, expected_type: type):
    value = unreal.EditorAssetLibrary.load_asset(path)
    require(value is not None, "Asset failed to load: " + path)
    require(isinstance(value, expected_type), "Asset class mismatch: " + path)
    require(package_path(value) == path, "Loaded package mismatch: " + path)
    return value


def load_blueprint(path: str, expected_parent=None):
    value = load_asset(path, unreal.Blueprint)
    status = value.get_editor_property("status")
    require(
        status in {
            unreal.BlueprintStatus.BS_UP_TO_DATE,
            unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS,
        },
        f"Blueprint is not serialized up-to-date: {path} status={status}",
    )
    if expected_parent is not None:
        require(
            value.get_blueprint_parent_class() == expected_parent,
            "Blueprint parent mismatch: " + path,
        )
    return value


def class_is_child(value, parent) -> bool:
    return bool(unreal.MathLibrary.class_is_child_of(value, parent))


def mapping_records(context) -> list[dict[str, Any]]:
    mappings = list(
        context.get_editor_property("default_key_mappings").get_editor_property("mappings")
    )
    records = []
    for mapping in mappings:
        modifiers = list(mapping.get_editor_property("modifiers"))
        records.append(
            {
                "action": package_path(mapping.get_editor_property("action")),
                "key": str(
                    mapping.get_editor_property("key").get_editor_property("key_name")
                ).lower(),
                "modifiers": [item.get_class().get_name() for item in modifiers],
                "swizzles": [
                    str(item.get_editor_property("order"))
                    for item in modifiers
                    if isinstance(item, unreal.InputModifierSwizzleAxis)
                ],
                "negate_axes": [
                    {
                        "x": bool(item.get_editor_property("x")),
                        "y": bool(item.get_editor_property("y")),
                        "z": bool(item.get_editor_property("z")),
                    }
                    for item in modifiers
                    if isinstance(item, unreal.InputModifierNegate)
                ],
                "triggers": [
                    item.get_class().get_name()
                    for item in mapping.get_editor_property("triggers")
                ],
            }
        )
    return records


def subobject_records(blueprint) -> list[dict[str, Any]]:
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = list(subsystem.k2_gather_subobject_data_for_blueprint(blueprint))
    require(handles, "No Blueprint subobject data: " + blueprint.get_path_name())
    library = unreal.SubobjectDataBlueprintFunctionLibrary
    result = []
    for handle in handles:
        data = library.get_data(handle)
        result.append(
            {
                "variable": str(library.get_variable_name(data)),
                "component": library.get_object_for_blueprint(data, blueprint),
                "is_component": bool(library.is_component(data)),
            }
        )
    return result


def one_component(blueprint, component_type: type, names: Iterable[str]):
    accepted = set(names)
    records = [
        record
        for record in subobject_records(blueprint)
        if record["is_component"]
        and isinstance(record["component"], component_type)
        and record["variable"] in accepted
    ]
    unique = {id(record["component"]): record for record in records}
    require(
        len(unique) == 1,
        f"Expected one {component_type.__name__} {sorted(accepted)}; found {records}",
    )
    return next(iter(unique.values()))["component"]


def path_of(value: Any) -> str:
    return "" if value is None else value.get_path_name()


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


def verify_protected_hashes() -> dict[str, str]:
    result = {}
    for path, expected in PROTECTED_FILES.items():
        require(os.path.isfile(path), "Protected file missing: " + path)
        actual = sha256(path)
        require(actual == expected, "Protected hash drift: " + path)
        result[path] = actual
    return result


def atomic_write_json(path: str, value: dict[str, Any]) -> None:
    require(not os.path.lexists(path), "Verifier report no-clobber failed before write")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp." + str(os.getpid())
    require(not os.path.lexists(temporary), "Verifier temporary report exists")
    try:
        with open(temporary, "x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.remove(temporary)


def verify(report_path: str) -> dict[str, Any]:
    build_path = os.environ.get(BUILD_REPORT_ENV, "")
    require(build_path, "Input build-report environment is missing")
    build_path = canonical(build_path)
    require(
        os.path.commonpath([build_path, canonical(REPORT_ROOT)]) == canonical(REPORT_ROOT),
        "Unsafe input build-report path",
    )
    require(build_path != report_path, "Input and output report paths collide")
    require(current_project() == canonical(PROJECT_FILE), "Wrong Unreal project")
    require(sha256(PROJECT_FILE) == PROJECT_SHA256, "Project descriptor hash drift")
    require(sha256(HOME_MAP_FILE) == HOME_MAP_SHA256, "Home map prehash drift")
    require(sha256(SOURCE_SHIP_FILE) == SOURCE_SHIP_SHA256, "Source ship package hash drift")
    require(dirty_packages() == {"content": [], "maps": []}, "Fresh process started dirty")
    pie_worlds = list(
        unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=False)
    )
    require(not pie_worlds, "PIE is active in fresh verifier")
    editor_world = unreal.EditorLevelLibrary.get_editor_world()
    require(editor_world is not None, "Fresh verifier editor world is unavailable")
    loaded_world_package = editor_world.get_outermost().get_path_name()
    require(
        loaded_world_package == "/Engine/Maps/Entry",
        "Fresh verifier must launch only /Engine/Maps/Entry; got " + loaded_world_package,
    )
    providers = {str(port): port_listening(port) for port in PROVIDER_PORTS}
    require(not any(providers.values()), "Provider listener active: " + str(providers))

    build = load_json(build_path)
    require(str(build.get("status", "")).startswith("pass_"), "Input build did not pass")
    require(build.get("transaction") == "clean_redmmo_trooper_assets_a01", "Input build transaction drift")
    require(canonical(str(build.get("project", ""))) == canonical(PROJECT_FILE), "Input build project drift")
    require(build.get("map_mutation_authorized") is False, "Input build authorized map mutation")
    require(build.get("map_saved") is False, "Input build saved a map")
    require(build.get("config_saved") is False, "Input build saved config")
    require(build.get("vendor_assets_modified") is False, "Input build modified vendor assets")
    preflight = build.get("preflight", {})
    require(preflight.get("home_map_sha256") == HOME_MAP_SHA256, "Input build home hash drift")
    require(preflight.get("source_ship_sha256") == SOURCE_SHIP_SHA256, "Input build source-ship hash drift")
    protected = verify_protected_hashes()
    require(preflight.get("protected_hashes") == protected, "Input build protected-hash evidence drift")
    require(tuple(build.get("created_assets", [])) == TARGETS, "Build target order/set drift")
    saved_items = build.get("saved_assets", [])
    require(isinstance(saved_items, list) and len(saved_items) == len(TARGETS), "Build saved-record cardinality drift")
    saved = {item["package"]: item for item in saved_items}
    require(set(saved) == set(TARGETS), "Build saved-asset set drift")
    file_records = []
    for package in TARGETS:
        path = asset_file(package)
        require(os.path.isfile(path), "Saved asset missing: " + package)
        require(canonical(str(saved[package].get("file", ""))) == canonical(path), "Saved asset path drift: " + package)
        require(bool(saved[package].get("class")), "Saved asset class evidence missing: " + package)
        actual = sha256(path)
        require(actual == str(saved[package]["sha256"]).upper(), "Saved asset hash drift: " + package)
        file_records.append({"package": package, "file": path, "sha256": actual})

    native = {}
    for key, path in NATIVE_CLASSES.items():
        native[key] = unreal.load_class(None, path)
        require(native[key] is not None, "Native class unavailable: " + path)

    actions = {
        key: load_asset(path, unreal.InputAction) for key, path in ACTION_PATHS.items()
    }
    ship_actions = {
        key: load_asset(path, unreal.InputAction)
        for key, path in SHIP_ACTION_PATHS.items()
    }
    expected_on_foot_types = {
        "move": unreal.InputActionValueType.AXIS2D,
        "look": unreal.InputActionValueType.AXIS2D,
        "jump": unreal.InputActionValueType.BOOLEAN,
        "sprint": unreal.InputActionValueType.BOOLEAN,
        "fire": unreal.InputActionValueType.BOOLEAN,
        "ads": unreal.InputActionValueType.BOOLEAN,
        "interact": unreal.InputActionValueType.BOOLEAN,
    }
    expected_ship_types = {
        "move": unreal.InputActionValueType.AXIS3D,
        "look": unreal.InputActionValueType.AXIS2D,
        "roll": unreal.InputActionValueType.AXIS1D,
        "boost": unreal.InputActionValueType.BOOLEAN,
        "exit": unreal.InputActionValueType.BOOLEAN,
    }
    for key, expected in expected_on_foot_types.items():
        require(actions[key].get_editor_property("value_type") == expected, "On-foot action type drift: " + key)
    for key, expected in expected_ship_types.items():
        require(ship_actions[key].get_editor_property("value_type") == expected, "Ship action type drift: " + key)

    on_foot_context = load_asset(INPUT_CONTEXT, unreal.InputMappingContext)
    ship_context = load_asset(SHIP_INPUT_CONTEXT, unreal.InputMappingContext)
    on_foot_mappings = mapping_records(on_foot_context)
    ship_mappings = mapping_records(ship_context)
    expected_on_foot_pairs = {
        (ACTION_PATHS["move"], "w"), (ACTION_PATHS["move"], "s"),
        (ACTION_PATHS["move"], "a"), (ACTION_PATHS["move"], "d"),
        (ACTION_PATHS["look"], "mouse2d"), (ACTION_PATHS["jump"], "spacebar"),
        (ACTION_PATHS["sprint"], "leftshift"),
        (ACTION_PATHS["fire"], "leftmousebutton"),
        (ACTION_PATHS["ads"], "rightmousebutton"),
        (ACTION_PATHS["interact"], "f"),
    }
    expected_ship_pairs = {
        (SHIP_ACTION_PATHS["move"], "w"), (SHIP_ACTION_PATHS["move"], "s"),
        (SHIP_ACTION_PATHS["move"], "a"), (SHIP_ACTION_PATHS["move"], "d"),
        (SHIP_ACTION_PATHS["move"], "spacebar"),
        (SHIP_ACTION_PATHS["move"], "leftcontrol"),
        (SHIP_ACTION_PATHS["look"], "mouse2d"),
        (SHIP_ACTION_PATHS["roll"], "q"), (SHIP_ACTION_PATHS["roll"], "e"),
        (SHIP_ACTION_PATHS["boost"], "leftshift"),
        (SHIP_ACTION_PATHS["exit"], "f"),
    }
    require(len(on_foot_mappings) == 10, "On-foot mapping count drift")
    require(len(ship_mappings) == 11, "Ship mapping count drift")
    require(
        {(item["action"], item["key"]) for item in on_foot_mappings}
        == expected_on_foot_pairs,
        "On-foot mapping pair drift",
    )
    require(
        {(item["action"], item["key"]) for item in ship_mappings}
        == expected_ship_pairs,
        "Ship mapping pair drift",
    )
    require(not any(item["triggers"] for item in on_foot_mappings + ship_mappings), "Unexpected input trigger")
    on_foot_by_key = {item["key"]: item for item in on_foot_mappings}
    ship_by_key = {item["key"]: item for item in ship_mappings}
    require(
        on_foot_by_key["w"]["modifiers"] == ["InputModifierSwizzleAxis"]
        and on_foot_by_key["w"]["swizzles"] == [str(unreal.InputAxisSwizzle.YXZ)]
        and on_foot_by_key["s"]["modifiers"]
        == ["InputModifierSwizzleAxis", "InputModifierNegate"]
        and on_foot_by_key["s"]["swizzles"] == [str(unreal.InputAxisSwizzle.YXZ)]
        and on_foot_by_key["a"]["modifiers"] == ["InputModifierNegate"]
        and all(
            not on_foot_by_key[key]["modifiers"]
            for key in (
                "d", "mouse2d", "spacebar", "leftshift", "leftmousebutton",
                "rightmousebutton", "f",
            )
        ),
        "On-foot modifier/swizzle semantics drift",
    )
    require(
        ship_by_key["s"]["modifiers"] == ["InputModifierNegate"]
        and ship_by_key["a"]["modifiers"]
        == ["InputModifierSwizzleAxis", "InputModifierNegate"]
        and ship_by_key["a"]["swizzles"] == [str(unreal.InputAxisSwizzle.YXZ)]
        and ship_by_key["d"]["modifiers"] == ["InputModifierSwizzleAxis"]
        and ship_by_key["d"]["swizzles"] == [str(unreal.InputAxisSwizzle.YXZ)]
        and ship_by_key["spacebar"]["modifiers"] == ["InputModifierSwizzleAxis"]
        and ship_by_key["spacebar"]["swizzles"] == [str(unreal.InputAxisSwizzle.ZYX)]
        and ship_by_key["leftcontrol"]["modifiers"]
        == ["InputModifierSwizzleAxis", "InputModifierNegate"]
        and ship_by_key["leftcontrol"]["swizzles"]
        == [str(unreal.InputAxisSwizzle.ZYX)]
        and ship_by_key["q"]["modifiers"] == ["InputModifierNegate"]
        and all(
            not ship_by_key[key]["modifiers"]
            for key in ("w", "mouse2d", "e", "leftshift", "f")
        ),
        "Ship modifier/swizzle semantics drift",
    )
    negated_on_foot_keys = {"s", "a"}
    negated_ship_keys = {"s", "a", "leftcontrol", "q"}
    expected_negate_axes = [{"x": True, "y": True, "z": True}]
    require(
        all(
            item["negate_axes"]
            == (expected_negate_axes if key in negated_on_foot_keys else [])
            for key, item in on_foot_by_key.items()
        ),
        "On-foot negate-axis semantics drift",
    )
    require(
        all(
            item["negate_axes"]
            == (expected_negate_axes if key in negated_ship_keys else [])
            for key, item in ship_by_key.items()
        ),
        "Ship negate-axis semantics drift",
    )
    require(
        actions["move"].get_editor_property("accumulation_behavior")
        == unreal.InputActionAccumulationBehavior.CUMULATIVE,
        "On-foot move accumulation drift",
    )
    require(
        ship_actions["move"].get_editor_property("accumulation_behavior")
        == unreal.InputActionAccumulationBehavior.CUMULATIVE
        and ship_actions["roll"].get_editor_property("accumulation_behavior")
        == unreal.InputActionAccumulationBehavior.CUMULATIVE,
        "Ship cumulative input semantics drift",
    )

    source_ship_class = unreal.load_class(None, SOURCE_SHIP_CLASS)
    require(source_ship_class is not None and class_is_child(source_ship_class, native["ship"]), "Source ship native compatibility failed")
    bolt = load_blueprint(BOLT_BP, native["bolt"])
    player = load_blueprint(PLAYER_BP, native["player"])
    ship = load_blueprint(SHIP_BP, source_ship_class)
    game_mode = load_blueprint(GAME_MODE_BP, native["game_mode"])
    require(class_is_child(ship.generated_class(), native["ship"]), "A01 ship is not a RedShip subclass")

    bolt_cdo = unreal.get_default_object(bolt.generated_class())
    player_cdo = unreal.get_default_object(player.generated_class())
    ship_cdo = unreal.get_default_object(ship.generated_class())
    game_mode_cdo = unreal.get_default_object(game_mode.generated_class())
    require(player_cdo.get_editor_property("default_mapping_context") == on_foot_context, "Player IMC drift")
    require(player_cdo.get_editor_property("ship_mapping_context") == ship_context, "Player ship IMC drift")
    for property_name, key in (
        ("move_action", "move"), ("look_action", "look"),
        ("jump_action", "jump"), ("sprint_action", "sprint"),
        ("fire_action", "fire"), ("ads_action", "ads"),
        ("interact_action", "interact"),
    ):
        require(player_cdo.get_editor_property(property_name) == actions[key], "Player action drift: " + property_name)
    for property_name, object_path in ANIMATIONS.items():
        require(
            path_of(player_cdo.get_editor_property(property_name)) == object_path,
            "Player animation drift: " + property_name,
        )
    require(player_cdo.get_editor_property("bolt_class") == bolt.generated_class(), "Player bolt class drift")
    require(path_of(player_cdo.get_editor_property("muzzle_vfx")) == MUZZLE_VFX, "Player muzzle VFX drift")
    require(str(player_cdo.get_editor_property("muzzle_socket_name")) == "Muzzle", "Player muzzle socket drift")
    require(ship_cdo.get_editor_property("ship_mapping_context") == ship_context, "Ship IMC drift")
    require(ship_cdo.get_editor_property("on_foot_mapping_context") == on_foot_context, "Ship on-foot IMC drift")
    for property_name, key in (
        ("move_action", "move"), ("look_action", "look"),
        ("roll_action", "roll"), ("boost_action", "boost"),
        ("exit_action", "exit"),
    ):
        require(ship_cdo.get_editor_property(property_name) == ship_actions[key], "Ship action drift: " + property_name)
    require(game_mode_cdo.get_editor_property("default_pawn_class") == player.generated_class(), "GameMode pawn drift")
    require(game_mode_cdo.get_editor_property("starter_ship_class") == ship.generated_class(), "GameMode ship drift")
    require(path_of(bolt_cdo.get_editor_property("projectile_mesh_asset")) == BOLT_MESH, "Bolt mesh drift")
    require(path_of(bolt_cdo.get_editor_property("projectile_material")) == BOLT_MATERIAL, "Bolt material drift")
    require(path_of(bolt_cdo.get_editor_property("impact_vfx")) == IMPACT_VFX, "Bolt impact VFX drift")

    body = one_component(player, unreal.SkeletalMeshComponent, ("CharacterMesh0", "Mesh"))
    weapon = one_component(player, unreal.SkeletalMeshComponent, ("WeaponMesh",))
    require(path_of(body.get_skeletal_mesh_asset()) == BODY_MESH, "Trooper body mesh drift")
    require(path_of(weapon.get_skeletal_mesh_asset()) == RIFLE_MESH, "Trooper rifle mesh drift")
    require(body.does_socket_exist(unreal.Name("hand_rSocket")), "Trooper hand socket missing")
    require(weapon.does_socket_exist(unreal.Name("Muzzle")), "Rifle muzzle socket missing")
    require(
        body.get_editor_property("animation_mode") == unreal.AnimationMode.ANIMATION_SINGLE_NODE,
        "Trooper body animation mode drift",
    )
    require(
        not bool(body.get_editor_property("hidden_in_game"))
        and bool(body.get_editor_property("visible")),
        "Trooper body visibility drift",
    )
    require(
        vector_is(body.get_editor_property("relative_location"), 0.0, 0.0, -96.0)
        and rotator_is(body.get_editor_property("relative_rotation"), 0.0, -90.0, 0.0)
        and vector_is(body.get_editor_property("relative_scale3d"), 1.0, 1.0, 1.0),
        "Trooper body relative transform drift",
    )
    require(weapon.get_attach_parent() == body, "Rifle parent drift")
    require(str(weapon.get_attach_socket_name()) == "hand_rSocket", "Rifle attach socket drift")
    require(
        weapon.get_collision_enabled() == unreal.CollisionEnabled.NO_COLLISION
        and not bool(weapon.get_editor_property("generate_overlap_events")),
        "Rifle collision/overlap drift",
    )
    require(
        vector_is(weapon.get_editor_property("relative_location"), 0.0, 0.0, 0.0)
        and rotator_is(weapon.get_editor_property("relative_rotation"), 0.0, 0.0, 0.0)
        and vector_is(weapon.get_editor_property("relative_scale3d"), 1.0, 1.0, 1.0),
        "Rifle relative transform drift",
    )

    require(dirty_packages() == {"content": [], "maps": []}, "Fresh verifier dirtied packages")
    require(sha256(HOME_MAP_FILE) == HOME_MAP_SHA256, "Fresh verifier changed the home map")
    require(sha256(SOURCE_SHIP_FILE) == SOURCE_SHIP_SHA256, "Fresh verifier changed source ship")
    return {
        "schema_version": 1,
        "status": "pass_fresh_process_serialized_readback",
        "captured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "evidence_class": "fresh_unreal_editor_asset_load_readback_no_save",
        "project": PROJECT_FILE,
        "build_report": {"path": build_path, "sha256": sha256(build_path)},
        "provider_ports_listening": providers,
        "protected_hashes": protected,
        "loaded_world_package": loaded_world_package,
        "pie_world_count": len(pie_worlds),
        "files": file_records,
        "input": {"on_foot": on_foot_mappings, "ship": ship_mappings},
        "blueprints": {
            "bolt": BOLT_BP, "player": PLAYER_BP, "ship": SHIP_BP,
            "game_mode": GAME_MODE_BP, "source_ship_class": SOURCE_SHIP_CLASS,
        },
        "mesh_and_socket_readback": {
            "body": BODY_MESH, "body_socket": "hand_rSocket",
            "rifle": RIFLE_MESH, "rifle_socket": "Muzzle",
            "rifle_attachment_socket": "hand_rSocket",
        },
        "home_map_sha256_after": sha256(HOME_MAP_FILE),
        "source_ship_sha256_after": sha256(SOURCE_SHIP_FILE),
        "dirty_packages_after": dirty_packages(),
        "project_map_loaded": loaded_world_package.startswith("/Game/"),
        "map_saved": False,
        "assets_saved": False,
        "pie_active": bool(pie_worlds),
        "claim_limit": (
            "Fresh-process serialized load/readback only. No compile/save, MapCheck, map bind, "
            "runtime, animation-in-motion, visual, input, collision, networking, PIE, package, "
            "multiplayer, or player-acceptance claim."
        ),
    }


_report_path = ""
try:
    _report_path = validated_report_path(os.environ.get(REPORT_ENV, ""))
    _result = verify(_report_path)
except Exception as _error:
    _result = {
        "schema_version": 1,
        "status": "fail",
        "captured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "error": str(_error),
        "traceback": traceback.format_exc(),
        "dirty_packages_after": dirty_packages(),
        "home_map_sha256_after": sha256(HOME_MAP_FILE) if os.path.isfile(HOME_MAP_FILE) else None,
    }
if _report_path:
    atomic_write_json(_report_path, _result)
if not str(_result.get("status", "")).startswith("pass_"):
    unreal.log_error("REDMMO_TROOPER_A01_FRESH_VERIFY FAIL " + str(_result.get("error", "")))
    raise RuntimeError(_result.get("error", "fresh verifier failed"))
unreal.log("REDMMO_TROOPER_A01_FRESH_VERIFY PASS")
