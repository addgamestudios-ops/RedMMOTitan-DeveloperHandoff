"""Fail-closed D3D12 PIE validation for the clean RedMMO A01 gameplay bind.

Run only in a fresh RedMMO editor process with ``-d3d12 -RenderOffscreen`` and
the exact bound PPG home map.  The required environment variable
``REDMMO_A01_PIE_REPORT`` must name a new ``result.json`` below the diagnostics
root.  The script never saves a package or configuration file.  It starts one
PIE world, drives the project-owned Enhanced Input actions directly, records
runtime telemetry, stops PIE, publishes one atomic no-clobber result, and exits
the editor.

This is automation evidence.  It proves the same InputAction event paths used
by the serialized F/WASD/mouse mappings, possession transitions, movement, and
authority-side spawning.  It deliberately does not claim physical-device feel,
human visual acceptance, packaging, standalone travel, or multiplayer.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import socket
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import unreal


PROJECT_ROOT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT_ROOT / "RedMMO.uproject"
PROJECT_SHA256 = os.environ.get(
    "REDMMO_A01_PROJECT_SHA256",
    "54E664A24FA5E9129C022740EE624F84389F1825AA9A4AE07D5E99DD783F382E",
).upper()
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT_ROOT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HOME_SHA256 = os.environ.get(
    "REDMMO_A01_HOME_SHA256",
    "1310D92641AC25DAEA4DF289A8B2C16A46F3F0D4AECB7FB9F4616FE5CEAD5209",
).upper()
BIND_HOME_SHA256 = "1310D92641AC25DAEA4DF289A8B2C16A46F3F0D4AECB7FB9F4616FE5CEAD5209"

BIND_REPORT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_HomeGameplayBind_A01_20260803T045519Z\bind_report.json"
)
BIND_REPORT_SHA256 = "79CFB186136A107C7869EE5E437FBAF367698E64F3F56DDC5DA6007DA254B4AC"
PROFILE_BIND_REPORT_ENV = "REDMMO_A01_PROFILE_BIND_REPORT"
PROFILE_BIND_REPORT_SHA256_ENV = "REDMMO_A01_PROFILE_BIND_REPORT_SHA256"
HOME_SUCCESSOR_REPORT_ENV = "REDMMO_A01_HOME_SUCCESSOR_REPORT"
HOME_SUCCESSOR_REPORT_SHA256_ENV = "REDMMO_A01_HOME_SUCCESSOR_REPORT_SHA256"
BUILD_REPORT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_TrooperAssets_A01_20260803T044000Z\build_report.json"
)
BUILD_REPORT_SHA256 = "21E20052DDAF86EA419AD0A00C9BEB3BB11EC2A34F3517608633E1D6202D19F1"
FRESH_REPORT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_TrooperAssets_A01_Fresh_20260803T044200Z\fresh_report.json"
)
FRESH_REPORT_SHA256 = "18346B265845444825332E9A946BFE0AF57E3115D4A86E35499B10D01DDFD571"

ROOT = "/Game/RedMMO/Gameplay/Trooper/A01"
GAME_MODE_CLASS = ROOT + "/Player/GM_RedTrooperPPG_A01.GM_RedTrooperPPG_A01_C"
PLAYER_CLASS = ROOT + "/Player/BP_RedTrooperPlayer_A01.BP_RedTrooperPlayer_A01_C"
SHIP_CLASS = ROOT + "/Ship/BP_RedModularStarSparrow_Trooper_A01.BP_RedModularStarSparrow_Trooper_A01_C"
BOLT_CLASS = ROOT + "/Combat/BP_RedBolt_Trooper_A01.BP_RedBolt_Trooper_A01_C"
ON_FOOT_CONTEXT = ROOT + "/Input/IMC_RedTrooper_A01"
SHIP_CONTEXT = ROOT + "/Input/IMC_RedShip_A01"
ACTIONS = {
    "move": ROOT + "/Input/IA_RedMove",
    "look": ROOT + "/Input/IA_RedLook",
    "jump": ROOT + "/Input/IA_RedJump",
    "sprint": ROOT + "/Input/IA_RedSprint",
    "fire": ROOT + "/Input/IA_RedFire",
    "ads": ROOT + "/Input/IA_RedADS",
    "interact": ROOT + "/Input/IA_RedInteract",
    "ship_move": ROOT + "/Input/IA_RedShipMove",
    "ship_look": ROOT + "/Input/IA_RedShipLook",
    "ship_roll": ROOT + "/Input/IA_RedShipRoll",
    "ship_boost": ROOT + "/Input/IA_RedShipBoost",
    "ship_exit": ROOT + "/Input/IA_RedShipExit",
}
ANIMATIONS = {
    "idle_animation": "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_Idle",
    "walk_animation": "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_ThirdPersonWalk",
    "run_animation": "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_Run",
    "jump_start_animation": "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_ThirdPersonJump_Start",
    "jump_loop_animation": "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_ThirdPersonJump_Loop",
    "jump_end_animation": "/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_ThirdPersonJump_End",
}
if os.environ.get("REDMMO_A01_RIFLE_READY_PROFILE") == "1":
    ANIMATIONS.update({
        "idle_animation": "/Game/Action_Male_and_Female/Animations/UE4TF/A_Tall_Female_Idle_Rifle",
        "walk_animation": "/Game/Action_Male_and_Female/Animations/UE4TF/A_Tall_Female_Sprint_Fwd_Rifle",
        "run_animation": "/Game/Action_Male_and_Female/Animations/UE4TF/A_Tall_Female_Sprint_Fwd_Rifle",
    })
BODY_MESH = "/Game/Action_Trooper/Meshes/Trooper_UE4_Tall_Female/SK_TF_Trooper_Standalone_Covered"
RIFLE_MESH = "/Game/RedMMO/Weapons/SK_RedTrooper_Rifle_A"
SOURCE_SHIP_FILE = PROJECT_ROOT / r"Content\RedMMO\Ships\BP_RedModularStarSparrow.uasset"
SOURCE_SHIP_SHA256 = "A8A6E128C2A08AE95A745B3A70C47A372339F314C67C6CE37539A25B67DC78C9"

BIND_PPG_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/DA_PPG_HomeWorld_StylizedBinding_R10O"
PPG_PLANET = os.environ.get("REDMMO_A01_PPG_PLANET", BIND_PPG_PLANET)
PPG_PLANET_FILE = PROJECT_ROOT / "Content" / (PPG_PLANET.removeprefix("/Game/") + ".uasset")
PPG_PLANET_SHA256 = os.environ.get(
    "REDMMO_A01_PPG_PLANET_SHA256",
    "7C6835CA50EBB06B4C94AA6D1E8B0419B1E0ACF09A44D5CEA5B670FBD5865C5A",
).upper()
PPG_FOLIAGE = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/Profiles/DA_PPG_HomeWorld_StylizedForest_R10O"
APPROVED_GRASS = (
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
)
APPROVED_GRASS_FILES = {
    PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset":
        "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset":
        "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
    PROJECT_ROOT / r"Content\StylizedRocksPack_01\Common\GrassChunks\Meshes\SM_GrassChunk_01.uasset":
        "294B5C257FFD2D31F192665E5A97F93E0B97E6B4D19C93D89782A338DD6AE699",
}
TRACKED_PACKAGE_HASH_OVERRIDES = {
    "/Game/RedMMO/Gameplay/Trooper/A01/Combat/BP_RedBolt_Trooper_A01": os.environ.get(
        "REDMMO_A01_BOLT_PACKAGE_SHA256", ""
    ).upper(),
    "/Game/RedMMO/Gameplay/Trooper/A01/Player/BP_RedTrooperPlayer_A01": os.environ.get(
        "REDMMO_A01_PLAYER_PACKAGE_SHA256", ""
    ).upper(),
}
TRACKED_PACKAGE_HASH_OVERRIDES = {
    package: digest for package, digest in TRACKED_PACKAGE_HASH_OVERRIDES.items() if digest
}

PROTECTED_FILES = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen.umap"):
        "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Environment\DA_RED_Planet50Km_FusedHeightfield.uasset"):
        "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"):
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap"):
        "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}

DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
REPORT_ENV = "REDMMO_A01_PIE_REPORT"
SCREENSHOT_ENV = "REDMMO_A01_PIE_SCREENSHOT"
FOLIAGE_SETTLE_ENV = "REDMMO_A01_FOLIAGE_SETTLE_SECONDS"
PROVIDER_PORTS = (5353, 8000, 8765)
OLD_VISUAL_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
EXPECTED_EDITOR_ACTOR_COUNT = 11
MIN_GROUND_DISPLACEMENT_CM = 500.0
MIN_SHIP_DISPLACEMENT_CM = 900.0


class ValidationError(RuntimeError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_json(path: Path, expected_hash: str, label: str) -> dict[str, Any]:
    require(path.is_file(), f"{label} is missing: {path}")
    require(sha256(path) == expected_hash, f"{label} hash drift")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{label} is not a JSON object")
    return value


def report_path() -> Path:
    raw = os.environ.get(REPORT_ENV, "")
    require(bool(raw), f"{REPORT_ENV} is required")
    root = DIAGNOSTICS_ROOT.resolve(strict=True)
    path = Path(raw).resolve(strict=False)
    require(os.path.commonpath([str(path), str(root)]) == str(root), "Unsafe PIE report path")
    require(path.name == "result.json", "PIE report must be named result.json")
    require(path.parent.name.startswith("RedMMO_TrooperStarSparrow_A01_PIE_"), "Unexpected PIE report directory")
    require(not os.path.lexists(path), f"PIE report no-clobber failed: {path}")
    require(not os.path.lexists(path.with_name("state.json")), "PIE state no-clobber failed")
    path.parent.mkdir(parents=True, exist_ok=False)
    return path


def optional_screenshot_path(result: Path) -> Path | None:
    raw = os.environ.get(SCREENSHOT_ENV, "")
    if not raw:
        return None
    root = DIAGNOSTICS_ROOT.resolve(strict=True)
    path = Path(raw).resolve(strict=False)
    require(os.path.commonpath([str(path), str(root)]) == str(root), "Unsafe PIE screenshot path")
    require(path.parent == result.parent, "PIE screenshot must share the result directory")
    require(path.suffix.lower() == ".png", "PIE screenshot must be PNG")
    require(not os.path.lexists(path), f"PIE screenshot no-clobber failed: {path}")
    return path


def atomic_replace_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.parent / ("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def atomic_no_clobber_json(path: Path, value: dict[str, Any]) -> None:
    require(not os.path.lexists(path), f"Final report target appeared during run: {path}")
    temporary = path.parent / ("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.rename(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def asset_path(value: Any) -> str | None:
    if value is None:
        return None
    path = str(value.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    if "." in leaf:
        path = path.rsplit(".", 1)[0]
    if path.endswith("_C"):
        path = path[:-2]
    return path


def class_path(value: Any) -> str | None:
    return value.get_class().get_path_name() if value is not None else None


def vec(value: Any) -> list[float]:
    return [float(value.x), float(value.y), float(value.z)]


def add(a: Any, b: Any) -> Any:
    return unreal.Vector(a.x + b.x, a.y + b.y, a.z + b.z)


def sub(a: Any, b: Any) -> Any:
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def mul(value: Any, scalar: float) -> Any:
    return unreal.Vector(value.x * scalar, value.y * scalar, value.z * scalar)


def dot(a: Any, b: Any) -> float:
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def length(value: Any) -> float:
    return math.sqrt(max(0.0, dot(value, value)))


def normalized(value: Any) -> Any:
    magnitude = length(value)
    require(magnitude > 1.0e-6, "Cannot normalize zero vector")
    return mul(value, 1.0 / magnitude)


def plane_project(value: Any, normal: Any) -> Any:
    return sub(value, mul(normal, dot(value, normal)))


def distance(a: Any, b: Any) -> float:
    return length(sub(a, b))


def dirty_packages() -> dict[str, list[str]]:
    return {
        "content": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}),
        "maps": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}),
    }


def no_dirty() -> bool:
    values = dirty_packages()
    return not values["content"] and not values["maps"]


def provider_gate() -> dict[str, bool]:
    closed: dict[str, bool] = {}
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            closed[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(closed.values()), f"AI/MCP/provider listener active: {closed}")
    return closed


def hash_tree(root: Path) -> list[dict[str, Any]]:
    require(root.is_dir(), f"Tree root missing: {root}")
    return [
        {
            "path": str(item.relative_to(root)).replace("\\", "/"),
            "bytes": item.stat().st_size,
            "sha256": sha256(item),
        }
        for item in sorted((candidate for candidate in root.rglob("*") if candidate.is_file()), key=lambda candidate: str(candidate).lower())
    ]


def verify_hashes(values: dict[Path, str], label: str) -> dict[str, str]:
    output: dict[str, str] = {}
    for path, expected in values.items():
        require(path.is_file(), f"{label} missing: {path}")
        actual = sha256(path)
        require(actual == expected, f"{label} hash drift: {path} expected={expected} actual={actual}")
        output[str(path)] = actual
    return output


def package_file(package: str) -> Path:
    require(package.startswith("/Game/"), f"Unexpected package root: {package}")
    return PROJECT_ROOT / ("Content" + package.removeprefix("/Game").replace("/", os.sep) + ".uasset")


def current_map(world: Any) -> str:
    path = world.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def command_log_path() -> Path:
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    path = Path((match.group(1) or match.group(2)) if match else PROJECT_ROOT / r"Saved\Logs\RedMMO.log")
    return path


def map_check(world: Any) -> dict[str, Any]:
    log = command_log_path()
    require(log.is_file(), f"Editor log missing for MapCheck: {log}")
    offset = log.stat().st_size
    marker = "REDMMO_A01_PIE_MAPCHECK_" + uuid.uuid4().hex.upper()
    unreal.log(marker)
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECKDEP NOCLEARLOG")
    pattern = re.compile(r"MapCheck: Map check complete: (\d+) Error\(s\), (\d+) Warning\(s\)")
    matches: list[tuple[str, str]] = []
    segment = ""
    for _ in range(160):
        time.sleep(0.1)
        with log.open("rb") as stream:
            stream.seek(min(offset, log.stat().st_size))
            segment = stream.read().decode("utf-8", errors="replace")
        if marker in segment:
            matches = pattern.findall(segment.split(marker, 1)[1])
        if marker in segment and matches:
            break
    require(marker in segment and matches, "No fresh authoritative MapCheck completion marker")
    errors, warnings = (int(value) for value in matches[-1])
    require(errors == 0 and warnings == 0, f"MapCheck failed: {errors} errors, {warnings} warnings")
    return {"errors": errors, "warnings": warnings, "marker": marker, "log": str(log), "log_offset": offset}


def load_asset_exact(path: str) -> Any:
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None and asset_path(asset) == path, f"Asset load failed: {path}")
    return asset


def component_named(actor: Any, component_class: Any, name: str) -> Any:
    matches = [item for item in actor.get_components_by_class(component_class) if item.get_name() == name]
    require(len(matches) == 1, f"Expected one {name} component on {actor.get_path_name()}, found {len(matches)}")
    return matches[0]


def enum_text(value: Any) -> str:
    return str(value).upper().replace(" ", "_")


def role_is_authority(actor: Any) -> bool:
    getter = getattr(actor, "get_local_role", None)
    require(callable(getter), f"Actor role API unavailable: {actor.get_path_name()}")
    return "AUTHORITY" in enum_text(getter())


def actor_hidden_in_game(actor: Any) -> bool:
    """Read AActor's runtime-hidden flag across supported Python reflections."""
    for method_name in ("is_hidden", "is_actor_hidden_in_game"):
        method = getattr(actor, method_name, None)
        if callable(method):
            try:
                return bool(method())
            except Exception:
                pass
    for property_name in ("hidden", "hidden_in_game"):
        try:
            return bool(actor.get_editor_property(property_name))
        except Exception:
            pass
    raise ValidationError("Actor hidden-in-game API unavailable: " + actor.get_path_name())


def actor_owner(actor: Any) -> Any:
    method = getattr(actor, "get_owner", None)
    if callable(method):
        return method()
    try:
        return actor.get_editor_property("owner")
    except Exception as error:
        raise ValidationError("Actor owner API unavailable: " + actor.get_path_name()) from error


def actor_instigator(actor: Any) -> Any:
    method = getattr(actor, "get_instigator", None)
    if callable(method):
        return method()
    try:
        return actor.get_editor_property("instigator")
    except Exception as error:
        raise ValidationError("Actor instigator API unavailable: " + actor.get_path_name()) from error


def component_collision_point(component: Any, probe_point: Any) -> tuple[float, Any] | None:
    query = getattr(component, "get_closest_point_on_collision", None)
    if not callable(query):
        return None
    raw = query(probe_point)
    values = raw if isinstance(raw, tuple) else (raw,)
    point = next((item for item in values if isinstance(item, unreal.Vector)), None)
    numeric = next((float(item) for item in values if isinstance(item, (int, float)) and math.isfinite(float(item))), None)
    if point is None or numeric is None or numeric < 0.0:
        return None
    return numeric, point


def owned_surface_at_direction(spawner: Any, center: Any, direction: Any, nominal_radius: float) -> dict[str, Any]:
    direction = normalized(direction)
    probe = add(center, mul(direction, nominal_radius + 5_000_000.0))
    candidates = []
    for component in spawner.get_components_by_class(unreal.StaticMeshComponent):
        if isinstance(component, unreal.InstancedStaticMeshComponent):
            continue
        mesh = component.get_editor_property("static_mesh")
        if mesh is None or not component.is_query_collision_enabled():
            continue
        result = component_collision_point(component, probe)
        if result is None:
            continue
        query_distance, point = result
        radial = sub(point, center)
        if length(radial) <= 1.0:
            continue
        alignment = dot(normalized(radial), direction)
        if alignment >= 0.9995:
            candidates.append((query_distance, alignment, component, point))
    require(candidates, "No aligned query-collision PPG terrain component")
    candidates.sort(key=lambda item: (-item[1], item[0]))
    query_distance, alignment, component, point = candidates[0]
    return {
        "owner": spawner.get_path_name(),
        "component": component.get_path_name(),
        "component_mesh": asset_path(component.get_editor_property("static_mesh")),
        "point": vec(point),
        "radius_cm": length(sub(point, center)),
        "alignment": alignment,
        "query_distance_cm": query_distance,
    }


def input_subsystem_for_world(world: Any) -> Any:
    candidates = []
    for item in unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem):
        try:
            if item.get_world() == world:
                candidates.append(item)
        except Exception:
            continue
    require(len(candidates) == 1, "Expected exactly one PIE EnhancedInputLocalPlayerSubsystem: " + str([item.get_path_name() for item in candidates]))
    subsystem = candidates[0]
    for method in ("inject_input_vector_for_action",):
        require(callable(getattr(subsystem, method, None)), f"Enhanced Input API missing: {method}")
    return subsystem


def input_context_state(owner: Any) -> dict[str, bool]:
    mask = int(owner.get_input_mapping_context_mask())
    return {
        "on_foot": bool(mask & 1),
        "ship": bool(mask & 2),
    }


def runtime_foliage_state(world: Any, player_location: Any) -> dict[str, Any]:
    records = []
    approved_instances = 0
    actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
    inspected_components = 0
    query_errors = []
    actor_classes: dict[str, int] = {}
    component_classes: dict[str, int] = {}
    static_mesh_components = []
    foliage_actor_components = []
    for actor in actors:
        actor_class = actor.get_class().get_name()
        actor_classes[actor_class] = actor_classes.get(actor_class, 0) + 1
        for component in list(actor.get_components_by_class(unreal.ActorComponent)):
            component_class = component.get_class().get_name()
            component_classes[component_class] = component_classes.get(component_class, 0) + 1
            try:
                mesh = component.get_editor_property("static_mesh")
                if mesh is not None:
                    bounds_origin, bounds_extent, bounds_radius = unreal.SystemLibrary.get_component_bounds(component)
                    static_mesh_components.append({
                        "actor": actor.get_path_name(),
                        "component": component.get_path_name(),
                        "class": component_class,
                        "mesh": asset_path(mesh),
                        "component_location": vec(component.get_world_location()),
                        "distance_to_player_cm": length(component.get_world_location() - player_location),
                        "visible": bool(component.get_editor_property("visible")),
                        "hidden_in_game": bool(component.get_editor_property("hidden_in_game")),
                        "bounds_origin": vec(bounds_origin),
                        "bounds_extent": vec(bounds_extent),
                        "bounds_radius_cm": float(bounds_radius),
                    })
            except Exception:
                pass
            count_method = getattr(component, "get_instance_count", None)
            if not callable(count_method):
                continue
            inspected_components += 1
            try:
                mesh = component.get_editor_property("static_mesh")
                mesh_path = asset_path(mesh)
                count = int(count_method())
                if count <= 0:
                    continue
                location = component.get_world_location()
                record = {
                    "actor": actor.get_path_name(),
                    "component": component.get_path_name(),
                    "class": component.get_class().get_name(),
                    "mesh": mesh_path,
                    "instance_count": count,
                    "distance_to_player_cm": length(location - player_location),
                    "visible": bool(component.get_editor_property("visible")),
                    "hidden_in_game": bool(component.get_editor_property("hidden_in_game")),
                }
                records.append(record)
                if mesh_path in APPROVED_GRASS:
                    approved_instances += count
            except Exception as error:
                query_errors.append({
                    "actor": actor.get_path_name(),
                    "component": component.get_path_name(),
                    "error": str(error),
                })
    # PPG 1.0's current runtime foliage path uses transient
    # UPPGGPUFoliageComponent objects. They are UStaticMeshComponent-derived
    # render components and do not expose the CPU ISMC get_instance_count API.
    # Query the authoritative foliage actor directly so component presence and
    # selected-mesh identity remain observable without pretending a CPU count.
    spawners = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
    spawners = [actor for actor in spawners if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    if len(spawners) == 1:
        get_foliage_actor = getattr(spawners[0], "get_foliage_actor", None)
        foliage_actor = get_foliage_actor() if callable(get_foliage_actor) else None
        if foliage_actor is not None:
            for component in list(foliage_actor.get_components_by_class(unreal.StaticMeshComponent)):
                mesh_path = asset_path(component.get_editor_property("static_mesh"))
                foliage_actor_components.append({
                    "component": component.get_path_name(),
                    "class": component.get_class().get_name(),
                    "mesh": mesh_path,
                    "approved_grass": mesh_path in APPROVED_GRASS,
                    "visible": bool(component.get_editor_property("visible")),
                    "hidden_in_game": bool(component.get_editor_property("hidden_in_game")),
                })
    records.sort(key=lambda item: (-item["instance_count"], item["mesh"] or "", item["component"]))
    return {
        "approved_grass_instance_count": approved_instances,
        "world_actor_count": len(actors),
        "actor_class_counts": dict(sorted(actor_classes.items())),
        "component_class_counts": dict(sorted(component_classes.items())),
        "static_mesh_components": static_mesh_components,
        "inspected_instanced_component_count": inspected_components,
        "populated_component_count": len(records),
        "populated_components": records,
        "query_errors": query_errors,
        "foliage_actor_static_mesh_components": foliage_actor_components,
        "approved_grass_component_count": sum(
            1 for item in foliage_actor_components if item["approved_grass"]
        ),
    }


class A01PIEValidation:
    def __init__(self) -> None:
        self.result_path = report_path()
        self.screenshot_path = optional_screenshot_path(self.result_path)
        self.screenshot_requested = False
        self.foliage_settle_seconds = max(float(os.environ.get(FOLIAGE_SETTLE_ENV, "0")), 0.0)
        self.state_path = self.result_path.with_name("state.json")
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.phase_started = time.monotonic()
        self.phase_frames = 0
        self.world = None
        self.spawner = None
        self.center = None
        self.initial_center = None
        self.nominal_radius = None
        self.controller = None
        self.trooper = None
        self.ship = None
        self.movement = None
        self.input_subsystem = None
        self.contexts: dict[str, Any] = {}
        self.actions: dict[str, Any] = {}
        self.body = None
        self.weapon = None
        self.tracked_hashes: dict[Path, str] = {}
        self.tracked_before: dict[str, str] = {}
        self.config_before: list[dict[str, Any]] = []
        self.phase_start_location = None
        self.phase_start_forward = None
        self.phase_start_right = None
        self.phase_start_up = None
        self.phase_max_speed = 0.0
        self.grounded_frames = 0
        self.jump_pulsed = False
        self.fire_pulsed = False
        self.enter_pulsed = False
        self.exit_pulsed = False
        self.new_bolt = None
        self.bolts_before: set[str] = set()
        self.muzzle_at_fire = None
        self.abort_error: Exception | None = None
        self.quit_scheduled = False
        self.report: dict[str, Any] = {
            "schema": "redmmo.trooper_starsparrow.a01.pie_automation.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "phase": self.phase,
            "evidence_class": "automation",
            "renderer_gate": "real D3D12 RenderOffscreen PIE; NullRHI forbidden",
            "claim_limit": (
                "Automated one-player PIE with direct Enhanced Input action injection and runtime telemetry only. "
                "Physical F/WASD/mouse device feel, art/visual acceptance, packaged standalone, replication, multiplayer, "
                "travel, and human hands-on acceptance remain separate gates."
            ),
            "persistent_writes": {"map_saved": False, "content_saved": False, "config_saved": False},
            "tests": {},
        }

    def publish_state(self) -> None:
        self.report["phase"] = self.phase
        self.report["phase_elapsed_seconds"] = time.monotonic() - self.phase_started
        self.report["phase_frames"] = self.phase_frames
        if (
            self.world is not None
            and self.controller is not None
            and self.level.is_in_play_in_editor()
        ):
            pawn = unreal.GameplayStatics.get_player_pawn(self.world, 0)
            self.report["live"] = {
                "controller_pawn": class_path(pawn),
                "location": vec(pawn.get_actor_location()) if pawn is not None else None,
                "pie_world_active": True,
            }
        elif "live" in self.report:
            self.report["live"]["pie_world_active"] = False
        atomic_replace_json(self.state_path, self.report)

    def set_phase(self, phase: str, reset_motion: bool = True) -> None:
        self.phase = phase
        self.phase_started = time.monotonic()
        self.phase_frames = 0
        self.phase_max_speed = 0.0
        if reset_motion:
            pawn = unreal.GameplayStatics.get_player_pawn(self.world, 0) if self.world is not None else None
            self.phase_start_location = pawn.get_actor_location() if pawn is not None else None
            self.phase_start_forward = pawn.get_actor_forward_vector() if pawn is not None else None
            self.phase_start_right = pawn.get_actor_right_vector() if pawn is not None else None
            self.phase_start_up = pawn.get_actor_up_vector() if pawn is not None else None
        unreal.log("REDMMO_A01_PIE_PHASE " + phase)
        self.publish_state()

    def start(self) -> None:
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.publish_state()
        unreal.log("REDMMO_A01_PIE_VALIDATION_BOOTSTRAPPED")

    def authenticate_inputs(self) -> None:
        actual_project = Path(
            unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
        ).resolve(strict=True)
        require(actual_project == PROJECT_FILE.resolve(strict=True), f"Wrong active project: {actual_project}")
        require(PROJECT_FILE.is_file() and sha256(PROJECT_FILE) == PROJECT_SHA256, "Project descriptor drift")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == HOME_SHA256, "Bound home-map hash drift")
        profile_bind_raw = os.environ.get(PROFILE_BIND_REPORT_ENV, "")
        if profile_bind_raw:
            profile_bind_path = Path(profile_bind_raw).resolve(strict=True)
            profile_bind_sha256 = os.environ.get(PROFILE_BIND_REPORT_SHA256_ENV, "").upper()
            require(
                re.fullmatch(r"[0-9A-F]{64}", profile_bind_sha256) is not None,
                f"{PROFILE_BIND_REPORT_SHA256_ENV} is required with a ProfileV1 bind report",
            )
            bind = load_json(profile_bind_path, profile_bind_sha256, "ProfileV1 bind report")
            require(bind.get("schema") == "redmmo.ppg_profile_v1.home_binding.apply.v1", "ProfileV1 bind report schema drift")
            require(
                bind.get("status") == "PASS_PROFILE_V1_BOUND_TO_HOME_PENDING_FRESH_RELOAD_MAPCHECK_RUNTIME_VISUAL",
                "ProfileV1 bind report did not pass",
            )
            successor_record = None
            successor_raw = os.environ.get(HOME_SUCCESSOR_REPORT_ENV, "")
            if successor_raw:
                successor_path = Path(successor_raw).resolve(strict=True)
                successor_sha256 = os.environ.get(HOME_SUCCESSOR_REPORT_SHA256_ENV, "").upper()
                require(
                    re.fullmatch(r"[0-9A-F]{64}", successor_sha256) is not None,
                    f"{HOME_SUCCESSOR_REPORT_SHA256_ENV} is required with a home successor report",
                )
                successor = load_json(successor_path, successor_sha256, "home successor report")
                require(
                    successor.get("schema") == "redmmo.ppg_profile_v1.playerstart_surface_fix.v1",
                    "Home successor report schema drift",
                )
                require(
                    successor.get("status") == "PASS_PLAYERSTART_ON_PROFILE_V1_SURFACE_PENDING_FRESH_PIE",
                    "Home successor report did not pass",
                )
                require(
                    successor.get("home_map_sha256_before") == bind.get("home_map_sha256_after"),
                    "Home successor report does not chain from ProfileV1 bind",
                )
                require(
                    successor.get("home_map_sha256_after") == HOME_SHA256,
                    "Home successor report home hash drift",
                )
                successor_record = {"path": str(successor_path), "sha256": successor_sha256}
            else:
                require(bind.get("home_map_sha256_after") == HOME_SHA256, "ProfileV1 bind report home hash drift")
            require(bind.get("actor_count_before_after") == EXPECTED_EDITOR_ACTOR_COUNT, "ProfileV1 bind report actor count drift")
            require(bool(bind.get("a01_game_mode_preserved")), "ProfileV1 bind report did not preserve A01 GameMode")
            require(bind.get("target_planet_data") == PPG_PLANET, "ProfileV1 bind report PPG binding drift")
            bind_report_record = {"path": str(profile_bind_path), "sha256": profile_bind_sha256}
        else:
            bind = load_json(BIND_REPORT, BIND_REPORT_SHA256, "A01 bind report")
            require(bind.get("schema") == "redmmo.home_gameplay_bind.a01.transaction.v1", "Bind report schema drift")
            require(bind.get("status") == "PASS_MAP_BOUND_PENDING_FRESH_RELOAD_MAPCHECK_PIE", "Bind report did not pass")
            require(bind.get("home_map_sha256_after") == BIND_HOME_SHA256, "Bind report home hash drift")
            require(bind.get("actor_count_after") == EXPECTED_EDITOR_ACTOR_COUNT, "Bind report actor count drift")
            require(bind.get("world_settings", {}).get("default_game_mode_after") == GAME_MODE_CLASS, "Bind report GameMode drift")
            require(bind.get("ppg_after", {}).get("planet_data") == BIND_PPG_PLANET, "Bind report PPG binding drift")
            require(bind.get("removed_actor", {}).get("label") == OLD_VISUAL_LABEL, "Bind report did not remove exact old visual ship")
            bind_report_record = {"path": str(BIND_REPORT), "sha256": BIND_REPORT_SHA256}
            successor_record = None

        build = load_json(BUILD_REPORT, BUILD_REPORT_SHA256, "A01 asset build report")
        fresh = load_json(FRESH_REPORT, FRESH_REPORT_SHA256, "A01 fresh asset report")
        require(build.get("status") == "pass_created_compiled_saved_same_process_readback", "A01 asset build did not pass")
        require(fresh.get("status") == "pass_fresh_process_serialized_readback", "A01 fresh asset readback did not pass")
        require(fresh.get("build_report", {}).get("sha256") == BUILD_REPORT_SHA256, "Fresh report build provenance drift")
        entries = fresh.get("files")
        require(isinstance(entries, list) and len(entries) == 18, "Fresh A01 package record count drift")
        self.tracked_hashes = {
            package_file(str(item["package"])): str(item["sha256"]).upper()
            for item in entries if isinstance(item, dict)
        }
        require(len(self.tracked_hashes) == 18, "Fresh A01 package set is malformed")
        for package, digest in TRACKED_PACKAGE_HASH_OVERRIDES.items():
            package_path = package_file(package)
            require(package_path in self.tracked_hashes, f"Tracked-package override is outside A01: {package}")
            require(re.fullmatch(r"[0-9A-F]{64}", digest) is not None, f"Malformed tracked-package override: {package}")
            self.tracked_hashes[package_path] = digest
        self.tracked_hashes.update({
            HOME_FILE: HOME_SHA256,
            SOURCE_SHIP_FILE: SOURCE_SHIP_SHA256,
            PPG_PLANET_FILE: PPG_PLANET_SHA256,
            **APPROVED_GRASS_FILES,
            **PROTECTED_FILES,
        })
        self.tracked_before = verify_hashes(self.tracked_hashes, "Tracked gameplay/home/grass/protected file")
        self.config_before = hash_tree(PROJECT_ROOT / "Config")
        self.report["authenticated_inputs"] = {
            "active_project": str(actual_project),
            "bind_report": bind_report_record,
            "home_successor_report": successor_record,
            "build_report": {"path": str(BUILD_REPORT), "sha256": BUILD_REPORT_SHA256},
            "fresh_report": {"path": str(FRESH_REPORT), "sha256": FRESH_REPORT_SHA256},
            "home_map_sha256": HOME_SHA256,
            "tracked_file_count": len(self.tracked_hashes),
            "approved_grass": list(APPROVED_GRASS),
            "approved_grass_source": "/Game/StylizedRocksPack_01/Common/GrassChunks/Meshes/SM_GrassChunk_01",
            "tracked_package_hash_overrides": dict(TRACKED_PACKAGE_HASH_OVERRIDES),
        }

    def verify_renderer(self) -> None:
        command = str(unreal.SystemLibrary.get_command_line())
        lowered = command.lower()
        require("-nullrhi" not in lowered, "NullRHI is forbidden for this PIE verifier")
        require("-d3d12" in lowered, "Fresh verifier was not launched with -d3d12")
        require("-renderoffscreen" in lowered, "Fresh verifier was not launched with -RenderOffscreen")
        self.report["command_line_gate"] = {
            "d3d12": True,
            "render_offscreen": True,
            "nullrhi": False,
            "command_line": command,
        }

    def verify_editor_contract(self, world: Any) -> None:
        require(current_map(world) == HOME_MAP, f"Wrong editor map: {current_map(world)}")
        world_settings = world.get_world_settings()
        require(world_settings is not None, "Editor WorldSettings unavailable")
        game_mode = world_settings.get_editor_property("default_game_mode")
        require(game_mode is not None and game_mode.get_path_name() == GAME_MODE_CLASS, f"Editor GameMode drift: {game_mode}")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        require(len(actors) == EXPECTED_EDITOR_ACTOR_COUNT, f"Editor actor count drift: {len(actors)}")
        require(not any(actor.get_actor_label() == OLD_VISUAL_LABEL for actor in actors), "Old visual-only ship remains in editor map")
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, f"Expected one editor PlanetSpawnerBP_C, found {len(spawners)}")
        spawner = spawners[0]
        require(asset_path(spawner.get_editor_property("planet_data")) == PPG_PLANET, "Editor PPG PlanetData drift")
        require(bool(spawner.get_editor_property("generate_collisions")), "Editor PPG collision generation disabled")
        planet = load_asset_exact(PPG_PLANET)
        require(bool(planet.get_editor_property("generate_water")), "Editor PPG seeded water generation disabled")

        require(int(planet.get_editor_property("generation_seed")) == 1337, "PPG home seed drift")
        require(abs(float(planet.get_editor_property("planet_radius")) - 300_000_000.0) <= 0.01, "PPG home radius drift")
        biome_foliage = []
        for biome in list(planet.get_editor_property("biome_data")):
            for key, value in biome.to_dict().items():
                if str(key).replace("_", "").lower() in ("foliagedata", "forestfoliagedata"):
                    biome_foliage.append(asset_path(value))
        require(biome_foliage.count(PPG_FOLIAGE) == 3, "R10O foliage binding is not present in all three seeded biomes")
        foliage = load_asset_exact(PPG_FOLIAGE)
        entries = list(foliage.get_editor_property("foliage_list"))
        require(len(entries) == 3, "R10O foliage list cardinality drift")
        grass_bindings = [asset_path(item.get_editor_property("mesh")) for item in entries[1].get_editor_property("meshes")]
        require(grass_bindings == list(APPROVED_GRASS), f"Approved grass binding drift: {grass_bindings}")
        self.report["editor_contract"] = {
            "map": HOME_MAP,
            "game_mode": GAME_MODE_CLASS,
            "actor_count": len(actors),
            "ppg_spawner": spawner.get_path_name(),
            "planet_data": PPG_PLANET,
            "generation_seed": 1337,
            "planet_radius_cm": 300_000_000.0,
            "approved_grass_bindings": grass_bindings,
            "old_visual_ship_absent": True,
        }

    def prepare(self) -> None:
        self.authenticate_inputs()
        self.verify_renderer()
        require(no_dirty(), f"Editor started dirty: {dirty_packages()}")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        self.report["provider_ports_closed_before"] = provider_gate()
        world = unreal.EditorLevelLibrary.get_editor_world()
        if world is None or current_map(world) != HOME_MAP:
            world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None and no_dirty(), f"Fresh home-map load failed or dirtied packages: {dirty_packages()}")
        self.verify_editor_contract(world)
        self.report["map_check"] = map_check(world)
        require(no_dirty(), f"MapCheck dirtied packages: {dirty_packages()}")
        self.contexts = {
            "on_foot": load_asset_exact(ON_FOOT_CONTEXT),
            "ship": load_asset_exact(SHIP_CONTEXT),
        }
        self.actions = {name: load_asset_exact(path) for name, path in ACTIONS.items()}
        self.report["preloaded_input_assets"] = {
            "contexts": {name: asset_path(asset) for name, asset in self.contexts.items()},
            "actions": {name: asset_path(asset) for name, asset in self.actions.items()},
        }
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE_WORLD", reset_motion=False)

    def inspect_trooper(self) -> dict[str, Any]:
        require(class_path(self.trooper) == PLAYER_CLASS, f"Wrong PIE pawn class: {class_path(self.trooper)}")
        require(role_is_authority(self.trooper), "PIE Trooper is not authoritative")
        body_matches = [
            component for component in self.trooper.get_components_by_class(unreal.SkeletalMeshComponent)
            if asset_path(component.get_skeletal_mesh_asset()) == BODY_MESH
        ]
        require(len(body_matches) == 1, f"Expected one visible Trooper body component, found {len(body_matches)}")
        weapon_matches = [
            component for component in self.trooper.get_components_by_class(unreal.SkeletalMeshComponent)
            if asset_path(component.get_skeletal_mesh_asset()) == RIFLE_MESH
        ]
        require(len(weapon_matches) == 1, f"Expected one Trooper rifle component, found {len(weapon_matches)}")
        self.body = body_matches[0]
        self.weapon = weapon_matches[0]
        for label, component in (("body", self.body), ("rifle", self.weapon)):
            require(bool(component.get_editor_property("visible")), f"Trooper {label} component is not visible")
            require(not bool(component.get_editor_property("hidden_in_game")), f"Trooper {label} component is hidden in game")
        parent = self.weapon.get_attach_parent()
        require(parent == self.body, "Rifle is not attached to the Trooper body component")
        require(str(self.weapon.get_attach_socket_name()).lower() == "hand_rsocket", "Rifle attachment socket drift")
        require(self.weapon.does_socket_exist(unreal.Name("Muzzle")), "Rifle Muzzle socket missing at runtime")
        require(not self.weapon.is_query_collision_enabled(), "Rifle collision is unexpectedly enabled")

        reflected_actions = {
            name: asset_path(self.trooper.get_editor_property(name + "_action"))
            for name in ("move", "look", "jump", "sprint", "fire", "ads", "interact")
        }
        require(reflected_actions == {name: ACTIONS[name] for name in reflected_actions}, f"Trooper action binding drift: {reflected_actions}")
        require(asset_path(self.trooper.get_editor_property("default_mapping_context")) == ON_FOOT_CONTEXT, "Trooper mapping context drift")
        require(asset_path(self.trooper.get_editor_property("ship_mapping_context")) == SHIP_CONTEXT, "Trooper ship-context reference drift")
        runtime_animations = {name: asset_path(self.trooper.get_editor_property(name)) for name in ANIMATIONS}
        require(runtime_animations == ANIMATIONS, f"Trooper animation-slot drift: {runtime_animations}")
        bolt_class = self.trooper.get_editor_property("bolt_class")
        require(bolt_class is not None and bolt_class.get_path_name() == BOLT_CLASS, "Trooper bolt class drift")
        return {
            "actor": self.trooper.get_path_name(),
            "class": PLAYER_CLASS,
            "authority": True,
            "body_component": self.body.get_path_name(),
            "body_mesh": BODY_MESH,
            "rifle_component": self.weapon.get_path_name(),
            "rifle_mesh": RIFLE_MESH,
            "rifle_parent": self.body.get_path_name(),
            "rifle_attachment_socket": str(self.weapon.get_attach_socket_name()),
            "rifle_muzzle_socket": "Muzzle",
            "actions": reflected_actions,
            "animations": runtime_animations,
            "current_animation_state": enum_text(self.trooper.get_editor_property("current_animation_state")),
        }

    def bind_pie(self) -> bool:
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        controller = unreal.GameplayStatics.get_player_controller(world, 0)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if controller is None or pawn is None:
            return False
        spawners = [actor for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor) if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, f"Expected one PIE PPG spawner, found {len(spawners)}")
        game_mode = unreal.GameplayStatics.get_game_mode(world)
        require(game_mode is not None and class_path(game_mode) == GAME_MODE_CLASS, f"PIE GameMode drift: {class_path(game_mode)}")
        require(role_is_authority(game_mode), "PIE GameMode is not authoritative")
        self.world = world
        self.controller = controller
        self.trooper = pawn
        self.spawner = spawners[0]
        self.center = self.spawner.get_actor_location()
        self.initial_center = self.center
        planet = self.spawner.get_editor_property("planet_data")
        require(asset_path(planet) == PPG_PLANET, "PIE PPG PlanetData drift")
        self.nominal_radius = float(planet.get_editor_property("planet_radius"))
        self.movement = self.trooper.get_editor_property("character_movement")
        require(self.movement is not None, "Trooper CharacterMovement unavailable")
        self.input_subsystem = input_subsystem_for_world(world)
        runtime_contexts = {
            "on_foot": self.trooper.get_editor_property("default_mapping_context"),
            "ship": self.trooper.get_editor_property("ship_mapping_context"),
        }
        require(
            {name: asset_path(asset) for name, asset in runtime_contexts.items()}
            == {"on_foot": ON_FOOT_CONTEXT, "ship": SHIP_CONTEXT},
            "PIE pawn input-context asset drift",
        )
        self.contexts = runtime_contexts
        contexts = input_context_state(self.trooper)
        input_component_type = getattr(unreal, "InputComponent", None)
        input_components = list(self.trooper.get_components_by_class(input_component_type)) if input_component_type else []
        self.report["input_diagnostics"] = {
            "controller_local": bool(self.controller.is_local_controller()),
            "pawn_locally_controlled": bool(self.trooper.is_locally_controlled()),
            "input_component_classes": [class_path(component) for component in input_components],
            "input_subsystem": self.input_subsystem.get_path_name(),
            "runtime_context_assets": {name: asset_path(asset) for name, asset in self.contexts.items()},
            "context_state": contexts,
        }
        if contexts != {"on_foot": True, "ship": False}:
            self.report["input_contexts_pending"] = contexts
            return False
        self.report.pop("input_contexts_pending", None)
        self.report["pie_contract"] = {
            "world": world.get_path_name(),
            "game_mode": GAME_MODE_CLASS,
            "controller": controller.get_path_name(),
            "ppg_spawner": self.spawner.get_path_name(),
            "planet_center": vec(self.center),
            "nominal_radius_cm": self.nominal_radius,
            "input_driver": "EnhancedInputLocalPlayerSubsystem.inject_input_vector_for_action",
            "physical_key_provenance": "Exact serialized mappings were authenticated by the A01 fresh report; this automation injects their InputActions rather than OS key events.",
            "input_contexts_initial": contexts,
            "trooper": self.inspect_trooper(),
        }
        self.set_phase("WAIT_GENERATION", reset_motion=False)
        return True

    def generation_ready(self) -> bool:
        method = getattr(self.spawner, "get_planet_generation_status", None)
        require(callable(method), "PPG generation-status API unavailable")
        status = method()
        record = {
            "phase": str(status.get_editor_property("phase")),
            "progress": float(status.get_editor_property("progress")),
            "is_generating": bool(status.get_editor_property("is_generating")),
            "collisions_enabled": bool(self.spawner.get_editor_property("generate_collisions")),
        }
        self.report["generation"] = record
        return "COMPLETE" in record["phase"].upper() and record["progress"] >= 0.999 and not record["is_generating"] and record["collisions_enabled"]

    def find_ship(self) -> Any | None:
        ships = [actor for actor in unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor) if class_path(actor) == SHIP_CLASS]
        require(len(ships) <= 1, f"Multiple A01 starter ships spawned: {len(ships)}")
        return ships[0] if ships else None

    def inject(self, action_name: str, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.input_subsystem.inject_input_vector_for_action(self.actions[action_name], unreal.Vector(x, y, z), [], [])

    def radial_up(self, location: Any | None = None) -> Any:
        if self.spawner is not None:
            self.center = self.spawner.get_actor_location()
        if location is None:
            pawn = unreal.GameplayStatics.get_player_pawn(self.world, 0)
            location = pawn.get_actor_location()
        return normalized(sub(location, self.center))

    def tangent_motion(self, actor: Any, start: Any) -> dict[str, Any]:
        location = actor.get_actor_location()
        up = self.radial_up(location)
        displacement = sub(location, start)
        tangent = plane_project(displacement, up)
        velocity = actor.get_velocity()
        tangent_speed = length(plane_project(velocity, up))
        self.phase_max_speed = max(self.phase_max_speed, tangent_speed)
        return {
            "start": vec(start),
            "end": vec(location),
            "tangent_displacement_cm": length(tangent),
            "radial_delta_cm": length(sub(location, self.center)) - length(sub(start, self.center)),
            "tangent_speed_cm_s": tangent_speed,
            "max_tangent_speed_cm_s": self.phase_max_speed,
            "actor_up_dot_radial_up": dot(normalized(actor.get_actor_up_vector()), up),
        }

    def face_tangent_toward(self, target: Any) -> dict[str, Any]:
        location = self.trooper.get_actor_location()
        up = self.radial_up(location)
        forward = plane_project(sub(target, location), up)
        require(length(forward) > 1.0, "Target has no tangent direction from Trooper")
        forward = normalized(forward)
        rotation = unreal.MathLibrary.make_rot_from_xz(forward, up)
        self.controller.set_control_rotation(rotation)
        return {"forward": vec(forward), "up": vec(up), "rotation": str(rotation)}

    def inspect_ship_parking(self) -> dict[str, Any]:
        require(class_path(self.ship) == SHIP_CLASS, f"Starter ship class drift: {class_path(self.ship)}")
        require(role_is_authority(self.ship), "Starter ship is not authoritative")
        require(self.ship.get_pilot() is None, "Starter ship already has a pilot")
        reflected_actions = {
            "ship_move": asset_path(self.ship.get_editor_property("move_action")),
            "ship_look": asset_path(self.ship.get_editor_property("look_action")),
            "ship_roll": asset_path(self.ship.get_editor_property("roll_action")),
            "ship_boost": asset_path(self.ship.get_editor_property("boost_action")),
            "ship_exit": asset_path(self.ship.get_editor_property("exit_action")),
        }
        require(reflected_actions == {name: ACTIONS[name] for name in reflected_actions}, f"Ship action binding drift: {reflected_actions}")
        require(asset_path(self.ship.get_editor_property("ship_mapping_context")) == SHIP_CONTEXT, "Ship mapping context drift")
        require(asset_path(self.ship.get_editor_property("on_foot_mapping_context")) == ON_FOOT_CONTEXT, "Ship on-foot context reference drift")

        fitted = component_named(self.ship, unreal.BoxComponent, "RuntimeHullCollision")
        extent = fitted.get_scaled_box_extent()
        require(min(float(extent.x), float(extent.y), float(extent.z)) >= 80.0, f"Fitted ship envelope is degenerate: {extent}")
        require(not fitted.is_query_collision_enabled(), "Fitted query envelope became a broad gameplay blocker")
        visible_meshes = []
        query_collision_meshes = []
        for component in self.ship.get_components_by_class(unreal.StaticMeshComponent):
            mesh = component.get_editor_property("static_mesh")
            if mesh is None or not bool(component.get_editor_property("visible")) or bool(component.get_editor_property("hidden_in_game")) or "plume" in component.get_name().lower():
                continue
            visible_meshes.append({"component": component.get_path_name(), "mesh": asset_path(mesh)})
            if component.is_query_collision_enabled():
                query_collision_meshes.append(component.get_path_name())
        require(visible_meshes, "Starter ship has no visible modular meshes")
        require(query_collision_meshes, "Starter ship has no query-collision visible mesh")

        has_validated_placement = getattr(self.ship, "has_validated_owned_surface_placement", None)
        get_validated_gap = getattr(self.ship, "get_validated_owned_surface_gap_cm", None)
        require(callable(has_validated_placement), "Starter ship lacks authoritative owned-surface placement telemetry")
        require(callable(get_validated_gap), "Starter ship lacks authoritative owned-surface gap telemetry")
        require(bool(has_validated_placement()), "Starter ship did not complete fitted-envelope placement on owned PPG terrain")
        gap = float(get_validated_gap())
        require(math.isfinite(gap) and 0.0 <= gap <= 100.0, f"Starter ship validated owned-surface gap is invalid: gap={gap}")
        return {
            "actor": self.ship.get_path_name(),
            "class": SHIP_CLASS,
            "authority": True,
            "actions": reflected_actions,
            "fitted_envelope_component": fitted.get_path_name(),
            "fitted_envelope_extent_cm": vec(extent),
            "fitted_envelope_no_collision": True,
            "visible_modular_meshes": visible_meshes,
            "query_collision_visible_meshes": query_collision_meshes,
            "owned_ppg_surface": {
                "validation_source": "ARedShip::PlaceOnOwnedSurface fitted-envelope SweepOwnedTerrain",
                "unique_ready_home_body_required": True,
                "foreign_blocker_check_required": True,
            },
            "fitted_envelope_owned_surface_gap_cm": gap,
        }

    def animation_state(self) -> str:
        return enum_text(self.trooper.get_editor_property("current_animation_state"))

    def ground_phase_complete(self, label: str, motion: dict[str, Any], required_state: str) -> None:
        require(motion["tangent_displacement_cm"] >= MIN_GROUND_DISPLACEMENT_CM, f"{label} displacement too small")
        require(motion["actor_up_dot_radial_up"] >= 0.97, f"{label} lost radial orientation")
        require(abs(motion["radial_delta_cm"]) <= motion["tangent_displacement_cm"] * 0.75 + 500.0, f"{label} radial drift is implausible")
        state = self.animation_state()
        require(required_state in state, f"{label} animation state mismatch: {state}")
        motion["animation_state"] = state
        self.report["tests"][label] = motion

    def bolt_actors(self) -> list[Any]:
        return [actor for actor in unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor) if class_path(actor) == BOLT_CLASS]

    def begin_ship_motion_phase(self, phase: str) -> None:
        self.set_phase(phase)

    def ship_motion(self) -> dict[str, Any]:
        self.center = self.spawner.get_actor_location()
        location = self.ship.get_actor_location()
        displacement = sub(location, self.phase_start_location)
        speed = length(self.ship.get_velocity())
        self.phase_max_speed = max(self.phase_max_speed, speed)
        return {
            "start": vec(self.phase_start_location),
            "end": vec(location),
            "displacement_cm": length(displacement),
            "radial_delta_cm": length(sub(location, self.center)) - length(sub(self.phase_start_location, self.center)),
            "max_speed_cm_s": self.phase_max_speed,
        }

    def verify_safe_exit(self) -> dict[str, Any]:
        self.center = self.spawner.get_actor_location()
        capsule = self.trooper.get_editor_property("capsule_component")
        require(capsule is not None, "Trooper capsule unavailable after ship exit")
        fitted = component_named(self.ship, unreal.BoxComponent, "RuntimeHullCollision")
        location = self.trooper.get_actor_location()
        up = self.radial_up(location)
        capsule_radius = float(capsule.get_scaled_capsule_radius())
        capsule_half_height = float(capsule.get_scaled_capsule_half_height())
        segment_half = max(0.0, capsule_half_height - capsule_radius)
        margin = float(self.ship.get_editor_property("pilot_exit_envelope_margin_cm"))
        extent = fitted.get_scaled_box_extent()
        extents = [float(extent.x), float(extent.y), float(extent.z)]
        axes = [normalized(fitted.get_forward_vector()), normalized(fitted.get_right_vector()), normalized(fitted.get_up_vector())]
        delta = sub(location, fitted.get_world_location())
        axis_records = []
        separated = False
        for axis, box_extent in zip(axes, extents):
            capsule_support = capsule_radius + segment_half * abs(dot(up, axis))
            projected = abs(dot(delta, axis))
            threshold = box_extent + capsule_support + margin
            axis_records.append({"projected_center_distance_cm": projected, "required_separation_cm": threshold, "separated": projected > threshold})
            separated = separated or projected > threshold
        require(separated, "Exited Trooper capsule is not separated from fitted ship envelope")
        has_validated_exit = getattr(self.ship, "has_validated_pilot_exit", None)
        get_validated_exit_gap = getattr(self.ship, "get_validated_pilot_exit_surface_gap_cm", None)
        require(callable(has_validated_exit), "Ship lacks authoritative pilot-exit validation telemetry")
        require(callable(get_validated_exit_gap), "Ship lacks authoritative pilot-exit gap telemetry")
        require(bool(has_validated_exit()), "Ship did not complete its authoritative pilot-exit transaction")
        surface_gap = float(get_validated_exit_gap())
        require(-25.0 <= surface_gap <= 150.0, f"Exited Trooper is not grounded near owned PPG terrain: gap={surface_gap}")
        return {
            "trooper_location": vec(location),
            "ship_location": vec(self.ship.get_actor_location()),
            "capsule_radius_cm": capsule_radius,
            "capsule_half_height_cm": capsule_half_height,
            "fitted_envelope_margin_cm": margin,
            "separating_axis_records": axis_records,
            "separated_from_fitted_envelope": True,
            "owned_ppg_surface": {
                "validation_source": "ARedShip::FindSafePilotExit LineTraceOwnedTerrain",
                "unique_ready_home_body_required": True,
                "foreign_blocker_check_required": True,
            },
            "capsule_bottom_surface_gap_cm": surface_gap,
        }

    def request_stop(self) -> None:
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == HOME_SHA256, "PIE changed the bound home map")
        require(no_dirty(), f"PIE dirtied packages before teardown: {dirty_packages()}")
        require(
            verify_hashes(self.tracked_hashes, "Runtime-complete tracked file") == self.tracked_before,
            "Tracked files changed during PIE",
        )
        require(hash_tree(PROJECT_ROOT / "Config") == self.config_before, "Project Config tree changed during PIE")
        self.report.update({
            "status": "PASS_RUNTIME_TESTS_COMPLETE_PENDING_PIE_TEARDOWN",
            "runtime_completed_utc": now(),
            "runtime_dirty_packages": dirty_packages(),
            "runtime_tracked_hashes_unchanged": True,
            "runtime_config_tree_unchanged": True,
            "runtime_provider_ports_closed": provider_gate(),
            "pie_stop_requested": True,
            "pie_stopped": False,
        })
        if self.result_path.exists():
            atomic_replace_json(self.result_path, self.report)
        else:
            atomic_no_clobber_json(self.result_path, self.report)
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        self.set_phase("WAIT_PIE_STOP", reset_motion=False)

    def schedule_quit(self, delay: float = 4.0) -> None:
        if self.quit_scheduled:
            return
        self.quit_scheduled = True
        started = time.monotonic()

        def quit_tick(_delta: float) -> None:
            if time.monotonic() - started < delay:
                return
            try:
                unreal.unregister_slate_post_tick_callback(handle)
            except Exception:
                pass
            unreal.SystemLibrary.quit_editor()

        handle = unreal.register_slate_post_tick_callback(quit_tick)

    def finalize_pass(self) -> None:
        require(not self.level.is_in_play_in_editor(), "PIE did not stop cleanly")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == HOME_SHA256, "PIE changed the bound home map")
        require(no_dirty(), f"PIE dirtied packages: {dirty_packages()}")
        require(verify_hashes(self.tracked_hashes, "Post-PIE tracked file") == self.tracked_before, "Tracked files changed during PIE")
        require(hash_tree(PROJECT_ROOT / "Config") == self.config_before, "Project Config tree changed during PIE")
        self.report["provider_ports_closed_after"] = provider_gate()
        if self.screenshot_path is not None:
            require(
                self.screenshot_requested and self.screenshot_path.is_file() and self.screenshot_path.stat().st_size > 0,
                f"Requested player-scale screenshot was not produced: {self.screenshot_path}",
            )
            self.report["player_scale_screenshot"] = {
                "path": str(self.screenshot_path),
                "bytes": self.screenshot_path.stat().st_size,
                "sha256": sha256(self.screenshot_path),
                "capture_phase": "grounded_before_walk",
            }
        self.report.update({
            "status": "PASS_AUTOMATED_REAL_D3D12_PIE_A01_TROOPER_STARSPARROW",
            "completed_utc": now(),
            "dirty_packages_after": dirty_packages(),
            "tracked_hashes_unchanged": self.tracked_before,
            "config_tree_unchanged": True,
            "hands_on_gate": "Pending a separate visible user-controlled PIE launch after this automation result is reviewed.",
            "pie_stopped": True,
            "editor_exit_scheduled": True,
        })
        self.publish_state()
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.log("REDMMO_A01_PIE_VALIDATION_PASS")
        self.schedule_quit(8.0)
        if self.result_path.exists():
            atomic_replace_json(self.result_path, self.report)
        else:
            atomic_no_clobber_json(self.result_path, self.report)

    def begin_failure(self, error: Exception) -> None:
        if self.abort_error is not None:
            return
        self.abort_error = error
        self.report.update({"status": "FAIL", "error": str(error), "traceback": traceback.format_exc(), "failed_phase": self.phase})
        unreal.log_error("REDMMO_A01_PIE_VALIDATION_FAIL " + str(error))
        self.report["failure_recorded_utc"] = now()
        self.report["pie_stop_requested"] = bool(self.level.is_in_play_in_editor())
        self.report["pie_stopped"] = not self.level.is_in_play_in_editor()
        if not self.result_path.exists():
            atomic_no_clobber_json(self.result_path, self.report)
        else:
            atomic_replace_json(self.result_path, self.report)
        try:
            if self.level.is_in_play_in_editor():
                self.level.editor_request_end_play()
        except Exception:
            pass
        self.set_phase("ABORT_WAIT_PIE_STOP", reset_motion=False)

    def finalize_failure(self) -> None:
        self.report["completed_utc"] = now()
        pie_stopped = not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None
        self.report["pie_stopped"] = pie_stopped
        self.report["pie_teardown_timeout"] = not pie_stopped
        try:
            self.report["dirty_packages_at_failure"] = dirty_packages()
        except Exception as dirty_error:
            self.report["dirty_package_query_failure"] = str(dirty_error)
        try:
            self.report["provider_ports_closed_at_failure"] = provider_gate()
        except Exception as gate_error:
            self.report["provider_gate_failure"] = str(gate_error)
        self.report["home_map_sha256_at_failure"] = sha256(HOME_FILE) if HOME_FILE.is_file() else None
        try:
            current = verify_hashes(self.tracked_hashes, "Failure-boundary tracked file")
            self.report["tracked_hashes_unchanged_at_failure"] = current == self.tracked_before
            self.report["tracked_hashes_at_failure"] = current
        except Exception as hash_error:
            self.report["tracked_hash_revalidation_failure"] = str(hash_error)
        try:
            self.report["config_tree_unchanged_at_failure"] = hash_tree(PROJECT_ROOT / "Config") == self.config_before
        except Exception as config_error:
            self.report["config_revalidation_failure"] = str(config_error)
        self.report["editor_exit_scheduled"] = True
        self.schedule_quit(4.0)
        if self.result_path.exists():
            atomic_replace_json(self.result_path, self.report)
        else:
            atomic_no_clobber_json(self.result_path, self.report)
        self.publish_state()
        if self.handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(self.handle)
            except Exception:
                pass
            self.handle = None

    def tick(self, _delta_seconds: float) -> None:
        try:
            self.phase_frames += 1
            elapsed = time.monotonic() - self.phase_started
            if self.phase == "PREPARE":
                self.prepare()
            elif self.phase == "WAIT_PIE_WORLD":
                require(elapsed <= 15.0, "PIE input-context startup timeout")
                self.bind_pie()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 240.0, "PPG generation timeout")
                if self.generation_ready():
                    self.ship = self.find_ship()
                    if self.ship is not None:
                        self.report["tests"]["starter_ship_parking"] = self.inspect_ship_parking()
                        self.set_phase("WAIT_GROUNDED")
            elif self.phase == "WAIT_GROUNDED":
                require(elapsed <= 90.0, "Trooper did not settle on generated PPG terrain")
                self.ship = self.find_ship()
                require(self.ship is not None, "Starter ship disappeared after generation")
                if not self.movement.is_falling():
                    self.grounded_frames += 1
                else:
                    self.grounded_frames = 0
                if self.grounded_frames >= 20:
                    self.report["runtime_foliage"] = runtime_foliage_state(
                        self.world, self.trooper.get_actor_location()
                    )
                    up = self.radial_up(self.trooper.get_actor_location())
                    forward = plane_project(self.trooper.get_actor_forward_vector(), up)
                    forward_length = length(forward)
                    require(
                        forward_length >= 0.90,
                        f"Trooper forward vector is not surface-tangent: projected length={forward_length}",
                    )
                    rotation = unreal.MathLibrary.make_rot_from_xz(normalized(forward), up)
                    self.controller.set_control_rotation(rotation)
                    if self.screenshot_path is not None and self.foliage_settle_seconds > 0.0:
                        self.set_phase("WAIT_FOLIAGE_SETTLE", reset_motion=False)
                    else:
                        if self.screenshot_path is not None and not self.screenshot_requested:
                            task = unreal.AutomationLibrary.take_high_res_screenshot(
                                1280, 720, str(self.screenshot_path)
                            )
                            require(task is not None, "High-resolution screenshot task was not created")
                            self.screenshot_requested = True
                        self.set_phase("WALK")
            elif self.phase == "WAIT_FOLIAGE_SETTLE":
                require(elapsed <= self.foliage_settle_seconds + 30.0, "Foliage settle timeout")
                if elapsed >= self.foliage_settle_seconds:
                    self.report["runtime_foliage_after_settle"] = runtime_foliage_state(
                        self.world, self.trooper.get_actor_location()
                    )
                    if self.screenshot_path is not None and not self.screenshot_requested:
                        task = unreal.AutomationLibrary.take_high_res_screenshot(
                            1280, 720, str(self.screenshot_path)
                        )
                        require(task is not None, "High-resolution screenshot task was not created")
                        self.screenshot_requested = True
                    self.set_phase("WALK")
            elif self.phase == "WALK":
                require(elapsed <= 20.0, "Radial walk timeout")
                self.inject("move", y=1.0)
                motion = self.tangent_motion(self.trooper, self.phase_start_location)
                if motion["tangent_displacement_cm"] >= MIN_GROUND_DISPLACEMENT_CM:
                    self.ground_phase_complete("radial_walk", motion, "WALK")
                    self.set_phase("WALK_SETTLE")
            elif self.phase == "WALK_SETTLE":
                require(elapsed <= 8.0, "Walk settle timeout")
                self.inject("move")
                if length(plane_project(self.trooper.get_velocity(), self.radial_up())) <= 100.0 and elapsed >= 0.5:
                    self.set_phase("SPRINT")
            elif self.phase == "SPRINT":
                require(elapsed <= 20.0, "Radial sprint timeout")
                self.inject("sprint", x=1.0)
                self.inject("move", y=1.0)
                motion = self.tangent_motion(self.trooper, self.phase_start_location)
                if motion["tangent_displacement_cm"] >= 800.0 and motion["max_tangent_speed_cm_s"] >= 700.0:
                    self.ground_phase_complete("radial_sprint", motion, "RUN")
                    self.set_phase("SPRINT_SETTLE")
            elif self.phase == "SPRINT_SETTLE":
                require(elapsed <= 8.0, "Sprint settle timeout")
                self.inject("sprint")
                self.inject("move")
                if length(plane_project(self.trooper.get_velocity(), self.radial_up())) <= 100.0 and elapsed >= 0.5:
                    self.set_phase("JUMP_PULSE")
            elif self.phase == "JUMP_PULSE":
                if not self.jump_pulsed:
                    self.jump_pulsed = True
                    self.phase_start_location = self.trooper.get_actor_location()
                    self.inject("jump", x=1.0)
                    self.set_phase("WAIT_AIRBORNE", reset_motion=False)
            elif self.phase == "WAIT_AIRBORNE":
                require(elapsed <= 8.0, "Jump action did not enter falling state")
                velocity = self.trooper.get_velocity()
                radial_speed = dot(velocity, self.radial_up())
                if self.movement.is_falling() and radial_speed > 25.0:
                    state = self.animation_state()
                    require("JUMP_START" in state or "JUMP_LOOP" in state, f"Jump animation state mismatch: {state}")
                    self.report["tests"]["radial_jump_takeoff"] = {
                        "location": vec(self.trooper.get_actor_location()),
                        "radial_speed_cm_s": radial_speed,
                        "animation_state": state,
                    }
                    self.set_phase("WAIT_LAND", reset_motion=False)
            elif self.phase == "WAIT_LAND":
                require(elapsed <= 25.0, "Trooper did not land after radial jump")
                if not self.movement.is_falling():
                    location = self.trooper.get_actor_location()
                    up_dot = dot(normalized(self.trooper.get_actor_up_vector()), self.radial_up(location))
                    require(up_dot >= 0.97, "Trooper lost radial orientation on landing")
                    self.report["tests"]["radial_jump_land"] = {
                        "location": vec(location),
                        "actor_up_dot_radial_up": up_dot,
                        "animation_state": self.animation_state(),
                    }
                    self.set_phase("FIRE_PULSE")
            elif self.phase == "FIRE_PULSE":
                if not self.fire_pulsed:
                    self.fire_pulsed = True
                    up = self.radial_up(self.trooper.get_actor_location())
                    forward = normalized(plane_project(self.trooper.get_actor_forward_vector(), up))
                    rotation = unreal.MathLibrary.make_rot_from_xz(forward, up)
                    self.controller.set_control_rotation(rotation)
                    self.bolts_before = {actor.get_path_name() for actor in self.bolt_actors()}
                    self.muzzle_at_fire = self.weapon.get_socket_location(unreal.Name("Muzzle"))
                    self.inject("fire", x=1.0)
                    self.set_phase("WAIT_BOLT", reset_motion=False)
            elif self.phase == "WAIT_BOLT":
                require(elapsed <= 4.0, "Fire action did not create the A01 RedBolt")
                candidates = [actor for actor in self.bolt_actors() if actor.get_path_name() not in self.bolts_before]
                if candidates:
                    require(len(candidates) == 1, f"Fire created unexpected bolt count: {len(candidates)}")
                    bolt = candidates[0]
                    require(role_is_authority(bolt), "Spawned RedBolt is not authoritative")
                    require(actor_owner(bolt) == self.trooper, "Spawned RedBolt owner drift")
                    require(actor_instigator(bolt) == self.trooper, "Spawned RedBolt instigator drift")
                    muzzle_distance = distance(bolt.get_actor_location(), self.muzzle_at_fire)
                    require(muzzle_distance <= 1500.0, f"RedBolt did not originate near exact rifle Muzzle socket: {muzzle_distance}")
                    self.new_bolt = bolt
                    self.report["tests"]["server_authoritative_fire"] = {
                        "trooper_authority": True,
                        "bolt": bolt.get_path_name(),
                        "bolt_class": BOLT_CLASS,
                        "bolt_authority": True,
                        "owner": self.trooper.get_path_name(),
                        "instigator": self.trooper.get_path_name(),
                        "muzzle_socket": "Muzzle",
                        "muzzle_location_at_fire": vec(self.muzzle_at_fire),
                        "bolt_location_when_observed": vec(bolt.get_actor_location()),
                        "muzzle_to_bolt_distance_cm": muzzle_distance,
                    }
                    self.set_phase("APPROACH_SHIP")
            elif self.phase == "APPROACH_SHIP":
                require(elapsed <= 35.0, "Trooper could not approach starter ship through radial movement")
                require(self.ship is not None, "Starter ship unavailable during approach")
                ship_distance = distance(self.trooper.get_actor_location(), self.ship.get_actor_location())
                if ship_distance <= 1200.0:
                    self.inject("move")
                    self.inject("sprint")
                    self.report["tests"]["ship_approach"] = {"distance_cm": ship_distance, "trooper": vec(self.trooper.get_actor_location()), "ship": vec(self.ship.get_actor_location())}
                    self.set_phase("ENTER_SETTLE")
                else:
                    self.face_tangent_toward(self.ship.get_actor_location())
                    self.inject("sprint", x=1.0)
                    self.inject("move", y=1.0)
            elif self.phase == "ENTER_SETTLE":
                require(elapsed <= 5.0, "Ship-entry settle timeout")
                if elapsed >= 0.5:
                    self.set_phase("ENTER_PULSE")
            elif self.phase == "ENTER_PULSE":
                if not self.enter_pulsed:
                    self.enter_pulsed = True
                    before_contexts = input_context_state(self.trooper)
                    require(before_contexts == {"on_foot": True, "ship": False}, f"Pre-entry context drift: {before_contexts}")
                    self.inject("interact", x=1.0)
                    self.set_phase("WAIT_SHIP_POSSESSION", reset_motion=False)
            elif self.phase == "WAIT_SHIP_POSSESSION":
                require(elapsed <= 12.0, "F/Interact action did not possess the A01 StarSparrow")
                possessed = unreal.GameplayStatics.get_player_pawn(self.world, 0)
                if possessed == self.ship:
                    contexts = input_context_state(self.ship)
                    require(contexts == {"on_foot": False, "ship": True}, f"Ship input-context switch failed: {contexts}")
                    require(self.ship.get_pilot() == self.trooper, "Ship pilot relationship was not established")
                    require(actor_hidden_in_game(self.trooper), "Possessed Trooper is not hidden")
                    require(not self.trooper.get_actor_enable_collision(), "Possessed Trooper collision remains enabled")
                    self.report["tests"]["f_context_ship_entry"] = {
                        "serialized_physical_key": "F",
                        "runtime_action": ACTIONS["interact"],
                        "possessed_class": SHIP_CLASS,
                        "pilot": self.trooper.get_path_name(),
                        "input_contexts": contexts,
                        "trooper_hidden": True,
                        "trooper_collision_disabled": True,
                    }
                    self.begin_ship_motion_phase("SHIP_ASCEND")
            elif self.phase == "SHIP_ASCEND":
                require(elapsed <= 20.0, "Ship upward-flight timeout")
                self.inject("ship_move", z=1.0)
                motion = self.ship_motion()
                if motion["radial_delta_cm"] >= 1000.0:
                    motion["input"] = {"axis": "up", "value": 1.0, "serialized_key": "SpaceBar"}
                    self.report["tests"]["ship_up"] = motion
                    self.begin_ship_motion_phase("SHIP_ASCEND_SETTLE")
            elif self.phase == "SHIP_ASCEND_SETTLE":
                require(elapsed <= 8.0, "Ship ascent settle timeout")
                self.inject("ship_move")
                if length(self.ship.get_velocity()) <= 100.0 and elapsed >= 0.5:
                    self.begin_ship_motion_phase("SHIP_FORWARD")
            elif self.phase == "SHIP_FORWARD":
                require(elapsed <= 20.0, "Ship forward-flight timeout")
                self.inject("ship_move", x=1.0)
                motion = self.ship_motion()
                if motion["displacement_cm"] >= MIN_SHIP_DISPLACEMENT_CM:
                    displacement = normalized(sub(self.ship.get_actor_location(), self.phase_start_location))
                    forward_dot = dot(displacement, normalized(self.phase_start_forward))
                    require(forward_dot >= 0.60, f"Ship forward displacement direction mismatch: {forward_dot}")
                    motion.update({"input": {"axis": "forward", "value": 1.0, "serialized_key": "W"}, "displacement_dot_initial_forward": forward_dot})
                    self.report["tests"]["ship_forward"] = motion
                    self.begin_ship_motion_phase("SHIP_FORWARD_SETTLE")
            elif self.phase == "SHIP_FORWARD_SETTLE":
                require(elapsed <= 8.0, "Ship forward settle timeout")
                self.inject("ship_move")
                if length(self.ship.get_velocity()) <= 100.0 and elapsed >= 0.5:
                    self.begin_ship_motion_phase("SHIP_STRAFE")
            elif self.phase == "SHIP_STRAFE":
                require(elapsed <= 20.0, "Ship strafe-flight timeout")
                self.inject("ship_move", y=1.0)
                motion = self.ship_motion()
                if motion["displacement_cm"] >= MIN_SHIP_DISPLACEMENT_CM:
                    displacement = normalized(sub(self.ship.get_actor_location(), self.phase_start_location))
                    right_dot = dot(displacement, normalized(self.phase_start_right))
                    require(right_dot >= 0.50, f"Ship strafe displacement direction mismatch: {right_dot}")
                    motion.update({"input": {"axis": "strafe_right", "value": 1.0, "serialized_key": "D"}, "displacement_dot_initial_right": right_dot})
                    self.report["tests"]["ship_strafe"] = motion
                    self.begin_ship_motion_phase("SHIP_STRAFE_SETTLE")
            elif self.phase == "SHIP_STRAFE_SETTLE":
                require(elapsed <= 8.0, "Ship strafe settle timeout")
                self.inject("ship_move")
                if length(self.ship.get_velocity()) <= 100.0 and elapsed >= 0.5:
                    self.begin_ship_motion_phase("SHIP_DESCEND")
            elif self.phase == "SHIP_DESCEND":
                require(elapsed <= 20.0, "Ship downward-flight timeout")
                self.inject("ship_move", z=-1.0)
                motion = self.ship_motion()
                if motion["radial_delta_cm"] <= -500.0:
                    motion["input"] = {"axis": "down", "value": -1.0, "serialized_key": "LeftControl"}
                    self.report["tests"]["ship_down"] = motion
                    self.begin_ship_motion_phase("SHIP_LOOK")
            elif self.phase == "SHIP_LOOK":
                require(elapsed <= 6.0, "Ship look-input timeout")
                self.inject("ship_look", x=0.75, y=-0.45)
                if elapsed >= 1.0:
                    forward_dot = dot(normalized(self.phase_start_forward), normalized(self.ship.get_actor_forward_vector()))
                    require(forward_dot <= 0.995, f"Ship look action did not rotate the craft: {forward_dot}")
                    self.report["tests"]["ship_mouse_look"] = {
                        "serialized_key": "Mouse2D",
                        "action": ACTIONS["ship_look"],
                        "initial_forward": vec(self.phase_start_forward),
                        "final_forward": vec(self.ship.get_actor_forward_vector()),
                        "forward_dot": forward_dot,
                    }
                    self.begin_ship_motion_phase("SHIP_ROLL")
            elif self.phase == "SHIP_ROLL":
                require(elapsed <= 6.0, "Ship roll-input timeout")
                self.inject("ship_roll", x=0.8)
                if elapsed >= 1.0:
                    up_dot = dot(normalized(self.phase_start_up), normalized(self.ship.get_actor_up_vector()))
                    require(up_dot <= 0.995, f"Ship roll action did not rotate the craft: {up_dot}")
                    self.report["tests"]["ship_roll"] = {
                        "serialized_keys": ["Q", "E"],
                        "action": ACTIONS["ship_roll"],
                        "initial_up": vec(self.phase_start_up),
                        "final_up": vec(self.ship.get_actor_up_vector()),
                        "up_dot": up_dot,
                    }
                    self.begin_ship_motion_phase("SHIP_CRUISE")
            elif self.phase == "SHIP_CRUISE":
                require(elapsed <= 8.0, "Ship cruise-speed timeout")
                self.inject("ship_move", x=1.0)
                motion = self.ship_motion()
                if elapsed >= 2.0:
                    require(motion["max_speed_cm_s"] >= 2000.0, f"Ship cruise speed too small: {motion}")
                    motion["input"] = {"axis": "forward", "boost": False}
                    self.report["tests"]["ship_cruise"] = motion
                    self.begin_ship_motion_phase("SHIP_COAST")
            elif self.phase == "SHIP_COAST":
                require(elapsed <= 8.0, "Ship coast-to-boost timeout")
                self.inject("ship_move")
                self.inject("ship_boost")
                if elapsed >= 2.0:
                    self.begin_ship_motion_phase("SHIP_BOOST")
            elif self.phase == "SHIP_BOOST":
                require(elapsed <= 8.0, "Ship boost timeout")
                self.inject("ship_boost", x=1.0)
                self.inject("ship_move", x=1.0)
                motion = self.ship_motion()
                if elapsed >= 2.0:
                    cruise = self.report["tests"]["ship_cruise"]["max_speed_cm_s"]
                    require(motion["max_speed_cm_s"] >= cruise * 1.20, f"Boost did not exceed cruise telemetry: cruise={cruise} boost={motion}")
                    motion["input"] = {"axis": "forward", "boost": True, "serialized_key": "LeftShift"}
                    motion["speed_ratio_vs_cruise"] = motion["max_speed_cm_s"] / max(1.0, cruise)
                    self.report["tests"]["ship_boost"] = motion
                    self.set_phase("SHIP_EXIT_PULSE")
            elif self.phase == "SHIP_EXIT_PULSE":
                if not self.exit_pulsed:
                    self.exit_pulsed = True
                    self.inject("ship_move")
                    self.inject("ship_boost")
                    self.inject("ship_exit", x=1.0)
                    self.set_phase("WAIT_TROOPER_REPOSSESSION", reset_motion=False)
            elif self.phase == "WAIT_TROOPER_REPOSSESSION":
                require(elapsed <= 20.0, "F/Exit action did not restore Trooper possession")
                possessed = unreal.GameplayStatics.get_player_pawn(self.world, 0)
                if possessed == self.trooper:
                    contexts = input_context_state(self.trooper)
                    require(contexts == {"on_foot": True, "ship": False}, f"On-foot input-context restoration failed: {contexts}")
                    require(self.ship.get_pilot() is None, "Ship retained pilot after exit")
                    require(not actor_hidden_in_game(self.trooper), "Trooper remains hidden after exit")
                    require(self.trooper.get_actor_enable_collision(), "Trooper collision was not restored after exit")
                    safety = self.verify_safe_exit()
                    safety.update({
                        "serialized_physical_key": "F",
                        "runtime_action": ACTIONS["ship_exit"],
                        "restored_pawn_class": PLAYER_CLASS,
                        "input_contexts": contexts,
                    })
                    self.report["tests"]["f_context_ship_exit"] = safety
                    self.request_stop()
            elif self.phase == "WAIT_PIE_STOP":
                require(elapsed <= 30.0, "PIE teardown timeout")
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None:
                    self.finalize_pass()
                    return
            elif self.phase == "ABORT_WAIT_PIE_STOP":
                if elapsed >= 30.0 or (not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None):
                    self.finalize_failure()
                    return
            self.publish_state()
        except Exception as error:
            self.begin_failure(error)


try:
    _REDMMO_A01_PIE_VALIDATION = A01PIEValidation()
    _REDMMO_A01_PIE_VALIDATION.start()
except Exception as bootstrap_error:
    unreal.log_error("REDMMO_A01_PIE_VALIDATION_BOOTSTRAP_FAIL " + str(bootstrap_error))
    try:
        unreal.SystemLibrary.quit_editor()
    except Exception:
        pass
