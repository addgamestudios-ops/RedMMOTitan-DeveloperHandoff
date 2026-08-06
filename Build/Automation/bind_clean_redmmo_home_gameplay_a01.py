"""Bind the authenticated A01 Trooper/ship GameMode to the RedMMO PPG home map.

Required environment variables:

``REDMMO_HOME_BIND_A01_CHECKPOINT_MANIFEST`` must name the manifest produced by
``create_clean_redmmo_home_gameplay_bind_a01_checkpoint.py``.

``REDMMO_HOME_BIND_A01_REPORT`` must name a new JSON file below
``D:\RedMMOTitanWindowsData\Diagnostics``.  The report is published atomically.

This Unreal Python transaction loads only the real RedMMO PPG home map, changes
only its WorldSettings GameMode override, removes exactly one authenticated
visual-only R12 ship actor, and saves only that map.  It does not run PIE,
MapCheck, generation, or runtime validation; those remain fresh-process gates.
"""

from __future__ import annotations

import hashlib
import json
import os
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
PROJECT_SHA256 = "54E664A24FA5E9129C022740EE624F84389F1825AA9A4AE07D5E99DD783F382E"
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT_ROOT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HOME_SHA256_BEFORE = "1821ED915E924085A2D6B3E1A85984A0F207C116EFF32AC974E8F0B7CD217F87"

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

SOURCE_SHIP = PROJECT_ROOT / r"Content\RedMMO\Ships\BP_RedModularStarSparrow.uasset"
SOURCE_SHIP_SHA256 = "A8A6E128C2A08AE95A745B3A70C47A372339F314C67C6CE37539A25B67DC78C9"
OLD_VISUAL_BP = PROJECT_ROOT / r"Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset"
OLD_VISUAL_BP_SHA256 = "C9FDCF7D0FE89DACE39D418B79A7951C37C699C1FEA7E485C85670B2AB864BD6"
OLD_GAME_MODE_FILE = PROJECT_ROOT / r"Content\RedMMO\Gameplay\Player\GM_RedPlanet_R11.uasset"
OLD_GAME_MODE_SHA256 = "0696DE6039A5389BF0F872DB84D970E981C69184CD3AEA0279D89001B98BBEBD"
PPG_PLANET_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\DA_PPG_HomeWorld_StylizedBinding_R10O.uasset"
PPG_PLANET_SHA256 = "7C6835CA50EBB06B4C94AA6D1E8B0419B1E0ACF09A44D5CEA5B670FBD5865C5A"

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

ROOT = "/Game/RedMMO/Gameplay/Trooper/A01"
EXPECTED_PACKAGES = (
    ROOT + "/Input/IA_RedMove",
    ROOT + "/Input/IA_RedLook",
    ROOT + "/Input/IA_RedJump",
    ROOT + "/Input/IA_RedSprint",
    ROOT + "/Input/IA_RedFire",
    ROOT + "/Input/IA_RedADS",
    ROOT + "/Input/IA_RedInteract",
    ROOT + "/Input/IMC_RedTrooper_A01",
    ROOT + "/Input/IA_RedShipMove",
    ROOT + "/Input/IA_RedShipLook",
    ROOT + "/Input/IA_RedShipRoll",
    ROOT + "/Input/IA_RedShipBoost",
    ROOT + "/Input/IA_RedShipExit",
    ROOT + "/Input/IMC_RedShip_A01",
    ROOT + "/Combat/BP_RedBolt_Trooper_A01",
    ROOT + "/Player/BP_RedTrooperPlayer_A01",
    ROOT + "/Ship/BP_RedModularStarSparrow_Trooper_A01",
    ROOT + "/Player/GM_RedTrooperPPG_A01",
)

GAME_MODE_CLASS = ROOT + "/Player/GM_RedTrooperPPG_A01.GM_RedTrooperPPG_A01_C"
EXPECTED_OLD_GAME_MODE_CLASS = "/Game/RedMMO/Gameplay/Player/GM_RedPlanet_R11.GM_RedPlanet_R11_C"
OLD_VISUAL_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
OLD_VISUAL_CLASS = "/Game/RedMMO/Gameplay/World/BP_RedParkedStarSparrow_R12.BP_RedParkedStarSparrow_R12_C"
EXPECTED_ACTORS_BEFORE = 12
EXPECTED_ACTORS_AFTER = 11
PPG_SPAWNER_CLASS = "PlanetSpawnerBP_C"
PPG_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/DA_PPG_HomeWorld_StylizedBinding_R10O"
PPG_WATER = "/PPG/Water/Materials/M_PlanetaryOceanWater"

PROVIDER_PORTS = (5353, 8000, 8765)
CHECKPOINT_ENV = "REDMMO_HOME_BIND_A01_CHECKPOINT_MANIFEST"
REPORT_ENV = "REDMMO_HOME_BIND_A01_REPORT"
ROLLBACK_ROOT = Path(r"D:\RedMMOTitanWindowsData\Rollback")
DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")


class BindError(RuntimeError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise BindError(message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def canonical_under(value: str, root: Path, must_exist: bool) -> Path:
    require(bool(value), "Required path environment variable is missing")
    path = Path(value).resolve(strict=must_exist)
    resolved_root = root.resolve(strict=True)
    require(os.path.commonpath([str(path), str(resolved_root)]) == str(resolved_root), f"Unsafe path outside {resolved_root}: {path}")
    return path


def report_path() -> Path:
    path = canonical_under(os.environ.get(REPORT_ENV, ""), DIAGNOSTICS_ROOT, must_exist=False)
    require(path.suffix.lower() == ".json", "Bind report must be JSON")
    require(not os.path.lexists(path), f"Bind report no-clobber failed: {path}")
    return path


def checkpoint_path() -> Path:
    path = canonical_under(os.environ.get(CHECKPOINT_ENV, ""), ROLLBACK_ROOT, must_exist=True)
    require(path.name == "manifest.json", "Unexpected checkpoint manifest name")
    require(path.parent.name.startswith("RedMMO_HomeGameplayBind_A01_"), "Unexpected checkpoint directory")
    return path


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    getter = getattr(value, "get_path_name", None)
    path = getter() if callable(getter) else str(value)
    return str(path).split(":", 1)[0]


def package_path(value: Any) -> str | None:
    path = asset_path(value)
    if not path:
        return None
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def package_file(package: str) -> Path:
    require(package.startswith("/Game/"), f"Unsafe package path: {package}")
    relative = package[len("/Game/") :].replace("/", os.sep) + ".uasset"
    result = (PROJECT_ROOT / "Content" / relative).resolve(strict=False)
    content = (PROJECT_ROOT / "Content").resolve(strict=True)
    require(os.path.commonpath([str(result), str(content)]) == str(content), f"Package escaped project Content: {package}")
    return result


def dirty_packages() -> dict[str, list[str]]:
    content = sorted(
        value
        for value in {
            package_path(item)
            for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        }
        if value
    )
    maps = sorted(
        value
        for value in {
            package_path(item)
            for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        }
        if value
    )
    return {
        "content": content,
        "maps": maps,
    }


def no_dirty() -> bool:
    value = dirty_packages()
    return value == {"content": [], "maps": []}


def pie_gate() -> dict[str, Any]:
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    worlds = list(unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=False))
    output = {"is_in_play_in_editor": bool(level.is_in_play_in_editor()), "pie_world_count": len(worlds)}
    require(not output["is_in_play_in_editor"] and output["pie_world_count"] == 0, "PIE is active")
    return output


def provider_gate() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.25)
        try:
            code = probe.connect_ex(("127.0.0.1", port))
        finally:
            probe.close()
        records.append({"port": port, "closed": code != 0, "connect_ex": code})
    require(all(item["closed"] for item in records), "AI/MCP/provider listener is active")
    return records


def verify_hashes(records: dict[Path, str], label: str) -> dict[str, str]:
    output: dict[str, str] = {}
    for path, expected in records.items():
        require(path.is_file(), f"{label} is missing: {path}")
        actual = sha256(path)
        require(actual == expected, f"{label} hash drift: {path} expected={expected} actual={actual}")
        output[str(path)] = actual
    return output


def load_authenticated_report(path: Path, expected: str, label: str) -> dict[str, Any]:
    require(path.is_file() and sha256(path) == expected, f"{label} missing or hash drift")
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    require(isinstance(value, dict), f"{label} is not an object")
    return value


def verify_assets() -> list[dict[str, Any]]:
    build = load_authenticated_report(BUILD_REPORT, BUILD_REPORT_SHA256, "A01 build report")
    fresh = load_authenticated_report(FRESH_REPORT, FRESH_REPORT_SHA256, "A01 fresh report")
    expected = set(EXPECTED_PACKAGES)
    require(build.get("status") == "pass_created_compiled_saved_same_process_readback", "A01 build report did not pass")
    require(build.get("target_count") == 18, "A01 build target count drift")
    require(set(build.get("created_assets", [])) == expected, "A01 created-asset set drift")
    saved_entries = build.get("saved_assets")
    require(isinstance(saved_entries, list) and len(saved_entries) == 18, "A01 saved-asset record count drift")
    require(all(isinstance(item, dict) for item in saved_entries), "Malformed A01 saved-asset record")
    require({item.get("package") for item in saved_entries} == expected, "A01 saved-asset set drift")
    saved_by_package = {item["package"]: item for item in saved_entries}
    require(build.get("map_saved") is False and build.get("config_saved") is False, "A01 build wrote map/config")
    require(build.get("vendor_assets_modified") is False and build.get("map_mutation_authorized") is False, "A01 build scope drift")
    require(build.get("home_map_sha256_after") == HOME_SHA256_BEFORE, "A01 build map hash drift")
    require(build.get("source_ship_sha256_after") == SOURCE_SHIP_SHA256, "A01 build source-ship drift")
    require(build.get("protected_hashes_after") == {str(path): value for path, value in PROTECTED_FILES.items()}, "A01 build protected set drift")
    require(fresh.get("status") == "pass_fresh_process_serialized_readback", "A01 fresh report did not pass")
    require(fresh.get("build_report", {}).get("sha256") == BUILD_REPORT_SHA256, "Fresh report references a different build")
    require(fresh.get("home_map_sha256_after") == HOME_SHA256_BEFORE, "Fresh report map hash drift")
    require(fresh.get("source_ship_sha256_after") == SOURCE_SHIP_SHA256, "Fresh source-ship drift")
    require(fresh.get("protected_hashes") == {str(path): value for path, value in PROTECTED_FILES.items()}, "Fresh protected set drift")
    require(fresh.get("map_saved") is False and fresh.get("assets_saved") is False, "Fresh verifier wrote content")
    require(fresh.get("pie_active") is False and fresh.get("pie_world_count") == 0, "Fresh verifier PIE drift")
    entries = fresh.get("files")
    require(isinstance(entries, list) and len(entries) == 18, "Fresh file count drift")
    require({item.get("package") for item in entries if isinstance(item, dict)} == expected, "Fresh package set drift")
    output: list[dict[str, Any]] = []
    for item in entries:
        require(isinstance(item, dict), "Malformed fresh package record")
        package = item.get("package")
        path = package_file(package)
        require(path.is_file(), f"A01 package missing: {path}")
        expected_hash = str(item.get("sha256", "")).upper()
        actual = sha256(path)
        require(len(expected_hash) == 64 and actual == expected_hash, f"A01 package hash drift: {package}")
        require(Path(str(item.get("file", ""))).resolve(strict=False) == path, f"A01 package file-path drift: {package}")
        saved = saved_by_package[package]
        require(Path(str(saved.get("file", ""))).resolve(strict=False) == path, f"Build saved-file path mismatch for {package}")
        require(str(saved.get("sha256", "")).upper() == expected_hash, f"Build/fresh hash mismatch for {package}")
        require(int(saved.get("bytes", -1)) == path.stat().st_size, f"Build saved-byte count mismatch for {package}")
        output.append(
            {
                "package": package,
                "file": str(path),
                "bytes": path.stat().st_size,
                "sha256": actual,
            }
        )
    return sorted(output, key=lambda item: item["package"])


def verify_checkpoint(path: Path, assets: list[dict[str, Any]]) -> dict[str, Any]:
    require(path.is_file(), "Checkpoint manifest is missing")
    with path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    require(manifest.get("schema") == "redmmo.home_gameplay_bind.a01.rollback.v1", "Checkpoint schema drift")
    require(manifest.get("status") == "PASS_READY_FOR_MAP_BIND", "Checkpoint did not pass")
    require(manifest.get("home_map") == str(HOME_FILE), "Checkpoint home path drift")
    require(manifest.get("home_map_sha256") == HOME_SHA256_BEFORE, "Checkpoint home hash drift")
    require(manifest.get("evidence", {}).get("build_report") == {"path": str(BUILD_REPORT), "sha256": BUILD_REPORT_SHA256}, "Checkpoint build evidence drift")
    require(manifest.get("evidence", {}).get("fresh_report") == {"path": str(FRESH_REPORT), "sha256": FRESH_REPORT_SHA256}, "Checkpoint fresh evidence drift")
    require(manifest.get("source_ship") == {"path": str(SOURCE_SHIP), "sha256": SOURCE_SHIP_SHA256}, "Checkpoint source ship drift")
    require(manifest.get("protected_hashes") == {str(item): value for item, value in PROTECTED_FILES.items()}, "Checkpoint protected set drift")
    require(manifest.get("a01_assets") == assets, "Checkpoint A01 asset set drift")
    copy_path = Path(str(manifest.get("rollback_map_copy", ""))).resolve(strict=True)
    require(copy_path.parent == path.parent and copy_path.name == "RedMMO_PPG_HomeWorld.umap.pre_bind_a01", "Checkpoint copy path drift")
    require(copy_path.is_file() and sha256(copy_path) == HOME_SHA256_BEFORE, "Checkpoint map copy drift")
    require(manifest.get("rollback_map_copy_sha256") == HOME_SHA256_BEFORE, "Checkpoint copy evidence drift")
    require(
        sorted(item.name for item in path.parent.iterdir())
        == sorted(["RedMMO_PPG_HomeWorld.umap.pre_bind_a01", "manifest.json"]),
        "Checkpoint contains unexpected files",
    )
    return {"manifest": str(path), "manifest_sha256": sha256(path), "map_copy": str(copy_path), "map_copy_sha256": HOME_SHA256_BEFORE}


def tree_hashes(root: Path) -> list[dict[str, Any]]:
    require(root.is_dir(), f"Tree root is missing: {root}")
    output = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: str(item).lower()):
        output.append({"path": str(path.relative_to(root)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256(path)})
    return output


def actor_record(actor: Any) -> dict[str, Any]:
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return {
        "name": actor.get_name(),
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_path_name(),
        "location": [float(location.x), float(location.y), float(location.z)],
        "rotation": [float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
        "scale": [float(scale.x), float(scale.y), float(scale.z)],
    }


def actor_records(actors: list[Any]) -> list[dict[str, Any]]:
    return sorted((actor_record(actor) for actor in actors), key=lambda item: (item["name"], item["label"], item["class"]))


def verify_ppg(actors: list[Any]) -> dict[str, Any]:
    spawners = [actor for actor in actors if actor.get_class().get_name() == PPG_SPAWNER_CLASS]
    require(len(spawners) == 1, f"Expected one PPG spawner, found {len(spawners)}")
    spawner = spawners[0]
    planet = spawner.get_editor_property("planet_data")
    require(package_path(planet) == PPG_PLANET, "PPG PlanetData binding drift")
    require(bool(planet.get_editor_property("generate_water")), "PPG GenerateWater is disabled")
    water = package_path(planet.get_editor_property("water_material"))
    require(water == PPG_WATER, "PPG water material drift")
    return {
        "actor": actor_record(spawner),
        "planet_data": package_path(planet),
        "generate_water": True,
        "water_material": water,
    }


def current_map(world: Any) -> str:
    value = world.get_path_name().split(":", 1)[0]
    return value.rsplit(".", 1)[0]


_EXIT = {"handle": None}


def schedule_exit(delay: float = 8.0) -> None:
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


def main() -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": "redmmo.home_gameplay_bind.a01.transaction.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
        "claim_limit": (
            "Same-process exact map bind and save only. Pending fresh-process reload, MapCheck, "
            "PIE, controls, animation-in-motion, ship operation, collision, visual, package, and multiplayer evidence."
        ),
        "authorized_changes": {
            "world_settings_default_game_mode": GAME_MODE_CLASS,
            "removed_actor_label": OLD_VISUAL_LABEL,
            "removed_actor_class": OLD_VISUAL_CLASS,
        },
        "rollback_instructions": (
            "Close Unreal and all Unreal/build helpers. Read the authenticated checkpoint manifest, "
            "verify its map-copy hash, and copy only rollback_map_copy over the exact home_map path."
        ),
    }
    report_target: Path | None = None
    try:
        report_target = report_path()
        checkpoint = checkpoint_path()
        actual_project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(actual_project == PROJECT_FILE.resolve(strict=True), f"Wrong Unreal project: {actual_project}")
        require(PROJECT_FILE.is_file() and sha256(PROJECT_FILE) == PROJECT_SHA256, "Project descriptor drift")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == HOME_SHA256_BEFORE, "Home-map preimage drift")
        require(no_dirty(), f"Dirty packages before bind: {dirty_packages()}")
        report["pie_gate_before"] = pie_gate()
        report["provider_gate_before"] = provider_gate()

        assets = verify_assets()
        report["checkpoint"] = verify_checkpoint(checkpoint, assets)
        tracked = {
            SOURCE_SHIP: SOURCE_SHIP_SHA256,
            OLD_VISUAL_BP: OLD_VISUAL_BP_SHA256,
            OLD_GAME_MODE_FILE: OLD_GAME_MODE_SHA256,
            PPG_PLANET_FILE: PPG_PLANET_SHA256,
            **PROTECTED_FILES,
        }
        tracked_before = verify_hashes(tracked, "tracked source/protected file")
        config_before = tree_hashes(PROJECT_ROOT / "Config")

        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None and current_map(world) == HOME_MAP, "Exact home-map load failed")
        require(no_dirty(), f"Exact home-map load dirtied packages: {dirty_packages()}")
        report["pie_gate_after_load"] = pie_gate()
        report["provider_gate_after_load"] = provider_gate()

        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors_before = list(subsystem.get_all_level_actors())
        require(len(actors_before) == EXPECTED_ACTORS_BEFORE, f"Home actor count drift: {len(actors_before)}")
        records_before = actor_records(actors_before)
        ppg_before = verify_ppg(actors_before)

        matches = [actor for actor in actors_before if actor.get_actor_label() == OLD_VISUAL_LABEL]
        require(len(matches) == 1, f"Expected one old visual ship, found {len(matches)}")
        old_visual = matches[0]
        require(old_visual.get_class().get_path_name() == OLD_VISUAL_CLASS, f"Old visual ship class drift: {old_visual.get_class().get_path_name()}")
        removed = actor_record(old_visual)

        world_settings = world.get_world_settings()
        require(world_settings is not None, "WorldSettings is unavailable")
        old_game_mode = world_settings.get_editor_property("default_game_mode")
        require(asset_path(old_game_mode) == EXPECTED_OLD_GAME_MODE_CLASS, f"Existing GameMode drift: {asset_path(old_game_mode)}")
        new_game_mode = unreal.load_class(None, GAME_MODE_CLASS)
        require(new_game_mode is not None and new_game_mode.get_path_name() == GAME_MODE_CLASS, "A01 GameMode class failed to load")

        world_settings.set_editor_property("default_game_mode", new_game_mode)
        require(world_settings.get_editor_property("default_game_mode") == new_game_mode, "GameMode readback mismatch")
        require(subsystem.destroy_actor(old_visual), "Exact old visual ship deletion failed")

        dirty_before_save = dirty_packages()
        require(dirty_before_save["content"] == [], f"Content dirtied during map bind: {dirty_before_save}")
        require(set(dirty_before_save["maps"]).issubset({HOME_MAP}) and HOME_MAP in dirty_before_save["maps"], f"Unexpected dirty map set: {dirty_before_save}")

        actors_mutated = list(subsystem.get_all_level_actors())
        require(len(actors_mutated) == EXPECTED_ACTORS_AFTER, "Actor count did not decrease by exactly one")
        expected_records = [item for item in records_before if item["name"] != removed["name"]]
        require(actor_records(actors_mutated) == expected_records, "Actor label/class/transform drift beyond exact ship removal")
        require(not any(actor.get_actor_label() == OLD_VISUAL_LABEL for actor in actors_mutated), "Old visual ship still exists")
        require(verify_ppg(actors_mutated) == ppg_before, "PPG spawner/PlanetData contract changed before save")

        level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        require(level.save_current_level(), "Saving the exact current home level failed")
        require(no_dirty(), f"Dirty packages remain after home-map save: {dirty_packages()}")

        actors_after = list(subsystem.get_all_level_actors())
        require(len(actors_after) == EXPECTED_ACTORS_AFTER, "Post-save actor count drift")
        require(actor_records(actors_after) == expected_records, "Post-save actor label/class/transform drift")
        ppg_after = verify_ppg(actors_after)
        require(ppg_after == ppg_before, "PPG spawner/PlanetData contract changed after save")
        require(world_settings.get_editor_property("default_game_mode") == new_game_mode, "Post-save GameMode readback mismatch")

        home_after = sha256(HOME_FILE)
        require(home_after != HOME_SHA256_BEFORE, "Home map did not serialize the authorized bind")
        require(verify_hashes(tracked, "post-bind tracked source/protected file") == tracked_before, "Tracked source/protected record drift")
        require(tree_hashes(PROJECT_ROOT / "Config") == config_before, "Project Config tree changed")
        require(verify_assets() == assets, "A01 asset files changed during map bind")
        report["provider_gate_after_save"] = provider_gate()
        report["pie_gate_after_save"] = pie_gate()

        report.update(
            {
                "status": "PASS_MAP_BOUND_PENDING_FRESH_RELOAD_MAPCHECK_PIE",
                "completed_utc": now(),
                "home_map": HOME_MAP,
                "home_map_file": str(HOME_FILE),
                "home_map_sha256_before": HOME_SHA256_BEFORE,
                "home_map_sha256_after": home_after,
                "actor_count_before": len(actors_before),
                "actor_count_after": len(actors_after),
                "removed_actor": removed,
                "world_settings": {
                    "path": world_settings.get_path_name(),
                    "default_game_mode_before": EXPECTED_OLD_GAME_MODE_CLASS,
                    "default_game_mode_after": GAME_MODE_CLASS,
                },
                "ppg_before": ppg_before,
                "ppg_after": ppg_after,
                "preserved_actor_records": expected_records,
                "dirty_packages_before_save": dirty_before_save,
                "dirty_packages_after": dirty_packages(),
                "tracked_hashes_unchanged": tracked_before,
                "a01_asset_count": len(assets),
                "map_saved": True,
                "config_saved": False,
                "content_assets_saved": False,
                "fresh_reload_mapcheck_required": True,
                "pie_required": True,
            }
        )
    except Exception as exc:
        report.update({"status": "FAIL", "completed_utc": now(), "error": str(exc), "traceback": traceback.format_exc(), "dirty_packages_at_failure": dirty_packages()})
    finally:
        try:
            if report_target is not None:
                atomic_json(report_target, report)
        finally:
            if report.get("status", "").startswith("PASS"):
                unreal.log("REDMMO_HOME_GAMEPLAY_BIND_A01 " + report["status"])
            else:
                unreal.log_error("REDMMO_HOME_GAMEPLAY_BIND_A01 " + report.get("status", "FAIL") + " " + report.get("error", ""))
            schedule_exit()
    return report


main()
